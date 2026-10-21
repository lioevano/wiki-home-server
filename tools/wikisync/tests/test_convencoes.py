"""Convenções da wiki (quadro da seção 0 do manual) que o wikisync não confere."""
from __future__ import annotations

import re

from test_observabilidade import ROOT

DOCS = ROOT / "wiki/docs"
# Páginas que citam o conteúdo de templates do Ansible (regras das integrações): podem mostrar {{ base_domain }}.
CITAM_TEMPLATES = {"02-visao-geral-arquitetura/10-indice-integracoes.md"}


def _fora_de_literais(texto: str) -> str:
    """Remove os blocos literais (title="ansible/…", "docker/…", "scripts/…") e os blocos jinja: lá o Jinja é o real.
    A cerca de fechamento tem a mesma indentação da de abertura (blocos dentro de listas e admonitions)."""
    return re.sub(r'^([ \t]*)```(?:jinja\b[^\n]*|[a-z]*[^\n]*title="(?:ansible|docker|scripts)/[^\n]*)\n.*?^\1```[ \t]*$',
                  "", texto, flags=re.S | re.M)


def test_fora_de_literais_respeita_a_indentacao():
    """Sentinelas: bloco jinja some; literal indentado some sem engolir a prosa seguinte."""
    assert "{{" not in _fora_de_literais("```jinja\n{{ base_domain }}\n```\n")
    texto = '    ```yaml title="ansible/x.yml"\n    a: {{ base_domain }}\n    ```\nprosa {{ base_domain }}\n```bash\necho\n```\n'
    resto = _fora_de_literais(texto)
    assert "a: {{" not in resto and "prosa {{ base_domain }}" in resto


def test_dominio_de_exemplo_em_prosa_e_compose():
    """Em prosa e em exemplos de compose, o domínio é seudominio.com ou ${BASE_DOMAIN_FROM_VAULT}, nunca {{ base_domain }}."""
    achados = []
    for pagina in sorted(DOCS.rglob("*.md")):
        rel = pagina.relative_to(DOCS).as_posix()
        if rel in CITAM_TEMPLATES or rel.startswith("01-manual-implementacao/"):
            continue  # o manual mostra os templates do Ansible por inteiro
        if "{{ base_domain }}" in _fora_de_literais(pagina.read_text(encoding="utf-8")):
            achados.append(rel)
    assert achados == []


def test_guias_numerados_sem_buraco():
    """Guias e manutenção numerados em sequência (wiki/AGENTS.md). A arquitetura (02) mantém o buraco do 08 de
    propósito: o catálogo (09) e o índice de integrações (10) são citados pelas skills e não mudam de caminho."""
    for secao in (DOCS / "03-guias-sustentacao", DOCS / "04-manutencao-recuperacao"):
        numeros = sorted(int(p.name[:2]) for p in secao.glob("[0-9][0-9]-*.md"))
        assert numeros == list(range(1, len(numeros) + 1)), secao.name


def test_full_deploy_cobre_todos_os_playbooks_de_volumes():
    """Um playbook setup-*-volumes.yml novo precisa entrar no full-deploy.yml (senão a reconstrução o esquece)."""
    import yaml
    pb = ROOT / "server/ansible/playbooks"
    importados = [p["import_playbook"] for p in yaml.safe_load((pb / "full-deploy.yml").read_text(encoding="utf-8"))]
    volumes = {p.name for p in pb.glob("setup-*-volumes.yml")}
    assert volumes <= set(importados), volumes - set(importados)
    assert len(importados) == len(set(importados)), "playbook repetido no full-deploy.yml"
    assert importados[:3] == ["setup-proxmox-host.yml", "setup-base-ubuntu.yml", "setup-core-networking.yml"]
    assert "setup-ai-keys.yml" not in importados and "vm-deploy.yml" not in importados


def test_imagens_com_versao():
    """Política de versões (spec 2026-10-21): nenhum compose usa :latest ou imagem sem tag. Imagens locais e as que
    vêm de variável ficam de fora (a versão está no group_vars)."""
    import yaml
    achados = []
    for compose in sorted((ROOT / "server/docker/stacks").glob("*/docker-compose.yml")):
        for nome, svc in (yaml.safe_load(compose.read_text(encoding="utf-8"))["services"] or {}).items():
            img = str(svc.get("image", ""))
            if not img or img.startswith(("${", "localhost/")):
                continue
            sem_digest = img.split("@", 1)[0]
            tag = sem_digest.rsplit(":", 1)[1] if ":" in sem_digest.rsplit("/", 1)[-1] else ""
            if ("@sha256:" not in img and not tag) or tag in ("latest", "main", "master", "develop", "nightly"):
                achados.append(f"{compose.parent.name}/{nome}: {img}")
    assert achados == []


def test_diun_observa_o_repositorio():
    """Com as versões fixadas, o Diun só avisa de versão nova se olhar as tags do repositório (watch_repo)."""
    import yaml
    for stack, diun in (("apps", "diun"), ("ai", "diun_ai")):
        svc = yaml.safe_load((ROOT / f"server/docker/stacks/{stack}/docker-compose.yml").read_text(encoding="utf-8"))["services"][diun]
        env = dict(e.split("=", 1) for e in svc["environment"])
        assert env["DIUN_DEFAULTS_WATCHREPO"] == "true"
        assert env["DIUN_DEFAULTS_SORTTAGS"] == "semver"
        assert env["DIUN_DEFAULTS_INCLUDETAGS"].split(" #")[0] == r"^v?\d+(\.\d+)+$$"  # $$ vira $ no compose
        assert int(env["DIUN_DEFAULTS_MAXTAGS"]) >= 1
