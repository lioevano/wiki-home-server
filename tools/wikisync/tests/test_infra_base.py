"""Testes da base das VMs e do host: Docker/Portainer em todas as VMs Ubuntu e repositórios do Proxmox."""
from __future__ import annotations

import yaml

from test_observabilidade import ROOT, _expr, _roles

ANS = ROOT / "server/ansible"
DOCKER_TASKS = ANS / "roles/infra/docker/tasks/main.yml"
DOCKER_DEFAULTS = ANS / "roles/infra/docker/defaults/main.yml"
PVE_TASKS = ANS / "roles/infra/proxmox-host-config/tasks/main.yml"


def _yaml(p):
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def _tarefa(tarefas, nome_contem):
    return next(t for t in tarefas if nome_contem in t.get("name", ""))


# --- Docker e Portainer ---

def test_docker_em_todas_as_vms_ubuntu():
    plays = _yaml(ANS / "playbooks/setup-base-ubuntu.yml")
    play = next(p for p in plays if "infra/docker" in _roles(p))
    assert play["hosts"] == "ubuntu_vms"


def test_modo_do_portainer_por_host():
    d = _yaml(DOCKER_DEFAULTS)
    grupos = {"core_services": ["core-services-vm"], "ai_desktop": ["ai-desktop-vm"]}
    assert _expr(d, "docker_portainer_mode", inventory_hostname="core-services-vm", groups=grupos) == "server"
    assert _expr(d, "docker_portainer_mode", inventory_hostname="ai-desktop-vm", groups=grupos) == "agent"


def test_portainer_server_e_agente_por_modo():
    t = _yaml(DOCKER_TASKS)
    server = _tarefa(t, "Deploy Portainer CE")
    assert server["when"] == "docker_portainer_mode == 'server'"
    assert server["community.docker.docker_container"]["env"]["AGENT_SECRET"] == "{{ portainer_agent_secret }}"
    for nome in ("dados persistentes do Portainer", "rede Docker 'proxy'"):
        assert _tarefa(t, nome)["when"] == "docker_portainer_mode == 'server'", nome
    agente = _tarefa(t, "Portainer Agent")
    assert agente["when"] == "docker_portainer_mode == 'agent'"
    c = agente["community.docker.docker_container"]
    assert c["image"] == "{{ portainer_agent_image }}"
    assert c["ports"] == ["{{ hostvars[inventory_hostname]['ansible_host'] }}:9001:9001"]
    assert c["env"]["AGENT_SECRET"] == "{{ portainer_agent_secret }}"
    assert "/var/run/docker.sock:/var/run/docker.sock" in c["volumes"]
    assert _yaml(DOCKER_DEFAULTS)["portainer_agent_image"] == "portainer/agent:2.19.4"


def test_segredo_do_agente_no_vault_example():
    ex = (ANS / "inventories/home/group_vars/all/vault.yml.example").read_text(encoding="utf-8")
    assert "portainer_agent_secret:" in ex


# --- Repositórios do Proxmox (PVE 8 .list e PVE 9 .sources) ---

def test_repositorios_enterprise_nos_dois_formatos():
    t = _yaml(PVE_TASKS)
    texto = PVE_TASKS.read_text(encoding="utf-8")
    verifica = [x for x in t if "ansible.builtin.stat" in x and "sources.list.d" in str(x)]
    for x in verifica:
        assert x["ansible.builtin.stat"]["path"] == "/etc/apt/sources.list.d/{{ item }}"
    nomes = {n for x in verifica for n in x["loop"]}
    assert nomes == {"pve-enterprise.list", "ceph.list", "pve-enterprise.sources", "ceph.sources"}
    assert "sources.list.d" in texto
    bloco = _tarefa(t, "Atualizar repositórios Proxmox")["block"]
    desliga = _tarefa(bloco, "Desativar repositórios enterprise no formato .sources")
    assert desliga["ansible.builtin.lineinfile"]["line"] == "Enabled: no"
    assert "item.stat.exists" in desliga["when"]
    deb822 = _tarefa(bloco, "no-subscription (PVE 9")
    r = deb822["ansible.builtin.deb822_repository"]
    assert r["uris"] == "http://download.proxmox.com/debian/pve" and r["components"] == "pve-no-subscription"
    assert r["suites"] == "{{ ansible_distribution_release }}"
    antigo = _tarefa(bloco, "no-subscription (PVE 8")
    assert "ansible.builtin.apt_repository" in antigo
    assert deb822["when"] != antigo["when"]
