"""Executor do sysadmin (sub-projeto 5a, página 19): configuração, portão de aprovação e comandos remotos."""
from __future__ import annotations

import json
import sys
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
from executor.config import Config, ConfigInvalida  # noqa: E402
from executor.portao import Portao  # noqa: E402
from executor.leitor import Leitor  # noqa: E402
from executor.remoto import Remoto, validar_diagnostico  # noqa: E402
from executor.segredos import CanalDeSegredos  # noqa: E402
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
    assert sorted(p.name for p in (tmp_path / "saida").iterdir()) == ["vault.yml"]  # sem temporários nem texto puro
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


def test_canal_de_segredos(tmp_path):
    gravados = {}
    vault = type("V", (), {"ler": lambda s: MODELO, "gravar": lambda s, t: gravados.update(t=t)})()
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
    vault = type("V", (), {"ler": lambda s: MODELO, "gravar": lambda s, t: gravados.update(t=t)})()
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

        def gravar(self, texto):
            if self.quebrar:
                raise RuntimeError(f"falhou com {texto}")
            self.ok = texto

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

    vault = SimpleNamespace(ler=lambda: MODELO, gravar=lambda t: None)
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
    vault = SimpleNamespace(ler=lambda: vault_atual, gravar=lambda t: gravados.update(t=t))
    bot = BotFalso()
    canal = CanalDeSegredos(bot, Config.do_ambiente(AMB), vault, chaves_do_modelo(MODELO), Relogio())
    with pytest.raises(Recusado, match="vault atual"):
        canal.pedir("grupo.filho")
    assert bot.chamadas == []                         # Léo nem chega a ver o pedido
    canal.pedir("a")
    pedido = bot.n
    vault_atual = ""                                  # a chave some entre o pedido e a resposta
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
