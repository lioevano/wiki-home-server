# Design: homeserver como projeto gerenciado por Claude

- **Data:** 2026-10-07
- **Autor:** Léo Ivan (com Claude)
- **Status:** aguardando revisão
- **Caminho:** arquitetural (spec → plano de implementação → execução)

## 1. Objetivo

Transformar a pasta `homeserver/` em um repositório único (`lioevano/wiki-home-server`) no qual:

1. a **wiki MkDocs (`wiki/`) é a fonte da verdade** da infraestrutura;
2. o diretório **`server/`** contém a implementação (Ansible, Docker, scripts) e é mantido coerente com a wiki de forma **verificável**;
3. o Claude (Claude Code em Windows e Linux, e o app do Claude) opera o projeto com contexto próprio (`CLAUDE.md`), um **índice gerado** para consulta rápida e **skills** para as tarefas recorrentes;
4. o site publicado em `https://lioevano.github.io/wiki-home-server/` (GitHub Pages, branch `gh-pages`) continua funcionando, agora publicado por CI.

### Critérios de pronto

- `python tools/dev.py check` sem erros; todos os avisos foram decididos (corrigidos ou registrados como ignorados com justificativa).
- `python tools/dev.py build` (`mkdocs build --strict`) passa; o site tem a mesma navegação de hoje mais as correções listadas.
- `python tools/dev.py test` e `python tools/dev.py lint` passam (em Linux; no Windows o lint de Ansible é pulado com aviso).
- `INDEX.md` e `index.json` gerados e commitados.
- O Claude, aberto na raiz em qualquer máquina, responde "onde está X / o que faz Y" pelo `INDEX.md` e executa "adicione o serviço Z" seguindo uma skill.

## 2. Decisões tomadas

| # | Decisão | Escolha |
|---|---|---|
| D1 | Fonte da verdade | `wiki/`. Mudanças começam na wiki e são refletidas no `server/`. |
| D2 | Nível da verdade | **Híbrido**: blocos marcados com `title="<caminho>"` são verdade literal; o resto vale por estrutura (o que existe e como se relaciona). |
| D3 | Ambiente do Claude | Claude Code (`CLAUDE.md` + `.claude/skills/` versionados) **e** skills também propostas para a conta do usuário. |
| D4 | Repositório | Único: `lioevano/wiki-home-server`, com `wiki/` e `server/` lado a lado. |
| D5 | Wiki local × `main` remota | A wiki local (41 páginas, revisada) substitui a `main` (68 páginas). As 27 páginas removidas ficam no histórico do git. |
| D6 | Deploy | GitHub Action: `mkdocs gh-deploy -f wiki/mkdocs.yml` em push na `main`. |
| D7 | `server/terraform/` | Removido (vazio e não citado na wiki). |
| D8 | Scripts de validação obsoletos | `check_docs_integrity.py` e `apply_revision_fixes.py` removidos (substituídos por `wikisync`). Os demais ficam. |
| D9 | Plataforma | Windows **e** Linux: LF em todo o repo, ambiente via `tools/dev.py`, CI em Linux. |
| D10 | Vault | `vault.yml.example` (texto, placeholders) versionado; `vault.yml` real versionado **somente criptografado**; CI falha se não estiver. |

## 3. Estado atual (levantamento de 2026-10-07)

- `wiki/`: MkDocs Material, 41 páginas (~7,8 mil linhas), `venv/` criado no Windows (Python 3.14), sem git.
- `server/`: 57 arquivos (`ansible/`, `docker/stacks/{core,apps,ai}`, `scripts/`), `terraform/` vazio.
- Repo remoto `main` (último commit 2026-01-15): `docs/`, `mkdocs.yml`, `requirements.txt` (**UTF-16**, quebra `pip` em Linux), **`venv/` commitado**. `gh-pages` publicada em 2025-06-03.
- `mkdocs.yml`: `edit_uri` aponta para caminho inexistente; `nav` omite as páginas 07–13 de sustentação; `extra_css: stylesheets/extra.css` aponta para arquivo inexistente.
- **43 de 98 arquivos com CRLF**, incluindo templates Jinja implantados em Linux (ex.: `node_exporter_vm.service.j2`, `traefik.yml.j2`).
- `roles/apps/desktop-environment/main.yml` solto na raiz da role.
- Wiki cita `docker/stacks/.env.template`, `.gitignore` e `README.md` na raiz — inexistentes.
- **33 blocos de código** da wiki começam com comentário de caminho (`# ansible/...`): 17 idênticos ao `server/`, 13 diferentes, 2 ausentes no `server/`, 1 exemplo didático (detalhe na seção 9).
- `server/.../group_vars/all/vault.yml` é um **modelo em texto puro**, não um vault criptografado.

## 4. Layout alvo

```
homeserver/                         repo lioevano/wiki-home-server
├── CLAUDE.md                       contexto do projeto para o Claude
├── README.md                       o que é o repo, link do site, ponteiro para CLAUDE.md
├── INDEX.md                        GERADO por wikisync index
├── index.json                      GERADO por wikisync index
├── requirements-dev.txt            deps de desenvolvimento (inclui wiki/requirements.txt)
├── .gitignore  .gitattributes  .editorconfig
├── .claude/
│   ├── settings.json               permissões do projeto
│   └── skills/<nome>/SKILL.md      skills do projeto
├── .github/workflows/
│   ├── docs.yml                    test → check → build → gh-deploy
│   └── server-lint.yml             lint + check em mudanças de server/
├── docs/superpowers/               specs e planos (este arquivo)
├── tools/
│   ├── dev.py                      executor de tarefas multiplataforma
│   └── wikisync/                   pacote de sincronização wiki ↔ server
│       ├── config.yml
│       ├── __main__.py  cli.py  extract.py  check.py  apply.py  index.py
│       └── tests/ (fixtures/ + test_*.py)
├── wiki/
│   ├── CLAUDE.md
│   ├── mkdocs.yml
│   ├── requirements.txt            UTF-8, só dependências diretas, versões fixadas
│   └── docs/
└── server/
    ├── CLAUDE.md
    ├── ansible/
    ├── docker/stacks/ (.env.template, core/, apps/, ai/)
    └── scripts/
```

`.venv/` (raiz), `wiki/venv/`, `wiki/site/` e `.env` ficam fora do git.

## 5. Migração para o repositório único

1. Criar o repositório local sobre o histórico da `main` remota (fetch de `origin/main`), sem perder histórico.
2. `git mv docs wiki/docs`, `git mv mkdocs.yml wiki/mkdocs.yml`, `git mv requirements.txt wiki/requirements.txt`; `git rm -r --cached venv`.
3. Sobrescrever `wiki/` com o conteúdo local revisado (remove as 27 páginas antigas). Commit: "wiki: substitui pela versão revisada".
4. Adicionar `server/` (sem `terraform/`). Commit: "server: adiciona implementação".
5. Commit **só de normalização** (CRLF → LF, `+x` nos `.sh`, shebangs `#!/usr/bin/env bash`). Assim os diffs seguintes ficam legíveis.
6. Demais mudanças em commits temáticos (ferramenta, reconciliação, camada Claude, CI).
7. **Push feito pelo usuário** (esta sessão não tem escrita no GitHub). Antes do primeiro push, o usuário garante em *Settings → Actions → Workflow permissions* que o Action pode escrever (`contents: write`).

### Restrições de execução conhecidas

- O shell vinculado ao computador do usuário **não alcança o GitHub** (proxy 403). O fetch da `main` é feito no container de nuvem (leitura pública) e o resultado é transferido para a pasta do usuário como *git bundle*; alternativamente o usuário executa o fetch localmente com um comando fornecido.
- Nas pastas do usuário, deleção de arquivos exige permissão explícita (o git também apaga arquivos de lock); ela será solicitada uma vez, para a raiz `homeserver/`, no início da execução.

## 6. Ambiente multiplataforma

- **`.gitattributes`:** `* text=auto eol=lf`; `*.sh eol=lf`; `*.ps1 eol=crlf`; imagens/fontes `binary`.
- **`.editorconfig`:** `charset = utf-8`, `end_of_line = lf`, `insert_final_newline = true`, indentação 2 para YAML.
- **`requirements-dev.txt`:** `-r wiki/requirements.txt`, `pytest`, `yamllint`, `ansible-core ; sys_platform != "win32"`, `ansible-lint ; sys_platform != "win32"`.
- **`tools/dev.py`** (somente biblioteca padrão; detecta `.venv/Scripts` × `.venv/bin`):

| Tarefa | Ação |
|---|---|
| `setup` | cria `.venv/` na raiz e instala `requirements-dev.txt` |
| `serve` / `build` | `mkdocs serve` / `mkdocs build --strict` com `-f wiki/mkdocs.yml` |
| `check` | `wikisync check` |
| `sync` | `wikisync apply` (dry-run; repassa `--yes`/`--path`) |
| `index` | `wikisync index` |
| `test` | `pytest tools/wikisync/tests` |
| `lint` | `yamllint server/`, `ansible-lint` (perfil leve), `ansible-playbook --syntax-check` em cada playbook, `docker compose config -q` por stack (se docker existir); no Windows pula Ansible com aviso |

O CI chama exatamente essas tarefas.

## 7. `tools/wikisync`

### 7.1 Convenção de marcação

- Um bloco é **literal** quando o atributo `title` da cerca é um caminho relativo a `server/` iniciado por `ansible/`, `docker/` ou `scripts/`:
  ````
  ```yaml title="ansible/roles/common/tasks/main.yml"
  ...conteúdo exato do arquivo...
  ```
  ````
- O conteúdo do bloco é o conteúdo **exato** do arquivo (inclusive um eventual comentário de caminho na primeira linha, se o arquivo o tiver).
- Blocos sem `title` ou com `title` que não é caminho do server (ex.: `"Exemplo: ..."`, `"/etc/fstab (host)"`) são ilustrativos.
- Blocos dentro de admonitions/abas são extraídos com a indentação removida.
- Comparação normaliza CRLF→LF e ignora uma quebra de linha final.

### 7.2 `config.yml`

```yaml
server_roots: [ansible, docker, scripts]
ignore_paths:          # placeholders didáticos citados na wiki
  - "docker/stacks/novoservico/**"
  - "docker/stacks/NOME_DA_STACK/**"
  - "docker/stacks/nome_da_stack/**"
  - "ansible/roles/NOME_DO_ROLE/**"
  - "ansible/playbooks/meu_playbook_modificado.yml"
  - "ansible/roles/meu_role_modificado/**"
ignore_orphans: []     # arquivos do server conscientemente não documentados, com motivo
```

### 7.3 Comandos

**`check`** — relatório com severidade:

| Código | Verificação | Severidade |
|---|---|---|
| `LIT-DIFF` | bloco literal ≠ arquivo do server | erro |
| `LIT-MISSING` | bloco literal sem arquivo no server | erro |
| `LIT-DUP` | mesmo caminho em 2+ blocos com conteúdos diferentes | erro |
| `REF-MISSING` | caminho citado na wiki (código inline ou texto) inexistente no server | erro |
| `ORPHAN` | arquivo do server não citado por nenhuma página | aviso |
| `UNMARKED` | bloco cuja 1ª linha é comentário de caminho, mas sem `title` | aviso |
| `DESC` | página sem `description:` no front-matter | aviso |
| `LINK` | link relativo quebrado | erro |
| `NAV` | página fora do `nav` ou entrada do `nav` sem arquivo | erro |
| `VAULT` | `vault.yml` sem cabeçalho `$ANSIBLE_VAULT;` | erro |
| `EOL` | arquivo versionado com CRLF (exceto `*.ps1`) | erro |

Saída em texto ou `--json`. Código de saída: `0` sem erros (avisos permitidos), `1` com erros, `2` falha de uso/configuração.

**`apply`** — escreve blocos literais no server. Padrão **dry-run** com diff unificado; grava só com `--yes`; `--path <arquivo>` restringe a um arquivo; nunca apaga arquivos; sempre grava UTF-8 + LF.

**`index`** — gera `INDEX.md` e `index.json` (ver 8.2). Determinístico (ordenado), para diffs limpos.

### 7.4 Leitura do `mkdocs.yml`

PyYAML com loader que aceita tags desconhecidas (`!!python/name:...`), usado apenas para ler `nav`, `docs_dir` e `plugins`.

### 7.5 Testes

`pytest` com uma mini-wiki e um mini-server em `tests/fixtures/`, cobrindo: extração com/sem indentação, cada código do `check`, `ignore_paths`, normalização CRLF, `apply` dry-run × `--yes` × `--path`, determinismo do `index`.

## 8. Camada Claude

### 8.1 Arquivos de contexto

- **`/CLAUDE.md`** (< 150 linhas): propósito; **regra de ouro** (mudança → wiki → `dev.py check` → `dev.py sync --yes` → `dev.py lint`/`build` → commit); mapa de pastas; comandos de `tools/dev.py`; consultar `INDEX.md` antes de buscar no disco; regras de segurança (nunca commitar segredos; vault sempre criptografado; nunca rodar `ansible-playbook` sem `--check` contra hosts reais sem confirmação; nunca apagar arquivo do server sem justificativa na wiki; nunca editar `INDEX.md` à mão).
- **`/wiki/CLAUDE.md`**: numeração `NN-nome.md` por seção e atualização do `nav`; front-matter `description:` obrigatório; convenção `title=` para blocos literais e `title="Exemplo: ..."` para ilustrativos; links relativos; admonitions; português; validar com `dev.py build`.
- **`/server/CLAUDE.md`**: roles em `common/infra/apps/tools`; inventário `home`; segredos só em `vault.yml` com prefixo `vault_`; padrão `setup-<stack>-volumes.yml`; stacks com redes externas, labels do Traefik e middleware do Authelia; `.env.template` como contrato de variáveis; nenhum arquivo muda sem página correspondente na wiki.

### 8.2 Índice

- Cada página da wiki recebe `description:` (front-matter; o Material usa como meta description). Primeira redação pelo Claude, revisão pelo usuário.
- `INDEX.md`:
  1. **Páginas** — caminho, título (H1), descrição, arquivos do server que define (literal) ou cita.
  2. **Arquivos do server** — caminho, tipo (role/task/handler/template/playbook/stack/script/inventário), páginas que o citam, estado literal (✅ sincronizado / ⚠️ divergente / — estrutural).
  3. **Serviços** — de cada `docker-compose.yml`: serviço, imagem, stack, redes, host do Traefik (`Host(...)` nas labels).
  4. **Playbooks e roles** — playbook → hosts → roles usadas.
- `index.json`: mesmos dados, para skills e scripts.

### 8.3 Skills (`.claude/skills/<nome>/SKILL.md`, também propostas para a conta)

| Skill | Gatilho | Fluxo |
|---|---|---|
| `wiki-first-change` | qualquer pedido de mudança na infra | localizar no `INDEX.md` → editar wiki → `check` → `sync` → `lint`/`build` → commit |
| `sync-wiki-server` | triagem de saída do `check` | por código: decidir "wiki vence" (apply) × "server evoluiu" (atualizar wiki primeiro, depois apply) × documentar/remover órfão |
| `add-docker-service` | adicionar serviço | seção na wiki com bloco literal do compose, labels Traefik/Authelia, variáveis no `.env.template`, playbook de volumes, sync, index |
| `add-ansible-component` | nova role/playbook | estrutura por convenção, documentação na wiki com blocos literais, `syntax-check` |
| `wiki-page-authoring` | criar/editar página | numeração, `nav`, `description`, marcação `title=`, `build --strict` |
| `validate-infra` | validar antes de deploy/commit | `dev.py check`, `lint`, scripts de `server/scripts/validation/`, interpretação dos resultados |

### 8.4 `.claude/settings.json`

- **allow:** `python tools/dev.py *`, `git status|diff|log|add|commit`, `mkdocs build`, `ansible-playbook --syntax-check`/`--check`, `docker compose config`.
- **ask:** `ansible-playbook` (sem `--check`), `ansible-vault`, `ssh`, `docker compose up|down`, `git push`.

## 9. Reconciliação inicial

1. **Marcação:** converter os 33 comentários de caminho em `title="..."` (script). O bloco `novoservico` passa a `title="Exemplo: docker/stacks/novoservico/docker-compose.yml"`.
2. **Ausentes (criar a partir da wiki):** `ansible/roles/infra/proxmox-host-config/templates/etc_exports.j2`, `.../node_exporter_host.service.j2`.
3. **Divergentes (triagem com o usuário, diff + recomendação, em lotes por página):**
   `ansible/inventories/home/group_vars/all/main.yml`, `.../all/vault.yml` (ver D10), `ansible/inventories/home/hosts.ini`, `ansible/playbooks/full-deploy.yml`, `setup-core-networking.yml`, `setup-proxmox-host.yml`, `vm-deploy.yml`, `ansible/roles/common/tasks/main.yml`, `ansible/roles/infra/proxmox-host-config/tasks/main.yml`, `.../handlers/main.yml`, `ansible/roles/tools/ai-cli-tools/tasks/main.yml`, `docker/stacks/core/docker-compose.yml`.
   Regra: se a wiki está certa → `apply`; se o server evoluiu → atualizar o bloco da wiki primeiro, depois `apply` (a wiki continua sendo a verdade).
4. **Estrutural:** decidir cada `ORPHAN`; mover/remover `roles/apps/desktop-environment/main.yml`; criar `docker/stacks/.env.template` conforme a wiki; remover `terraform/` e os 2 scripts obsoletos.
5. **`mkdocs.yml`:** `edit_uri: edit/main/wiki/docs/`; incluir páginas 07–13 de sustentação no `nav`; criar `wiki/docs/stylesheets/extra.css` vazio **ou** remover `extra_css` (decidir na execução; padrão: remover).
6. **Vault:** `vault.yml` atual → `vault.yml.example`; wiki atualizada para refletir o par example/criptografado.

## 10. CI

- **`docs.yml`** — gatilho: push na `main` com mudança em `wiki/**`, `tools/**`, `requirements-dev.txt` ou no próprio workflow; também `workflow_dispatch`. `permissions: contents: write`. Passos: checkout com `fetch-depth: 0` (plugin de data de revisão) → Python → `dev.py setup` → `test` → `check` → `build` → `mkdocs gh-deploy --force -f wiki/mkdocs.yml`.
- **`server-lint.yml`** — gatilho: push/PR com mudança em `server/**`. Passos: `setup` → `lint` → `check`.

## 11. Fora de escopo

- Renomear o repositório.
- Revisar o conteúdo técnico das páginas além do necessário para a reconciliação.
- Executar playbooks ou subir stacks contra hosts reais.
- Recuperar as 27 páginas removidas (permanecem no histórico).

## 12. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| `apply` sobrescrever evolução feita no server | dry-run por padrão; triagem manual dos 13 divergentes; regra "server evoluiu → wiki primeiro" |
| Primeiro deploy pelo Action alterar o site | `build --strict` antes; comparar `nav` gerado; `gh-pages` antiga recuperável pelo histórico |
| Vault real em texto puro chegar ao git | `check` (`VAULT`) local e no CI; `.gitignore` para `*.decrypted*` |
| Falsos positivos de `REF-MISSING` em texto corrido | `ignore_paths` e regex restrita a caminhos sob `server_roots` |
| Divergência de ambiente Windows × Linux | LF forçado por `.gitattributes`; `dev.py` único; CI em Linux como referência |
