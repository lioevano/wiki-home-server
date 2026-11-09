"""Canal de segredos: o Léo responde no Telegram a um pedido e o valor vai direto para o vault.

O valor nunca passa pelo modelo, por log ou por mensagem: a mensagem do Léo é apagada primeiro de tudo
e as falhas só registram o tipo do erro.
"""
from __future__ import annotations

import sys
import threading
import time
from typing import Callable

from ops.politica import Recusado

from .config import Config
from .vault import chaves_do_modelo, definir


class CanalDeSegredos:
    def __init__(self, bot, cfg: Config, vault, chaves: set[str], relogio: Callable[[], float] = time.time):
        self.bot, self.cfg, self.vault, self.chaves, self.relogio = bot, cfg, vault, set(chaves), relogio
        self._pendentes: dict[int, tuple[str, float]] = {}   # id da mensagem do pedido -> (chave, vence em)
        self._gravadas: list[str] = []
        self._trava = threading.Lock()                       # o MCP (pedir/status) e o leitor rodam em threads

    def _minutos(self) -> int:
        return max(1, self.cfg.validade_s // 60)

    def _dizer(self, texto: str, **extra) -> dict | None:
        try:
            return self.bot.chamar("sendMessage", {"chat_id": self.cfg.chat_id, "text": texto, **extra})
        except OSError as erro:
            print(f"segredos: mensagem não saiu: {erro}", file=sys.stderr)
            return None

    def _vencidos(self) -> None:
        agora = self.relogio()
        for mid in [m for m, (_, vence) in self._pendentes.items() if agora > vence]:
            del self._pendentes[mid]

    def pedir(self, chave: str) -> str:
        if chave not in self.chaves:
            raise Recusado(f"chave desconhecida no modelo do vault: {chave}")
        try:
            presentes = chaves_do_modelo(self.vault.ler())
        except Exception as erro:  # noqa: BLE001 — só o tipo do erro
            print(f"segredos: vault ilegível ({type(erro).__name__})", file=sys.stderr)
            raise Recusado("não consegui ler o vault") from None
        if chave not in presentes:
            raise Recusado(f"a chave {chave} não existe no vault atual (só no modelo); "
                           "acrescente-a ao vault antes de pedir o valor")
        texto = (f"🔐 Responda a esta mensagem com o valor de `{chave}` "
                 f"(vale {self._minutos()} min; a sua resposta é apagada)")
        try:
            msg = self.bot.chamar("sendMessage", {"chat_id": self.cfg.chat_id, "text": texto, "parse_mode": "Markdown",
                                                  "reply_markup": {"force_reply": True}})
            mid = int(msg["message_id"])
        except (OSError, KeyError, TypeError, ValueError):
            raise Recusado("não consegui enviar o pedido pelo Telegram") from None
        with self._trava:
            self._vencidos()
            for antigo in [m for m, (c, _) in self._pendentes.items() if c == chave]:
                del self._pendentes[antigo]                  # um pedido novo substitui o anterior da mesma chave
            self._pendentes[mid] = (chave, self.relogio() + self.cfg.validade_s)
        return (f"Pedido de `{chave}` enviado ao Léo no Telegram (vale {self._minutos()} min). "
                "O valor vai direto para o vault; você não o verá. Consulte com o status dos segredos.")

    def receber(self, update: dict) -> None:
        msg = update.get("message")
        if not isinstance(msg, dict):
            return
        quem = str((msg.get("from") or {}).get("id", ""))
        chat = str((msg.get("chat") or {}).get("id", ""))
        if chat != self.cfg.chat_id or quem not in self.cfg.usuarios:
            return                                           # só o Léo, no chat configurado
        mid = msg.get("message_id")
        try:                                                 # antes de tudo: o valor não fica no chat
            self.bot.chamar("deleteMessage", {"chat_id": self.cfg.chat_id, "message_id": mid})
        except OSError as erro:
            print(f"segredos: mensagem {mid} não foi apagada: {erro}", file=sys.stderr)
        valor = msg.get("text")
        resposta_a = (msg.get("reply_to_message") or {}).get("message_id")
        with self._trava:
            pedido = self._pendentes.get(resposta_a) if isinstance(valor, str) else None
            if pedido is not None and self.relogio() > pedido[1]:
                self._vencidos()
                self._dizer("⌛ O pedido venceu; peça de novo ao sysadmin.")
                return
            if pedido is None:
                self._dizer("Responda à mensagem do pedido (use “Responder” nela).")
                return
            chave = pedido[0]
            try:
                self.vault.gravar(definir(self.vault.ler(), chave, valor))
            except KeyError:                                 # a chave sumiu do vault: repetir não adianta
                del self._pendentes[resposta_a]
                self._dizer(f"⚠️ `{chave}` não existe no vault atual; não gravei nada. Avise o sysadmin.",
                            parse_mode="Markdown")
                return
            except Exception as erro:  # noqa: BLE001 — a mensagem do erro poderia trazer o valor: só o tipo
                print(f"segredos: não gravei {chave} ({type(erro).__name__})", file=sys.stderr)
                self._dizer(f"⚠️ Não consegui gravar `{chave}`; responda de novo à mesma mensagem.", parse_mode="Markdown")
                return
            del self._pendentes[resposta_a]
            if chave not in self._gravadas:
                self._gravadas.append(chave)
        self._dizer(f"✅ `{chave}` gravada; o sysadmin abre o PR", parse_mode="Markdown")

    def status(self) -> str:
        with self._trava:
            self._vencidos()
            linhas = [f"{chave}: pendente" for chave, _ in self._pendentes.values()]
            linhas += [f"{chave}: gravada" for chave in self._gravadas]
        return "\n".join(linhas) or "Nenhum pedido de segredo."
