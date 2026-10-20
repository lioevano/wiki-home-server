"""Testes do segundo cérebro (4b): dataset notes, conversor, stack notes (Syncthing, qmd, escrita, proxies MCP) e integrações."""
from __future__ import annotations

import yaml

from test_observabilidade import ROOT, render

MAIN = ROOT / "server/ansible/inventories/home/group_vars/all/main.yml"
COMMON = ROOT / "server/ansible/roles/common/tasks/main.yml"
PVE_TASKS = ROOT / "server/ansible/roles/infra/proxmox-host-config/tasks/main.yml"
AI_IP = "192.168.15.68"


def _main() -> dict:
    return yaml.safe_load(MAIN.read_text(encoding="utf-8"))


def _mount_itens() -> dict:
    tarefas = yaml.safe_load(COMMON.read_text(encoding="utf-8"))
    mount = next(t for t in tarefas if "ansible.posix.mount" in t)
    return mount, {i["dataset_name"]: i for i in mount["loop"]}


# --- Task 1: dataset, exports, montagens e snapshots ---

def test_export_notes_so_para_a_vm_de_ia():
    ctx = {**_main(), "docker_puid": 1001, "docker_pgid": 1001, "ai_desktop_vm_ip_var": AI_IP,
           "groups": {"virtual_machines": ["ai-desktop-vm"]}}
    out = render("roles/infra/proxmox-host-config/templates/etc_exports.j2", **ctx)
    linhas = [l for l in out.splitlines() if l.startswith("/data/notes ")]
    assert linhas == [f"/data/notes {AI_IP}(rw,sync,no_subtree_check,all_squash,anonuid=1001,anongid=1001)"]


def test_montagens_da_vm_de_ia():
    assert _main()["zfs_notes_dataset_name"] == "notes"
    mount, itens = _mount_itens()
    notes = itens["{{ zfs_notes_dataset_name }}"]
    assert notes["when_condition"] == "'ai_desktop' in group_names"
    files_ia = [i for i in mount["loop"] if i["dataset_name"] == "{{ zfs_files_dataset_name }}"
                and "'ai_desktop' in group_names" in i.get("when_condition", "")]
    assert len(files_ia) == 1 and files_ia[0]["opts"].startswith("ro,")
    assert "'ai_desktop' in group_names" in itens["{{ zfs_rag_sources_dataset_name }}"]["when_condition"]
    assert "item.opts | default(" in mount["ansible.posix.mount"]["opts"]
    assert "'ai-desktop-vm' in group_names" not in COMMON.read_text(encoding="utf-8")


def test_snapshots_so_em_notes():
    tarefas = yaml.safe_load(PVE_TASKS.read_text(encoding="utf-8"))
    pacotes = [t for t in tarefas if "zfs-auto-snapshot" in str(t.get("ansible.builtin.apt", {}).get("name", ""))]
    assert pacotes
    props = {t["community.general.zfs"]["name"]: t["community.general.zfs"]["extra_zfs_properties"]
             for t in tarefas if "community.general.zfs" in t}
    assert props["data"] == {"com.sun:auto-snapshot": "false"}
    assert props["data/{{ zfs_notes_dataset_name }}"] == {"com.sun:auto-snapshot": "true"}
