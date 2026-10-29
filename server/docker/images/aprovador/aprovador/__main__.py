"""python -m aprovador: serve na porta APROVADOR_PORTA (8080) e lê os cliques do Telegram."""
from __future__ import annotations

import os
import sys
import threading

from .config import Config
from .pedidos import Registro
from .servidor import servir
from .telegram import Bot, Telegram


def main() -> int:
    cfg = Config.do_ambiente(dict(os.environ))
    registro = Registro(cfg.dados, cfg.validade_s)
    telegram = Telegram(Bot(cfg.bot_token), registro, cfg.chat_id, cfg.usuarios, cfg.url_publica)
    parar = threading.Event()
    servidor = servir(cfg, registro, telegram, parar)
    try:
        servidor.serve_forever()
    finally:
        parar.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
