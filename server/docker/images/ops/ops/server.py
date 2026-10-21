"""Ponto de entrada do MCP ops: registra no FastMCP as ferramentas do modo (OPS_MODO) e serve em HTTP."""
from __future__ import annotations

import os

from fastmcp import FastMCP
from starlette.middleware import Middleware

from .auditoria import enviar_webhook
from .autenticacao import ExigirToken
from .config import Config
from .ferramentas import ferramentas
from .portainer import Portainer, http_real
from .runner import Runner


def _cliente() -> str:
    """Cliente do hub que fez a chamada: o agentgateway grava o metadado da chave em x-homeserver-cliente.
    Só o hub chega até aqui (token interno), então o cabeçalho é confiável."""
    try:
        from fastmcp.server.dependencies import get_http_headers
        return get_http_headers().get("x-homeserver-cliente", "")
    except Exception:  # fora de uma requisição HTTP ou API do FastMCP diferente: registra como desconhecido
        return ""


def main() -> None:
    cfg = Config.do_ambiente(os.environ)
    runner = Runner(cfg) if cfg.modo == "controle" else None
    mcp = FastMCP(name=f"ops-{cfg.modo}",
                  instructions="Operações do homeserver: containers e stacks (Portainer) e playbooks Ansible "
                               "(simule com ansible_check antes de ansible_aplicar).")
    for f in ferramentas(cfg, Portainer(cfg, http_real(cfg)), runner,
                         enviar_webhook(cfg.webhook_url, cfg.webhook_token), _cliente).values():
        so_le = not f.destrutiva and f.nome != "ansible_check"
        mcp.tool(f.funcao, name=f.nome, description=f.descricao,
                 annotations={"readOnlyHint": so_le, "destructiveHint": f.destrutiva, "openWorldHint": False})
    # Só o hub chama o ops (token interno em OPS_TOKEN): as redes Docker são compartilhadas com outras aplicações.
    mcp.run(transport="http", host="0.0.0.0", port=8000, path="/mcp",
            middleware=[Middleware(ExigirToken, token=os.environ.get("OPS_TOKEN", ""))])


if __name__ == "__main__":
    main()
