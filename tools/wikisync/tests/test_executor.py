"""Executor do sysadmin (sub-projeto 5a, página 19): configuração, portão de aprovação e comandos remotos."""
from __future__ import annotations

import sys

import pytest

from test_observabilidade import ROOT

sys.path.insert(0, str(ROOT / "server/docker/images/executor"))
sys.path.insert(0, str(ROOT / "server/docker/images/ops"))
sys.path.insert(0, str(ROOT / "server/docker/images/aprovador"))
sys.dont_write_bytecode = True  # sem __pycache__ em docker/images (o copy do playbook o levaria)

from aprovador.pedidos import Registro  # noqa: E402
from executor.config import Config, ConfigInvalida  # noqa: E402
from executor.portao import Portao  # noqa: E402
from executor.remoto import Remoto, validar_diagnostico  # noqa: E402
from ops.politica import Recusado  # noqa: E402

AMB = {"EXECUTOR_TOKEN": "tok", "TELEGRAM_BOT_TOKEN": "1:x", "TELEGRAM_CHAT_ID": "4242",
       "EXECUTOR_PLAYBOOKS": '{"setup-vpn.yml": "VPN"}', "TAILSCALE_CHAVE_HOST": "tskey-h",
       "ANSIBLE_USUARIO_HOST": "proxmox_ansible_user", "REPO_URL_RAW": "https://raw.githubusercontent.com/o/r/main",
       "EQUIPE_REPO": "o/homeserver-equipe", "GITHUB_TOKEN_EQUIPE": "ghp", "CONTA_SYSADMIN": "o-sysadmin",
       "WEBHOOK_URL": "http://sysadmin:8644/webhooks/equipe", "WEBHOOK_SEGREDO": "s",
       "EXECUTOR_ROTAS": "192.168.15.66/32,192.168.15.67/32,192.168.15.68/32"}


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_config_falha_fechada():
    c = Config.do_ambiente(AMB)
    assert c.usuarios == {"4242"} and c.playbooks == {"setup-vpn.yml": "VPN"} and c.validade_s == 1800
    with pytest.raises(ConfigInvalida, match="EXECUTOR_TOKEN"):
        Config.do_ambiente({**AMB, "EXECUTOR_TOKEN": " "})
    assert c.para_ops().modo == "controle" and c.para_ops().chave_ssh == "/segredos/id_ed25519"


def test_config_padroes_e_grupo():
    c = Config.do_ambiente(AMB)
    assert c.repo_dir == "/repo" and c.inventario == "inventories/home/hosts.ini"
    assert c.rotas == AMB["EXECUTOR_ROTAS"] and c.carteiro_intervalo_s == 120 and c.limite_saida == 20000
    o = c.para_ops()
    assert o.inventario == "inventories/home/hosts.ini" and o.playbooks == c.playbooks
    assert o.plano_validade_s == 1800 and o.portainer_url == "" and o.repo_dir == "/repo"
    # grupo (id negativo): só os usuários extras decidem; sem eles, falha fechada
    g = {**AMB, "TELEGRAM_CHAT_ID": "-100"}
    with pytest.raises(ConfigInvalida, match="ninguém"):
        Config.do_ambiente(g)
    assert Config.do_ambiente({**g, "EXECUTOR_TELEGRAM_USUARIOS": "7, 8"}).usuarios == {"7", "8"}
    with pytest.raises(ConfigInvalida, match="EXECUTOR_PLAYBOOKS"):
        Config.do_ambiente({**AMB, "EXECUTOR_PLAYBOOKS": "não é json"})
    with pytest.raises(ConfigInvalida, match="EXECUTOR_PLAYBOOKS"):
        Config.do_ambiente({**AMB, "EXECUTOR_PLAYBOOKS": '["a"]'})


@pytest.mark.parametrize("cmd,become", [
    ("systemctl status docker", False), ("journalctl -u tailscaled -n 200 --no-pager", True),
    ("docker ps -a", True), ("docker logs --tail 100 traefik", True), ("df -h", False), ("free -m", False),
    ("ip -br a", False), ("ss -tlnp", True), ("ping -c 3 1.1.1.1", False), ("tailscale status", False),
    ("cat /etc/os-release", False),
    ("systemctl is-active docker.service", False), ("systemctl list-units --failed", False),
    ("journalctl -u tailscaled -n 500", True), ("docker ps", True), ("uptime", False), ("ip route", False)])
def test_diagnostico_aceita_so_leitura(cmd, become):
    argv, b = validar_diagnostico(cmd)
    assert argv == cmd.split() and b is become


@pytest.mark.parametrize("cmd", [
    "journalctl -u x;rm -rf /", "docker logs --tail 9999 x", "docker inspect authelia", "cat /etc/shadow",
    "ping -c 50 1.1.1.1", "systemctl restart docker", "df -h | sh", "echo $(id)", "docker logs --tail 10 'a b'",
    "", "rm -rf /",
    # fora do intervalo, formas quase certas, metacaracteres e argumentos extras
    "docker logs --tail 0 x", "docker logs --tail 501 x", "docker logs --tail -5 x", "docker logs --tail 5",
    "journalctl -u x -n 0", "journalctl -u x -n 501", "journalctl -u x", "journalctl -u x -n 5 --follow",
    "ping -c 0 1.1.1.1", "ping -c 6 1.1.1.1", "ping -c 3 -f 1.1.1.1", "ping 1.1.1.1",
    "systemctl status", "systemctl status a b", "systemctl status --all", "systemctl is-active -x",
    "systemctl list-units", "systemctl list-units --failed --all", "systemctl status docker\nrm x",
    "docker ps -a -q", "docker ps --format {{.ID}}", "docker exec x ls", "docker logs --tail 5 -f",
    "df -h /", "df", "free -h", "ip a", "ip -br a extra", "ss -a", "uptime -p", "tailscale up", "tailscale status --json",
    "cat /etc/os-release /etc/shadow", "cat /etc/passwd", "cat ../etc/os-release", "cat",
    "docker logs --tail 10 `id`", 'docker logs --tail 10 "a"', "docker logs --tail 10 a&b", "df -h > /tmp/x",
    "df -h\n", "ping -c 3 -- x", "ping -c 3 $HOME", "docker logs --tail 10 x\x00", "systemctl status \\x",
    "docker logs --tail 010 x", "docker logs --tail １０ x", "docker logs --tail 1_0 x"])
def test_diagnostico_recusa(cmd):
    with pytest.raises(Recusado):
        validar_diagnostico(cmd)


def test_diagnostico_recusa_nao_texto():
    with pytest.raises(Recusado):
        validar_diagnostico(None)  # type: ignore[arg-type]


def test_portao_pede_e_depois_executa(tmp_path):
    rel, enviados = Relogio(), []
    reg = Registro(str(tmp_path / "p.json"), 1800, rel)
    tg = type("T", (), {"avisar": lambda self, p: enviados.append(p)})()
    portao, feito = Portao(reg, tg), []
    r = portao.executar("comando", "core-services-vm", {"comando": "ls"}, None, "listar", lambda: feito.append(1) or "ok")
    pid = enviados[0]["id"]
    assert pid in r and feito == [] and enviados[0]["cliente"] == "sysadmin"
    assert "Aguardando aprovação humana" in r and f'aprovacao_id="{pid}"' in r
    with pytest.raises(Recusado):  # ainda pendente
        portao.executar("comando", "core-services-vm", {"comando": "ls"}, pid, "", lambda: "x")
    reg.decidir(pid, True, "telegram:leo")
    with pytest.raises(Recusado):  # outro argumento
        portao.executar("comando", "core-services-vm", {"comando": "id"}, pid, "", lambda: "x")
    assert portao.executar("comando", "core-services-vm", {"comando": "ls"}, pid, "", lambda: "ok") == "ok"
    with pytest.raises(Recusado):  # uso único
        portao.executar("comando", "core-services-vm", {"comando": "ls"}, pid, "", lambda: "ok")
    assert feito == []


def test_portao_recusa_pedido_recusado_e_inexistente(tmp_path):
    reg = Registro(str(tmp_path / "p.json"), 1800, Relogio())
    enviados = []
    tg = type("T", (), {"avisar": lambda self, p: enviados.append(p)})()
    portao = Portao(reg, tg)
    portao.executar("playbook", "setup-vpn.yml", {}, None, "", lambda: "x")
    reg.decidir(enviados[0]["id"], False, "telegram:leo")
    with pytest.raises(Recusado):
        portao.executar("playbook", "setup-vpn.yml", {}, enviados[0]["id"], "", lambda: "x")
    with pytest.raises(Recusado):
        portao.executar("playbook", "setup-vpn.yml", {}, "naoexiste", "", lambda: "x")


def test_portao_limite_de_pendentes_vira_recusa(tmp_path):
    reg = Registro(str(tmp_path / "p.json"), 1800, Relogio())
    tg = type("T", (), {"avisar": lambda self, p: None})()
    portao = Portao(reg, tg)
    with pytest.raises(Recusado):
        for i in range(10):
            portao.executar("comando", "h", {"n": i}, None, "", lambda: "x")


def test_remoto_monta_o_ansible_adhoc(tmp_path):
    inv = tmp_path / "server/ansible/inventories/home"
    inv.mkdir(parents=True)
    (inv / "hosts.ini").write_text("[proxmox_hosts]\nproxmox_main_host ansible_host=1.2.3.4\n[core_services]\n"
                                   "core-services-vm ansible_host=1.2.3.5\n[all:vars]\nx=1\n", encoding="utf-8")
    chamadas = []
    cfg = Config.do_ambiente({**AMB, "EXECUTOR_REPO_DIR": str(tmp_path)})
    r = Remoto(cfg, lambda argv, cwd, t: chamadas.append((argv, cwd, t)) or (0, "token=abc\nok"))
    assert r.hosts() == {"proxmox_main_host", "core-services-vm"}
    rc, saida = r.rodar("core-services-vm", ["docker", "ps"], shell=False, become=True)
    argv, cwd, t = chamadas[0]
    assert argv[:6] == ["ansible", "core-services-vm", "-i", "inventories/home/hosts.ini", "-m", "ansible.builtin.command"]
    assert "--become" in argv and t == 120 and cwd.endswith("server/ansible") and "token=abc" not in saida
    with pytest.raises(Recusado):
        r.rodar("outro", ["df"], shell=False, become=False)


def test_remoto_hosts_ignora_comentarios_vars_e_children(tmp_path):
    inv = tmp_path / "server/ansible/inventories/home"
    inv.mkdir(parents=True)
    (inv / "hosts.ini").write_text(
        "# comentário\n; outro\n\n[a]\nh1 ansible_host=1\n  h2\n[b:children]\na\n[b:vars]\nvar=1\n[c]\nh3 x=y\n",
        encoding="utf-8")
    cfg = Config.do_ambiente({**AMB, "EXECUTOR_REPO_DIR": str(tmp_path)})
    assert Remoto(cfg, lambda *a: (0, "")).hosts() == {"h1", "h2", "h3"}


def test_remoto_shell_sem_become_e_comando_como_texto(tmp_path):
    inv = tmp_path / "server/ansible/inventories/home"
    inv.mkdir(parents=True)
    (inv / "hosts.ini").write_text("[g]\nh1\n", encoding="utf-8")
    chamadas = []
    cfg = Config.do_ambiente({**AMB, "EXECUTOR_REPO_DIR": str(tmp_path)})
    r = Remoto(cfg, lambda argv, cwd, t: chamadas.append(argv) or (3, "falhou"))
    assert r.rodar("h1", "df -h | head", shell=True, become=False) == (3, "falhou")
    argv = chamadas[0]
    assert "ansible.builtin.shell" in argv and "--become" not in argv and "df -h | head" in argv
    assert "ansible_ssh_private_key_file=/segredos/id_ed25519" in argv
    r.rodar("h1", ["docker", "logs", "x y"], shell=False, become=False)
    assert "docker logs 'x y'" in chamadas[1]  # argv vira texto com aspas (módulo command separa de volta)
    with pytest.raises(Recusado):  # nome de host que parece opção ou fora do inventário
        r.rodar("-m", ["df"], shell=False, become=False)
