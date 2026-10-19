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
    ctx = {**_main(), "docker_puid": 1001, "docker_pgid": 1001, "groups": {"virtual_machines": []}}
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
}


def _authelia(pem=PEM_TESTE, oidc=OIDC) -> str:
    return render(AUTHELIA_TPL, base_domain=DOM, authelia_jwt_secret="j" * 64,
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
    assert set(cli) == {"immich", "nextcloud"}
    for nome, c in cli.items():
        assert c["authorization_policy"] == "two_factor"
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
    assert "segredoImmich123" not in _authelia() and "segredoNextcloud123" not in _authelia()


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
