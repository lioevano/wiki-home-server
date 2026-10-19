"""Testes dos templates e arquivos de observabilidade do server (Loki, Alloy, Prometheus, alertas)."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import jinja2
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def _bool(v) -> bool:
    return str(v).lower() in ("true", "1", "yes", "on")


def render(rel: str, **vars) -> str:
    """Renderiza server/ansible/<rel> como o Ansible faria (StrictUndefined, filtro bool)."""
    env = jinja2.Environment(
        undefined=jinja2.StrictUndefined,
        loader=jinja2.FileSystemLoader(ROOT / "server" / "ansible"),
        keep_trailing_newline=True,
    )
    env.filters["bool"] = _bool
    return env.get_template(rel).render(**vars)


def test_loki_schema_v13_tsdb():
    cfg = yaml.safe_load(render("templates/loki-local-config.yaml.j2"))
    periodo = cfg["schema_config"]["configs"][-1]
    assert periodo["schema"] == "v13" and periodo["store"] == "tsdb"
    assert periodo["object_store"] == "filesystem" and periodo["index"]["period"] == "24h"
    assert "tsdb_shipper" in cfg["storage_config"]
    assert "alertmanager_url" not in str(cfg.get("ruler", {}))


# --- Alloy (role infra/alloy) ---

ALLOY_VARS = dict(alloy_loki_push_url="http://192.168.15.67:3100/loki/api/v1/push",
                  alloy_remote_write_url="http://192.168.15.67:9090/api/v1/write")
ALLOY_TPL = "roles/infra/alloy/templates/config.alloy.j2"


def test_alloy_vm_com_docker():
    out = render(ALLOY_TPL, inventory_hostname="core-services-vm", alloy_docker_enabled=True, **ALLOY_VARS)
    for trecho in ('loki.source.docker', 'prometheus.exporter.cadvisor', 'loki.source.journal',
                   'prometheus.exporter.unix', '"docker_logs"', '"system_journal"', '"var_log"',
                   '"cadvisor"', '"node"', 'regex = "/(.*)"', '"container_name"', '"core-services-vm"',
                   ALLOY_VARS["alloy_loki_push_url"], ALLOY_VARS["alloy_remote_write_url"]):
        assert trecho in out, trecho
    assert "{{" not in out and "{%" not in out


def test_alloy_host_sem_docker():
    out = render(ALLOY_TPL, inventory_hostname="proxmox_main_host", alloy_docker_enabled=False, **ALLOY_VARS)
    assert "loki.source.docker" not in out and "cadvisor" not in out
    assert "prometheus.exporter.unix" in out and '"proxmox_main_host"' in out


def test_alloy_docker_desligado_como_texto():
    # O Ansible entrega o padrão de alloy_docker_enabled como a string "False".
    out = render(ALLOY_TPL, inventory_hostname="proxmox_main_host", alloy_docker_enabled="False", **ALLOY_VARS)
    assert "loki.source.docker" not in out


@pytest.mark.skipif(shutil.which("alloy") is None, reason="binário alloy ausente")
@pytest.mark.parametrize("docker", [True, False])
def test_alloy_validate(tmp_path, docker):
    # Mesmo comando que o 'validate:' do template no role (confere componentes e argumentos).
    f = tmp_path / "config.alloy"
    f.write_text(render(ALLOY_TPL, inventory_hostname="h", alloy_docker_enabled=docker, **ALLOY_VARS))
    r = subprocess.run(["alloy", "validate", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def _expr(defaults: dict, chave: str, **ctx) -> str:
    return jinja2.Environment().from_string(defaults[chave]).render(**ctx)


def test_alloy_defaults_por_host():
    d = yaml.safe_load((ROOT / "server/ansible/roles/infra/alloy/defaults/main.yml").read_text(encoding="utf-8"))
    grupos = {"ubuntu_vms": ["core-services-vm", "ai-desktop-vm"]}
    assert _expr(d, "alloy_docker_enabled", inventory_hostname="proxmox_main_host", groups=grupos) == "False"
    assert _expr(d, "alloy_docker_enabled", inventory_hostname="ai-desktop-vm", groups=grupos) == "True"
    ip = "192.168.15.67"
    assert _expr(d, "alloy_scrape_allowed_from", inventory_hostname="core-services-vm",
                 core_services_vm_ip_var=ip) == "172.16.0.0/12"
    assert _expr(d, "alloy_scrape_allowed_from", inventory_hostname="ai-desktop-vm",
                 core_services_vm_ip_var=ip) == ip


# --- VMs: Alloy no lugar do node_exporter ---

def _roles(play) -> list[str]:
    return [r["role"] if isinstance(r, dict) else r for r in play.get("roles", [])]


def test_vms_recebem_alloy_depois_do_docker():
    plays = yaml.safe_load((ROOT / "server/ansible/playbooks/setup-base-ubuntu.yml").read_text(encoding="utf-8"))
    i_docker = next(i for i, p in enumerate(plays) if "infra/docker" in _roles(p))
    i_alloy = next(i for i, p in enumerate(plays) if "infra/alloy" in _roles(p))
    # O grupo docker precisa existir quando o role do Alloy adiciona o usuário alloy a ele.
    assert i_alloy > i_docker
    assert plays[i_alloy]["hosts"].split()[0] == "ubuntu_vms"
    assert "node_exporter" not in (ROOT / "server/ansible/roles/common/tasks/main.yml").read_text(encoding="utf-8").lower()
    assert not (ROOT / "server/ansible/roles/common/templates/node_exporter_vm.service.j2").exists()


# --- Host Proxmox: Alloy, condição pveversion e firewall ---

PVE_TASKS = ROOT / "server/ansible/roles/infra/proxmox-host-config/tasks/main.yml"


def test_sem_condicao_proxmox_ve():
    # No Proxmox o fato ansible_distribution é 'Debian': a condição antiga pulava as tarefas sem avisar.
    for f in (ROOT / "server/ansible").rglob("*.yml"):
        assert "ansible_distribution == 'Proxmox VE'" not in f.read_text(encoding="utf-8"), f


def test_firewall_host_libera_nfs_e_alloy_antes_do_drop():
    tasks = yaml.safe_load(PVE_TASKS.read_text(encoding="utf-8"))
    nomes = [t.get("name", "") for t in tasks]
    i_regras = next(i for i, t in enumerate(tasks) if "community.proxmox.proxmox_firewall" in t)
    i_drop = next(i for i, t in enumerate(tasks) if "community.proxmox.proxmox_cluster_firewall_options" in t)
    assert i_regras < i_drop
    regras = {r["pos"]: r for r in tasks[i_regras]["community.proxmox.proxmox_firewall"]["rules"]}
    assert regras[2]["dport"] == "2049" and "vm_nfs_allowed_clients_cidr" in regras[2]["source"]
    assert regras[3]["dport"] == "12345" and "core_services_vm_ip_var" in regras[3]["source"]
    assert not any("node exporter" in n.lower() for n in nomes)
    play = yaml.safe_load((ROOT / "server/ansible/playbooks/setup-proxmox-host.yml").read_text(encoding="utf-8"))[0]
    assert _roles(play) == ["infra/proxmox-host-config", "infra/alloy"]


def test_condicao_pve_usa_pveversion():
    tasks = yaml.safe_load(PVE_TASKS.read_text(encoding="utf-8"))
    assert tasks[0].get("ansible.builtin.stat", {}).get("path") == "/usr/bin/pveversion"
    assert tasks[0].get("register") == "pve_binary"


# --- Prometheus: remote write, job alloy e alertas ---

PROM_VARS = dict(proxmox_host_ip_var="192.168.15.66", core_services_vm_ip_var="192.168.15.67",
                 ai_desktop_vm_ip_var="192.168.15.68")


def _jobs(groups):
    cfg = yaml.safe_load(render("templates/prometheus.yml.j2", groups=groups, **PROM_VARS))
    return {j["job_name"]: j for j in cfg["scrape_configs"]}


def test_prometheus_job_alloy():
    jobs = _jobs({"ai_desktop": ["ai-desktop-vm"]})
    assert not any(n.startswith("node_exporter") for n in jobs)
    alvos = {c["targets"][0]: c["labels"]["instance"] for c in jobs["alloy"]["static_configs"]}
    assert alvos == {"192.168.15.66:12345": "proxmox_main_host", "192.168.15.67:12345": "core-services-vm",
                     "192.168.15.68:12345": "ai-desktop-vm"}


def test_prometheus_sem_vm_ia():
    alvos = [c["targets"][0] for c in _jobs({})["alloy"]["static_configs"]]
    assert "192.168.15.68:12345" not in alvos


def test_alertas_alloy_e_reinicios():
    regras = {r["uid"]: r for r in yaml.safe_load(render("templates/grafana/alerting/rules.yml.j2"))["groups"][0]["rules"]}
    assert 'job=~"alloy|blackbox_http"' in regras["host-sem-resposta"]["data"][0]["model"]["expr"]
    r = regras["container-reiniciando"]
    assert r["data"][0]["model"]["expr"] == 'changes(container_start_time_seconds{name!=""}[15m])'
    assert r["data"][1]["model"]["conditions"][0]["evaluator"] == {"type": "gt", "params": [3]}
    assert r["labels"]["severity"] == "warning"


def test_prometheus_remote_write_na_lan():
    svc = yaml.safe_load((ROOT / "server/docker/stacks/apps/docker-compose.yml").read_text(encoding="utf-8"))["services"]["prometheus"]
    assert "--web.enable-remote-write-receiver" in svc["command"]
    assert "${CORE_SERVICES_VM_IP_VAR}:9090:9090" in svc["ports"]
