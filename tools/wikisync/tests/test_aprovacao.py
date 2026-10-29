"""Aprovação humana dos agentes autônomos (sub-projeto 4c3, página 16): o aprovador (registro, Telegram, API e
tela) e o fluxo no ops, de ponta a ponta, com o aprovador de verdade num servidor local e um Telegram falso."""
from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from test_observabilidade import ROOT

sys.path.insert(0, str(ROOT / "server/docker/images/aprovador"))
sys.path.insert(0, str(ROOT / "server/docker/images/ops"))
sys.dont_write_bytecode = True  # sem __pycache__ em docker/images (o copy do playbook o levaria)

from aprovador.config import Config, ConfigInvalida  # noqa: E402
from aprovador.pedidos import Conflito, Registro  # noqa: E402
from aprovador.servidor import fazer_handler  # noqa: E402
from aprovador.telegram import Telegram, texto_do_pedido  # noqa: E402
from ops.aprovacao import Aprovador  # noqa: E402
from ops.config import Config as ConfigOps  # noqa: E402
from ops.ferramentas import ferramentas  # noqa: E402
from ops.politica import Recusado  # noqa: E402
from ops.portainer import Portainer  # noqa: E402
from test_ops import AMBIENTE as AMBIENTE_OPS, PortainerFalso  # noqa: E402

AMBIENTE = {"APROVADOR_TOKEN": "tok-ops", "APROVADOR_CHAVE_PROXY": "chave-traefik",
            "APROVADOR_URL_PUBLICA": "https://aprovacoes.exemplo.com", "TELEGRAM_BOT_TOKEN": "123:abc",
            "TELEGRAM_CHAT_ID": "4242"}


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# --- Configuração e registro ---

def test_config():
    c = Config.do_ambiente(AMBIENTE)
    assert c.usuarios == {"4242"} and c.validade_s == 1800 and c.porta == 8080
    with pytest.raises(ConfigInvalida, match="APROVADOR_CHAVE_PROXY"):
        Config.do_ambiente({**AMBIENTE, "APROVADOR_CHAVE_PROXY": ""})
    # Num grupo (id negativo), o id do chat não é de ninguém: precisa da lista de usuários.
    with pytest.raises(ConfigInvalida, match="ninguém pode decidir"):
        Config.do_ambiente({**AMBIENTE, "TELEGRAM_CHAT_ID": "-100123"})
    assert Config.do_ambiente({**AMBIENTE, "TELEGRAM_CHAT_ID": "-100123",
                               "APROVADOR_TELEGRAM_USUARIOS": "7, 8"}).usuarios == {"7", "8"}


def test_registro_ciclo_e_persistencia(tmp_path, capsys):
    rel = Relogio()
    arq = str(tmp_path / "pedidos.json")
    r = Registro(arq, 1800, rel)
    p = r.criar("agentes", "container_reiniciar", "jellyfin", {"nome": "jellyfin", "vm": None}, "reiniciar")
    assert p["estado"] == "pendente" and len(p["id"]) == 8
    with pytest.raises(Conflito, match="pedido pendente"):
        r.usar(p["id"], "container_reiniciar", "jellyfin", {"nome": "jellyfin", "vm": None})
    r.decidir(p["id"], True, "tela:leo")
    with pytest.raises(Conflito, match="já está aprovado"):
        r.decidir(p["id"], False, "x")
    with pytest.raises(Conflito, match="outra ação"):
        r.usar(p["id"], "container_reiniciar", "traefik", {"nome": "traefik", "vm": None})
    # Sobrevive a um reinício (arquivo no disco) e só vale uma vez.
    r2 = Registro(arq, 1800, rel)
    assert r2.usar(p["id"], "container_reiniciar", "jellyfin", {"nome": "jellyfin", "vm": None})["estado"] == "usado"
    with pytest.raises(Conflito, match="pedido usado"):
        r2.usar(p["id"], "container_reiniciar", "jellyfin", {"nome": "jellyfin", "vm": None})
    eventos = [json.loads(l)["acao_registro"] for l in capsys.readouterr().out.splitlines()]
    assert eventos == ["criado", "aprovado", "usado"]


def test_registro_expira(tmp_path):
    rel = Relogio()
    r = Registro(str(tmp_path / "p.json"), 1800, rel)
    pendente = r.criar("agentes", "a", "b", {}, "")
    aprovado = r.criar("agentes", "a", "c", {}, "")
    r.decidir(aprovado["id"], True, "x")
    rel.t += 1801
    assert {p["id"] for p in r.expirar()} == {pendente["id"], aprovado["id"]}
    with pytest.raises(Conflito, match="já está expirado"):
        r.decidir(pendente["id"], True, "x")
    with pytest.raises(Conflito, match="pedido expirado"):
        r.usar(aprovado["id"], "a", "c", {})


def test_registro_arquivo_ilegivel_nao_derruba(tmp_path):
    arq = tmp_path / "p.json"
    arq.write_text("{quebrado", encoding="utf-8")
    assert Registro(str(arq), 1800).listar() == []


# --- Telegram ---

class BotFalso:
    def __init__(self, updates=None):
        self.chamadas: list[tuple[str, dict]] = []
        self.updates = list(updates or [])

    def chamar(self, metodo, params, timeout=15):
        self.chamadas.append((metodo, params))
        if metodo == "sendMessage":
            return {"message_id": 77}
        if metodo == "getUpdates":
            atuais, self.updates = self.updates, []
            return atuais
        return True


def _clique(pid, dado="a", quem=4242, chat=4242, uid=1):
    return {"update_id": uid, "callback_query": {"id": f"cb{uid}", "data": f"{dado}:{pid}",
                                                 "from": {"id": quem, "username": "leo"},
                                                 "message": {"chat": {"id": chat}}}}


def test_telegram_avisa_e_aplica_cliques(tmp_path):
    r = Registro(str(tmp_path / "p.json"), 1800)
    p = r.criar("agentes", "stack_redeploy", "media", {"nome": "media", "puxar_imagens": False}, "redeploy <b>")
    bot = BotFalso()
    tg = Telegram(bot, r, "4242", frozenset({"4242"}), "https://aprovacoes.exemplo.com")
    tg.avisar(p)
    metodo, params = bot.chamadas[0]
    assert metodo == "sendMessage" and params["chat_id"] == "4242" and params["parse_mode"] == "HTML"
    assert params["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"a:{p['id']}"
    assert "&lt;b&gt;" in params["text"]  # descrição escapada (vem do agente)
    assert r.obter(p["id"])["mensagem_telegram"] == 77
    # Clique de outra pessoa (num grupo, por exemplo) não decide nada.
    bot.updates = [_clique(p["id"], quem=999, uid=5), _clique(p["id"], chat=-1, uid=6)]
    tg.ler()
    assert r.obter(p["id"])["estado"] == "pendente" and tg.offset == 7
    assert [c[1]["text"] for c in bot.chamadas if c[0] == "answerCallbackQuery"] == ["Sem permissão."] * 2
    bot.updates = [_clique(p["id"], "r", uid=9)]
    tg.ler()
    assert r.obter(p["id"])["estado"] == "recusado" and r.obter(p["id"])["decidido_por"] == "telegram:leo"
    edicao = next(c for c in bot.chamadas if c[0] == "editMessageText")[1]
    assert edicao["message_id"] == 77 and "Recusado" in edicao["text"]
    assert "Sem decisão" not in texto_do_pedido(r.obter(p["id"]), "x")


def test_telegram_fora_nao_impede_o_pedido(tmp_path):
    class BotQuebrado(BotFalso):
        def chamar(self, metodo, params, timeout=15):
            raise OSError("Telegram sendMessage: HTTP 401")
    r = Registro(str(tmp_path / "p.json"), 1800)
    p = r.criar("agentes", "a", "b", {}, "")
    Telegram(BotQuebrado(), r, "4242", frozenset({"4242"}), "u").avisar(p)
    assert r.obter(p["id"])["estado"] == "pendente"  # segue na tela


# --- HTTP: API do ops e tela ---

@pytest.fixture
def servidor(tmp_path):
    cfg = Config.do_ambiente({**AMBIENTE, "APROVADOR_DADOS": str(tmp_path / "p.json")})
    registro = Registro(cfg.dados, cfg.validade_s)
    bot = BotFalso()
    tg = Telegram(bot, registro, cfg.chat_id, cfg.usuarios, cfg.url_publica)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), fazer_handler(cfg, registro, tg))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", registro, bot
    srv.shutdown()


def _req(url, metodo="GET", corpo=None, cab=None, form=False):
    dados = None
    if corpo is not None:
        dados = urllib.parse.urlencode(corpo).encode() if form else json.dumps(corpo).encode()
    req = urllib.request.Request(url, data=dados, method=metodo, headers=cab or {})

    class SemRedirecionar(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    try:
        with urllib.request.build_opener(SemRedirecionar).open(req, timeout=5) as r:
            return r.status, r.read().decode(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), dict(e.headers)


TELA = {"X-Aprovador-Chave": "chave-traefik", "Remote-User": "leo"}


def test_api_e_tela(servidor):
    base, registro, bot = servidor
    api = {"Authorization": "Bearer tok-ops", "Content-Type": "application/json"}
    assert _req(base + "/api/pedidos", "POST", {"cliente": "a"}, {"Authorization": "Bearer errado"})[0] == 401
    assert _req(base + "/api/pedidos", "POST", {"cliente": "agentes"}, api)[0] == 400
    codigo, corpo, _ = _req(base + "/api/pedidos", "POST", {"cliente": "agentes", "acao": "container_reiniciar",
                                                           "alvo": "jellyfin", "argumentos": {"nome": "jellyfin"}}, api)
    assert codigo == 201
    pid = json.loads(corpo)["id"]
    assert bot.chamadas[0][0] == "sendMessage"
    # A tela só responde pelo Traefik (chave do proxy) e com o usuário do Authelia.
    assert _req(base + "/")[0] == 403
    assert _req(base + "/", cab={"Remote-User": "leo"})[0] == 403
    codigo, html_, _ = _req(base + "/", cab=TELA)
    assert codigo == 200 and pid in html_ and "Aprovar" in html_
    # POST sem a origem da própria tela (outra página no navegador) é recusado.
    assert _req(base + "/decidir", "POST", {"id": pid, "decisao": "aprovar"}, {**TELA, "Origin": "https://mal.com"},
                form=True)[0] == 403
    codigo, _, cab = _req(base + "/decidir", "POST", {"id": pid, "decisao": "aprovar"},
                          {**TELA, "Origin": "https://aprovacoes.exemplo.com"}, form=True)
    assert codigo == 303 and "aprovado" in urllib.parse.unquote(cab["Location"])
    assert registro.obter(pid)["decidido_por"] == "tela:leo"
    assert any(c[0] == "editMessageText" for c in bot.chamadas)  # a mensagem do Telegram acompanha
    usar = base + f"/api/pedidos/{pid}/usar"
    assert _req(usar, "POST", {"acao": "container_reiniciar", "alvo": "jellyfin", "argumentos": {"nome": "x"}}, api)[0] == 409
    assert _req(usar, "POST", {"acao": "container_reiniciar", "alvo": "jellyfin", "argumentos": {"nome": "jellyfin"}}, api)[0] == 200
    assert json.loads(_req(base + f"/api/pedidos/{pid}", cab=api)[1])["estado"] == "usado"


# --- O fluxo no ops, com o aprovador de verdade ---

def _ops(base, cliente):
    cfg = ConfigOps.do_ambiente({**AMBIENTE_OPS, "APROVADOR_URL": base, "APROVADOR_TOKEN": "tok-ops"})
    falso = PortainerFalso()
    fs = ferramentas(cfg, Portainer(cfg, falso), None, None, cliente=lambda: cliente)
    return fs, falso


def test_ops_agente_autonomo_precisa_de_aprovacao(servidor, capsys):
    base, registro, _ = servidor
    fs, falso = _ops(base, "agentes")
    texto = fs["container_reiniciar"].funcao(nome="jellyfin")
    assert texto.startswith("Aguardando aprovação humana: pedido ")
    pid = texto.split("pedido ")[1].split(".")[0]
    assert not any(m == "POST" for m, _, _ in falso.chamadas)  # nada reiniciado ainda
    with pytest.raises(Recusado, match="pedido pendente"):
        fs["container_reiniciar"].funcao(nome="jellyfin", aprovacao_id=pid)
    registro.decidir(pid, True, "telegram:leo")
    with pytest.raises(Recusado, match="outra ação"):  # o pedido aprovado não serve para outro container
        fs["container_reiniciar"].funcao(nome="litellm_proxy", aprovacao_id=pid)
    assert fs["container_reiniciar"].funcao(nome="jellyfin", aprovacao_id=pid) == "container jellyfin reiniciado"
    assert ("POST", "/api/endpoints/1/docker/containers/c1/restart", None) in falso.chamadas
    with pytest.raises(Recusado, match="pedido usado"):  # uma vez só
        fs["container_reiniciar"].funcao(nome="jellyfin", aprovacao_id=pid)
    resultados = [json.loads(l).get("resultado") for l in capsys.readouterr().out.splitlines() if '"ops_acao"' in l]
    assert resultados[0] == "aguardando" and "ok" in resultados


def test_ops_protegido_nem_vira_pedido(servidor):
    base, registro, bot = servidor
    fs, _ = _ops(base, "assistente")
    with pytest.raises(Recusado, match="protegido"):
        fs["container_reiniciar"].funcao(nome="traefik")
    assert registro.listar() == [] and bot.chamadas == []


def test_ops_claude_code_nao_passa_pelo_aprovador(servidor):
    base, registro, _ = servidor
    fs, _ = _ops(base, "claude_code")
    assert fs["container_reiniciar"].funcao(nome="jellyfin") == "container jellyfin reiniciado"
    assert registro.listar() == []


def test_ops_aprovador_fora_falha_fechado():
    with pytest.raises(Recusado, match="inalcançável"):
        Aprovador("http://127.0.0.1:9", "t").pedir("agentes", "a", "b", {}, "")
    with pytest.raises(Recusado, match="não está configurado"):
        Aprovador("", "").pedir("agentes", "a", "b", {}, "")
    with pytest.raises(Recusado, match="inválido"):
        Aprovador("http://x", "t").usar("../../x", "a", "b", {})


def test_codigo_so_com_biblioteca_padrao():
    import ast
    padrao = set(sys.stdlib_module_names) | {"aprovador"}
    for arq in (ROOT / "server/docker/images/aprovador/aprovador").glob("*.py"):
        for no in ast.walk(ast.parse(arq.read_text(encoding="utf-8"))):
            nomes = ([a.name for a in no.names] if isinstance(no, ast.Import)
                     else [no.module or ""] if isinstance(no, ast.ImportFrom) and no.level == 0 else [])
            for nome in nomes:
                assert nome.split(".")[0] in padrao, f"{arq.name}: {nome}"
