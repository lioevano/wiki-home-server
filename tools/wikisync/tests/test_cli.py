from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
CLEAN_INDEX = (
    "---\ndescription: D\n---\n# I\n\n"
    '```yaml title="ansible/a.yml"\nx: 1\n```\n'
)


def run(args, cwd=None):
    env = dict(os.environ, PYTHONPATH=str(TOOLS), PYTHONUTF8="1")
    return subprocess.run([sys.executable, "-m", "wikisync", *args], cwd=cwd, env=env, capture_output=True, text=True)


def test_exit_0_with_only_warnings(make_repo):
    root = make_repo({"wiki/docs/index.md": CLEAN_INDEX, "server/ansible/a.yml": "x: 1\n", "server/ansible/orfao.yml": "o: 1\n"})
    proc = run(["--root", str(root), "check"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ORPHAN" in proc.stdout
    assert "0 erro(s), 1 aviso(s)" in proc.stdout


def test_exit_1_with_errors(make_repo):
    root = make_repo({"wiki/docs/index.md": CLEAN_INDEX, "server/ansible/a.yml": "x: 2\n"})
    proc = run(["--root", str(root), "check"])
    assert proc.returncode == 1
    assert "LIT-DIFF" in proc.stdout


def test_exit_2_without_config(tmp_path):
    proc = run(["--root", str(tmp_path), "check"])
    assert proc.returncode == 2
    assert "config.yml" in proc.stderr


def test_json_output_is_list_of_findings(make_repo):
    root = make_repo({"wiki/docs/index.md": CLEAN_INDEX, "server/ansible/a.yml": "x: 2\n"})
    data = json.loads(run(["--root", str(root), "check", "--json"]).stdout)
    assert data == [{
        "code": "LIT-DIFF", "severity": "erro", "path": "ansible/a.yml",
        "page": "index.md", "message": data[0]["message"],
    }]


def test_default_root_from_other_cwd(tmp_path):
    proc = run(["check"], cwd=tmp_path)
    assert proc.returncode != 2, proc.stderr
