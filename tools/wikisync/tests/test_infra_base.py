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


# --- Pendências menores (#21, #50) ---

def _daemon_json():
    import json
    t = _tarefa(_yaml(DOCKER_TASKS), "daemon do Docker")
    return json.loads(t["ansible.builtin.copy"]["content"])


def test_pools_do_docker_fixos_fora_da_lan():
    """#50: as regras de UFW para 172.16.0.0/12 valem por construção; nunca 192.168.0.0/16 (a LAN)."""
    import ipaddress
    d = _daemon_json()
    assert d["features"]["containerd-snapshotter"] is False
    pools = d["default-address-pools"]
    assert pools == [{"base": "172.16.0.0/12", "size": 24}]
    assert not ipaddress.ip_network(pools[0]["base"]).overlaps(ipaddress.ip_network("192.168.0.0/16"))


def test_docker_depois_do_nfs_sem_exigir():
    """#21: o Docker sobe depois das montagens de rede, mas o NFS fora não impede a core de subir."""
    t = _tarefa(_yaml(DOCKER_TASKS), "Docker depois das montagens")
    c = t["ansible.builtin.copy"]
    assert c["dest"] == "/etc/systemd/system/docker.service.d/10-montagens.conf"
    assert "After=remote-fs.target" in c["content"] and "Wants=remote-fs.target" in c["content"]
    assert "Requires" not in c["content"]
    servico = _tarefa(_yaml(DOCKER_TASKS), "serviço Docker está rodando")
    assert servico["ansible.builtin.systemd_service"]["daemon_reload"] is True


# --- Pendências menores (#45, #46) ---

COMMON_TASKS = ANS / "roles/common/tasks/main.yml"
UFW_PARAMS = {"state", "default", "direction", "logging", "insert", "insert_relative_to", "rule", "log", "from_ip",
              "from_port", "to_ip", "to_port", "proto", "name", "delete", "interface", "interface_in",
              "interface_out", "route", "comment", "port"}


def _ufw_tarefas():
    return [t for t in _yaml(COMMON_TASKS) if "community.general.ufw" in t]


def test_ufw_so_com_parametros_do_modulo():
    """O módulo community.general.ufw não tem 'rules', 'policy' nem 'default_outgoing_policy' (falhava na execução)."""
    for t in _ufw_tarefas():
        assert set(t["community.general.ufw"]) <= UFW_PARAMS, t["name"]


def test_ufw_em_todas_as_vms():
    """#45: o UFW liga em todas as VMs (o Alloy nativo da ai-desktop-vm escuta na 12345), não só com GUI_ENABLED."""
    tarefas = _ufw_tarefas()
    ligar = next(t for t in tarefas if t["community.general.ufw"].get("state") == "enabled")
    assert "when" not in ligar
    padrao = next(t for t in tarefas if t["community.general.ufw"].get("default") == "deny")
    assert padrao["community.general.ufw"]["direction"] == "incoming"
    ssh = next(t for t in tarefas if t["community.general.ufw"].get("port") == "22")
    assert "when" not in ssh
    nomes = [t["name"] for t in tarefas]
    assert nomes.index(ssh["name"]) < nomes.index(ligar["name"])  # SSH liberado antes de ligar: sem se trancar fora
    web = next(t for t in tarefas if "80" in str(t.get("loop", "")) or t["community.general.ufw"].get("port") == "80")
    assert "core_services" in str(web["when"])
    vnc = next(t for t in tarefas if t["community.general.ufw"].get("port") == "5901")
    assert "GUI_ENABLED" in str(vnc["when"])


def test_prometheus_sem_api_de_ciclo_de_vida():
    """#46: com a 9090 na LAN (remote write), /-/quit e /-/reload ficam desligados."""
    svc = _yaml(ROOT / "server/docker/stacks/apps/docker-compose.yml")["services"]["prometheus"]
    assert "--web.enable-lifecycle" not in svc["command"]


def test_docker_reinicia_quando_a_configuracao_muda():
    """Revisão final: daemon.json e drop-in novos só valem com o daemon reiniciado."""
    tarefas = _yaml(DOCKER_TASKS)
    for trecho in ("daemon do Docker", "Docker depois das montagens"):
        assert _tarefa(tarefas, trecho)["notify"] == "Reiniciar Docker", trecho
    h = next(h for h in _yaml(ANS / "roles/infra/docker/handlers/main.yml") if h["name"] == "Reiniciar Docker")
    assert h["ansible.builtin.systemd_service"] == {"name": "docker", "state": "restarted", "daemon_reload": True}
