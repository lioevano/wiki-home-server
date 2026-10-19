"""Testes de fotos e arquivos: datasets, OIDC do Authelia, stacks photos (Immich) e cloud (Nextcloud)."""
from __future__ import annotations

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
