"""Regras que valem para todas as ferramentas: o que é recusado e como a saída é limpa."""
from __future__ import annotations

import re

from .config import Config

SEGREDO = re.compile(r"vault|password|token|secret", re.IGNORECASE)
MASCARA = "[linha omitida: possível segredo]"


class Recusado(Exception):
    """Ação recusada pela política (container protegido, plano vencido, playbook fora da lista…)."""


def limpar_saida(texto: str, limite: int) -> str:
    """Mascara linhas que parecem ter segredo e mantém só o fim do texto (o que importa num log ou num Ansible)."""
    linhas = [MASCARA if SEGREDO.search(linha) else linha for linha in texto.splitlines()]
    limpo = "\n".join(linhas)
    if len(limpo) > limite:
        cortados = len(limpo) - limite
        limpo = f"[…truncado: {cortados} caracteres]\n" + limpo[-limite:]
    return limpo


def checar_container(nome: str, cfg: Config) -> None:
    if nome in cfg.containers_protegidos:
        raise Recusado(f"o container {nome} é protegido (caminho de controle da própria IA); reinicie pelo Portainer")


def checar_stack(nome: str, cfg: Config) -> None:
    if nome in cfg.stacks_protegidas:
        raise Recusado(f"a stack {nome} é protegida; faça o redeploy pelo Portainer")
