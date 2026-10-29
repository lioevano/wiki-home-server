"""Configuração lida das variáveis de ambiente (compose da stack agents; valores no agents.env)."""
from __future__ import annotations

from dataclasses import dataclass


class ConfigInvalida(ValueError):
    pass


def _inteiro(env: dict, nome: str, padrao: int) -> int:
    try:
        n = int(env.get(nome, "") or padrao)
    except ValueError as erro:
        raise ConfigInvalida(f"{nome} precisa ser inteiro") from erro
    if n <= 0:
        raise ConfigInvalida(f"{nome} precisa ser maior que zero")
    return n


@dataclass(frozen=True)
class Config:
    token: str            # o ops manda Authorization: Bearer <token> na API
    chave_proxy: str      # o Traefik injeta X-Aprovador-Chave nas requisições da tela (outros containers não sabem)
    url_publica: str      # https://aprovacoes.<domínio>: conferência do Origin e link na mensagem
    bot_token: str        # bot de avisos do Telegram (o mesmo das notificações)
    chat_id: str
    usuarios: frozenset   # ids do Telegram que podem decidir (o chat privado do Léo + extras)
    validade_s: int = 1800
    dados: str = "/data/pedidos.json"
    porta: int = 8080

    @classmethod
    def do_ambiente(cls, env: dict) -> "Config":
        obrigatorias = {"token": "APROVADOR_TOKEN", "chave_proxy": "APROVADOR_CHAVE_PROXY",
                        "url_publica": "APROVADOR_URL_PUBLICA", "bot_token": "TELEGRAM_BOT_TOKEN",
                        "chat_id": "TELEGRAM_CHAT_ID"}
        faltando = [v for v in obrigatorias.values() if not env.get(v, "").strip()]
        if faltando:
            raise ConfigInvalida("variáveis obrigatórias vazias: " + ", ".join(faltando))
        valores = {campo: env[var].strip() for campo, var in obrigatorias.items()}
        extras = {u.strip() for u in env.get("APROVADOR_TELEGRAM_USUARIOS", "").split(",") if u.strip()}
        # Num chat privado, o id do chat é o id do usuário; num grupo (id negativo), só os extras decidem.
        usuarios = extras | ({valores["chat_id"]} if not valores["chat_id"].startswith("-") else set())
        if not usuarios:
            raise ConfigInvalida("ninguém pode decidir: TELEGRAM_CHAT_ID é um grupo e APROVADOR_TELEGRAM_USUARIOS está vazio")
        return cls(**valores, usuarios=frozenset(usuarios),
                   validade_s=_inteiro(env, "APROVADOR_VALIDADE_MIN", 30) * 60,
                   dados=env.get("APROVADOR_DADOS", "") or "/data/pedidos.json",
                   porta=_inteiro(env, "APROVADOR_PORTA", 8080))
