# homeserver — guia para agentes de IA

Este arquivo é a entrada canônica para qualquer LLM ou agente (Claude Code, Codex, Gemini CLI, Copilot, Cursor…). O `CLAUDE.md` apenas o importa.

Repositório único (`lioevano/wiki-home-server`) do servidor doméstico do Léo Ivan:
Proxmox VE + ZFS/NFS, Ansible, Docker/Portainer, Traefik, Cloudflare Tunnel e Authelia.

- `wiki/` — documentação MkDocs, **fonte da verdade** da infraestrutura. Publicada em
  https://wiki.lioevano.com/ pelo GitHub Actions (branch `gh-pages`; domínio próprio via `wiki/docs/CNAME`).
- `server/` — implementação (Ansible, stacks Docker, scripts). **Reflete a wiki.**
- `tools/` — `dev.py` (executor de tarefas) e `wikisync` (verificação/sincronização wiki → server).

## Regra de ouro

Toda mudança na infraestrutura começa na wiki:

1. Localize o assunto no `INDEX.md` (página ↔ arquivos do server ↔ serviços).
2. Edite a página da wiki (texto e, se for o caso, o bloco literal do arquivo).
3. `python tools/dev.py check` — veja as divergências.
4. `python tools/dev.py sync` (dry-run) → confira o diff → `python tools/dev.py sync --yes`.
5. `python tools/dev.py build` e `python tools/dev.py lint`.
6. Skill `update-index` e commit (wiki + server + índice juntos).

Nunca altere um arquivo do `server/` sem a página correspondente na wiki justificar a mudança.
Use as skills do projeto (`.agents/skills/`, tabela abaixo) — elas descrevem esses fluxos passo a passo.

## Blocos literais

Na wiki, um bloco de código com `title="<caminho relativo a server/>"` (iniciado por
`ansible/`, `docker/` ou `scripts/`) é o **conteúdo exato** daquele arquivo:

````markdown
```yaml title="ansible/roles/common/tasks/main.yml"
...conteúdo exato...
```
````

- `title="Exemplo: ..."` e `title="Trecho: ..."` são ilustrativos (não sincronizam).
- Arquivos sem bloco literal valem pela estrutura: precisam existir e ser citados por alguma página.

## Comandos (`python tools/dev.py <tarefa>`, Windows e Linux)

| Tarefa | O que faz |
|---|---|
| `setup` | cria o ambiente (`.venv/` ou `$HOMESERVER_VENV`) e instala `requirements-dev.txt` |
| `serve` | wiki local em http://127.0.0.1:8000 |
| `build` | `mkdocs build --strict` (falha com qualquer aviso) |
| `check` | `wikisync check`: divergências wiki ↔ server (código 1 = há erros) |
| `sync` | `wikisync apply` em dry-run; `--yes` grava; `--path <arquivo>` restringe |
| `test` | testes do `wikisync` |
| `lint` | yamllint, ansible-lint, `--syntax-check` e `docker compose config` com as variáveis do `.env.template` (falha se o compose usar variável fora dele; Ansible só fora do Windows) |

Códigos do `check`: `LIT-DIFF`, `LIT-MISSING`, `LIT-DUP`, `REF-MISSING`, `LINK`, `NAV`, `VAULT`, `EOL`
são **erros**; `ORPHAN`, `UNMARKED`, `DESC`, `REF-PENDING` são avisos (`REF-PENDING` = arquivo listado em `pending_files`, como o `vault.yml`, que o usuário só cria após consolidar wiki e server — não é pendência sua). Configuração em `tools/wikisync/config.yml`.

## Onde procurar

- **Antes de buscar no disco, leia `INDEX.md`.** Ele é mantido pela skill `update-index` — atualize-o por ela.
- Convenções da wiki: `wiki/AGENTS.md`. Convenções do Ansible/Docker: `server/AGENTS.md`.
- Aplicações e integrações: `wiki/docs/02-visao-geral-arquitetura/09-catalogo-aplicacoes.md` (catálogo) e `wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md` (índice de integrações).
- Decisões de projeto: `docs/superpowers/specs/` e `docs/superpowers/plans/`.

## Segurança — sempre

- Nunca commite segredos. `server/ansible/inventories/home/group_vars/all/vault.yml` só entra no git
  **criptografado** (`$ANSIBLE_VAULT;...`); o modelo é `vault.yml.example`. O `check` e o CI falham se não estiver.
- `.env` reais das stacks nunca são versionados; o contrato é `server/docker/stacks/.env.template`.
- Não execute `ansible-playbook` contra hosts reais sem `--check`/`--syntax-check`, nem `ansible-vault`,
  `ssh`, `docker compose up/down` ou `git push`, sem confirmação explícita do usuário.
- Não apague arquivos do `server/` sem que a wiki justifique a remoção.

## Convenções gerais

- Português em docs, mensagens de commit e textos para o usuário.
- UTF-8 sem BOM e LF em todos os arquivos (`.gitattributes`); exceção: `*.ps1`.
- Commits pequenos e temáticos; wiki, server e índice da mesma mudança vão juntos.
- O site é publicado automaticamente pelo workflow `docs` a cada push na `main` que altere `wiki/` ou `tools/`.

## Skills

Cada skill é um `SKILL.md` em `.agents/skills/<nome>/` (formato Agent Skills). Se a sua ferramenta não carrega skills sozinha, **leia o arquivo da skill indicada antes de começar a tarefa**.

| Skill | Quando usar | Caminho |
|---|---|---|
| `wiki-first-change` | qualquer mudança na infraestrutura ou na wiki | `.agents/skills/wiki-first-change/SKILL.md` |
| `sync-wiki-server` | `dev.py check` com erros ou avisos | `.agents/skills/sync-wiki-server/SKILL.md` |
| `wiki-page-authoring` | criar, renomear ou editar páginas da wiki | `.agents/skills/wiki-page-authoring/SKILL.md` |
| `add-ansible-component` | criar role, playbook, grupo ou variável Ansible | `.agents/skills/add-ansible-component/SKILL.md` |
| `validate-infra` | antes de commitar ou entregar mudanças | `.agents/skills/validate-infra/SKILL.md` |
| `audit-integrations` | verificar integrações (catálogo × índice × arquivos) | `.agents/skills/audit-integrations/SKILL.md` |
| `update-index` | manter o `INDEX.md` em dia (fim de toda mudança) | `.agents/skills/update-index/SKILL.md` |
| `add-app` | adicionar uma aplicação | `.agents/skills/add-app/SKILL.md` |
| `remove-app` | remover uma aplicação | `.agents/skills/remove-app/SKILL.md` |
| `add-integration` | criar uma integração e ligá-la em todos os consumidores | `.agents/skills/add-integration/SKILL.md` |
| `remove-integration` | desligar uma integração de todos e remover o provedor | `.agents/skills/remove-integration/SKILL.md` |
| `fix-integrations` | corrigir achados da auditoria e gerar variáveis que faltam | `.agents/skills/fix-integrations/SKILL.md` |
