"""As ferramentas do ops. O modo decide quais existem: 'leitura' nem registra as que mudam algo."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from . import auditoria
from .aprovacao import Aprovador
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
                enviar: auditoria.Enviar | None, cliente: Callable[[], str] = lambda: "",
                aprovador: Aprovador | None = None) -> dict[str, Ferramenta]:
    aprovador = aprovador or Aprovador(cfg.aprovador_url, cfg.aprovador_token)

    def quem() -> str:
        return cliente() or "desconhecido"

    def acao(nome_acao: str, alvo: str, executar: Callable[[], "str | tuple[str, bool, str]"]) -> str:
        """executar devolve o texto, ou (texto, deu_certo, alvo) quando o resultado depende do que rodou (Ansible)."""
        inicio = time.monotonic()
        try:
            r = executar()
        except Recusado as erro:
            auditoria.registrar(nome_acao, alvo, "recusado", time.monotonic() - inicio, str(erro), enviar, quem())
            raise
        except Exception as erro:
            auditoria.registrar(nome_acao, alvo, "erro", time.monotonic() - inicio, str(erro), enviar, quem())
            raise
        texto, ok, alvo = (r, True, alvo) if isinstance(r, str) else r
        auditoria.registrar(nome_acao, alvo, "ok" if ok else "erro", time.monotonic() - inicio, texto[-300:], enviar,
                            quem())
        return texto

    def aprovada(nome_acao: str, alvo: str, argumentos: dict, aprovacao_id: str | None, descricao: str,
                 checar: Callable[[], None], executar: Callable[[], "str | tuple[str, bool, str]"]) -> str:
        """Todo cliente fora de OPS_CLIENTES_SEM_APROVACAO (agentes, assistente, desconhecido): a 1ª chamada cria
        o pedido e devolve o id; a 2ª, com aprovacao_id, só executa se o pedido estiver aprovado e for deste
        cliente e desta mesma ação. O Claude Code (aprovação na própria interface) executa direto."""
        if cliente() and cliente() in cfg.clientes_sem_aprovacao:
            return acao(nome_acao, alvo, executar)
        try:
            checar()  # protegidos e afins: recusa antes de incomodar o Léo
            if not aprovacao_id:
                p = aprovador.pedir(quem(), nome_acao, alvo, argumentos, descricao)
            else:
                aprovador.usar(aprovacao_id, quem(), nome_acao, alvo, argumentos)
        except Recusado as erro:
            auditoria.registrar(nome_acao, alvo, "recusado", 0.0, str(erro), enviar, quem())
            raise
        if aprovacao_id:
            return acao(nome_acao, alvo, executar)
        auditoria.registrar(nome_acao, alvo, "aguardando", 0.0, f"pedido {p['id']}", None, quem())
        return (f"Aguardando aprovação humana: pedido {p['id']}. O Léo decide pelo Telegram ou na tela de "
                f"aprovações (vale {p.get('validade_min', 30)} min). Não fique repetindo a chamada: espere o Léo dizer "
                f"que aprovou e então chame esta mesma ferramenta com os mesmos argumentos e "
                f"aprovacao_id=\"{p['id']}\". Se for recusado, não tente de novo.")

    # --- leitura ---
    def containers_listar(vm: str | None = None) -> str:
        """Lista os containers das VMs (core e ai): nome, imagem, estado e saúde. vm: 'core', 'ai' ou vazio."""
        return _tabela(portainer.containers(vm), ["vm", "nome", "imagem", "estado", "saude", "status"])

    def container_logs(nome: str, linhas: int = 200, vm: str | None = None) -> str:
        """Últimas linhas do log de um container (no máximo 500). Linhas com cara de segredo vêm mascaradas.
        vm ('core' ou 'ai') só é exigida quando o mesmo nome existe nas duas VMs."""
        return limpar_saida(portainer.logs(nome, max(1, min(linhas, 500)), vm), cfg.limite_saida)

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
        def container_reiniciar(nome: str, vm: str | None = None, aprovacao_id: str | None = None) -> str:
            """Reinicia um container. Containers do caminho de controle (Traefik, Authelia, Portainer, hub) são recusados.
            vm ('core' ou 'ai') só é exigida quando o mesmo nome existe nas duas VMs. Agentes autônomos recebem um
            pedido de aprovação e repetem a chamada com aprovacao_id depois que o Léo aprovar."""
            def fazer() -> str:
                checar_container(nome, cfg)
                portainer.reiniciar(nome, vm)
                return f"container {nome} reiniciado"
            return aprovada("container_reiniciar", nome, {"nome": nome, "vm": vm}, aprovacao_id,
                            f"reiniciar o container {nome}" + (f" na VM {vm}" if vm else ""),
                            lambda: checar_container(nome, cfg), fazer)

        def stack_redeploy(nome: str, puxar_imagens: bool = False, aprovacao_id: str | None = None) -> str:
            """Redeploy de uma stack do Portainer com o mesmo compose e variáveis; puxar_imagens baixa as versões do compose.
            Agentes autônomos recebem um pedido de aprovação e repetem a chamada com aprovacao_id."""
            def fazer() -> str:
                checar_stack(nome, cfg)
                portainer.redeploy(nome, puxar_imagens)
                return f"stack {nome} redeployada" + (" (imagens atualizadas)" if puxar_imagens else "")
            return aprovada("stack_redeploy", nome, {"nome": nome, "puxar_imagens": puxar_imagens}, aprovacao_id,
                            f"redeploy da stack {nome}" + (" baixando as imagens" if puxar_imagens else ""),
                            lambda: checar_stack(nome, cfg), fazer)

        def _runner() -> "Runner":
            if runner is None:
                raise Recusado("runner Ansible indisponível nesta instância")
            return runner

        def ansible_check(playbook: str, limite: str | None = None, aprovacao_id: str | None = None) -> str:
            """Simula um playbook (--check --diff) no commit atual do repositório e devolve o diff e um plano_id.
            Agentes autônomos também pedem aprovação aqui: mesmo em --check, o Ansible roda lookups, templates e
            tarefas com check_mode: false do commit que estiver no repositório, com a senha do vault."""
            def fazer() -> str:
                r = _runner().check(playbook, limite)
                texto = (f"plano_id: {r['plano_id']}\ncommit: {r['commit']} ({r.get('autor_assunto', '')})\n"
                         f"rc: {r['rc']}\n{r['saida']}")
                return texto, r["rc"] == 0, playbook

            def checar() -> None:
                if playbook not in cfg.playbooks:
                    raise Recusado(f"{playbook} não está em ops_playbooks_permitidos")
            return aprovada("ansible_check", playbook, {"playbook": playbook, "limite": limite}, aprovacao_id,
                            f"simular o playbook {playbook}" + (f" (limite {limite})" if limite else "")
                            + " no commit mais novo da main (o --check também roda código do repositório)",
                            checar, fazer)

        def ansible_aplicar(plano_id: str, aprovacao_id: str | None = None) -> str:
            """Aplica de verdade o playbook simulado pelo ansible_check (mesmo playbook, limite e commit; vale 30 min).
            Agentes autônomos recebem um pedido de aprovação e repetem a chamada com aprovacao_id."""
            def fazer() -> str:
                r = _runner().aplicar(plano_id)
                texto = f"playbook: {r['playbook']}\ncommit: {r['commit']}\nrc: {r['rc']}\n{r['saida']}"
                return texto, r["rc"] == 0, r["playbook"]

            def checar() -> None:
                if _runner().ver(plano_id) is None:
                    raise Recusado("plano inexistente ou já usado; rode ansible_check")
            plano = (runner.ver(plano_id) if runner else None) or {}
            descricao = (f"aplicar o playbook {plano.get('playbook', '?')}"
                         + (f" (limite {plano['limite']})" if plano.get("limite") else "")
                         + f" no commit {str(plano.get('commit', '?'))[:8]} ({plano.get('autor_assunto', '?')}),"
                         + f" simulado pelo ansible_check. {plano.get('recap', '')}")
            return aprovada("ansible_aplicar", plano_id, {"plano_id": plano_id}, aprovacao_id, descricao, checar, fazer)

        lista += [
            Ferramenta("container_reiniciar", container_reiniciar, True, container_reiniciar.__doc__),
            Ferramenta("stack_redeploy", stack_redeploy, True, stack_redeploy.__doc__),
            Ferramenta("ansible_check", ansible_check, False, ansible_check.__doc__),
            Ferramenta("ansible_aplicar", ansible_aplicar, True, ansible_aplicar.__doc__),
        ]
    return {f.nome: f for f in lista}
