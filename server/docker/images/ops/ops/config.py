"""Configuração do ops, lida das variáveis de ambiente (geradas pelo setup-agents-volumes.yml)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Mapping

MODOS = ("leitura", "controle")


def _lista(valor: str) -> frozenset[str]:
    return frozenset(x.strip() for x in valor.split(",") if x.strip())


@dataclass(frozen=True)
class Config:
    modo: Literal["leitura", "controle"]
    portainer_url: str
    portainer_api_key: str
    endpoints: dict[str, str]
    containers_protegidos: frozenset[str]
    stacks_protegidas: frozenset[str]
    playbooks: dict[str, str]
    limite_saida: int
    webhook_url: str
    webhook_token: str
    repo_dir: str
    repo_url: str
    inventario: str
    chave_ssh: str
    plano_validade_s: int
    # Clientes do hub (metadado da chave) cujas ações esperam o "aprovar" do Léo no aprovador (página 16).
    clientes_com_aprovacao: frozenset[str] = frozenset()
    aprovador_url: str = ""
    aprovador_token: str = ""

    @classmethod
    def do_ambiente(cls, env: Mapping[str, str]) -> "Config":
        modo = env.get("OPS_MODO", "")
        if modo not in MODOS:
            raise ValueError(f"OPS_MODO deve ser 'leitura' ou 'controle', não {modo!r}")
        return cls(
            modo=modo,  # type: ignore[arg-type]
            portainer_url=env["PORTAINER_URL"].rstrip("/"),
            portainer_api_key=env["PORTAINER_API_KEY"],
            endpoints=json.loads(env.get("OPS_ENDPOINTS", "{}")),
            containers_protegidos=_lista(env.get("OPS_CONTAINERS_PROTEGIDOS", "")),
            stacks_protegidas=_lista(env.get("OPS_STACKS_PROTEGIDAS", "")),
            playbooks=json.loads(env.get("OPS_PLAYBOOKS", "{}")),
            limite_saida=int(env.get("OPS_LIMITE_SAIDA", "20000")),
            webhook_url=env.get("NOTIFICACOES_WEBHOOK_URL", ""),
            webhook_token=env.get("NOTIFICACOES_WEBHOOK_TOKEN", ""),
            repo_dir=env.get("OPS_REPO_DIR", "/repo"),
            repo_url=env.get("OPS_REPO_URL", ""),
            inventario=env.get("OPS_INVENTARIO", "server/ansible/inventories/home/hosts.ini"),
            chave_ssh=env.get("OPS_CHAVE_SSH", "/segredos/id_ed25519"),
            plano_validade_s=int(env.get("OPS_PLANO_VALIDADE_MIN", "30")) * 60,
            clientes_com_aprovacao=_lista(env.get("OPS_CLIENTES_COM_APROVACAO", "agentes,assistente")),
            aprovador_url=env.get("APROVADOR_URL", ""),
            aprovador_token=env.get("APROVADOR_TOKEN", ""),
        )
