#!/usr/bin/env python3
"""Executor de tarefas do repositório homeserver (Windows, Linux e CI).

Uso: python tools/dev.py <tarefa> [argumentos...]

Tarefas:
  setup   cria .venv/ na raiz e instala requirements-dev.txt
  serve   mkdocs serve (wiki local em http://127.0.0.1:8000)
  build   mkdocs build --strict
  check   wikisync check   (verifica wiki <-> server)
  sync    wikisync apply   (dry-run; use --yes para gravar, --path para um arquivo)
  index   wikisync index   (gera INDEX.md e index.json)
  test    testes do wikisync
  lint    yamllint, ansible-lint, syntax-check e docker compose config

O ambiente fica em .venv/ na raiz; defina HOMESERVER_VENV para usar outro local.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = os.name == "nt"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def venv_dir() -> Path:
    """Local do ambiente: .venv/ na raiz, ou HOMESERVER_VENV se definido
    (útil quando a pasta do repo é um disco lento ou compartilhado)."""
    override = os.environ.get("HOMESERVER_VENV")
    return Path(override).expanduser() if override else repo_root() / ".venv"


def venv_python() -> Path:
    return venv_dir() / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


def venv_bin(name: str) -> str:
    venv = venv_dir()
    exe = venv / ("Scripts" if IS_WINDOWS else "bin") / (name + (".exe" if IS_WINDOWS else ""))
    return str(exe)


def run(cmd: list[str], **kw) -> int:
    print("$ " + " ".join(cmd), flush=True)
    return subprocess.call(cmd, **kw)


def _require_venv() -> str:
    py = venv_python()
    if not py.exists():
        sys.exit("Ambiente não encontrado. Rode primeiro: python tools/dev.py setup")
    return str(py)


def _wikisync(subcommand: str, args: list[str]) -> int:
    env = dict(os.environ, PYTHONPATH=str(repo_root() / "tools"), PYTHONUTF8="1")
    return run([_require_venv(), "-m", "wikisync", subcommand, *args], cwd=repo_root(), env=env)


def task_setup(args: list[str]) -> int:
    py = venv_python()
    if not py.exists():
        code = run([sys.executable, "-m", "venv", str(venv_dir())])
        if code:
            return code
    run([str(py), "-m", "pip", "install", "-q", "--upgrade", "pip"])
    return run([str(py), "-m", "pip", "install", "-r", str(repo_root() / "requirements-dev.txt"), *args])


def task_serve(args: list[str]) -> int:
    _require_venv()
    return run([venv_bin("mkdocs"), "serve", "-f", "wiki/mkdocs.yml", *args], cwd=repo_root())


def task_build(args: list[str]) -> int:
    _require_venv()
    return run([venv_bin("mkdocs"), "build", "--strict", "-f", "wiki/mkdocs.yml", *args], cwd=repo_root())


def task_check(args: list[str]) -> int:
    return _wikisync("check", args)


def task_sync(args: list[str]) -> int:
    return _wikisync("apply", args)


def task_index(args: list[str]) -> int:
    return _wikisync("index", args)


def task_test(args: list[str]) -> int:
    env = dict(os.environ, PYTHONPATH=str(repo_root() / "tools"), PYTHONUTF8="1")
    return run([_require_venv(), "-m", "pytest", "tools/wikisync/tests", "-q", *args], cwd=repo_root(), env=env)


def task_lint(args: list[str]) -> int:
    _require_venv()
    root = repo_root()
    failures = 0
    yaml_targets = [p for p in ("server/", ".github/") if (root / p).exists()]
    failures += bool(run([venv_bin("yamllint"), "-c", ".yamllint", *yaml_targets], cwd=root))
    if IS_WINDOWS:
        print("AVISO: lint de Ansible ignorado no Windows (use WSL/Linux ou o CI).")
    else:
        ansible_dir = root / "server" / "ansible"
        env = dict(os.environ, ANSIBLE_CONFIG=str(ansible_dir / "ansible.cfg"))
        failures += bool(run([venv_bin("ansible-lint"), "--profile", "min", "playbooks/", "roles/"], cwd=ansible_dir, env=env))
        for playbook in sorted((ansible_dir / "playbooks").glob("*.yml")):
            failures += bool(run(
                [venv_bin("ansible-playbook"), "-i", "localhost,", "--syntax-check", f"playbooks/{playbook.name}"],
                cwd=ansible_dir, env=env,
            ))
    if shutil.which("docker"):
        for compose in sorted((root / "server" / "docker" / "stacks").glob("*/docker-compose.yml")):
            failures += bool(run(["docker", "compose", "-f", str(compose), "config", "-q"], cwd=root))
    else:
        print("AVISO: docker não encontrado; 'docker compose config' ignorado.")
    print("lint: OK" if not failures else f"lint: {failures} verificação(ões) falharam")
    return 1 if failures else 0


TASKS = {
    "setup": task_setup,
    "serve": task_serve,
    "build": task_build,
    "check": task_check,
    "sync": task_sync,
    "index": task_index,
    "test": task_test,
    "lint": task_lint,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in TASKS:
        print(__doc__)
        return 2
    return TASKS[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
