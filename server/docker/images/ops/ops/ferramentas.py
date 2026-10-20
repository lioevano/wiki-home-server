"""As ferramentas do ops. O modo decide quais existem: 'leitura' nem registra as que mudam algo."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from . import auditoria
from .config import Config
from .politica import Recusado, checar_container, checar_stack, limpar_saida
from .portainer import Portainer

if TYPE_CHECKING:
    from .runner import Runner


@dataclass
class Ferramenta:
    nome: str
    funcao: Callable
    destrutiva: bool
    descricao: str


def _tabela(linhas: list[dict], campos: list[str]) -> str:
    if not linhas:
        return "(nada)"
    return "\n".join(" | ".join(str(l[c]) for c in campos) for l in [dict(zip(campos, campos))] + linhas)


def ferramentas(cfg: Config, portainer: Portainer, runner: "Runner | None",
                enviar: auditoria.Enviar | None) -> dict[str, Ferramenta]:
    def acao(nome_acao: str, alvo: str, executar: Callable[[], "str | tuple[str, bool, str]"]) -> str:
        """executar devolve o texto, ou (texto, deu_certo, alvo) quando o resultado depende do que rodou (Ansible)."""
        inicio = time.monotonic()
        try:
            r = executar()
        except Recusado as erro:
            auditoria.registrar(nome_acao, alvo, "recusado", time.monotonic() - inicio, str(erro), enviar)
            raise
        except Exception as erro:
            auditoria.registrar(nome_acao, alvo, "erro", time.monotonic() - inicio, str(erro), enviar)
            raise
        texto, ok, alvo = (r, True, alvo) if isinstance(r, str) else r
        auditoria.registrar(nome_acao, alvo, "ok" if ok else "erro", time.monotonic() - inicio, texto[-300:], enviar)
        return texto

    # --- leitura ---
    def containers_listar(vm: str | None = None) -> str:
        """Lista os containers das VMs (core e ai): nome, imagem, estado e saúde. vm: 'core', 'ai' ou vazio."""
        return _tabela(portainer.containers(vm), ["vm", "nome", "imagem", "estado", "saude", "status"])

    def container_logs(nome: str, linhas: int = 200) -> str:
        """Últimas linhas do log de um container (no máximo 500). Linhas com cara de segredo vêm mascaradas."""
        return limpar_saida(portainer.logs(nome, max(1, min(linhas, 500))), cfg.limite_saida)

    def stacks_listar() -> str:
        """Lista as stacks do Portainer, a VM de cada uma e se está ativa."""
        return _tabela(portainer.stacks(), ["nome", "vm", "estado"])

    def playbooks_listar() -> str:
        """Playbooks Ansible que podem ser simulados (ansible_check) e aplicados (ansible_aplicar)."""
        return "\n".join(f"{n}: {d}" for n, d in sorted(cfg.playbooks.items())) or "(nenhum)"

    lista = [
        Ferramenta("containers_listar", containers_listar, False, containers_listar.__doc__),
        Ferramenta("container_logs", container_logs, False, container_logs.__doc__),
        Ferramenta("stacks_listar", stacks_listar, False, stacks_listar.__doc__),
        Ferramenta("playbooks_listar", playbooks_listar, False, playbooks_listar.__doc__),
    ]

    if cfg.modo == "controle":
        def container_reiniciar(nome: str) -> str:
            """Reinicia um container. Containers do caminho de controle (Traefik, Authelia, Portainer, hub) são recusados."""
            def fazer() -> str:
                checar_container(nome, cfg)
                portainer.reiniciar(nome)
                return f"container {nome} reiniciado"
            return acao("container_reiniciar", nome, fazer)

        def stack_redeploy(nome: str, puxar_imagens: bool = False) -> str:
            """Redeploy de uma stack do Portainer com o mesmo compose e variáveis; puxar_imagens baixa as versões do compose."""
            def fazer() -> str:
                checar_stack(nome, cfg)
                portainer.redeploy(nome, puxar_imagens)
                return f"stack {nome} redeployada" + (" (imagens atualizadas)" if puxar_imagens else "")
            return acao("stack_redeploy", nome, fazer)

        def _runner() -> "Runner":
            if runner is None:
                raise Recusado("runner Ansible indisponível nesta instância")
            return runner

        def ansible_check(playbook: str, limite: str | None = None) -> str:
            """Simula um playbook (--check --diff) no commit atual do repositório e devolve o diff e um plano_id."""
            def fazer() -> str:
                r = _runner().check(playbook, limite)
                texto = f"plano_id: {r['plano_id']}\ncommit: {r['commit']}\nrc: {r['rc']}\n{r['saida']}"
                return texto, r["rc"] == 0, playbook
            return acao("ansible_check", playbook, fazer)

        def ansible_aplicar(plano_id: str) -> str:
            """Aplica de verdade o playbook simulado pelo ansible_check (mesmo playbook, limite e commit; vale 30 min)."""
            def fazer() -> str:
                r = _runner().aplicar(plano_id)
                texto = f"playbook: {r['playbook']}\ncommit: {r['commit']}\nrc: {r['rc']}\n{r['saida']}"
                return texto, r["rc"] == 0, r["playbook"]
            return acao("ansible_aplicar", plano_id, fazer)

        lista += [
            Ferramenta("container_reiniciar", container_reiniciar, True, container_reiniciar.__doc__),
            Ferramenta("stack_redeploy", stack_redeploy, True, stack_redeploy.__doc__),
            Ferramenta("ansible_check", ansible_check, False, ansible_check.__doc__),
            Ferramenta("ansible_aplicar", ansible_aplicar, True, ansible_aplicar.__doc__),
        ]
    return {f.nome: f for f in lista}
