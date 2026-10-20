"""Testes da fundação de IA: gateway LiteLLM, stack ai, chaves por cliente, Open WebUI e integrações."""
from __future__ import annotations

import yaml

from test_observabilidade import ROOT, render

MAIN = ROOT / "server/ansible/inventories/home/group_vars/all/main.yml"
LITELLM_TPL = "templates/litellm_config.yaml.j2"
SEGREDOS = {"litellm_master_key": "MESTRA-SECRETA-123",
            "llm_api_keys": {"openai": "OPENAI-SECRETA", "anthropic": "ANTHROPIC-SECRETA",
                             "google_gemini": "GEMINI-SECRETA", "typesafe": "TYPESAFE-SECRETA"}}


def _main() -> dict:
    return yaml.safe_load(MAIN.read_text(encoding="utf-8"))


def _litellm_txt() -> str:
    m = _main()
    return render(LITELLM_TPL, llm_models=m["llm_models"], llm_fallbacks=m["llm_fallbacks"], **SEGREDOS)


# --- Gateway ---

def test_litellm_config_de_llm_models():
    cfg = yaml.safe_load(_litellm_txt())
    modelos = {m["model_name"]: m["litellm_params"] for m in cfg["model_list"]}
    for nome in ("principal", "rapido", "local", "decisao", "claude-opus-5-5", "claude-sonnet-5-5",
                 "claude-haiku-5-5", "gpt-6.1-sol", "gpt-6-luna", "gemini-3.8-flash"):
        assert nome in modelos, nome
    assert modelos["principal"]["model"] == "anthropic/claude-sonnet-5-5"
    assert modelos["rapido"]["model"] == "anthropic/claude-haiku-5-5"
    assert modelos["decisao"]["model"] == "typesafe/jev-latest"
    assert modelos["local"]["model"] == "ollama_chat/llama3.2:3b"
    assert modelos["local"]["api_base"] == "http://ollama:11434"
    for m in _main()["llm_models"]:
        if "chave" in m:
            assert modelos[m["name"]]["api_key"] == f"os.environ/{m['chave']}", m["name"]
    assert cfg["router_settings"]["fallbacks"] == [{"principal": ["gpt-6.1-sol"]}, {"rapido": ["gpt-6-luna"]}]
    g = cfg["general_settings"]
    assert g["store_model_in_db"] is False
    assert g["master_key"] == "os.environ/LITELLM_MASTER_KEY"
    assert g["database_url"] == "os.environ/DATABASE_URL"
    assert cfg["litellm_settings"]["callbacks"] == ["prometheus"]


def test_litellm_config_sem_segredos():
    txt = _litellm_txt()
    for valor in ["MESTRA-SECRETA-123", *SEGREDOS["llm_api_keys"].values()]:
        assert valor not in txt, valor


# --- Stack ai e preparação da VM ---

from test_midia import _env, _svc  # noqa: E402
from test_fotos_arquivos import COMUNS, _configs, _env_task, _pb_tasks, _vars_compose, _volume  # noqa: E402

AI = ROOT / "server/docker/stacks/ai/docker-compose.yml"
PB_AI = ROOT / "server/ansible/playbooks/setup-ai-volumes.yml"
ML_TOOLS = ROOT / "server/ansible/roles/apps/ml-tools"
SEGREDOS_PROVEDOR = ("${LITELLM_MASTER_KEY}", "${ANTHROPIC_API_KEY}", "${OPENAI_API_KEY}",
                     "${GEMINI_API_KEY}", "${TYPESAFE_API_KEY}")


def test_ai_servicos():
    s = _svc(AI)
    assert set(s) == {"litellm", "litellm_db", "ollama", "open-webui", "diun_ai"}
    for nome, svc in s.items():
        if nome == "diun_ai":
            continue  # o Diun observa as outras; segue a política dele
        img = svc["image"]
        assert not img.endswith((":latest", ":main", ":main-latest", ":rocm")), (nome, img)
    assert s["ollama"]["image"] == "${OLLAMA_IMAGE}"
    assert s["litellm"]["image"] == "docker.io/litellm/litellm-database:v1.106.0"
    assert s["open-webui"]["image"] == "ghcr.io/open-webui/open-webui:v0.12.3"


def test_so_o_litellm_tem_segredos_de_provedor():
    s = _svc(AI)
    for nome, svc in s.items():
        if nome == "litellm":
            continue
        valores = set(_env(svc).values())
        assert not (valores & set(SEGREDOS_PROVEDOR)), nome
    ow = _env(s["open-webui"])
    assert ow["OPENAI_API_KEY"] == "${LITELLM_KEY_OPENWEBUI}"
    assert ow["OPENAI_API_BASE_URL"] == "http://litellm:4000/v1"
    assert ow["ENABLE_OLLAMA_API"] == "false"


def test_litellm_banco_local_e_metricas():
    s = _svc(AI)
    lt = s["litellm"]
    assert _env(lt)["DATABASE_URL"] == "postgresql://litellm:${LITELLM_DB_PASSWORD}@litellm_db:5432/litellm"
    assert lt["ports"] == ["${AI_DESKTOP_VM_IP}:4000:4000", "${AI_DESKTOP_VM_IP}:4001:4001"]
    cmd = lt["command"]
    assert "--prometheus_metrics_port" in cmd and cmd[cmd.index("--prometheus_metrics_port") + 1] == "4001"
    assert lt["depends_on"]["litellm_db"]["condition"] == "service_healthy"
    assert _volume(s["litellm_db"], "/var/lib/postgresql/data").startswith("${AI_STACK_LITELLM_DB_PATH}")
    assert _configs(PB_AI, "ai.env")["AI_STACK_LITELLM_DB_PATH"].startswith("{{ vm_local_data_path }}/")


def test_ollama_vulkan_sem_porta():
    o = _svc(AI)["ollama"]
    assert "ports" not in o
    assert o["devices"] == ["/dev/dri"]
    assert o["group_add"] == ["${AI_RENDER_GID}"]
    tarefas = (ML_TOOLS / "tasks/main.yml").read_text(encoding="utf-8")
    assert "rocm" not in tarefas.lower()
    t = yaml.safe_load(tarefas)
    img = next(x["community.docker.docker_image"] for x in t if "community.docker.docker_image" in x)
    assert img["name"] == "localhost/homeserver/ollama-vulkan" and img["tag"] == "{{ ollama_version }}"
    assert img["source"] == "build"
    df = render("roles/apps/ml-tools/templates/Dockerfile.ollama-vulkan.j2", ollama_version="0.40.6")
    assert "FROM ollama/ollama:0.40.6" in df and "mesa-vulkan-drivers" in df
    assert _configs(PB_AI, "ai.env")["OLLAMA_IMAGE"] == "localhost/homeserver/ollama-vulkan:{{ ollama_version }}"


def test_variaveis_ai_no_env():
    assert _vars_compose(AI) <= set(_configs(PB_AI, "ai.env")) | COMUNS
    assert _env_task(PB_AI, "ai.env")["ansible.builtin.template"]["mode"] == "0600"
    env_tpl = (ROOT / "server/docker/stacks/.env.template").read_text(encoding="utf-8")
    for txt in (PB_AI.read_text(encoding="utf-8"), env_tpl):
        assert "OPENCLAW" not in txt.upper() and "OPENCLAUDE" not in txt.upper()


# --- Chaves virtuais por cliente ---

VAULT_EX = ROOT / "server/ansible/inventories/home/group_vars/all/vault.yml.example"
PB_KEYS = ROOT / "server/ansible/playbooks/setup-ai-keys.yml"
CLIENTES = {"openwebui", "claude_code", "n8n"}


def test_chaves_por_cliente():
    v = yaml.safe_load(VAULT_EX.read_text(encoding="utf-8"))
    chaves = v["litellm_client_keys"]
    assert set(chaves) == CLIENTES
    assert all(str(x).startswith("sk-") for x in chaves.values())
    assert "litellm_db_password" in v
    orc = _main()["litellm_key_budgets"]
    assert set(orc) == CLIENTES and all(isinstance(x, (int, float)) and x > 0 for x in orc.values())


def test_playbook_de_chaves_idempotente():
    play = yaml.safe_load(PB_KEYS.read_text(encoding="utf-8"))[0]
    assert play["hosts"] == "ai_desktop"
    uris = [t for t in play["tasks"] if "ansible.builtin.uri" in t]
    assert uris
    for t in uris:
        assert t.get("no_log") is True, t["name"]
        assert t["ansible.builtin.uri"]["headers"]["Authorization"] == "Bearer {{ litellm_master_key }}"
        assert t["loop"] in ("{{ litellm_client_keys | dict2items }}", "{{ chaves_info.results }}"), t["name"]
    por_rota = {next(r for r in ("/key/info", "/key/generate", "/key/update", "/key/delete")
                     if r in t["ansible.builtin.uri"]["url"]): t
                for t in uris}
    info, gen, upd = por_rota["/key/info"], por_rota["/key/generate"], por_rota["/key/update"]
    assert 404 in info["ansible.builtin.uri"]["status_code"] and info["changed_when"] is False
    assert "status" in str(gen["when"]) and "200" in str(gen["when"])
    corpo = gen["ansible.builtin.uri"]["body"]
    assert {"key", "key_alias", "max_budget", "budget_duration"} <= set(corpo)
    assert corpo["budget_duration"] == "30d"
    assert "max_budget" in str(upd["when"]) and "budget_duration" in str(upd["when"])


# --- Open WebUI com OIDC ---

def test_cliente_oidc_openwebui():
    from test_fotos_arquivos import DOM, OIDC, _authelia
    cli = {c["client_id"]: c for c in yaml.safe_load(_authelia())["identity_providers"]["oidc"]["clients"]}
    c = cli["openwebui"]
    assert c["client_name"] == "Open WebUI"
    assert c["client_secret"] == OIDC["openwebui"]["secret_digest"]
    assert c["authorization_policy"] == "two_factor" and c["public"] is False
    assert c["require_pkce"] is True and c["pkce_challenge_method"] == "S256"
    assert c["token_endpoint_auth_method"] == "client_secret_basic"
    assert c["redirect_uris"] == [f"https://openwebui.{DOM}/oauth/oidc/callback"]
    assert c["scopes"] == ["openid", "profile", "groups", "email"]
    assert "openwebui" in yaml.safe_load(VAULT_EX.read_text(encoding="utf-8"))["oidc_clients"]


def test_openwebui_oidc():
    env = _env(_svc(AI)["open-webui"])
    esperado = {
        "WEBUI_URL": "https://openwebui.${BASE_DOMAIN_FROM_VAULT}",
        "OAUTH_CLIENT_ID": "openwebui",
        "OAUTH_CLIENT_SECRET": "${OPENWEBUI_OAUTH_CLIENT_SECRET}",
        "OPENID_PROVIDER_URL": "https://auth.${BASE_DOMAIN_FROM_VAULT}/.well-known/openid-configuration",
        "OAUTH_PROVIDER_NAME": "Authelia",
        "OAUTH_CODE_CHALLENGE_METHOD": "S256",
        "OAUTH_SCOPES": "openid email profile groups",
        "ENABLE_OAUTH_SIGNUP": "true",
        "OAUTH_MERGE_ACCOUNTS_BY_EMAIL": "true",
        "ENABLE_OAUTH_ROLE_MANAGEMENT": "true",
        "OAUTH_ROLES_CLAIM": "groups",
        "OAUTH_ALLOWED_ROLES": "admins",
        "OAUTH_ADMIN_ROLES": "admins",
        "ENABLE_LOGIN_FORM": "${OPENWEBUI_LOGIN_FORM}",
    }
    for k, v in esperado.items():
        assert env.get(k) == v, k
    assert _configs(PB_AI, "ai.env")["OPENWEBUI_LOGIN_FORM"] == "{{ openwebui_login_form | bool | lower }}"


# --- Dump genérico de Postgres ---

def test_dump_generico_nos_dois_bancos():
    from test_fotos_arquivos import PB_CLOUD, _script_dump
    nc = _script_dump(PB_CLOUD, "/usr/local/sbin/backup-nextcloud-db.sh")
    lt = _script_dump(PB_AI, "/usr/local/sbin/backup-litellm-db.sh")
    assert "docker exec nextcloud_db pg_dump -U nextcloud -d nextcloud -Fc" in nc
    assert "docker exec litellm_db pg_dump -U litellm -d litellm -Fc" in lt
    assert 'destino="/mnt/pve_data_zfs/docker-volumes/litellm/db-dumps"' in lt
    for out in (nc, lt):
        assert "-mtime +14" in out and "*.tmp" in out
    assert "tar " in nc and "tar " not in lt
    tarefas = _pb_tasks(PB_AI)
    copias = {x["ansible.builtin.copy"]["dest"]: x["ansible.builtin.copy"]["content"]
              for x in tarefas if "ansible.builtin.copy" in x}
    timer = copias["/etc/systemd/system/backup-litellm-db.timer"]
    assert "OnCalendar=*-*-* 03:45:00" in timer and "Persistent=true" in timer
    assert "ExecStart=/usr/local/sbin/backup-litellm-db.sh" in copias["/etc/systemd/system/backup-litellm-db.service"]
    sd = next(x["ansible.builtin.systemd"] for x in tarefas if "ansible.builtin.systemd" in x)
    assert sd["name"] == "backup-litellm-db.timer" and sd["enabled"] is True
    assert not (ROOT / "server/ansible/templates/nextcloud/backup-nextcloud-db.sh.j2").exists()


# --- Integrações: llm., métricas, alerta e painel ---

def test_router_llm_com_authelia():
    out = yaml.safe_load(render("roles/infra/traefik-config/templates/dynamic_rag_services.yml.j2",
                                base_domain="exemplo.com", ai_desktop_vm_ip_var="192.168.15.68"))
    r = out["http"]["routers"]["litellm-dynamic"]
    assert r["rule"] == "Host(`llm.exemplo.com`)"
    assert r["middlewares"] == ["authelia-forwardauth@docker"]
    svc = out["http"]["services"][r["service"]]
    assert svc["loadBalancer"]["servers"] == [{"url": "http://192.168.15.68:4000"}]


def test_job_litellm_e_alerta_de_gasto():
    from test_midia import PROM_VARS
    jobs = {j["job_name"]: j for j in yaml.safe_load(render(
        "templates/prometheus.yml.j2", groups={"ai_desktop": ["ai-desktop-vm"]}, **PROM_VARS))["scrape_configs"]}
    assert jobs["litellm"]["static_configs"][0]["targets"] == ["192.168.15.68:4001"]
    sem_ia = {j["job_name"] for j in yaml.safe_load(render(
        "templates/prometheus.yml.j2", groups={}, **PROM_VARS))["scrape_configs"]}
    assert "litellm" not in sem_ia
    regras = {r["uid"]: r for r in yaml.safe_load(render(
        "templates/grafana/alerting/rules.yml.j2", llm_gasto_diario_alerta=7))["groups"][0]["rules"]}
    r = regras["llm-gasto-alto"]
    assert r["data"][0]["model"]["expr"] == "sum(increase(litellm_spend_metric_total[1d]))"
    assert r["data"][1]["model"]["conditions"][0]["evaluator"] == {"type": "gt", "params": [7]}
    assert r["labels"]["severity"] == "warning"


def test_homepage_litellm():
    from test_midia import PROM_VARS
    import re as _re
    src = (ROOT / "server/ansible/templates/homepage/services.yaml.j2").read_text(encoding="utf-8")
    ctx = {"base_domain": "exemplo.com", "groups": {"ai_desktop": ["ai-desktop-vm"]}, **PROM_VARS}
    ctx.update({v: "x" for v in set(_re.findall(r"\{\{\s*([a-z_]+)", src)) - {"item"} if v not in ctx})
    ia = next(g for g in yaml.safe_load(render("templates/homepage/services.yaml.j2", **ctx)) if "ia" in g)["ia"]
    e = {list(x)[0]: list(x.values())[0] for x in ia}["litellm"]
    assert e["href"] == "https://llm.exemplo.com"
    assert e["siteMonitor"] == "http://192.168.15.68:4000/health/liveliness"


# --- Documentação, catálogo e índice ---

def test_catalogo_ia():
    from test_fotos_arquivos import _catalogo
    cat = _catalogo()
    assert "openclaw" not in cat and "openclaude" not in cat
    lt = cat["litellm"]
    assert lt[3] == "`litellm`, `litellm_db`"
    assert lt[4] == "protegida" and lt[5] == "`llm`" and lt[7] == "sim"
    indice = (ROOT / "wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md").read_text(encoding="utf-8")
    assert "**LLM-4**" in indice and "${TYPESAFE_API_KEY}" in indice
    pagina = (ROOT / "wiki/docs/01-manual-implementacao/08-stack-ia.md").read_text(encoding="utf-8")
    for trecho in ("setup-ai-keys.yml", "claude-gw", "ANTHROPIC_BASE_URL", "/v1/messages", "openwebui_login_form",
                   "Vulkan", "decisao", "llm."):
        assert trecho in pagina, trecho


# --- Correções da revisão final ---

def test_openwebui_config_vem_do_compose():
    # Sem isto, o Open WebUI grava a configuração no banco na primeira partida e passa a ignorar o compose
    # (chave do LiteLLM, Ollama desligado, formulário de login).
    assert _env(_svc(AI)["open-webui"])["ENABLE_PERSISTENT_CONFIG"] == "false"


def test_imagem_local_do_ollama_nunca_vem_do_registro():
    # "homeserver/..." resolveria para docker.io; um namespace tomado por terceiros entregaria outra imagem.
    o = _svc(AI)["ollama"]
    assert o["pull_policy"] == "never"
    assert o["labels"]["diun.enable"] == "false"


def test_playbook_chaves_hash_rotacao_e_apagadas():
    play = yaml.safe_load(PB_KEYS.read_text(encoding="utf-8"))[0]
    uris = {t["name"]: t for t in play["tasks"] if "ansible.builtin.uri" in t}
    info = next(t for t in uris.values() if "/key/info" in t["ansible.builtin.uri"]["url"])
    assert "item.value | hash('sha256')" in info["ansible.builtin.uri"]["url"]  # chave crua fora da URL/logs
    gen = next(t for t in uris.values() if "/key/generate" in t["ansible.builtin.uri"]["url"])
    upd = next(t for t in uris.values() if "/key/update" in t["ansible.builtin.uri"]["url"])
    apaga = next(t for t in uris.values() if "/key/delete" in t["ansible.builtin.uri"]["url"])
    assert "deleted" in str(gen["when"]) and "deleted" in str(upd["when"])  # chave apagada na tela = inexistente
    assert apaga["ansible.builtin.uri"]["body"] == {"key_aliases": ["{{ item.item.key }}"]}  # troca de valor no vault
    assert apaga["when"] == gen["when"]
    nomes = [t["name"] for t in play["tasks"]]
    assert nomes.index(apaga["name"]) < nomes.index(gen["name"])


def test_doc_jev_pela_rota_unificada():
    pagina = (ROOT / "wiki/docs/01-manual-implementacao/08-stack-ia.md").read_text(encoding="utf-8")
    assert "/v1/systemone" in pagina and '"model": "decisao"' in pagina
