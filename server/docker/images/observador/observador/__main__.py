"""python -m observador: serve na porta OBSERVADOR_PORTA (8080).
python -m observador boletim: faz um boletim agora e sai (teste; docker exec observador python -m observador boletim)."""
from __future__ import annotations

import os
import sys
import threading

from .config import Config
from .servidor import Observador, servir


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cfg = Config.do_ambiente(dict(os.environ))
    if argv[:1] == ["boletim"]:
        return 0 if Observador(cfg).processar("boletim")["resultado"] == "ok" else 1
    if argv:
        print("uso: python -m observador [boletim]", file=sys.stderr)
        return 2
    parar = threading.Event()
    servidor = servir(Observador(cfg), parar)
    try:
        servidor.serve_forever()
    finally:
        parar.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
