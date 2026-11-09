"""Ponto de entrada do executor: leitor do Telegram e carteiro em threads, e o MCP (FastMCP) atrás do token."""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Callable

MODELO_DO_VAULT = "server/ansible/inventories/home/group_vars/all/vault.yml.example"
SO_LEITURA = {"diagnostico", "playbooks_listar", "vault_status"}


def manter_vivo(nome: str, alvo: Callable[[threading.Event], None], parar: threading.Event, espera: float = 10) -> None:
    """Roda `alvo(parar)` até `parar`; se ele levantar qualquer exceção, registra só o tipo (a mensagem poderia
    trazer um segredo), espera e recomeça: uma thread morta calaria as aprovações e os segredos."""
    while not parar.is_set():
        try:
            alvo(parar)
        except Exception as erro:  # noqa: BLE001 — o laço não pode morrer
            print(f"{nome}: {type(erro).__name__}", file=sys.stderr)
        if not parar.is_set():
            parar.wait(espera)


def main() -> None:
    from aprovador.pedidos import Registro
    from aprovador.telegram import Bot, Telegram
    from fastmcp import FastMCP
    from ops.runner import Runner
    from starlette.middleware import Middleware

    from ops.autenticacao import ExigirToken
    from .carteiro import Carteiro
    from .config import Config
    from .ferramentas import ferramentas
    from .leitor import Leitor
    from .portao import Portao
    from .remoto import Remoto
    from .segredos import CanalDeSegredos
    from .vault import Vault, chaves_do_modelo

    cfg = Config.do_ambiente(os.environ)
    os.makedirs(cfg.dados_dir, exist_ok=True)
    registro = Registro(os.path.join(cfg.dados_dir, "pedidos.json"), cfg.validade_s)
    bot = Bot(cfg.bot_token)
    telegram = Telegram(bot, registro, cfg.chat_id, cfg.usuarios, "")
    chaves = chaves_do_modelo(Path(cfg.repo_dir, MODELO_DO_VAULT).read_text(encoding="utf-8"))
    canal = CanalDeSegredos(bot, cfg, Vault(cfg), chaves)

    parar = threading.Event()
    leitor, carteiro = Leitor(telegram, canal), Carteiro(cfg)
    for nome, alvo in (("leitor", leitor.rodar), ("carteiro", carteiro.rodar)):
        threading.Thread(target=manter_vivo, args=(nome, alvo, parar, 10), name=nome, daemon=True).start()

    def enviar_ao_leo(texto: str) -> None:
        bot.chamar("sendMessage", {"chat_id": cfg.chat_id, "text": texto})

    mcp = FastMCP(name="executor",
                  instructions="Executor do sysadmin: diagnóstico de leitura nos hosts; comando e playbooks Ansible só "
                               "com aprovação do Léo no Telegram (simule com ansible_check antes de ansible_aplicar); "
                               "segredos do vault pedidos ao Léo pelo Telegram.")
    for f in ferramentas(cfg, Portao(registro, telegram), Remoto(cfg), Runner(cfg.para_ops()), canal,
                         enviar_ao_leo).values():
        mcp.tool(f.funcao, name=f.nome, description=f.descricao,
                 annotations={"readOnlyHint": f.nome in SO_LEITURA, "destructiveHint": f.destrutiva,
                              "openWorldHint": False})
    mcp.run(transport="http", host="0.0.0.0", port=8000, path="/mcp",
            middleware=[Middleware(ExigirToken, token=cfg.token_mcp)])
