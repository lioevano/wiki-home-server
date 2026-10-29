"""Configuração lida das variáveis de ambiente (compose da stack agents; valores no agents.env)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


class ConfigInvalida(ValueError):
    pass


def _int(env: dict, nome: str, padrao: int) -> int:
    valor = env.get(nome, "") or str(padrao)
    try:
        n = int(valor)
    except ValueError as erro:
        raise ConfigInvalida(f"{nome} precisa ser inteiro: {valor!r}") from erro
    if n <= 0:
        raise ConfigInvalida(f"{nome} precisa ser maior que zero: {n}")
    return n


@dataclass(frozen=True)
class Config:
    hub_url: str
    hub_token: str
    llm_url: str
    llm_chave: str
    modelo: str
    token: str  # quem chama POST /alerta (o Grafana) manda Authorization: Bearer <token>
    webhook_url: str
    webhook_token: str
    boletim_hora: str = "07:30"  # HH:MM no fuso da VM; vazio desliga o boletim
    max_passos: int = 8
    limite_saida: int = 6000
    tempo_max_s: int = 180
    reanalise_h: int = 12
    max_por_hora: int = 6
    fila_max: int = 10
    porta: int = 8080
    ignorar: frozenset = field(default_factory=lambda: frozenset({"observador-falhou"}))
    # Prefixos de ferramentas que o observador nem oferece ao modelo: o estado da casa não ajuda a analisar o
    # servidor, sai de casa à toa e as definições custam tokens em cada chamada.
    excluir: tuple = ("homeassistant_", "n8n_")

    @classmethod
    def do_ambiente(cls, env: dict) -> "Config":
        obrigatorias = {
            "hub_url": "OBSERVADOR_HUB_URL", "hub_token": "OBSERVADOR_HUB_TOKEN", "llm_url": "OBSERVADOR_LLM_URL",
            "llm_chave": "OBSERVADOR_LLM_CHAVE", "token": "OBSERVADOR_TOKEN",
            "webhook_url": "NOTIFICACOES_WEBHOOK_URL", "webhook_token": "NOTIFICACOES_WEBHOOK_TOKEN",
        }
        faltando = [v for v in obrigatorias.values() if not env.get(v)]
        if faltando:
            raise ConfigInvalida("variáveis obrigatórias vazias: " + ", ".join(faltando))
        hora = env.get("OBSERVADOR_BOLETIM_HORA", "07:30").strip()
        if hora and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", hora):
            raise ConfigInvalida(f"OBSERVADOR_BOLETIM_HORA precisa ser HH:MM: {hora!r}")
        ignorar = {a.strip() for a in env.get("OBSERVADOR_IGNORAR", "observador-falhou").split(",") if a.strip()}
        return cls(
            **{campo: env[var].strip() for campo, var in obrigatorias.items()},
            modelo=env.get("OBSERVADOR_MODELO", "").strip() or "rapido",
            boletim_hora=hora,
            max_passos=_int(env, "OBSERVADOR_MAX_PASSOS", 8),
            limite_saida=_int(env, "OBSERVADOR_LIMITE_SAIDA", 6000),
            tempo_max_s=_int(env, "OBSERVADOR_TEMPO_MAX_S", 180),
            reanalise_h=_int(env, "OBSERVADOR_REANALISE_H", 12),
            max_por_hora=_int(env, "OBSERVADOR_MAX_POR_HORA", 6),
            fila_max=_int(env, "OBSERVADOR_FILA_MAX", 10),
            porta=_int(env, "OBSERVADOR_PORTA", 8080),
            ignorar=frozenset(ignorar | {"observador-falhou"}),  # nunca analisa a própria falha (laço)
            excluir=tuple(p.strip() for p in env.get("OBSERVADOR_EXCLUIR", "homeassistant_,n8n_").split(",")
                          if p.strip()),
        )
