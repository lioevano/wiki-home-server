"""Testes da base dos agentes (4c1): versões fixadas, stack agents (hub, mcp-grafana, ops), conector Servidor,
Langfuse e integrações. Os testes unitários do código do ops ficam em test_ops.py."""
from __future__ import annotations

import yaml

from test_observabilidade import ROOT, render  # noqa: F401
from test_midia import _svc, _env  # noqa: F401

MAIN = ROOT / "server/ansible/inventories/home/group_vars/all/main.yml"
VAULT_EX = ROOT / "server/ansible/inventories/home/group_vars/all/vault.yml.example"
APPS = ROOT / "server/docker/stacks/apps/docker-compose.yml"
PLAYBOOKS = ROOT / "server/ansible/playbooks"


def _main() -> dict:
    return yaml.safe_load(MAIN.read_text(encoding="utf-8"))


def _vault() -> dict:
    return yaml.safe_load(VAULT_EX.read_text(encoding="utf-8"))


# --- Task 1: versões fixadas e variáveis ---

def test_versoes_fixadas_de_quem_o_hub_depende():
    s = _svc(APPS)
    assert s["grafana"]["image"] == "grafana/grafana-oss:13.2.4"
    assert s["n8n"]["image"] == "docker.n8n.io/n8nio/n8n:2.44.4"
    assert s["homeassistant"]["image"] == "ghcr.io/home-assistant/home-assistant:2026.10.2"


def test_variaveis_agentes():
    m = _main()
    assert m["agentgateway_version"] == "v1.6.0"
    assert m["mcp_grafana_version"] == "2.1.1"
    assert m["ops_fastmcp_version"] == "4.1.2"
    assert m["ops_ansible_core_version"] == "2.21.5"
    assert m["langfuse_version"] == "4.66.0"
    assert m["agents_leitura"] == {"grafana": "*", "ops": "*", "homeassistant": ["GetLiveContext"],
                                   "n8n": ["search_workflows"]}
    assert m["ops_stacks_protegidas"] == ["core", "agents"]
    assert {"traefik", "authelia", "cloudflared", "portainer", "agentgateway", "mcp_auth_servidor",
            "ops_leitura", "ops_controle"} <= set(m["ops_containers_protegidos"])
    nomes = [p["nome"] for p in m["ops_playbooks_permitidos"]]
    assert nomes and "vm-deploy.yml" not in nomes and "setup-proxmox-host.yml" not in nomes
    for p in m["ops_playbooks_permitidos"]:
        assert (PLAYBOOKS / p["nome"]).is_file(), p["nome"]
        assert p["descricao"]
    assert m["ops_endpoints"] == {"core": "local", "ai": "ai-desktop-vm"}
    assert m["ops_repo_url"] == "https://github.com/lioevano/wiki-home-server.git"
    assert m["ops_plano_validade_min"] == 30
    assert m["langfuse_retencao_dias"] == 30


def test_vault_agentes():
    v = _vault()
    assert set(v["agents_api_keys"]) == {"claude_code", "agentes"}
    assert all(str(x).startswith("ag-") for x in v["agents_api_keys"].values())
    assert set(v["grafana_sa_tokens"]) == {"leitura", "controle"}
    for chave in ("homeassistant_mcp_token", "n8n_mcp_token", "portainer_api_key", "ops_ssh_private_key",
                  "ops_vault_password"):
        assert v.get(chave), chave
    lf = v["langfuse_secrets"]
    assert set(lf) == {"salt", "encryption_key", "nextauth_secret", "db_password", "clickhouse_password",
                       "redis_password", "minio_password", "public_key", "secret_key"}
    assert lf["public_key"].startswith("pk-lf-") and lf["secret_key"].startswith("sk-lf-")
    assert set(v["oidc_clients"]["langfuse"]) == {"secret", "secret_digest"}
