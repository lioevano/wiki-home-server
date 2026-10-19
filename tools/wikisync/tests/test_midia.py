"""Testes da stack de mídia (docker/stacks/media), do playbook de mídia e das integrações."""
from __future__ import annotations

import re

import yaml

from test_observabilidade import ROOT, render

MEDIA = ROOT / "server/docker/stacks/media/docker-compose.yml"
APPS = ROOT / "server/docker/stacks/apps/docker-compose.yml"
SERVICOS = {"jellyfin", "seerr", "sonarr", "radarr", "lidarr", "prowlarr", "bazarr",
            "gluetun", "qbittorrent", "flaresolverr", "recyclarr"}


def _svc(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))["services"]


def _env(servico) -> dict:
    env = servico.get("environment", {})
    if isinstance(env, dict):
        return env
    return dict(e.split("=", 1) for e in env)


def test_stack_media_tem_os_servicos_e_apps_nao():
    assert set(_svc(MEDIA)) == SERVICOS
    assert not (SERVICOS & set(_svc(APPS)))


def test_qbittorrent_so_pela_vpn():
    q = _svc(MEDIA)["qbittorrent"]
    assert q["network_mode"] == "service:gluetun"
    assert not ({"ports", "networks", "labels"} & set(q))
    assert q["depends_on"]["gluetun"]["condition"] == "service_healthy"


def test_data_de_uma_unica_origem():
    for nome, s in _svc(MEDIA).items():
        for v in s.get("volumes", []):
            destino = v.split(":")[1]
            if destino.startswith("/data"):
                assert v.startswith("${MEDIA_STACK_DATA_PATH}"), (nome, v)


def test_gluetun_porta_encaminhada():
    env = _env(_svc(MEDIA)["gluetun"])
    for k in ("VPN_PORT_FORWARDING", "PORT_FORWARD_ONLY", "VPN_PORT_FORWARDING_UP_COMMAND", "WIREGUARD_PRIVATE_KEY"):
        assert k in env, k
    assert env["WIREGUARD_PRIVATE_KEY"] == "${PROTONVPN_WIREGUARD_PRIVATE_KEY}"
    up = env["VPN_PORT_FORWARDING_UP_COMMAND"]
    assert "{{PORT}}" in up and "{{VPN_INTERFACE}}" in up and "127.0.0.1:8088" in up
    # '$' solto seria interpolado pelo Compose/Portainer (vira variável vazia)
    assert not re.search(r"(?<!\$)\$(?![\${])", up)


def test_exposicao_e_autenticacao():
    s = _svc(MEDIA)
    for nome, sub in (("jellyfin", "jellyfin"), ("seerr", "pedidos")):
        lab = s[nome]["labels"]
        assert f"Host(`{sub}.${{BASE_DOMAIN_FROM_VAULT}}`)" in str(lab)
        assert "authelia" not in str(lab)
    for nome in ("sonarr", "radarr", "lidarr", "prowlarr", "bazarr", "gluetun"):
        assert "authelia-forwardauth@docker" in str(s[nome]["labels"]), nome
    assert "qbittorrent.${BASE_DOMAIN_FROM_VAULT}" in str(s["gluetun"]["labels"])
    for app in ("sonarr", "radarr", "lidarr", "prowlarr"):
        env = _env(s[app])
        assert env[f"{app.upper()}__AUTH__APIKEY"] == f"${{{app.upper()}_API_KEY}}"
        assert env[f"{app.upper()}__AUTH__METHOD"] == "External"
