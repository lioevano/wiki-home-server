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
