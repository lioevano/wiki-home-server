"""Testes dos templates e arquivos de observabilidade do server (Loki, Alloy, Prometheus, alertas)."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import jinja2
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def _bool(v) -> bool:
    return str(v).lower() in ("true", "1", "yes", "on")


def render(rel: str, **vars) -> str:
    """Renderiza server/ansible/<rel> como o Ansible faria (StrictUndefined, filtro bool)."""
    env = jinja2.Environment(
        undefined=jinja2.StrictUndefined,
        loader=jinja2.FileSystemLoader(ROOT / "server" / "ansible"),
        keep_trailing_newline=True,
    )
    env.filters["bool"] = _bool
    return env.get_template(rel).render(**vars)


def test_loki_schema_v13_tsdb():
    cfg = yaml.safe_load(render("templates/loki-local-config.yaml.j2"))
    periodo = cfg["schema_config"]["configs"][-1]
    assert periodo["schema"] == "v13" and periodo["store"] == "tsdb"
    assert periodo["object_store"] == "filesystem" and periodo["index"]["period"] == "24h"
    assert "tsdb_shipper" in cfg["storage_config"]
    assert "alertmanager_url" not in str(cfg.get("ruler", {}))
