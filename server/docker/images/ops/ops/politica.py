"""Regras que valem para todas as ferramentas: o que é recusado e como a saída é limpa."""
from __future__ import annotations

import re

from .config import Config

SEGREDO = re.compile(r"vault|password|passwd|pass|token|secret|key|auth|salt|hmac|private|credential|bearer|cookie",
                     re.IGNORECASE)
# Linha de .env (ou de diff de .env): NOME=valor — o nome nem sempre denuncia o segredo (ex.: OPENAI_API_KEY já pega,
# mas um NOME qualquer com valor também é mascarado: no diff do Ansible, .env só traz configuração e segredos).
LINHA_ENV = re.compile(r"^[+-]?\s*[A-Z][A-Z0-9_]*=.+")
PEM_INICIO = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
PEM_FIM = re.compile(r"-----END [A-Z ]*PRIVATE KEY-----")
MASCARA = "[linha omitida: possível segredo]"


class Recusado(Exception):
    """Ação recusada pela política (container protegido, plano vencido, playbook fora da lista…)."""


def limpar_saida(texto: str, limite: int) -> str:
    """Mascara linhas que parecem ter segredo e mantém só o fim do texto (o que importa num log ou num Ansible)."""
    linhas, em_pem = [], False
    for linha in texto.splitlines():
        if PEM_INICIO.search(linha):
            em_pem = True
        if em_pem or SEGREDO.search(linha) or LINHA_ENV.match(linha):
            linhas.append(MASCARA)
        else:
            linhas.append(linha)
        if PEM_FIM.search(linha):
            em_pem = False
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
