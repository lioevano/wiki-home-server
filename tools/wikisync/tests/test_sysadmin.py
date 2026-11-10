"""Testes da imagem e das configurações do sysadmin (página 19): Hermes, Honcho e variáveis do grupo."""
from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import sys
import tomllib

import pytest
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
        assert f"-i br-sysadmin -s 172.30.10.0/24 -d {destino} -j DROP" in t
    assert "-t raw" in t and "PREROUTING" in t and "DOCKER-USER" not in t and "set -euo pipefail" in t
    # o servidor de metadados também é o DNS da VM: DNS passa, o resto (token na porta 80) é bloqueado
    meta = "-i br-sysadmin -s 172.30.10.0/24 -d 169.254.169.254/32"
    drop = t.index(f"{meta} -j DROP")
    for proto in ("udp", "tcp"):
        assert t.index(f"{meta} -p {proto} --dport 53 -j RETURN") < drop


def test_rede_do_sysadmin_endurecida():
    c = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    r = c["networks"]["sysadmin_rede"]
    assert r["driver_opts"] == {"com.docker.network.bridge.name": "br-sysadmin"}
    assert r["enable_ipv6"] is False
    for nome in ("sysadmin", "sysadmin_painel"):
        assert c["services"][nome]["cap_drop"] == ["NET_RAW"]


def test_separar_diretorios_0700(tmp_path):
    separar(DADOS, tmp_path / "d", 1001, 1000)
    for d in ("d", "d/executor", "d/host"):
        assert (tmp_path / d).stat().st_mode & 0o777 == 0o700


def test_separar_protege_o_env_do_compose(tmp_path, capsys, monkeypatch):
    separar(DADOS | {"honcho_db_senha": "a$b@c/d"}, tmp_path / "ok", 1001, 1000)
    assert "POSTGRES_PASSWORD=a$$b@c/d" in (tmp_path / "ok/honcho-db.env").read_text()  # compose interpola `$`
    assert "honcho:a%24b%40c%2Fd@honcho_db" in (tmp_path / "ok/honcho.env").read_text()  # URI com a senha codificada
    # quebra de linha num valor de .env injetaria outra variável: recusa por nome
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(DADOS | {"gemini_api_key": "x\nGH_TOKEN=y"})))
    assert separar_main(["--destino", str(tmp_path / "ruim")]) == 1
    assert "gemini_api_key" in capsys.readouterr().err and not (tmp_path / "ruim").exists()


# --- Playbook setup-sysadmin.yml e role infra/sysadmin-gcp (Task 11) ---

PB_SA = ANS / "playbooks/setup-sysadmin.yml"
ROLE_SA = ANS / "roles/infra/sysadmin-gcp"
PULL = ("ansible-pull -U https://github.com/lioevano/wiki-home-server.git -C main -d /opt/sysadmin/pull "
        "-i server/ansible/inventories/home/hosts.ini -l sysadmin-gcp server/ansible/playbooks/setup-sysadmin.yml")


def test_playbook_roda_local_e_fora_do_full_deploy():
    pb = yaml.safe_load(PB_SA.read_text(encoding="utf-8"))
    assert pb[0]["hosts"] == "gcp" and pb[0]["become"] is True
    papeis = [r["role"] if isinstance(r, dict) else r for r in pb[0]["roles"]]
    assert papeis == ["infra/docker", "infra/tailscale", "infra/sysadmin-gcp"]
    ts = next(r for r in pb[0]["roles"] if isinstance(r, dict) and r["role"] == "infra/tailscale")["vars"]
    assert ts["tailscale_tags"] == ["tag:sysadmin"] and ts["tailscale_aceitar_rotas"] is True and ts["tailscale_rotas"] == []
    full = [p["import_playbook"] for p in yaml.safe_load((ANS / "playbooks/full-deploy.yml").read_text(encoding="utf-8"))]
    assert "setup-sysadmin.yml" not in full
    hosts = (ANS / "inventories/home/hosts.ini").read_text(encoding="utf-8")
    assert "[gcp]\nsysadmin-gcp ansible_connection=local" in hosts


def test_role_sysadmin_gcp():
    t = yaml.safe_load((ANS / "roles/infra/sysadmin-gcp/tasks/main.yml").read_text(encoding="utf-8"))
    nomes = [x["name"] for x in t]
    for n in ("Swap de 4 GB", "Segredos do Secret Manager no tmpfs", "Firewall da rede do sysadmin",
              "Clone de trabalho do sysadmin", "Clone da main para o executor", "Plugin do Honcho",
              "Imagem do sysadmin", "Imagem do executor", "Stack do sysadmin", "Atualização diária (ansible-pull)",
              "Backup diário no GCS"):
        assert n in nomes
    stack = next(x for x in t if x["name"] == "Stack do sysadmin")
    assert stack["community.docker.docker_compose_v2"]["project_src"] == "/opt/sysadmin/stack"
    assert all(x.get("no_log") is True for x in t if "segredo" in x["name"].lower())
    timer = (ANS / "roles/infra/sysadmin-gcp/templates/sysadmin-pull.service.j2").read_text(encoding="utf-8")
    assert "ansible-pull -U https://github.com/lioevano/wiki-home-server.git -C main" in timer and "-l sysadmin-gcp" in timer
    unit = (ANS / "roles/infra/sysadmin-gcp/templates/sysadmin-segredos.service.j2").read_text(encoding="utf-8")
    assert "Before=docker.service" in unit and "gcloud secrets versions access latest --secret=sysadmin-segredos" in unit


def test_executor_pode_todos_os_playbooks_menos_o_proprio():
    m = yaml.safe_load((ANS / "inventories/home/group_vars/all/main.yml").read_text(encoding="utf-8"))
    todos = {p.name for p in (ANS / "playbooks").glob("*.yml")}
    assert set(m["executor_playbooks_permitidos"]) == todos - {"setup-sysadmin.yml"}


def _defaults_sa() -> dict:
    return yaml.safe_load((ROLE_SA / "defaults/main.yml").read_text(encoding="utf-8"))


def _tarefas_sa(arquivo: str = "main.yml") -> list[dict]:
    return yaml.safe_load((ROLE_SA / "tasks" / arquivo).read_text(encoding="utf-8"))


def _todas(tarefas: list[dict]):
    """Tarefas e blocos, achatados (com os filhos dos blocos)."""
    for t in tarefas:
        yield t
        for chave in ("block", "rescue", "always"):
            yield from _todas(t.get(chave) or [])


def _unit(nome: str, **extra) -> str:
    return render(f"roles/infra/sysadmin-gcp/templates/{nome}",
                  **{**_m(), **_defaults_sa(), "sysadmin_bucket": "proj-sysadmin", **extra})


def _rotas() -> list[str]:
    """tailscale_rotas do group_vars com os IPs do [all:vars] do hosts.ini."""
    import configparser
    import jinja2
    ini = configparser.ConfigParser(allow_no_value=True, delimiters=("=",), strict=False)
    ini.read_string((ANS / "inventories/home/hosts.ini").read_text(encoding="utf-8"))
    ips = {k: v for k, v in ini["all:vars"].items() if k.endswith("_ip_var")}
    return [jinja2.Environment().from_string(r).render(**ips) for r in _m()["tailscale_rotas"]]


def test_segredos_antes_do_tailscale_e_sem_vault():
    """A chave do Tailscale vem de /run/sysadmin: o pre_tasks separa os segredos antes dos roles. Só o main.yml
    entra por vars_files (a VM não tem a senha do vault de casa)."""
    play = yaml.safe_load(PB_SA.read_text(encoding="utf-8"))[0]
    assert play["vars_files"] == ["../inventories/home/group_vars/all/main.yml"]
    pre = play["pre_tasks"][0]["ansible.builtin.include_role"]
    assert pre == {"name": "infra/sysadmin-gcp", "tasks_from": "segredos.yml"}
    ts = next(r for r in play["roles"] if isinstance(r, dict) and r["role"] == "infra/tailscale")["vars"]
    assert ts["tailscale_auth_key"] == "{{ lookup('file', '/run/sysadmin/host/tailscale_chave') }}"
    assert ts["tailscale_hostname"] == "sysadmin" and ts["tailscale_coredns"] is False and ts["tailscale_ufw"] is False
    dk = next(r for r in play["roles"] if isinstance(r, dict) and r["role"] == "infra/docker")["vars"]
    assert dk == {"docker_portainer_mode": "nenhum", "docker_usuarios_grupo": []}  # sem Portainer, sem reboot
    seg = next(t for t in _tarefas_sa() if t["name"] == "Segredos do Secret Manager no tmpfs")
    assert seg["ansible.builtin.include_tasks"] == "segredos.yml"
    # nenhum nome com "segredo" sem no_log, em todos os arquivos de tarefas do role (blocos inclusive)
    for arq in (ROLE_SA / "tasks").glob("*.yml"):
        for t in _todas(_tarefas_sa(arq.name)):
            if "segredo" in t.get("name", "").lower():
                assert t.get("no_log") is True, (arq.name, t["name"])
    # nenhuma variável do vault no playbook, no role e nos templates do sysadmin
    vault = set(yaml.safe_load((ANS / "inventories/home/group_vars/all/vault.yml.example").read_text(encoding="utf-8")))
    import re
    textos = [PB_SA.read_text(encoding="utf-8")] + [p.read_text(encoding="utf-8") for p in ROLE_SA.rglob("*")
                                                     if p.is_file()]
    textos += [p.read_text(encoding="utf-8") for p in (ANS / "templates/sysadmin").glob("*.j2")]
    usadas = {v for t in textos for v in re.findall(r"\b([a-z_][a-z0-9_]*)\b", t)}
    # tailscale_auth_key: o nome é o do role; o valor vem do tmpfs (lookup acima), não do vault de casa
    assert not (usadas & vault) - {"tailscale_auth_key"}, usadas & vault


def test_projeto_do_servidor_de_metadados():
    seg = _tarefas_sa("segredos.yml")
    uri = next(t for t in seg if "ansible.builtin.uri" in t)["ansible.builtin.uri"]
    assert uri["url"] == "http://metadata.google.internal/computeMetadata/v1/project/project-id"
    assert uri["headers"] == {"Metadata-Flavor": "Google"}
    assert _defaults_sa()["sysadmin_bucket"] == "{{ gcp_projeto }}-sysadmin"


def test_unit_dos_segredos():
    d = _defaults_sa()
    u = _unit("sysadmin-segredos.service.j2")
    assert "After=network-online.target" in u and "Before=docker.service" in u
    pre = next(l for l in u.splitlines() if l.startswith("ExecStartPre="))
    assert "rm -rf /run/.sysadmin.*" in pre  # sobras de uma troca interrompida, antes de separar
    assert u.index(pre) < u.index("\nExecStart=")
    assert ("python3 /usr/local/lib/sysadmin/separar_segredos.py --destino /run/sysadmin "
            f"--uid-executor {d['sysadmin_executor_uid']} --uid-sysadmin {d['sysadmin_uid']}") in u
    assert "pipefail" in u  # gcloud falhou: o separar_segredos não roda com stdin vazio
    assert "gs://proj-sysadmin/entrada/vault.yml" in u and "/opt/sysadmin/saida/vault.yml" in u
    assert "Type=oneshot" in u and "RemainAfterExit=true" in u
    seg = _tarefas_sa("segredos.yml")
    copia = next(t for t in seg if "separar_segredos.py" in json.dumps(t.get("ansible.builtin.copy", {})))
    assert copia["ansible.builtin.copy"]["dest"] == "/usr/local/lib/sysadmin/separar_segredos.py"


def test_docker_depois_dos_segredos_e_do_firewall():
    t = list(_todas(_tarefas_sa()))
    dropin = next(x for x in t if "docker.service.d" in json.dumps(x.get("ansible.builtin.copy", {})))
    conteudo = dropin["ansible.builtin.copy"]["content"]
    assert "Requires=sysadmin-segredos.service firewall-sysadmin.service" in conteudo
    assert "After=sysadmin-segredos.service firewall-sysadmin.service" in conteudo
    fw = _unit("firewall-sysadmin.service.j2")
    assert "Before=docker.service" in fw and "ExecStart=/usr/local/sbin/firewall-sysadmin.sh" in fw


def test_rede_e_bloqueios_do_sysadmin():
    import ipaddress
    m = _m()
    rede = ipaddress.ip_network(m["sysadmin_rede_subnet"])
    assert str(rede) == "172.30.10.0/24"
    b = m["sysadmin_bloqueios_fixos"]
    for destino in ("100.64.0.0/10", "169.254.169.254/32", f"{next(rede.hosts())}/32",
                    "{{ ansible_facts.default_ipv4.address }}/32"):
        assert destino in b, destino
    redes = [ipaddress.ip_network(x) for x in b if "{{" not in x]
    for rota in _rotas():  # a LAN de casa cobre todas as rotas que o executor recebe
        assert any(ipaddress.ip_network(rota).subnet_of(r) for r in redes if r.version == 4), rota


def test_env_da_stack():
    import re
    texto = render("roles/infra/sysadmin-gcp/templates/sysadmin.env.j2",
                   **{**_m(), **_defaults_sa(), "tailscale_rotas": _rotas()})
    env = _env("\n".join(l for l in texto.splitlines() if not l.startswith("#")))
    usadas = set(re.findall(r"\$\{(\w+)\}", COMPOSE.read_text(encoding="utf-8")))
    assert usadas <= set(env), usadas - set(env)
    assert env["EXECUTOR_ROTAS"] == ",".join(_rotas()) and len(_rotas()) == 3
    assert env["SYSADMIN_REDE_SUBNET"] == _m()["sysadmin_rede_subnet"]  # uma fonte só: o group_vars
    assert env["SYSADMIN_DATA_PATH"] == "/opt/sysadmin"
    assert env["DOCKER_PUID"] == env["DOCKER_PGID"] == str(_defaults_sa()["sysadmin_uid"]) == "1000"
    assert env["SYSADMIN_IMAGE_TAG"] == _m()["sysadmin_version"] and env["EXECUTOR_IMAGE_TAG"] == _m()["executor_version"]
    assert env["ANSIBLE_USUARIO_HOST"] == _m()["proxmox_ansible_user_on_host"]
    assert env["REPO_URL_RAW"] == "https://raw.githubusercontent.com/lioevano/wiki-home-server/main"
    assert env["EQUIPE_REPO"] == _m()["equipe_repo"] and env["CONTA_SYSADMIN"] == _m()["conta_sysadmin"]
    pb = env["EXECUTOR_PLAYBOOKS"]
    assert pb.startswith("'") and pb.endswith("'") and "'" not in pb[1:-1]  # literal para o compose
    playbooks = json.loads(pb[1:-1])
    assert list(playbooks) == _m()["executor_playbooks_permitidos"]
    assert playbooks["setup-vpn.yml"] == "setup-vpn.yml"
    assert playbooks["setup-n8n-volumes.yml"] == "Diretórios e variáveis do n8n"  # descrição do ops, quando há
    for nome in env:
        assert not re.search(r"TOKEN|SENHA|SECRET|SEGREDO|KEY|PASSWORD|CHAVE", nome), nome


def test_imagens_locais_do_sysadmin():
    t = list(_todas(_tarefas_sa()))
    imagens = {x["community.docker.docker_image"]["name"]: x["community.docker.docker_image"]
               for x in t if "community.docker.docker_image" in x}
    ex, sa = imagens["localhost/homeserver/executor"], imagens["localhost/homeserver/sysadmin"]
    assert ex["tag"] == "{{ executor_version }}" and sa["tag"] == "{{ sysadmin_version }}"
    assert ex["source"] == sa["source"] == "build"
    assert ex["build"]["args"] == {"UID": "{{ sysadmin_executor_uid }}", "GID": "{{ sysadmin_executor_uid }}"}
    assert sa["build"]["args"] == {"HERMES_VERSION": "{{ hermes_version }}",
                                   "ANSIBLE_CORE_VERSION": "{{ ops_ansible_core_version }}",
                                   "HONCHO_AI_VERSION": "{{ honcho_ai_version }}"}
    # contextos: o que cada Dockerfile copia
    texto = json.dumps(t)
    for origem in ("docker/images/executor/", "docker/images/ops/ops", "docker/images/aprovador/aprovador",
                   "templates/agents/ops-requirements.txt.j2", "ansible/requirements.yml",
                   "docker/images/sysadmin/", '"requirements-dev.txt"', "wiki/requirements.txt"):
        assert origem in texto, origem
    d = (ROOT / "server/docker/images/sysadmin/Dockerfile").read_text(encoding="utf-8")
    assert "COPY requirements.yml" in d and "ansible-galaxy collection install -r" in d  # coleções no build


def test_clones_e_honcho():
    t = {x["name"]: x for x in _todas(_tarefas_sa())}
    trab = t["Clone de trabalho do sysadmin"]["ansible.builtin.git"]
    assert trab["dest"] == "/opt/sysadmin/repo" and trab["update"] is False
    ex = t["Clone da main para o executor"]["ansible.builtin.git"]
    assert ex["dest"] == "/opt/sysadmin/repo-executor" and ex["update"] is False and ex["version"] == "main"
    nomes = list(t)
    assert nomes.index("Clone da main para o executor") < nomes.index("Stack do sysadmin")
    plugin = json.dumps(t["Plugin do Honcho"])
    assert "{{ honcho_version }}" in plugin and "/opt/sysadmin/build/honcho-src" in plugin
    assert "hermes-plugin-honcho/" in plugin and "/opt/sysadmin/config/plugins/honcho/" in plugin
    cfg = json.dumps([x for x in t.values() if "ansible.builtin.template" in x])
    for destino in ("/opt/sysadmin/config/config.yaml", "/opt/sysadmin/config/SOUL.md",
                    "/opt/sysadmin/config/honcho.json", "/opt/sysadmin/honcho-config.toml"):
        assert destino in cfg, destino


def test_root_fora_dos_diretorios_dos_containers():
    """R13: o root do host não escreve nem roda git onde um container escreve (symlink plantado, hooks e
    core.fsmonitor no .git/config virariam escrita ou execução como root no host)."""
    t = list(_todas(_tarefas_sa()))
    texto = json.dumps(t)
    assert "/opt/sysadmin/hermes" not in texto  # nada do root dentro do HERMES_HOME (só o próprio diretório)
    dirs = next(x for x in t if x["name"] == "Diretórios do sysadmin")
    assert dirs["ansible.builtin.file"]["follow"] is False and "recurse" not in dirs["ansible.builtin.file"]
    caminhos = [i["path"] for i in dirs["loop"]]
    assert "hermes" in caminhos and not [c for c in caminhos if c.startswith(("hermes/", "repo"))]
    cfg = next(i for i in dirs["loop"] if i["path"] == "config")
    assert cfg["dono"] == "root" and cfg["modo"] == "0755"
    assert "safe.directory" not in texto  # o root não roda git nos clones dos containers
    for nome, var in (("Clone de trabalho do sysadmin", "sysadmin_repo_existe"),
                      ("Clone da main para o executor", "sysadmin_repo_executor_existe")):
        clone = next(x for x in t if x["name"] == nome)
        assert clone["when"] == f"not {var}.stat.exists", nome  # só se o diretório ainda não existe
        stat = next(x for x in t if x.get("register") == var)["ansible.builtin.stat"]
        assert stat["follow"] is False
    for x in t:
        f = x.get("ansible.builtin.file") or {}
        if f.get("recurse"):  # só a entrega do clone recém-criado, sem seguir links
            assert f["follow"] is False and x["when"].endswith(".changed"), x["name"]
    # a unit dos segredos baixa o vault de entrada num diretório do root e só o renomeia para dentro de saida/
    u = _unit("sysadmin-segredos.service.j2")
    assert "saida/.vault" not in u and "mktemp -d /opt/sysadmin/build/" in u and "mv -T" in u


def test_configs_do_hermes_somente_leitura():
    c = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    for nome in ("sysadmin", "sysadmin_painel"):
        vols = c[nome]["volumes"]
        for arq in ("config.yaml", "SOUL.md", "honcho.json", "plugins/honcho"):
            assert f"${{SYSADMIN_DATA_PATH}}/config/{arq}:/opt/data/{arq}:ro" in vols, (nome, arq)


def test_rebuild_por_versao():
    """Versão nova reconstrói, e build que falhou é refeito: o carimbo .construido só é gravado depois do build."""
    t = list(_todas(_tarefas_sa()))
    for img, ctx, versoes in (
            ("sysadmin", "/opt/sysadmin/build/sysadmin",
             ("{{ hermes_version }}", "{{ ops_ansible_core_version }}", "{{ honcho_ai_version }}", "{{ sysadmin_version }}")),
            ("executor", "/opt/sysadmin/build/executor",
             ("{{ ops_fastmcp_version }}", "{{ ops_ansible_core_version }}", "{{ sysadmin_executor_uid }}",
              "{{ executor_version }}"))):
        i_carimbo = next(i for i, x in enumerate(t)
                         if (x.get("ansible.builtin.copy") or {}).get("dest") == f"{ctx}/.versoes")
        conteudo = t[i_carimbo]["ansible.builtin.copy"]["content"]
        for v in versoes:
            assert v in conteudo, (img, v)
        i_limpa = next(i for i, x in enumerate(t) if (x.get("ansible.builtin.file") or {}).get("path") == f"{ctx}/.construido")
        assert t[i_limpa]["ansible.builtin.file"]["state"] == "absent"
        i_build = next(i for i, x in enumerate(t) if (x.get("community.docker.docker_image") or {}).get("name")
                       == f"localhost/homeserver/{img}")
        i_stat = next(i for i, x in enumerate(t) if (x.get("ansible.builtin.stat") or {}).get("path") == f"{ctx}/.construido")
        forca = t[i_build]["community.docker.docker_image"]["force_source"]
        assert f"not {t[i_stat]['register']}.stat.exists" in forca and f"{t[i_stat]['register']}.stat.checksum" in forca
        assert i_limpa < i_stat < i_build
        i_marca = next(i for i, x in enumerate(t)
                       if (x.get("ansible.builtin.copy") or {}).get("dest") == f"{ctx}/.construido")
        marca = t[i_marca]["ansible.builtin.copy"]
        assert marca["src"] == f"{ctx}/.versoes" and marca["remote_src"] is True
        assert i_carimbo < i_limpa < i_build < i_marca, img


def test_swap_cifrada():
    """R14: o que o kernel joga na swap (inclusive segredos do tmpfs) não fica legível no disco: chave nova a cada boot."""
    swap = next(x for x in _tarefas_sa() if x["name"] == "Swap de 4 GB")
    texto = json.dumps(swap)
    linhas = {x["ansible.builtin.lineinfile"]["path"]: x["ansible.builtin.lineinfile"]
              for x in swap["block"] if "ansible.builtin.lineinfile" in x}
    assert linhas["/etc/crypttab"]["line"] == "cryptswap /swapfile /dev/urandom swap,cipher=aes-xts-plain64,size=256"
    fstab = [x["ansible.builtin.lineinfile"] for x in swap["block"]
             if (x.get("ansible.builtin.lineinfile") or {}).get("path") == "/etc/fstab"]
    assert {"line": "/dev/mapper/cryptswap none swap sw 0 0"}.items() <= next(f for f in fstab if "line" in f).items()
    assert any(f.get("state") == "absent" and "/swapfile" in f["regexp"] for f in fstab)  # nada de swap em claro
    assert "mkswap /swapfile" not in texto and "swapon /swapfile" not in texto
    assert "systemd-cryptsetup@cryptswap.service" in texto and "dev-mapper-cryptswap.swap" in texto


def test_units_do_gcloud():
    u = _unit("sysadmin-segredos.service.j2")
    assert "Restart=on-failure" in u and "RestartSec=60" in u  # falha passageira do Secret Manager
    # sem passar por failed entre as tentativas: o job do Docker (Requires=) espera em vez de falhar por dependência
    assert "\nRestartMode=direct\n" in u
    for nome in ("sysadmin-segredos.service.j2", "sysadmin-backup.service.j2", "sysadmin-backup.sh.j2",
                 "sysadmin-pull.service.j2", "firewall-sysadmin.service.j2"):
        texto = _unit(nome)
        unit = texto if nome.endswith(".service.j2") else _unit("sysadmin-backup.service.j2")
        if "gcloud" in texto:
            assert "Environment=CLOUDSDK_CORE_DISABLE_FILE_LOGGING=1" in unit, nome
    assert "Environment=CLOUDSDK_CORE_DISABLE_FILE_LOGGING=1" in _unit("sysadmin-backup.service.j2")
    # o Ansible não fica preso se o segredo nunca chegar: a unit segue tentando, o play falha com aviso
    sep = next(x for x in _tarefas_sa("segredos.yml") if "ansible.builtin.systemd_service" in x)
    assert isinstance(sep.get("timeout"), int) and sep["timeout"] > 0


def test_timers_do_sysadmin():
    s = _unit("sysadmin-pull.service.j2")
    assert PULL in s
    # ansible-pull roda de /: o -i relativo só vale depois do checkout (senão o git seria pulado)
    assert "WorkingDirectory=/\n" in s
    assert "Environment=ANSIBLE_CONFIG=/opt/sysadmin/pull/server/ansible/ansible.cfg" in s  # roles_path
    assert "Environment=ANSIBLE_VARS_ENABLED=\n" in s  # sem group_vars automático: o vault cifrado não abre aqui
    assert "OnCalendar=*-*-* 05:17:00 UTC" in _unit("sysadmin-pull.timer.j2")
    assert "OnCalendar=*-*-* 06:07:00 UTC" in _unit("sysadmin-backup.timer.j2")
    b = _unit("sysadmin-backup.sh.j2")
    assert b.startswith("#!/bin/bash") and "set -euo pipefail" in b
    assert "docker exec honcho_db pg_dump" in b and "gs://proj-sysadmin/backup/" in b and "gcloud storage cp" in b
    assert "--exclude='hermes/.env*'" in b and "--exclude='hermes/auth.json*'" in b and "tar -C /opt/sysadmin" in b
    assert "ExecStart=/usr/local/sbin/sysadmin-backup.sh" in _unit("sysadmin-backup.service.j2")


def test_painel_pelo_tailscale_serve():
    t = list(_todas(_tarefas_sa()))
    status = next(x for x in t if x.get("ansible.builtin.command") == "tailscale serve status --json")
    assert status["changed_when"] is False
    serve = next(x for x in t if "tailscale serve --bg" in str(x.get("ansible.builtin.command", "")))
    assert "--https=443 http://127.0.0.1:9119" in serve["ansible.builtin.command"]
    assert "127.0.0.1:9119" in serve["when"]  # só quando ainda não está servindo


def test_grupo_gcp_fora_dos_playbooks_de_casa():
    """Handoff 10: nenhum playbook de casa alcança o sysadmin-gcp por hosts: all; o grupo [gcp] não é filho de nada."""
    for p in (ANS / "playbooks").glob("*.yml"):
        for play in yaml.safe_load(p.read_text(encoding="utf-8")) or []:
            hosts = str(play.get("hosts", ""))
            assert hosts not in ("all", "*") and (hosts != "gcp" or p.name == "setup-sysadmin.yml"), p.name
    hosts = (ANS / "inventories/home/hosts.ini").read_text(encoding="utf-8")
    import re
    for filhos in re.findall(r"^\[\w+:children\]\n((?:[^\[\n].*\n?)*)", hosts, re.M):
        assert "gcp" not in filhos.split()


def test_docker_reaproveitado_sem_portainer():
    d = (ANS / "roles/infra/docker/defaults/main.yml").read_text(encoding="utf-8")
    dd = yaml.safe_load(d)
    assert dd["docker_usuarios_grupo"] == ["{{ vm_ansible_user_name }}", "{{ docker_user_name_on_vm }}"]
    t = yaml.safe_load((ANS / "roles/infra/docker/tasks/main.yml").read_text(encoding="utf-8"))
    grupo = next(x for x in t if "ao grupo 'docker'" in x["name"])
    assert grupo["loop"] == "{{ docker_usuarios_grupo }}"


# --- criar-sysadmin.sh (Cloud Shell, Task 12) ---

SH = ROOT / "server/scripts/gcp/criar-sysadmin.sh"


def test_criar_sysadmin_barato_e_fechado():
    s = SH.read_text(encoding="utf-8")
    assert s.startswith("#!/bin/bash") and "set -euo pipefail" in s
    assert 'REGIAO="${REGIAO:-us-east1}"' in s and 'TIPO="${TIPO:-e2-micro}"' in s
    assert "us-west1|us-central1|us-east1" in s  # recusa região fora do free tier
    assert "--boot-disk-type=pd-standard" in s and "--boot-disk-size=30GB" in s
    assert "gcloud compute firewall-rules create sysadmin-recusa-entrada" in s and "--priority=100" in s
    assert "--action=DENY" in s and "--rules=all" in s
    assert "secretmanager.secretAccessor" in s and "roles/owner" not in s and "roles/editor" not in s
    assert "gcloud billing budgets create" in s and "--budget-amount=2USD" in s
    assert "read -rs" in s and "gcloud secrets create sysadmin-segredos --data-file=-" in s  # o JSON vai pelo stdin
    for campo in CAMPOS:
        assert campo in s


def test_criar_sysadmin_shellcheck():
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck ausente")
    r = subprocess.run(["shellcheck", str(SH), str(ROOT / "server/scripts/gcp/preparar-host.sh")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def _startup() -> str:
    """O startup-script embutido (heredoc 'STARTUP')."""
    s = SH.read_text(encoding="utf-8")
    m = re.search(r"<<'STARTUP'\n(.*?)\nSTARTUP\n", s, re.S)
    assert m, "heredoc STARTUP ausente"
    return m.group(1)


def test_criar_sysadmin_sintaxe_bash():
    r = subprocess.run(["bash", "-n", str(SH)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    r = subprocess.run(["bash", "-n"], input=_startup(), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_criar_sysadmin_campos_iguais_ao_separador():
    s = SH.read_text(encoding="utf-8")
    m = re.search(r"local CAMPOS=\(([^)]*)\)", s)
    assert m and tuple(m.group(1).split()) == CAMPOS  # mesma lista e mesma ordem do separar_segredos.py


def test_startup_script_repete_o_ansible_pull_da_unit():
    """O primeiro boot e o timer diário precisam se comportar igual (handoff da Task 11)."""
    unit = (ANS / "roles/infra/sysadmin-gcp/templates/sysadmin-pull.service.j2").read_text(encoding="utf-8")
    st = _startup()
    exec_start = re.search(r"^ExecStart=(ansible-pull .*)$", unit, re.M).group(1)
    assert exec_start in st  # mesmo comando, mesmos argumentos
    for var in re.findall(r"^Environment=(ANSIBLE_\w+=\S*)$", unit, re.M):
        assert f"export {var}" in st
    assert "ANSIBLE_VARS_ENABLED=" in st
    # a unit roda de "/" (o -i relativo só existe depois do checkout)
    assert re.search(r"^\s*cd / \|\| return 1$", st, re.M) and "WorkingDirectory=/\n" in unit
    # coleções: mesmo destino da unit, a partir do requirements.yml do repositório
    assert "-p /usr/share/ansible/collections" in unit and "-p /usr/share/ansible/collections" in st
    assert "server/ansible/requirements.yml" in st
    # ansible-core num venv ligado em /usr/local/bin, na versão do group_vars (substituída na criação)
    assert "/usr/local/bin" in st and "-m venv" in st and "ansible-core==@VERSAO_ANSIBLE@" in st
    # o endereço do repositório é o do role
    assert _defaults_repo() in exec_start and _defaults_repo_raw() in st
    # metadado da VM: nenhum segredo
    assert not re.search(r"(?i)token|senha|password|api_key|secret", st)


def _defaults_repo() -> str:
    return yaml.safe_load((ANS / "roles/infra/sysadmin-gcp/defaults/main.yml").read_text(encoding="utf-8"))["sysadmin_repo_url"]


def _defaults_repo_raw() -> str:
    return yaml.safe_load((ANS / "roles/infra/sysadmin-gcp/defaults/main.yml").read_text(encoding="utf-8"))["sysadmin_repo_url_raw"]


def test_criar_sysadmin_nomes_do_role():
    s = SH.read_text(encoding="utf-8")
    assert 'BUCKET="${PROJETO}-sysadmin"' in s  # sysadmin_bucket
    assert "sysadmin-vm" in s and "gs://${BUCKET}/entrada/vault.yml" in s  # lido pela unit sysadmin-segredos
    assert "--senha-vault-arquivo" in s and "ssh-keygen -t ed25519 -N" in s


def test_criar_sysadmin_reaproveita_o_segredo_existente():
    s = SH.read_text(encoding="utf-8")
    assert "REUSAR=1" in s and 'if [ "${REGERAR:-0}" = 1 ]' in s  # padrão: reaproveita; REGERAR=1 pede confirmação
    assert 'if [ "$REUSAR" = 1 ]; then\n        etapa "7/11 e 8/11' in s and "coletar_e_gravar\n" in s
    assert 'gcloud storage ls "gs://${BUCKET}/entrada/vault.yml"' in s  # vault de entrada só se faltar
    assert "gcloud secrets versions access latest --secret=$SEGREDO | python3 -c" in s  # onde ler as senhas
    assert "o que já existe é mantido" not in s and "REAPROVEITADO" in s
    # falha depois de o segredo existir: a saída diz que os valores estão no Secret Manager
    assert "SEGREDO_FEITO=1" in s and "os valores estão lá" in s
    # a senha do vault do segredo vai a um arquivo por redirecionamento, nunca por argumento
    assert '>"$TMP/senha-vault"' in s


def test_startup_script_espera_o_apt_e_repete():
    st = _startup()
    assert len(re.findall(r"apt-get\b", st)) == len(re.findall(r"apt-get -o DPkg::Lock::Timeout=600 ", st)) == 2
    assert "for tentativa in 1 2 3" in st and "sleep 60" in st and "touch \"$MARCA\"" in st
    assert st.index("touch \"$MARCA\"") > st.index("if primeiro_boot")  # a marca só depois do sucesso
    assert 'log() { echo "sysadmin-boot:' in st  # progresso no console serial


def test_criar_sysadmin_iap_de_emergencia_e_orcamento():
    s = SH.read_text(encoding="utf-8")
    i = s.index("gcloud compute firewall-rules create sysadmin-iap-emergencia")
    bloco = s[i:i + 400]
    for parte in ("--direction=INGRESS", "--priority=90", "--action=ALLOW", "--rules=tcp:22",
                  "--source-ranges=35.235.240.0/20", "--disabled"):
        assert parte in bloco
    assert "firewall-rules update sysadmin-iap-emergencia --no-disabled" in s
    assert "firewall-rules update sysadmin-iap-emergencia --disabled" in s
    for cmd in ("gcloud billing budgets list", "gcloud billing budgets create"):
        trecho = s[s.index(cmd):].split("\n")[0]
        assert '--billing-project="$PROJETO"' in trecho


def test_skills_do_sysadmin():
    for nome in ("implantar-fase", "status-implantacao", "equipe"):
        canon = (ROOT / f".agents/skills/{nome}/SKILL.md").read_text(encoding="utf-8")
        inv = (ROOT / f".claude/skills/{nome}/SKILL.md").read_text(encoding="utf-8")
        fm = lambda t: yaml.safe_load(t.split("---")[1])
        assert fm(canon)["name"] == fm(inv)["name"] == nome and fm(canon)["description"] == fm(inv)["description"]
        assert f".agents/skills/{nome}/SKILL.md" in (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    eq = (ROOT / ".agents/skills/equipe/SKILL.md").read_text(encoding="utf-8")
    for etiqueta in ("papel:sysadmin", "papel:metricas", "papel:apps", "papel:variaveis", "papel:atualizacoes",
                     "papel:backup", "papel:assistente", "estado:aberto", "estado:em-andamento", "estado:feito",
                     "estado:bloqueado", "diario"):
        assert etiqueta in eq
    assert "nunca" in eq.lower() and "segredo" in eq.lower()


def test_skills_do_sysadmin_citam_as_ferramentas_reais():
    ferr = (ROOT / "server/docker/images/executor/executor/ferramentas.py").read_text(encoding="utf-8")
    nomes = set(re.findall(r"^\s+def (\w+)\(", ferr, re.M)) - {"fazer", "_runner"}
    texto = {n: (ROOT / f".agents/skills/{n}/SKILL.md").read_text(encoding="utf-8")
             for n in ("implantar-fase", "status-implantacao", "equipe")}
    for t in ("diagnostico", "ansible_check", "ansible_aplicar", "vault_preencher", "preparar_host", "aprovacao_id"):
        assert t in texto["implantar-fase"], t
    assert "vault_status" in texto["status-implantacao"] and "free -m" in texto["status-implantacao"]
    for n, t in texto.items():
        for citado in re.findall(r"`(\w+)\(", t):          # só chamadas `ferramenta(`
            assert citado in nomes, f"{n}: ferramenta inexistente {citado}"
    assert "lioevano/homeserver-equipe" in texto["equipe"] and "equipe_repo" in texto["implantar-fase"]
    assert "gh issue create -R lioevano/homeserver-equipe --label papel:" in texto["equipe"]


def test_skills_do_sysadmin_sem_comandos_inexistentes():
    arquivos = [*(ROOT / ".agents/skills").glob("*/SKILL.md"), *(ROOT / ".claude/skills").glob("*/SKILL.md"),
                ROOT / "AGENTS.md", ROOT / "INDEX.md"]
    for a in arquivos:
        for i, linha in enumerate(a.read_text(encoding="utf-8").splitlines(), 1):
            assert not re.search(r"/fase\b|/status(?![\w-])", linha), f"{a.relative_to(ROOT)}:{i}: {linha}"
    st = (ROOT / ".agents/skills/status-implantacao/SKILL.md").read_text(encoding="utf-8")
    assert "terminal" in st and "Peça ao Léo que rode" not in st
    for n in ("implantar-fase", "equipe"):
        assert "ansible-playbook" in (ROOT / f".agents/skills/{n}/SKILL.md").read_text(encoding="utf-8")


# --- Task 14: regra do AGENTS.md, página 19 e catálogo ---

def test_regra_do_agents_md_e_pagina():
    a = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "botão do executor" in a and "página 19" in a and "push na `main`" in a
    p = (ROOT / "wiki/docs/01-manual-implementacao/19-sysadmin-gcp.md").read_text(encoding="utf-8")
    for arq in ("scripts/gcp/criar-sysadmin.sh", "scripts/gcp/preparar-host.sh", "scripts/gcp/separar_segredos.py",
                "scripts/tailscale/acl.json", "docker/stacks/sysadmin/docker-compose.yml", "ansible/playbooks/setup-sysadmin.yml",
                "docker/images/executor/executor/carteiro.py", "docker/images/sysadmin/Dockerfile"):
        assert f"`{arq}`" in p
    cat = (ROOT / "wiki/docs/02-visao-geral-arquitetura/09-catalogo-aplicacoes.md").read_text(encoding="utf-8")
    assert all(f"| `{n}` |" in cat for n in ("sysadmin", "executor", "honcho"))


# --- Revisão final do 5a ---

def _semear_vault(tmp_path, *, main: bool, saida: bool) -> bool:
    """Roda o ExecStart do vault de entrada da unit com /opt/sysadmin em tmp_path e gcloud/chown falsos."""
    import shlex
    u = _unit("sysadmin-segredos.service.j2")
    linha = next(l for l in u.splitlines() if l.startswith("ExecStart=-") and "entrada/vault.yml" in l)
    argv = shlex.split(linha[len("ExecStart=-"):])
    assert argv[:2] == ["/bin/sh", "-c"]
    raiz = tmp_path / "opt"
    script = argv[2].replace("$$", "$").replace("/opt/sysadmin", str(raiz))
    falsos = tmp_path / "bin"
    falsos.mkdir(parents=True)
    (falsos / "gcloud").write_text('#!/bin/sh\nfor a; do d="$a"; done\necho entrada > "$d"\n', encoding="utf-8")
    (falsos / "chown").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for b in falsos.iterdir():
        b.chmod(0o755)
    vault_main = raiz / "repo-executor/server/ansible/inventories/home/group_vars/all/vault.yml"
    if main:
        vault_main.parent.mkdir(parents=True)
        vault_main.write_text("main", encoding="utf-8")
    if saida:
        (raiz / "saida").mkdir(parents=True)
        (raiz / "saida/vault.yml").write_text("saida", encoding="utf-8")
    import os
    r = subprocess.run(["/bin/sh", "-c", script], capture_output=True, text=True,
                       env={**os.environ, "PATH": f"{falsos}:{os.environ['PATH']}"})
    assert r.returncode == 0, r.stderr
    destino = raiz / "saida/vault.yml"
    return destino.exists() and destino.read_text(encoding="utf-8").strip() == "entrada"


def test_unit_so_semeia_o_vault_quando_a_main_nao_tem(tmp_path):
    """R17: com vault.yml no clone da main do executor, o vault de entrada (da fase 1) não volta para saida/."""
    assert _semear_vault(tmp_path / "a", main=False, saida=False) is True
    assert _semear_vault(tmp_path / "b", main=True, saida=False) is False
    assert _semear_vault(tmp_path / "c", main=False, saida=True) is False
    u = _unit("sysadmin-segredos.service.j2")
    assert "/opt/sysadmin/repo-executor/server/ansible/inventories/home/group_vars/all/vault.yml" in u


def test_criar_sysadmin_em_reuso_a_main_manda_no_vault():
    """R17: em reuso, com vault.yml no clone da main, nada de vault novo nem de entrada/ nova."""
    s = SH.read_text(encoding="utf-8")
    i_clone = s.index('git clone --quiet --depth 1 --branch main "$REPO_URL" "$TMP/repo"')
    teste = ('if [ "$REUSAR" = 1 ] && [ -e "$TMP/repo/server/ansible/inventories/home/group_vars/all/vault.yml" ]; then')
    assert teste in s
    i = s.index(teste)
    bloco = s[i:s.index("fi\n", i)]
    assert "gerar_vault=0" in bloco and "a main manda" in bloco
    assert 'gcloud storage rm "gs://${BUCKET}/entrada/vault.yml"' in bloco   # a VM recriada não semeia a entrada velha
    assert i_clone < i < s.index('if [ "$gerar_vault" = 1 ]; then')
    # a checagem do bucket só vale quando a main não tem vault (elif) e o envio só acontece com gerar_vault=1
    assert 'elif [ "$REUSAR" = 1 ] && gcloud storage ls "gs://${BUCKET}/entrada/vault.yml"' in s
    assert s.count('gcloud storage cp "$TMP/vault.yml" "gs://${BUCKET}/entrada/vault.yml"') == 1
    assert s.index('if [ "$gerar_vault" = 1 ]; then') < s.index('gcloud storage cp "$TMP/vault.yml"')


def test_criar_sysadmin_regerar_avisa_do_vault_na_main():
    """REGERAR=1 com vault na main: a senha nova deixa o executor sem ler o vault da main; o aviso vem antes da pergunta."""
    s = SH.read_text(encoding="utf-8")
    i = s.index('if [ "${REGERAR:-0}" = 1 ]; then')
    bloco = s[i:s.index("else", i)]
    assert 'git clone --quiet --depth 1 --branch main "$REPO_URL" "$TMP/repo"' in bloco
    assert "remova antes o vault.yml da" in bloco and "gcloud compute instances delete" in bloco
    assert bloco.index("remova antes") < bloco.index("read -r -p")
    assert '[ -d "$TMP/repo" ] || git clone' in s                       # a etapa 9 não clona de novo


def test_bloqueios_do_sysadmin_cobrem_as_rotas():
    """As três /32 de tailscale_rotas entram na lista, além da LAN literal (se a LAN mudar, as rotas seguem)."""
    m = _m()
    assert m["sysadmin_bloqueios"] == "{{ sysadmin_bloqueios_fixos + tailscale_rotas }}"
    assert "192.168.15.0/24" in m["sysadmin_bloqueios_fixos"]
    t = render("roles/infra/sysadmin-gcp/templates/firewall-sysadmin.sh.j2", sysadmin_rede_subnet="172.30.10.0/24",
               sysadmin_bloqueios=[b for b in m["sysadmin_bloqueios_fixos"] if "{{" not in b] + _rotas())
    for rota in _rotas():
        assert f"-i br-sysadmin -s 172.30.10.0/24 -d {rota} -j DROP" in t, rota


def test_logs_da_stack_com_rotacao():
    """O executor audita em stdout: sem rotação, o json-file encheria os 30 GB da VM."""
    c = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    for nome, svc in c["services"].items():
        assert svc.get("logging") == {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}}, nome


def test_regra_do_agents_md_push_em_branch():
    a = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert ("push em branch de trabalho e abertura de PR pela conta de máquina são permitidos sem botão (spec S1/S7); "
            "push na `main` continua proibido para todos") in a.replace("\n    ", " ")


def test_docs_da_revisao_final():
    """PR do vault antes do playbook; nada de alerta inexistente; ACL antes das três chaves; o check só na fase 2."""
    wiki = ROOT / "wiki/docs/01-manual-implementacao"
    p19 = (wiki / "19-sysadmin-gcp.md").read_text(encoding="utf-8")
    p18 = (wiki / "18-roteiro-primeiro-deploy.md").read_text(encoding="utf-8")
    p14 = (wiki / "14-vpn-tailscale.md").read_text(encoding="utf-8")
    skill = (ROOT / ".agents/skills/implantar-fase/SKILL.md").read_text(encoding="utf-8")
    assert "ao fim da fase e você mescla" not in p19 and "**antes** de qualquer playbook" in p19
    assert "**Antes de qualquer playbook que use as chaves novas**" in skill
    assert "no log do container, com rotação de 3 × 10 MB" in p19 and "auditoria em arquivo" not in p19
    assert "sysadmin sem modelo" not in p19 and "não há aviso automático" in p19 and "docker logs sysadmin" in p19
    assert "duas chaves de uso único" not in p19 + p18 and "**três chaves de uso único**" in p18
    fase0 = p18[p18.index("## Fase 0"):p18.index("## Fase 1")]
    assert fase0.index("**Primeiro** a ACL") < fase0.index("**três chaves")
    conf = p14[p14.index("## Primeira configuração"):p14.index("## O que muda nas aplicações")]
    assert conf.index("**ACL primeiro") < conf.index("**Três chaves de uso único**")
    assert all(t in conf for t in ("`tailscale_auth_key`", "`tailscale_chave_homeserver`", "`tailscale_chave_sysadmin`"))
    fase1 = p18[p18.index("## Fase 1"):p18.index("## Fase 2")]
    assert "só vale depois da fase 2" in fase1
    assert "**Só depois da fase 2" in p19
    dr = (ROOT / "wiki/docs/04-manutencao-recuperacao/04-reconstruindo-infraestrutura.md").read_text(encoding="utf-8")
    assert "novo `preparar_host`" in dr and "`tailscale_auth_key_host`" in dr and "`tailscale_chave_homeserver`" in dr


# --- Pendências da 5a: alerta, ansible-core e contextos de build ---

def _bloco(nome: str) -> list[dict]:
    return next(t for t in _tarefas_sa() if t.get("name") == nome)["block"]


def test_units_que_rodam_sozinhas_avisam_a_falha():
    for unit in ("sysadmin-backup.service.j2", "sysadmin-pull.service.j2"):
        u = (ROLE_SA / "templates" / unit).read_text(encoding="utf-8")
        unidade = u.split("[Service]")[0]
        assert "OnFailure=sysadmin-alerta@%n.service" in unidade, unit
    a = (ROLE_SA / "templates/sysadmin-alerta.service.j2").read_text(encoding="utf-8")
    assert "ExecStart=/usr/local/sbin/sysadmin-alerta.sh %i" in a
    tarefas = _bloco("Aviso de falha das units")
    scripts = tarefas[0]
    assert scripts["loop"] == ["sysadmin-alerta.sh", "sysadmin-ansible-core.sh"]
    assert scripts["ansible.builtin.template"]["mode"] == "0750"
    assert tarefas[1]["ansible.builtin.template"]["dest"] == "/etc/systemd/system/sysadmin-alerta@.service"


def test_alerta_nao_poe_o_token_na_linha_de_comando_nem_le_o_journal():
    s = (ROLE_SA / "templates/sysadmin-alerta.sh.j2").read_text(encoding="utf-8")
    assert "/run/sysadmin/host/alerta.env" in s and "--config -" in s
    assert "journalctl -u $unidade." in s and "journalctl -u \"$unidade\"" not in s   # só sugere o comando
    linha_curl = next(l for l in s.splitlines() if "curl " in l)
    assert "$token" not in linha_curl


def test_separar_entrega_ao_host_so_o_bot_de_aprovacoes(tmp_path):
    separar(DADOS, tmp_path / "d", 1001, 1000)
    alerta = tmp_path / "d/host/alerta.env"
    assert _env(alerta.read_text()) == {"TELEGRAM_BOT_TOKEN": "v-telegram_bot_aprovacoes",
                                        "TELEGRAM_CHAT_ID": "v-telegram_chat_id"}
    assert alerta.stat().st_mode & 0o777 == 0o400


def test_ansible_core_da_vm_segue_o_group_vars_antes_do_pull(tmp_path):
    u = (ROLE_SA / "templates/sysadmin-pull.service.j2").read_text(encoding="utf-8")
    pre = [l for l in u.splitlines() if l.startswith("ExecStartPre=")]
    assert pre[0] == "ExecStartPre=-/usr/local/sbin/sysadmin-ansible-core.sh"   # antes das coleções
    s = (ROLE_SA / "templates/sysadmin-ansible-core.sh.j2").read_text(encoding="utf-8")
    assert "/opt/sysadmin/pull/server/ansible/inventories/home/group_vars/all/main.yml" in s
    # a mesma extração de versão do criar-sysadmin.sh, sobre o main.yml real
    m = re.search(r"sed -n '([^']+)' \"\$main\"", s)
    assert m
    r = subprocess.run(["sed", "-n", m.group(1), str(ANS / "inventories/home/group_vars/all/main.yml")],
                       capture_output=True, text=True)
    assert r.stdout.strip() == _m()["ops_ansible_core_version"]


def test_contexto_de_build_apaga_o_que_saiu_do_repositorio():
    for bloco, ctx, quando in (("Imagem do sysadmin", "/opt/sysadmin/build/sysadmin", "sysadmin_contexto.changed"),
                               ("Imagem do executor", "/opt/sysadmin/build/executor", "sysadmin_executor_codigo.changed")):
        t = _bloco(bloco)
        i = next(i for i, x in enumerate(t) if x.get("ansible.builtin.include_tasks") == "contexto-limpo.yml")
        assert t[i]["vars"]["contexto_destino"] == ctx
        assert {".versoes", ".construido"} <= set(t[i]["vars"]["contexto_gerados"])
        j = next(j for j, x in enumerate(t) if (x.get("ansible.builtin.file") or {}).get("path") == f"{ctx}/.construido")
        assert i < j and "contexto_limpeza.changed" in t[j]["when"] and quando in t[j]["when"]
    limpo = _tarefas_sa("contexto-limpo.yml")
    assert limpo[-1]["register"] == "contexto_limpeza" and limpo[-1]["ansible.builtin.file"]["state"] == "absent"


def test_scripts_do_host_passam_no_shellcheck(tmp_path):
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck ausente")
    for nome in ("sysadmin-alerta.sh.j2", "sysadmin-ansible-core.sh.j2"):
        r = subprocess.run(["shellcheck", "-s", "sh", str(ROLE_SA / "templates" / nome)], capture_output=True, text=True)
        assert r.returncode == 0, nome + r.stdout
