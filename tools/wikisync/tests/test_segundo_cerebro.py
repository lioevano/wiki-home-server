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


# --- Task 2: conversor de documentos do Nextcloud ---

import importlib.util  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402

import pytest  # noqa: E402

CONVERSOR = ROOT / "server/ansible/templates/notes/conversor.py"


def _conv():
    spec = importlib.util.spec_from_file_location("conversor", CONVERSOR)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["conversor"] = mod  # dataclasses precisa do módulo registrado
    spec.loader.exec_module(mod)
    return mod


def _falso(p):
    if "quebrado" in p.name:
        raise ValueError("arquivo corrompido")
    return f"texto de {p.name}"


EXT = {"pdf", "docx", "md", "txt"}


def _arq(base, rel, conteudo="x"):
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(conteudo, encoding="utf-8")
    return p


def test_converte_e_mantem(tmp_path):
    c = _conv()
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    _arq(origem, "a.pdf"), _arq(origem, "sub/b.docx"), _arq(origem, "foto.jpg")
    r = c.sincronizar(origem, destino, EXT, 10_000, _falso)
    assert (r.convertidos, r.mantidos, r.removidos, r.falhas) == (2, 0, 0, [])
    b = (destino / "sub/b.docx.md").read_text(encoding="utf-8")
    assert b.startswith('---\norigem: "Nextcloud/sub/b.docx"\n---\n\n') and "texto de b.docx" in b
    assert (destino / "a.pdf.md").exists() and not (destino / "foto.jpg.md").exists()
    r = c.sincronizar(origem, destino, EXT, 10_000, _falso)
    assert (r.convertidos, r.mantidos) == (0, 2)
    a = origem / "a.pdf"
    a.write_text("conteúdo novo", encoding="utf-8")
    os.utime(a, ns=(a.stat().st_atime_ns, a.stat().st_mtime_ns + 5_000_000_000))
    r = c.sincronizar(origem, destino, EXT, 10_000, _falso)
    assert (r.convertidos, r.mantidos) == (1, 1)


def test_remove_o_que_sumiu(tmp_path):
    c = _conv()
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    _arq(origem, "a.pdf"), _arq(origem, "sub/b.docx")
    c.sincronizar(origem, destino, EXT, 10_000, _falso)
    (origem / "sub/b.docx").unlink()
    r = c.sincronizar(origem, destino, EXT, 10_000, _falso)
    assert r.removidos == 1
    assert not (destino / "sub/b.docx.md").exists() and not (destino / "sub").exists()
    manifesto = (destino / ".manifesto.json").read_text(encoding="utf-8")
    assert "sub/b.docx" not in manifesto and "a.pdf" in manifesto


def test_falha_nao_para_o_resto(tmp_path):
    c = _conv()
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    _arq(origem, "quebrado.pdf"), _arq(origem, "ok.pdf")
    r = c.sincronizar(origem, destino, EXT, 10_000, _falso)
    assert (destino / "ok.pdf.md").exists()
    assert r.falhas == ["quebrado.pdf"] and r.convertidos == 1
    assert "quebrado.pdf" not in (destino / ".manifesto.json").read_text(encoding="utf-8")


def test_ignora_symlink_oculto_e_grande(tmp_path):
    c = _conv()
    origem, destino, fora = tmp_path / "origem", tmp_path / "destino", tmp_path / "fora"
    alvo = _arq(fora, "segredo.pdf")
    origem.mkdir()
    os.symlink(alvo, origem / "link.pdf")
    os.symlink(fora, origem / "pasta-link")
    _arq(origem, ".oculto/x.pdf"), _arq(origem, ".y.pdf"), _arq(origem, "grande.pdf", "z" * 200)
    _arq(origem, "ok.md")
    antes = {p for p in tmp_path.rglob("*")}
    r = c.sincronizar(origem, destino, EXT, 100, _falso)
    assert r.convertidos == 1
    novos = {p for p in tmp_path.rglob("*")} - antes
    assert all(destino in p.parents or p == destino for p in novos)
    assert {p.name for p in novos if p.is_file()} == {"ok.md.md", ".manifesto.json"}


def test_origem_vazia_nao_apaga(tmp_path):
    c = _conv()
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    _arq(origem, "a.pdf")
    c.sincronizar(origem, destino, EXT, 10_000, _falso)
    (origem / "a.pdf").unlink()
    with pytest.raises(c.OrigemVazia):
        c.sincronizar(origem, destino, EXT, 10_000, _falso)
    with pytest.raises(c.OrigemVazia):
        c.sincronizar(tmp_path / "nao-existe", destino, EXT, 10_000, _falso)
    assert (destino / "a.pdf.md").exists()
    args = ["--origem", str(tmp_path / "nao-existe"), "--destino", str(destino), "--extensoes", "pdf", "--max-mb", "1"]
    assert c.main(args) == 2
    assert (destino / "a.pdf.md").exists()
