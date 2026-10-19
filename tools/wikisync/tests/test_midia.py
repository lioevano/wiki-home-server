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


# --- Playbook de mídia ---

PB = ROOT / "server/ansible/playbooks/setup-media-stack-volumes.yml"
APPS_CONFIG = ("JELLYFIN", "SEERR", "SONARR", "RADARR", "LIDARR", "PROWLARR", "BAZARR",
               "GLUETUN", "QBITTORRENT", "RECYCLARR")


def _tasks():
    return yaml.safe_load(PB.read_text(encoding="utf-8"))[0]["tasks"]


def test_media_env_com_segredos_e_0600():
    t = next(t for t in _tasks() if "media.env" in str(t.get("ansible.builtin.template", {}).get("dest", "")))
    assert t["ansible.builtin.template"]["mode"] == "0600"
    nomes = {c["name"] for c in t["vars"]["stack_configs"]}
    assert {"MEDIA_STACK_DATA_PATH", "SONARR_API_KEY", "RADARR_API_KEY", "LIDARR_API_KEY",
            "PROWLARR_API_KEY", "PROTONVPN_WIREGUARD_PRIVATE_KEY"} <= nomes
    assert {f"MEDIA_STACK_{a}_CONFIG_PATH" for a in APPS_CONFIG} <= nomes
    # o compose não usa nada que o .env não traga
    usadas = set(re.findall(r"\$\{([A-Z0-9_]+)\}", MEDIA.read_text(encoding="utf-8")))
    comuns = {"DOCKER_PUID", "DOCKER_PGID", "SYSTEM_TIMEZONE", "BASE_DOMAIN_FROM_VAULT"}
    assert usadas <= nomes | comuns, usadas - nomes - comuns


def test_arvore_data():
    texto = PB.read_text(encoding="utf-8")
    for p in ("torrents/movies", "torrents/tv", "torrents/music", "media/movies", "media/tv", "media/music"):
        assert p in texto, p


def test_recyclarr_renderiza():
    cfg = yaml.safe_load(render("templates/recyclarr.yml.j2",
                                arr_api_keys={"sonarr": "s" * 32, "radarr": "r" * 32}))
    assert cfg["sonarr"] and cfg["radarr"]
    assert "s" * 32 in str(cfg["sonarr"]) and "http://sonarr:8989" in str(cfg["sonarr"])
    assert "r" * 32 in str(cfg["radarr"]) and "http://radarr:7878" in str(cfg["radarr"])
    tarefa = next(t for t in _tasks() if "recyclarr.yml.j2" in str(t.get("ansible.builtin.template", {}).get("src", "")))
    assert tarefa["ansible.builtin.template"]["mode"] == "0600"


# --- Dataset único ---

def test_sem_dataset_downloads():
    for f in (ROOT / "server").rglob("*"):
        if f.is_file():
            t = f.read_text(encoding="utf-8", errors="ignore")
            assert "zfs_downloads_dataset_name" not in t and "ZFS_DOWNLOADS" not in t, f


# --- Painel, disponibilidade e alertas ---

PROM_VARS = dict(proxmox_host_ip_var="192.168.15.66", core_services_vm_ip_var="192.168.15.67",
                 ai_desktop_vm_ip_var="192.168.15.68")


def test_blackbox_midia():
    cfg = yaml.safe_load(render("templates/prometheus.yml.j2", groups={}, **PROM_VARS))
    pares = [(c["labels"]["app"], c["targets"][0]) for j in cfg["scrape_configs"] if j["job_name"] == "blackbox_http"
             for c in j["static_configs"]]
    alvos = dict(pares)
    assert ("qbittorrent", "http://gluetun:8088/") in pares
    assert alvos["seerr"] == "http://seerr:5055/api/v1/status"
    for app, url in (("lidarr", "http://lidarr:8686/ping"), ("prowlarr", "http://prowlarr:9696/ping"),
                     ("bazarr", "http://bazarr:6767/")):
        assert alvos[app] == url


def test_alerta_vpn_separado():
    regras = {r["uid"]: r for r in yaml.safe_load(render("templates/grafana/alerting/rules.yml.j2"))["groups"][0]["rules"]}
    assert 'app!~"n8n|qbittorrent"' in regras["servico-fora-do-ar"]["data"][0]["model"]["expr"]
    vpn = regras["qbittorrent-ou-vpn-fora"]
    assert vpn["data"][0]["model"]["expr"] == '1 - probe_success{app="qbittorrent"}'
    assert vpn["labels"]["severity"] == "critical"


def test_homepage_midia():
    import pathlib
    src = (ROOT / "server/ansible/templates/homepage/services.yaml.j2").read_text(encoding="utf-8")
    variaveis = set(re.findall(r"\{\{\s*([a-z_]+)", src)) - {"item"}
    ctx = {"base_domain": "seudominio.com", "groups": {"ai_desktop": ["ai-desktop-vm"]}, **PROM_VARS}
    ctx.update({v: "x" for v in variaveis if v not in ctx})
    out = render("templates/homepage/services.yaml.j2", **ctx)
    midia = next(g for g in yaml.safe_load(out) if "mídia" in g)["mídia"]
    nomes = {list(e)[0] for e in midia}
    assert {"jellyfin", "seerr", "sonarr", "radarr", "lidarr", "prowlarr", "bazarr", "qbittorrent"} <= nomes
    assert "http://gluetun:8088" in out
    for var in ("SEERR", "BAZARR", "LIDARR", "PROWLARR"):
        assert "{{HOMEPAGE_VAR_%s_KEY}}" % var in out


def test_chaves_homepage_das_arr_vem_de_arr_api_keys():
    pb = (ROOT / "server/ansible/playbooks/setup-monitoring-stack-volumes.yml").read_text(encoding="utf-8")
    for app in ("sonarr", "radarr", "lidarr", "prowlarr"):
        assert re.search(r"HOMEPAGE_VAR_%s_KEY', value: \"\{\{ arr_api_keys\.%s \}\}\"" % (app.upper(), app), pb), app
    for app in ("bazarr", "seerr"):
        assert "homepage_widget_keys.%s" % app in pb
    assert "homepage_widget_keys.sonarr" not in pb and "homepage_widget_keys.radarr" not in pb


def test_homepage_recebe_todas_as_variaveis_do_painel():
    src = (ROOT / "server/ansible/templates/homepage/services.yaml.j2").read_text(encoding="utf-8")
    usadas = set(re.findall(r"\{\{(HOMEPAGE_VAR_[A-Z_]+)\}\}", src))
    env = _env(_svc(APPS)["homepage"])
    assert usadas <= set(env), usadas - set(env)


def test_authelia_bypass_para_publicas_antes_do_curinga():
    src = (ROOT / "server/ansible/roles/infra/authelia-config/templates/configuration.yml.j2").read_text(encoding="utf-8")
    regras = yaml.safe_load(re.sub(r"\{\{[^}]+\}\}", "x", src))["access_control"]["rules"]
    dominios = [r["domain"] for r in regras]
    curinga = dominios.index("*.x")
    for sub in ("jellyfin.x", "pedidos.x"):
        i = dominios.index(sub)
        assert i < curinga and regras[i]["policy"] == "bypass"



# --- Correções da revisão final ---

PAGINA10 = ROOT / "wiki/docs/01-manual-implementacao/10-midia.md"


def test_vpn_fora_detectado_pela_saude_do_gluetun():
    # O firewall do gluetun aceita entrada das redes Docker mesmo com o túnel caído: a WebUI segue
    # respondendo. Quem reflete o túnel é o servidor de saúde do gluetun (200 ok / 500 fora).
    assert _env(_svc(MEDIA)["gluetun"])["HEALTH_SERVER_ADDRESS"] == ":9999"
    cfg = yaml.safe_load(render("templates/prometheus.yml.j2", groups={}, **PROM_VARS))
    pares = [(c["labels"]["app"], c["targets"][0]) for j in cfg["scrape_configs"] if j["job_name"] == "blackbox_http"
             for c in j["static_configs"]]
    assert ("qbittorrent", "http://gluetun:9999/") in pares


def test_qbittorrent_reinicia_junto_com_o_gluetun():
    # Container com network_mode: service:gluetun perde a rede quando o gluetun é recriado.
    assert _svc(MEDIA)["qbittorrent"]["depends_on"]["gluetun"]["restart"] is True
    texto = PAGINA10.read_text(encoding="utf-8")
    assert "docker restart qbittorrent" in texto


def test_traefik_repassa_ip_real_do_cliente():
    # Sem confiar nos cabeçalhos X-Forwarded-For do cloudflared, o Jellyfin vê todo acesso como local.
    cfg = yaml.safe_load(render("roles/infra/traefik-config/templates/traefik.yml.j2",
                                base_domain="seudominio.com", letsencrypt_email="a@b.c"))
    assert "172.16.0.0/12" in cfg["entryPoints"]["websecure"]["forwardedHeaders"]["trustedIPs"]
    texto = PAGINA10.read_text(encoding="utf-8")
    assert "Known proxies" in texto


def test_assistentes_publicos_logo_apos_o_deploy():
    # Jellyfin e Seerr ficam públicos: o assistente inicial vem antes de qualquer outro passo.
    texto = PAGINA10.read_text(encoding="utf-8")
    primeira = texto.index("## Primeira configuração")
    passos = texto[primeira:]
    assert passos.index("**Jellyfin") < passos.index("**ProtonVPN")
    assert passos.index("**Seerr") < passos.index("**ProtonVPN")
