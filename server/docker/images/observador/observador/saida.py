"""Saídas: uma linha JSON por análise no stdout (o Alloy leva ao Loki) e o aviso no Telegram via n8n."""
from __future__ import annotations

import json
import sys
import urllib.request
from typing import Callable

LIMITE_MENSAGEM = 3500  # o Telegram aceita 4.096 caracteres; sobra para o título e a formatação do n8n
RODAPE = "\n\n(análise automática da IA, só leitura)"
Enviar = Callable[[dict], None]


def registrar(reg: dict) -> dict:
    print(json.dumps({"evento": "observador", **reg}, ensure_ascii=False), flush=True)
    return reg


def enviar_webhook(url: str, token: str, abrir=urllib.request.urlopen) -> Enviar:
    def enviar(aviso: dict) -> None:
        req = urllib.request.Request(url, data=json.dumps(aviso).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with abrir(req, timeout=15) as resp:
            if not 200 <= resp.status < 300:
                raise OSError(f"webhook respondeu {resp.status}")
    return enviar


def _mensagem(texto: str) -> str:
    texto = texto.strip() or "(o modelo não devolveu texto)"
    if len(texto) > LIMITE_MENSAGEM:
        texto = texto[:LIMITE_MENSAGEM].rstrip() + " […]"
    return texto + RODAPE


def aviso_alerta(alerta: dict, texto: str) -> dict:
    rotulos = alerta.get("labels") or {}
    nome = rotulos.get("alertname", "alerta")
    return {"titulo": f"IA analisou: {nome}", "mensagem": _mensagem(texto),
            "gravidade": rotulos.get("severity") or "warning", "app": rotulos.get("app") or "observador"}


def aviso_boletim(texto: str) -> dict:
    primeira = (texto.strip().splitlines() or [""])[0].lower()
    gravidade = "warning" if ("problema" in primeira or "atenção" in primeira) else "ok"
    return {"titulo": "Boletim do servidor", "mensagem": _mensagem(texto), "gravidade": gravidade,
            "app": "observador"}


def aviso_erro(motivo: str, gatilho: str) -> None:
    print(f"observador: {gatilho} falhou: {motivo}", file=sys.stderr, flush=True)
