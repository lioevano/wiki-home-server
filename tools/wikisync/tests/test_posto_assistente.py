"""Posto de agentes (4c3, página 16) e assistente (4c4, página 17): stacks, playbooks e configs geradas."""
from __future__ import annotations

import json

import yaml

from test_fotos_arquivos import COMUNS, _configs, _pb_tasks, _vars_compose
from test_midia import _env, _svc
from test_observabilidade import ROOT, render

ANS = ROOT / "server/ansible"
POSTO = ROOT / "server/docker/stacks/posto/docker-compose.yml"
ASSISTENTE = ROOT / "server/docker/stacks/assistente/docker-compose.yml"
AGENTS = ROOT / "server/docker/stacks/agents/docker-compose.yml"
PB_POSTO = ANS / "playbooks/setup-posto-volumes.yml"
PB_ASSIST = ANS / "playbooks/setup-assistente-volumes.yml"
SEGREDOS = {"agents_autonomos_keys": {"agentes": "ag-AGENTES-SEGREDO", "assistente": "ag-ASSIST-SEGREDO"},
            "litellm_client_keys": {"assistente": "sk-ASSIST-SEGREDO"}, "hermes_telegram_bot_token": "123:BOT",
            "telegram_chat_id": "4242"}


def _main() -> dict:
    return yaml.safe_load((ANS / "inventories/home/group_vars/all/main.yml").read_text(encoding="utf-8"))


def _vault() -> dict:
    return yaml.safe_load((ANS / "inventories/home/group_vars/all/vault.yml.example").read_text(encoding="utf-8"))


# --- Posto (4c3) ---

def test_posto_sem_login_proprio_so_pelo_traefik():
    s = _svc(POSTO)["posto"]
    assert s["image"] == "${POSTO_IMAGE}" and s["pull_policy"] == "never" and s["labels"]["diun.enable"] == "false"
    assert s["ports"] == ["${AI_DESKTOP_VM_IP}:3005:3005"]  # o porteiro (Caddy), não o Vibe Kanban
    assert _env(s)["HOST"] == "127.0.0.1"  # o Vibe Kanban não atende as redes ai_network e notes_mcp
    core = {r["porta"]: r["origens"] for r in _main()["firewall_docker_portas"]["ai-desktop-vm"]}
    assert core[3005] == ["{{ core_services_vm_ip_var }}"]  # só o Traefik da core
    assert {"kanban", "aprovacoes"} <= set(_main()["authelia_dominios_admins"])
    rotas = yaml.safe_load(render("roles/infra/traefik-config/templates/dynamic_ai_services.yml.j2",
                                  base_domain="exemplo.com", ai_desktop_vm_ip_var="192.168.15.68",
                                  posto_chave_proxy="CHAVE-POSTO"))["http"]
    assert rotas["routers"]["kanban-dynamic"]["middlewares"] == ["authelia-forwardauth@docker", "posto-chave"]
    assert rotas["middlewares"]["posto-chave"]["headers"]["customRequestHeaders"] == {"X-Posto-Chave": "CHAVE-POSTO"}
    assert rotas["services"]["kanban-svc-dynamic"]["loadBalancer"]["servers"] == [{"url": "http://192.168.15.68:3005"}]


def test_porteiro_do_posto():
    """O Caddy divide a rede do posto e só repassa com o segredo do Traefik (e o retira); /api/health passa."""
    p = _svc(POSTO)["posto_porteiro"]
    assert p["image"].startswith("caddy:2.") and p["image"].endswith("-alpine")
    assert p["network_mode"] == "service:posto" and "ports" not in p and "networks" not in p
    assert p["read_only"] is True and p["cap_drop"] == ["ALL"] and "no-new-privileges:true" in p["security_opt"]
    assert p["volumes"] == ["${POSTO_DATA_PATH}/Caddyfile:/etc/caddy/Caddyfile:ro"]
    txt = render("templates/posto/Caddyfile.j2", posto_chave_proxy="CHAVE-POSTO", base_domain="exemplo.com")
    linhas = [l.strip() for l in txt.splitlines()]
    assert "admin off" in linhas and ":3005 {" in linhas
    assert '@traefik header X-Posto-Chave "CHAVE-POSTO"' in linhas and "request_header -X-Posto-Chave" in linhas
    assert linhas.count("reverse_proxy 127.0.0.1:3000") == 2 and "handle /api/health {" in linhas
    assert any(l.startswith("respond ") and l.endswith(" 403") for l in linhas)  # o resto: recusado
    t = _pb_tasks(PB_POSTO)
    assert t[0]["ansible.builtin.assert"]["that"] == "posto_chave_proxy | default('') | length >= 32"
    caddy = next(x for x in t if "Caddyfile" in str(x.get("ansible.builtin.template", {})))
    assert caddy["ansible.builtin.template"]["mode"] == "0600" and caddy.get("no_log") is True
    assert _vault()["posto_chave_proxy"] not in (_vault()["aprovador_chave_proxy"], _vault()["aprovador_token"])
    df = (ROOT / "server/docker/images/posto/Dockerfile").read_text(encoding="utf-8")
    assert "ENV HOST=127.0.0.1" in df and "3000/api/health" in df
    prom = (ANS / "templates/prometheus.yml.j2").read_text(encoding="utf-8")
    assert "3005/api/health" in prom


def test_posto_usa_o_litellm_com_chave_propria():
    e = _env(_svc(POSTO)["posto"])
    assert e["ANTHROPIC_BASE_URL"] == "http://litellm:4000" and e["ANTHROPIC_AUTH_TOKEN"] == "${LITELLM_KEY_AGENTES}"
    assert e["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "claude-sonnet-5-5"  # nomes reais (página 08)
    assert not any("MASTER" in v or "ANTHROPIC_API_KEY" in v for v in e.values())
    assert set(_svc(POSTO)["posto"]["networks"]) == {"ai_network", "notes_mcp"}
    assert _main()["litellm_key_budgets"]["agentes"] > 0 and "agentes" in _vault()["litellm_client_keys"]


def test_mcps_gerenciados_dos_agentes():
    txt = render("templates/posto/managed-mcp.json.j2", core_services_vm_ip_var="192.168.15.67", **SEGREDOS)
    mcp = json.loads(txt)["mcpServers"]
    assert mcp["servidor"] == {"type": "http", "url": "http://192.168.15.67:4200/mcp",
                               "headers": {"Authorization": "Bearer ag-AGENTES-SEGREDO"}}
    assert mcp["notas"]["url"] == "http://qmd:8181/mcp" and mcp["escrita"]["url"] == "http://notes_escrita:8000/mcp"
    vols = _svc(POSTO)["posto"]["volumes"]
    assert "${POSTO_DATA_PATH}/managed-mcp.json:/etc/claude-code/managed-mcp.json:ro" in vols
    tarefa = next(t for t in _pb_tasks(PB_POSTO) if "managed-mcp" in str(t.get("ansible.builtin.template", {})))
    assert tarefa["ansible.builtin.template"]["mode"] == "0600" and tarefa.get("no_log") is True


def test_perfis_pedem_aprovacao_na_tela():
    perfis = json.loads(render("templates/posto/profiles.json.j2"))["executors"]["CLAUDE_CODE"]
    assert perfis["DEFAULT"]["CLAUDE_CODE"] == {"approvals": True, "dangerously_skip_permissions": False}
    assert perfis["AUTONOMO"]["CLAUDE_CODE"]["dangerously_skip_permissions"] is True
    tarefa = next(t for t in _pb_tasks(PB_POSTO) if "profiles" in str(t.get("ansible.builtin.template", {})))
    assert tarefa["ansible.builtin.template"]["force"] is False  # a tela pode mudar depois


def test_vibe_kanban_do_codigo_fonte():
    t = _pb_tasks(PB_POSTO)
    git = next(x for x in t if "ansible.builtin.git" in x)["ansible.builtin.git"]
    assert git["repo"] == "https://github.com/BloopAI/vibe-kanban.git" and git["version"] == "{{ posto_vibe_kanban_tag }}"
    build = next(x for x in t if "community.docker.docker_image_build" in x)["community.docker.docker_image_build"]
    assert build["tag"] == "{{ posto_vibe_kanban_tag }}" and "args" not in build  # POSTHOG/SENTRY vazios
    posto = next(x for x in t if x.get("community.docker.docker_image", {}).get("name") == "localhost/homeserver/posto")
    # A tag da imagem muda com qualquer das três versões (senão a stack seguiria com o Claude Code antigo).
    tag = yaml.safe_load(PB_POSTO.read_text(encoding="utf-8"))[0]["vars"]["posto_tag"]
    assert all(v in tag for v in ("posto_version", "posto_vibe_kanban_tag", "posto_claude_code_version"))
    assert posto["community.docker.docker_image"]["tag"] == "{{ posto_tag }}"
    args = posto["community.docker.docker_image"]["build"]["args"]
    assert args["VIBE_KANBAN_IMAGE"] == "localhost/homeserver/vibe-kanban:{{ posto_vibe_kanban_tag }}"
    assert args["CLAUDE_CODE_VERSION"] == "{{ posto_claude_code_version }}"
    df = (ROOT / "server/docker/images/posto/Dockerfile").read_text(encoding="utf-8")
    assert "COPY --from=vibe /usr/local/bin/server /usr/local/bin/vibe-kanban" in df
    assert "npx -y @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" in df
    assert _main()["posto_vibe_kanban_tag"].startswith("v0.")
    c = _configs(PB_POSTO, "posto.env")
    assert _vars_compose(POSTO) - COMUNS <= set(c)


# --- Aprovador (4c3) ---

def test_aprovador_na_stack_agents():
    s = _svc(AGENTS)["aprovador"]
    lab = s["labels"]
    assert lab["traefik.http.routers.aprovacoes.middlewares"] == "authelia-forwardauth@docker,aprovador-chave@file"
    # O segredo fica no arquivo do Traefik, não em label (que qualquer leitor do docker inspect vê).
    assert not any("CHAVE" in str(v) for v in lab.values())
    mw = yaml.safe_load(render("roles/infra/traefik-config/templates/dynamic_agents.yml.j2",
                               aprovador_chave_proxy="CHAVE-APROV"))["http"]["middlewares"]
    assert mw["aprovador-chave"]["headers"]["customRequestHeaders"] == {"X-Aprovador-Chave": "CHAVE-APROV"}
    tarefas = yaml.safe_load((ANS / "roles/infra/traefik-config/tasks/main.yml").read_text(encoding="utf-8"))
    copia = next(x for x in tarefas if x.get("ansible.builtin.template", {}).get("src") == "dynamic_agents.yml.j2")
    assert copia.get("no_log") is True
    assert "ports" not in s and set(s["networks"]) == {"agents_internal", "proxy"}
    e = _env(s)
    assert e["APROVADOR_URL_PUBLICA"] == "https://aprovacoes.${BASE_DOMAIN_FROM_VAULT}"
    assert "aprovador" in _main()["ops_containers_protegidos"]
    c = _configs(ANS / "playbooks/setup-agents-volumes.yml", "agents.env")
    assert c["APROVADOR_TOKEN"] == "{{ aprovador_token }}" and c["TELEGRAM_BOT_TOKEN"] == "{{ telegram_bot_token }}"
    v = _vault()
    assert v["aprovador_token"] and v["aprovador_chave_proxy"] and v["aprovador_token"] != v["aprovador_chave_proxy"]


# --- Assistente (4c4) ---

def test_assistente_sem_porta_nem_socket():
    s = _svc(ASSISTENTE)["assistente"]
    assert s["image"] == f"nousresearch/hermes-agent:{_main()['hermes_version']}"
    assert s["command"] == ["gateway", "run"] and "ports" not in s
    assert "no-new-privileges:true" in s["security_opt"]
    assert not any("docker.sock" in v for v in s.get("volumes", []))
    e = _env(s)
    assert e["HERMES_UID"] == "${DOCKER_PUID}" and "HERMES_DASHBOARD" not in e and "API_SERVER_ENABLED" not in e
    assert set(s["networks"]) == {"ai_network", "notes_mcp"}


def _config_hermes() -> dict:
    return yaml.safe_load(render("templates/assistente/config.yaml.j2", assistente_modelo="principal",
                                 core_services_vm_ip_var="192.168.15.67"))


def test_config_do_hermes():
    cfg = _config_hermes()
    assert cfg["model"] == {"provider": "custom", "default": "principal", "base_url": "http://litellm:4000/v1",
                            "api_key": "${LITELLM_KEY_ASSISTENTE}", "context_length": 200000}
    mcp = cfg["mcp_servers"]
    assert mcp["servidor"]["url"] == "http://192.168.15.67:4200/mcp"  # rota dos autônomos (aprovação no ops)
    assert mcp["servidor"]["headers"]["Authorization"] == "Bearer ${HUB_CHAVE_ASSISTENTE}"
    assert mcp["notas"]["url"] == "http://qmd:8181/mcp" and mcp["escrita"]["url"] == "http://notes_escrita:8000/mcp"
    # Nada que execute código, mexa em arquivos do container, saia para a internet ou acrescente MCPs.
    desligados = set(cfg["agent"]["disabled_toolsets"])
    assert {"terminal", "code_execution", "file", "browser", "web", "connections", "skills", "delegation"} <= desligados
    # Tarefas agendadas buscam qualquer URL e entregam em qualquer chat: fora.
    assert "cronjob" in desligados and "memory" not in desligados
    # A API compatível com OpenAI liga sozinha com API_SERVER_KEY (o init da imagem gera): desligada no config.
    assert cfg["platforms"]["api_server"]["enabled"] is False


def test_segredos_do_hermes():
    txt = render("templates/assistente/env.j2", **SEGREDOS)
    env = dict(l.split("=", 1) for l in txt.splitlines() if l and not l.startswith("#"))
    assert env == {"TELEGRAM_BOT_TOKEN": "123:BOT", "TELEGRAM_ALLOWED_USERS": "4242", "TELEGRAM_HOME_CHANNEL": "4242",
                   "LITELLM_KEY_ASSISTENTE": "sk-ASSIST-SEGREDO", "HUB_CHAVE_ASSISTENTE": "ag-ASSIST-SEGREDO"}
    tarefa = next(t for t in _pb_tasks(PB_ASSIST) if str(t.get("ansible.builtin.template", {}).get("dest", "")).endswith("/.env"))
    assert tarefa["ansible.builtin.template"]["mode"] == "0600" and tarefa.get("no_log") is True
    for segredo in SEGREDOS["agents_autonomos_keys"].values():
        assert segredo not in yaml.safe_dump(_config_hermes())
    assert "hermes_telegram_bot_token" in _vault() and _vault()["hermes_telegram_bot_token"] != _vault()["telegram_bot_token"]


def test_deploy_completo_e_painel():
    importados = [p["import_playbook"] for p in yaml.safe_load((ANS / "playbooks/full-deploy.yml").read_text(encoding="utf-8"))]
    assert importados[-2:] == ["setup-posto-volumes.yml", "setup-assistente-volumes.yml"]
    prom = (ANS / "templates/prometheus.yml.j2").read_text(encoding="utf-8")
    assert "app: 'vibe-kanban'" in prom and "app: 'aprovador'" in prom
    painel = (ANS / "templates/homepage/services.yaml.j2").read_text(encoding="utf-8")
    assert "https://kanban.{{ base_domain }}" in painel and "https://aprovacoes.{{ base_domain }}" in painel
