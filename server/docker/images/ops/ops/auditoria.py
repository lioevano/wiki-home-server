"""Registro de cada ação (linha JSON no stdout, coletada pelo Alloy para o Loki) e aviso no Telegram via n8n."""
from __future__ import annotations

import json
import sys
import urllib.request
from typing import Callable

Enviar = Callable[[dict], None]


def registrar(acao: str, alvo: str, resultado: str, duracao_s: float, detalhe: str = "",
              enviar: Enviar | None = None, cliente: str = "desconhecido") -> dict:
    """cliente: quem pediu pelo hub (metadado da chave: claude_code, agentes, mcp_auth_servidor)."""
    reg = {"evento": "ops_acao", "acao": acao, "alvo": alvo, "resultado": resultado, "cliente": cliente,
           "duracao_s": round(duracao_s, 2), "detalhe": detalhe[:500]}
    if enviar is not None:
        try:
            enviar({"gravidade": "info" if resultado == "ok" else "warning",
                    "titulo": f"IA: {acao} {alvo} ({resultado}, {cliente})",
                    "mensagem": detalhe[:500] or f"{acao} em {alvo}: {resultado}", "app": "ops"})
            reg["aviso"] = "enviado"
        except Exception as erro:  # o aviso nunca derruba a ação
            reg["aviso"] = "falhou"
            print(f"aviso não enviado: {erro}", file=sys.stderr)
    print(json.dumps(reg, ensure_ascii=False), flush=True)
    return reg


def enviar_webhook(url: str, token: str) -> Enviar | None:
    """Envia ao webhook /webhook/notificar do n8n (mesmo formato do scripts/notify.sh)."""
    if not url or not token:
        return None

    def enviar(aviso: dict) -> None:
        req = urllib.request.Request(url, data=json.dumps(aviso).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if not 200 <= resp.status < 300:
                raise OSError(f"webhook respondeu {resp.status}")

    return enviar
