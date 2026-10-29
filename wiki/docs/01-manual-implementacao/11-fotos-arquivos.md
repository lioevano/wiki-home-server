---
description: "Stacks photos (Immich) e cloud (Nextcloud, cron e Collabora), públicas pelo túnel com login OIDC do Authelia, datasets com cota e bancos no disco local."
---

# Seção 11: Fotos e Arquivos (Immich, Nextcloud e Collabora)

O **Immich** substitui o Google Fotos: o app do celular envia cada foto e vídeo para o servidor, com linha do tempo, rostos, busca e links de compartilhamento. O **Nextcloud** substitui o Google Drive: sincroniza pastas do computador, guarda calendário e contatos e, com o **Collabora**, edita documentos no navegador. Os dois entram com a sua conta e o seu 2FA do **Authelia** (OIDC), inclusive nos apps.

```
internet ──► Cloudflare Tunnel ──► Traefik ──► fotos.      (Immich)      login: OIDC do Authelia
                                          ├──► nextcloud.  (Nextcloud)   login: OIDC do Authelia
                                          └──► office.     (Collabora)   token WOPI do Nextcloud
casa (Wi-Fi) ─────────────────────► http://<IP da core-services-vm>:2283 (Immich, sem o limite de 100 MB do túnel)
```

## Serviços

| Stack | Serviço | Para que serve | Endereço interno |
|---|---|---|---|
| `photos` | `immich_server` | Interface, API e app do celular | `http://immich_server:2283` |
| `photos` | `immich_ml` | Rostos, busca e duplicatas (CPU) | `http://immich_ml:3003` |
| `photos` | `immich_redis` / `immich_db` | Fila (Valkey) e banco (Postgres com extensão vetorial) | — |
| `cloud` | `nextcloud_app` | Arquivos, calendário e contatos | `http://nextcloud_app` |
| `cloud` | `nextcloud_cron` | Tarefas de fundo a cada 5 minutos | — |
| `cloud` | `nextcloud_redis` / `nextcloud_db` | Cache e banco (Postgres) | — |
| `cloud` | `collabora` | Edição de documentos (Nextcloud Office) | `http://collabora:9980` |

Os três endereços públicos ficam fora do forward-auth do Authelia (regras `bypass` na [seção 5](05-rede-segura.md)): os apps de celular e de desktop não passam por ele. O login de cada app vai direto para o Authelia, com `two_factor`, pelo provedor OIDC configurado no mesmo `configuration.yml`. Os dois clientes usam a política `familia`: só quem está no grupo `users` do Authelia entra (e só então o Nextcloud cria a conta). Quem já entrou no Authelia em outro subdomínio não precisa entrar de novo. A conversa do servidor com o Authelia (descoberta e troca do código) vai pela LAN: `immich_server` e `nextcloud_app` resolvem `auth.<domínio>` para o Traefik na `core-services-vm` (`extra_hosts`), então o login funciona mesmo com a internet fora (o navegador ou o app ainda precisam alcançar `auth.`).

## Dados

| O quê | Onde | Backup |
|---|---|---|
| Fotos, vídeos, miniaturas e dumps do banco do Immich | dataset `photos` (NFS), em `/data` do `immich_server` | restic (disco externo e nuvem; [backup](../04-manutencao-recuperacao/02-backup-restore-estrategia.md)) |
| Arquivos do Nextcloud | dataset `files` (NFS), em `/data` do `nextcloud_app` | restic (disco externo e nuvem; [backup](../04-manutencao-recuperacao/02-backup-restore-estrategia.md)) |
| Hook do Nextcloud | `docker-volumes` (NFS) | restic (disco externo e nuvem; [backup](../04-manutencao-recuperacao/02-backup-restore-estrategia.md)) |
| `immich.json` (contém o segredo do cliente OIDC) | disco local da VM, em `/opt/local-data/immich-config` (`0600`) | regerado pelo `setup-photos-stack-volumes.yml` a partir do vault |
| Bancos (`immich_db`, `nextcloud_db`), html e config do Nextcloud, cache de modelos | disco local da VM, em `/opt/local-data` | **só os dumps** (abaixo); o html sai da imagem e o cache é baixado de novo |

!!! warning "Bancos fora dos snapshots ZFS"
    O Immich exige o banco em disco local ("never a network share"), e o do Nextcloud foi junto. O html e o config do Nextcloud também ficam no disco local: o `occ` e o cron só rodam como o dono do `config.php`, e o entrypoint entrega os arquivos ao `www-data` com `chown`, o que o NFS com `all_squash` não permite. Esses diretórios ficam fora dos snapshots ZFS: o backup deles são os **dumps diários** no NFS:

    * **Immich:** o próprio Immich grava um dump por dia às 02:00 em `photos/backups/` e guarda os 14 últimos.
    * **Nextcloud:** o timer `backup-nextcloud-db.timer` roda `/usr/local/sbin/backup-nextcloud-db.sh` às 03:30 e grava `nextcloud-<data>.dump` (banco) e `nextcloud-config-<data>.tar.gz` (o `config/`, com `instanceid`, `secret` e `passwordsalt`) em `docker-volumes/nextcloud/db-dumps/`, guardando duas semanas. Se o dump falhar, o alerta `timer-falhou` avisa ([seção 9](09-painel-notificacoes.md)).

    Os dois estão na [estratégia de backup](../04-manutencao-recuperacao/02-backup-restore-estrategia.md).

Os datasets `photos` e `files` são criados com cota na [seção 2](02-proxmox-ve-host.md); com cota, o alerta `disco-cheio` avisa quando um deles está quase cheio. Para mudar: `zfs set quota=<tamanho> data/photos`.

## Deploy

1. **Vault** (`ansible-vault edit inventories/home/group_vars/all/vault.yml`, a partir de `server/ansible`; modelo e comandos de geração no [`vault.yml.example`](01-maquina-controle-ansible.md)):
    * `authelia_oidc_hmac_secret` (`openssl rand -hex 32`) e `authelia_oidc_jwks_key` (`openssl genrsa 2048`);
    * `oidc_clients.immich` e `oidc_clients.nextcloud`: `secret` (`openssl rand -hex 32`) e `secret_digest`, gerado com `docker run --rm authelia/authelia:4.39.28 authelia crypto hash generate pbkdf2 --variant sha512 --password <secret>` (o valor depois de `Digest: `);
    * `immich_db_password`; `nextcloud_db_password` e `nextcloud_admin_initial_password` (já existiam).
2. **Authelia:** rode o `setup-core-networking.yml` (gera o `configuration.yml` com o provedor OIDC e as regras) e reinicie o container: `docker restart authelia`. Confira no log que não há erro de configuração (`docker logs authelia | grep -i error`).
3. **Volumes e `.env`** (cada um primeiro com `--check`):
   ```bash
   ansible-playbook -i inventories/home/hosts.ini playbooks/setup-photos-stack-volumes.yml --ask-vault-pass --check
   ansible-playbook -i inventories/home/hosts.ini playbooks/setup-photos-stack-volumes.yml --ask-vault-pass
   ansible-playbook -i inventories/home/hosts.ini playbooks/setup-cloud-stack-volumes.yml --ask-vault-pass --check
   ansible-playbook -i inventories/home/hosts.ini playbooks/setup-cloud-stack-volumes.yml --ask-vault-pass
   ```
    * `ansible/playbooks/setup-photos-stack-volumes.yml` cria os diretórios, gera o `immich.json` a partir de `ansible/templates/immich/immich.json.j2` (`0600`, contém o segredo do cliente OIDC) e o `/opt/portainer_stack_envs/photos.env` (`0600`).
    * `ansible/playbooks/setup-cloud-stack-volumes.yml` cria os diretórios (banco, html e config no disco local), deixa a raiz do dataset `files` em `0770`, grava o hook `ansible/templates/nextcloud/10-homeserver.sh.j2`, instala o dump diário (`ansible/templates/backup-postgres.sh.j2` e o timer systemd) e gera o `/opt/portainer_stack_envs/cloud.env` (`0600`).
4. **Portainer → Stacks → Add Stack**, uma de cada vez: `photos` com `docker/stacks/photos/docker-compose.yml` e o `photos.env`; `cloud` com `docker/stacks/cloud/docker-compose.yml` e o `cloud.env` → **Deploy the stack**. Se a stack `apps` ainda tiver o Nextcloud antigo, atualize-a antes (**Update the stack** com o compose atual).

### Variáveis das stacks

| Variável | Origem |
|---|---|
| `IMMICH_VERSION` | `immich_version` (`group_vars/all/main.yml`) |
| `PHOTOS_STACK_UPLOAD_PATH` | NFS + `zfs_photos_dataset_name` |
| `PHOTOS_STACK_CONFIG_PATH` | `/opt/local-data/immich-config` (disco local: o arquivo tem um segredo) |
| `PHOTOS_STACK_DB_PATH`, `PHOTOS_STACK_MODEL_CACHE_PATH` | `vm_local_data_path` + `immich-db` / `immich-model-cache` |
| `IMMICH_DB_PASSWORD` | vault `immich_db_password` |
| `NEXTCLOUD_MAJOR` | `nextcloud_major` (`group_vars/all/main.yml`) |
| `CLOUD_STACK_NEXTCLOUD_HTML_PATH`, `CLOUD_STACK_NEXTCLOUD_CONFIG_PATH` | `vm_local_data_path` + `nextcloud/html` / `nextcloud/config` |
| `CLOUD_STACK_NEXTCLOUD_HOOKS_PATH` | NFS + `docker-volumes/nextcloud/hooks` |
| `CLOUD_STACK_NEXTCLOUD_DATA_PATH` | NFS + `zfs_files_dataset_name` (montado em `/data`, `NEXTCLOUD_DATA_DIR`; o playbook deixa a raiz em `0770`, que o Nextcloud exige) |
| `CLOUD_STACK_NEXTCLOUD_DB_PATH` | `vm_local_data_path` + `nextcloud-db` |
| `NEXTCLOUD_DB_PASSWORD_FROM_PORTAINER_ENV`, `NEXTCLOUD_ADMIN_PASSWORD_FROM_PORTAINER_ENV` | vault `nextcloud_db_password`, `nextcloud_admin_initial_password` |
| `NEXTCLOUD_OIDC_CLIENT_SECRET` | vault `oidc_clients.nextcloud.secret` (lido pelo hook, nunca gravado em arquivo) |
| `CORE_SERVICES_VM_IP_VAR` | `core_services_vm_ip_var` do `hosts.ini` (porta 2283 na LAN e `extra_hosts` do Collabora) |

## Primeiro acesso

!!! warning "Immich primeiro"
    O `fotos.` é público desde o **Deploy the stack**, e o assistente do Immich cria o administrador para quem chegar primeiro. Faça o passo 1 logo depois do deploy. O Nextcloud não tem esse risco: ele se instala sozinho com a conta `ncadmin` e a senha do vault.

1. **Immich** (`fotos.seudominio.com`): no assistente, crie o administrador com **o mesmo e-mail da sua conta no Authelia**. Saia e entre de novo por **Entrar com Authelia**: o Immich vincula a conta pelo e-mail. Depois, desligue o login por senha (`immich_password_login: false` no `group_vars/all/main.yml`, pela wiki), rode o `setup-photos-stack-volumes.yml` e `docker restart immich_server`. Contas novas não são criadas pelo Authelia (`autoRegister` desligado).
2. **Nextcloud** (`nextcloud.seudominio.com`): o hook já instalou `user_oidc`, `richdocuments`, `calendar` e `contacts`, desligou `photos` e configurou o Authelia e o Collabora (confira em `docker logs nextcloud_app | grep homeserver-hook`: nenhum aviso). Entre pelo Authelia e torne a sua conta administradora, uma vez:
   ```bash
   docker exec -u www-data nextcloud_app php occ group:adduser admin <seu usuário do Authelia>
   ```
   A conta `ncadmin` fica para emergência, por `https://nextcloud.seudominio.com/login?direct=1`.
3. **Homepage:** no Immich, *Conta → Configurações da conta → Chaves de API*, crie uma chave com a permissão `server.statistics` e grave-a em `homepage_widget_keys.immich`; a do Nextcloud segue a [seção 9](09-painel-notificacoes.md). Rode o `setup-monitoring-stack-volumes.yml`.

## Clientes

* **Immich (Android):** servidor `https://fotos.seudominio.com`, **Entrar com Authelia**. Em *Configurações → Rede*, ligue a **troca automática de URL**: o Wi-Fi de casa usa `http://<IP da core-services-vm>:2283`, e fora dele o app usa `https://fotos.seudominio.com`. Ative o backup das pastas da câmera. O túnel da Cloudflare recusa requisições acima de 100 MB, então vídeos maiores só sobem em casa (o app tenta de novo sozinho); deixe desligado o uso de dados móveis para vídeos. Com o **Tailscale** ligado no celular ([seção 14](14-vpn-tailscale.md)), `https://fotos.seudominio.com` vai direto ao Traefik de casa, sem esse limite, e a troca de URL vira opcional.
* **Nextcloud (desktop Linux/macOS):** servidor `https://nextcloud.seudominio.com`; o login abre o navegador, que passa pelo Authelia. Para os arquivos grandes passarem pelo túnel, feche o cliente e acrescente, na seção `[General]` de `~/.config/Nextcloud/nextcloud.cfg` (Linux) ou `~/Library/Preferences/Nextcloud/nextcloud.cfg` (macOS):
  ```ini
  maxChunkSize=50000000
  ```
  O envio pelo navegador já usa pedaços de 50 MiB (configurado pelo hook).
* **Nextcloud (Android):** mesmo endereço e login pelo navegador. Deixe o *upload automático* desligado: as fotos vão pelo Immich.
* **Calendário e contatos (DAVx⁵):** *Adicionar conta → Login com URL e nome de usuário* não funciona com OIDC; use **Login com Nextcloud** (Login Flow) e o endereço `https://nextcloud.seudominio.com`. A descoberta de CalDAV e CardDAV vem do middleware `nextcloud-dav` (`/.well-known/caldav` e `/.well-known/carddav`).
* **Documentos:** abra um `.docx`, `.xlsx` ou `.odt` no Nextcloud; o editor do Collabora abre na mesma aba.

## Mudando a configuração do Immich

A configuração do Immich vem do `immich.json` (`IMMICH_CONFIG_FILE`): a página *Administração → Configurações* fica **só leitura**. As preferências de usuário, álbuns, pessoas, links compartilhados, *Jobs* e a gestão de usuários continuam na interface.

Para mudar uma configuração, acrescente a chave em `immich_config_overrides` (`group_vars/all/main.yml`, pela wiki), que é mesclada por cima da base do `ansible/templates/immich/immich.json.j2`. Os nomes das chaves são os da [documentação do arquivo de configuração](https://docs.immich.app/install/config-file), e a tela só leitura mostra os valores em vigor.

```yaml title="Exemplo: immich_config_overrides"
immich_config_overrides:
  machineLearning:
    ocr: { enabled: false }
  backup:
    database: { cronExpression: "0 03 * * *" }
```

Depois: `setup-photos-stack-volumes.yml` e `docker restart immich_server` (o Immich só lê o arquivo ao iniciar).

## Atualizações

* **Immich:** leia as notas da release, troque `immich_version` e, se o `docker-compose.yml` oficial da versão nova mudar a imagem do Valkey ou do Postgres, copie as novas no `docker/stacks/photos/docker-compose.yml`. Rode o `setup-photos-stack-volumes.yml`, cole o `photos.env` atualizado ([como](07-deploy-apps.md#como-as-stacks-recebem-as-variáveis)) e **Update the stack** com **Re-pull image**.
* **Nextcloud:** suba **uma versão principal por vez** (o Nextcloud não pula versões): `nextcloud_major` de `34` para `35`, `setup-cloud-stack-volumes.yml`, cole o `cloud.env` atualizado e **Update the stack** com **Re-pull image**. Acompanhe `docker logs -f nextcloud_app` até o fim da atualização; os apps incompatíveis ficam desativados e voltam quando houver versão nova deles.

## Falhas

| Situação | Comportamento | O que fazer |
|---|---|---|
| Authelia fora do ar | Login novo falha nos dois apps; sessões abertas e apps já logados continuam | Immich: `immich_password_login: true`, playbook e `docker restart immich_server`; entre por `https://fotos.<domínio>/auth/login?autoLaunch=0` (sem isso, a tela pula direto para o Authelia). Nextcloud: `ncadmin` por `/login?direct=1` |
| Upload acima de 100 MB pelo túnel | A Cloudflare responde 413 | Nextcloud: pedaços de 50 MB (navegador e `maxChunkSize` no desktop). Immich: o vídeo sobe em casa, pela URL local |
| Collabora não abre o documento | O Nextcloud recusa as chamadas WOPI | Confira `wopi_allowlist` (redes Docker), `aliasgroup1` e o `extra_hosts` do `collabora`; `docker logs collabora` |
| Editor do Collabora em branco dentro do Nextcloud | O navegador recusou o iframe de `office.` | O Traefik aplica `X-Frame-Options: SAMEORIGIN` em tudo; o Collabora manda `Content-Security-Policy: frame-ancestors`, que os navegadores atuais respeitam no lugar dele. Se o console do navegador acusar `X-Frame-Options`, o middleware global não pode ser desligado só para um router: tire o `customFrameOptionsValue` do `securityHeaders` ([seção 5](05-rede-segura.md)) e confie no cabeçalho de cada aplicação (a conferir no primeiro deploy) |
| Aviso no log do hook (`homeserver-hook: aviso`) | O Nextcloud sobe com aquele passo pendente | Corrija a causa (ex.: loja de apps fora do ar) e `docker restart nextcloud_app` |
| Cota cheia | Uploads falham; alerta `disco-cheio` | `zfs set quota=<maior> data/photos` (ou `data/files`) ou mova o dataset para os discos novos ([seção 2](02-proxmox-ve-host.md)) |
| Disco local da VM perdido | Bancos perdidos; fotos e arquivos intactos no NFS | Immich: [restauração do backup](https://docs.immich.app/administration/backup-and-restore) a partir de `photos/backups/` (container `immich_db`, usuário `immich`). Nextcloud: abaixo |

**Restaurar o Nextcloud** (a partir dos arquivos mais recentes em `docker-volumes/nextcloud/db-dumps/`): pare `nextcloud_app` e `nextcloud_cron`; devolva o config com `sudo tar -xzf nextcloud-config-<data>.tar.gz -C /opt/local-data/nextcloud/config`; suba só o `nextcloud_db` (vazio) e rode `docker exec -i nextcloud_db pg_restore -U nextcloud -d nextcloud --clean --if-exists < nextcloud-<data>.dump`; depois suba o resto e rode `docker exec -u www-data nextcloud_app php occ maintenance:data-fingerprint`.

## Teste de ponta a ponta

1. **Login:** em uma aba anônima, `fotos.` e `nextcloud.` levam ao Authelia, pedem o 2FA e voltam logados.
2. **Calendário:** `curl -sI https://nextcloud.seudominio.com/.well-known/caldav` responde `301` para `/remote.php/dav/`; o DAVx⁵ sincroniza um evento criado no Nextcloud.
3. **Fotos:** tire uma foto no celular; ela aparece no Immich e no disco em `photos/library/.../<ano>/<ano-mês-dia>/`.
4. **Vídeo grande:** um vídeo acima de 100 MB sobe em casa (URL local) e fica pendente nos dados móveis.
5. **Arquivo grande:** um arquivo de 200 MB sincroniza pelo cliente desktop fora de casa (pedaços de 50 MB). Confira também um envio de mais de 100 MB pelo app Android do Nextcloud fora de casa; se falhar, envie em casa.
6. **Documento:** um `.docx` abre e salva no Collabora.
7. **Backups:** `sudo systemctl start backup-nextcloud-db.service` cria um `nextcloud-<data>.dump` e um `nextcloud-config-<data>.tar.gz` em `docker-volumes/nextcloud/db-dumps/`; no dia seguinte, há um dump do Immich em `photos/backups/`.
8. **Painel:** o widget do Immich mostra fotos e vídeos na Homepage, e as sondas `immich`, `nextcloud` e `collabora` aparecem como `up` no Prometheus.
