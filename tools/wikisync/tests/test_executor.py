"""Executor do sysadmin (sub-projeto 5a, página 02): configuração, portão de aprovação e comandos remotos."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest
import yaml

from test_observabilidade import ROOT

sys.path.insert(0, str(ROOT / "server/docker/images/executor"))
sys.path.insert(0, str(ROOT / "server/docker/images/ops"))
sys.path.insert(0, str(ROOT / "server/docker/images/aprovador"))
sys.dont_write_bytecode = True  # sem __pycache__ em docker/images (o copy do playbook o levaria)

from aprovador.pedidos import Registro  # noqa: E402
from executor.carteiro import Carteiro, assinar  # noqa: E402
from executor.config import Config, ConfigInvalida  # noqa: E402
from executor.ferramentas import ferramentas  # noqa: E402
from executor.portao import Portao  # noqa: E402
from executor.leitor import Leitor  # noqa: E402
from executor.remoto import Remoto, validar_diagnostico  # noqa: E402
from executor.segredos import CanalDeSegredos  # noqa: E402
from executor.servidor import manter_vivo  # noqa: E402
from executor.vault import Vault, chaves_do_modelo, definir  # noqa: E402
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


@pytest.mark.parametrize("marcador", ["{{", "{%", "{#"])
@pytest.mark.parametrize("forma", ["lista", "texto", "elemento"])
def test_remoto_recusa_jinja_sem_executar(tmp_path, marcador, forma):
    inv = tmp_path / "server/ansible/inventories/home"
    inv.mkdir(parents=True)
    (inv / "hosts.ini").write_text("[g]\nh1\n", encoding="utf-8")
    chamadas = []
    cfg = Config.do_ambiente({**AMB, "EXECUTOR_REPO_DIR": str(tmp_path)})
    r = Remoto(cfg, lambda argv, cwd, t: chamadas.append(argv) or (0, ""))
    perigo = f"x {marcador} lookup('file', '/segredos/vault_senha') y"
    comando = {"lista": ["echo", perigo], "texto": f"echo {perigo}", "elemento": [f"{marcador}"]}[forma]
    for shell in (False, True):
        with pytest.raises(Recusado, match="Jinja"):
            r.rodar("h1", comando, shell=shell, become=False)
    assert chamadas == []


MODELO = 'a: "X"\ngrupo:\n  filho: "Y" # comentario\nchave_ssh: |\n  -----BEGIN-----\n  abc\n'


def test_chaves_e_definir():
    assert chaves_do_modelo(MODELO) == {"a", "grupo.filho", "chave_ssh"}
    for valor in ['com "aspas" e \\barra', "linha1\nlinha2", "simples"]:
        for chave in ("a", "grupo.filho", "chave_ssh"):
            novo = definir(MODELO, chave, valor)
            dados = yaml.safe_load(novo)
            alvo = dados["grupo"]["filho"] if chave == "grupo.filho" else dados[chave]
            assert alvo == valor
    assert "# comentario" in definir(MODELO, "grupo.filho", "z")
    with pytest.raises(KeyError):
        definir(MODELO, "nao.existe", "v")


@pytest.mark.parametrize("valor", ["", " com espaço na ponta ", "fim\n", "fim\n\n", "  recuo\nb", "a\n\nb", "tab\tcr\r\nx",
                                   "x #y", "k: v", "ç→✓", "'simples'", "\n"])
def test_definir_valores_dificeis(valor):
    modelo = 'antes: "1"\ngrupo:\n  filho: "Y" # c\n\n  bloco: |\n    a: b\n    c\n\nultimo: "Z"\n'
    for chave in ("grupo.filho", "grupo.bloco"):
        novo = definir(modelo, chave, valor)
        dados = yaml.safe_load(novo)
        assert dados["grupo"]["filho" if chave == "grupo.filho" else "bloco"] == valor
        assert dados["antes"] == "1" and dados["ultimo"] == "Z"
        assert chaves_do_modelo(novo) == chaves_do_modelo(modelo)
    # o resto do texto fica intacto (inclusive a linha em branco antes de `ultimo`)
    assert definir(modelo, "grupo.filho", "z").endswith('\n\n  bloco: |\n    a: b\n    c\n\nultimo: "Z"\n')
    assert definir(modelo, "grupo.bloco", "z").startswith('antes: "1"\ngrupo:\n  filho: "Y" # c\n\n')
    assert definir(modelo, "grupo.bloco", "z").endswith('\n\nultimo: "Z"\n')


def test_chaves_ignoram_comentarios_e_conteudo_de_bloco():
    texto = '# k: v\nmapa:\n  # x: y\n  a: "1"\n  b: |\n    falso: chave\n    mais\n  c: "3"\nvazio:\n'
    assert chaves_do_modelo(texto) == {"mapa.a", "mapa.b", "mapa.c"}
    assert "mapa" not in chaves_do_modelo(texto)
    with pytest.raises(KeyError):
        definir(texto, "mapa", "v")      # chave de mapa não é folha
    with pytest.raises(KeyError):
        definir(texto, "mapa.b.falso", "v")


def test_comentario_com_aspas_no_valor_antigo():
    modelo = 'x: "a #b" # nota\ny: "1"\n'
    assert definir(modelo, "x", "novo") == 'x: "novo" # nota\ny: "1"\n'


def _cfg_vault(tmp_path):
    (tmp_path / "senha").write_text("s3nha\n", encoding="utf-8")
    (tmp_path / "saida").mkdir()
    (tmp_path / ".git").mkdir(exist_ok=True)          # um clone (o git falha nele: histórico desconhecido)
    return replace(Config.do_ambiente(AMB), saida_dir=str(tmp_path / "saida"),
                   senha_vault_arquivo=str(tmp_path / "senha"), repo_dir=str(tmp_path))


def test_vault_cifra_na_saida(tmp_path):
    cfg = _cfg_vault(tmp_path)
    v = Vault(cfg)
    assert v.origem() == tmp_path / "server/ansible/inventories/home/group_vars/all/vault.yml"
    v.gravar(MODELO)
    bruto = (tmp_path / "saida/vault.yml").read_text(encoding="utf-8")
    assert bruto.startswith("$ANSIBLE_VAULT;1.1;AES256") and v.ler() == MODELO and v.origem().parent.name == "saida"
    assert "grupo" not in bruto and "BEGIN" not in bruto
    assert sorted(p.name for p in (tmp_path / "saida").iterdir()) == [".base", "vault.yml"]  # sem temporários nem texto puro
    v.gravar(MODELO + 'z: "1"\n')                    # sobrescreve atomicamente
    assert v.ler().endswith('z: "1"\n')


def test_vault_le_o_do_repo_quando_nao_ha_saida(tmp_path):
    cfg = _cfg_vault(tmp_path)
    Vault(cfg).gravar("k: 1\n")
    alvo = tmp_path / "server/ansible/inventories/home/group_vars/all"
    alvo.mkdir(parents=True)
    (tmp_path / "saida/vault.yml").rename(alvo / "vault.yml")
    v = Vault(cfg)
    assert v.origem() == alvo / "vault.yml" and v.ler() == "k: 1\n"


class BotFalso:
    def __init__(self):
        self.chamadas = []
        self.n = 100

    def chamar(self, metodo, params, timeout=15):
        self.chamadas.append((metodo, params))
        self.n += 1
        return {"message_id": self.n}


def _msg(texto, de="4242", chat="4242", resposta_a=None, mid=7):
    m = {"message_id": mid, "from": {"id": int(de)}, "chat": {"id": int(chat)}, "text": texto}
    if resposta_a:
        m["reply_to_message"] = {"message_id": resposta_a}
    return {"update_id": 1, "message": m}


class VaultFalso:
    """Vault de mentira com a interface do canal (ler e editar); `texto` pode ser trocado no meio do teste."""

    def __init__(self, texto, gravados):
        self.texto, self.gravados = texto, gravados

    def ler(self):
        return self.texto

    def editar(self, chave, valor):
        self.gravados["t"] = definir(self.texto, chave, valor)
        return []


def test_canal_de_segredos(tmp_path):
    gravados = {}
    vault = VaultFalso(MODELO, gravados)
    bot, rel = BotFalso(), Relogio()
    canal = CanalDeSegredos(bot, Config.do_ambiente(AMB), vault, chaves_do_modelo(MODELO), rel)
    with pytest.raises(Recusado):
        canal.pedir("inexistente")
    texto = canal.pedir("grupo.filho")
    assert "grupo.filho" in texto and bot.chamadas[0][1]["reply_markup"] == {"force_reply": True}
    pedido_msg = bot.n
    canal.receber(_msg("solto", mid=8))                       # sem responder: apaga e orienta, não grava
    assert ("deleteMessage", {"chat_id": "4242", "message_id": 8}) in bot.chamadas and gravados == {}
    canal.receber(_msg("x", de="999", resposta_a=pedido_msg))  # outra conta: ignora
    assert gravados == {}
    canal.receber(_msg("VALOR-SECRETO", resposta_a=pedido_msg, mid=9))
    assert yaml.safe_load(gravados["t"])["grupo"]["filho"] == "VALOR-SECRETO"
    assert ("deleteMessage", {"chat_id": "4242", "message_id": 9}) in bot.chamadas
    assert all("VALOR-SECRETO" not in json.dumps(p) for m, p in bot.chamadas if m != "deleteMessage")
    assert "grupo.filho: gravada" in canal.status() and "VALOR-SECRETO" not in canal.status()
    canal.pedir("a")
    pedido_a = bot.n
    rel.t += 1801
    canal.receber(_msg("tarde", resposta_a=pedido_a, mid=10))  # pedido vencido: não grava
    assert "tarde" not in gravados["t"]


def test_canal_segredo_nunca_vaza(tmp_path, capsys):
    """O valor só existe no vault: nem no retorno ao modelo, nem em log, nem em mensagem (só é apagado)."""
    segredo = "S3GREDO-NUNCA-VAZA"
    gravados = {}
    vault = VaultFalso(MODELO, gravados)
    bot, rel = BotFalso(), Relogio()
    cfg = Config.do_ambiente(AMB)
    canal = CanalDeSegredos(bot, cfg, vault, chaves_do_modelo(MODELO), rel)
    retornos = [canal.pedir("a")]
    pedido = bot.n
    # grupo: só quem está em `usuarios` conta, mesmo no chat certo; chat errado também não
    canal.receber(_msg(segredo, de="999", resposta_a=pedido))
    canal.receber(_msg(segredo, chat="555", resposta_a=pedido))
    assert gravados == {} and not any(m == "deleteMessage" for m, _ in bot.chamadas)
    canal.receber({"update_id": 2})                                        # sem mensagem
    canal.receber({"message": {"message_id": 3, "from": {"id": 4242}, "chat": {"id": 4242}}})  # sem texto: só apaga
    canal.receber(_msg(segredo, resposta_a=pedido, mid=9))
    # reaproveitar o mesmo pedido não grava de novo
    antes = gravados["t"]
    canal.receber(_msg("OUTRO-VALOR", resposta_a=pedido, mid=11))
    assert gravados["t"] == antes
    retornos.append(canal.status())
    assert segredo not in "".join(retornos) and "OUTRO-VALOR" not in "".join(retornos)
    assert all(segredo not in json.dumps(p) and "OUTRO-VALOR" not in json.dumps(p)
               for m, p in bot.chamadas if m != "deleteMessage")
    for mid in (9, 11):
        assert ("deleteMessage", {"chat_id": "4242", "message_id": mid}) in bot.chamadas
    saida = capsys.readouterr()
    assert segredo not in saida.out + saida.err


def test_canal_falha_ao_gravar_nao_vaza_e_mantem_o_pedido(capsys):
    segredo = "S3GREDO-NO-ERRO"

    class Quebrado:
        quebrar = True

        def ler(self):
            return MODELO

        def editar(self, chave, valor):
            texto = definir(MODELO, chave, valor)
            if self.quebrar:
                raise RuntimeError(f"falhou com {texto}")
            self.ok = texto
            return []

    vault, bot = Quebrado(), BotFalso()
    canal = CanalDeSegredos(bot, Config.do_ambiente(AMB), vault, chaves_do_modelo(MODELO), Relogio())
    canal.pedir("a")
    pedido = bot.n
    canal.receber(_msg(segredo, resposta_a=pedido, mid=9))
    assert ("deleteMessage", {"chat_id": "4242", "message_id": 9}) in bot.chamadas
    assert all(segredo not in json.dumps(p) for m, p in bot.chamadas if m != "deleteMessage")
    assert "a: gravada" not in canal.status() and "a: pendente" in canal.status()
    saida = capsys.readouterr()
    assert segredo not in saida.out + saida.err
    vault.quebrar = False                                                  # pode tentar de novo no mesmo pedido
    canal.receber(_msg(segredo, resposta_a=pedido, mid=12))
    assert yaml.safe_load(vault.ok)["a"] == segredo and "a: gravada" in canal.status()


def test_canal_pedir_sem_telegram_recusa():
    class BotQuebrado:
        def chamar(self, metodo, params, timeout=15):
            raise OSError("Telegram sendMessage: HTTP 500")

    vault = VaultFalso(MODELO, {})
    canal = CanalDeSegredos(BotQuebrado(), Config.do_ambiente(AMB), vault, {"a"}, Relogio())
    with pytest.raises(Recusado):
        canal.pedir("a")
    assert "pendente" not in canal.status()


class TelegramFalso:
    def __init__(self, updates):
        self.offset = 0
        self.tratados = []
        self.registro = SimpleNamespace(expirar=lambda: [])
        self.chamadas = []
        self.bot = SimpleNamespace(chamar=self._chamar)
        self._updates = updates

    def _chamar(self, metodo, params, timeout=15):
        self.chamadas.append((metodo, params, timeout))
        return self._updates

    def tratar(self, update):
        self.tratados.append(update)

    def atualizar(self, p):
        pass


def test_leitor_despacha_cliques_e_mensagens(capsys):
    clique = {"update_id": 5, "callback_query": {"id": "c", "data": "a:1"}}
    texto = _msg("SEGREDO-DO-LEITOR")
    texto["update_id"] = 6
    outro = {"update_id": 7, "edited_message": {"text": "ignorado"}}
    tg = TelegramFalso([clique, texto, outro])
    recebidos = []
    canal = SimpleNamespace(receber=recebidos.append)
    Leitor(tg, canal).ler(timeout=3)
    metodo, params, timeout = tg.chamadas[0]
    assert metodo == "getUpdates" and params["allowed_updates"] == ["callback_query", "message"]
    assert params["offset"] == 0 and params["timeout"] == 3 and timeout == 13
    assert tg.tratados == [clique] and recebidos == [texto] and tg.offset == 8


def test_leitor_falha_no_canal_nao_vaza_nem_trava(capsys):
    segredo = "SEGREDO-NA-EXCECAO"
    texto = _msg(segredo)

    def quebrar(update):
        raise RuntimeError(update["message"]["text"])

    tg = TelegramFalso([texto, {"update_id": 9, "callback_query": {"id": "c", "data": "a:1"}}])
    Leitor(tg, SimpleNamespace(receber=quebrar)).ler()
    assert tg.offset == 10 and len(tg.tratados) == 1       # o próximo update ainda é tratado
    saida = capsys.readouterr()
    assert segredo not in saida.out + saida.err


def test_leitor_rodar_expira_e_continua_apos_erro_de_rede(capsys):
    import threading
    parar = threading.Event()
    tg = TelegramFalso([])
    atualizados = []
    tg.registro = SimpleNamespace(expirar=lambda: [{"id": "p"}])
    tg.atualizar = atualizados.append
    chamadas = {"n": 0}

    def chamar(metodo, params, timeout=15):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise OSError("Telegram getUpdates: HTTP 502")
        parar.set()
        return []

    tg.bot = SimpleNamespace(chamar=chamar)
    esperas = []
    Leitor(tg, SimpleNamespace(receber=lambda u: None)).rodar(parar, espera=esperas.append)
    assert chamadas["n"] == 2 and esperas == [10] and atualizados == [{"id": "p"}]


def test_vault_gravado_legivel_pelo_sysadmin(tmp_path):
    Vault(_cfg_vault(tmp_path)).gravar("k: 1\n")
    assert (tmp_path / "saida/vault.yml").stat().st_mode & 0o777 == 0o644


def test_chave_so_no_modelo_recusa_no_pedido_e_descarta_na_resposta():
    vault_atual = 'a: "X"\n'                       # sem grupo.filho nem chave_ssh
    gravados = {}
    vault = VaultFalso(vault_atual, gravados)
    bot = BotFalso()
    canal = CanalDeSegredos(bot, Config.do_ambiente(AMB), vault, chaves_do_modelo(MODELO), Relogio())
    with pytest.raises(Recusado, match="vault atual"):
        canal.pedir("grupo.filho")
    assert bot.chamadas == []                         # Léo nem chega a ver o pedido
    canal.pedir("a")
    pedido = bot.n
    vault.texto = ""                                  # a chave some entre o pedido e a resposta
    canal.receber(_msg("VALOR", resposta_a=pedido, mid=9))
    assert gravados == {} and "a: pendente" not in canal.status()
    ultimo = bot.chamadas[-1][1]["text"]
    assert "não existe no vault" in ultimo and "de novo" not in ultimo and "VALOR" not in ultimo


def test_itens_de_lista_nao_sao_folhas_enderecaveis():
    real = (ROOT / "server/ansible/inventories/home/group_vars/all/vault.yml.example").read_text(encoding="utf-8")
    chaves = chaves_do_modelo(real)
    assert "restic_senha" in chaves
    assert not any(c.startswith("restic_repositorios") for c in chaves)
    for c in ("restic_repositorios.repositorio", "restic_repositorios.ambiente", "restic_repositorios.nome",
              "restic_repositorios.ambiente.AWS_ACCESS_KEY_ID"):
        with pytest.raises(KeyError):
            definir(real, c, "x")
    modelo = 'lista:\n  - nome: a\n    v: "1"\n  - nome: b\n    v: "2"\nvolta: "3"\n'
    assert chaves_do_modelo(modelo) == {"volta"}


class Resp:
    def __init__(self, corpo, status=200):
        self.corpo, self.status = corpo, status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.corpo


class GitHubFalso:
    def __init__(self, issues, comentarios, avulsas=None, status_post=200):
        self.issues, self.comentarios, self.avulsas, self.status_post = issues, comentarios, avulsas or {}, status_post
        self.posts, self.gets = [], []

    def __call__(self, req, timeout=15):
        url = req.full_url
        if req.get_method() == "POST":
            self.posts.append(req)
            return Resp(b'{"status":"ok"}', self.status_post)
        self.gets.append(req)
        if "/issues/comments" in url:
            corpo = self.comentarios
        elif "/issues?" in url:
            corpo = self.issues
        else:
            corpo = self.avulsas[int(url.rsplit("/", 1)[1])]
        return Resp(json.dumps(corpo).encode())


API = "https://api.github.com/repos/o/homeserver-equipe/issues/"


def _cart(tmp_path, gh, agora=2_000_000_000.0, desde="2026-11-09T00:00:00Z"):
    cfg = replace(Config.do_ambiente(AMB), dados_dir=str(tmp_path))
    if desde:
        (tmp_path / "carteiro.json").write_text(json.dumps({"desde": desde}))
    return Carteiro(cfg, gh, lambda: agora)


def test_carteiro_primeira_vez_nao_acorda(tmp_path):
    cfg = replace(Config.do_ambiente(AMB), dados_dir=str(tmp_path))
    gh = GitHubFalso([{"number": 1, "title": "velha", "labels": [{"name": "papel:sysadmin"}],
                       "user": {"login": "o"}, "html_url": "u"}], [])
    assert Carteiro(cfg, gh, lambda: 1_000.0).rodar_uma_vez() == 0 and gh.posts == []
    assert json.loads((tmp_path / "carteiro.json").read_text())["desde"] == "1970-01-01T00:16:40Z"


def test_carteiro_acorda_com_resposta_de_outro(tmp_path):
    cfg = replace(Config.do_ambiente(AMB), dados_dir=str(tmp_path))
    (tmp_path / "carteiro.json").write_text('{"desde": "2026-11-09T00:00:00Z"}')
    issues = [{"number": 2, "title": "pedido", "labels": [{"name": "papel:metricas"}], "user": {"login": "o-sysadmin"},
               "html_url": "https://g/2"},
              {"number": 3, "title": "incidente", "labels": [{"name": "papel:sysadmin"}], "user": {"login": "observador"},
               "html_url": "https://g/3", "created_at": "2026-11-09T01:00:00Z"}]
    comentarios = [{"issue_url": API + "2", "user": {"login": "metricas"}, "html_url": "https://g/2#c"},
                   {"issue_url": API + "2", "user": {"login": "o-sysadmin"}, "html_url": "https://g/2#d"}]
    gh = GitHubFalso(issues, comentarios)
    assert Carteiro(cfg, gh, lambda: 2_000_000_000.0).rodar_uma_vez() == 2
    req = gh.posts[0]
    ts = req.headers["X-webhook-timestamp"]
    assert req.headers["X-webhook-signature-v2"] == assinar("s", ts, req.data)
    assert req.headers["Content-type"] == "application/json" and req.full_url == AMB["WEBHOOK_URL"]
    corpo = json.loads(req.data)
    assert {i["numero"] for i in corpo["itens"]} == {2, 3} and "o-sysadmin" not in json.dumps(corpo)
    assert {i["tipo"] for i in corpo["itens"]} == {"comentario", "issue"}
    assert json.loads((tmp_path / "carteiro.json").read_text())["desde"] == "2033-05-18T03:33:20Z"
    auth = gh.gets[0]
    assert auth.headers["Authorization"] == "Bearer ghp" and auth.headers["X-github-api-version"] == "2022-11-28"
    assert "since=2026-11-09T00:00:00Z" in gh.gets[0].full_url


def test_assinar_e_hmac_sha256_de_ts_ponto_corpo():
    import hashlib
    import hmac
    assert assinar("s", "123", b'{"a":1}') == hmac.new(b"s", b'123.{"a":1}', hashlib.sha256).hexdigest()


def test_carteiro_comentario_em_issue_fora_da_pagina_busca_a_issue(tmp_path):
    avulsa = {"number": 9, "title": "antiga", "labels": [{"name": "papel:sysadmin"}], "user": {"login": "x"},
              "html_url": "https://g/9"}
    gh = GitHubFalso([], [{"issue_url": API + "9", "user": {"login": "metricas"}, "html_url": "https://g/9#c"}],
                     avulsas={9: avulsa})
    assert _cart(tmp_path, gh).rodar_uma_vez() == 1
    assert gh.gets[-1].full_url.endswith("/issues/9") and json.loads(gh.posts[0].data)["itens"][0]["numero"] == 9


def test_carteiro_ignora_pr_proprio_autor_e_issue_antiga(tmp_path):
    issues = [{"number": 4, "title": "pr", "labels": [{"name": "papel:sysadmin"}], "user": {"login": "a"},
               "html_url": "u", "created_at": "2026-11-09T01:00:00Z", "pull_request": {}},
              {"number": 5, "title": "minha", "labels": [{"name": "papel:sysadmin"}], "user": {"login": "o-sysadmin"},
               "html_url": "u", "created_at": "2026-11-09T01:00:00Z"},
              {"number": 6, "title": "antiga", "labels": [{"name": "papel:sysadmin"}], "user": {"login": "a"},
               "html_url": "u", "created_at": "2026-11-08T01:00:00Z"},
              {"number": 7, "title": "outra", "labels": [{"name": "papel:metricas"}], "user": {"login": "a"},
               "html_url": "u", "created_at": "2026-11-09T01:00:00Z"}]
    comentarios = [{"issue_url": API + "4", "user": {"login": "b"}, "html_url": "u"},
                   {"issue_url": API + "7", "user": {"login": "b"}, "html_url": "u"}]
    gh = GitHubFalso(issues, comentarios)
    assert _cart(tmp_path, gh).rodar_uma_vez() == 0 and gh.posts == []
    assert json.loads((tmp_path / "carteiro.json").read_text())["desde"] == "2033-05-18T03:33:20Z"


@pytest.mark.parametrize("status", [500, 302])
def test_carteiro_so_avanca_desde_com_post_2xx(tmp_path, status):
    issues = [{"number": 3, "title": "t", "labels": [{"name": "papel:sysadmin"}], "user": {"login": "a"},
               "html_url": "u", "created_at": "2026-11-09T01:00:00Z"}]
    gh = GitHubFalso(issues, [], status_post=status)
    assert _cart(tmp_path, gh).rodar_uma_vez() == 0
    assert json.loads((tmp_path / "carteiro.json").read_text())["desde"] == "2026-11-09T00:00:00Z"


def test_carteiro_erro_de_rede_nao_vaza_token_nem_avanca(tmp_path, capsys):
    import urllib.error

    def quebrado(req, timeout=15):
        raise urllib.error.HTTPError(req.full_url + "?t=ghp", 502, "x", {}, None)
    assert _cart(tmp_path, quebrado).rodar_uma_vez() == 0
    err = capsys.readouterr().err
    assert "502" in err and "ghp" not in err
    assert json.loads((tmp_path / "carteiro.json").read_text())["desde"] == "2026-11-09T00:00:00Z"


def _gh_issue_some(codigo):
    import urllib.error
    outro = {"number": 3, "title": "t", "labels": [{"name": "papel:sysadmin"}], "user": {"login": "a"},
             "html_url": "u", "created_at": "2026-11-09T01:00:00Z"}
    gh = GitHubFalso([outro], [{"issue_url": API + "8", "user": {"login": "b"}, "html_url": "u"}])
    base = gh.__call__

    def abrir(req, timeout=15):
        if req.get_method() == "GET" and req.full_url.endswith("/issues/8"):
            raise urllib.error.HTTPError(req.full_url, codigo, "x", {}, None)
        return base(req, timeout)
    return gh, abrir


def test_carteiro_pula_comentario_de_issue_apagada(tmp_path):
    gh, abrir = _gh_issue_some(404)
    assert _cart(tmp_path, abrir).rodar_uma_vez() == 1
    assert [i["numero"] for i in json.loads(gh.posts[0].data)["itens"]] == [3]
    assert json.loads((tmp_path / "carteiro.json").read_text())["desde"] == "2033-05-18T03:33:20Z"


def test_carteiro_500_na_issue_aborta_sem_avancar(tmp_path):
    gh, abrir = _gh_issue_some(500)
    assert _cart(tmp_path, abrir).rodar_uma_vez() == 0 and gh.posts == []
    assert json.loads((tmp_path / "carteiro.json").read_text())["desde"] == "2026-11-09T00:00:00Z"


# --- Task 8: ferramentas MCP, imagem e comando de preparo do host ---------------------------------------------

def _ferr(tmp_path, executar=lambda a, c, t: (0, "ok"), runner=None, canal=None):
    rel = Relogio(); reg = Registro(str(tmp_path / "p.json"), 1800, rel); avisos, ao_leo = [], []
    portao = Portao(reg, type("T", (), {"avisar": lambda s, p: avisos.append(p)})())
    (tmp_path / "id.pub").write_text("ssh-ed25519 AAAA sysadmin\n", encoding="utf-8")
    cfg = replace(Config.do_ambiente({**AMB, "EXECUTOR_REPO_DIR": str(tmp_path)}), chave_ssh=str(tmp_path / "id"),
                  saida_dir=str(tmp_path / "saida"))
    chamadas = []
    remoto = type("R", (), {"hosts": lambda s: {"core-services-vm"},
                            "rodar": lambda s, h, c, shell, become: chamadas.append((h, c, shell, become)) or executar(c, h, 0)})()
    (tmp_path / ".git").mkdir(exist_ok=True)
    f = ferramentas(cfg, portao, remoto, runner, canal, ao_leo.append)
    f["_chamadas"] = chamadas
    f["_cfg"] = cfg
    return f, reg, avisos, ao_leo


def test_nomes_e_destrutivas(tmp_path):
    f, *_ = _ferr(tmp_path)
    f.pop("_chamadas")
    f.pop("_cfg")
    assert set(f) == {"diagnostico", "comando", "playbooks_listar", "ansible_check", "ansible_aplicar",
                      "vault_preencher", "vault_status", "preparar_host"}
    assert {n for n, x in f.items() if x.destrutiva} == {"comando", "ansible_aplicar"}
    assert all(x.descricao for x in f.values())


def test_comando_passa_pelo_portao(tmp_path):
    f, reg, avisos, _ = _ferr(tmp_path)
    r = f["comando"].funcao("core-services-vm", "systemctl restart docker")
    assert "Aguardando" in r and avisos[0]["acao"] == "comando" and avisos[0]["argumentos"] == {
        "host": "core-services-vm", "comando": "systemctl restart docker"}
    assert f["_chamadas"] == []                       # nada rodou antes da aprovação
    reg.decidir(avisos[0]["id"], True, "telegram:leo")
    r = f["comando"].funcao("core-services-vm", "systemctl restart docker", aprovacao_id=avisos[0]["id"])
    assert r.endswith("ok") and f["_chamadas"] == [("core-services-vm", "systemctl restart docker", True, True)]


def test_comando_recusa_antes_de_pedir(tmp_path):
    f, reg, avisos, _ = _ferr(tmp_path)
    for host, cmd in [("core-services-vm", "x" * 251), ("core-services-vm", ""), ("outro", "ls"),
                      ("core-services-vm", "echo {{ lookup('file', '/segredos/vault_senha') }}")]:
        with pytest.raises(Recusado):
            f["comando"].funcao(host, cmd)
    assert avisos == [] and reg.listar() == []
    assert "Aguardando" in f["comando"].funcao("core-services-vm", "x" * 250)   # o limite é 250, inclusive


def test_diagnostico_sem_portao(tmp_path):
    f, _, avisos, _ = _ferr(tmp_path)
    assert f["diagnostico"].funcao("core-services-vm", "docker ps").endswith("ok")
    assert f["_chamadas"] == [("core-services-vm", ["docker", "ps"], False, True)] and avisos == []
    with pytest.raises(Recusado):
        f["diagnostico"].funcao("core-services-vm", "rm -rf /")
    assert len(f["_chamadas"]) == 1


class RunnerFalso:
    def __init__(self):
        self.chamadas = []
        self.plano = {"playbook": "setup-vpn.yml", "limite": None, "commit": "abcdef0123", "autor_assunto": "Ana <a@x>: muda",
                      "recap": "PLAY RECAP ok=3"}

    def check(self, playbook, limite=None):
        self.chamadas.append(("check", playbook, limite))
        return {"plano_id": "p1", "commit": "abcdef0123", "rc": 0, "autor_assunto": "Ana <a@x>: muda", "saida": "diff"}

    def ver(self, plano_id):
        return dict(self.plano) if plano_id == "p1" else None

    def aplicar(self, plano_id):
        self.chamadas.append(("aplicar", plano_id))
        return {"playbook": "setup-vpn.yml", "commit": "abcdef0123", "rc": 0, "saida": "feito"}


def test_ansible_check_e_aplicar_pelo_portao(tmp_path):
    runner = RunnerFalso()
    f, reg, avisos, _ = _ferr(tmp_path, runner=runner)
    assert not f["ansible_check"].destrutiva and "playbooks_listar" in f
    assert "setup-vpn.yml: VPN" in f["playbooks_listar"].funcao()
    with pytest.raises(Recusado):                      # fora de cfg.playbooks: nem chega a pedir
        f["ansible_check"].funcao("outro.yml")
    assert avisos == []
    assert "Aguardando" in f["ansible_check"].funcao("setup-vpn.yml", limite="pve")
    a = avisos[0]
    assert a["acao"] == "ansible_check" and a["alvo"] == "setup-vpn.yml" and "limite pve" in a["descricao"]
    assert runner.chamadas == []
    reg.decidir(a["id"], True, "telegram:leo")
    r = f["ansible_check"].funcao("setup-vpn.yml", limite="pve", aprovacao_id=a["id"])
    assert "plano_id: p1" in r and "commit: abcdef0123 (Ana <a@x>: muda)" in r and runner.chamadas == [("check", "setup-vpn.yml", "pve")]
    with pytest.raises(Recusado):                      # plano que não existe
        f["ansible_aplicar"].funcao("nada")
    assert "Aguardando" in f["ansible_aplicar"].funcao("p1")
    b = avisos[1]
    assert b["acao"] == "ansible_aplicar" and b["alvo"] == "p1"
    assert "abcdef01" in b["descricao"] and "Ana <a@x>: muda" in b["descricao"] and "PLAY RECAP ok=3" in b["descricao"]
    reg.decidir(b["id"], True, "telegram:leo")
    r = f["ansible_aplicar"].funcao("p1", aprovacao_id=b["id"])
    assert "feito" in r and runner.chamadas[-1] == ("aplicar", "p1")


def test_vault_preencher_e_status(tmp_path):
    pedidos = []
    canal = type("C", (), {"pedir": lambda s, c: pedidos.append(c) or "pedido enviado", "status": lambda s: "k: gravada"})()
    f, *_ = _ferr(tmp_path, canal=canal)
    assert f["vault_preencher"].funcao("k") == "pedido enviado" and pedidos == ["k"]
    assert "k: gravada" in f["vault_status"].funcao() and "não há" in f["vault_status"].funcao()
    (tmp_path / "saida").mkdir()
    (tmp_path / "saida/vault.yml").write_text("x", encoding="utf-8")
    assert "atualizado em 20" in f["vault_status"].funcao()


def test_preparar_host_vai_so_ao_leo(tmp_path):
    f, _, avisos, ao_leo = _ferr(tmp_path)
    r = f["preparar_host"].funcao()
    assert "tskey-h" not in r and "AAAA" not in r and r == "comando enviado ao Léo pelo bot de aprovações"
    assert "tskey-h" in ao_leo[0] and avisos == []
    assert ao_leo[0].startswith("curl -fsSL https://raw.githubusercontent.com/o/r/main/server/scripts/gcp/preparar-host.sh | bash -s -- ")
    assert "'proxmox_ansible_user'" in ao_leo[0] and "'ssh-ed25519 AAAA sysadmin'" in ao_leo[0]
    assert "'192.168.15.66/32,192.168.15.67/32,192.168.15.68/32'" in ao_leo[0] and "'tskey-h'" in ao_leo[0]


def test_preparar_host_falha_do_telegram_nao_vaza(tmp_path):
    f, *_ = _ferr(tmp_path)
    def falha(_):
        raise OSError("Telegram sendMessage: HTTP 500")
    rel = Relogio()
    portao = Portao(Registro(str(tmp_path / "q.json"), 1800, rel), type("T", (), {"avisar": lambda s, p: None})())
    cfg = replace(Config.do_ambiente({**AMB, "EXECUTOR_REPO_DIR": str(tmp_path)}), chave_ssh=str(tmp_path / "id"))
    g = ferramentas(cfg, portao, None, None, None, falha)
    with pytest.raises(Recusado) as e:
        g["preparar_host"].funcao()
    assert "tskey-h" not in str(e.value)


def test_manter_vivo_pega_excecao_e_continua(capsys):
    parar, chamadas, esperas = threading.Event(), [], []

    def alvo(p):
        chamadas.append(1)
        if len(chamadas) < 3:
            raise RuntimeError("segredo-no-erro")
        parar.set()
    parar.wait = lambda t=None: esperas.append(t) or False   # sem dormir de verdade
    manter_vivo("leitor", alvo, parar, 7)
    assert len(chamadas) == 3 and esperas == [7, 7]
    err = capsys.readouterr().err
    assert "leitor" in err and "RuntimeError" in err and "segredo-no-erro" not in err


def test_imagem_executor():
    d = (ROOT / "server/docker/images/executor/Dockerfile").read_text(encoding="utf-8")
    assert [l for l in d.splitlines() if l and not l.startswith("#")][0] == "FROM python:3.13-slim"
    for trecho in ("COPY ops /app/ops", "COPY aprovador /app/aprovador", "COPY executor /app/executor",
                   'ENTRYPOINT ["python", "-m", "executor"]', "useradd --uid ${UID} --gid ${GID}",
                   "ENV ANSIBLE_VAULT_PASSWORD_FILE=/segredos/vault_senha", "git openssh-client"):
        assert trecho in d
    assert d.index("COPY ops ") < d.index("COPY aprovador ") < d.index("COPY executor ")
    assert "ANSIBLE_HOST_KEY_CHECKING" not in d and "StrictHostKeyChecking" not in d
    assert "USER root" not in d.split("\nUSER ")[-1] and "\nUSER " in d
    assert (ROOT / "server/docker/images/executor/.dockerignore").read_text(encoding="utf-8").split() == [
        "**/__pycache__", "**/*.pyc"]


def test_preparar_host_sh():
    s = (ROOT / "server/scripts/gcp/preparar-host.sh").read_text(encoding="utf-8")
    assert s.startswith("#!/bin/bash") and "set -euo pipefail" in s
    for trecho in ("--advertise-tags=tag:homeserver", "--hostname=pve", "NOPASSWD: ALL", "authorized_keys",
                   "adduser --disabled-password", "/etc/sysctl.d/99-tailscale.conf", "--accept-dns=false"):
        assert trecho in s
    assert "set -x" not in s and "echo \"$CHAVE_TS" not in s


def test_preparar_host_sh_valida_argumentos():
    sh = str(ROOT / "server/scripts/gcp/preparar-host.sh")
    assert subprocess.run(["bash", "-n", sh]).returncode == 0
    for args in ([], ["a", "b", "c"], ["a", "b", "c", ""], ["a", "b", "c", "   "], ["a", "b", "c", "d", "e"],
                 ["a", "b", "root; rm -rf /", "d"]):
        r = subprocess.run(["bash", sh, *args], capture_output=True, text=True)
        assert r.returncode != 0 and "preparar-host" in r.stderr


@pytest.mark.parametrize("cmd", [
    'echo "' + 'a' * 20 + '" ' + '"x" ' * 55,                  # 250 caracteres, mas as aspas viram \" no JSON: passa de 300
    "echo " + "\\" * 200,                                    # barras invertidas dobram no JSON
    "ls \u202e/etc", "ls \u200b/etc", "ls \u2028 /etc", "ls\n/etc", "ls \x00", "ls \ufeff/etc", "ls \ue000"])
def test_comando_recusa_o_que_o_leo_nao_veria_inteiro(tmp_path, cmd):
    f, reg, avisos, _ = _ferr(tmp_path)
    assert len(cmd) <= 250
    with pytest.raises(Recusado):
        f["comando"].funcao("core-services-vm", cmd)
    assert avisos == [] and reg.listar() == []


def test_comando_cabe_em_300_apos_o_json(tmp_path):
    f, _, avisos, _ = _ferr(tmp_path)
    assert "Aguardando" in f["comando"].funcao("core-services-vm", "echo ação ok " + "x" * 200)
    assert len(json.dumps(avisos[0]["argumentos"], ensure_ascii=False)) <= 300


def test_preparar_host_sh_robusto():
    s = (ROOT / "server/scripts/gcp/preparar-host.sh").read_text(encoding="utf-8")
    assert "\nmain() {" in s and s.rstrip().endswith('main "$@"')                 # download truncado não roda pela metade
    assert "trap 'rm -f \"$TMP\"' EXIT" in s
    assert "command -v visudo" in s and "apt-get install -y sudo" in s
    assert 'id -gn "$USUARIO"' in s and "-g \"$GRUPO\"" in s
    assert "tail -c1" in s                                                         # newline final antes de acrescentar


def test_remoto_ignora_host_de_conexao_local(tmp_path):
    """R12: o sysadmin-gcp (ansible_connection=local) rodaria dentro do próprio executor, onde estão os segredos."""
    inv = tmp_path / "server/ansible/inventories/home"
    inv.mkdir(parents=True)
    (inv / "hosts.ini").write_text(
        "[core_services]\ncore-services-vm ansible_host=1.2.3.5\n[gcp]\nsysadmin-gcp ansible_connection=local\n"
        "[outro]\nh2 ansible_host=1.2.3.6 ansible_connection='local'\nh3 ansible_connection=ssh\n", encoding="utf-8")
    chamadas = []
    cfg = Config.do_ambiente({**AMB, "EXECUTOR_REPO_DIR": str(tmp_path)})
    r = Remoto(cfg, lambda argv, cwd, t: chamadas.append(argv) or (0, ""))
    assert r.hosts() == {"core-services-vm", "h3"}
    for host in ("sysadmin-gcp", "h2"):
        with pytest.raises(Recusado, match="inventário"):
            r.rodar(host, ["uptime"], shell=False, become=False)
    assert chamadas == []


def test_inventario_real_sem_host_local_no_executor():
    cfg = Config.do_ambiente({**AMB, "EXECUTOR_REPO_DIR": str(ROOT)})
    hosts = Remoto(cfg, lambda *a: (0, "")).hosts()
    assert "sysadmin-gcp" not in hosts and {"proxmox_main_host", "core-services-vm", "ai-desktop-vm"} <= hosts


# --- Revisão final do 5a ---

@pytest.mark.parametrize("limite", ["@/segredos/vault_senha", "core services", "core\nai", "core‮ia",
                                    "", "x" * 201, 5, "-e@/segredos/vault_senha", "--help", ",core", ":core"])
def test_ansible_check_recusa_limite_fora_do_padrao_antes_de_pedir(tmp_path, limite):
    """R19: `@arquivo` faria o Ansible ler um arquivo do executor como lista de hosts e devolver as linhas."""
    runner = RunnerFalso()
    f, reg, avisos, _ = _ferr(tmp_path, runner=runner)
    with pytest.raises(Recusado):
        f["ansible_check"].funcao("setup-vpn.yml", limite=limite)
    assert avisos == [] and reg.listar() == [] and runner.chamadas == []


@pytest.mark.parametrize("limite", ["core-services-vm", "core*:!ai", "proxmox_main_host,core-services-vm",
                                    "ubuntu_vms:&core_services", "x" * 200, None])
def test_ansible_check_aceita_padroes_de_host(tmp_path, limite):
    f, _, avisos, _ = _ferr(tmp_path, runner=RunnerFalso())
    assert "Aguardando" in f["ansible_check"].funcao("setup-vpn.yml", limite=limite)
    assert avisos[0]["argumentos"]["limite"] == limite


def _vault_main(tmp_path, texto: str):
    """Grava, como o PR mesclado faria, um vault cifrado no clone da main do executor."""
    import hashlib
    from ansible.parsing.vault import VaultLib, VaultSecret
    alvo = tmp_path / "server/ansible/inventories/home/group_vars/all/vault.yml"
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_bytes(VaultLib([("default", VaultSecret(b"s3nha"))]).encrypt(texto))
    return alvo, hashlib.sha256(alvo.read_bytes()).hexdigest()


def test_vault_base_ausente_quando_a_main_nao_tem_vault(tmp_path):
    v = Vault(_cfg_vault(tmp_path))
    v.gravar(v_texto := "k: 1\n")
    assert (tmp_path / "saida/.base").read_text(encoding="utf-8").split()[0] == "ausente"
    assert v.origem() == tmp_path / "saida/vault.yml" and v.ler() == v_texto


def test_vault_edicao_pendente_vale_enquanto_a_main_nao_muda(tmp_path):
    """R17: a base do saida/ é o vault da main de quando ele foi gravado; com a mesma main, vale o saida/."""
    cfg = _cfg_vault(tmp_path)
    main, sha = _vault_main(tmp_path, "k: main\n")
    v = Vault(cfg)
    assert v.origem() == main and v.ler() == "k: main\n"
    v.gravar(definir(v.ler(), "k", "editado"))
    assert (tmp_path / "saida/.base").read_text(encoding="utf-8").split()[0] == sha
    assert v.origem() == tmp_path / "saida/vault.yml" and v.ler() == 'k: "editado"\n'
    v.gravar(definir(v.ler(), "k", "de novo"))       # 2ª edição em cima da 1ª: a base continua a mesma main
    assert (tmp_path / "saida/.base").read_text(encoding="utf-8").split()[0] == sha and v.ler() == 'k: "de novo"\n'


def test_vault_main_mudou_volta_para_a_main(tmp_path):
    """R17: mesclado o PR (ou a main mudou por outro caminho), o saida/ velho não sobrescreve a main."""
    cfg = _cfg_vault(tmp_path)
    _vault_main(tmp_path, "k: main\n")
    v = Vault(cfg)
    v.gravar(definir(v.ler(), "k", "editado"))
    main, _ = _vault_main(tmp_path, "k: mesclado\n")
    assert v.origem() == main and v.ler() == "k: mesclado\n"
    v.gravar(definir(v.ler(), "k", "novo"))           # a próxima edição parte da main nova
    assert v.origem().parent.name == "saida" and v.ler() == 'k: "novo"\n'


def test_vault_sem_base_usa_a_main_se_existir(tmp_path):
    """O saida/vault.yml semeado do bucket (entrada/) não tem .base: com vault na main, a main manda."""
    cfg = _cfg_vault(tmp_path)
    Vault(cfg).gravar("k: entrada\n")
    (tmp_path / "saida/.base").unlink()
    v = Vault(cfg)
    assert v.origem() == tmp_path / "saida/vault.yml" and v.ler() == "k: entrada\n"   # main sem vault: vale o saida
    main, _ = _vault_main(tmp_path, "k: main\n")
    assert v.origem() == main and v.ler() == "k: main\n"


def test_vault_main_que_sumiu_depois_da_base_nao_promove_o_saida(tmp_path):
    """A main some no meio de um git pull (ou o clone estragou): um saida/ baseado nela não pode virar "pendente"."""
    from executor.vault import VaultIndisponivel
    cfg = _cfg_vault(tmp_path)
    main, _ = _vault_main(tmp_path, "k: main\n")
    v = Vault(cfg)
    v.editar("k", "editado")
    main.unlink()
    for chamada in (v.situacao, v.ler, lambda: v.editar("k", "outro")):
        with pytest.raises(VaultIndisponivel):
            chamada()
    _vault_main(tmp_path, "k: main\n")                 # o pull terminou: tudo volta ao normal
    assert v.origem().parent.name == "saida" and yaml.safe_load(v.ler()) == {"k": "editado"}


def test_vault_sem_main_e_sem_clone_nao_vale(tmp_path):
    from executor.vault import VaultIndisponivel
    cfg = _cfg_vault(tmp_path)
    Vault(cfg).gravar('k: "entrada"\n')
    (tmp_path / ".git").rmdir()                        # clone ausente: a falta de vault.yml não quer dizer nada
    with pytest.raises(VaultIndisponivel):
        Vault(cfg).situacao()


def test_vault_status_diz_se_o_saida_esta_superado_pela_main(tmp_path):
    """R17: o sysadmin abre o PR do vault com /saida/vault.yml; um saida/ superado pela main não pode virar PR."""
    canal = type("C", (), {"pedir": lambda s, c: "", "status": lambda s: "nada"})()
    f, *_ = _ferr(tmp_path, canal=canal)
    (tmp_path / "saida").mkdir()
    (tmp_path / "saida/vault.yml").write_text("x", encoding="utf-8")
    r = f["vault_status"].funcao()                                    # main sem vault: o saida é o que vale
    assert "pendentes sobre a main (base ausente)" in r and "não abra o PR do vault agora" in r   # sem runner
    _vault_main(tmp_path, "k: main\n")
    r = f["vault_status"].funcao()                                    # entrada sem .base: superada e encerrada
    assert "nenhuma edição pendente" in r and not (tmp_path / "saida/vault.yml").exists()


def test_vault_reaplica_edicoes_feitas_depois_do_pr(tmp_path):
    """O PR do vault levou `a`; `b` foi preenchida depois de aberto o PR, antes do executor ver a main nova: não se perde."""
    cfg = _cfg_vault(tmp_path)
    _vault_main(tmp_path, 'a: "x"\nb: "y"\nc: "z"\n')
    v = Vault(cfg)
    assert v.editar("a", "A") == []                   # vai no PR
    assert v.editar("b", "B") == []                   # preenchida com o PR já aberto
    _vault_main(tmp_path, 'a: "A"\nb: "y"\nc: "z"\n')  # PR mesclado só com `a`
    assert v.situacao() == (tmp_path / "saida/vault.yml", [])
    assert yaml.safe_load(v.ler()) == {"a": "A", "b": "B", "c": "z"}
    main = tmp_path / "server/ansible/inventories/home/group_vars/all/vault.yml"
    sha = __import__("hashlib").sha256(main.read_bytes()).hexdigest()
    assert (tmp_path / "saida/.base").read_text(encoding="utf-8").split()[0] == sha   # gravado sobre a main nova
    _vault_main(tmp_path, 'a: "A"\nb: "B"\nc: "z"\n')  # 2º PR mesclado: nada pendente
    assert v.situacao() == (main, [])


def test_vault_conflito_quando_a_main_tambem_mudou_a_chave(tmp_path):
    cfg = _cfg_vault(tmp_path)
    _vault_main(tmp_path, 'a: "x"\nb: "y"\n')
    v = Vault(cfg)
    v.editar("a", "LEO")
    v.editar("b", "B")
    main, _ = _vault_main(tmp_path, 'a: "OUTRA"\nb: "y"\n')   # outro caminho mudou `a`
    arquivo, conflitos = v.situacao()
    assert conflitos == ["a"] and arquivo.parent.name == "saida"
    assert yaml.safe_load(v.ler()) == {"a": "OUTRA", "b": "B"}  # vale a main em `a`; `b` reaplicada
    assert (tmp_path / "saida/.conflitos").read_text(encoding="utf-8").split() == ["a"]
    assert "LEO" not in (tmp_path / "saida/.conflitos").read_text(encoding="utf-8")
    assert v.editar("b", "B2") == ["a"]              # o Léo é avisado na próxima gravação, uma vez só
    assert v.editar("b", "B3") == [] and v.situacao()[1] == ["a"]    # o vault_status continua mostrando
    assert v.editar("a", "LEO2") == [] and v.situacao()[1] == []     # preenchida de novo: deixa de ser conflito


def test_vault_da_entrada_ate_o_primeiro_pr(tmp_path):
    """Fase 1: o saida/ é a entrada do bucket (sem .base); o 1º PR leva `a`, `b` vem depois e é reaplicada."""
    cfg = _cfg_vault(tmp_path)
    Vault(cfg).gravar('a: "x"\nb: "y"\n')
    for nome in (".base", ".base.yml"):
        (tmp_path / "saida" / nome).unlink(missing_ok=True)   # como o semeado do bucket
    v = Vault(cfg)
    v.editar("a", "A")
    v.editar("b", "B")
    _vault_main(tmp_path, 'a: "A"\nb: "y"\n')
    assert yaml.safe_load(v.ler()) == {"a": "A", "b": "B"} and v.origem().parent.name == "saida"


def test_vault_entrada_velha_sem_edicoes_nao_sobrescreve_a_main(tmp_path):
    cfg = _cfg_vault(tmp_path)
    Vault(cfg).gravar('a: "entrada"\n')
    for nome in (".base", ".base.yml"):
        (tmp_path / "saida" / nome).unlink(missing_ok=True)
    main, _ = _vault_main(tmp_path, 'a: "main"\n')
    assert Vault(cfg).situacao() == (main, []) and Vault(cfg).ler() == 'a: "main"\n'


def test_vault_base_antiga_de_uma_linha_volta_para_a_main(tmp_path):
    cfg = _cfg_vault(tmp_path)
    _vault_main(tmp_path, 'a: "x"\n')
    v = Vault(cfg)
    v.editar("a", "A")
    base = (tmp_path / "saida/.base").read_text(encoding="utf-8").split()[0]
    (tmp_path / "saida/.base").write_text(base + "\n", encoding="utf-8")   # formato anterior, sem ancestral
    main, _ = _vault_main(tmp_path, 'a: "y"\n')
    assert v.situacao() == (main, [])


def test_vault_ancestral_adulterado_nao_vale(tmp_path):
    cfg = _cfg_vault(tmp_path)
    _vault_main(tmp_path, 'a: "x"\nb: "y"\n')
    v = Vault(cfg)
    v.editar("b", "B")
    (tmp_path / "saida/.base.yml").write_bytes(b"outro")
    main, _ = _vault_main(tmp_path, 'a: "x2"\nb: "y"\n')
    assert v.situacao() == (main, [])


def test_vault_editar_grava_a_base_do_texto_lido(tmp_path):
    """A corrida antiga: a base gravada é sempre a do texto editado, sob a mesma trava, mesmo com leituras em paralelo."""
    import threading
    cfg = _cfg_vault(tmp_path)
    _vault_main(tmp_path, 'a: "x"\nb: "y"\n')
    v = Vault(cfg)
    fios = [threading.Thread(target=v.ler) for _ in range(8)] + [threading.Thread(target=v.editar, args=("a", "A"))]
    for f in fios:
        f.start()
    for f in fios:
        f.join()
    leitura = v.ler_com_base()
    linhas = (tmp_path / "saida/.base").read_text(encoding="utf-8").split()
    assert linhas[0] == leitura.base and yaml.safe_load(leitura.texto)["a"] == "A"
    assert linhas[1] == __import__("hashlib").sha256((tmp_path / "saida/.base.yml").read_bytes()).hexdigest()


def test_canal_avisa_os_conflitos_sem_valores():
    class ComConflito(VaultFalso):
        def editar(self, chave, valor):
            super().editar(chave, valor)
            return ["grupo.filho"]

    bot = BotFalso()
    canal = CanalDeSegredos(bot, Config.do_ambiente(AMB), ComConflito(MODELO, {}), chaves_do_modelo(MODELO), Relogio())
    canal.pedir("a")
    canal.receber(_msg("VALOR", resposta_a=bot.n, mid=9))
    avisos = [p["text"] for m, p in bot.chamadas if m == "sendMessage"]
    assert "grupo.filho" in avisos[-1] and "vale a main" in avisos[-1] and all("VALOR" not in a for a in avisos)


def test_vault_status_atualiza_a_main_antes(tmp_path):
    ordem = []

    class R:
        def atualizar(self):
            ordem.append("pull")
            return "abcdef0123"

    canal = type("C", (), {"pedir": lambda s, c: "", "status": lambda s: ordem.append("status") or "nada"})()
    f, *_ = _ferr(tmp_path, runner=R(), canal=canal)
    r = f["vault_status"].funcao()
    assert ordem[0] == "pull" and "atualizada (abcdef01)" in r

    class Ocupado:
        def atualizar(self):
            raise Recusado("outra execução em andamento; tente de novo quando ela terminar")

    f, *_ = _ferr(tmp_path, runner=Ocupado(), canal=canal)
    (tmp_path / "saida").mkdir(exist_ok=True)
    (tmp_path / "saida/vault.yml").write_text("x", encoding="utf-8")   # pendente (main sem vault)
    r = f["vault_status"].funcao()
    assert "pode estar atrasado" in r and "não abra o PR do vault agora" in r and "abra o PR do vault com" not in r

    class Quebrado:
        def atualizar(self):
            raise OSError("git ausente")

    f, *_ = _ferr(tmp_path, runner=Quebrado(), canal=canal)
    assert "OSError" in f["vault_status"].funcao()


# --- Revisão das pendências: histórico do vault na main (git de verdade) ---

def _git_main(tmp_path):
    """Clone de verdade: cada _vault_main seguido de commit, como um PR mesclado e puxado pelo executor."""
    import subprocess
    if shutil.which("git") is None:
        pytest.skip("git ausente")
    cfg = _cfg_vault(tmp_path)
    (tmp_path / ".git").rmdir()
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q", "-b", "main"], check=True)

    def commit(texto, msg):
        _vault_main(tmp_path, texto)
        subprocess.run(["git", "-C", str(tmp_path), "add", "server"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                        "-m", msg], check=True)
    return cfg, commit


def test_vault_revert_do_pr_nao_ressuscita_o_saida(tmp_path):
    """ABA: o PR levou `a`, o executor não leu a main do merge, e a main voltou `a` ao valor antigo (revert):
    o saida/ não pode voltar a ser "pendente" (o PR seguinte desfaria o revert)."""
    cfg, commit = _git_main(tmp_path)
    commit('a: "x"\nb: "y"\n', "vault")
    v = Vault(cfg)
    v.editar("a", "A")
    commit('a: "A"\nb: "y"\n', "PR do vault")       # mesclado e puxado, sem leitura do executor no meio
    commit('a: "x"\nb: "y"\n', "revert")            # mesmo conteúdo da base, byte a byte não importa
    main = tmp_path / "server/ansible/inventories/home/group_vars/all/vault.yml"
    assert v.situacao() == (main, []) and not (tmp_path / "saida/vault.yml").exists()


def test_vault_rotacao_depois_do_merge_nao_e_conflito(tmp_path):
    cfg, commit = _git_main(tmp_path)
    commit('a: "x"\nb: "y"\n', "vault")
    v = Vault(cfg)
    v.editar("a", "A")
    v.editar("b", "B")                                 # preenchida com o PR (só de `a`) já aberto
    commit('a: "A"\nb: "y"\n', "PR do vault")
    commit('a: "A2"\nb: "y"\n', "rotação de a")
    arquivo, conflitos = v.situacao()
    assert conflitos == [] and arquivo.parent.name == "saida"           # `a` já foi mesclada: vale a main
    assert yaml.safe_load(v.ler()) == {"a": "A2", "b": "B"}


def test_vault_mesmo_conteudo_com_historia_nova_reaplica_pelo_historico(tmp_path):
    cfg, commit = _git_main(tmp_path)
    commit('a: "x"\nb: "y"\n', "vault")
    v = Vault(cfg)
    v.editar("b", "B")
    commit('a: "z"\nb: "y"\n', "outro PR")
    commit('a: "x"\nb: "y"\n', "volta")             # bytes iguais aos da base, mas outra história
    arquivo, _ = v.situacao()
    assert arquivo.parent.name == "saida" and yaml.safe_load(v.ler()) == {"a": "x", "b": "B"}


def test_vault_edicao_igual_a_main_nao_fica_pendente(tmp_path):
    cfg = _cfg_vault(tmp_path)
    main, _ = _vault_main(tmp_path, 'a: "x"\n')
    v = Vault(cfg)
    v.editar("a", "x")
    assert v.situacao() == (main, []) and not (tmp_path / "saida/vault.yml").exists()


def test_vault_fase_1_o_base_vai_antes_do_vault(tmp_path, monkeypatch):
    """Sem main, uma queda entre os dois arquivos não pode deixar o vault.yml editado sem .base (ele viraria o
    ancestral e a edição deixaria de ser "nossa")."""
    cfg = _cfg_vault(tmp_path)
    Vault(cfg).gravar('a: "x"\n')
    for nome in (".base", ".base.yml"):
        (tmp_path / "saida" / nome).unlink(missing_ok=True)
    v = Vault(cfg)
    ordem = []
    original = v._gravar_atomico
    monkeypatch.setattr(v, "_gravar_atomico", lambda d, b: ordem.append(d.name) or original(d, b))
    v.editar("a", "A")
    assert ordem.index(".base") < ordem.index("vault.yml")
