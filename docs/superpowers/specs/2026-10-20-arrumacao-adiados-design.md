# Design: arrumação dos itens adiados (guias, nomes, apps.env, Portainer)

- **Data:** 2026-10-20
- **Autor:** Léo Ivan (com Claude)
- **Status:** decidido de forma autônoma, a pedido do Léo ("pode seguir da mesma forma autônoma com os demais pontos").
- **Caminho:** arquitetural leve. Renomeia arquivos do `server/`, remove um role e um dataset do Ansible e reorganiza a seção de guias.
- **Origem:** "Itens adiados" do `contexto-homeserver.md` e as sugestões da rodada de pendências menores.

## 1. Objetivo

Deixar a wiki e o `server/` coerentes com o que foi construído nos sub-projetos 1 a 4c1, antes do primeiro deploy:

- tirar nomes e peças que não servem mais;
- fazer os guias genéricos refletirem o fluxo "wiki primeiro";
- automatizar o único passo manual que sobrava no deploy da stack `apps`.

### Critérios de pronto

- `test`, `check` (só o `REF-PENDING`), `build` estrito e `lint` passam.
- Nenhuma página fora do manual usa `{{ base_domain }}` em prosa ou em exemplo de compose (teste novo).
- Guias e manutenção numerados sem buraco (teste novo).
- O `full-deploy.yml` cobre todos os `setup-*-volumes.yml` (teste novo).
- `INDEX.md` atualizado.

## 2. Decisões

| # | Item | Decisão |
|---|---|---|
| A1 | Fundir os guias 03/01 e 03/09 | O 03/01 foi reescrito e cobre stack nova **e** existente: pesquisa → catálogo → integrações → página → compose e playbook (exemplo) → validação → deploy, com os erros comuns. O 03/09 saiu. Os guias 10–12 viraram 09–11, sem buraco na numeração. |
| A2 | Guia 03/13 e role `ai-cli-tools` (Gemini CLI) | **Removidos.** O role nunca entrou em nenhum playbook, e o caminho escolhido para IA operando o servidor é o Claude Code com o hub de MCPs (página 13), com aprovação e auditoria. Instalar outra CLI com acesso de shell nas VMs iria contra essa decisão. A categoria `roles/tools/` sai do `server/AGENTS.md`. |
| A3 | Nome legado "rag" | `dynamic_rag_services.yml.j2` vira `dynamic_ai_services.yml.j2`, gravado como `ai_services.yml`. Uma tarefa apaga o `rag_services.yml` antigo, senão o Traefik carregaria os routers em dobro. O dataset `rag_sources` sai do Ansible (variável, montagem, export NFS, script de validação): nada o usava, e os documentos agora vêm do `files` do Nextcloud pelo segundo cérebro. Como nada foi implantado, não há dataset a migrar. |
| A4 | Guias genéricos (03/02–08, 03/10, 03/11, 04/04, 04/05, 02/01) | Correções pontuais em vez de reescrita: `seudominio.com` em prosa e `${BASE_DOMAIN_FROM_VAULT}` nas labels; opções de montagem NFS atuais; Grafana/Loki como primeiro lugar para ler logs (03/03); fluxo wiki-first no 03/02; IPs que mudam numa troca de rede (04/05). |
| A5 | 03/11 (agora 03/10): hostname do domínio raiz | O curinga `*` do túnel não cobre o domínio raiz. O guia agora pede um Public Hostname com subdomínio vazio e explica que o Authelia não entra (a regra curinga não casa com o domínio raiz). Saiu também o `securityHeaders@file` no router, que já é global no entrypoint. |
| A6 | 04/03 (CI/CD) | Reescrita com o que existe: `dev.py`, os workflows `docs` e `server-lint`, deploy manual com `--check`, o `ops` como CD assistido. O `full-deploy.yml` (literal) passa a incluir os playbooks de photos, cloud, notes, langfuse e agents (faltavam desde os sub-projetos 3 e 4), e o `restore.sh` virou bloco literal. |
| A7 | 02/07 (estratégia de LLM) | O diagrama antigo (roteamento "inteligente" por tamanho de prompt, Gemini primeiro) foi trocado pelo fluxo real: chaves por cliente → apelidos → provedores, reservas, Prometheus e Langfuse. |
| A8 | Fluxo do `apps.env` | `ansible/playbooks/tasks/apps-env.yml`, incluído no fim dos três playbooks da stack `apps`, junta os quatro `.env` sem nomes repetidos (`0600`, `no_log`). A junção à mão sai da página 07. |
| A9 | Primeiro acesso ao Portainer | Seção nova na página 07: administrador nos primeiros 5 minutos, ambientes `local` e `ai-desktop-vm` (Agent :9001, nomes que o `ops` procura), token de API. Também explica que o "Load variables from .env file" lê um arquivo do **computador**: o `.env` da VM é colado em **Advanced mode**. As páginas que mandavam "carregar" o `.env` passam a apontar para esse procedimento. |
| A10 | `n8n_subdomain` × literal `n8n` | Fica como está, com o aviso no `main.yml` (decidido na rodada anterior). |
| A11 | Teste real do `get_http_headers` do `ops` | Adiado: exigiria o FastMCP no `requirements-dev.txt`, com várias dependências, só para um teste. A revisão anterior conferiu a API no FastMCP 4.1.2. |

## 3. Achados para as próximas rodadas

- **Postgres do Authelia e do Grafana no NFS** (`authelia/db_pg`, `grafana/db_pg`). A regra DAD-5 manda banco para o disco local com dump. Fica para a rodada de **backup**, que mexe nos dumps de todos os bancos.
- A página de backup (04/02) ainda cita o `rag_sources`. Ela é reescrita na rodada de backup.
