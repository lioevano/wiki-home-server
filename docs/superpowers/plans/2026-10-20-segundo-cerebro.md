# Segundo cérebro: Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vaults do Obsidian (Pessoal, Trabalho, Estudos) sincronizados pelo Syncthing num dataset novo, indexados localmente pelo qmd junto com os documentos do Nextcloud convertidos para Markdown, e expostos por MCP (busca para tudo, escrita só em Trabalho e Estudos) ao claude.ai, ao Claude Code, ao Open WebUI e aos agentes da 4c.

**Architecture:** Stack nova `notes` na `ai-desktop-vm`. O escopo é garantido por montagem: o `qmd` vê tudo em `:ro`; o `notes_escrita` (server-filesystem via supergateway) só vê `trabalho/` e `estudos/`. Dois `mcp-auth-proxy` fazem o OAuth exigido pelo claude.ai e delegam o login ao Authelia (cliente OIDC `mcp`, grupo `admins`). Timers systemd convertem os documentos do Nextcloud (markitdown) e reindexam (`qmd update`/`embed`) a cada 10 min. Snapshots ZFS automáticos só em `data/notes`.

**Tech Stack:** Syncthing 2.1.6, qmd 2.8.3 (`@tobilu/qmd`, Node 22, GGUF locais com Vulkan), `@modelcontextprotocol/server-filesystem` 2.0.0 (Node 24) + supergateway 4.2.0, markitdown 0.1.8 (Python 3.13), `ghcr.io/sigbit/mcp-auth-proxy:v2.10.2`, Authelia 4.38 OIDC, Open WebUI v0.12.3 (`TOOL_SERVER_CONNECTIONS`), Grafana Alloy (coletor `systemd`), zfs-auto-snapshot, Ansible, pytest, MkDocs.

**Spec:** `docs/superpowers/specs/2026-10-20-segundo-cerebro-design.md` (com a seção 13, "Ajustes do plano", acrescentada na Task 0).

## Global Constraints

- Wiki-first. **Literais:** `group_vars/all/main.yml` e `vault.yml.example` (página 01), `.env.template` (00), `etc_exports.j2` e tarefas do `proxmox-host-config` (02), `roles/common/tasks/main.yml` (04), `configuration.yml.j2` do Authelia e `dynamic_rag_services.yml.j2` (05), arquivos de `server/ansible/templates/notes/` (página nova 12). **Estruturais** (diretos, citados com caminho): `docker/stacks/notes/docker-compose.yml`, `docker/stacks/ai/docker-compose.yml`, `playbooks/setup-notes-volumes.yml`, `prometheus.yml.j2`, `homepage/services.yaml.j2`, `grafana/alerting/rules.yml.j2`, `config.alloy.j2`.
- Ambiente: `export HOMESERVER_VENV=$HOME/.venvs/homeserver PATH=$HOME/.local/bin:$PATH` na mesma chamada; fluxo `dev.py check` (só `REF-PENDING`) → `sync` → `sync --yes` → `test` → `lint`; build estrito num clone local do HEAD (`git clone -q --no-hardlinks . /tmp/rb/repo && cd /tmp/rb/repo && $HOMESERVER_VENV/bin/mkdocs build --strict -f wiki/mkdocs.yml -d /tmp/rb/site`).
- Testes em `tools/wikisync/tests/test_segundo_cerebro.py` (`from test_observabilidade import ROOT, render`; `from test_midia import _svc, _env`; `from test_fotos_arquivos import _authelia, _pb_tasks, _env_task, _configs, _vars_compose, _volume, COMUNS, DOM, OIDC`).
- **Versões (`group_vars`):** `syncthing_version: "2.1.6"`, `qmd_version: "2.8.3"`, `mcp_filesystem_version: "2.0.0"`, `supergateway_version: "4.2.0"`, `markitdown_version: "0.1.8"`, `mcp_auth_proxy_version: "v2.10.2"`. Bases: `node:22-bookworm-slim` (qmd), `node:24-bookworm-slim` (escrita), `python:3.13-slim` (conversor). Nenhuma imagem `:latest`.
- **Nomes:** dataset `zfs_notes_dataset_name: "notes"` (cota 20G, manual na página 02); stack/arquivo `notes`; pastas `pessoal`, `trabalho`, `estudos`; serviços `syncthing`, `qmd`, `notes_escrita`, `mcp_auth_busca`, `mcp_auth_escrita`; rede compartilhada `notes_mcp` (`name: notes_mcp`); imagens locais `localhost/homeserver/qmd`, `localhost/homeserver/notes-escrita`, `localhost/homeserver/notes-conversor` (tag = versão do componente principal), `pull_policy: never`, label `diun.enable: "false"`; subdomínios `notas` (busca), `escrita`, `sync`; portas na LAN `8481` (busca), `8482` (escrita), `8384` (Syncthing), `22000/tcp+udp`.
- **Variáveis do `notes.env`** (nomes exatos, além de `COMUNS`): `AI_DESKTOP_VM_IP`, `AI_RENDER_GID`, `NOTES_STACK_DATA_PATH` (= `{{ vm_nfs_mount_base_path }}/{{ zfs_notes_dataset_name }}`), `NOTES_STACK_SYNCTHING_CONFIG_PATH` (NFS `docker-volumes/syncthing/config`), `NOTES_STACK_SYNCTHING_DB_PATH` (`{{ vm_local_data_path }}/syncthing`), `NOTES_STACK_QMD_CONFIG_PATH` (NFS `docker-volumes/qmd/config`), `NOTES_STACK_QMD_CACHE_PATH` (`{{ vm_local_data_path }}/qmd`), `NOTES_STACK_DOCUMENTOS_PATH` (`{{ vm_local_data_path }}/notes-documentos`), `NOTES_STACK_MCP_AUTH_BUSCA_PATH` e `NOTES_STACK_MCP_AUTH_ESCRITA_PATH` (`{{ vm_local_data_path }}/mcp-auth-{busca,escrita}`), `QMD_IMAGE`, `NOTES_ESCRITA_IMAGE`, `SYNCTHING_API_KEY`, `MCP_OIDC_CLIENT_SECRET`, `MCP_AUTH_HMAC_SECRET`. Arquivo `0600`.
- **Vault (novas):** `oidc_clients.mcp.{secret,secret_digest}`, `mcp_auth_hmac_secret` (`openssl rand -base64 32`), `syncthing_gui_password`, `syncthing_api_key` (`openssl rand -hex 24`). **`group_vars` (novas):** as versões acima, `zfs_notes_dataset_name`, `syncthing_gui_user: "admin"`, `notes_nextcloud_usuario` (id do usuário no Nextcloud; `occ user:list`), `notes_documentos_extensoes: [pdf, docx, pptx, xlsx, html, htm, csv, txt, md]`, `notes_documentos_max_mb: 50`, `qmd_modelos: {}` (vazio = padrões do qmd).
- Cliente OIDC `mcp`: `client_secret_basic`, **`require_pkce: false`** (o mcp-auth-proxy não envia PKCE ao provedor), `two_factor`, escopos `openid profile email groups`, redirects `https://notas.{{ base_domain }}/.auth/oidc/callback` e `https://escrita.{{ base_domain }}/.auth/oidc/callback`.
- Nada de `docker compose up/down`, `ansible-playbook` sem `--check`/`--syntax-check`, `ansible-vault`, `ssh` ou `git push`. Commits com o trailer da sessão. Execução direta em `main`, com ledger.

## Review Focus

1. **Vault Pessoal ou arquivos do Nextcloud graváveis por algum serviço de IA:** só o `syncthing` monta `pessoal` com escrita; `files` sempre `ro` (VM e container) → Tasks 1, 3, 4, 5 testam todas as montagens de todos os serviços.
2. **MCP sem autenticação alcançável pela LAN ou pela internet:** `qmd` e `notes_escrita` sem `ports`; proxies exigem `/groups=admins`; `notas.`/`escrita.` sem forward-auth mas com bypass explícito no Authelia (AUT-3) → Tasks 3, 4, 6.
3. **Montagem NFS do Nextcloud ausente (pasta vazia) apagando toda a cópia convertida:** o conversor aborta (código 2) sem remover nada quando a origem não existe ou está vazia e o manifesto não → Task 2.
4. **Um documento corrompido parando a conversão inteira, ou nome de arquivo estranho/symlink escrevendo fora do destino:** falha é contada e o resto segue; symlinks e ocultos ignorados; toda saída fica dentro do destino → Task 2.
5. **Requisição do proxy recusada pelo qmd por causa do cabeçalho `Host`** (o proxy repassa `notas.<domínio>`): `QMD_ALLOWED_HOSTS` inclui `qmd`, `qmd:8181` e `notas.${BASE_DOMAIN_FROM_VAULT}` → Task 3.

---

### Task 0: Ajustes do plano na especificação

**Files:**
- Modify: `docs/superpowers/specs/2026-10-20-segundo-cerebro-design.md` (seção nova 13)

- [ ] **Step 1: Acrescentar a seção "13. Ajustes do plano"** com: cliente `mcp` sem PKCE (o proxy não envia); regras `bypass` para `notas.` e `escrita.` no Authelia (AUT-3); retenção padrão do zfs-auto-snapshot (15 min ×4, hora ×24, dia ×31, semana ×8, mês ×12); sem job de métricas do Syncthing nem alerta de pasta (evita token no `prometheus.yml`; disponibilidade pela sonda); dados dos mcp-auth-proxy no disco local (regeráveis); export de `notes` só para o IP da `ai-desktop-vm`; correção da condição `'ai-desktop-vm' in group_names` → `'ai_desktop' in group_names` (o `rag_sources` nunca era montado); Open WebUI pelos `TOOL_SERVER_CONNECTIONS` (sem `access_grants` = só admins); modelo do qmd trocável por `qmd_modelos` no `index.yml` (não por variável de ambiente).
- [ ] **Step 2: Commit** `docs(spec): ajustes do plano no segundo cérebro`

### Task 1: Dataset, exports, montagens e snapshots

**Files:**
- Modify: `main.yml` (`zfs_notes_dataset_name`, versões e variáveis da Global Constraints) — página 01
- Modify: `roles/infra/proxmox-host-config/templates/etc_exports.j2` e `tasks/main.yml` (página 02): export de `notes` para `{{ ai_desktop_vm_ip_var }}`; `apt` de `zfs-auto-snapshot`; `community.general.zfs` com `extra_zfs_properties: {"com.sun:auto-snapshot": "false"}` em `data` e `"true"` em `data/{{ zfs_notes_dataset_name }}`
- Modify: `roles/common/tasks/main.yml` (página 04): item `notes` e item `files` com `opts` só leitura na `ai_desktop`; `opts: "{{ item.opts | default(<opções atuais>) }}"`; condição do `rag_sources` corrigida
- Modify: página 02 (`zfs create -o quota=20G data/notes`, `chown`) e guia `03-guias-sustentacao/12-guia-snapshots-zfs.md` (política: automático só em `notes`)
- Test: `tools/wikisync/tests/test_segundo_cerebro.py`

**Interfaces:**
- Produces: `/mnt/pve_data_zfs/notes` (rw) e `/mnt/pve_data_zfs/files` (ro) na `ai-desktop-vm`; `zfs_notes_dataset_name`.

- [ ] **Step 1: Write the failing tests**
  - `test_export_notes_so_para_a_vm_de_ia`: render de `etc_exports.j2` (com `ai_desktop_vm_ip_var="192.168.15.68"` e `groups`) tem a linha `/data/notes 192.168.15.68(rw,sync,no_subtree_check,all_squash,anonuid=…,anongid=…)`; nenhuma linha de `notes` com o CIDR.
  - `test_montagens_da_vm_de_ia`: no loop de montagem do `roles/common`, o item `notes` tem condição `'ai_desktop' in group_names`; o item `files` para `ai_desktop` tem `opts` começando com `ro,`; o item `rag_sources` usa `'ai_desktop' in group_names`; nenhuma condição contém `'ai-desktop-vm' in group_names`.
  - `test_snapshots_so_em_notes`: as tarefas do `proxmox-host-config` instalam `zfs-auto-snapshot` e definem `com.sun:auto-snapshot` `false` em `{{ zfs_pool_name | default('data') }}`/`data` e `true` em `data/{{ zfs_notes_dataset_name }}` (asserção sobre `extra_zfs_properties`).
- [ ] **Step 2: Run** `dev.py test` → FAIL.
- [ ] **Step 3: Implement** pela wiki (01, 02, 04, guia 12); `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS (inclusive `test_datasets_exportados_e_montados_na_core`).
- [ ] **Step 5: Commit** `feat(notas): dataset notes, montagens na VM de IA e snapshots automáticos só nele`

### Task 2: Conversor de documentos do Nextcloud

**Files:**
- Create: `server/ansible/templates/notes/conversor.py` (literal na página 12; copiado com `ansible.builtin.copy`)
- Create: `server/ansible/templates/notes/Dockerfile.conversor.j2` (`FROM python:3.13-slim`; `pip install --no-cache-dir "markitdown[pdf,docx,pptx,xlsx]=={{ markitdown_version }}"`; `COPY conversor.py /app/`; `USER` não-root; `ENTRYPOINT ["python", "/app/conversor.py"]`)
- Test: `tools/wikisync/tests/test_segundo_cerebro.py` (importa o módulo por `importlib.util.spec_from_file_location`)

**Interfaces:**
- Produces:
  - `@dataclass Resumo: convertidos: int; mantidos: int; removidos: int; falhas: list[str]`
  - `class OrigemVazia(Exception)`
  - `sincronizar(origem: Path, destino: Path, extensoes: set[str], max_bytes: int, converter: Callable[[Path], str]) -> Resumo`
  - `main(argv: list[str] | None = None) -> int` — `--origem`, `--destino`, `--extensoes` (vírgulas), `--max-mb`; imprime `convertidos=N mantidos=N removidos=N falhas=N`; retorna 0, ou 2 em `OrigemVazia`.
  - Saída: `destino/<rel>.md` (ex.: `a/b.pdf` → `a/b.pdf.md`), com cabeçalho `---\norigem: "Nextcloud/<rel>"\n---\n\n`; manifesto `destino/.manifesto.json` = `{rel: [tamanho, mtime_ns]}`.

- [ ] **Step 1: Write the failing tests** (com `tmp_path` e um `converter` falso que devolve `f"texto de {p.name}"` e lança `ValueError` para nomes com `quebrado`)
  - `test_converte_e_mantem`: 1ª chamada com `a.pdf`, `sub/b.docx`, `foto.jpg` → `convertidos == 2`, arquivos `a.pdf.md` e `sub/b.docx.md` com o cabeçalho `origem: "Nextcloud/sub/b.docx"`; nenhum `.jpg.md`; 2ª chamada sem mudanças → `mantidos == 2`, `convertidos == 0`; alterar `a.pdf` (conteúdo e mtime) → `convertidos == 1`.
  - `test_remove_o_que_sumiu`: apagar `sub/b.docx` → `removidos == 1`, `sub/b.docx.md` e o diretório vazio `sub/` saem; chave fora do manifesto.
  - `test_falha_nao_para_o_resto`: `quebrado.pdf` + `ok.pdf` → `ok.pdf.md` existe, `falhas == ["quebrado.pdf"]`, `quebrado.pdf` fora do manifesto (tenta de novo na próxima).
  - `test_ignora_symlink_oculto_e_grande`: symlink para arquivo fora da origem, `.oculto/x.pdf`, `.y.pdf` e um arquivo maior que `max_bytes` → nenhum convertido; nenhuma escrita fora de `destino` (varredura de `tmp_path` só encontra arquivos novos dentro de `destino`).
  - `test_origem_vazia_nao_apaga`: com manifesto não vazio, origem inexistente ou vazia → `OrigemVazia`; arquivos de `destino` intactos; `main([...])` retorna `2`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** em `conversor.py`: `os.walk(followlinks=False)` pulando nomes que começam com `.`; extensão sem ponto, minúscula; escrita atômica (`.tmp` + `os.replace`); `main` monta o `converter` real: `md`/`txt` lidos como UTF-8 (`errors="replace"`), o resto por `MarkItDown().convert(str(p)).text_content` (import dentro de `main`, para os testes não precisarem do markitdown). Página 12 com o literal; `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(notas): conversor incremental dos documentos do Nextcloud para Markdown`

### Task 3: Busca (qmd) e esqueleto da stack `notes`

**Files:**
- Create: `server/docker/stacks/notes/docker-compose.yml` (serviço `qmd`; redes `notes_network` e `notes_mcp` com `name: notes_mcp`)
- Create: `server/ansible/playbooks/setup-notes-volumes.yml` (`hosts: ai_desktop`; diretórios da Global Constraints com dono `docker_puid:docker_pgid`; `notes.env` `0600` via `portainer_stack_env.j2` como nas outras stacks; GID do `render` por `getent`; build das imagens)
- Create: `server/ansible/templates/notes/Dockerfile.qmd.j2` (`FROM node:22-bookworm-slim`; `apt-get install -y --no-install-recommends mesa-vulkan-drivers libvulkan1 ca-certificates`; `npm install -g @tobilu/qmd@{{ qmd_version }}`)
- Create: `server/ansible/templates/notes/index.yml.j2` (coleções `pessoal`, `trabalho`, `estudos`, `documentos` em `/notes/<nome>`, `pattern: "**/*.md"`, `ignore: [".obsidian/**", ".trash/**", "**/*.sync-conflict-*"]`, `context."/"` em português dizendo o que é cada coleção e que `pessoal` e `documentos` são só leitura; bloco `models:` só se `qmd_modelos`)
- Modify: `.env.template` (página 00)
- Test: `tools/wikisync/tests/test_segundo_cerebro.py`

**Interfaces:**
- Consumes: Task 1 (montagens), Task 2 (`Dockerfile.conversor.j2`, `conversor.py` — o build da imagem do conversor também entra aqui).
- Produces: `http://qmd:8181/mcp` na rede `notes_mcp`; imagens `localhost/homeserver/qmd:{{ qmd_version }}` e `localhost/homeserver/notes-conversor:{{ markitdown_version }}`; `notes.env`.

- [ ] **Step 1: Write the failing tests**
  - `test_qmd_so_leitura_e_sem_porta`: `qmd` sem `ports`; volumes `${NOTES_STACK_DATA_PATH}/pessoal:/notes/pessoal:ro`, idem `trabalho` e `estudos`, `${NOTES_STACK_DOCUMENTOS_PATH}:/notes/documentos:ro`; os únicos volumes sem `:ro` são `${NOTES_STACK_QMD_CONFIG_PATH}:/config` e `${NOTES_STACK_QMD_CACHE_PATH}:/cache`; `devices == ["/dev/dri"]`; `group_add == ["${AI_RENDER_GID}"]`; `image == "${QMD_IMAGE}"`, `pull_policy == "never"`; `command == ["qmd", "mcp", "--http", "--host", "0.0.0.0", "--port", "8181"]`; env `QMD_CONFIG_DIR == "/config"`, `XDG_CACHE_HOME == "/cache"`, `QMD_ALLOWED_HOSTS == "qmd,qmd:8181,notas.${BASE_DOMAIN_FROM_VAULT}"`; redes `notes_mcp`.
  - `test_index_qmd`: render de `index.yml.j2` → quatro coleções com os caminhos e `ignore` acima; sem `models` com `qmd_modelos={}`; com `qmd_modelos={"embed": "hf:x/y/z.gguf"}` → `models.embed`.
  - `test_imagens_locais_reconstroem`: no playbook, cada `community.docker.docker_image` (`qmd`, `notes-conversor`) tem `source: build`, `name` `localhost/homeserver/…`, `force_source` ligado ao `register` da tarefa que grava o Dockerfile (corrige o problema da 4a); o Dockerfile do qmd renderizado contém `@tobilu/qmd@2.8.3` e `mesa-vulkan-drivers`; o do conversor, `markitdown[pdf,docx,pptx,xlsx]==0.1.8`.
  - `test_variaveis_notes_no_env`: `_vars_compose(NOTES) <= set(_configs(PB_NOTES, "notes.env")) | COMUNS`; `mode == "0600"`; os caminhos locais começam com `{{ vm_local_data_path }}/`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** (compose, playbook, templates pela página 12, `.env.template` pela 00); `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(notas): busca local com qmd sobre os vaults e documentos`

### Task 4: Escrita com escopo

**Files:**
- Create: `server/ansible/templates/notes/Dockerfile.escrita.j2` (`FROM node:24-bookworm-slim`; `npm install -g supergateway@{{ supergateway_version }} @modelcontextprotocol/server-filesystem@{{ mcp_filesystem_version }}`; `USER node`)
- Modify: compose `notes` (serviço `notes_escrita`), playbook (build `localhost/homeserver/notes-escrita:{{ mcp_filesystem_version }}`)
- Test: `tools/wikisync/tests/test_segundo_cerebro.py`

**Interfaces:**
- Produces: `http://notes_escrita:8000/mcp` na rede `notes_mcp`; healthcheck em `/healthz`.

- [ ] **Step 1: Write the failing tests**
  - `test_escrita_so_trabalho_e_estudos`: volumes do `notes_escrita` == `["${NOTES_STACK_DATA_PATH}/trabalho:/notes/trabalho", "${NOTES_STACK_DATA_PATH}/estudos:/notes/estudos"]` exatamente; sem `ports`; `user == "${DOCKER_PUID}:${DOCKER_PGID}"`; redes só `notes_mcp`; `command == ["supergateway", "--stdio", "mcp-server-filesystem /notes/trabalho /notes/estudos", "--outputTransport", "streamableHttp", "--stateful", "--sessionTimeout", "600000", "--port", "8000", "--healthEndpoint", "/healthz"]`.
  - `test_ninguem_mais_escreve_em_pessoal_ou_files`: para todo serviço do compose `notes`, todo volume que contenha `/pessoal` ou o caminho de `files` termina em `:ro`, exceto o do `syncthing` sobre `${NOTES_STACK_DATA_PATH}` (raiz).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(notas): MCP de escrita só em Trabalho e Estudos`

### Task 5: Syncthing

**Files:**
- Modify: compose `notes` (serviço `syncthing`, imagem `docker.io/syncthing/syncthing:2.1.6`), playbook (tarefa `generate` antes do deploy)
- Modify: `vault.yml.example` (`syncthing_gui_password`, `syncthing_api_key`) e `main.yml` (`syncthing_gui_user`) — página 01
- Test: `tools/wikisync/tests/test_segundo_cerebro.py`

**Interfaces:**
- Produces: painel em `${AI_DESKTOP_VM_IP}:8384`, sincronização em `${AI_DESKTOP_VM_IP}:22000`.

- [ ] **Step 1: Write the failing tests**
  - `test_syncthing`: env `PUID == "${DOCKER_PUID}"`, `PGID == "${DOCKER_PGID}"`, `STHOMEDIR == ""`, `STCONFDIR == "/var/syncthing/config"`, `STDATADIR == "/var/syncthing/data"`, `STGUIAPIKEY == "${SYNCTHING_API_KEY}"`, `STNOUPGRADE == "1"`; volumes `${NOTES_STACK_DATA_PATH}:/var/syncthing/notes`, `${NOTES_STACK_SYNCTHING_CONFIG_PATH}:/var/syncthing/config`, `${NOTES_STACK_SYNCTHING_DB_PATH}:/var/syncthing/data`; `ports == ["${AI_DESKTOP_VM_IP}:8384:8384", "${AI_DESKTOP_VM_IP}:22000:22000/tcp", "${AI_DESKTOP_VM_IP}:22000:22000/udp"]`; healthcheck em `/rest/noauth/health`.
  - `test_syncthing_generate`: tarefa `ansible.builtin.command` com `docker run --rm` da mesma imagem, `generate --gui-user {{ syncthing_gui_user }} --gui-password -`, `stdin: "{{ syncthing_gui_password }}"`, `creates` apontando para `config.xml` do diretório de config, `no_log: true`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(notas): Syncthing como nó do servidor`

### Task 6: Acesso remoto (mcp-auth-proxy, Authelia, Traefik)

**Files:**
- Modify: compose `notes` (`mcp_auth_busca`, `mcp_auth_escrita`)
- Modify: `configuration.yml.j2` do Authelia (página 05): cliente `mcp` (Global Constraints) e regras `bypass` para `notas.` e `escrita.` antes da curinga
- Modify: `dynamic_rag_services.yml.j2` (página 05): routers `notas` → `:8481` e `escrita` → `:8482` **sem** middleware; `sync` → `:8384` com `authelia-forwardauth@docker`
- Modify: `vault.yml.example` (`oidc_clients.mcp`, `mcp_auth_hmac_secret`); página 05 (Public Hostnames `notas`, `escrita`, `sync`)
- Test: `tools/wikisync/tests/test_segundo_cerebro.py`; `OIDC` de teste em `test_fotos_arquivos.py` ganha `mcp`

**Interfaces:**
- Consumes: Tasks 3 e 4 (backends).
- Produces: `https://notas.<domínio>/mcp` e `https://escrita.<domínio>/mcp` com OAuth 2.1 + DCR.

- [ ] **Step 1: Write the failing tests**
  - `test_proxies_mcp`: para (`mcp_auth_busca`, `notas`, `http://qmd:8181/mcp`, `8481`) e (`mcp_auth_escrita`, `escrita`, `http://notes_escrita:8000/mcp`, `8482`): `image == "ghcr.io/sigbit/mcp-auth-proxy:v2.10.2"`; `command == [<backend>]`; `ports == ["${AI_DESKTOP_VM_IP}:<porta>:80"]`; env `EXTERNAL_URL == "https://<sub>.${BASE_DOMAIN_FROM_VAULT}"`, `NO_AUTO_TLS == "true"`, `LISTEN == ":80"`, `DATA_PATH == "/data"`, `OIDC_CONFIGURATION_URL == "https://auth.${BASE_DOMAIN_FROM_VAULT}/.well-known/openid-configuration"`, `OIDC_CLIENT_ID == "mcp"`, `OIDC_CLIENT_SECRET == "${MCP_OIDC_CLIENT_SECRET}"`, `OIDC_SCOPES == "openid,profile,email,groups"`, `OIDC_ALLOWED_ATTRIBUTES == "/groups=admins"`, `AUTH_HMAC_SECRET == "${MCP_AUTH_HMAC_SECRET}"`, `TRUSTED_PROXIES` == IP da `core-services-vm` por variável; nenhum `PASSWORD`.
  - `test_cliente_oidc_mcp`: cliente `mcp` com os valores da Global Constraints (`require_pkce is False`, sem `pkce_challenge_method`); `test_authelia_validate_config` segue passando com quatro clientes.
  - `test_bypass_notas_e_escrita`: como `test_bypass_dos_publicos`, para `notas` e `escrita`.
  - `test_rotas_notes`: render do `dynamic_rag_services.yml.j2`: routers com ``Host(`notas.exemplo.com`)``/``escrita``/``sync``; os dois primeiros sem `middlewares` do Authelia, `sync` com `authelia-forwardauth@docker`; serviços apontando para `http://192.168.15.68:8481`, `:8482`, `:8384`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS (com `PATH` incluindo o binário do Authelia).
- [ ] **Step 5: Commit** `feat(notas,autenticacao): conectores MCP com OAuth pelo Authelia`

### Task 7: Timers, coletor systemd e alerta

**Files:**
- Create: `server/ansible/templates/notes/notes-documentos.service.j2`, `notes-documentos.timer.j2`, `notes-indice.service.j2`, `notes-indice.timer.j2` (literais na página 12)
- Modify: playbook (instala as units em `/etc/systemd/system`, `daemon_reload`, timers `enabled` mas **não** `started` antes do deploy — corrige o problema da 4a — com a página mandando `systemctl start` depois do deploy)
- Modify: `roles/infra/alloy/templates/config.alloy.j2` (`enable_collectors = ["systemd"]`, `systemd { unit_include = "notes-.+\\.service" }`)
- Modify: `grafana/alerting/rules.yml.j2` (regra `notes-timer-falhou`)
- Test: `tools/wikisync/tests/test_segundo_cerebro.py`

**Interfaces:**
- Consumes: Task 2 (imagem do conversor, CLI), Task 3 (container `qmd`).

- [ ] **Step 1: Write the failing tests**
  - `test_units_notes`: `notes-documentos.service` (`Type=oneshot`) com `ExecStart` contendo `flock -n /run/notes-documentos.lock`, `docker run --rm`, `-v {{ vm_nfs_mount_base_path }}/{{ zfs_files_dataset_name }}/{{ notes_nextcloud_usuario }}/files:/origem:ro`, `-v {{ vm_local_data_path }}/notes-documentos:/destino`, `--user {{ docker_puid }}:{{ docker_pgid }}`, a imagem `localhost/homeserver/notes-conversor:{{ markitdown_version }}`, `--extensoes` de `notes_documentos_extensoes | join(',')` e `--max-mb {{ notes_documentos_max_mb }}`; `notes-indice.service` com `flock -n /run/notes-indice.lock` e `docker exec qmd sh -c 'qmd update && qmd embed'`, `After=notes-documentos.service`; timers com `OnCalendar=*:0/10` e `*:5/10`, `Persistent=false`.
  - `test_coletor_systemd_e_alerta`: `config.alloy.j2` com `enable_collectors = ["systemd"]` e `unit_include` `notes-`; regra `notes-timer-falhou` com `node_systemd_unit_state{name=~"notes-.*", state="failed"}`, `op: gt`, `v: 0`, `sev: warning`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(notas): conversão e indexação periódicas com alerta de falha`

### Task 8: Open WebUI com os dois MCPs

**Files:**
- Modify: `server/docker/stacks/ai/docker-compose.yml` (`open-webui` na rede externa `notes_mcp`; env `TOOL_SERVER_CONNECTIONS`)
- Modify: página 08 (seção nova "Ferramentas: notas") e página 12 (ordem de deploy: `notes` antes de redeployar `ai`)
- Test: `tools/wikisync/tests/test_segundo_cerebro.py`

- [ ] **Step 1: Write the failing test**
  - `test_openwebui_usa_os_mcps`: `open-webui.networks` inclui `notes_mcp`; a rede `notes_mcp` no compose `ai` é `external: true`; `json.loads(TOOL_SERVER_CONNECTIONS)` == lista de dois itens com `type == "mcp"`, `url` `http://qmd:8181/mcp` e `http://notes_escrita:8000/mcp`, `auth_type == "none"`, `config == {"enable": True}` (sem `access_grants` → só admins), `info.id` `notas` e `escrita`, `info.name` `Notas (busca)` e `Notas (escrita)`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS (e os testes da 4a sobre o compose `ai`).
- [ ] **Step 5: Commit** `feat(ia,notas): Open WebUI com as ferramentas de notas`

### Task 9: Sondas, painel, catálogo, índice e páginas

**Files:**
- Modify: `prometheus.yml.j2` (blackbox: `http://{{ ai_desktop_vm_ip_var }}:8481/.well-known/oauth-protected-resource` com `app: notas`, `:8482/...` com `app: notas-escrita`, `:8384/rest/noauth/health` com `app: syncthing`)
- Modify: `homepage/services.yaml.j2` (`syncthing` → `sync.`, `notas` → `notas.`; `siteMonitor` pela LAN, PNL-1)
- Modify: catálogo `09-catalogo-aplicacoes.md` (linhas `syncthing` — protegida, `sync`, nfs; `notas` — `mcp_auth_busca`, `qmd`, publica, `notas`, local; `notas-escrita` — `mcp_auth_escrita`, `notes_escrita`, publica, `escrita`, nfs); índice `10-indice-integracoes.md` (provedor `mcp` com **MCP-1** e **MCP-2** da spec; DAD-5 citando os dados regeráveis); `INDEX.md`; `mkdocs.yml` (nav da página 12)
- Create/Modify: página `01-manual-implementacao/12-segundo-cerebro.md` (conteúdo da seção 7 da spec, incluindo pareamento, `.stignore` com `.obsidian/workspace*.json`, endereço estático `tcp://<ip da VM>:22000`, conectores no claude.ai e `claude mcp add --transport http`, como desfazer por snapshot); edições em 00, 01, 02, 04, 05, 08, 09, backup, `03-armazenamento-zfs-nfs.md`, `07-apis-llm-estrategia.md`
- Test: `tools/wikisync/tests/test_segundo_cerebro.py`

- [ ] **Step 1: Write the failing tests**
  - `test_sondas_e_painel_notes`: os três alvos com os `app` acima no `blackbox_http`; Homepage com `syncthing` e `notas`.
  - `test_catalogo_notes`: linhas `syncthing`, `notas`, `notas-escrita` no catálogo com Exposição e Subdomínio acima.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; skills `update-index` e `audit-integrations` (sem ❌/⚠️); `check` → `sync --yes`.
- [ ] **Step 4: Run** `dev.py test`, `check` (só `REF-PENDING`), `lint`, build estrito no clone → tudo passa.
- [ ] **Step 5: Commit** `docs(notas): página 12, catálogo, índice e sondas do segundo cérebro`

### Task 10: Revisão final e registro

- [ ] **Step 1:** Revisor único (modelo mais capaz disponível) sobre `git diff <commit da spec>..HEAD` contra a spec; corrigir achados críticos e importantes com teste primeiro; registrar menores adiados no ledger.
- [ ] **Step 2:** `dev.py test`, `check`, `lint`, build estrito → passam.
- [ ] **Step 3:** Atualizar `claude/contexto-homeserver.md` no Project (4b concluída, pendências, ordem de deploy).
- [ ] **Step 4: Commit** das correções `fix(notas): correções da revisão final`.
