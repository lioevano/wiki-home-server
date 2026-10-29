"""Bot API do Telegram: manda o pedido com botões, lê os cliques (getUpdates) e atualiza a mensagem."""
from __future__ import annotations

import html
import json
import sys
import threading
import urllib.error
import urllib.request
from typing import Callable

from .pedidos import Conflito, Registro

API = "https://api.telegram.org"
SIMBOLO = {"aprovado": "✅ Aprovado", "recusado": "❌ Recusado", "expirado": "⌛ Expirado", "usado": "✅ Aprovado e executado"}


class Bot:
    def __init__(self, token: str, abrir=urllib.request.urlopen, api: str = API):
        self.base = f"{api}/bot{token}"
        self._abrir = abrir

    def chamar(self, metodo: str, params: dict, timeout: float = 15) -> object:
        req = urllib.request.Request(f"{self.base}/{metodo}", data=json.dumps(params).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with self._abrir(req, timeout=timeout) as resp:
                dados = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as erro:  # o corpo traz a descrição; a URL (com o token) não vai para o log
            raise OSError(f"Telegram {metodo}: HTTP {erro.code}") from None
        except (urllib.error.URLError, OSError, ValueError) as erro:
            raise OSError(f"Telegram {metodo}: {type(erro).__name__}") from None
        if not dados.get("ok"):
            raise OSError(f"Telegram {metodo}: {dados.get('description', 'erro')}")
        return dados.get("result")


def texto_do_pedido(p: dict, url_publica: str) -> str:
    args = json.dumps(p["argumentos"], ensure_ascii=False)
    linhas = [f"🤖 <b>Pedido de ação</b> <code>{p['id']}</code>",
              f"<b>{html.escape(p['cliente'])}</b> quer <b>{html.escape(p['acao'])}</b> em <b>{html.escape(p['alvo'])}</b>",
              f"Argumentos: <code>{html.escape(args[:300])}</code>"]
    if p.get("descricao"):
        linhas.append(html.escape(p["descricao"]))
    estado = SIMBOLO.get(p["estado"])
    if estado:
        linhas.append(f"\n{estado}" + (f" por {html.escape(p['decidido_por'])}" if p.get("decidido_por") else ""))
    else:
        linhas.append(f"\nSem decisão, vence sozinho. Também em {html.escape(url_publica)}")
    return "\n".join(linhas)


def botoes(pid: str) -> dict:
    return {"inline_keyboard": [[{"text": "✅ Aprovar", "callback_data": f"a:{pid}"},
                                 {"text": "❌ Recusar", "callback_data": f"r:{pid}"}]]}


class Telegram:
    """Liga o registro ao bot: avisa os pedidos novos e aplica os cliques de quem pode decidir."""

    def __init__(self, bot: Bot, registro: Registro, chat_id: str, usuarios: frozenset, url_publica: str):
        self.bot, self.registro, self.chat_id = bot, registro, chat_id
        self.usuarios, self.url_publica = usuarios, url_publica
        self.offset = 0

    def avisar(self, p: dict) -> None:
        try:
            msg = self.bot.chamar("sendMessage", {"chat_id": self.chat_id, "parse_mode": "HTML",
                                                  "text": texto_do_pedido(p, self.url_publica),
                                                  "reply_markup": botoes(p["id"])})
            self.registro.anotar_mensagem(p["id"], int(msg["message_id"]))
        except (OSError, KeyError, TypeError, ValueError) as erro:  # o pedido continua na tela
            print(f"aprovador: aviso do pedido {p['id']} não saiu: {erro}", file=sys.stderr)

    def atualizar(self, p: dict) -> None:
        if not p.get("mensagem_telegram"):
            return
        try:
            self.bot.chamar("editMessageText", {"chat_id": self.chat_id, "message_id": p["mensagem_telegram"],
                                                "parse_mode": "HTML", "text": texto_do_pedido(p, self.url_publica)})
        except OSError as erro:
            print(f"aprovador: mensagem do pedido {p['id']} não atualizada: {erro}", file=sys.stderr)

    def tratar(self, update: dict) -> None:
        clique = update.get("callback_query")
        if not clique:
            return
        quem = str((clique.get("from") or {}).get("id", ""))
        chat = str(((clique.get("message") or {}).get("chat") or {}).get("id", ""))
        dados = str(clique.get("data", ""))
        resposta = "Sem permissão."
        if quem in self.usuarios and chat == self.chat_id and dados[:2] in ("a:", "r:"):
            nome = (clique.get("from") or {}).get("username") or quem
            try:
                p = self.registro.decidir(dados[2:], dados[0] == "a", f"telegram:{nome}")
                resposta = "Aprovado." if p["estado"] == "aprovado" else "Recusado."
                self.atualizar(p)
            except Conflito as erro:
                resposta = str(erro).capitalize() + "."
        try:
            self.bot.chamar("answerCallbackQuery", {"callback_query_id": clique.get("id", ""), "text": resposta})
        except OSError:
            pass

    def ler(self, timeout: int = 30) -> None:
        updates = self.bot.chamar("getUpdates", {"offset": self.offset, "timeout": timeout,
                                                 "allowed_updates": ["callback_query"]}, timeout=timeout + 10)
        for u in updates or []:
            self.offset = max(self.offset, int(u.get("update_id", 0)) + 1)
            self.tratar(u)

    def rodar(self, parar: threading.Event, espera: Callable[[float], bool] | None = None) -> None:
        espera = espera or parar.wait
        while not parar.is_set():
            try:
                self.ler()
                for p in self.registro.expirar():
                    self.atualizar(p)
            except OSError as erro:
                print(f"aprovador: leitura do Telegram falhou: {erro}", file=sys.stderr)
                espera(10)
