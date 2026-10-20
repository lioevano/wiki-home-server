# IA — fundação: Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gateway LiteLLM com apelidos de modelo, chaves por cliente, orçamento e registro de uso; Open WebUI com OIDC; Ollama com Vulkan; Claude Code documentado — tudo na stack `ai` da `ai-desktop-vm`.

**Architecture:** O `config.yaml` do LiteLLM sai de `llm_models` (`group_vars`), sem segredos (chaves por `os.environ/`). O LiteLLM ganha Postgres local e um servidor de métricas na porta 4001; as chaves virtuais vêm do vault e são aplicadas pelo `setup-ai-keys.yml` depois do deploy. O Open WebUI fala só com o LiteLLM e entra pelo OIDC do Authelia. O Ollama roda numa imagem local (oficial + Mesa/RADV) construída pelo role `ml-tools`.

**Tech Stack:** LiteLLM v1.106.0, Postgres 16, Ollama 0.40.6 (Vulkan), Open WebUI v0.12.3, Authelia 4.38 OIDC, Ansible, Docker Compose (Portainer Agent), Prometheus, pytest, MkDocs.

**Spec:** `docs/superpowers/specs/2026-10-20-ia-fundacao-design.md`

## Global Constraints

- Wiki-first. **Literais:** `group_vars/all/main.yml` e `vault.yml.example` (página 01), `.env.template` (00), `configuration.yml.j2` do Authelia e `dynamic_rag_services.yml.j2` (05), `litellm_config.yaml.j2` e role `ml-tools` (08). **Estruturais** (diretos, citados com caminho): `docker/stacks/ai/docker-compose.yml`, playbooks `setup-ai-volumes.yml`, `setup-ai-keys.yml`, `setup-cloud-stack-volumes.yml`, `setup-monitoring-stack-volumes.yml`, templates `prometheus.yml.j2`, `homepage/services.yaml.j2`, `grafana/alerting/rules.yml.j2`, `backup-postgres.sh.j2`.
- Ambiente: `export HOMESERVER_VENV=$HOME/.venvs/homeserver PATH=$HOME/.local/bin:$PATH` na mesma chamada; `check` só `REF-PENDING`; `lint` OK; build estrito num clone local do HEAD (`git clone -q --no-hardlinks . /tmp/rb/repo` → `mkdocs build --strict -f wiki/mkdocs.yml -d /tmp/rb/site`), porque na pasta do Windows ele estoura 180 s.
- Testes novos em `tools/wikisync/tests/test_ia.py` (`from test_observabilidade import ROOT, render`; `from test_midia import _svc, _env`; `from test_fotos_arquivos import _authelia, _pb_tasks, _env_task, _configs, _vars_compose, _volume, COMUNS, DOM, OIDC`).
- **Versões:** `ollama_version: "0.40.6"`, Open WebUI `ghcr.io/open-webui/open-webui:v0.12.3`, LiteLLM `litellm-database` na tag exata da release **v1.106.0** (conferir a tag no Docker Hub `litellm/litellm-database` ou no ghcr antes de escrever; nada de `main-latest`), `postgres:16-alpine`.
- **Modelos** (`llm_models`, `group_vars`): por nome próprio `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5` (`anthropic/…`), `gpt-6.1-sol`, `gpt-6-luna` (`openai/…`), `gemini-3.8-flash` (`gemini/gemini-3.8-flash`); apelidos `principal` → `anthropic/claude-sonnet-5-5`, `rapido` → `anthropic/claude-haiku-5-5`, `local` → `ollama_chat/llama3.2:3b` com `api_base: http://ollama:11434`, `decisao` → `typesafe/jev-latest`. `llm_fallbacks`: `principal` → `gpt-6.1-sol`; `rapido` → `gpt-6-luna`. Os IDs saíram do `model_prices_and_context_window.json` da v1.106.0.
- **Variáveis do `ai.env`** (nomes exatos, além das comuns): `AI_DESKTOP_VM_IP`, `AI_STACK_LITELLM_CONFIG_PATH`, `AI_STACK_LITELLM_DB_PATH` (= `{{ vm_local_data_path }}/litellm-db`), `AI_STACK_OLLAMA_MODELS_PATH`, `AI_STACK_OPENWEBUI_DATA_PATH`, `AI_STACK_DIUN_DATA_PATH`, `AI_RENDER_GID`, `OLLAMA_IMAGE` (= `homeserver/ollama-vulkan:{{ ollama_version }}`), `LITELLM_MASTER_KEY`, `LITELLM_DB_PASSWORD`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `TYPESAFE_API_KEY`, `LITELLM_KEY_OPENWEBUI`, `OPENWEBUI_SECRET_KEY`, `OPENWEBUI_OAUTH_CLIENT_SECRET`, `OPENWEBUI_LOGIN_FORM`, `NOTIFICACOES_WEBHOOK_TOKEN`. Saem `AI_STACK_OPENCLAW_*` e `AI_STACK_OPENCLAUDE_*`.
- **Vault (novas):** `llm_api_keys.typesafe`, `litellm_db_password`, `litellm_client_keys.{openwebui,claude_code,n8n}` (valores `sk-` + `openssl rand -hex 24`), `oidc_clients.openwebui.{secret,secret_digest}`. **`group_vars` (novas):** `llm_models`, `llm_fallbacks`, `litellm_key_budgets: {openwebui: 20, claude_code: 50, n8n: 10}` (USD/mês), `ollama_version`, `openwebui_login_form: true`, `llm_gasto_diario_alerta: 5` (USD).
- Nada de `docker compose up/down`, `ansible-playbook` sem `--check`/`--syntax-check`, `ansible-vault` ou `git push`. Commits com o trailer da sessão.

## Review Focus

1. **Chave mestra ou de provedor vazando para um cliente:** só o `litellm` recebe `LITELLM_MASTER_KEY` e chaves de provedor → Task 2 testa todos os serviços do compose.
2. **Segredo gravado no `config.yaml` (NFS, 0644):** chaves só por `os.environ/` → Task 1 testa o render sem nenhum valor do vault.
3. **Ollama acessível na LAN sem autenticação:** sem `ports` → Task 2.
4. **Playbook de chaves imprimindo segredos ou recriando chaves a cada execução:** `no_log: true` e ramos `generate`/`update` condicionados → Task 3.
5. **Qualquer usuário do Authelia entrando no Open WebUI:** `ENABLE_OAUTH_ROLE_MANAGEMENT` com `OAUTH_ALLOWED_ROLES=admins` → Task 4.

---

### Task 1: Gateway — modelos, apelidos e métricas

**Files:**
- Modify: `server/ansible/templates/litellm_config.yaml.j2` (literal na página 08)
- Modify: `server/ansible/inventories/home/group_vars/all/main.yml` (`llm_models`, `llm_fallbacks`, `llm_gasto_diario_alerta`) e `vault.yml.example` (`llm_api_keys.typesafe`) — página 01
- Test: `tools/wikisync/tests/test_ia.py`

**Interfaces:**
- Produces: `llm_models` (lista de `{name, model, chave?, api_base?}`; `chave` = nome da variável de ambiente do provedor), `llm_fallbacks` (lista de `{apelido: [modelos]}`); `config.yaml` com `litellm_settings.callbacks: [prometheus]`.

- [ ] **Step 1: Write the failing tests**
  - `test_litellm_config_de_llm_models`: render com `llm_models`/`llm_fallbacks` do `main.yml` → YAML; `model_name` inclui `principal`, `rapido`, `local`, `decisao` e todos os nomes próprios da Global Constraints; `decisao` → `typesafe/jev-latest`; `local` com `api_base == "http://ollama:11434"`; cada modelo com `chave` tem `api_key == "os.environ/<chave>"`; `router_settings.fallbacks == [{"principal": ["gpt-6.1-sol"]}, {"rapido": ["gpt-6-luna"]}]`; `general_settings.store_model_in_db is False`, `master_key == "os.environ/LITELLM_MASTER_KEY"`, `database_url == "os.environ/DATABASE_URL"`; `litellm_settings.callbacks == ["prometheus"]`.
  - `test_litellm_config_sem_segredos`: o render recebe valores de vault falsos (`litellm_master_key`, `llm_api_keys.*`) e nenhum aparece no texto.
- [ ] **Step 2: Run** `dev.py test` → FAIL.
- [ ] **Step 3: Implement** o template (laço em `llm_models`; sem acessar o vault) e as variáveis pela wiki; `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(ia): gateway LiteLLM com apelidos de modelo, Jev e métricas`

### Task 2: Stack `ai` e preparação da VM

**Files:**
- Modify: `server/docker/stacks/ai/docker-compose.yml` (saem `openclaw`, `openclaude`; entra `litellm_db`; versões fixadas)
- Modify: `server/ansible/playbooks/setup-ai-volumes.yml` (diretórios, `ai.env` da Global Constraints, GID do `render` via `ansible.builtin.getent`)
- Modify: role `ml-tools` (página 08): sai o bloco ROCm; entra `templates/Dockerfile.ollama-vulkan.j2` (`FROM ollama/ollama:{{ ollama_version }}` + `apt-get install -y mesa-vulkan-drivers`) gravado em `/opt/ollama-vulkan/Dockerfile` e `community.docker.docker_image` (`source: build`, `name: homeserver/ollama-vulkan`, `tag: "{{ ollama_version }}"`); usuários nos grupos `render` e `video` mantidos
- Modify: `.env.template` (página 00); `main.yml` (`ollama_version`, `openwebui_login_form`)
- Test: `tools/wikisync/tests/test_ia.py`

**Interfaces:**
- Consumes: Task 1 (`config.yaml`).
- Produces: serviços `litellm` (container `litellm_proxy`, 4000 API, 4001 métricas), `litellm_db`, `ollama`, `open-webui`, `diun_ai`; variáveis do `ai.env`.

- [ ] **Step 1: Write the failing tests**
  - `test_ai_servicos`: `set(_svc(AI)) == {"litellm", "litellm_db", "ollama", "open-webui", "diun_ai"}`; nenhuma imagem termina em `:latest`, `:main`, `:main-latest` ou `:rocm`; `ollama.image == "${OLLAMA_IMAGE}"`.
  - `test_so_o_litellm_tem_segredos_de_provedor`: para todo serviço ≠ `litellm`, o env não contém `${LITELLM_MASTER_KEY}`, `${ANTHROPIC_API_KEY}`, `${OPENAI_API_KEY}`, `${GEMINI_API_KEY}`, `${TYPESAFE_API_KEY}`; `open-webui` tem `OPENAI_API_KEY == "${LITELLM_KEY_OPENWEBUI}"`, `OPENAI_API_BASE_URL == "http://litellm:4000/v1"`, `ENABLE_OLLAMA_API == "false"`.
  - `test_litellm_banco_local_e_metricas`: `litellm.environment.DATABASE_URL` aponta para `litellm_db` com `${LITELLM_DB_PASSWORD}`; `ports == ["${AI_DESKTOP_VM_IP}:4000:4000", "${AI_DESKTOP_VM_IP}:4001:4001"]`; `command` contém `--prometheus_metrics_port` `4001`; `depends_on.litellm_db.condition == "service_healthy"`; volume do `litellm_db` começa com `${AI_STACK_LITELLM_DB_PATH}`, que no playbook começa com `{{ vm_local_data_path }}/`.
  - `test_ollama_vulkan_sem_porta`: sem `ports`; `devices == ["/dev/dri"]`; `group_add == ["${AI_RENDER_GID}"]`; o role `ml-tools` não contém `rocm` (sem maiúsculas/minúsculas) e tem a tarefa `docker_image` com `name: homeserver/ollama-vulkan`; o Dockerfile renderizado tem `FROM ollama/ollama:0.40.6` e `mesa-vulkan-drivers`.
  - `test_variaveis_ai_no_env`: `_vars_compose(AI) <= set(_configs(PB_AI, "ai.env")) | COMUNS`; `mode == "0600"`; nenhum `OPENCLAW`/`OPENCLAUDE` no playbook nem no `.env.template`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** (compose, playbook, role, variáveis); `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS (inclusive os testes antigos que leem o compose `ai`).
- [ ] **Step 5: Commit** `feat(ia): stack ai com banco do LiteLLM, Ollama com Vulkan e sem OpenClaw/OpenClaude`

### Task 3: Chaves virtuais por cliente

**Files:**
- Create: `server/ansible/playbooks/setup-ai-keys.yml` (`hosts: ai_desktop`, `gather_facts: false`, base `http://{{ ai_desktop_vm_ip_var }}:4000`)
- Modify: `vault.yml.example` (`litellm_client_keys`, `litellm_db_password`) e `main.yml` (`litellm_key_budgets`) — página 01
- Test: `tools/wikisync/tests/test_ia.py`

- [ ] **Step 1: Write the failing tests**
  - `test_chaves_por_cliente`: `litellm_client_keys` no `vault.yml.example` com `openwebui`, `claude_code`, `n8n`, valores começando com `sk-`; cada uma tem orçamento em `litellm_key_budgets`.
  - `test_playbook_de_chaves_idempotente`: todas as tarefas `ansible.builtin.uri` têm `no_log: true` e cabeçalho `Authorization: "Bearer {{ litellm_master_key }}"`; existe tarefa para `/key/info` (com `status_code` aceitando chave inexistente), `/key/generate` (com `when` sobre a chave não existir; corpo com `key`, `key_alias`, `max_budget`, `budget_duration: "30d"`) e `/key/update` (com `when` sobre orçamento ou duração diferentes); as tarefas de consulta têm `changed_when: false`; o laço é sobre `litellm_client_keys | dict2items`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS; `ansible-playbook --syntax-check` do playbook novo via `dev.py lint`.
- [ ] **Step 5: Commit** `feat(ia): chaves virtuais por cliente com orçamento (setup-ai-keys.yml)`

### Task 4: Open WebUI com OIDC

**Files:**
- Modify: `configuration.yml.j2` do Authelia (página 05): cliente `openwebui` (`client_name: "Open WebUI"`, `two_factor`, PKCE S256, `client_secret_basic`, redirect `https://openwebui.{{ base_domain }}/oauth/oidc/callback`, escopos `openid profile groups email`)
- Modify: `vault.yml.example` (`oidc_clients.openwebui`); compose `open-webui`; `setup-ai-volumes.yml`
- Test: `tools/wikisync/tests/test_ia.py` e `test_fotos_arquivos.py` (`OIDC` de teste ganha `openwebui`)

- [ ] **Step 1: Write the failing tests**
  - `test_cliente_oidc_openwebui`: com `OIDC` estendido, o cliente `openwebui` existe com os valores acima; `test_authelia_validate_config` (existente) continua passando com três clientes.
  - `test_openwebui_oidc`: env do `open-webui` com `WEBUI_URL == "https://openwebui.${BASE_DOMAIN_FROM_VAULT}"`, `OAUTH_CLIENT_ID == "openwebui"`, `OAUTH_CLIENT_SECRET == "${OPENWEBUI_OAUTH_CLIENT_SECRET}"`, `OPENID_PROVIDER_URL == "https://auth.${BASE_DOMAIN_FROM_VAULT}/.well-known/openid-configuration"`, `OAUTH_CODE_CHALLENGE_METHOD == "S256"`, `OAUTH_SCOPES == "openid email profile groups"`, `ENABLE_OAUTH_SIGNUP == "true"`, `OAUTH_MERGE_ACCOUNTS_BY_EMAIL == "true"`, `ENABLE_OAUTH_ROLE_MANAGEMENT == "true"`, `OAUTH_ROLES_CLAIM == "groups"`, `OAUTH_ALLOWED_ROLES == "admins"`, `OAUTH_ADMIN_ROLES == "admins"`, `ENABLE_LOGIN_FORM == "${OPENWEBUI_LOGIN_FORM}"`; o playbook emite `OPENWEBUI_LOGIN_FORM` de `openwebui_login_form`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS (com `PATH` incluindo o binário do Authelia).
- [ ] **Step 5: Commit** `feat(ia,autenticacao): Open WebUI com login OIDC do Authelia`

### Task 5: Dump genérico de Postgres

**Files:**
- Create: `server/ansible/templates/backup-postgres.sh.j2` (variáveis `backup_container`, `backup_db`, `backup_user`, `backup_dest`, `backup_prefix`, `backup_extra_dir` opcional — tar do diretório, como o config do Nextcloud; retenção 14 dias; `.tmp` limpos)
- Delete: `server/ansible/templates/nextcloud/backup-nextcloud-db.sh.j2` (substituído; a página 11 passa a citar o genérico)
- Modify: `setup-cloud-stack-volumes.yml` (usa o genérico com `vars:`, mesmo destino `/usr/local/sbin/backup-nextcloud-db.sh`); `setup-ai-volumes.yml` (script `/usr/local/sbin/backup-litellm-db.sh`, `.service`, `.timer` diário 03:45 `Persistent=true`, destino `docker-volumes/litellm/db-dumps`)
- Test: `tools/wikisync/tests/test_fotos_arquivos.py` (`DUMP_TPL` e os dois testes de dump renderizam o genérico com as `vars:` do playbook) e `test_ia.py`

- [ ] **Step 1: Write the failing tests**
  - `test_dump_generico_nos_dois_bancos`: para `PB_CLOUD` e `PB_AI`, a tarefa de template do script usa `../templates/backup-postgres.sh.j2`; renderizando com as `vars:` da tarefa (mais `vm_nfs_mount_base_path`, `zfs_docker_volumes_dataset_name`, `vm_local_data_path` de teste): `docker exec <container> pg_dump -U <user> -d <db> -Fc`, destino certo, `-mtime +14`, `*.tmp`; só o do Nextcloud tem `tar` do config; timer do LiteLLM com `OnCalendar` diário e `Persistent=true`.
  - Os testes `test_dump_diario_do_nextcloud` e `test_dump_guarda_o_config_do_nextcloud` passam a renderizar o genérico (mesmas asserções).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; página 11 cita o template genérico.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `refactor(backup): dump genérico de Postgres para Nextcloud e LiteLLM`

### Task 6: Integrações — `llm.`, métricas, alerta e painel

**Files:**
- Modify: `dynamic_rag_services.yml.j2` (página 05): router `litellm-dynamic` `Host(\`llm.{{ base_domain }}\`)` → `http://{{ ai_desktop_vm_ip_var }}:4000`, middleware `authelia-forwardauth@docker`
- Modify: `prometheus.yml.j2`: job `litellm` (`{{ ai_desktop_vm_ip_var }}:4001`), dentro do mesmo `{% if %}` dos alvos da VM de IA
- Modify: `grafana/alerting/rules.yml.j2`: regra `llm-gasto-alto` (`sum(increase(litellm_spend_metric_total[1d]))` `gt` `llm_gasto_diario_alerta`, `for: 0s`, `warning`)
- Modify: `homepage/services.yaml.j2`: entrada `litellm` no grupo `ia`, `href: https://llm.{{ base_domain }}`, `siteMonitor: http://{{ ai_desktop_vm_ip_var }}:4000/health/liveliness`
- Test: `tools/wikisync/tests/test_ia.py`

- [ ] **Step 1: Write the failing tests** `test_router_llm_com_authelia`, `test_job_litellm_e_alerta_de_gasto` (com `groups` contendo a VM de IA, como os testes existentes do Prometheus) e `test_homepage_litellm`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS (inclusive `test_alertas_*` e `test_prometheus_*` existentes).
- [ ] **Step 5: Commit** `feat(ia,painel,notificacoes): llm. com Authelia, métricas e alerta de gasto do LiteLLM`

### Task 7: Documentação, catálogo, índice e verificação final

**Files:**
- Modify: página 08 (reescrita conforme spec §7: arquitetura, apelidos e troca de modelo, Jev, chaves e `setup-ai-keys.yml`, tela de uso, Open WebUI/OIDC com o passo de desligar `openwebui_login_form`, Ollama/Vulkan com como confirmar e voltar para CPU, Claude Code com assinatura × alias `claude-gw` e `~/.claude/settings.json`, teste `curl` em `/v1/messages`, `/status`, `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` como contorno, falhas, teste ponta a ponta); 00, 01, 05, 06, 09, backup, `02-visao-geral-arquitetura/07-apis-llm-estrategia.md`
- Modify: catálogo (saem `openclaw` e `openclaude`; `litellm`: Serviços `litellm`, `litellm_db`, Exposição `protegida`, Subdomínio `llm`, Métricas `sim`; `ollama` e `open-webui` mantidos), índice (LLM-4 nova; LLM-2 cita `${TYPESAFE_API_KEY}`), `INDEX.md` (skill `update-index`)
- Test: `tools/wikisync/tests/test_ia.py`

- [ ] **Step 1: Write the failing test** `test_catalogo_ia`: linha `litellm` como acima; `openclaw` e `openclaude` ausentes; índice com `**LLM-4**`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** páginas, catálogo, índice e `INDEX.md`.
- [ ] **Step 4: Verify** `dev.py test` (todos passam, exceto os ignorados por binário), `check` só `REF-PENDING`, `sync` sem diferenças, build estrito no clone, `lint` OK, `audit-integrations` sem ❌/⚠️.
- [ ] **Step 5: Commit** `docs(ia): página 08, catálogo, índice e backup da fundação de IA`
