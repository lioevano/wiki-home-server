"""Token interno entre o hub e o ops: sem ele, ninguém nas redes Docker compartilhadas chama as ferramentas."""
from __future__ import annotations

import hmac


class ExigirToken:
    """Middleware ASGI: só deixa passar requisições HTTP com 'Authorization: Bearer <token>'."""

    def __init__(self, app, token: str):
        if not token:
            raise ValueError("OPS_TOKEN vazio: o ops não sobe sem o token interno do hub")
        self.app = app
        self._esperado = f"Bearer {token}".encode()

    async def __call__(self, escopo, receive, send):
        if escopo["type"] == "http":
            recebido = dict(escopo.get("headers") or []).get(b"authorization", b"")
            if not hmac.compare_digest(recebido, self._esperado):
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"text/plain; charset=utf-8")]})
                await send({"type": "http.response.body", "body": "token do hub ausente ou inválido".encode()})
                return
        await self.app(escopo, receive, send)
