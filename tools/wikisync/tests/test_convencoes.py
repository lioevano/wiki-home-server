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
