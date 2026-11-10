"""VPN e firewall das portas do Docker (spec 2026-10-21-vpn-firewall-design)."""
from __future__ import annotations

import json
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
    assert core[4200] == ["192.168.15.68"]  # rota dos autônomos: só a VM de IA (página 18)
    ai = {r["porta"]: r["origens"] for r in regras["ai-desktop-vm"]}
    assert ai == {9001: ["192.168.15.67"], 3100: ["192.168.15.67"], 3005: ["192.168.15.67"]}
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
    # Roda antes do Docker: cria a DOCKER-USER (o Docker a reaproveita) antes da cadeia própria.
    assert l[:2] == ["-N DOCKER-USER", "-N HOMESERVER"] and "-I DOCKER-USER -j HOMESERVER" in l
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
    # Antes do Docker: as regras existem quando os containers sobem (sem janela aberta no boot).
    assert "Before=docker.service" in c and "After=docker.service" not in c
    assert "PartOf=docker.service" in c and "WantedBy=docker.service" in c
    assert "RemainAfterExit=true" in c


# --- Tailscale e DNS da VPN ---

def _acl():
    return json.loads((ROOT / "server/scripts/tailscale/acl.json").read_text(encoding="utf-8"))


def test_rotas_incluem_o_host_e_tags():
    m = _main()
    assert m["tailscale_rotas"] == ["{{ proxmox_host_ip_var }}/32", "{{ core_services_vm_ip_var }}/32",
                                    "{{ ai_desktop_vm_ip_var }}/32"]
    d = yaml.safe_load((ANS / "roles/infra/tailscale/defaults/main.yml").read_text(encoding="utf-8"))
    assert d == {"tailscale_tags": ["tag:homeserver"], "tailscale_aceitar_rotas": False,
                 "tailscale_coredns": True, "tailscale_ufw": True}


def test_role_tailscale_parametrizado():
    t = (ANS / "roles/infra/tailscale/tasks/main.yml").read_text(encoding="utf-8")
    assert "{{ ansible_facts.distribution | lower }}" in t           # Ubuntu (VMs, GCP) e Debian (Proxmox)
    assert "--advertise-tags={{ tailscale_tags | join(',') }}" in t
    assert "--accept-routes={{ tailscale_aceitar_rotas | bool | lower }}" in t
    tarefas = yaml.safe_load(t)
    for x in tarefas:
        if x["name"].startswith("CoreDNS"):
            assert x["when"] == "tailscale_coredns | bool"
        if x["name"].startswith("UFW"):
            assert x["when"] == "tailscale_ufw | bool"
    # Tags só no 'up' (R1): o 'tailscale set' não troca tags sem reautenticar.
    sete = next(x for x in tarefas if "tailscale set" in str(x.get("ansible.builtin.command", "")))
    assert "advertise-tags" not in sete["ansible.builtin.command"]


def test_host_proxmox_e_no_proprio():
    pb = yaml.safe_load((ANS / "playbooks/setup-proxmox-host.yml").read_text(encoding="utf-8"))
    papeis = [r for p in pb for r in p.get("roles", [])]
    ts = next(r for r in papeis if isinstance(r, dict) and r.get("role") == "infra/tailscale")
    assert ts["vars"] == {"tailscale_hostname": "pve", "tailscale_coredns": False, "tailscale_ufw": False,
                          "tailscale_auth_key": "{{ tailscale_auth_key_host | default('') }}"}


def test_acl_casa_nao_alcanca_o_sysadmin():
    acl = _acl()
    assert set(acl["tagOwners"]) == {"tag:sysadmin", "tag:homeserver"}
    assert acl["hosts"] == {"pve": "192.168.15.66", "core": "192.168.15.67", "ai": "192.168.15.68"}
    for regra in acl["acls"]:
        if any(s in ("tag:homeserver", "pve", "core", "ai") for s in regra["src"]):
            assert not any(d.startswith("tag:sysadmin") for d in regra["dst"])
    sa = [r for r in acl["acls"] if r["src"] == ["tag:sysadmin"]]
    assert sa == [{"action": "accept", "src": ["tag:sysadmin"], "dst": ["pve:22,8006", "core:22,443,53", "ai:22"]}]
    assert {"action": "accept", "src": ["autogroup:member"], "dst": ["tag:sysadmin:22,443"]} in acl["acls"]
    assert acl["autoApprovers"]["routes"] == {f"192.168.15.{n}/32": ["tag:homeserver"] for n in (66, 67, 68)}


def test_role_tailscale():
    t = yaml.safe_load((ANS / "roles/infra/tailscale/tasks/main.yml").read_text(encoding="utf-8"))
    up = next(x for x in t if "tailscale up" in str(x.get("ansible.builtin.command", "")))
    assert up.get("no_log") is True and "--advertise-routes" in up["ansible.builtin.command"]
    assert "Running" in up["when"]  # a auth key é de uso único: só entra se ainda não está na rede
    nomes = [x["name"] for x in t]
    apt = next(x for x in t if "ansible.builtin.apt" in x)
    assert apt["when"] == "not ansible_check_mode"  # no --check o repositório só foi simulado
    sysctl = next(x for x in t if "ansible.posix.sysctl" in x)["ansible.posix.sysctl"]
    assert sysctl["name"] == "net.ipv4.ip_forward" and sysctl["reload"] is True
    assert "ipv6" not in str(t)  # forwarding do IPv6 desligaria o accept_ra da LAN
    assert nomes.index(next(x["name"] for x in t if "ansible.posix.sysctl" in x)) < nomes.index(up["name"])
    sete = next(x for x in t if "tailscale set" in str(x.get("ansible.builtin.command", "")))
    assert "AdvertiseRoutes" in sete["when"] and sete["changed_when"] is True
    assert not (ANS / "roles/infra/tailscale/handlers/main.yml").exists()
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
        resposta = None
        for _ in range(50):
            try:
                resposta = _consulta(15353, "fotos.exemplo.com")
                break
            except OSError:
                time.sleep(0.1)
        assert resposta is not None, "o CoreDNS não respondeu em 5 s"
        assert resposta == (0, ["192.168.15.67"])
        assert _consulta(15353, "fotos.exemplo.com", 28) == (0, [])  # AAAA: vazio, sem erro
        for tipo in (65, 16, 15, 6):  # HTTPS (navegadores, iOS), TXT, MX, SOA: vazio, nunca SERVFAIL
            assert _consulta(15353, "fotos.exemplo.com", tipo) == (0, []), tipo
        assert _consulta(15353, "google.com")[0] == 5  # REFUSED: fora do domínio
    finally:
        p.terminate()
        p.wait(timeout=5)


def test_tailscale_up_exige_chave():
    """Host em DR (ou caminho manual) sem chave: falha clara antes do `tailscale up`, não um `up` sem chave."""
    import jinja2
    t = yaml.safe_load((ANS / "roles/infra/tailscale/tasks/main.yml").read_text(encoding="utf-8"))
    nomes = [x["name"] for x in t]
    up = next(x for x in t if "tailscale up" in str(x.get("ansible.builtin.command", "")))
    a = next(x for x in t if "ansible.builtin.assert" in x)
    assert nomes.index(a["name"]) < nomes.index(up["name"])
    assert a["when"] == up["when"]  # só quando o nó ainda não está na rede
    msg = a["ansible.builtin.assert"]["fail_msg"]
    assert "scripts/gcp/preparar-host.sh" in msg and "tailscale_auth_key_host" in msg and "vault" in msg
    assert "no_log" not in a  # a mensagem precisa aparecer; o assert não mostra o valor
    (cond,) = a["ansible.builtin.assert"]["that"]
    env = jinja2.Environment()
    avaliar = lambda **v: env.from_string("{{ " + cond + " }}").render(**v) == "True"
    assert avaliar(tailscale_auth_key="tskey-auth-x") is True
    for v in ({"tailscale_auth_key": ""}, {"tailscale_auth_key": "  "}, {}):
        assert avaliar(**v) is False, v


@pytest.mark.parametrize("estado, entra, religa", [
    ("NeedsLogin", True, False), ("NoState", True, False), (None, True, False),
    ("Stopped", False, True), ("Running", False, False), ("Starting", False, False)])
def test_tailscale_desligado_religa_sem_chave(estado, entra, religa):
    """Um nó só desligado (`tailscale down`) não pede chave: o assert e o `up` com chave são para quem não tem login."""
    import json as _json
    import jinja2
    t = yaml.safe_load((ANS / "roles/infra/tailscale/tasks/main.yml").read_text(encoding="utf-8"))
    env = jinja2.Environment()
    env.filters["from_json"] = _json.loads
    saida = "" if estado is None else _json.dumps({"BackendState": estado})
    vale = lambda x: env.from_string("{{ " + x["when"] + " }}").render(tailscale_status={"stdout": saida}) == "True"
    a = next(x for x in t if "ansible.builtin.assert" in x)
    up = next(x for x in t if "--auth-key" in str(x.get("ansible.builtin.command", "")))
    rel = next(x for x in t if x["name"] == "Tailscale: religar (estava desligado)")
    assert (vale(a), vale(up), vale(rel)) == (entra, entra, religa)
    assert "--auth-key" not in rel["ansible.builtin.command"] and "no_log" not in rel
