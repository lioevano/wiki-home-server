"""Testes da imagem e das configurações do sysadmin (página 19): Hermes, Honcho e variáveis do grupo."""
from __future__ import annotations

import io
import json
import sys
import tomllib

import yaml

from test_observabilidade import ROOT, render

sys.path.insert(0, str(ROOT / "server/scripts/gcp"))
from separar_segredos import CAMPOS, separar, main as separar_main  # noqa: E402

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


# --- Segredos na VM, compose e firewall (Task 10) ---

DADOS = {c: f"v-{c}" for c in CAMPOS} | {
    "ssh_chave_privada": "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----"}
COMPOSE = ROOT / "server/docker/stacks/sysadmin/docker-compose.yml"


def _env(texto: str) -> dict[str, str]:
    return dict(l.split("=", 1) for l in texto.splitlines() if l)


def test_campos():
    assert set(CAMPOS) == {"anthropic_api_key", "gemini_api_key", "telegram_bot_sysadmin", "telegram_bot_aprovacoes",
        "telegram_chat_id", "tailscale_chave_sysadmin", "tailscale_chave_homeserver", "github_token_sysadmin",
        "github_token_carteiro", "vault_senha", "ssh_chave_privada", "ssh_chave_publica", "honcho_db_senha",
        "executor_token", "webhook_segredo", "dashboard_usuario", "dashboard_senha", "dashboard_segredo"}


def test_separar_isola_o_executor(tmp_path):
    separar(DADOS, tmp_path, 1001, 1000)
    sa = (tmp_path / "sysadmin.env").read_text()
    assert "v-vault_senha" not in sa and "OPENSSH" not in sa and "v-tailscale_chave_homeserver" not in sa
    assert "TELEGRAM_BOT_TOKEN=v-telegram_bot_sysadmin" in sa and "GH_TOKEN=v-github_token_sysadmin" in sa
    assert set(_env(sa)) == {"ANTHROPIC_API_KEY", "GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS",
        "TELEGRAM_HOME_CHANNEL", "GH_TOKEN", "EXECUTOR_TOKEN", "WEBHOOK_SEGREDO",
        "HERMES_DASHBOARD_BASIC_AUTH_USERNAME", "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD",
        "HERMES_DASHBOARD_BASIC_AUTH_SECRET"}
    assert _env(sa)["TELEGRAM_HOME_CHANNEL"] == _env(sa)["TELEGRAM_ALLOWED_USERS"] == "v-telegram_chat_id"
    ex = (tmp_path / "executor.env").read_text()
    assert "TELEGRAM_BOT_TOKEN=v-telegram_bot_aprovacoes" in ex and "v-anthropic_api_key" not in ex
    assert set(_env(ex)) == {"EXECUTOR_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TAILSCALE_CHAVE_HOST",
                             "GITHUB_TOKEN_EQUIPE", "WEBHOOK_SEGREDO"}
    assert _env(ex)["TAILSCALE_CHAVE_HOST"] == "v-tailscale_chave_homeserver"
    assert _env(ex)["GITHUB_TOKEN_EQUIPE"] == "v-github_token_carteiro"
    assert (tmp_path / "executor/id_ed25519").read_text().endswith("\n")
    assert (tmp_path / "executor/vault_senha").read_text() == "v-vault_senha\n"
    assert (tmp_path / "executor/id_ed25519.pub").read_text() == "v-ssh_chave_publica\n"
    assert (tmp_path / "host/tailscale_chave").read_text() == "v-tailscale_chave_sysadmin\n"
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert oct(f.stat().st_mode & 0o777) in ("0o600", "0o400")
    for f in ("executor/vault_senha", "executor/id_ed25519"):
        assert (tmp_path / f).stat().st_mode & 0o777 == 0o400
    assert "LLM_GEMINI_API_KEY=v-gemini_api_key" in (tmp_path / "honcho.env").read_text()
    assert "postgresql+psycopg://honcho:v-honcho_db_senha@honcho_db:5432/honcho" in (tmp_path / "honcho.env").read_text()
    assert _env((tmp_path / "honcho-db.env").read_text()) == {
        "POSTGRES_USER": "honcho", "POSTGRES_DB": "honcho", "POSTGRES_PASSWORD": "v-honcho_db_senha"}


def test_separar_substitui_o_destino_anterior(tmp_path):
    destino = tmp_path / "run-sysadmin"
    destino.mkdir()
    (destino / "velho.env").write_text("x")
    separar(DADOS, destino, 1001, 1000)
    assert not (destino / "velho.env").exists() and (destino / "executor.env").is_file()
    assert [p.name for p in tmp_path.iterdir()] == ["run-sysadmin"]  # sem temporário esquecido


def test_separar_falha_fechada(tmp_path, capsys, monkeypatch):
    falta = {k: v for k, v in DADOS.items() if k != "executor_token"} | {"webhook_segredo": " "}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(falta)))
    assert separar_main(["--destino", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "executor_token" in err and "webhook_segredo" in err and not any(tmp_path.iterdir())
    assert "v-" not in err  # nenhum valor vai para o erro


def test_separar_main_nao_imprime_segredo(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(DADOS)))
    assert separar_main(["--destino", str(tmp_path / "d")]) == 0
    saida = capsys.readouterr()
    assert "v-" not in saida.out + saida.err and (tmp_path / "d/sysadmin.env").is_file()


def test_compose_isola_o_sysadmin():
    c = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    s, p, e = c["services"]["sysadmin"], c["services"]["sysadmin_painel"], c["services"]["executor"]
    assert set(s["networks"]) == {"sysadmin_rede", "interna"} and "ports" not in s
    assert p["ports"] == ["127.0.0.1:9119:9119"] and p["command"][:1] == ["dashboard"]
    assert set(e["networks"]) == {"executor_rede", "interna"} and "ports" not in e
    assert c["networks"]["interna"]["internal"] is True
    assert c["networks"]["sysadmin_rede"]["ipam"]["config"] == [{"subnet": "${SYSADMIN_REDE_SUBNET}"}]
    for nome in ("sysadmin", "sysadmin_painel"):
        vols = " ".join(c["services"][nome]["volumes"])
        assert "/run/sysadmin/sysadmin.env:/opt/data/.env:ro" in vols and "executor" not in vols and "docker.sock" not in vols
        assert "${SYSADMIN_DATA_PATH}/saida:/saida:ro" in c["services"][nome]["volumes"]
        assert "/run/sysadmin/executor" not in json.dumps(c["services"][nome])
        assert c["services"][nome]["environment"]["HOMESERVER_VENV"] == "/opt/dev"
    assert "/run/sysadmin/executor:/segredos:ro" in e["volumes"]
    assert c["services"]["honcho_api"]["image"] == "ghcr.io/plastic-labs/honcho:v3.6.0"
    assert c["services"]["honcho_db"]["image"] == "pgvector/pgvector:0.8.7-pg17"
    assert set(c["services"]["honcho_db"]["networks"]) == {"honcho_interna"}
    assert c["services"]["honcho_deriver"]["entrypoint"] == ["/app/.venv/bin/python", "-m", "src.deriver"]
    for svc in c["services"].values():
        assert (svc.get("labels") or {}).get("diun.enable") == "false"
        assert "no-new-privileges:true" in svc.get("security_opt", [])
        assert svc["restart"] == "unless-stopped"
        # só o painel publica porta; 8644 (webhook) e 8000 (MCP) ficam na rede interna
        assert "ports" not in svc or svc is p


def test_compose_env_files_nao_obrigatorios():
    """R3: o lint roda sem /run/sysadmin; a falha fechada fica no separar_segredos e no Config do executor."""
    c = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    esperado = {"executor": "executor.env", "honcho_api": "honcho.env", "honcho_deriver": "honcho.env",
                "honcho_db": "honcho-db.env"}
    for nome, arq in esperado.items():
        assert c[nome]["env_file"] == [{"path": f"/run/sysadmin/{arq}", "required": False}]
    for nome in ("sysadmin", "sysadmin_painel"):
        assert "env_file" not in c[nome]  # o .env do Hermes entra pelo volume, não pelo ambiente do container


def test_executor_recebe_toda_variavel_obrigatoria(tmp_path):
    sys.path.insert(0, str(ROOT / "server/docker/images/executor"))
    from executor.config import OBRIGATORIAS
    c = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["executor"]
    separar(DADOS, tmp_path / "x", 1001, 1000)
    do_arquivo = set(_env((tmp_path / "x/executor.env").read_text()))
    do_compose = set(c["environment"])
    assert not do_arquivo & do_compose  # cada variável tem uma só origem
    assert (set(OBRIGATORIAS.values()) | {"EXECUTOR_PLAYBOOKS"}) <= do_arquivo | do_compose
    assert c["environment"]["WEBHOOK_URL"] == "http://sysadmin:8644/webhooks/equipe"
    for var in do_compose - {"WEBHOOK_URL", "TZ"}:
        assert c["environment"][var] == f"${{{var}}}"  # vem do .env da stack


def test_variaveis_do_compose_no_env_template():
    import re
    modelo = (ROOT / "server/docker/stacks/.env.template").read_text(encoding="utf-8")
    nomes = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", modelo, re.M))
    for v in ("SYSADMIN_IMAGE_TAG", "EXECUTOR_IMAGE_TAG", "SYSADMIN_DATA_PATH", "SYSADMIN_REDE_SUBNET",
              "EXECUTOR_PLAYBOOKS", "EXECUTOR_ROTAS", "ANSIBLE_USUARIO_HOST", "REPO_URL_RAW", "EQUIPE_REPO",
              "CONTA_SYSADMIN"):
        assert v in nomes


def test_firewall_do_sysadmin():
    t = render("roles/infra/sysadmin-gcp/templates/firewall-sysadmin.sh.j2", sysadmin_rede_subnet="172.30.10.0/24",
               sysadmin_bloqueios=["100.64.0.0/10", "192.168.15.0/24", "169.254.169.254/32"])
    for destino in ("100.64.0.0/10", "192.168.15.0/24", "169.254.169.254/32"):
        assert f"-s 172.30.10.0/24 -d {destino} -j DROP" in t
    assert "DOCKER-USER" in t and "set -euo pipefail" in t


def test_separar_protege_o_env_do_compose(tmp_path, capsys, monkeypatch):
    separar(DADOS | {"honcho_db_senha": "a$b@c/d"}, tmp_path / "ok", 1001, 1000)
    assert "POSTGRES_PASSWORD=a$$b@c/d" in (tmp_path / "ok/honcho-db.env").read_text()  # compose interpola `$`
    assert "honcho:a%24b%40c%2Fd@honcho_db" in (tmp_path / "ok/honcho.env").read_text()  # URI com a senha codificada
    # quebra de linha num valor de .env injetaria outra variável: recusa por nome
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(DADOS | {"gemini_api_key": "x\nGH_TOKEN=y"})))
    assert separar_main(["--destino", str(tmp_path / "ruim")]) == 1
    assert "gemini_api_key" in capsys.readouterr().err and not (tmp_path / "ruim").exists()
