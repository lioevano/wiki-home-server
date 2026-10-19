# Design: fotos e arquivos (Immich, Nextcloud reformulado e SSO OIDC pelo Authelia)

- **Data:** 2026-10-19
- **Autor:** Léo Ivan (com Claude)
- **Status:** aguardando revisão
- **Caminho:** arquitetural — sub-projeto **3** da refatoração do server (1 Alloy ✓, 2 mídia ✓, 3 fotos e arquivos, 4 IA). A VPN (Tailscale) virou sub-projeto próprio.
- **Depende de:** catálogo e índice (`2026-10-12`), painel e notificações (`2026-10-14`), coleta com Alloy (`2026-10-18`), mídia completa (`2026-10-19`).

## 1. Objetivo

Substituir Google Fotos e Google Drive para um único usuário (o Léo; celular Android, PC Linux/macOS):

- **Fotos (Immich):** backup automático do celular, linha do tempo, rostos, busca e links de compartilhamento.
- **Arquivos (Nextcloud):** sincronizar pastas do PC, acessar pelo app, compartilhar por link, calendário e contatos (CalDAV/CardDAV) e edição de documentos no navegador (Collabora).
- **Login único:** Authelia vira provedor OIDC; Immich e Nextcloud entram com a conta e o 2FA do Authelia, inclusive nos apps de celular.

### Critérios de pronto

- Stack nova `photos` (`docker/stacks/photos/docker-compose.yml`) com Immich; stack nova `cloud` (`docker/stacks/cloud/docker-compose.yml`) com Nextcloud, cron, Redis, Postgres e Collabora; nenhum serviço do Nextcloud na stack `apps`.
- Datasets `photos` e `files` com cota, exportados por NFS e montados na `core-services-vm`.
- Bancos de dados do Immich e do Nextcloud no disco local da VM, com dumps diários no NFS.
- Authelia com `identity_providers.oidc` e os clientes `immich` e `nextcloud` (`two_factor`, PKCE S256); `authelia validate-config` passa na configuração renderizada.
- Catálogo e índice atualizados; `audit-integrations` sem ❌/⚠️ (só `✋` de passos manuais documentados).
- Página nova `01-manual-implementacao/11-fotos-arquivos.md` com deploy, primeiro acesso, clientes, manutenção e teste de ponta a ponta.
- `dev.py test`, `check` (só `REF-PENDING` do vault), `build` (sem WARNING nem INFO de âncora) e `lint` passam.

## 2. Decisões

| # | Decisão | Escolha |
|---|---|---|
| F1 | Fotos | **Immich**, servidor + aprendizado de máquina **na CPU** da `core-services-vm`. GPU (ROCm na RX 5600 XT, gfx1010 sem suporte oficial) fica para o sub-projeto 4. |
| F2 | Arquivos | **Nextcloud continua**, só para arquivos, calendário, contatos e documentos; app `photos` desligado. Edição com **Collabora CODE** (Nextcloud Office). |
| F3 | Stacks | Duas stacks próprias: `photos` e `cloud` (Nextcloud sai da `apps`). Ciclos de atualização independentes; cada uma com seu playbook e seu `.env` (0600) carregado direto no Portainer, como a `media`. |
| F4 | Login | SSO **OIDC pelo Authelia** (4.38.0, a versão fixada; atualizar o Authelia fica fora de escopo). Immich e Nextcloud saem do forward-auth (bypass), e o login de cada app redireciona para o Authelia. Contas locais de emergência mantidas. |
| F5 | Acesso externo | Público pelo **Cloudflare Tunnel**: `fotos.`, `nextcloud.`, `office.`. Limite de 100 MB por requisição contornado com chunks de 50 MB (Nextcloud) e envio de vídeos grandes do Immich em casa (troca automática de URL) — depois também pela VPN. |
| F6 | Bancos | Postgres do Immich (exigência do Immich: "never a network share") e do Nextcloud no **disco local** em `/opt/local-data/<app>-db`; backup por dumps no NFS. |
| F7 | Espaço | Datasets `photos` e `files` com `quota` ZFS (variáveis com padrão; ajustáveis). Ao chegar disco novo: `zfs send/recv` para o pool novo com `mountpoint=/data/<dataset>` — caminhos inalterados. |
| F8 | Config do Immich | `IMMICH_CONFIG_FILE` gerado pelo Ansible (base fixa + `immich_config_overrides` mesclado em profundidade). A tela Administração › Configurações fica só leitura (aceito). |
| F9 | Config do Nextcloud | Script `before-starting` nos hooks da imagem oficial, idempotente, sem segredos no arquivo (segredos por variável de ambiente). Sem `occ` manual, exceto promover o usuário OIDC a admin uma vez. |
| F10 | Fora de escopo | VPN Tailscale (sub-projeto próprio), GPU para o Immich (sub-projeto 4), mover os bancos do Grafana/Authelia para disco local, atualizar Authelia/Traefik. |

## 3. Serviços

### Stack `photos` (core-services-vm)

| Serviço | Imagem | Rede | Dados |
|---|---|---|---|
| `immich_server` | `ghcr.io/immich-app/immich-server:${IMMICH_VERSION}` | `proxy`, `internal_services` | `/data` ← dataset `photos` (NFS); `immich.json` (ro) ← `docker-volumes/immich/config` |
| `immich_ml` | `ghcr.io/immich-app/immich-machine-learning:${IMMICH_VERSION}` | `internal_services` | cache de modelos ← `/opt/local-data/immich-model-cache` |
| `immich_redis` | Valkey (tag do compose oficial da versão fixada) | `internal_services` | — |
| `immich_db` | Postgres com extensão vetorial do compose oficial da versão fixada | `internal_services` | `/opt/local-data/immich-db` |

- Versões e imagens de `immich_redis`/`immich_db` copiadas do `docker-compose.yml` oficial da release fixada em `IMMICH_VERSION` (definida no plano).
- `immich_server` publica `${CORE_SERVICES_VM_IP_VAR}:2283:2283` (só LAN, para a troca automática de URL do app em casa) e tem rota no Traefik `fotos.<domínio>`.

### Stack `cloud` (core-services-vm)

| Serviço | Imagem | Rede | Dados |
|---|---|---|---|
| `nextcloud_app` | `nextcloud:${NEXTCLOUD_MAJOR}-apache` | `proxy`, `internal_services` | html e config ← `docker-volumes/nextcloud/{html,config}`; `data` ← dataset `files`; hook ← `docker-volumes/nextcloud/hooks` (ro) |
| `nextcloud_cron` | mesma imagem, `entrypoint: /cron.sh` | `internal_services` | mesmos volumes do app |
| `nextcloud_redis` | `redis:7-alpine` | `internal_services` | — |
| `nextcloud_db` | `postgres:15-alpine` (mantém a versão atual) | `internal_services` | `/opt/local-data/nextcloud-db` |
| `collabora` | `collabora/code` | `proxy`, `internal_services` | — |

- `nextcloud_app`: `TRUSTED_PROXIES` (redes Docker), `OVERWRITEPROTOCOL=https`, `OVERWRITECLIURL=https://nextcloud.<domínio>`, `REDIS_HOST`, `NEXTCLOUD_ADMIN_USER=ncadmin` + senha do vault, `NEXTCLOUD_TRUSTED_DOMAINS`; middlewares `nextcloud-headers@file` (sem `authelia-forwardauth`).
- `collabora`: `aliasgroup1=https://nextcloud\.<domínio>:443`, `server_name=office.<domínio>`, `extra_params=--o:ssl.enable=false --o:ssl.termination=true`, `dictionaries=pt_BR en_US`; `extra_hosts: nextcloud.<domínio>:${CORE_SERVICES_VM_IP_VAR}` (WOPI pela LAN via Traefik, sem passar pela Cloudflare).

### Hook do Nextcloud (`before-starting/10-homeserver.sh`)

Gerado pelo Ansible, executável, idempotente (cada passo checa antes de aplicar). Aplica:

1. `app:install`/`app:enable` de `user_oidc`, `richdocuments`, `calendar`, `contacts`; `app:disable photos`.
2. Provedor OIDC `Authelia` (`user_oidc:provider`), discovery `https://auth.<domínio>/.well-known/openid-configuration`, client `nextcloud`, segredo de `$NEXTCLOUD_OIDC_CLIENT_SECRET` (env), uid mapeado para `preferred_username` sem hash; `user_oidc` com `default_token_endpoint_auth_method=client_secret_post` e `allow_multiple_user_backends=0` (login direto no Authelia; `ncadmin` por `/login?direct=1`).
3. `richdocuments`: `wopi_url=http://collabora:9980`, `public_wopi_url=https://office.<domínio>`, `wopi_allowlist` = redes Docker.
4. `files max_chunk_size` = 50 MiB; `default_phone_region=BR`; `maintenance_window_start` de madrugada.

## 4. Dados

- **Host Proxmox (página 02):** `zfs create -o quota=<zfs_photos_quota> data/photos` e `zfs create -o quota=<zfs_files_quota> data/files`; exports NFS iguais aos demais (`all_squash`, `anonuid/anongid` do dockeruser); montagem na `core-services-vm` pelo role `common`.
- **Immich (`/data` = dataset `photos`):** uploads, miniaturas, vídeos convertidos e `backups/` (dumps do banco, 14 últimos, diários às 02:00); *storage template* `{{y}}/{{y}}-{{MM}}-{{dd}}/{{filename}}`.
- **Nextcloud:** `data` = dataset `files`; dump diário (`pg_dump`, timer systemd instalado pelo playbook) em `backups/nextcloud/` com retenção.
- **Disco local da VM (`/opt/local-data`):** `immich-db`, `immich-model-cache`, `nextcloud-db` — criados pelos playbooks; fora do ZFS, cobertos só pelos dumps.

## 5. Variáveis e segredos

**`group_vars/all/main.yml`:** `zfs_photos_dataset_name`, `zfs_files_dataset_name`, `zfs_photos_quota`, `zfs_files_quota`, `vm_local_data_path`, `immich_version`, `nextcloud_major`, `immich_password_login` (padrão `true`), `immich_config_overrides` (padrão `{}`), subdomínios `immich_subdomain: fotos`, `collabora_subdomain: office`.

**Vault (`vault.yml.example` e página 01):**

| Chave | Uso |
|---|---|
| `authelia_oidc_hmac_secret` | `identity_providers.oidc.hmac_secret` |
| `authelia_oidc_jwks_key` | chave privada RSA 2048 (PEM) para `jwks` (RS256) |
| `oidc_clients.immich.secret` / `.secret_digest` | segredo em claro (Immich) / digest pbkdf2-sha512 (Authelia) |
| `oidc_clients.nextcloud.secret` / `.secret_digest` | idem para o Nextcloud |
| `immich_db_password` | Postgres do Immich |
| `nextcloud_db_password`, `nextcloud_admin_initial_password` | já existem |
| `homepage_widget_keys.immich` | chave de API do widget |

Segredos alfanuméricos (o `user_oidc` não codifica bem outros caracteres). Digests gerados com `authelia crypto hash generate pbkdf2 --variant sha512` rodando a imagem fixada.

**`.env` das stacks:** `photos.env` (`setup-photos-stack-volumes.yml`) e `cloud.env` (`setup-cloud-stack-volumes.yml`), 0600, via `portainer_stack_env.j2`; `cloud.env` inclui `NEXTCLOUD_OIDC_CLIENT_SECRET`. O `productivity.env` perde as variáveis do Nextcloud.

**`immich.json`:** base fixa — `oauth` (enabled, issuer `https://auth.<domínio>`, client `immich`, `client_secret_basic`, `autoLaunch: true`, `autoRegister: false`, botão "Entrar com Authelia"), `passwordLogin.enabled: {{ immich_password_login }}`, `server.externalDomain`, `storageTemplate`, `backup.database` — mesclada com `immich_config_overrides` (`combine(recursive=True)`). Arquivo 0600.

## 6. Integrações

| Integração | Mudança |
|---|---|
| Authelia | `identity_providers.oidc` (seção 2, F4) com clientes `immich` (redirects `/auth/login`, `/user-settings`, `app.immich:///oauth-callback`; `client_secret_basic`) e `nextcloud` (redirect `/apps/user_oidc/code`; `client_secret_post`; escopo extra `groups`). Regras `bypass` uma por domínio: `fotos.`, `nextcloud.`, `office.`. |
| Traefik | Rotas `fotos.`, `nextcloud.`, `office.`; `nextcloud-headers` ganha os redirecionamentos `/.well-known/caldav` e `/.well-known/carddav` → `/remote.php/dav/`. |
| Cloudflare | Os três subdomínios pelo túnel (confirmar no plano se o curinga atual cobre). |
| Blackbox | Sondas `fotos` (`/api/server/ping`), `nextcloud` (`/status.php`), `office` (`/hosting/discovery`); alerta `servico-fora-do-ar` existente. |
| Alertas | Nenhum novo: `disco-cheio` cobre as cotas (dataset com cota aparece com o tamanho da cota). |
| Homepage | Widget `immich` (chave em `homepage_widget_keys.immich`) e `nextcloud` (existente), no grupo de fotos e arquivos. |
| Logs/métricas | Já cobertos pelo Alloy (todos os containers). |
| Backup | Página de backup: datasets `photos` e `files`, dumps do Immich, `backups/nextcloud`, aviso de que os bancos locais dependem dos dumps. |
| Catálogo/índice | Apps novos (`immich`, `immich_ml`, `immich_redis`, `immich_db`, `collabora`, `nextcloud_cron`); Nextcloud muda de stack e de `protegida` para `publica`; regras do índice estendidas conforme o `update-index`. |

## 7. Páginas

- **Nova `11-fotos-arquivos.md`:**
  - visão geral;
  - datasets;
  - variáveis e segredos (com a geração dos digests);
  - deploy das duas stacks;
  - primeiro acesso:
    - Immich: criar o admin logo após o deploy, com o e-mail da conta do Authelia → entrar com Authelia (vínculo por e-mail) → `immich_password_login: false` + playbook + restart;
    - Nextcloud: login pelo Authelia → `occ group:adduser admin <usuário>`;
  - clientes:
    - app do Immich com troca automática de URL pelo Wi-Fi de casa;
    - Nextcloud desktop com `maxChunkSize=50000000`;
    - Nextcloud Android;
    - DAVx⁵;
  - mudando a configuração do Immich (`immich_config_overrides`);
  - subindo a versão principal do Nextcloud (uma de cada vez);
  - recuperação se o Authelia falhar;
  - tabela de falhas;
  - teste de ponta a ponta.
- **Editadas:**
  - 00 (`.env.template`);
  - 01 (vault);
  - 02 (datasets, cotas, migração para discos novos);
  - 05 (Authelia OIDC, regras, middleware);
  - 06 (segurança: apps públicos com OIDC);
  - 07 (Nextcloud sai, aponta para a 11);
  - 09 (sondas e widgets);
  - backup (04-02);
  - catálogo, índice, `mkdocs.yml` (nav), `INDEX.md`.

## 8. Falhas

| Falha | Comportamento | Recuperação documentada |
|---|---|---|
| Authelia fora | Login novo nos dois apps falha; sessões dos apps continuam | Immich: `immich_password_login: true` + playbook + restart; Nextcloud: `ncadmin` por `/login?direct=1` |
| Upload > 100 MB pelo túnel | Cloudflare recusa (413) | Chunks de 50 MB no Nextcloud; Immich envia vídeos grandes em casa (URL local) |
| Assistente público do Immich antes do admin | Qualquer um poderia criar o admin | Criar o admin logo após o deploy (mesmo cuidado da página 10) |
| Collabora não abre documentos | WOPI recusado | Conferir `wopi_allowlist`, `aliasgroup1` e `extra_hosts` (tabela da página 11) |
| Cota cheia | Uploads falham; alerta `disco-cheio` | Aumentar `quota` ou migrar para disco novo |
| Disco local da VM perdido | Bancos perdidos | Restaurar dos dumps (Immich: procedimento de restauração da documentação oficial, conferido no plano; Nextcloud: restauração do `pg_dump`) |

## 9. Verificação

- Novo `tools/wikisync/tests/test_fotos_arquivos.py` (padrão de `test_midia.py`):
  - **Composes:**
    - bancos em `/opt/local-data`, nunca no NFS;
    - toda variável dos composes existe no `.env` da stack;
    - `nextcloud_cron` com a mesma imagem e os mesmos volumes do app;
    - `collabora` com `extra_hosts` para `nextcloud.`;
    - porta 2283 só no IP da LAN;
    - Nextcloud sem `authelia-forwardauth`.
  - **Modelos renderizados:**
    - `immich.json` válido, `autoRegister: false`, `immich_config_overrides` mesclado em profundidade sem perder a base;
    - hook sem segredos literais e com checagens idempotentes;
    - middlewares `.well-known`.
  - **Authelia:**
    - dois clientes `two_factor` + PKCE S256 com os redirects certos;
    - um `bypass` por domínio público;
    - `authelia validate-config` com o binário 4.38.0 (ignorado se ausente).
  - **Integrações:** sondas, widgets e catálogo.
- `dev.py check`, `sync`, `test`, `build`, `lint`; skills `update-index` e `audit-integrations`.

## 10. Fora de escopo

VPN Tailscale; GPU para o Immich; métricas Prometheus do Immich; bancos do Grafana/Authelia para disco local; atualização de Authelia/Traefik; migração de dados existentes (nada foi implantado ainda).

## 11. Riscos

- **Authelia 4.38 × guias testados em 4.39:** mitigado por `validate-config` no teste e pela leitura dos guias da 4.38 no plano.
- **Configuração por arquivo do Immich muda entre versões:** a base fixa só usa chaves estáveis; `IMMICH_VERSION` fixada e atualizada de propósito.
- **Comportamento do app Android do Nextcloud com arquivos > 100 MB pelo túnel:** a verificar no teste de ponta a ponta; se falhar, enviar em casa (e pela VPN no futuro).
- **Nextcloud html/config no NFS:** desempenho aceitável hoje; mover para disco local fica para depois, se necessário.
- **Hairpin do Collabora:** depende do Traefik publicar a 443 no IP da LAN (já publica).
