"""Testes de fotos e arquivos: datasets, OIDC do Authelia, stacks photos (Immich) e cloud (Nextcloud)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest
import yaml

from test_observabilidade import ROOT, render
from test_midia import _env, _svc  # noqa: F401  (usados nas tarefas seguintes)

MAIN = ROOT / "server/ansible/inventories/home/group_vars/all/main.yml"
COMMON = ROOT / "server/ansible/roles/common/tasks/main.yml"


def _main() -> dict:
    return yaml.safe_load(MAIN.read_text(encoding="utf-8"))


# --- Datasets e disco local ---

def test_datasets_exportados_e_montados_na_core():
    ctx = {**_main(), "docker_puid": 1001, "docker_pgid": 1001, "ai_desktop_vm_ip_var": "192.168.15.68",
           "groups": {"virtual_machines": []}}
    out = render("roles/infra/proxmox-host-config/templates/etc_exports.j2", **ctx)
    for ds in ("photos", "files"):
        linha = next(l for l in out.splitlines() if l.startswith(f"/data/{ds} "))
        assert "all_squash" in linha and "anonuid=1001" in linha
    tarefas = yaml.safe_load(COMMON.read_text(encoding="utf-8"))
    mount = next(t for t in tarefas if "ansible.posix.mount" in t)
    itens = {i["dataset_name"]: i for i in mount["loop"]}
    for var in ("zfs_photos_dataset_name", "zfs_files_dataset_name"):
        item = itens["{{ " + var + " }}"]
        assert "'core_services' in group_names" in item["when_condition"]


def test_variaveis_novas():
    m = _main()
    assert m["zfs_photos_dataset_name"] == "photos"
    assert m["zfs_files_dataset_name"] == "files"
    assert m["vm_local_data_path"] == "/opt/local-data"
    assert m["immich_version"] == "v3.3.3"
    assert str(m["nextcloud_major"]).isdigit()
    assert m["immich_password_login"] is True
    assert m["immich_config_overrides"] == {}


# --- Authelia como provedor OIDC ---

AUTHELIA_TPL = "roles/infra/authelia-config/templates/configuration.yml.j2"
DOM = "exemplo.com"
PEM_TESTE = "-----BEGIN PRIVATE KEY-----\nLINHA1\nLINHA2\n-----END PRIVATE KEY-----"
OIDC = {
    "immich": {"secret": "segredoImmich123", "secret_digest": "$pbkdf2-sha512$310000$aW1taWNo$ZGlnZXN0"},
    "nextcloud": {"secret": "segredoNextcloud123", "secret_digest": "$pbkdf2-sha512$310000$bmV4dA$ZGlnZXN0"},
    "openwebui": {"secret": "segredoOpenwebui123", "secret_digest": "$pbkdf2-sha512$310000$b3dlYg$ZGlnZXN0"},
    "mcp": {"secret": "segredoMcp123", "secret_digest": "$pbkdf2-sha512$310000$bWNw$ZGlnZXN0"},
    "langfuse": {"secret": "segredoLangfuse123", "secret_digest": "$pbkdf2-sha512$310000$bGFuZ2Z1c2U$ZGlnZXN0"},
}


def _dominios_admins() -> list[str]:
    main = ROOT / "server/ansible/inventories/home/group_vars/all/main.yml"
    return yaml.safe_load(main.read_text(encoding="utf-8")).get("authelia_dominios_admins", [])


def _authelia(pem=PEM_TESTE, oidc=OIDC) -> str:
    return render(AUTHELIA_TPL, base_domain=DOM, authelia_dominios_admins=_dominios_admins(),
                  authelia_jwt_secret="j" * 64,
                  authelia_session_secret="s" * 64, authelia_storage_encryption_key="e" * 64,
                  authelia_storage_postgres_password="p" * 32, authelia_oidc_hmac_secret="h" * 64,
                  authelia_oidc_jwks_key=pem, oidc_clients=oidc)


def test_oidc_clientes():
    oidc = yaml.safe_load(_authelia())["identity_providers"]["oidc"]
    assert oidc["hmac_secret"] == "h" * 64
    jwk = oidc["jwks"][0]
    assert jwk["algorithm"] == "RS256" and jwk["use"] == "sig"
    assert jwk["key"].strip() == PEM_TESTE
    cli = {c["client_id"]: c for c in oidc["clients"]}
    assert set(cli) == {"immich", "nextcloud", "openwebui", "mcp", "langfuse"}  # langfuse: base dos agentes (4c1)
    for nome, c in cli.items():
        assert c["authorization_policy"] in oidc["authorization_policies"]  # todas exigem two_factor
        if nome != "mcp":  # o mcp-auth-proxy não envia PKCE ao provedor (test_cliente_oidc_mcp)
            assert c["require_pkce"] is True and c["pkce_challenge_method"] == "S256"
        assert c["client_secret"] == OIDC[nome]["secret_digest"]
        assert c["public"] is False
    assert cli["immich"]["token_endpoint_auth_method"] == "client_secret_basic"
    assert cli["immich"]["redirect_uris"] == [
        f"https://fotos.{DOM}/auth/login", f"https://fotos.{DOM}/user-settings", "app.immich:///oauth-callback"]
    assert cli["immich"]["scopes"] == ["openid", "profile", "email"]
    assert cli["nextcloud"]["token_endpoint_auth_method"] == "client_secret_post"
    assert cli["nextcloud"]["redirect_uris"] == [f"https://nextcloud.{DOM}/apps/user_oidc/code"]
    assert cli["nextcloud"]["scopes"] == ["openid", "profile", "email", "groups"]
    assert all(v["secret"] not in _authelia() for v in OIDC.values())


def test_bypass_dos_publicos():
    regras = yaml.safe_load(_authelia())["access_control"]["rules"]
    curinga = next(i for i, r in enumerate(regras) if r["domain"] == f"*.{DOM}")
    for sub in ("fotos", "nextcloud", "office"):
        idx = [i for i, r in enumerate(regras) if r["domain"] == f"{sub}.{DOM}"]
        assert len(idx) == 1, sub
        assert regras[idx[0]]["policy"] == "bypass" and "resources" not in regras[idx[0]]
        assert idx[0] < curinga


@pytest.mark.skipif(shutil.which("authelia") is None or shutil.which("openssl") is None,
                    reason="binário authelia ou openssl ausente")
def test_authelia_validate_config(tmp_path):
    pem = subprocess.run(["openssl", "genrsa", "2048"], capture_output=True, text=True, check=True).stdout.strip()

    def digest(s):
        out = subprocess.run(["authelia", "crypto", "hash", "generate", "pbkdf2", "--variant", "sha512",
                              "--password", s], capture_output=True, text=True, check=True).stdout
        return next(l.split("Digest: ", 1)[1] for l in out.splitlines() if l.startswith("Digest: "))

    oidc = {k: {"secret": v["secret"], "secret_digest": digest(v["secret"])} for k, v in OIDC.items()}
    users = tmp_path / "users_database.yml"
    users.write_text("users: {}\n")
    cfg = tmp_path / "configuration.yml"
    cfg.write_text(_authelia(pem=pem, oidc=oidc).replace("/config/users_database.yml", str(users))
                   .replace("/config/notification.txt", str(tmp_path / "n.txt")))
    r = subprocess.run(["authelia", "validate-config", "--config", str(cfg)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# --- Stack photos (Immich) ---

PHOTOS = ROOT / "server/docker/stacks/photos/docker-compose.yml"
PB_PHOTOS = ROOT / "server/ansible/playbooks/setup-photos-stack-volumes.yml"
IMMICH_TPL = "templates/immich/immich.json.j2"
COMUNS = {"DOCKER_PUID", "DOCKER_PGID", "SYSTEM_TIMEZONE", "BASE_DOMAIN_FROM_VAULT",
          "VM_NFS_MOUNT_BASE_PATH", "ZFS_DOCKER_VOLUMES_DATASET_NAME"}


def _pb_tasks(pb) -> list[dict]:
    return yaml.safe_load(pb.read_text(encoding="utf-8"))[0]["tasks"]


def _env_task(pb, arquivo) -> dict:
    return next(t for t in _pb_tasks(pb)
                if str(t.get("ansible.builtin.template", {}).get("dest", "")).endswith("/" + arquivo))


def _configs(pb, arquivo) -> dict:
    return {c["name"]: c["value"] for c in _env_task(pb, arquivo)["vars"]["stack_configs"]}


def _vars_compose(path) -> set:
    return set(re.findall(r"\$\{([A-Z0-9_]+)", path.read_text(encoding="utf-8")))


def _volume(servico, destino) -> str:
    return next(v for v in servico["volumes"] if v.split(":")[1] == destino)


def test_photos_servicos():
    s = _svc(PHOTOS)
    assert set(s) == {"immich_server", "immich_ml", "immich_redis", "immich_db"}
    assert s["immich_server"]["image"] == "ghcr.io/immich-app/immich-server:${IMMICH_VERSION}"
    assert s["immich_ml"]["image"] == "ghcr.io/immich-app/immich-machine-learning:${IMMICH_VERSION}"
    for n in ("immich_redis", "immich_db"):
        assert "@sha256:" in s[n]["image"], n
    assert s["immich_ml"]["networks"] == ["internal_services"]


def test_banco_e_cache_no_disco_local():
    s = _svc(PHOTOS)
    assert _volume(s["immich_db"], "/var/lib/postgresql/data").startswith("${PHOTOS_STACK_DB_PATH}")
    assert _volume(s["immich_ml"], "/cache").startswith("${PHOTOS_STACK_MODEL_CACHE_PATH}")
    cfg = _configs(PB_PHOTOS, "photos.env")
    for v in ("PHOTOS_STACK_DB_PATH", "PHOTOS_STACK_MODEL_CACHE_PATH"):
        assert cfg[v].startswith("{{ vm_local_data_path }}/"), v
    criados = {str(p) for t in _pb_tasks(PB_PHOTOS) if "ansible.builtin.file" in t
               for p in ([t["ansible.builtin.file"]["path"]] + list(t.get("loop", [])))}
    assert any("immich-db" in c for c in criados) and any("immich-model-cache" in c for c in criados)
    assert cfg["PHOTOS_STACK_UPLOAD_PATH"] == "{{ vm_nfs_mount_base_path }}/{{ zfs_photos_dataset_name }}"


def test_immich_rede_e_porta():
    srv = _svc(PHOTOS)["immich_server"]
    assert srv["ports"] == ["${CORE_SERVICES_VM_IP_VAR}:2283:2283"]
    assert "Host(`fotos.${BASE_DOMAIN_FROM_VAULT}`)" in str(srv["labels"])
    assert "authelia" not in str(srv["labels"])
    env = _env(srv)
    assert env["DB_HOSTNAME"] == "immich_db" and env["REDIS_HOSTNAME"] == "immich_redis"
    assert env["IMMICH_CONFIG_FILE"] == "/config/immich.json"
    assert _volume(srv, "/data").startswith("${PHOTOS_STACK_UPLOAD_PATH}")
    assert _volume(srv, "/config") == "${PHOTOS_STACK_CONFIG_PATH}:/config:ro"


def test_variaveis_photos_no_env():
    assert _vars_compose(PHOTOS) <= set(_configs(PB_PHOTOS, "photos.env")) | COMUNS
    assert _env_task(PB_PHOTOS, "photos.env")["ansible.builtin.template"]["mode"] == "0600"


IMMICH_CTX = dict(base_domain=DOM, oidc_clients=OIDC, immich_password_login=True, immich_config_overrides={})


def _immich(**kw) -> dict:
    return json.loads(render(IMMICH_TPL, **{**IMMICH_CTX, **kw}))


def test_immich_json():
    c = _immich()
    o = c["oauth"]
    assert o["enabled"] is True and o["autoLaunch"] is True and o["autoRegister"] is False
    assert o["issuerUrl"] == f"https://auth.{DOM}" and o["clientId"] == "immich"
    assert o["clientSecret"] == OIDC["immich"]["secret"]
    assert o["tokenEndpointAuthMethod"] == "client_secret_basic"
    assert c["server"]["externalDomain"] == f"https://fotos.{DOM}"
    assert c["machineLearning"]["urls"] == ["http://immich_ml:3003"]
    assert c["storageTemplate"] == {"enabled": True, "template": "{{y}}/{{y}}-{{MM}}-{{dd}}/{{filename}}"}
    assert c["backup"]["database"]["keepLastAmount"] == 14
    assert c["passwordLogin"]["enabled"] is True
    assert _immich(immich_password_login="False")["passwordLogin"]["enabled"] is False


def test_immich_overrides_mesclam():
    c = _immich(immich_config_overrides={"oauth": {"buttonText": "X"},
                                         "machineLearning": {"ocr": {"enabled": False}}})
    assert c["oauth"]["buttonText"] == "X"
    assert c["oauth"]["enabled"] is True and c["oauth"]["clientId"] == "immich"
    assert c["machineLearning"]["urls"] == ["http://immich_ml:3003"]
    assert c["machineLearning"]["ocr"] == {"enabled": False}


def test_immich_json_0600():
    t = next(t for t in _pb_tasks(PB_PHOTOS)
             if str(t.get("ansible.builtin.template", {}).get("dest", "")).endswith("/immich.json"))
    assert t["ansible.builtin.template"]["src"].endswith("immich/immich.json.j2")
    assert t["ansible.builtin.template"]["mode"] == "0600"


# --- Stack cloud (Nextcloud, cron, Collabora) ---

CLOUD = ROOT / "server/docker/stacks/cloud/docker-compose.yml"
APPS = ROOT / "server/docker/stacks/apps/docker-compose.yml"
PB_CLOUD = ROOT / "server/ansible/playbooks/setup-cloud-stack-volumes.yml"
HOOK_TPL = "templates/nextcloud/10-homeserver.sh.j2"
DUMP_TPL = "templates/backup-postgres.sh.j2"
DUMP_BASE = dict(vm_nfs_mount_base_path="/mnt/pve_data_zfs", zfs_docker_volumes_dataset_name="docker-volumes",
                 vm_local_data_path="/opt/local-data")


def _script_dump(pb, destino) -> str:
    """Renderiza o dump genérico com as vars: da tarefa do playbook que instala o script em `destino`."""
    import jinja2
    tarefa = next(x for x in _pb_tasks(pb)
                  if x.get("ansible.builtin.template", {}).get("dest") == destino)
    assert tarefa["ansible.builtin.template"]["src"] == "../" + DUMP_TPL
    vars_ = {k: jinja2.Environment().from_string(str(v)).render(**DUMP_BASE) if isinstance(v, str) else v
             for k, v in tarefa.get("vars", {}).items()}
    return render(DUMP_TPL, **DUMP_BASE, **vars_)
MIDDLEWARE_TPL = "roles/infra/traefik-config/templates/nextcloud_middleware.yml.j2"


def test_cloud_servicos_e_apps_sem_nextcloud():
    assert set(_svc(CLOUD)) == {"nextcloud_app", "nextcloud_cron", "nextcloud_redis", "nextcloud_db", "collabora"}
    assert not [n for n in _svc(APPS) if n.startswith("nextcloud")]


def test_cron_igual_ao_app():
    s = _svc(CLOUD)
    assert s["nextcloud_cron"]["image"] == s["nextcloud_app"]["image"] == "nextcloud:${NEXTCLOUD_MAJOR}-apache"
    assert s["nextcloud_cron"]["entrypoint"] == "/cron.sh"
    assert s["nextcloud_cron"]["volumes"] == s["nextcloud_app"]["volumes"]
    # Sem o mesmo ambiente, o cron usa trava no banco (sem REDIS_HOST) e o app usa Redis: não se excluem.
    assert _env(s["nextcloud_cron"]) == _env(s["nextcloud_app"])


def test_nextcloud_publico_com_dav():
    app = _svc(CLOUD)["nextcloud_app"]
    lab = str(app["labels"])
    assert "nextcloud-dav@file" in lab and "nextcloud-headers@file" in lab and "authelia" not in lab
    assert "Host(`nextcloud.${BASE_DOMAIN_FROM_VAULT}`)" in lab
    env = _env(app)
    assert env["TRUSTED_PROXIES"] == "172.16.0.0/12"
    assert env["OVERWRITEPROTOCOL"] == "https"
    assert env["OVERWRITECLIURL"] == "https://nextcloud.${BASE_DOMAIN_FROM_VAULT}"
    assert env["NEXTCLOUD_OIDC_CLIENT_SECRET"] == "${NEXTCLOUD_OIDC_CLIENT_SECRET}"
    assert _volume(app, "/docker-entrypoint-hooks.d/before-starting") == \
        "${CLOUD_STACK_NEXTCLOUD_HOOKS_PATH}:/docker-entrypoint-hooks.d/before-starting:ro"
    mw = yaml.safe_load(render(MIDDLEWARE_TPL))["http"]["middlewares"]
    rr = mw["nextcloud-dav"]["redirectRegex"]
    assert rr["regex"] == "^https://(.*)/.well-known/(?:card|cal)dav"
    assert rr["replacement"] == "https://${1}/remote.php/dav/" and rr["permanent"] is True


def test_collabora_wopi_pela_lan():
    c = _svc(CLOUD)["collabora"]
    assert c["extra_hosts"] == ["nextcloud.${BASE_DOMAIN_FROM_VAULT}:${CORE_SERVICES_VM_IP_VAR}"]
    env = _env(c)
    assert env["aliasgroup1"] == "https://nextcloud.${BASE_DOMAIN_FROM_VAULT}:443"
    assert env["server_name"] == "office.${BASE_DOMAIN_FROM_VAULT}"
    assert "--o:ssl.enable=false" in env["extra_params"] and "--o:ssl.termination=true" in env["extra_params"]
    assert "Host(`office.${BASE_DOMAIN_FROM_VAULT}`)" in str(c["labels"]) and "authelia" not in str(c["labels"])


def test_banco_nextcloud_local():
    db = _svc(CLOUD)["nextcloud_db"]
    assert _volume(db, "/var/lib/postgresql/data").startswith("${CLOUD_STACK_NEXTCLOUD_DB_PATH}")
    cfg = _configs(PB_CLOUD, "cloud.env")
    assert cfg["CLOUD_STACK_NEXTCLOUD_DB_PATH"].startswith("{{ vm_local_data_path }}/")
    assert cfg["CLOUD_STACK_NEXTCLOUD_DATA_PATH"] == "{{ vm_nfs_mount_base_path }}/{{ zfs_files_dataset_name }}"


def test_variaveis_cloud_no_env():
    assert _vars_compose(CLOUD) <= set(_configs(PB_CLOUD, "cloud.env")) | COMUNS
    assert _env_task(PB_CLOUD, "cloud.env")["ansible.builtin.template"]["mode"] == "0600"


def test_hook_sem_segredo_e_idempotente(tmp_path):
    out = render(HOOK_TPL, base_domain=DOM, oidc_clients=OIDC)
    assert OIDC["nextcloud"]["secret"] not in out and OIDC["immich"]["secret"] not in out
    assert '"$NEXTCLOUD_OIDC_CLIENT_SECRET"' in out
    for linha in (l for l in out.splitlines() if "app:install" in l):
        assert "|| " in linha and "app:enable" in linha.split("|| ", 1)[1], linha
    for trecho in ("app:disable photos", "user_oidc:provider", "allow_multiple_user_backends", "wopi_url",
                   "public_wopi_url", "wopi_allowlist", "max_chunk_size", "default_phone_region",
                   f"https://auth.{DOM}/.well-known/openid-configuration", f"https://office.{DOM}"):
        assert trecho in out, trecho
    f = tmp_path / "h.sh"
    f.write_text(out)
    assert subprocess.run(["bash", "-n", str(f)]).returncode == 0
    t = next(t for t in _pb_tasks(PB_CLOUD)
             if str(t.get("ansible.builtin.template", {}).get("src", "")).endswith("10-homeserver.sh.j2"))
    assert t["ansible.builtin.template"]["mode"] == "0755"


def test_dump_diario_do_nextcloud():
    tarefas = _pb_tasks(PB_CLOUD)
    script = next(t for t in tarefas
                  if t.get("ansible.builtin.template", {}).get("dest") == "/usr/local/sbin/backup-nextcloud-db.sh")
    assert script["ansible.builtin.template"]["mode"] == "0750"
    copias = {t["ansible.builtin.copy"]["dest"]: t["ansible.builtin.copy"]["content"]
              for t in tarefas if "ansible.builtin.copy" in t}
    timer = next(v for k, v in copias.items() if k.endswith(".timer"))
    assert "OnCalendar=" in timer and "Persistent=true" in timer
    assert any(k.endswith(".service") for k in copias)
    sd = next(t for t in tarefas if "ansible.builtin.systemd" in t)["ansible.builtin.systemd"]
    assert sd["name"].endswith(".timer") and sd["enabled"] is True and sd.get("daemon_reload") is True
    out = _script_dump(PB_CLOUD, "/usr/local/sbin/backup-nextcloud-db.sh")
    assert "pg_dump" in out and "/mnt/pve_data_zfs/docker-volumes/nextcloud/db-dumps" in out
    assert "-mtime +14" in out and "-delete" in out


# --- Painel e disponibilidade ---

def test_sondas_fotos_arquivos():
    from test_midia import PROM_VARS
    cfg = yaml.safe_load(render("templates/prometheus.yml.j2", groups={}, **PROM_VARS))
    alvos = {c["labels"]["app"]: c["targets"][0] for j in cfg["scrape_configs"] if j["job_name"] == "blackbox_http"
             for c in j["static_configs"]}
    assert alvos["immich"] == "http://immich_server:2283/api/server/ping"
    assert alvos["nextcloud"] == "http://nextcloud_app/status.php"
    assert alvos["collabora"] == "http://collabora:9980/hosting/discovery"


def test_homepage_immich():
    from test_midia import PROM_VARS
    src = (ROOT / "server/ansible/templates/homepage/services.yaml.j2").read_text(encoding="utf-8")
    ctx = {"base_domain": DOM, "groups": {"ai_desktop": ["ai-desktop-vm"]}, **PROM_VARS}
    ctx.update({v: "x" for v in set(re.findall(r"\{\{\s*([a-z_]+)", src)) - {"item"} if v not in ctx})
    grupo = next(g for g in yaml.safe_load(render("templates/homepage/services.yaml.j2", **ctx))
                 if "produtividade" in g)["produtividade"]
    entradas = {list(e)[0]: list(e.values())[0] for e in grupo}
    im = entradas["immich"]
    assert im["href"] == f"https://fotos.{DOM}" and im["container"] == "immich_server" and im["server"] == "core"
    assert im["widget"]["type"] == "immich" and im["widget"]["url"] == "http://immich_server:2283"
    assert im["widget"]["key"] == "{{HOMEPAGE_VAR_IMMICH_KEY}}" and im["widget"]["version"] == 2
    co = entradas["collabora"]
    assert co["href"] == f"https://office.{DOM}" and co["container"] == "collabora" and "widget" not in co
    pb = (ROOT / "server/ansible/playbooks/setup-monitoring-stack-volumes.yml").read_text(encoding="utf-8")
    assert "{ name: 'HOMEPAGE_VAR_IMMICH_KEY', value: \"{{ homepage_widget_keys.immich }}\" }" in pb
    assert "HOMEPAGE_VAR_IMMICH_KEY" in _env(_svc(APPS)["homepage"])


# --- Documentação e catálogo ---

def _catalogo() -> dict:
    src = (ROOT / "wiki/docs/02-visao-geral-arquitetura/09-catalogo-aplicacoes.md").read_text(encoding="utf-8")
    linhas = {}
    for l in src.splitlines():
        cel = [c.strip() for c in l.strip().strip("|").split("|")]
        if len(cel) == 11 and cel[0].startswith("`"):
            linhas[cel[0].strip("`")] = cel
    return linhas


def test_catalogo_fotos_arquivos():
    cat = _catalogo()
    for app, stack, sub in (("immich", "photos", "fotos"), ("nextcloud", "cloud", "nextcloud"),
                            ("collabora", "cloud", "office")):
        c = cat[app]
        assert c[2] == f"{stack} / core-services-vm", app
        assert c[4] == "publica" and c[5] == f"`{sub}`", app
        assert "11-fotos-arquivos.md" in c[10], app
    assert "`nextcloud_cron`" in cat["nextcloud"][3]
    assert (ROOT / "wiki/docs/01-manual-implementacao/11-fotos-arquivos.md").exists()
    assert "11-fotos-arquivos.md" in (ROOT / "wiki/mkdocs.yml").read_text(encoding="utf-8")


# --- Correções da revisão final ---

def test_nextcloud_html_e_config_no_disco_local():
    # occ e cron.php exigem que o usuário seja o dono do config.php, e o entrypoint faz chown: nada disso
    # funciona no NFS com all_squash. html e config ficam no disco local; os dados, no dataset files em /data.
    app = _svc(CLOUD)["nextcloud_app"]
    assert _volume(app, "/var/www/html").startswith("${CLOUD_STACK_NEXTCLOUD_HTML_PATH}")
    assert _volume(app, "/var/www/html/config").startswith("${CLOUD_STACK_NEXTCLOUD_CONFIG_PATH}")
    assert _volume(app, "/data").startswith("${CLOUD_STACK_NEXTCLOUD_DATA_PATH}")
    assert _env(app)["NEXTCLOUD_DATA_DIR"] == "/data"
    cfg = _configs(PB_CLOUD, "cloud.env")
    for v in ("CLOUD_STACK_NEXTCLOUD_HTML_PATH", "CLOUD_STACK_NEXTCLOUD_CONFIG_PATH"):
        assert cfg[v].startswith("{{ vm_local_data_path }}/"), v
    raiz = next(t["ansible.builtin.file"] for t in _pb_tasks(PB_CLOUD) if "ansible.builtin.file" in t
                and t["ansible.builtin.file"]["path"] == "{{ vm_nfs_mount_base_path }}/{{ zfs_files_dataset_name }}")
    assert raiz["mode"] == "0770"  # o Nextcloud recusa diretório de dados com outra permissão


def test_dump_guarda_o_config_do_nextcloud():
    out = _script_dump(PB_CLOUD, "/usr/local/sbin/backup-nextcloud-db.sh")
    assert "tar" in out and "/opt/local-data/nextcloud/config" in out  # instanceid, secret e passwordsalt
    assert "nextcloud-config-*.tar.gz" in out and "*.tmp" in out


def test_raiz_dos_datasets_do_dockeruser():
    pagina = (ROOT / "wiki/docs/01-manual-implementacao/02-proxmox-ve-host.md").read_text(encoding="utf-8")
    linha = next(l for l in pagina.splitlines() if "chown" in l and "/data/photos" in l)
    for ds in ("/data/docker-volumes", "/data/media", "/data/photos", "/data/files"):
        assert ds in linha, ds


def test_login_direto_no_authelia():
    out = render(HOOK_TPL, base_domain=DOM, oidc_clients=OIDC)
    assert "occ config:app:set --type=string --value=0 user_oidc allow_multiple_user_backends" in out
    assert "config:system:set user_oidc allow_multiple_user_backends" not in out


# --- Pendências menores (spec 2026-10-20-pendencias-menores, #24, #30, #33) ---

def test_dominios_de_administracao_so_para_admins():
    """#24: llm., openwebui. e os outros painéis de administração recusam quem não é do grupo admins."""
    import yaml as _y
    main = _y.safe_load((ROOT / "server/ansible/inventories/home/group_vars/all/main.yml").read_text(encoding="utf-8"))
    admins = main["authelia_dominios_admins"]
    assert {"llm", "openwebui", "langfuse", "portainer", "traefik", "grafana", "prometheus", "sync"} <= set(admins)
    assert not {"home", "hass", "auth"} & set(admins)
    regras = yaml.safe_load(_authelia())["access_control"]["rules"]
    dominios = [f"{d}.{DOM}" for d in admins]
    curinga = next(i for i, r in enumerate(regras) if r["domain"] == f"*.{DOM}")
    permite = next(i for i, r in enumerate(regras) if r.get("subject") == "group:admins")
    nega = permite + 1
    assert regras[permite]["domain"] == dominios and regras[permite]["policy"] == "two_factor"
    assert regras[nega] == {"domain": dominios, "policy": "deny"}
    assert nega < curinga


def test_politicas_oidc_por_cliente():
    """#33: só quem é do grupo certo ganha conta pelo OIDC; #30: consentimento lembrado por um ano."""
    oidc = yaml.safe_load(_authelia())["identity_providers"]["oidc"]
    pol = oidc["authorization_policies"]
    assert pol["so_admins"] == {"default_policy": "deny",
                                "rules": [{"policy": "two_factor", "subject": "group:admins"}]}
    assert pol["familia"] == {"default_policy": "deny",
                              "rules": [{"policy": "two_factor", "subject": "group:users"}]}
    por_cliente = {c["client_id"]: c for c in oidc["clients"]}
    assert {c: por_cliente[c]["authorization_policy"] for c in por_cliente} == {
        "immich": "familia", "nextcloud": "familia",
        "openwebui": "so_admins", "mcp": "so_admins", "langfuse": "so_admins"}
    assert all(c["pre_configured_consent_duration"] == "1y" for c in oidc["clients"])
