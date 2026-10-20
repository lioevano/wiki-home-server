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


# --- Task 4: stack agents e preparação da core ---

from test_fotos_arquivos import COMUNS, _configs, _pb_tasks, _vars_compose  # noqa: E402

AGENTS = ROOT / "server/docker/stacks/agents/docker-compose.yml"
PB_AGENTS = ROOT / "server/ansible/playbooks/setup-agents-volumes.yml"


def _vols(servico) -> list[str]:
    return [v if isinstance(v, str) else f"{v['source']}:{v['target']}" for v in servico.get("volumes", [])]


def test_grafana_mcp_leitura_e_controle():
    s = _svc(AGENTS)
    for nome, token, escrita in (("mcp_grafana_leitura", "${GRAFANA_SA_TOKEN_LEITURA}", False),
                                 ("mcp_grafana_controle", "${GRAFANA_SA_TOKEN_CONTROLE}", True)):
        g = s[nome]
        assert g["image"] == "grafana/mcp-grafana:2.1.1"
        cmd = g["command"]
        assert cmd[cmd.index("-t") + 1] == "streamable-http"
        assert cmd[cmd.index("--address") + 1] == "0.0.0.0:8000"
        assert cmd[cmd.index("--allowed-hosts") + 1] == f"{nome}:8000"
        assert ("--disable-write" in cmd) is not escrita
        env = _env(g)
        assert env["GRAFANA_URL"] == "http://grafana:3000"
        assert env["GRAFANA_SERVICE_ACCOUNT_TOKEN"] == token
        assert set(g["networks"]) == {"agents_internal", "internal_services"}
        assert "ports" not in g


def test_ops_leitura_sem_segredos_de_escrita():
    s = _svc(AGENTS)
    leitura, controle = s["ops_leitura"], s["ops_controle"]
    assert _env(leitura)["OPS_MODO"] == "leitura" and not leitura.get("volumes")
    assert _env(controle)["OPS_MODO"] == "controle"
    assert set(_vols(controle)) == {"${OPS_DATA_PATH}/segredos:/segredos:ro", "${OPS_DATA_PATH}/repo:/repo"}
    for o in (leitura, controle):
        env = _env(o)
        assert env["PORTAINER_URL"] == "http://portainer:9000"
        assert env["PORTAINER_API_KEY"] == "${PORTAINER_API_KEY}"
        for var in ("OPS_PLAYBOOKS", "OPS_CONTAINERS_PROTEGIDOS", "OPS_STACKS_PROTEGIDAS", "OPS_ENDPOINTS"):
            assert env[var] == "${" + var + "}", var
        assert set(o["networks"]) == {"agents_internal", "proxy"}
        assert "ports" not in o
        assert o["image"] == "${OPS_IMAGE}" and o["pull_policy"] == "never"
        assert o["user"] == "${DOCKER_PUID}:${DOCKER_PGID}"
        assert env["HOME"] == "/tmp"
    # só o controle tem o runner: chave, vault e o callback de saída compatível com o ansible-core novo
    env = _env(controle)
    assert env["OPS_CHAVE_SSH"] == "/segredos/id_ed25519"
    assert env["ANSIBLE_VAULT_PASSWORD_FILE"] == "/segredos/vault_pass"
    assert env["ANSIBLE_STDOUT_CALLBACK"] == "default" and env["ANSIBLE_CALLBACK_RESULT_FORMAT"] == "yaml"
    assert "ANSIBLE_VAULT_PASSWORD_FILE" not in _env(leitura)


def test_segredos_do_runner():
    tarefas = _pb_tasks(PB_AGENTS)
    copias = [t for t in tarefas if "ansible.builtin.copy" in t
              and "/ops/segredos/" in str(t["ansible.builtin.copy"].get("dest", ""))]
    destinos = {t["ansible.builtin.copy"]["dest"].rsplit("/", 1)[1] for t in copias}
    assert destinos == {"id_ed25519", "vault_pass"}
    for t in copias:
        assert t["ansible.builtin.copy"]["mode"] == "0400" and t.get("no_log") is True
        assert t["ansible.builtin.copy"]["dest"].startswith("{{ vm_local_data_path }}/ops/segredos/")
    configs = _configs(PB_AGENTS, "agents.env")
    env_task = next(t for t in tarefas if str(t.get("ansible.builtin.template", {}).get("dest", "")).endswith("/agents.env"))
    assert env_task["ansible.builtin.template"]["mode"] == "0600"
    assert _vars_compose(AGENTS) <= set(configs) | COMUNS
    assert configs["OPS_DATA_PATH"] == "{{ vm_local_data_path }}/ops"
    assert "items2dict" in configs["OPS_PLAYBOOKS"] and "to_json" in configs["OPS_PLAYBOOKS"]
    assert configs["OPS_IMAGE"] == "localhost/homeserver/ops:{{ ops_fastmcp_version }}"


def test_imagem_ops_construida_e_repo_clonado():
    tarefas = _pb_tasks(PB_AGENTS)
    img = next(t for t in tarefas if "community.docker.docker_image" in t)["community.docker.docker_image"]
    assert img["name"] == "localhost/homeserver/ops" and img["tag"] == "{{ ops_fastmcp_version }}"
    assert img["source"] == "build"
    registros = [t["register"] for t in tarefas if "register" in t
                 and ("ansible.builtin.copy" in t or "ansible.builtin.template" in t)
                 and "{{ ops_imagem }}" in str(t.get("ansible.builtin.copy", t.get("ansible.builtin.template", {})).get("dest", ""))]
    assert yaml.safe_load(PB_AGENTS.read_text(encoding="utf-8"))[0]["vars"]["ops_imagem"] == "/opt/ops-image"
    assert len(registros) >= 3  # Dockerfile + código, requirements.txt, requirements.yml
    for r in registros:
        assert r + ".changed" in img["force_source"]
    git = next(t for t in tarefas if "ansible.builtin.git" in t)["ansible.builtin.git"]
    assert git["repo"] == "{{ ops_repo_url }}" and git["dest"] == "{{ vm_local_data_path }}/ops/repo"
    assert git.get("update") is False  # o runner faz o pull antes de cada execução
