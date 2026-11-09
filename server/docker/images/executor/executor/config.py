"""Configuração do executor, lida das variáveis de ambiente (falha fechada: obrigatória vazia não sobe)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping

from ops.config import Config as ConfigOps


class ConfigInvalida(ValueError):
    pass


# campo -> variável de ambiente (todas obrigatórias: vazia ou só espaços recusa)
OBRIGATORIAS = {
    "token_mcp": "EXECUTOR_TOKEN", "bot_token": "TELEGRAM_BOT_TOKEN", "chat_id": "TELEGRAM_CHAT_ID",
    "tailscale_chave_host": "TAILSCALE_CHAVE_HOST", "ansible_usuario_host": "ANSIBLE_USUARIO_HOST",
    "rotas": "EXECUTOR_ROTAS", "repo_url_raw": "REPO_URL_RAW", "equipe_repo": "EQUIPE_REPO",
    "github_token_equipe": "GITHUB_TOKEN_EQUIPE", "conta_sysadmin": "CONTA_SYSADMIN",
    "webhook_url": "WEBHOOK_URL", "webhook_segredo": "WEBHOOK_SEGREDO",
}


@dataclass(frozen=True)
class Config:
    token_mcp: str                # Authorization: Bearer do MCP (o agente sysadmin)
    bot_token: str                # bot do Telegram dos pedidos de aprovação
    chat_id: str
    usuarios: frozenset[str]      # ids do Telegram que podem decidir
    tailscale_chave_host: str
    ansible_usuario_host: str
    rotas: str                    # CIDRs da casa anunciados pelo tailnet, separados por vírgula
    repo_url_raw: str
    equipe_repo: str
    github_token_equipe: str
    conta_sysadmin: str
    webhook_url: str
    webhook_segredo: str
    playbooks: dict[str, str]
    repo_dir: str = "/repo"
    inventario: str = "inventories/home/hosts.ini"  # relativo a <repo>/server/ansible (cwd do ansible)
    chave_ssh: str = "/segredos/id_ed25519"
    senha_vault_arquivo: str = "/segredos/vault_senha"
    saida_dir: str = "/saida"
    dados_dir: str = "/data"
    limite_saida: int = 20000
    validade_s: int = 1800
    carteiro_intervalo_s: int = 120

    @classmethod
    def do_ambiente(cls, env: Mapping[str, str]) -> "Config":
        faltando = [v for v in OBRIGATORIAS.values() if not env.get(v, "").strip()]
        if not env.get("EXECUTOR_PLAYBOOKS", "").strip():
            faltando.append("EXECUTOR_PLAYBOOKS")
        if faltando:
            raise ConfigInvalida("variáveis obrigatórias vazias: " + ", ".join(faltando))
        valores = {campo: env[var].strip() for campo, var in OBRIGATORIAS.items()}
        try:
            playbooks = json.loads(env["EXECUTOR_PLAYBOOKS"])
        except ValueError as erro:
            raise ConfigInvalida("EXECUTOR_PLAYBOOKS não é JSON válido") from erro
        if not isinstance(playbooks, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                       for k, v in playbooks.items()):
            raise ConfigInvalida("EXECUTOR_PLAYBOOKS precisa ser um objeto JSON nome -> descrição")
        extras = {u.strip() for u in env.get("EXECUTOR_TELEGRAM_USUARIOS", "").split(",") if u.strip()}
        # Num chat privado, o id do chat é o id do usuário; num grupo (id negativo), só os extras decidem.
        usuarios = extras | ({valores["chat_id"]} if not valores["chat_id"].startswith("-") else set())
        if not usuarios:
            raise ConfigInvalida("ninguém pode decidir: TELEGRAM_CHAT_ID é um grupo e "
                                 "EXECUTOR_TELEGRAM_USUARIOS está vazio")
        return cls(**valores, usuarios=frozenset(usuarios), playbooks=playbooks,
                   repo_dir=env.get("EXECUTOR_REPO_DIR", "").strip() or "/repo")

    def para_ops(self) -> ConfigOps:
        """Config do runner Ansible do ops (reaproveitado): sem Portainer, sempre em modo controle."""
        return ConfigOps(modo="controle", portainer_url="", portainer_api_key="", endpoints={},
                         containers_protegidos=frozenset(), stacks_protegidas=frozenset(),
                         playbooks=self.playbooks, limite_saida=self.limite_saida, webhook_url="",
                         webhook_token="", repo_dir=self.repo_dir, repo_url="", inventario=self.inventario,
                         chave_ssh=self.chave_ssh, plano_validade_s=self.validade_s)
