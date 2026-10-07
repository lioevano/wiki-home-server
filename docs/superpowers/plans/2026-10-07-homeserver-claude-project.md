# homeserver como projeto gerenciado por Claude — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unificar `wiki/` + `server/` no repo `lioevano/wiki-home-server`, com a wiki como fonte da verdade verificada por `tools/wikisync`, ambiente multiplataforma, camada Claude (CLAUDE.md, índice gerado, skills) e deploy da wiki por GitHub Actions.

**Architecture:** Repositório montado sobre o histórico da `main` remota. `tools/wikisync` (pacote Python) extrai blocos `title="<caminho>"` da wiki, verifica/aplica no `server/` e gera `INDEX.md`/`index.json`. `tools/dev.py` é o executor único de tarefas, chamado igualmente por humanos, pelo Claude e pelo CI.

**Tech Stack:** Python ≥ 3.10 (stdlib + PyYAML), pytest, MkDocs 1.6 + Material, yamllint, ansible-core/ansible-lint (só não-Windows), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-07-homeserver-claude-project-design.md`

## Global Constraints

- Python mínimo **3.10** (máquina Linux do usuário tem 3.10.12; Windows tem 3.14). Sem dependências além de stdlib + PyYAML em `tools/`.
- Todo arquivo versionado em **UTF-8 sem BOM e LF**; exceção `*.ps1` (CRLF).
- Textos voltados ao usuário (docs, CLAUDE.md, skills, mensagens do `wikisync`) em **português**.
- `wikisync`: códigos de saída `0` sem erros (avisos permitidos), `1` com erros, `2` uso/configuração.
- `wikisync apply` é **dry-run por padrão**, grava só com `--yes`, **nunca apaga** arquivos.
- Raízes literais do server: `ansible/`, `docker/`, `scripts/` (relativas a `server/`).
- Nada de `ansible-playbook` sem `--check`/`--syntax-check`, `docker compose up`, `ssh` ou `git push` executado pelo agente.
- Commits terminam com:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_011krkx9xaitppbasvkkgk5w
  ```

## Ambiente de execução (ler antes da Task 1)

- Os arquivos estão **no computador do usuário**: operar via `device_bash` em `$HOME/mnt/homeserver` (Linux, Python 3.10.12, git 2.34, `pip` funciona, sem docker/ansible instalados). Read/Write/Edit locais do container **não** alcançam essa pasta.
- O shell do usuário **não alcança o GitHub** (proxy 403). Leitura da `main` remota é feita no container de nuvem (`git clone` público funciona lá) e transferida como *git bundle* via `device_commit_files` (o arquivo deve estar em `/mnt/user-data/outputs/`).
- Deleção na pasta do usuário exige permissão: chamar `device_request_delete_permission` para a raiz `homeserver/` **uma vez**, no início da Task 1 (git também apaga arquivos de lock).
- Identidade git local do repo: `user.name "Léo Ivan"`, `user.email leoivan.gru@gmail.com`.
- Push e configuração do GitHub são do usuário (Task 14).

## Review Focus

1. **Cercas aninhadas** (```` ```` ```` contendo ```` ``` ````, comum em páginas que ensinam markdown): a cerca só fecha com a mesma sequência e comprimento ≥ ao de abertura — testado na Task 3.
2. **Atributos da cerca em outras formas** (`title='...'`, `{ .yaml title="..." linenums="1" }`): o `title` deve ser reconhecido igual — testado na Task 3.
3. **Arquivo com BOM ou CRLF vindo do Windows** em wiki ou server: comparação literal ignora BOM e CRLF (o `EOL` acusa separadamente) — testado na Task 4.
4. **`nav` com links externos e seções aninhadas**: `NAV` ignora URLs `http(s)://` e percorre qualquer profundidade — testado na Task 4.
5. **`wikisync` chamado de outro diretório ou sem `--root`**: raiz padrão = repo que contém `tools/wikisync/config.yml`; config ausente → código 2 com mensagem clara — testado na Task 4.

---

### Task 1: Repositório único sobre o histórico da `main`

**Files:**
- Create: `.gitignore`
- Move (git): `docs/` → `wiki/docs/`, `mkdocs.yml` → `wiki/mkdocs.yml`, `requirements.txt` → `wiki/requirements.txt`
- Remove do índice: `venv/`; Remove do disco: `server/terraform/`

**Interfaces:**
- Produces: repo git em `homeserver/` com remote `origin = https://github.com/lioevano/wiki-home-server.git`, branch `main` descendente de `origin/main`.

- [ ] **Step 1: Pedir permissão de deleção** para a raiz `homeserver/` (`device_request_delete_permission`, motivo: "git cria/apaga arquivos de lock e a migração remove server/terraform").
- [ ] **Step 2: Criar bundle no container.** `git clone https://github.com/lioevano/wiki-home-server /tmp/.../src` (clone completo, sem `--filter`), `git -C src bundle create /mnt/user-data/outputs/wiki-home-server-main.bundle main`, `git bundle verify`. Expected: "is okay".
- [ ] **Step 3: Transferir** com `device_commit_files` para `<homeserver>/../wiki-home-server-main.bundle` (fora do repo).
- [ ] **Step 4: Inicializar no device.**
  ```bash
  cd ~/mnt/homeserver
  git init -b main
  git config user.name "Léo Ivan"; git config user.email leoivan.gru@gmail.com
  git remote add origin https://github.com/lioevano/wiki-home-server.git
  git fetch ../wiki-home-server-main.bundle main:refs/remotes/origin/main
  git reset origin/main          # índice = main remota; árvore = conteúdo local
  ```
  Expected: `git log --oneline | head -1` mostra `9e207b0 praque`.
- [ ] **Step 5: Escrever `.gitignore`** com: `.venv/`, `venv/`, `wiki/venv/`, `wiki/site/`, `site/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.env`, `*.retry`, `*.decrypted*`, `.DS_Store`.
- [ ] **Step 6: Commit da wiki.** `rmdir server/terraform`; `git rm -r -q --cached venv docs mkdocs.yml requirements.txt`; `git show origin/main:requirements.txt > wiki/requirements.txt` (conteúdo provisório, reescrito na Task 2); `git add .gitignore wiki/docs wiki/mkdocs.yml wiki/requirements.txt docs/superpowers`. Commit: `wiki: move para wiki/ e substitui pela versão revisada`.
  Expected: `git show --stat HEAD` lista renomeações `docs/… → wiki/docs/…` e 27 páginas removidas; `git ls-files | grep -c '^venv/'` = 0.
- [ ] **Step 7: Commit do server.** `git add server` → `server: adiciona implementação (ansible, docker, scripts)`. Expected: `git status --short` vazio (exceto `wiki/venv/` ignorado).

### Task 2: Normalização, ambiente de desenvolvimento e `mkdocs.yml`

**Files:**
- Create: `.gitattributes`, `.editorconfig`, `.yamllint`, `requirements-dev.txt`, `tools/dev.py`
- Modify: `wiki/requirements.txt` (reescrito UTF-8), `wiki/mkdocs.yml`, `server/scripts/validation/check_nfs_permissions.sh:1`, `server/scripts/validation/validate_infrastructure.sh:1`

**Interfaces:**
- Produces: `python tools/dev.py <tarefa> [args…]` com tarefas `setup, serve, build, check, sync, index, test, lint`. `check/sync/index` executam `<venv-python> -m wikisync <check|apply|index> [args…]` com `PYTHONPATH=tools` e `cwd=raiz`; `test` executa `pytest tools/wikisync/tests -q`. Funções: `repo_root() -> Path`, `venv_python() -> Path` (`.venv/Scripts/python.exe` no Windows, `.venv/bin/python` nos demais), `run(cmd: list[str], **kw) -> int`. Código de saída do processo filho é repassado.

- [ ] **Step 1: Commit de normalização.** Criar `.gitattributes` (`* text=auto eol=lf`, `*.sh text eol=lf`, `*.ps1 text eol=crlf`, `*.png *.jpg *.jpeg *.gif *.ico *.woff *.woff2 *.bundle binary`) e `.editorconfig` (raiz: `charset=utf-8`, `end_of_line=lf`, `insert_final_newline=true`; `[*.{yml,yaml,j2}] indent_size=2`). Converter CRLF→LF nos arquivos de trabalho (`sed -i 's/\r$//'` nos 43 arquivos listados por `grep -rlI $'\r' server wiki/docs`), trocar shebang `#!/bin/bash` → `#!/usr/bin/env bash` nos 2 scripts, `git add --renormalize .`, `git update-index --chmod=+x` em todo `server/**/*.sh`. Commit: `chore: normaliza LF, UTF-8 e permissões de execução`.
  Expected: `grep -rlI $'\r' server wiki/docs | wc -l` = 0; `git ls-files -s server/scripts/bootstrap.sh` começa com `100755`.
- [ ] **Step 2: Dependências.** `wiki/requirements.txt` (UTF-8) só com diretas e versões do freeze atual: `mkdocs==1.6.1`, `mkdocs-material==9.7.1`, `mkdocs-mermaid2-plugin==1.2.3`, `mkdocs-glightbox` (fixar última versão compatível; o plugin `glightbox` está em uso e faltava no freeze), `mkdocs-git-revision-date-localized-plugin==1.5.0`, `pymdown-extensions==10.20`. `requirements-dev.txt`: `-r wiki/requirements.txt`, `pytest>=8`, `PyYAML>=6`, `yamllint>=1.35`, `ansible-core>=2.17,<2.18 ; sys_platform != "win32"`, `ansible-lint>=24 ; sys_platform != "win32"`.
- [ ] **Step 3: `tools/dev.py`** com a interface acima. `setup`: cria `.venv` (`python -m venv`) se ausente e `pip install -r requirements-dev.txt`. `serve`/`build`: `mkdocs serve|build --strict -f wiki/mkdocs.yml`. `lint`: `yamllint -c .yamllint server/`; se não-Windows, `ansible-lint --profile min` e, para cada `server/ansible/playbooks/*.yml`, `ansible-playbook -i localhost, --syntax-check <pb>` com `cwd=server/ansible` (inventário inline evita carregar o vault); se `docker` estiver no PATH, `docker compose -f <stack>/docker-compose.yml config -q` para cada stack. No Windows imprime "lint de Ansible ignorado no Windows (use WSL/Linux ou o CI)". `.yamllint`: `extends: default`, desativar `line-length`, `document-start`, `truthy` com `allowed-values: ['true','false','yes','no']`, `comments-indentation: disable`, ignorar `*.j2`.
- [ ] **Step 4: Corrigir `wiki/mkdocs.yml`:** `edit_uri: 'edit/main/wiki/docs/'`; incluir no `nav` de Sustentação as páginas 07–13 (títulos curtos: 'Cenários de VMs', 'Recursos entre VMs', 'Integrando Serviços', 'Atualização Segura', 'App no Domínio Raiz', 'Snapshots ZFS', 'Gemini CLI'); remover `extra_css`.
- [ ] **Step 5: Verificar.** `python3 tools/dev.py setup` → sucesso; `python3 tools/dev.py build` → `INFO - Documentation built` sem `WARNING`. Se `--strict` falhar por links/âncoras quebrados, corrigir o link na página (correção mínima) e registrar a lista no commit.
- [ ] **Step 6: Commit** `chore: ambiente multiplataforma (dev.py, requirements) e correções do mkdocs.yml`.

### Task 3: `wikisync` — configuração e extração

**Files:**
- Create: `tools/wikisync/__init__.py`, `tools/wikisync/config.yml`, `tools/wikisync/config.py`, `tools/wikisync/extract.py`, `tools/wikisync/tests/conftest.py`, `tools/wikisync/tests/test_extract.py`

**Interfaces:**
- Produces:
  - `config.py`: `@dataclass Config(root: Path, wiki_dir: Path, docs_dir: Path, mkdocs_file: Path, server_dir: Path, server_roots: list[str], ignore_paths: list[str], ignore_orphans: dict[str, str], exclude_dirs: list[str])`; `load_config(root: Path) -> Config` (lê `root/tools/wikisync/config.yml`; levanta `ConfigError` se ausente); `is_ignored(path: str, cfg) -> bool` (fnmatch sobre `ignore_paths`, e qualquer caminho contendo `...`).
  - `extract.py`: `@dataclass Block(page: str, line: int, lang: str, title: str | None, content: str)`; `extract_blocks(text: str, page: str) -> list[Block]`; `literal_path(block: Block, cfg: Config) -> str | None`; `page_refs(text: str, cfg: Config) -> set[str]`; `page_meta(text: str) -> tuple[str | None, str | None]` (título H1, `description` do front-matter); `load_mkdocs(path: Path) -> dict`; `nav_pages(nav: list) -> list[str]`; `normalize(text: str) -> str` (remove BOM, CRLF→LF, remove `\n` finais).
  - `conftest.py`: fixture `make_repo(files: dict[str, str]) -> Path` que cria a árvore em `tmp_path`, incluindo um `tools/wikisync/config.yml` e `wiki/mkdocs.yml` mínimos quando não fornecidos.
- `config.yml` inicial: `wiki_dir: wiki`, `server_dir: server`, `server_roots: [ansible, docker, scripts]`, `ignore_paths` exatamente como na seção 7.2 do spec, `ignore_orphans: {}`, `exclude_dirs: [.git, .venv, venv, wiki/venv, wiki/site, site, __pycache__, .pytest_cache, node_modules]`.

- [ ] **Step 1: Testes que falham** em `test_extract.py`:
  - `test_extracts_titled_block`: ```` ```yaml title="ansible/a.yml"\nx: 1\n``` ```` → `title == "ansible/a.yml"`, `content == "x: 1"`, `lang == "yaml"`, `line == 1`.
  - `test_dedents_block_inside_admonition`: bloco indentado 4 espaços sob `!!! note` → `content == "x: 1"`.
  - `test_nested_fence_closes_only_on_matching_length` (Review Focus 1): bloco de 4 crases contendo um bloco de 3 → 1 bloco externo cujo conteúdo inclui as 3 crases internas.
  - `test_title_variants` (Review Focus 2): `title='ansible/a.yml'` e `{ .yaml title="ansible/a.yml" linenums="1" }` → ambos `title == "ansible/a.yml"`, segundo com `lang == "yaml"`.
  - `test_literal_path_rules`: `"Exemplo: docker/x.yml"` → `None`; `"/etc/fstab"` → `None`; `"docker/stacks/core/docker-compose.yml"` → ele mesmo; `"docker/stacks/novoservico/docker-compose.yml"` → `None` (ignore_paths).
  - `test_page_refs`: texto "`ansible/playbooks/a.yml`, veja docker/stacks/core/. e docker/stacks/.../" → `{"ansible/playbooks/a.yml", "docker/stacks/core/"}`.
  - `test_page_meta`: `"---\ndescription: D\n---\n# T\n"` → `("T", "D")`; sem front-matter → `("T", None)`.
  - `test_load_mkdocs_tolerates_python_tags`: YAML com `!!python/name:pymdownx.superfences.fence_code_format` carrega e devolve `nav`.
  - `test_nav_pages_nested_and_external` (Review Focus 4): nav com seção aninhada 2 níveis e `{'GitHub': 'https://x'}` → só os `.md`, em ordem.
  - `test_normalize_strips_bom_and_crlf`: `"﻿a\r\nb\r\n\n"` → `"a\nb"`.
- [ ] **Step 2:** `PYTHONPATH=tools .venv/bin/python -m pytest tools/wikisync/tests/test_extract.py -q` → FAIL (ImportError).
- [ ] **Step 3: Implementar** `config.py` e `extract.py`. Cercas: abertura `^([ \t]*)(`{3,}|~{3,})(.*)$`; fecha na primeira linha com a mesma indentação (ou menor) e mesma sequência de comprimento ≥. `title` por `title=(["'])(.*?)\1`; `lang` = primeiro token sem `{`/`.`. Refs: regex `(?<![\w/])(?:ansible|docker|scripts)/[\w.\-/{}]+` aplicada ao texto inteiro (inclusive blocos), removendo pontuação final `.,:;)` e descartando `is_ignored`. Loader YAML: subclasse de `yaml.SafeLoader` com `add_multi_constructor("tag:yaml.org,2002:python/", lambda l, s, n: None)`.
- [ ] **Step 4:** mesmos testes → PASS.
- [ ] **Step 5: Commit** `feat(wikisync): configuração e extração de blocos/referências`.

### Task 4: `wikisync check` e CLI

**Files:**
- Create: `tools/wikisync/check.py`, `tools/wikisync/cli.py`, `tools/wikisync/__main__.py`, `tools/wikisync/tests/test_check.py`, `tools/wikisync/tests/test_cli.py`

**Interfaces:**
- Consumes: Task 3.
- Produces:
  - `@dataclass Finding(code: str, severity: Literal["erro","aviso"], path: str, page: str | None, message: str)`
  - `collect(cfg) -> Wiki` com `Wiki(pages: dict[str, str], blocks: list[Block], literals: dict[str, list[Block]], refs: dict[str, set[str]])` (refs: página → caminhos) — reutilizado por `apply` e `index`.
  - `run_check(cfg: Config) -> list[Finding]` — ordenado por (severidade, código, path).
  - `server_files(cfg) -> list[str]` (relativos a `server/`, POSIX, ordenados, respeitando `exclude_dirs`).
  - `is_covered(path: str, refs: set[str]) -> bool`: verdadeiro se `path` ∈ refs, ou se algum ref terminado em `/` com **≥ 3 segmentos** é prefixo de `path`.
  - CLI: `python -m wikisync [--root PATH] check [--json] | apply [--yes] [--path P] | index`. Raiz padrão: `Path(__file__).resolve().parents[2]`. `--json` imprime lista de objetos `Finding`. Saída texto: `ERRO|AVISO  CÓDIGO  path  (página)  mensagem` + linha-resumo `N erro(s), M aviso(s)`.

- [ ] **Step 1: Testes que falham** (`make_repo`), cada um assertando o conjunto de `(code, severity, path)`:
  - `test_clean_repo_has_no_findings`
  - `test_lit_diff`, `test_lit_missing`, `test_lit_dup` (dois blocos mesmo caminho, conteúdos diferentes) → `erro`
  - `test_bom_and_crlf_only_difference_is_not_lit_diff` (Review Focus 3) → sem `LIT-DIFF`, com `EOL` `erro` no arquivo CRLF
  - `test_crlf_allowed_in_ps1` → sem `EOL`
  - `test_ref_missing` (inclui ref a diretório inexistente `docker/stacks/x/`) → `erro`
  - `test_orphan_warning`, `test_orphan_covered_by_deep_dir_ref` (`docker/stacks/core/`), `test_orphan_not_covered_by_shallow_dir_ref` (`ansible/playbooks/`), `test_ignore_orphans` → sem achado
  - `test_unmarked_warning` (bloco sem `title`, 1ª linha `# ansible/x.yml`)
  - `test_desc_warning`
  - `test_link_broken` (inclui `img.png` inexistente; ignora `http`, `#ancora`, `mailto:`)
  - `test_nav_page_missing_from_nav`, `test_nav_entry_without_file`
  - `test_vault_plaintext_is_error`, `test_vault_encrypted_ok` (`$ANSIBLE_VAULT;1.1;AES256`), `test_vault_example_not_checked`
  - `test_cli.py`: `test_exit_0_with_only_warnings`, `test_exit_1_with_errors`, `test_exit_2_without_config` (Review Focus 5; stderr contém `config.yml`), `test_json_output_is_list_of_findings`, `test_default_root_from_other_cwd` (executa com `cwd=tmp` e `--root` omitido sobre o repo real → código ≠ 2).
- [ ] **Step 2:** `dev.py test` → FAIL.
- [ ] **Step 3: Implementar** `check.py` (uma função privada por código, compostas em `run_check`), `cli.py`, `__main__.py`.
- [ ] **Step 4:** `python tools/dev.py test` → PASS.
- [ ] **Step 5: Rodar no repo real:** `python tools/dev.py check` → código 1, com `UNMARKED` para os blocos com comentário de caminho e `REF-MISSING`/`ORPHAN` esperados. Salvar a saída em `/tmp` para as Tasks 7–9 (não commitar).
- [ ] **Step 6: Commit** `feat(wikisync): comando check e CLI`.

### Task 5: `wikisync apply`

**Files:**
- Create: `tools/wikisync/apply.py`, `tools/wikisync/tests/test_apply.py`; Modify: `tools/wikisync/cli.py`

**Interfaces:**
- Consumes: `collect`, `literal_path`, `normalize`.
- Produces: `@dataclass Change(path: str, old: str | None, new: str)` com `diff() -> str` (unified, rótulos `server/<path>` e `wiki`); `plan_apply(cfg, only: str | None = None) -> list[Change]` (só caminhos cujo conteúdo normalizado difere; levanta `ApplyError` listando caminhos com `LIT-DUP`); `write_changes(cfg, changes) -> None` (UTF-8, LF, um `\n` final, cria diretórios).

- [ ] **Step 1: Testes que falham:** `test_dry_run_does_not_write` (mtime e conteúdo inalterados; CLI imprime diff e "dry-run: use --yes para gravar"), `test_yes_writes_lf_utf8_with_final_newline` (bytes terminam em `b"\n"`, sem `b"\r"`), `test_creates_missing_file_and_dirs`, `test_path_restricts_to_one_file`, `test_never_deletes_unmarked_server_files`, `test_dup_refuses_with_exit_1`, `test_noop_when_equal_ignoring_crlf`.
- [ ] **Step 2:** FAIL. **Step 3:** implementar + subcomando `apply`. **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(wikisync): comando apply (dry-run por padrão)`.

### Task 6: `wikisync index`

**Files:**
- Create: `tools/wikisync/index.py`, `tools/wikisync/tests/test_index.py`; Modify: `tools/wikisync/cli.py`

**Interfaces:**
- Consumes: `collect`, `server_files`, `page_meta`, `run_check` (para estado literal).
- Produces: `build_index(cfg) -> dict` com chaves `pages` (`path,title,description,literal,refs`), `server_files` (`path,kind,pages,literal_state ∈ {"sincronizado","divergente",None}`), `services` (`stack,service,image,networks,traefik_hosts`), `playbooks` (`path,hosts,roles`); `render_markdown(idx: dict) -> str`; `write_index(cfg, idx) -> None` (grava `INDEX.md` e `index.json` na raiz; JSON `indent=2, ensure_ascii=False, sort_keys=True` + `\n`).
- `kind` por regra de caminho: `inventario` (`ansible/inventories/**`), `playbook`, `role-tasks|role-handlers|role-defaults|role-template` (`roles/**/<pasta>/`), `template` (`ansible/templates/**`), `stack` (`docker-compose.yml`), `env-template`, `script` (`scripts/**`), senão `outro`.
- `INDEX.md` começa com aviso `<!-- GERADO por tools/wikisync — não editar à mão -->` e tem as seções "Páginas", "Arquivos do server", "Serviços", "Playbooks e roles", em tabelas.

- [ ] **Step 1: Testes que falham:** `test_pages_and_server_files`, `test_literal_state_values`, `test_services_from_compose_list_and_dict_labels` (extrai host de ``Host(`a.exemplo.com`)``), `test_playbook_roles_str_and_dict`, `test_index_is_deterministic` (duas execuções → bytes idênticos), `test_markdown_has_generated_header_and_sections`.
- [ ] **Step 2:** FAIL. **Step 3:** implementar + subcomando `index`. **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(wikisync): geração de INDEX.md e index.json`.

### Task 7: Migrar a marcação da wiki para `title=`

**Files:** Modify: páginas de `wiki/docs/` que contêm os 33 blocos com comentário de caminho.

- [ ] **Step 1:** Script descartável (fora do repo) que, para cada `Finding` `UNMARKED` de `check --json`, adiciona `title="<caminho do comentário>"` à linha de abertura da cerca, sem alterar o conteúdo do bloco. O bloco de `novoservico` recebe `title="Exemplo: docker/stacks/novoservico/docker-compose.yml"`.
- [ ] **Step 2:** `python tools/dev.py check` → 0 `UNMARKED`; os `LIT-*` mostram exatamente: 17 sincronizados, 13 `LIT-DIFF`, 2 `LIT-MISSING` (lista da seção 9 do spec). Divergência dessa contagem = parar e investigar.
- [ ] **Step 3:** `python tools/dev.py build` → sem `WARNING` (os títulos aparecem como cabeçalho do bloco).
- [ ] **Step 4: Commit** `wiki: marca blocos literais com title=`.

### Task 8: Triagem dos blocos literais (com o usuário)

**Files:** Modify: páginas da wiki e/ou arquivos do server listados na seção 9.3 do spec; Create: `etc_exports.j2`, `node_exporter_host.service.j2`, `server/ansible/inventories/home/group_vars/all/vault.yml.example`.

- [ ] **Step 1: Ausentes:** `python tools/dev.py sync --path <cada um dos 2> --yes`. Expected: arquivos criados; `check` sem `LIT-MISSING`.
- [ ] **Step 2: Vault (D10):** `git mv .../all/vault.yml .../all/vault.yml.example`; atualizar os 2 blocos da página `01-maquina-controle-ansible.md`: o bloco de modelo passa a `title="ansible/inventories/home/group_vars/all/vault.yml.example"` com o conteúdo atual do server; o bloco do vault real vira ilustrativo (`title="Exemplo: vault.yml criptografado"`); texto explica "copie o example, preencha e rode `ansible-vault encrypt`". **Checkpoint do usuário:** gerar o `vault.yml` criptografado na máquina de controle e copiá-lo para a pasta; até lá, `REF-MISSING` desse caminho é esperado e bloqueia apenas a Task 14.
- [ ] **Step 3: Divergentes, em lotes por página** (01-maquina-controle-ansible; 02-proxmox-ve-host; 03-provisionamento-vms; 04-configuracao-base-vms-ubuntu; 05-rede-segura; 13-usando-geminicli; 03-cicd-basico-ansible). Para cada lote: enviar ao usuário (`SendUserMessage`) o `sync --path` dry-run de cada arquivo + recomendação ("wiki vence" / "server evoluiu"); **aguardar a decisão**; aplicar: "wiki vence" → `sync --path X --yes`; "server evoluiu" → substituir o conteúdo do bloco da wiki pelo do server (e ajustar o texto ao redor que descreve o arquivo).
- [ ] **Step 4:** `python tools/dev.py check` → 0 achados `LIT-*`; `python tools/dev.py build` sem `WARNING`.
- [ ] **Step 5: Commit** por lote: `reconcilia: <página> (wiki ↔ server)`.

### Task 9: Divergências estruturais (com o usuário)

**Files:** Create: `server/docker/stacks/.env.template`; Delete: `server/scripts/validation/check_docs_integrity.py`, `server/scripts/validation/apply_revision_fixes.py`; Modify: `roles/apps/desktop-environment/` (mover ou remover `main.yml` solto), páginas da wiki, `tools/wikisync/config.yml` (`ignore_orphans`).

- [ ] **Step 1:** Remover os 2 scripts obsoletos (`git rm`) e atualizar qualquer página que os cite.
- [ ] **Step 2:** `desktop-environment/main.yml`: se idêntico a `tasks/main.yml`, `git rm`; senão mostrar diff ao usuário e decidir.
- [ ] **Step 3:** `.env.template`: reunir as variáveis `${VAR}` usadas em `docker/stacks/*/docker-compose.yml` e as descritas em `00-preparacao-planejamento.md`; criar o arquivo com `VAR=` e comentários; documentar na página 00 com bloco `title="docker/stacks/.env.template"`.
- [ ] **Step 4:** Para cada `REF-MISSING` e `ORPHAN` restante, enviar a lista ao usuário agrupada com recomendação (documentar na página X / remover / ignorar com motivo) e aplicar as decisões. Órfãos mantidos sem documentação entram em `ignore_orphans` com motivo.
- [ ] **Step 5:** `python tools/dev.py check` → 0 erros (exceto o `vault.yml` do checkpoint, se pendente); `build` sem `WARNING`.
- [ ] **Step 6: Commit** `reconcilia: estrutura do server conforme a wiki`.

### Task 10: `description` em todas as páginas

**Files:** Modify: as 41 páginas de `wiki/docs/`.

- [ ] **Step 1:** Redigir uma `description:` (≤ 160 caracteres, português, factual, sem repetir o título) por página, no front-matter.
- [ ] **Step 2:** Enviar ao usuário a tabela página → descrição para revisão; aplicar correções.
- [ ] **Step 3:** `check` → 0 `DESC`; `build` sem `WARNING`.
- [ ] **Step 4: Commit** `wiki: descrições das páginas`.

### Task 11: Contexto do Claude e permissões

**Files:** Create: `CLAUDE.md`, `wiki/CLAUDE.md`, `server/CLAUDE.md`, `README.md`, `.claude/settings.json`

- [ ] **Step 1:** Escrever os três `CLAUDE.md` com o conteúdo da seção 8.1 do spec (raiz < 150 linhas). Comandos sempre via `python tools/dev.py …`.
- [ ] **Step 2:** `README.md`: 1 parágrafo do que é o repo, link `https://lioevano.github.io/wiki-home-server/`, "comece por `CLAUDE.md`", bloco de comandos `setup/serve/check`.
- [ ] **Step 3:** `.claude/settings.json` com `permissions.allow`: `Bash(python tools/dev.py:*)`, `Bash(python3 tools/dev.py:*)`, `Bash(git status:*)`, `Bash(git diff:*)`, `Bash(git log:*)`, `Bash(git add:*)`, `Bash(git commit:*)`, `Bash(ansible-playbook --syntax-check:*)`, `Bash(docker compose config:*)`; `permissions.ask`: `Bash(ansible-playbook:*)`, `Bash(ansible-vault:*)`, `Bash(ssh:*)`, `Bash(docker compose up:*)`, `Bash(docker compose down:*)`, `Bash(git push:*)`.
- [ ] **Step 4:** Verificar: `python -c "import json;json.load(open('.claude/settings.json'))"` OK; todo comando citado nos CLAUDE.md existe em `dev.py` (grep cruzado); `check` sem novos achados.
- [ ] **Step 5: Commit** `claude: contexto do projeto e permissões`.

### Task 12: Skills do projeto

**Files:** Create: `.claude/skills/{wiki-first-change,sync-wiki-server,add-docker-service,add-ansible-component,wiki-page-authoring,validate-infra}/SKILL.md`

- [ ] **Step 1:** Escrever as 6 skills (front-matter `name`, `description` em uma frase dizendo *quando* usar; corpo com os passos da seção 8.3 do spec, comandos `dev.py` exatos e critério de término). Seguir `superpowers:writing-skills` para formato.
- [ ] **Step 2: Teste de uso:** despachar um subagente sem contexto, apontado para o repo, com o pedido "adicione um serviço `uptime-kuma` na stack apps" e as skills disponíveis; ele deve parar no dry-run, sem aplicar. Critério: o subagente edita a wiki antes do server e roda `check`/`sync` na ordem. Ajustar a skill se ele desviar. Descartar as mudanças do subagente (`git restore`/`git clean` só nos arquivos que ele criou).
- [ ] **Step 3:** Propor para a conta do usuário (`propose_skills`, limite de 3 por chamada): `wiki-first-change`, `sync-wiki-server`, `add-docker-service`, com o mesmo conteúdo.
- [ ] **Step 4: Commit** `claude: skills do projeto`.

### Task 13: Índice e CI

**Files:** Create: `INDEX.md`, `index.json` (gerados), `.github/workflows/docs.yml`, `.github/workflows/server-lint.yml`

- [ ] **Step 1:** `python tools/dev.py index`; revisar `INDEX.md` (todas as 41 páginas, todos os arquivos do server, serviços das 3 stacks).
- [ ] **Step 2: `docs.yml`** conforme seção 10 do spec: `on.push.branches: [main]`, `paths: [wiki/**, tools/**, requirements-dev.txt, .github/workflows/docs.yml]`, `workflow_dispatch`; `permissions: contents: write`; `actions/checkout@v4` com `fetch-depth: 0`; `actions/setup-python@v5` `python-version: "3.12"`; passos `python tools/dev.py setup|test|check|build`; deploy `.venv/bin/mkdocs gh-deploy --force -f wiki/mkdocs.yml` após `git config user.name github-actions[bot]`/`user.email 41898282+github-actions[bot]@users.noreply.github.com`.
- [ ] **Step 3: `server-lint.yml`**: `on: push` e `pull_request` com `paths: [server/**, tools/**, .yamllint, requirements-dev.txt]`; mesma preparação; passos `setup`, `lint`, `check`.
- [ ] **Step 4:** Verificar localmente (device Linux): `yamllint .github/workflows` OK; `python tools/dev.py setup && python tools/dev.py test && python tools/dev.py check && python tools/dev.py build && python tools/dev.py lint` — todos código 0 (exceto o `vault.yml` do checkpoint, se pendente). Corrigir achados reais de `yamllint`/`ansible-lint --profile min` nos arquivos do server **pela wiki** (bloco literal → `sync`), nunca editando só o server.
- [ ] **Step 5:** Teste de regeneração: alterar 1 descrição, `index`, ver o diff de `INDEX.md` refletir só aquela linha; reverter.
- [ ] **Step 6: Commit** `ci: deploy da wiki e lint do server; índice gerado`.

### Task 14: Verificação final e entrega

- [ ] **Step 1:** Confirmar o checkpoint do vault (Task 8 Step 2): `vault.yml` criptografado presente; `check` → 0 erros.
- [ ] **Step 2:** Rodar a sequência completa do Task 13 Step 4 e anexar a saída ao resumo para o usuário.
- [ ] **Step 3:** `git log --oneline origin/main..main` e `git status` (limpo).
- [ ] **Step 4: Revisão independente:** um revisor novo (modelo mais capaz) confere o branch inteiro contra o spec.
- [ ] **Step 5: Instruções ao usuário** (enviadas por `SendUserMessage`): no Windows, em `homeserver/`: `git push origin main`; se o git acusar *dubious ownership*, `git config --global --add safe.directory <caminho>`; no GitHub, *Settings → Actions → General → Workflow permissions → Read and write*; *Settings → Pages* continua em `gh-pages`; acompanhar a execução do workflow `docs` e abrir o site. Remover `../wiki-home-server-main.bundle` e o antigo `wiki/venv/` quando quiser (ignorados pelo git).
