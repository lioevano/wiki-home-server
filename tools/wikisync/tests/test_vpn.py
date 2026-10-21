"""VPN e firewall das portas do Docker (spec 2026-10-21-vpn-firewall-design)."""
from __future__ import annotations

import shutil
import socket
import struct
import subprocess
import sys
import time

import pytest
import yaml

from test_observabilidade import ROOT, render

ANS = ROOT / "server/ansible"
MAIN = ANS / "inventories/home/group_vars/all/main.yml"
IPS = {"proxmox_host_ip_var": "192.168.15.66", "core_services_vm_ip_var": "192.168.15.67",
       "ai_desktop_vm_ip_var": "192.168.15.68"}


def _main() -> dict:
    return yaml.safe_load(MAIN.read_text(encoding="utf-8"))


def _resolve(v):
    if isinstance(v, str):
        for k, ip in IPS.items():
            v = v.replace("{{ " + k + " }}", ip)
        return v
    if isinstance(v, list):
        return [_resolve(x) for x in v]
    if isinstance(v, dict):
        return {k: _resolve(x) for k, x in v.items()}
    return v


# --- Firewall das portas publicadas pelo Docker ---

def test_portas_restritas():
    regras = _resolve(_main()["firewall_docker_portas"])
    core = {r["porta"]: r["origens"] for r in regras["core-services-vm"]}
    assert core[9090] == core[3100] == ["192.168.15.66", "192.168.15.68"]
    assert core[4100] == []  # rota de controle do hub: só pela VPN
    ai = {r["porta"]: r["origens"] for r in regras["ai-desktop-vm"]}
    assert ai == {9001: ["192.168.15.67"], 3100: ["192.168.15.67"]}
    assert all(r["motivo"] for r in regras["core-services-vm"] + regras["ai-desktop-vm"])


def _script(host: str) -> str:
    return render("roles/infra/docker/templates/firewall-docker.sh.j2", inventory_hostname=host,
                  ansible_facts={"default_ipv4": {"interface": "ens18"}},
                  firewall_docker_portas=_resolve(_main()["firewall_docker_portas"]))


@pytest.mark.skipif(sys.platform == "win32", reason="bash")
def test_script_monta_a_cadeia_na_ordem(tmp_path):
    """Executa o script com um iptables falso: cadeia própria em DOCKER-USER, RETURN das origens antes do DROP."""
    falso = tmp_path / "iptables"
    falso.write_text('#!/bin/bash\necho "$*" >> "$LOG"\ncase "$1" in -C) exit 1;; esac\nexit 0\n')
    falso.chmod(0o755)
    script = tmp_path / "fw.sh"
    script.write_text(_script("core-services-vm"))
    log = tmp_path / "log"
    import os
    r = subprocess.run(["bash", str(script)], env=dict(os.environ, IPTABLES=str(falso), LOG=str(log)),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    l = log.read_text().splitlines()
    assert l[0] == "-N HOMESERVER" and "-I DOCKER-USER -j HOMESERVER" in l
    ok = l.index("-A HOMESERVER -i ens18 -p tcp -s 192.168.15.66 -m conntrack --ctorigdstport 9090 --ctdir ORIGINAL -j RETURN")
    drop = l.index("-A HOMESERVER -i ens18 -p tcp -m conntrack --ctorigdstport 9090 --ctdir ORIGINAL -j DROP")
    assert ok < drop
    assert "-A HOMESERVER -i ens18 -p tcp -m conntrack --ctorigdstport 4100 --ctdir ORIGINAL -j DROP" in l
    assert not any("4100" in x and "RETURN" in x for x in l)
    assert l[-1] == "-A HOMESERVER -j RETURN"
    assert "ens18" in _script("ai-desktop-vm") and "9090" not in _script("ai-desktop-vm")


def test_unit_do_firewall_acompanha_o_docker():
    tarefas = yaml.safe_load((ANS / "roles/infra/docker/tasks/main.yml").read_text(encoding="utf-8"))
    unit = next(t for t in tarefas if t.get("ansible.builtin.copy", {}).get("dest") == "/etc/systemd/system/firewall-docker.service")
    c = unit["ansible.builtin.copy"]["content"]
    assert "After=docker.service" in c and "PartOf=docker.service" in c and "WantedBy=docker.service" in c
    assert "RemainAfterExit=true" in c


# --- Tailscale e DNS da VPN ---

def test_rotas_so_das_vms():
    rotas = _resolve(_main()["tailscale_rotas"])
    assert rotas == ["192.168.15.67/32", "192.168.15.68/32"]  # o host Proxmox fica fora (alcançável sem a VPN)


def test_role_tailscale():
    t = yaml.safe_load((ANS / "roles/infra/tailscale/tasks/main.yml").read_text(encoding="utf-8"))
    up = next(x for x in t if "tailscale up" in str(x.get("ansible.builtin.command", "")))
    assert up.get("no_log") is True and "--advertise-routes" in up["ansible.builtin.command"]
    assert "Running" in up["when"]  # a auth key é de uso único: só entra se ainda não está na rede
    rota = next(x for x in t if x.get("community.general.ufw", {}).get("route") is True)
    assert rota["community.general.ufw"]["interface_in"] == "tailscale0"
    dns = next(x for x in t if "community.docker.docker_container" in x)["community.docker.docker_container"]
    assert dns["image"] == "coredns/coredns:{{ coredns_version }}"
    assert dns["ports"] == ["{{ core_services_vm_ip_var }}:53:53/udp", "{{ core_services_vm_ip_var }}:53:53/tcp"]
    pb = yaml.safe_load((ANS / "playbooks/setup-vpn.yml").read_text(encoding="utf-8"))[0]
    assert pb["hosts"] == "core_services" and pb["roles"] == [{"role": "infra/tailscale"}]
    importados = [p["import_playbook"] for p in yaml.safe_load((ANS / "playbooks/full-deploy.yml").read_text(encoding="utf-8"))]
    assert importados.index("setup-core-networking.yml") < importados.index("setup-vpn.yml")
    assert "tailscale_auth_key" in yaml.safe_load(
        (ANS / "inventories/home/group_vars/all/vault.yml.example").read_text(encoding="utf-8"))


def _consulta(porta: int, nome: str, tipo: int = 1) -> tuple[int, list[str]]:
    q = struct.pack(">HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
    q += b"".join(bytes([len(p)]) + p.encode() for p in nome.split(".")) + b"\x00" + struct.pack(">HH", tipo, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2)
    s.sendto(q, ("127.0.0.1", porta))
    r, _ = s.recvfrom(512)
    rcode = r[3] & 0x0F
    ancount = struct.unpack(">H", r[6:8])[0]
    return rcode, [socket.inet_ntoa(r[-4:])] if ancount else []  # uma resposta A: o IP são os 4 últimos bytes


@pytest.mark.skipif(shutil.which("coredns") is None, reason="binário coredns ausente")
def test_dns_da_vpn(tmp_path):
    """O CoreDNS de verdade com o Corefile renderizado: *.domínio → core; outras zonas recusadas."""
    cfg = render("roles/infra/tailscale/templates/Corefile.j2", base_domain="exemplo.com",
                 core_services_vm_ip_var="192.168.15.67").replace("exemplo.com:53", "exemplo.com:15353")
    (tmp_path / "Corefile").write_text(cfg)
    p = subprocess.Popen(["coredns", "-conf", str(tmp_path / "Corefile")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            try:
                rcode, ips = _consulta(15353, "fotos.exemplo.com")
                break
            except OSError:
                time.sleep(0.1)
        assert rcode == 0 and ips == ["192.168.15.67"]
        assert _consulta(15353, "fotos.exemplo.com", 28) == (0, [])  # AAAA: vazio, sem erro
        assert _consulta(15353, "google.com")[0] == 5  # REFUSED: fora do domínio
    finally:
        p.terminate()
        p.wait(timeout=5)
