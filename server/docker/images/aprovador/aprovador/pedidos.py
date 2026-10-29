"""Registro dos pedidos: criar, decidir, usar (uma vez) e expirar. Guardado em JSON no disco (sobrevive a um
reinício) e protegido por uma trava (servidor HTTP e Telegram em threads)."""
from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import time
from typing import Callable

ESTADOS_FINAIS = ("recusado", "expirado", "usado")
MANTER = 300  # pedidos guardados (os mais recentes)
MAX_PENDENTES_POR_CLIENTE = 5  # uma enxurrada de pedidos não vira uma enxurrada de mensagens


class Conflito(Exception):
    """Pedido inexistente, já decidido, vencido ou diferente do que se quer executar."""


def registrar(evento: str, pedido: dict, **extra) -> None:
    print(json.dumps({"evento": "aprovacao", "acao_registro": evento, "pedido": pedido["id"],
                      "cliente": pedido["cliente"], "acao": pedido["acao"], "alvo": pedido["alvo"], **extra},
                     ensure_ascii=False), flush=True)


class Registro:
    def __init__(self, arquivo: str, validade_s: int, relogio: Callable[[], float] = time.time):
        self.arquivo, self.validade_s, self.relogio = arquivo, validade_s, relogio
        self._trava = threading.RLock()
        self._pedidos: dict[str, dict] = {}
        try:
            with open(arquivo, encoding="utf-8") as f:
                self._pedidos = {p["id"]: p for p in json.load(f)}
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError) as erro:
            print(f"aprovador: {arquivo} ilegível, começando vazio: {erro}", file=sys.stderr)

    def _gravar(self) -> None:
        ordem = sorted(self._pedidos.values(), key=lambda p: p["criado"])[-MANTER:]
        self._pedidos = {p["id"]: p for p in ordem}
        temporario = self.arquivo + ".tmp"
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump(ordem, f, ensure_ascii=False)
        os.replace(temporario, self.arquivo)

    def _vencer(self, p: dict, agora: float) -> bool:
        """Pendente há mais que a validade, ou aprovado e não usado dentro dela: expira."""
        if p["estado"] == "pendente" and agora - p["criado"] > self.validade_s:
            p.update(estado="expirado", decidido_em=agora)
        elif p["estado"] == "aprovado" and agora - p["decidido_em"] > self.validade_s:
            p.update(estado="expirado")
        else:
            return False
        registrar("expirado", p)
        return True

    def expirar(self) -> list[dict]:
        with self._trava:
            agora = self.relogio()
            vencidos = [p for p in self._pedidos.values() if self._vencer(p, agora)]
            if vencidos:
                self._gravar()
            return [dict(p) for p in vencidos]

    def criar(self, cliente: str, acao: str, alvo: str, argumentos: dict, descricao: str) -> dict:
        with self._trava:
            agora = self.relogio()
            for p in self._pedidos.values():
                self._vencer(p, agora)
            pendentes = sum(1 for p in self._pedidos.values() if p["cliente"] == cliente and p["estado"] == "pendente")
            if pendentes >= MAX_PENDENTES_POR_CLIENTE:
                raise Conflito(f"{cliente} já tem {pendentes} pedidos pendentes; espere a decisão")
            pid = secrets.token_hex(4)
            while pid in self._pedidos:
                pid = secrets.token_hex(4)
            p = {"id": pid, "cliente": cliente, "acao": acao, "alvo": alvo, "argumentos": argumentos,
                 "descricao": descricao[:500], "criado": self.relogio(), "estado": "pendente",
                 "decidido_por": "", "decidido_em": 0.0, "mensagem_telegram": 0}
            self._pedidos[pid] = p
            self._gravar()
            registrar("criado", p)
            return dict(p)

    def anotar_mensagem(self, pid: str, mensagem_id: int) -> None:
        with self._trava:
            if pid in self._pedidos:
                self._pedidos[pid]["mensagem_telegram"] = mensagem_id
                self._gravar()

    def obter(self, pid: str) -> dict | None:
        with self._trava:
            p = self._pedidos.get(pid)
            if p and self._vencer(p, self.relogio()):
                self._gravar()
            return dict(p) if p else None

    def listar(self) -> list[dict]:
        self.expirar()
        with self._trava:
            return [dict(p) for p in sorted(self._pedidos.values(), key=lambda p: p["criado"], reverse=True)]

    def decidir(self, pid: str, aprovar: bool, quem: str) -> dict:
        with self._trava:
            p = self._pedidos.get(pid)
            if p is None:
                raise Conflito("pedido não encontrado")
            self._vencer(p, self.relogio())
            if p["estado"] != "pendente":
                raise Conflito(f"pedido já está {p['estado']}")
            p.update(estado="aprovado" if aprovar else "recusado", decidido_por=quem[:100],
                     decidido_em=self.relogio())
            self._gravar()
            registrar(p["estado"], p, por=p["decidido_por"])
            return dict(p)

    def usar(self, pid: str, cliente: str, acao: str, alvo: str, argumentos: dict) -> dict:
        """O ops chama antes de executar: só passa um pedido aprovado, no prazo, do mesmo cliente e da mesma
        ação, uma vez."""
        with self._trava:
            p = self._pedidos.get(pid)
            if p is None:
                raise Conflito("pedido não encontrado")
            self._vencer(p, self.relogio())
            if p["estado"] != "aprovado":
                raise Conflito(f"pedido {p['estado']}")
            if (p["cliente"], p["acao"], p["alvo"], p["argumentos"]) != (cliente, acao, alvo, argumentos):
                raise Conflito("o pedido aprovado é de outro cliente, ação, alvo ou argumentos")
            p["estado"] = "usado"
            self._gravar()
            registrar("usado", p)
            return dict(p)
