"""tools/dev.py: o lint dos composes usa o .env.template como contrato de variáveis."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("dev", ROOT / "tools" / "dev.py")
dev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dev)


def test_env_lint_preenche_vazios_e_mantem_valores():
    modelo = "\n".join([
        "# comentário",
        "SYSTEM_TIMEZONE=America/Sao_Paulo",
        "BASE_DOMAIN_FROM_VAULT=",
        "CORE_SERVICES_VM_IP_VAR=",
        "AI_DESKTOP_VM_IP=",
        "MEDIA_STACK_DATA_PATH=",
        "AI_RENDER_GID=",
        "LITELLM_KEY_OPENWEBUI=",
        "",
    ])
    env = dict(l.split("=", 1) for l in dev.env_lint(modelo).splitlines())
    assert env["SYSTEM_TIMEZONE"] == "America/Sao_Paulo"
    assert env["CORE_SERVICES_VM_IP_VAR"] == env["AI_DESKTOP_VM_IP"] == "192.0.2.10"
    assert env["MEDIA_STACK_DATA_PATH"] == "/lint/media_stack_data_path"
    assert env["AI_RENDER_GID"] == "1000"
    assert env["BASE_DOMAIN_FROM_VAULT"] == "lint" and env["LITELLM_KEY_OPENWEBUI"] == "lint"
    assert all(v for v in env.values())


def test_variavel_fora_do_template_falha():
    saida = 'time="x" level=warning msg="The \\"NOVA_VAR\\" variable is not set. Defaulting to a blank string."'
    assert dev.variaveis_ausentes(saida) == ["NOVA_VAR"]
    assert dev.variaveis_ausentes("tudo certo") == []


def test_template_cobre_todos_os_composes():
    """Regra do server/AGENTS.md: toda ${VAR} de um compose existe no .env.template."""
    import re
    modelo = (ROOT / "server/docker/stacks/.env.template").read_text(encoding="utf-8")
    definidas = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", modelo, re.M))
    usadas = set()
    for compose in (ROOT / "server/docker/stacks").glob("*/docker-compose.yml"):
        usadas |= set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", compose.read_text(encoding="utf-8")))
    assert usadas - definidas == set()


def test_pytest_mostra_motivo_dos_pulos():
    assert "-rs" in dev.PYTEST_ARGS
