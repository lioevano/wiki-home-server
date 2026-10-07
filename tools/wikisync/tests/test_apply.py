from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from wikisync.apply import ApplyError, plan_apply, write_changes
from wikisync.config import load_config

TOOLS = Path(__file__).resolve().parents[2]


def page(*blocks: tuple[str, str]) -> str:
    body = "".join(f'```yaml title="{p}"\n{c}\n```\n\n' for p, c in blocks)
    return "---\ndescription: D\n---\n# I\n\n" + body


def cli(root, *args):
    env = dict(os.environ, PYTHONPATH=str(TOOLS), PYTHONUTF8="1")
    return subprocess.run([sys.executable, "-m", "wikisync", "--root", str(root), "apply", *args],
                          env=env, capture_output=True, text=True)


def test_dry_run_does_not_write(make_repo):
    root = make_repo({"wiki/docs/index.md": page(("ansible/a.yml", "x: 1")), "server/ansible/a.yml": "x: 2\n"})
    target = root / "server/ansible/a.yml"
    before = (target.read_bytes(), target.stat().st_mtime_ns)
    proc = cli(root)
    assert proc.returncode == 0
    assert "-x: 2" in proc.stdout and "+x: 1" in proc.stdout
    assert "dry-run: use --yes para gravar" in proc.stdout
    assert (target.read_bytes(), target.stat().st_mtime_ns) == before


def test_yes_writes_lf_utf8_with_final_newline(make_repo):
    root = make_repo({"wiki/docs/index.md": page(("ansible/a.yml", "nome: ação\nx: 1")), "server/ansible/a.yml": "x: 2\r\n"})
    assert cli(root, "--yes").returncode == 0
    data = (root / "server/ansible/a.yml").read_bytes()
    assert data == "nome: ação\nx: 1\n".encode("utf-8")


def test_creates_missing_file_and_dirs(make_repo):
    root = make_repo({"wiki/docs/index.md": page(("ansible/roles/r/tasks/main.yml", "- debug: msg=oi"))})
    changes = plan_apply(load_config(root))
    assert [(c.path, c.old) for c in changes] == [("ansible/roles/r/tasks/main.yml", None)]
    write_changes(load_config(root), changes)
    assert (root / "server/ansible/roles/r/tasks/main.yml").read_text(encoding="utf-8") == "- debug: msg=oi\n"


def test_path_restricts_to_one_file(make_repo):
    root = make_repo({"wiki/docs/index.md": page(("ansible/a.yml", "a: 1"), ("ansible/b.yml", "b: 1"))})
    assert [c.path for c in plan_apply(load_config(root), only="ansible/b.yml")] == ["ansible/b.yml"]


def test_never_deletes_unmarked_server_files(make_repo):
    root = make_repo({"wiki/docs/index.md": page(("ansible/a.yml", "a: 1")), "server/ansible/orfao.yml": "o: 1\n"})
    assert cli(root, "--yes").returncode == 0
    assert (root / "server/ansible/orfao.yml").read_text(encoding="utf-8") == "o: 1\n"


def test_dup_refuses_with_exit_1(make_repo):
    root = make_repo({"wiki/docs/index.md": page(("ansible/a.yml", "a: 1"), ("ansible/a.yml", "a: 2"))})
    with pytest.raises(ApplyError, match="ansible/a.yml"):
        plan_apply(load_config(root))
    proc = cli(root, "--yes")
    assert proc.returncode == 1
    assert not (root / "server/ansible/a.yml").exists()


def test_noop_when_equal_ignoring_crlf(make_repo):
    root = make_repo({"wiki/docs/index.md": page(("ansible/a.yml", "a: 1")), "server/ansible/a.yml": b"a: 1\r\n"})
    assert plan_apply(load_config(root)) == []
    assert "nada a aplicar" in cli(root).stdout


def test_path_without_literal_block_is_error(make_repo):
    root = make_repo({"wiki/docs/index.md": page(("ansible/a.yml", "a: 1")), "server/ansible/a.yml": "a: 1\n"})
    proc = cli(root, "--path", "ansible/digitado-errado.yml")
    assert proc.returncode == 1
    assert "nenhum bloco literal" in proc.stderr


def test_directory_target_refuses_before_writing_anything(make_repo):
    root = make_repo({
        "wiki/docs/index.md": page(("ansible/a.yml", "a: 1"), ("ansible/sub", "x: 1")),
        "server/ansible/sub/keep.yml": "k: 1\n",
    })
    with pytest.raises(ApplyError, match="ansible/sub"):
        plan_apply(load_config(root))
    proc = cli(root, "--yes")
    assert proc.returncode == 1
    assert not (root / "server/ansible/a.yml").exists()


def test_symlink_escaping_server_is_refused(make_repo, tmp_path_factory):
    outside = tmp_path_factory.mktemp("fora")
    root = make_repo({"wiki/docs/index.md": page(("ansible/link/x.yml", "x: 1"))})
    (root / "server/ansible").mkdir(parents=True, exist_ok=True)
    (root / "server/ansible/link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ApplyError, match="ansible/link/x.yml"):
        plan_apply(load_config(root))
    assert not (outside / "x.yml").exists()
