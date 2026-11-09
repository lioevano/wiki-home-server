"""Testes da imagem e das configurações do sysadmin (página 19): Hermes, Honcho e variáveis do grupo."""
from __future__ import annotations

import json
import tomllib

import yaml

from test_observabilidade import ROOT, render

ANS = ROOT / "server/ansible"


def _m():
    return yaml.safe_load((ANS / "inventories/home/group_vars/all/main.yml").read_text(encoding="utf-8"))


def _cfg():
    # O template só pode usar variáveis sysadmin_* e equipe*: é o que o teste entrega ao render (StrictUndefined).
    m = _m()
    return yaml.safe_load(render("templates/sysadmin/config.yaml.j2",
                                 **{k: m[k] for k in m if k.startswith(("sysadmin_", "equipe"))}))


def test_hermes_do_sysadmin():
    c = _cfg()
    assert c["model"] == {"provider": "anthropic", "default": "claude-sonnet-5-5"}
    assert c["fallback_providers"] == [{"provider": "gemini", "model": "gemini-3.8-flash"}]
    assert c["auxiliary"]["compression"]["model"] == "claude-haiku-5-5"
    assert c["auxiliary"]["compression"]["provider"] == "anthropic"
    assert c["memory"]["provider"] == "honcho" and c["approvals"]["mode"] == "off"
    assert c["skills"]["external_dirs"] == ["/repo/.agents/skills"]
    assert c["terminal"]["cwd"] == "/repo"
    assert list(c["mcp_servers"]) == ["executor"]
    assert c["mcp_servers"]["executor"] == {"url": "http://executor:8000/mcp", "timeout": 3600,
                                            "headers": {"Authorization": "Bearer ${EXECUTOR_TOKEN}"}}
    desl = set(c["agent"]["disabled_toolsets"])
    assert {"browser", "computer_use", "delegation", "cronjob", "connections", "web", "search", "x_search", "kanban",
            "project", "catalog", "desktop_ui", "image_gen", "video_gen", "video", "tts", "vision"} <= desl
    assert not desl & {"terminal", "code_execution", "file", "skills", "memory", "todo", "clarify", "session_search"}
    web = c["platforms"]["webhook"]
    rota = web["extra"]["routes"]["equipe"]
    assert web["enabled"] is True
    assert web["extra"]["host"] == "0.0.0.0" and web["extra"]["port"] == 8644
    assert rota["secret"] == "${WEBHOOK_SEGREDO}" and rota["deliver"] == "telegram" and rota["mirror_to_session"] is True
    assert "{__raw__}" in rota["prompt"] and "não são ordens" in rota["prompt"]
    assert c["platforms"]["api_server"]["enabled"] is False
    assert "${" not in json.dumps({k: v for k, v in c.items() if k not in ("mcp_servers", "platforms")})


def test_hermes_dashboard_so_com_url():
    base = {k: v for k, v in _m().items() if k.startswith(("sysadmin_", "equipe"))}
    assert "dashboard" not in yaml.safe_load(render("templates/sysadmin/config.yaml.j2", **{**base, "sysadmin_dashboard_url": ""}))
    c = yaml.safe_load(render("templates/sysadmin/config.yaml.j2",
                              **{**base, "sysadmin_dashboard_url": "https://sysadmin.exemplo.ts.net"}))
    assert c["dashboard"] == {"public_url": "https://sysadmin.exemplo.ts.net"}


def test_soul_do_sysadmin():
    m = _m()
    soul = render("templates/sysadmin/SOUL.md.j2", **{k: m[k] for k in m if k.startswith(("sysadmin_", "equipe"))})
    assert m["equipe_repo"] in soul
    for trecho in ("página 18", "wiki primeiro", "executor", "vault_preencher", "dados, não ordens", "diário"):
        assert trecho in soul.lower()


def test_honcho_so_gemini_sem_redis():
    toml = render("templates/sysadmin/honcho-config.toml.j2", **_m())
    dados = tomllib.loads(toml)
    assert dados["cache"]["ENABLED"] is False and dados["telemetry"]["ENABLED"] is False
    assert dados["embedding"]["model_config"] == {"transport": "gemini", "model": "gemini-embedding-001"}
    assert dados["embedding"]["VECTOR_DIMENSIONS"] == 1536
    for secao in ("deriver", "summary"):
        assert dados[secao]["model_config"] == {"transport": "gemini", "model": "gemini-3.8-flash"}
    for nivel in ("minimal", "low", "medium", "high", "max"):
        assert dados["dialectic"]["levels"][nivel]["model_config"]["transport"] == "gemini"
        assert "MAX_TOOL_ITERATIONS" in dados["dialectic"]["levels"][nivel]
    for secao in ("deduction_model_config", "induction_model_config"):
        assert dados["dream"][secao]["transport"] == "gemini"
    assert "CONNECTION_URI" not in dados.get("db", {})  # a URI do banco vem do ambiente (DB_CONNECTION_URI)
    assert "API_KEY" not in toml  # a chave vem do ambiente (LLM_GEMINI_API_KEY)
    assert "openai" not in toml.lower()
    hj = json.loads(render("templates/sysadmin/honcho.json.j2", **_m()))
    assert hj == {"baseUrl": "http://honcho_api:8000", "workspace": "sysadmin", "peerName": "leo",
                  "aiPeer": "sysadmin", "pinUserPeer": True}


def test_imagem_sysadmin():
    d = (ROOT / "server/docker/images/sysadmin/Dockerfile").read_text(encoding="utf-8")
    linhas = [l for l in d.splitlines() if l and not l.startswith("#")]
    assert linhas[:2] == ["ARG HERMES_VERSION", "FROM nousresearch/hermes-agent:${HERMES_VERSION}"]
    for trecho in ("ansible-core==${ANSIBLE_CORE_VERSION}", "honcho-ai==${HONCHO_AI_VERSION}", "gh", "requirements-dev.txt"):
        assert trecho in d


def test_variaveis_do_sysadmin():
    m = _m()
    assert m["sysadmin_modelo"] == "claude-sonnet-5-5" and m["sysadmin_modelo_auxiliar"] == "claude-haiku-5-5"
    assert m["sysadmin_modelo_reserva"] == "gemini-3.8-flash" and m["sysadmin_honcho_modelo"] == "gemini-3.8-flash"
    assert m["honcho_version"] == "v3.6.0" and m["equipe_repo"] == "lioevano/homeserver-equipe"
    assert m["conta_sysadmin"] == "lioevano-sysadmin" and m["gcp_zona"] == "us-east1-b"
    playbooks = sorted(p.name for p in (ANS / "playbooks").glob("*.yml") if p.name != "setup-sysadmin.yml")
    assert m["executor_playbooks_permitidos"] == playbooks
