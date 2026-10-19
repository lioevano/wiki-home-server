# Fotos e arquivos — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Immich (stack `photos`) e Nextcloud reformulado com cron e Collabora (stack `cloud`), ambos públicos pelo túnel com login OIDC pelo Authelia, sobre datasets `photos` e `files` com cota e bancos no disco local da VM.

**Architecture:** O Authelia ganha `identity_providers.oidc` com os clientes `immich` e `nextcloud`. Duas stacks novas na `core-services-vm`, cada uma com seu playbook de volumes e seu `.env` (0600). A configuração dos apps é gerada pelo Ansible: `immich.json` (base + `immich_config_overrides`) e um hook `before-starting` do Nextcloud. Painel, disponibilidade, backup, catálogo e índice são ajustados; a página 11 documenta tudo.

**Tech Stack:** Docker Compose (Portainer), Ansible (Jinja2), Authelia 4.38 (OIDC), Immich v3.3.3, Nextcloud (apache), Collabora CODE, Homepage, Prometheus/blackbox, pytest, MkDocs.

**Spec:** `docs/superpowers/specs/2026-10-19-fotos-arquivos-design.md`

## Global Constraints

- Wiki-first: literais na wiki → `check` → `sync` (dry-run) → `sync --yes`. **Literais:** `group_vars/all/main.yml` e `vault.yml.example` (página 01), role `common` (04), `etc_exports.j2` (02), `.env.template` (00), `configuration.yml.j2` do Authelia e `nextcloud_middleware.yml.j2` (05). **Estruturais** (mudam direto, citados com caminho completo): composes, playbooks `setup-photos-stack-volumes.yml`, `setup-cloud-stack-volumes.yml`, `setup-productivity-automation-volumes.yml`, `setup-monitoring-stack-volumes.yml`, templates `prometheus.yml.j2`, `homepage/services.yaml.j2`, `immich/immich.json.j2`, `nextcloud/10-homeserver.sh.j2`, `nextcloud/backup-nextcloud-db.sh.j2`.
- `export HOMESERVER_VENV=$HOME/.venvs/homeserver` na mesma chamada; `check` só com `REF-PENDING`; `build` (`timeout 170`) sem WARNING/INFO de âncora; `lint` OK. Permissão de apagar pedida uma vez na sessão (`.ansible/.lock`, `wiki/site`, locks do git).
- Testes novos em `tools/wikisync/tests/test_fotos_arquivos.py`, com `from test_observabilidade import ROOT, render` e `from test_midia import _svc, _env`.
- Subdomínios literais (como `pedidos`): `fotos` (immich_server), `nextcloud` (nextcloud_app), `office` (collabora). Nenhum dos três com `authelia-forwardauth`.
- `group_vars/all/main.yml` (novos): `zfs_photos_dataset_name: "photos"`, `zfs_files_dataset_name: "files"`, `vm_local_data_path: "/opt/local-data"`, `immich_version: "v3.3.3"`, `nextcloud_major` (major atual da tag `stable` do Docker Hub, string só com dígitos), `immich_password_login: true`, `immich_config_overrides: {}`.
- Vault (novas chaves no `vault.yml.example`): `authelia_oidc_hmac_secret`, `authelia_oidc_jwks_key` (PEM, bloco `|`), `oidc_clients: {immich: {secret, secret_digest}, nextcloud: {secret, secret_digest}}`, `immich_db_password`, `homepage_widget_keys.immich`. Segredos alfanuméricos.
- `photos.env` (nomes exatos): `IMMICH_VERSION`, `PHOTOS_STACK_UPLOAD_PATH` (= `{{ vm_nfs_mount_base_path }}/{{ zfs_photos_dataset_name }}`), `PHOTOS_STACK_CONFIG_PATH` (= `…/docker-volumes/immich/config`), `PHOTOS_STACK_DB_PATH` (= `{{ vm_local_data_path }}/immich-db`), `PHOTOS_STACK_MODEL_CACHE_PATH` (= `{{ vm_local_data_path }}/immich-model-cache`), `IMMICH_DB_PASSWORD`, `CORE_SERVICES_VM_IP_VAR`.
- `cloud.env` (nomes exatos): `NEXTCLOUD_MAJOR`, `CLOUD_STACK_NEXTCLOUD_{HTML,CONFIG,HOOKS}_PATH` (`…/docker-volumes/nextcloud/{html,config,hooks}`), `CLOUD_STACK_NEXTCLOUD_DATA_PATH` (= `{{ vm_nfs_mount_base_path }}/{{ zfs_files_dataset_name }}`), `CLOUD_STACK_NEXTCLOUD_DB_PATH` (= `{{ vm_local_data_path }}/nextcloud-db`), `NEXTCLOUD_DB_PASSWORD_FROM_PORTAINER_ENV`, `NEXTCLOUD_ADMIN_PASSWORD_FROM_PORTAINER_ENV`, `NEXTCLOUD_OIDC_CLIENT_SECRET`, `CORE_SERVICES_VM_IP_VAR`. Saem do `.env.template` os `PROD_STACK_NEXTCLOUD_*`.
- Nada de `docker compose up/down`, `ansible-playbook` sem `--check`/`--syntax-check`, `ansible-vault` ou `git push`. Commits com o trailer da sessão.

### Decisões do plano (desvios do spec)

- **Dump do Nextcloud** em `docker-volumes/nextcloud/db-dumps` (não `backups/nextcloud`): o dataset `backups` não é exportado para as VMs; `docker-volumes` já tem snapshots e Borg.
- **Sem variáveis de cota:** os datasets são criados à mão (página 02); a cota vai no comando `zfs create -o quota=…` (sugestão 150G para `photos`, 75G para `files`) e muda com `zfs set quota=`.
- **Subdomínios literais** no compose e nos templates, sem `immich_subdomain`/`collabora_subdomain`.
- **Catálogo:** uma linha por aplicação — `immich` (serviços `immich_server`, `immich_ml`, `immich_redis`, `immich_db`) e `collabora`; `nextcloud` ganha `nextcloud_cron`. Categoria `produtividade` (grupo da Homepage idem).

## Review Focus

1. **Banco no NFS por engano:** um `${…_DB_PATH}` apontando para o NFS corrompe o Postgres do Immich → Task 3/4 testam que o volume de `/var/lib/postgresql/data` vem de `PHOTOS_STACK_DB_PATH`/`CLOUD_STACK_NEXTCLOUD_DB_PATH` e que o playbook os define sob `vm_local_data_path`.
2. **Segredo do OIDC gravado em arquivo legível no NFS:** o hook do Nextcloud é lido pelo `www-data` → Task 4 testa que o hook renderizado não contém o valor do segredo e usa `$NEXTCLOUD_OIDC_CLIENT_SECRET`; Task 3 testa `mode: '0600'` no `immich.json`.
3. **`immich_config_overrides` apagando a base:** um override de `oauth.buttonText` não pode derrubar `oauth.enabled`/`clientId` → Task 3 testa a mescla recursiva.
4. **Assinatura de conta pelo Authelia:** `autoRegister` ligado deixaria qualquer conta do Authelia criar usuário no Immich → Task 3 testa `autoRegister: false`.
5. **Hook que falha na segunda partida:** `occ app:install` de app já instalado sai com erro e trava o container → Task 4 testa que todo `app:install` tem fallback (`|| … app:enable`) e que o script passa em `bash -n`.

---

### Task 1: Datasets `photos` e `files` e disco local

**Files:**
- Modify: `server/ansible/inventories/home/group_vars/all/main.yml` (variáveis da Global Constraints) — literal na página 01
- Modify: `server/ansible/roles/infra/proxmox-host-config/templates/etc_exports.j2` (exports de `photos` e `files`, mesmas opções do `media`) — literal na página 02
- Modify: `server/ansible/roles/common/tasks/main.yml` (montar `photos` e `files` só com `when_condition: "'core_services' in group_names"`) — literal na página 04
- Modify: `wiki/docs/01-manual-implementacao/02-*.md` (passos `zfs create -o quota=150G data/photos`, `zfs create -o quota=75G data/files`; migração para pool novo com `zfs send | zfs recv` + `mountpoint=/data/<dataset>`)
- Test: `tools/wikisync/tests/test_fotos_arquivos.py`

**Interfaces:**
- Produces: `zfs_photos_dataset_name`, `zfs_files_dataset_name`, `vm_local_data_path`, `immich_version`, `nextcloud_major`, `immich_password_login`, `immich_config_overrides` (Tasks 2–5).

- [ ] **Step 1: Write the failing tests** `test_datasets_exportados_e_montados_na_core` (o `etc_exports.j2` renderizado contém `/data/photos` e `/data/files`; o loop de montagem do `common` tem `zfs_photos_dataset_name` e `zfs_files_dataset_name` com `when_condition` contendo `core_services`) e `test_variaveis_novas` (`main.yml` carregado com `yaml.safe_load` tem as chaves da Global Constraints; `nextcloud_major.isdigit()`; `immich_config_overrides == {}`).
- [ ] **Step 2: Run** `python3 tools/dev.py test` → FAIL nos dois testes.
- [ ] **Step 3: Implement** nas literais da wiki (01, 02, 04) e na página 02; `check` → `sync` → `sync --yes`.
- [ ] **Step 4: Run** `python3 tools/dev.py test` → PASS; `check` só `REF-PENDING`.
- [ ] **Step 5: Commit** `feat(dados): datasets photos e files e caminho local para bancos`

### Task 2: Authelia como provedor OIDC

**Files:**
- Modify: `server/ansible/roles/infra/authelia-config/templates/configuration.yml.j2` (literal na página 05)
- Modify: `server/ansible/inventories/home/group_vars/all/vault.yml.example` (literal na página 01)
- Test: `tools/wikisync/tests/test_fotos_arquivos.py`

**Interfaces:**
- Consumes: vault da Global Constraints.
- Produces: clientes `immich` e `nextcloud`; issuer `https://auth.{{ base_domain }}` (Tasks 3 e 4).

- [ ] **Step 1: Write the failing tests**
  - `test_oidc_clientes`: renderizar o template com valores de teste e `yaml.safe_load`; `identity_providers.oidc.clients` por `client_id`:
    - `immich`: `authorization_policy == "two_factor"`, `require_pkce is True`, `pkce_challenge_method == "S256"`, `token_endpoint_auth_method == "client_secret_basic"`, `redirect_uris == ["https://fotos.<dom>/auth/login", "https://fotos.<dom>/user-settings", "app.immich:///oauth-callback"]`, `scopes == ["openid", "profile", "email"]`;
    - `nextcloud`: idem com `client_secret_post`, `redirect_uris == ["https://nextcloud.<dom>/apps/user_oidc/code"]`, `scopes` com `groups`;
    - `client_secret` = o `secret_digest` (nunca o `secret`); `jwks[0]` com `algorithm: RS256`, `use: sig` e a chave PEM intacta (multilinha).
  - `test_bypass_dos_publicos`: as regras `fotos.`, `nextcloud.`, `office.` existem com `policy: bypass`, uma por domínio, **antes** da regra curinga (AUT-3).
  - `test_authelia_validate_config` (`skipif` sem `authelia` e `openssl` no PATH): gera chave com `openssl genrsa 2048`, digests com `authelia crypto hash generate pbkdf2 --variant sha512 --password <s>` (linha `Digest: …`), renderiza, roda `authelia validate-config --config <arquivo>` → `returncode == 0`. Se o caminho `/config/users_database.yml` for exigido, troque-o no texto por um arquivo temporário.
- [ ] **Step 2: Run** → FAIL (o de validação só falha se o binário existir).
- [ ] **Step 3: Implement** o bloco `identity_providers.oidc` (`hmac_secret`, `jwks` com `key: |` + `{{ authelia_oidc_jwks_key | indent(10) }}`, dois clientes com `response_types: [code]`, `grant_types: [authorization_code]`, `userinfo_signed_response_alg: none`), as três regras `bypass` (comentário: login próprio pelo OIDC; Collabora protegido pelo token WOPI) e as chaves no `vault.yml.example` (com como gerar: `openssl rand -hex 32`, `openssl genrsa 2048`, e o digest com `docker run --rm authelia/authelia:4.38.0 authelia crypto hash generate pbkdf2 --variant sha512 --password <segredo>`). Para instalar o binário de teste: `authelia-v4.38.0-linux-amd64.tar.gz` das releases do GitHub em `$HOME/.local/bin`; se o download for bloqueado, siga sem ele (o teste fica ignorado e isso vai no relatório).
- [ ] **Step 4: Run** → PASS; `check` → `sync --yes`.
- [ ] **Step 5: Commit** `feat(autenticacao): Authelia como provedor OIDC para Immich e Nextcloud`

### Task 3: Stack `photos` (Immich)

**Files:**
- Create: `server/docker/stacks/photos/docker-compose.yml` (redes `proxy` e `internal_services` `external: true`)
- Create: `server/ansible/playbooks/setup-photos-stack-volumes.yml` (molde: `setup-media-stack-volumes.yml`)
- Create: `server/ansible/templates/immich/immich.json.j2`
- Modify: `tools/wikisync/tests/test_observabilidade.py` (`render` registra os filtros `combine(*dicts, recursive=False)` e `to_nice_json` com a semântica do Ansible: `json.dumps(indent=4, sort_keys=True)`)
- Modify: `.env.template` (literal na página 00): bloco `# --- Stack photos ---` com as variáveis do `photos.env`
- Test: `tools/wikisync/tests/test_fotos_arquivos.py`

**Interfaces:**
- Consumes: Task 1 (variáveis), Task 2 (cliente `immich`).
- Produces: serviço `immich_server` porta 2283, container `immich_server` (Task 5).

- [ ] **Step 1: Write the failing tests**
  - `test_photos_servicos`: `set(_svc(PHOTOS)) == {"immich_server", "immich_ml", "immich_redis", "immich_db"}`; imagens de `immich_server`/`immich_ml` terminam em `:${IMMICH_VERSION}`; `immich_redis` e `immich_db` com `@sha256:`.
  - `test_banco_e_cache_no_disco_local`: volume de `/var/lib/postgresql/data` começa com `${PHOTOS_STACK_DB_PATH}`, cache com `${PHOTOS_STACK_MODEL_CACHE_PATH}`; no playbook, essas variáveis começam com `{{ vm_local_data_path }}`, e uma tarefa cria os dois diretórios.
  - `test_immich_rede_e_porta`: `immich_server.ports == ["${CORE_SERVICES_VM_IP_VAR}:2283:2283"]`; label `Host(\`fotos.${BASE_DOMAIN_FROM_VAULT}\`)`; nenhum `authelia` nas labels; env com `DB_HOSTNAME: immich_db`, `REDIS_HOSTNAME: immich_redis`, `IMMICH_CONFIG_FILE: /config/immich.json`.
  - `test_variaveis_photos_no_env`: toda `${VAR}` do compose está nos `stack_configs` do playbook ou entre as comuns do `portainer_stack_env.j2`; a tarefa do `photos.env` tem `mode: '0600'`.
  - `test_immich_json`: renderizar `immich/immich.json.j2` → `json.loads`:
    - `oauth.enabled`, `oauth.autoLaunch` verdadeiros; `oauth.autoRegister is False`;
    - `oauth.issuerUrl == "https://auth.<dom>"`, `clientId == "immich"`, `clientSecret == <secret>`, `tokenEndpointAuthMethod == "client_secret_basic"`;
    - `server.externalDomain == "https://fotos.<dom>"`, `machineLearning.urls == ["http://immich_ml:3003"]`, `storageTemplate.template == "{{y}}/{{y}}-{{MM}}-{{dd}}/{{filename}}"`, `backup.database.keepLastAmount == 14`;
    - `passwordLogin.enabled` segue `immich_password_login` (testar `"False"` como texto → `False`).
  - `test_immich_overrides_mesclam`: com `immich_config_overrides={"oauth": {"buttonText": "X"}, "machineLearning": {"ocr": {"enabled": False}}}` → `buttonText == "X"`, `oauth.enabled` e `clientId` mantidos, `machineLearning.urls` mantido.
  - `test_immich_json_0600`: a tarefa que gera o `immich.json` tem `mode: '0600'`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**
  - **Compose:** imagens e digests de `immich_redis`/`immich_db` copiados **literalmente** do `docker-compose.yml` oficial da release `v3.3.3` (`https://raw.githubusercontent.com/immich-app/immich/v3.3.3/docker/docker-compose.yml`), com `shm_size: 128mb` e `POSTGRES_INITDB_ARGS: '--data-checksums'` no banco; `restart: unless-stopped`; `healthcheck` como no oficial; `immich_ml` só em `internal_services`.
  - **Playbook:** diretórios `docker-volumes/immich/config`, `{{ vm_local_data_path }}/immich-db` (`0700`, sem owner) e `immich-model-cache`; `immich.json` (`0600`); `photos.env` (`0600`).
  - **Template:** a base como dicionário Jinja (placeholders do storage template dentro de `{% raw %}`), `| combine(immich_config_overrides, recursive=True) | to_nice_json`.
- [ ] **Step 4: Run** → PASS; `check` → `sync --yes` (`.env.template`).
- [ ] **Step 5: Commit** `feat(fotos): stack photos com Immich, configuração por arquivo e OIDC`

### Task 4: Stack `cloud` (Nextcloud, cron, Collabora)

**Files:**
- Create: `server/docker/stacks/cloud/docker-compose.yml`
- Modify: `server/docker/stacks/apps/docker-compose.yml` (saem `nextcloud_app`, `nextcloud_db`, `nextcloud_redis` e o bloco de produtividade)
- Create: `server/ansible/playbooks/setup-cloud-stack-volumes.yml`
- Create: `server/ansible/templates/nextcloud/10-homeserver.sh.j2`, `server/ansible/templates/nextcloud/backup-nextcloud-db.sh.j2`
- Modify: `server/ansible/playbooks/setup-productivity-automation-volumes.yml` (sai tudo do Nextcloud; o `productivity.env` fica só com `CORE_SERVICES_VM_IP_VAR`, usado pelo Prometheus da `apps`)
- Modify: `server/ansible/roles/infra/traefik-config/templates/nextcloud_middleware.yml.j2` (literal na página 05): middleware `nextcloud-dav` (`redirectRegex`, `regex: "^https://(.*)/.well-known/(?:card|cal)dav"`, `replacement: "https://${1}/remote.php/dav/"`, `permanent: true`)
- Modify: `.env.template` (página 00): bloco `# --- Stack cloud ---`; saem `PROD_STACK_NEXTCLOUD_*`
- Test: `tools/wikisync/tests/test_fotos_arquivos.py`

**Interfaces:**
- Consumes: Task 1, Task 2 (cliente `nextcloud`).
- Produces: containers `nextcloud_app` (porta 80) e `collabora` (porta 9980) (Task 5).

- [ ] **Step 1: Write the failing tests**
  - `test_cloud_servicos_e_apps_sem_nextcloud`: `set(_svc(CLOUD)) == {"nextcloud_app", "nextcloud_cron", "nextcloud_redis", "nextcloud_db", "collabora"}`; nenhum `nextcloud*` em `_svc(APPS)`.
  - `test_cron_igual_ao_app`: `nextcloud_cron.image == nextcloud_app.image == "nextcloud:${NEXTCLOUD_MAJOR}-apache"`; `entrypoint == "/cron.sh"`; mesmos `volumes`.
  - `test_nextcloud_publico_com_dav`: as labels de `nextcloud_app` têm `nextcloud-dav@file` e `nextcloud-headers@file` nos middlewares e nenhum `authelia`; o env tem `TRUSTED_PROXIES`, `OVERWRITEPROTOCOL: https`, `OVERWRITECLIURL: https://nextcloud.${BASE_DOMAIN_FROM_VAULT}`, `NEXTCLOUD_OIDC_CLIENT_SECRET: ${NEXTCLOUD_OIDC_CLIENT_SECRET}`; o hook está montado em `/docker-entrypoint-hooks.d/before-starting:ro`; o middleware renderizado tem `nextcloud-dav.redirectRegex`.
  - `test_collabora_wopi_pela_lan`: `collabora.extra_hosts == ["nextcloud.${BASE_DOMAIN_FROM_VAULT}:${CORE_SERVICES_VM_IP_VAR}"]`; env `aliasgroup1 == "https://nextcloud.${BASE_DOMAIN_FROM_VAULT}:443"`, `server_name == "office.${BASE_DOMAIN_FROM_VAULT}"`, `extra_params` com `--o:ssl.enable=false` e `--o:ssl.termination=true`; label `Host(\`office.${BASE_DOMAIN_FROM_VAULT}\`)` sem `authelia`.
  - `test_banco_nextcloud_local`: volume do Postgres começa com `${CLOUD_STACK_NEXTCLOUD_DB_PATH}`, que no playbook começa com `{{ vm_local_data_path }}`; `CLOUD_STACK_NEXTCLOUD_DATA_PATH` usa `zfs_files_dataset_name`.
  - `test_variaveis_cloud_no_env`: como na Task 3 (0600 inclusive).
  - `test_hook_sem_segredo_e_idempotente`: renderizar com `base_domain` e `oidc_clients` de teste → o valor do segredo não aparece; aparece `$NEXTCLOUD_OIDC_CLIENT_SECRET`; toda linha com `app:install` tem `|| ` seguido de `app:enable`; contém `app:disable photos`, `user_oidc:provider`, `allow_multiple_user_backends`, `wopi_url`, `public_wopi_url`, `wopi_allowlist`, `max_chunk_size`, `default_phone_region`; `bash -n` sobre o arquivo → `returncode == 0`. A tarefa do playbook grava com `mode: '0755'`.
  - `test_dump_diario_do_nextcloud`: o playbook instala o script (`0750`), um `.service` e um `.timer` (`OnCalendar` diário, `Persistent=true`) e habilita o timer; o script renderizado usa `pg_dump`, grava em `…/nextcloud/db-dumps` e apaga dumps com mais de 14 dias.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**
  - **Hook:** `#!/bin/bash`, `set -eu`, função `occ() { php /var/www/html/occ "$@"; }`. Passos do spec §3 (Hook):
    - `user_oidc:provider Authelia --clientid=nextcloud --clientsecret="$NEXTCLOUD_OIDC_CLIENT_SECRET" --discoveryuri=https://auth.<dom>/.well-known/openid-configuration --scope="openid email profile groups" --unique-uid=0 --mapping-uid=preferred_username`;
    - `config:system:set user_oidc default_token_endpoint_auth_method --value=client_secret_post`, `… allow_multiple_user_backends --value=0 --type=integer`, `… enrich_login_id_token_with_userinfo --value=true --type=boolean`;
    - `config:app:set richdocuments wopi_url --value=http://collabora:9980`, `public_wopi_url --value=https://office.<dom>`, `wopi_allowlist --value=172.16.0.0/12`;
    - `config:app:set files max_chunk_size --value=52428800`;
    - `config:system:set default_phone_region --value=BR`, `maintenance_window_start --value=4 --type=integer`.
  - **Compose:**
    - `nextcloud_app`: `APACHE_DISABLE_REWRITE_IP: "1"`, `TRUSTED_PROXIES: "172.16.0.0/12"`;
    - `collabora`: `collabora/code:latest`, `dictionaries: "pt_BR en_US"`.
  - **Playbook:** diretórios `docker-volumes/nextcloud/{html,config,hooks,db-dumps}` e `{{ vm_local_data_path }}/nextcloud-db` (`0700`, sem owner); hook (`0755`); script, unidades e timer (`systemd` com `daemon_reload`); `cloud.env` (`0600`).
- [ ] **Step 4: Run** → PASS (inclusive os testes de mídia/observabilidade que leem o `apps`); `check` → `sync --yes`.
- [ ] **Step 5: Commit** `feat(arquivos): stack cloud com Nextcloud, cron, Collabora, OIDC e dump diário`

### Task 5: Painel e disponibilidade

**Files:**
- Modify: `server/ansible/templates/prometheus.yml.j2` (alvos `http://immich_server:2283/api/server/ping` `{app: 'immich'}` e `http://collabora:9980/hosting/discovery` `{app: 'collabora'}`; `nextcloud` mantém `http://nextcloud_app/status.php`)
- Modify: `server/ansible/templates/homepage/services.yaml.j2` (no grupo `produtividade`: `immich` com widget `type: immich`, `url: http://immich_server:2283`, `key: {{HOMEPAGE_VAR_IMMICH_KEY}}`, `version: 2`; `collabora` sem widget; `href`/`server: core`/`container` como PNL-1)
- Modify: `server/ansible/playbooks/setup-monitoring-stack-volumes.yml` (`HOMEPAGE_VAR_IMMICH_KEY` de `homepage_widget_keys.immich`) e `server/docker/stacks/apps/docker-compose.yml` (env da Homepage)
- Modify: `vault.yml.example` (página 01): `homepage_widget_keys.immich`
- Test: `tools/wikisync/tests/test_fotos_arquivos.py`

- [ ] **Step 1: Write the failing tests**
  - `test_sondas_fotos_arquivos`: no `blackbox_http`, alvos com `app` `immich`, `nextcloud` e `collabora` nas URLs internas acima.
  - `test_homepage_immich`: entrada `immich` com `widget.type == "immich"` e `key` `{{HOMEPAGE_VAR_IMMICH_KEY}}`; `HOMEPAGE_VAR_IMMICH_KEY` no env da Homepage e nos `stack_configs` do playbook, vindo de `homepage_widget_keys.immich`; entrada `collabora` presente.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** as mudanças; `vault.yml.example` pela wiki.
- [ ] **Step 4: Run** → PASS; `check` → `sync --yes`.
- [ ] **Step 5: Commit** `feat(painel,notificacoes): Immich, Nextcloud e Collabora no painel e no blackbox`

### Task 6: Documentação, catálogo, índice e verificação final

**Files:**
- Create: `wiki/docs/01-manual-implementacao/11-fotos-arquivos.md` (conteúdo do spec §7; cita com caminho completo os composes, playbooks e templates estruturais; aviso DAD-2 sobre os bancos locais)
- Modify:
  - páginas 00, 01, 05 (texto em volta das literais);
  - página 06 (apps públicos com OIDC);
  - página 07 (sai o Nextcloud, link para a 11; tabela de `.env` sem `productivity.env` do Nextcloud);
  - página 09 (sondas e widget);
  - `04-manutencao-recuperacao/02-backup-restore-estrategia.md` (datasets `photos`/`files`, dumps do Immich em `photos/backups`, `nextcloud/db-dumps`, bancos locais só pelos dumps, restauração de cada um);
  - `wiki/mkdocs.yml` (nav);
  - `INDEX.md`;
  - catálogo (linhas `immich`, `collabora`, `nextcloud` como nas Decisões do plano, Exposição `publica`, Página = 11);
  - índice (pela skill `update-index`): **DAD-5**, PNL-2 com `immich` (`homepage_widget_keys.immich`) e DAD-1 remetendo à DAD-5. Texto da DAD-5: "Dados = `nfs` com banco de dados no disco local: o volume do banco vem de `{{ vm_local_data_path }}` pelo playbook da stack, a página da aplicação avisa que o banco fica fora dos snapshots e documenta o dump para o NFS, e a página de backup lista o dump".
- Test: `tools/wikisync/tests/test_fotos_arquivos.py`

- [ ] **Step 1: Write the failing test** `test_catalogo_fotos_arquivos`: as linhas `immich`, `nextcloud` e `collabora` do catálogo têm Stack `photos`/`cloud`/`cloud`, Exposição `publica`, Subdomínio `fotos`/`nextcloud`/`office` e Página `11-fotos-arquivos.md`; a página 11 existe e está no nav.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** páginas, catálogo, índice (`update-index`) e `INDEX.md`.
- [ ] **Step 4: Verify**
  - `dev.py test`: todos passam, exceto os ignorados por binário ausente;
  - `check`: só `REF-PENDING`;
  - `sync`: sem diferenças;
  - `build`: rc 0, sem WARNING nem INFO de âncora;
  - `lint`: OK;
  - skill `audit-integrations` sem ❌/⚠️, só `✋` documentados (o OIDC de cada app e a promoção a admin do Nextcloud).
- [ ] **Step 5: Commit** `docs(fotos-arquivos): página 11, catálogo, índice e backup`
