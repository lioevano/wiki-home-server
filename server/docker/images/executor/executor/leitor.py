"""Leitor do Telegram do executor: cliques nos botões vão ao aprovador; mensagens, ao canal de segredos."""
from __future__ import annotations

import sys
import threading
from typing import Callable


class Leitor:
    def __init__(self, telegram, canal):
        self.telegram, self.canal = telegram, canal

    def ler(self, timeout: int = 30) -> None:
        t = self.telegram
        updates = t.bot.chamar("getUpdates", {"offset": t.offset, "timeout": timeout,
                                              "allowed_updates": ["callback_query", "message"]}, timeout=timeout + 10)
        for u in updates or []:
            t.offset = max(t.offset, int(u.get("update_id", 0)) + 1)   # avança antes: um update ruim não repete
            try:
                if u.get("callback_query"):
                    t.tratar(u)
                elif u.get("message"):
                    self.canal.receber(u)
            except Exception as erro:  # noqa: BLE001 — o update pode ter o segredo: só o tipo do erro vai ao log
                print(f"leitor: falha ao tratar um update ({type(erro).__name__})", file=sys.stderr)

    def rodar(self, parar: threading.Event, espera: Callable[[float], bool] | None = None) -> None:
        espera = espera or parar.wait
        while not parar.is_set():
            try:
                self.ler()
                for p in self.telegram.registro.expirar():
                    self.telegram.atualizar(p)
            except OSError as erro:
                print(f"leitor: leitura do Telegram falhou: {erro}", file=sys.stderr)
                espera(10)
