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
    assert img["name"] == "homeserver/ollama-vulkan" and img["tag"] == "{{ ollama_version }}"
    assert img["source"] == "build"
    df = render("roles/apps/ml-tools/templates/Dockerfile.ollama-vulkan.j2", ollama_version="0.40.6")
    assert "FROM ollama/ollama:0.40.6" in df and "mesa-vulkan-drivers" in df
    assert _configs(PB_AI, "ai.env")["OLLAMA_IMAGE"] == "homeserver/ollama-vulkan:{{ ollama_version }}"


def test_variaveis_ai_no_env():
    assert _vars_compose(AI) <= set(_configs(PB_AI, "ai.env")) | COMUNS
    assert _env_task(PB_AI, "ai.env")["ansible.builtin.template"]["mode"] == "0600"
    env_tpl = (ROOT / "server/docker/stacks/.env.template").read_text(encoding="utf-8")
    for txt in (PB_AI.read_text(encoding="utf-8"), env_tpl):
        assert "OPENCLAW" not in txt.upper() and "OPENCLAUDE" not in txt.upper()
