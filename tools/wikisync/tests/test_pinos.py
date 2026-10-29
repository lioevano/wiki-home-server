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
    assert lab[pre + "trustForwardHeader"] == "true"  # explícito: a v3.6.14+ avisa quando falta
    assert lab[pre + "maxResponseBodySize"] == "8192"


def test_traefik_descarta_cabecalhos_com_underscore():
    cfg = yaml.safe_load(render("roles/infra/traefik-config/templates/traefik.yml.j2", base_domain=DOM,
                                letsencrypt_email="a@b.c"))
    for ep in ("web", "websecure"):
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
