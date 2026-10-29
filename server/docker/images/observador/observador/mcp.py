"""Cliente MCP mínimo (transporte Streamable HTTP) para a rota de leitura do hub: initialize, tools/list e
tools/call. Aceita resposta em JSON ou em SSE (text/event-stream)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable

from . import VERSAO

PROTOCOLO = "2025-06-18"
Abrir = Callable[..., object]


class ErroMCP(RuntimeError):
    pass


def _mensagens_sse(corpo: str) -> list[dict]:
    """Cada evento SSE junta as linhas 'data:'; eventos sem JSON (ping, comentário) são ignorados."""
    mensagens, dados = [], []
    for linha in corpo.splitlines() + [""]:
        if linha.startswith("data:"):
            dados.append(linha[5:].lstrip())
        elif linha == "" and dados:
            try:
                mensagens.append(json.loads("\n".join(dados)))
            except json.JSONDecodeError:
                pass
            dados = []
    return mensagens


class ClienteMCP:
    def __init__(self, url: str, token: str, timeout: float = 30, abrir: Abrir = urllib.request.urlopen):
        self.url, self.token, self.timeout, self._abrir = url, token, timeout, abrir
        self.sessao: str | None = None
        self.protocolo: str | None = None
        self._id = 0

    def _post(self, mensagem: dict) -> dict | None:
        cab = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "Authorization": f"Bearer {self.token}"}
        if self.protocolo:
            cab["MCP-Protocol-Version"] = self.protocolo
        if self.sessao:
            cab["Mcp-Session-Id"] = self.sessao
        req = urllib.request.Request(self.url, data=json.dumps(mensagem).encode(), headers=cab, method="POST")
        try:
            with self._abrir(req, timeout=self.timeout) as resp:
                sessao = resp.headers.get("Mcp-Session-Id")
                if sessao:
                    self.sessao = sessao
                tipo = resp.headers.get("Content-Type", "")
                corpo = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as erro:
            detalhe = ""
            try:  # o hub explica no corpo (ex.: "Unknown tool"): o modelo precisa ver o motivo
                corpo_erro = json.loads(erro.read().decode("utf-8", "replace") or "{}")
                detalhe = (corpo_erro.get("error") or {}).get("message", "") if isinstance(corpo_erro, dict) else ""
            except (ValueError, OSError, AttributeError):
                pass
            raise ErroMCP(f"hub respondeu {erro.code} em {mensagem.get('method')}"
                          + (f": {detalhe}" if detalhe else "")) from erro
        except (urllib.error.URLError, OSError) as erro:
            raise ErroMCP(f"hub inalcançável: {erro}") from erro
        if "id" not in mensagem:  # notificação: o hub responde 202 sem corpo
            return None
        candidatos = _mensagens_sse(corpo) if tipo.startswith("text/event-stream") else [json.loads(corpo or "{}")]
        resposta = next((m for m in candidatos if m.get("id") == mensagem["id"]), None)
        if resposta is None:
            raise ErroMCP(f"sem resposta para {mensagem.get('method')}")
        if "error" in resposta:
            raise ErroMCP(f"{mensagem.get('method')}: {resposta['error'].get('message', resposta['error'])}")
        return resposta.get("result", {})

    def _pedido(self, metodo: str, params: dict | None = None) -> dict:
        self._id += 1
        return self._post({"jsonrpc": "2.0", "id": self._id, "method": metodo, "params": params or {}})

    def iniciar(self) -> None:
        res = self._pedido("initialize", {"protocolVersion": PROTOCOLO, "capabilities": {},
                                          "clientInfo": {"name": "observador", "version": VERSAO}})
        self.protocolo = res.get("protocolVersion") or PROTOCOLO
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def ferramentas(self) -> list[dict]:
        todas, cursor = [], None
        for _ in range(20):  # paginação; 20 páginas é muito mais do que o hub tem
            res = self._pedido("tools/list", {"cursor": cursor} if cursor else {})
            todas.extend(res.get("tools", []))
            cursor = res.get("nextCursor")
            if not cursor:
                break
        return todas

    def chamar(self, nome: str, argumentos: dict) -> str:
        res = self._pedido("tools/call", {"name": nome, "arguments": argumentos})
        partes = []
        for item in res.get("content", []):
            if item.get("type") == "text":
                partes.append(item.get("text", ""))
            else:
                partes.append(f"[{item.get('type')} omitido]")
        if not partes and "structuredContent" in res:
            partes.append(json.dumps(res["structuredContent"], ensure_ascii=False))
        texto = "\n".join(partes)
        return f"ERRO da ferramenta: {texto}" if res.get("isError") else texto
