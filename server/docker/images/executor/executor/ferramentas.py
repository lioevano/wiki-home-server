"""As ferramentas MCP do executor. Tudo que muda a casa passa pelo Portão; segredos só vão ao Léo."""
from __future__ import annotations

import json
import shlex
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ops.ferramentas import Ferramenta
from ops.politica import Recusado, checar_limite

from .config import Config
from .portao import Portao
from .remoto import Remoto, validar_diagnostico
from .vault import Vault

MAX_COMANDO = 250  # o pedido no Telegram corta os argumentos em 300 caracteres: o Léo precisa ver o comando inteiro
MAX_JSON = 300  # quanto do JSON dos argumentos o texto do pedido mostra
JINJA = ("{{", "{%", "{#")
CONFIRMACAO = "comando enviado ao Léo pelo bot de aprovações"


def _entre_aspas(valor: str) -> str:
    """Sempre entre aspas simples (o Léo reconhece os argumentos); shlex.quote cuida das aspas internas."""
    q = shlex.quote(valor)
    return q if q.startswith("'") else f"'{q}'"


def ferramentas(cfg: Config, portao: Portao, remoto: Remoto, runner, canal,
                enviar_ao_leo: Callable[[str], None]) -> dict[str, Ferramenta]:
    def _runner():
        if runner is None:
            raise Recusado("runner Ansible indisponível nesta instância")
        return runner

    def diagnostico(host: str, comando: str) -> str:
        """Roda um comando de leitura num host do inventário, sem pedir aprovação. Só aceita as formas fixas de
        diagnóstico (systemctl status/is-active/list-units --failed, journalctl -u X -n N, docker ps/logs, df -h,
        free -m, uptime, ip, ss -tlnp, ping -c, tailscale status, cat /etc/os-release); o resto é recusado."""
        argv, become = validar_diagnostico(comando)
        rc, saida = remoto.rodar(host, argv, shell=False, become=become)
        return f"rc: {rc}\n{saida}"

    def comando(host: str, comando: str, aprovacao_id: str | None = None) -> str:
        """Roda um comando de shell, como root, num host do inventário. Exige aprovação do Léo no Telegram: a 1ª
        chamada cria o pedido e devolve o id; depois que o Léo aprovar, repita a chamada com o mesmo host, o mesmo
        comando e aprovacao_id. O comando tem no máximo 250 caracteres (o Léo precisa lê-lo inteiro); para algo maior,
        versione um script por PR."""
        if not isinstance(comando, str) or not comando.strip():
            raise Recusado("comando vazio")
        if len(comando) > MAX_COMANDO:
            raise Recusado(f"comando com {len(comando)} caracteres; o máximo é {MAX_COMANDO} (o Léo precisa vê-lo "
                           "inteiro antes de aprovar). Para algo maior, versione um script por PR")
        # O Léo lê json.dumps(argumentos, ensure_ascii=False)[:300] (aprovador/telegram.py): o JSON infla aspas e
        # barras, e caracteres invisíveis ou que reordenam o texto (U+202E, largura zero) esconderiam parte do comando.
        if any(unicodedata.category(c).startswith("C") or unicodedata.category(c) in ("Zl", "Zp") for c in comando):
            raise Recusado("comando com caractere de controle, invisível ou de direção de texto; escreva-o só com "
                           "caracteres visíveis, numa linha")
        if len(json.dumps({"host": host, "comando": comando}, ensure_ascii=False)) > MAX_JSON:
            raise Recusado(f"comando grande demais depois de escapado (aspas e barras invertidas contam em dobro; "
                           f"o Léo vê só {MAX_JSON} caracteres do pedido). Simplifique ou versione um script por PR")
        if any(m in comando for m in JINJA):
            raise Recusado("comando contém {{, {% ou {#: o Ansible interpretaria isso como Jinja no próprio executor")
        if host not in remoto.hosts():
            raise Recusado(f"host {host!r} não está no inventário")

        def fazer() -> str:
            rc, saida = remoto.rodar(host, comando, shell=True, become=True)
            return f"rc: {rc}\n{saida}"
        return portao.executar("comando", host, {"host": host, "comando": comando}, aprovacao_id,
                               f"rodar no host {host}, como root, o comando acima", fazer)

    def playbooks_listar() -> str:
        """Playbooks Ansible que podem ser simulados (ansible_check) e aplicados (ansible_aplicar)."""
        return "\n".join(f"{n}: {d}" for n, d in sorted(cfg.playbooks.items())) or "(nenhum)"

    def ansible_check(playbook: str, limite: str | None = None, aprovacao_id: str | None = None) -> str:
        """Simula um playbook (--check --diff) no commit atual do repositório e devolve o diff e um plano_id.
        Pede aprovação do Léo no Telegram: mesmo em --check, o Ansible roda lookups, templates e tarefas com
        check_mode: false do commit que estiver no repositório, com a senha do vault. Repita a chamada com
        aprovacao_id depois que o Léo aprovar. limite é um padrão de hosts do inventário (core-services-vm,
        core*:!ai), só com letras, números e _ . - , : ! & *."""
        if playbook not in cfg.playbooks:
            raise Recusado(f"{playbook} não está na lista de playbooks permitidos")
        checar_limite(limite)

        def fazer() -> str:
            r = _runner().check(playbook, limite)
            return (f"plano_id: {r['plano_id']}\ncommit: {r['commit']} ({r.get('autor_assunto', '')})\n"
                    f"rc: {r['rc']}\n{r['saida']}")
        return portao.executar("ansible_check", playbook, {"playbook": playbook, "limite": limite}, aprovacao_id,
                               f"simular o playbook {playbook}" + (f" (limite {limite})" if limite else "")
                               + " no commit mais novo da main (o --check também roda código do repositório)", fazer)

    def ansible_aplicar(plano_id: str, aprovacao_id: str | None = None) -> str:
        """Aplica de verdade o playbook simulado pelo ansible_check (mesmo playbook, limite e commit; o plano vale
        30 min). Pede aprovação do Léo no Telegram; repita a chamada com aprovacao_id depois que ele aprovar."""
        plano = _runner().ver(plano_id)
        if plano is None:
            raise Recusado("plano inexistente ou já usado; rode ansible_check")

        def fazer() -> str:
            r = _runner().aplicar(plano_id)
            return f"playbook: {r['playbook']}\ncommit: {r['commit']}\nrc: {r['rc']}\n{r['saida']}"
        descricao = (f"aplicar o playbook {plano.get('playbook', '?')}"
                     + (f" (limite {plano['limite']})" if plano.get("limite") else "")
                     + f" no commit {str(plano.get('commit', '?'))[:8]} ({plano.get('autor_assunto', '?')}),"
                     + f" simulado pelo ansible_check. {plano.get('recap', '')}")
        return portao.executar("ansible_aplicar", plano_id, {"plano_id": plano_id}, aprovacao_id, descricao, fazer)

    def vault_preencher(chave: str) -> str:
        """Pede ao Léo, pelo Telegram, o valor de uma chave do vault (nome com ponto, como em grupo.chave). A resposta
        do Léo é a aprovação: o valor vai direto para o vault e você nunca o vê. Consulte com vault_status."""
        return canal.pedir(chave)

    def vault_status() -> str:
        """Atualiza a main do executor (git pull) e diz a situação dos pedidos de segredo (pendentes e gravados), quando
        o saida/vault.yml foi atualizado, se ele tem edições pendentes sobre a main (só então ele vira PR, e só se o
        vault.yml na base do branch do PR tiver o sha256 da base informada) e as chaves que o Léo preencheu mas a main
        também mudou (não reaplicadas: peça de novo as que ainda valem)."""
        arquivo = Path(cfg.saida_dir) / "vault.yml"
        atualizada = False
        if runner is None:
            main = "main do executor não atualizada (sem runner)"
        else:
            try:                                        # a main de agora: senão um PR já mesclado passaria por pendente
                main = f"main do executor atualizada ({runner.atualizar()[:8]})"
                atualizada = True
            except Exception as erro:  # noqa: BLE001 — Recusado (ocupado, git) ou falha ao rodar o git
                motivo = str(erro) if isinstance(erro, Recusado) else type(erro).__name__
                main = f"não atualizei a main do executor ({motivo}); este status pode estar atrasado"
        try:
            origem, conflitos = Vault(cfg).situacao()   # pode reaplicar edições sobre a main nova ou encerrar o saida/
            if origem == arquivo:
                quando = datetime.fromtimestamp(arquivo.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
                try:
                    base = (Path(cfg.saida_dir) / ".base").read_text(encoding="utf-8").splitlines()[0].strip()
                except (OSError, IndexError):
                    base = "ausente"                    # a entrada do bucket, ainda sem edição
                rodape = f"saida/vault.yml atualizado em {quando}; edições pendentes sobre a main (base {base})"
                if atualizada:
                    rodape += ("; abra o PR do vault com ele, num branch cujo vault.yml tenha esse sha256 "
                               "(\"ausente\": sem vault.yml), e não abra se não tiver")
                else:
                    rodape += "; não abra o PR do vault agora: tente o vault_status de novo"
            else:
                rodape = "nenhuma edição pendente: vale o vault da main (não há PR do vault a abrir)"
            if conflitos:
                rodape += ("\na main também mudou estas chaves preenchidas pelo Léo (vale a main; peça de novo as que "
                           "ainda valem): " + ", ".join(conflitos))
        except Exception as erro:  # noqa: BLE001 — só o tipo do erro
            rodape = f"não consegui ler o vault ({type(erro).__name__}); não abra o PR do vault agora"
        return f"{canal.status()}\n{main}\n{rodape}"

    def preparar_host() -> str:
        """Envia ao Léo, pelo bot de aprovações, o comando único que ele cola no console do host Proxmox (instala o
        Tailscale com a chave de uso único, cria o usuário do Ansible e autoriza a chave SSH do sysadmin). Nada disso
        volta para você."""
        try:
            pub = Path(cfg.chave_ssh + ".pub").read_text(encoding="utf-8").strip()
        except OSError:
            raise Recusado("não consegui ler a chave pública do sysadmin") from None
        args = " ".join(_entre_aspas(v) for v in (cfg.tailscale_chave_host, pub, cfg.ansible_usuario_host, cfg.rotas))
        texto = f"curl -fsSL {cfg.repo_url_raw.rstrip('/')}/server/scripts/gcp/preparar-host.sh | bash -s -- {args}"
        try:
            enviar_ao_leo(texto)
        except OSError:
            raise Recusado("não consegui enviar o comando pelo Telegram") from None
        return CONFIRMACAO

    lista = [Ferramenta(f.__name__, f, destrutiva, f.__doc__) for f, destrutiva in (
        (diagnostico, False), (comando, True), (playbooks_listar, False), (ansible_check, False),
        (ansible_aplicar, True), (vault_preencher, False), (vault_status, False), (preparar_host, False))]
    return {f.nome: f for f in lista}
