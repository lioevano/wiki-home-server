"""Migração dos pinos antigos (spec 2026-10-28): Traefik v3, Authelia 4.39, cloudflared, Portainer e Postgres 17.

O `authelia validate-config` só roda com o binário da versão fixada (test_fotos_arquivos); estes testes conferem a
forma da configuração mesmo sem ele."""
from __future__ import annotations

import yaml

from test_fotos_arquivos import DOM, _authelia
from test_observabilidade import ROOT, render

CORE = ROOT / "server/docker/stacks/core/docker-compose.yml"


def _core() -> dict:
    return yaml.safe_load(CORE.read_text(encoding="utf-8"))["services"]


def test_versoes_da_stack_core():
    s = _core()
    assert s["traefik"]["image"] == "traefik:v3.7.16"
    assert s["authelia"]["image"] == "authelia/authelia:4.39.28"
    assert s["cloudflared"]["image"] == "cloudflare/cloudflared:2026.10.5"


def test_postgres_17_menos_o_do_immich():
    """Sem dados ainda, todos os Postgres ficam na mesma versão principal (o do Immich segue o Immich)."""
    achados = []
    for compose in sorted((ROOT / "server/docker/stacks").glob("*/docker-compose.yml")):
        for nome, svc in yaml.safe_load(compose.read_text(encoding="utf-8"))["services"].items():
            img = str(svc.get("image", ""))
            if "postgres:" in img and "immich" not in img and not img.endswith("postgres:17-alpine"):
                achados.append(f"{compose.parent.name}/{nome}: {img}")
    assert achados == []


def test_forward_auth_no_endpoint_novo():
    lab = _core()["authelia"]["labels"]
    pre = "traefik.http.middlewares.authelia-forwardauth.forwardauth."
    assert lab[pre + "address"] == "http://authelia:9091/api/authz/forward-auth"  # /api/verify é legado na 4.39
    # false e explícito (a v3.6.14+ avisa quando falta): com true, um X-Forwarded-Host forjado pela internet
    # faria o Authelia avaliar outro domínio (um bypass) e o Traefik entregar o domínio real.
    assert lab[pre + "trustForwardHeader"] == "false"
    assert lab[pre + "maxResponseBodySize"] == "8192"


def test_traefik_descarta_cabecalhos_com_underscore():
    cfg = yaml.safe_load(render("roles/infra/traefik-config/templates/traefik.yml.j2", base_domain=DOM,
                                letsencrypt_email="a@b.c"))
    assert cfg["entryPoints"]["traefik"]["address"] == ":8080"  # o do /ping, declarado para levar a opção
    for ep in ("web", "websecure", "traefik"):
        assert cfg["entryPoints"][ep]["http"]["aliasHeadersStrategy"] == "delete", ep
    assert "delayBeforeCheck:" not in (ROOT / "server/ansible/roles/infra/traefik-config/templates/traefik.yml.j2").read_text()


def test_authelia_sem_chaves_obsoletas():
    cfg = yaml.safe_load(_authelia())
    assert "jwt_secret" not in cfg and "default_redirection_url" not in cfg
    assert cfg["identity_validation"]["reset_password"]["jwt_secret"] == "j" * 64
    assert "domain" not in cfg["session"]
    assert cfg["session"]["cookies"] == [{"domain": DOM, "authelia_url": f"https://auth.{DOM}",
                                          "default_redirection_url": f"https://home.{DOM}"}]


def test_clientes_oidc_com_claims_no_id_token():
    """A 4.39 só põe os claims padrão no ID token; todos os clientes usam a política 'legado'."""
    oidc = yaml.safe_load(_authelia())["identity_providers"]["oidc"]
    legado = oidc["claims_policies"]["legado"]["id_token"]
    assert {"email", "groups", "name", "preferred_username"} <= set(legado)
    assert {c["client_id"]: c.get("claims_policy") for c in oidc["clients"]} == dict.fromkeys(
        ("immich", "nextcloud", "openwebui", "mcp", "langfuse"), "legado")


def test_defaults_mortos_removidos():
    for role in ("traefik-config", "authelia-config"):
        assert not (ROOT / f"server/ansible/roles/infra/{role}/defaults/main.yml").exists(), role


def _caminhos(valor, prefixo=""):
    """Caminhos de chave no formato do schema do Authelia: listas de mapas viram '[]'."""
    if isinstance(valor, dict):
        for k, v in valor.items():
            atual = f"{prefixo}.{k}" if prefixo else str(k)
            yield atual
            yield from _caminhos(v, atual)
    elif isinstance(valor, list):
        for item in valor:
            if isinstance(item, (dict, list)):
                yield from _caminhos(item, prefixo + "[]")


def test_authelia_so_chaves_validas():
    """Chave desconhecida é erro fatal no Authelia 4.39 (o validate-config da 4.38 saía com 0 mesmo assim).
    A lista vem do schema da versão fixada; os mapas ('*') aceitam qualquer nome."""
    import re
    fixada = re.search(r"authelia/authelia:(\S+)", CORE.read_text(encoding="utf-8")).group(1)
    arq = ROOT / f"tools/wikisync/tests/dados/authelia-{fixada}-chaves.txt"
    assert arq.exists(), f"atualize a lista de chaves para a versão {fixada}"
    chaves = [l for l in arq.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
    # O schema lista as folhas; os nós intermediários (access_control, session.cookies[]...) são os prefixos delas.
    nos = {c[:m.start()] for c in chaves for m in re.finditer(r"\.|\[\]", c)} | set(chaves)
    padroes = [re.compile("^" + re.escape(n).replace(r"\*", r"[^.\[\]]+") + "$") for n in nos]
    cfg = yaml.safe_load(_authelia())
    invalidas = sorted({c for c in _caminhos(cfg) if not any(p.match(c) for p in padroes)})
    assert invalidas == []


def test_portainer_http_so_na_rede_docker():
    """A 9000 (HTTP, usada pelo ops) não é publicada: senha e chave de API não passam em claro pela LAN."""
    t = yaml.safe_load((ROOT / "server/ansible/roles/infra/docker/tasks/main.yml").read_text(encoding="utf-8"))
    p = next(x for x in t if x.get("name") == "Deploy Portainer CE container")["community.docker.docker_container"]
    assert not any(":9000:" in porta for porta in p["ports"])
