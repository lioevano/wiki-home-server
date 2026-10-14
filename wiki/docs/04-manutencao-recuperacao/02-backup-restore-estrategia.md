---
description: "Estratégia de backup 3-2-1 e procedimentos de restauração de VMs, volumes e configurações."
---

# Estratégia de Backup e Procedimentos de Restauração

Uma estratégia de backup abrangente, bem planejada e regularmente testada é a sua apólice de seguro mais valiosa contra a perda de dados. Falhas de hardware, corrupção de software, erros humanos, ou até mesmo eventos maliciosos como ransomware podem ocorrer, e ter backups confiáveis é o que determinará se você pode se recuperar completamente ou se enfrentará uma perda de dados catastrófica.

Este guia detalha o que fazer backup em nossa arquitetura de servidor doméstico, como implementar os backups para cada componente, e, crucialmente, os procedimentos para restaurar a partir desses backups.

## A Regra de Ouro dos Backups: 3-2-1

Lembre-se sempre da **regra 3-2-1** para backups, um princípio fundamental na proteção de dados:

*   **3 Cópias dos Dados:** Mantenha pelo menos **TRÊS** cópias de qualquer dado importante. Isso inclui o dado original (em produção) e pelo menos dois backups.
*   **2 Mídias Diferentes:** Armazene essas cópias em pelo menos **DOIS** tipos diferentes de mídia de armazenamento. Por exemplo:
    *   HD interno do servidor (para o original).
    *   HDs do pool ZFS `/data` (para backups locais de VMs, snapshots ZFS).
    *   Um HD externo USB.
    *   Armazenamento em nuvem.
    *   Outro servidor NAS na sua rede.
*   **1 Cópia Off-site:** Mantenha pelo menos **UMA** cópia do backup fisicamente separada do local original do seu servidor (e.g., na nuvem, na casa de um amigo ou familiar de confiança, em um cofre à prova de fogo em outro local). Isso protege contra desastres locais como incêndio, roubo ou inundação.

!!! critical "Backups Não Testados São Backups Que Podem Falhar!"
    Um backup só é útil se você sabe que pode restaurá-lo com sucesso. **TESTE SEUS PROCEDIMENTOS DE RESTAURAÇÃO REGULARMENTE!** Não espere um desastre real para descobrir que seus backups estão corrompidos ou que você não sabe como usá-los. Consulte a seção [Rotinas de Manutenção Essenciais](01-rotinas-manutencao.md#6-verificação-e-teste-de-backups) para dicas sobre testes.

## O Que Fazer Backup e Como Implementar

Vamos detalhar a estratégia de backup para cada componente crítico da nossa infraestrutura:

### 1. Configuração do Host Proxmox VE

Isto inclui as configurações do próprio hypervisor Proxmox VE, definições de rede do host, configurações ZFS, NFS, e outros arquivos de sistema importantes.

*   **O Que Fazer Backup (Arquivos e Diretórios Chave no Host Proxmox):**
    *   `/etc/pve/` (Contém a configuração do cluster Proxmox, definições de VMs, storage, etc. **MUITO IMPORTANTE!**)
    *   `/etc/hostname`
    *   `/etc/hosts`
    *   `/etc/network/interfaces` (Configuração de rede do host)
    *   `/etc/resolv.conf` (Se não for gerenciado dinamicamente)
    *   `/etc/default/grub` (Opções de boot do kernel, importantes para IOMMU)
    *   `/etc/kernel/cmdline` (Se usado para opções de kernel)
    *   `/etc/modules` e `/etc/modprobe.d/` (Módulos do kernel e blacklists, importantes para passthrough)
    *   `/etc/cron*` (Tarefas agendadas do host)
    *   `/etc/ssh/sshd_config` (Configuração do servidor SSH do host)
    *   `/etc/smartd.conf` (Configuração do monitoramento S.M.A.R.T. de discos)
    *   `/etc/zfs/` (Configuração do ZFS, embora os metadados do pool estejam nos discos)
    *   `/etc/exports` (Configuração do servidor NFS, gerada por Ansible)
    *   `/etc/systemd/system/ollama.service.d/override.conf` (Se você instalou Ollama diretamente no host e customizou o serviço)
    *   Quaisquer outros arquivos de configuração importantes que você tenha modificado manualmente no host.
*   **Como Fazer Backup (Script Agendado no Host Proxmox):**
    *   Use um script para arquivar esses arquivos e diretórios importantes em um arquivo `.tar.gz` e salvá-lo no seu dataset de backups ZFS (e.g., `/data/backups/proxmox_host_config/`).
    *   **Exemplo de Script (`/usr/local/sbin/backup_proxmox_host_config.sh` no host Proxmox):**
        ```bash
        #!/bin/bash
        # /usr/local/sbin/backup_proxmox_host_config.sh

        # Destino do backup (no pool ZFS /data/backups, que deve ser um dataset separado)
        # As variáveis {{ zfs_base_pool_path }} e {{ zfs_backups_dataset_name }} são do Ansible,
        # aqui usamos os valores literais ou definimos variáveis no script.
        ZFS_BASE_POOL_PATH="/data" # Ou o que você definiu
        ZFS_BACKUPS_DATASET_NAME="backups" # Ou o que você definiu
        BACKUP_DEST_PARENT="${ZFS_BASE_POOL_PATH}/${ZFS_BACKUPS_DATASET_NAME}"
        BACKUP_DEST="${BACKUP_DEST_PARENT}/proxmox_host_config"
        TIMESTAMP=$(date +%Y%m%d-%H%M%S)
        FILENAME="proxmox_etc_backup_${TIMESTAMP}.tar.gz"

        # Garante que o diretório de destino exista
        mkdir -p "$BACKUP_DEST"

        echo "Iniciando backup da configuração do host Proxmox para ${BACKUP_DEST}/${FILENAME}..."

        # Lista de arquivos e diretórios a serem backupeados
        # O -P no tar preserva os caminhos absolutos, mas ao restaurar é melhor
        # extrair para um local temporário e copiar seletivamente.
        # Usar --transform='s,^etc,etc_backup,' pode ser mais seguro para extração.
        # Para simplicidade aqui, vamos usar caminhos relativos a /etc ou absolutos com cuidado.
        # É mais seguro fazer backup de /etc e depois selecionar o que restaurar.
        # Ou listar explicitamente:
        PATHS_TO_BACKUP="
        /etc/pve
        /etc/hostname
        /etc/hosts
        /etc/network/interfaces
        /etc/resolv.conf
        /etc/default/grub
        /etc/kernel/cmdline
        /etc/modules
        /etc/modprobe.d
        /etc/cron.allow
        /etc/cron.deny
        /etc/cron.d
        /etc/cron.daily
        /etc/cron.hourly
        /etc/cron.monthly
        /etc/cron.weekly
        /etc/crontab
        /etc/issue
        /etc/issue.net
        /etc/ssh/sshd_config
        /etc/smartd.conf
        /etc/zfs
        /etc/exports
        /etc/systemd/system/ollama.service.d/override.conf
        "
        # Outros locais importantes podem incluir /root (para scripts), /usr/local/sbin (para scripts customizados)

        tar czfP ${BACKUP_DEST}/${FILENAME} ${PATHS_TO_BACKUP}
        # Alternativa mais segura para restauração: cd / && tar czf ${BACKUP_DEST}/${FILENAME} etc/pve etc/hostname ...

        if [ $? -eq 0 ]; then
          echo "Backup da configuração do host Proxmox concluído com sucesso: ${FILENAME}"
          # Opcional: Remover backups antigos deste tipo (e.g., manter os últimos 7)
          find "$BACKUP_DEST" -name "proxmox_etc_backup_*.tar.gz" -type f -mtime +7 -delete
        else
          echo "ERRO: Backup da configuração do host Proxmox falhou."
          # Adicione aqui uma notificação por email ou outro método, se desejar.
        fi
        ```
    *   **Agendamento:** Torne o script executável (`sudo chmod +x ...`) e agende-o com `cron` para rodar diariamente (e.g., `sudo crontab -e` e adicione `0 3 * * * /usr/local/sbin/backup_proxmox_host_config.sh`).
*   **Como Restaurar a Configuração do Host Proxmox:**
    1.  Este é um cenário de recuperação de desastre, geralmente após uma reinstalação limpa do Proxmox VE no mesmo hardware ou em um novo (consulte [Reconstruindo a Infraestrutura](04-reconstruindo-infraestrutura.md)).
    2.  Copie o arquivo `.tar.gz` de backup mais recente para o novo host Proxmox (e.g., para `/tmp`).
    3.  **Com MUITO CUIDADO**, extraia seletivamente os arquivos e diretórios necessários. **Não sobrescreva tudo cegamente**, especialmente se o hardware ou a versão do Proxmox mudaram.
        ```bash
        cd /tmp
        tar xzf proxmox_etc_backup_YYYYMMDD-HHMMSS.tar.gz
        # Agora você terá uma estrutura como etc/pve, etc/network, etc. em /tmp
        # Copie seletivamente para os locais corretos, e.g.:
        # sudo cp -ar /tmp/etc/pve/* /etc/pve/  (MUITO CUIDADO com este, pode ser melhor restaurar VMs de seus backups)
        # sudo cp /tmp/etc/network/interfaces /etc/network/interfaces (Verifique se os nomes das interfaces são os mesmos)
        # sudo cp /tmp/etc/exports /etc/exports
        ```
    4.  Pode ser necessário ajustar configurações (e.g., nomes de interface de rede em `/etc/network/interfaces` se o hardware mudou) antes de reiniciar serviços ou o host.
    5.  Reboot o host Proxmox após restaurar arquivos críticos do sistema.

### 2. Máquinas Virtuais (VMs) do Proxmox (`core-services-vm`, `ai-desktop-vm`)

Proxmox VE tem um sistema de backup integrado robusto para VMs.

*   **Como Fazer Backup (Recomendado: via UI Proxmox para Agendamento):**
    1.  **Configure um Storage de Backup no Proxmox:**
        *   Na UI web do Proxmox: Datacenter -> Storage -> Add -> Directory.
        *   **ID:** Dê um nome (e.g., `local_zfs_backups`).
        *   **Directory:** Especifique o caminho no host Proxmox para o seu dataset ZFS de backups (e.g., `{{ zfs_base_pool_path }}/{{ zfs_backups_dataset_name }}/vms` que seria `/data/backups/vms`). Crie este subdiretório `vms` se não existir.
        *   **Content:** Selecione **APENAS "VZDump backup file"**.
        *   **Max Backups:** Você pode definir uma retenção aqui, mas é melhor gerenciar a retenção no próprio job de backup.
    2.  **Crie um Job de Backup Agendado:**
        *   Na UI web do Proxmox: Datacenter -> Backup -> Add.
        *   **Node:** Selecione seu nó Proxmox (`pve`).
        *   **Storage:** Escolha o storage de backup que você acabou de configurar (e.g., `local_zfs_backups`).
        *   **Schedule:** Defina a frequência (e.g., `Diariamente às 02:00`).
        *   **Selection mode:** "Include selected VMs". Selecione suas VMs (`core-services-vm`, `ai-desktop-vm`).
        *   **Mode:**
            *   `Snapshot`: Recomendado. Cria um snapshot da VM em execução e faz o backup a partir dele. Consistente para a maioria das cargas de trabalho. Mínimo downtime.
            *   `Suspend`: Suspende a VM, faz o backup e depois retoma. Mais consistente, mas causa um breve downtime.
            *   `Stop`: Desliga a VM, faz o backup e depois religa (se configurado). Máxima consistência, maior downtime.
        *   **Compression:** `ZSTD (good)` é geralmente uma boa escolha, oferecendo boa compressão com velocidade razoável.
        *   **Retention:** Configure quantas cópias de backup manter (e.g., Keep last: 7 diárias, Keep weekly: 4, Keep monthly: 3). Proxmox podará os backups antigos automaticamente.
        *   **Email Notification:** Configure para receber emails sobre o status dos backups.
*   **Como Restaurar uma VM:**
    1.  Na UI web do Proxmox:
        *   Selecione o **storage de backup** na árvore à esquerda (e.g., `local_zfs_backups`).
        *   A aba "Backups" listará os arquivos de backup disponíveis.
        *   Selecione o arquivo de backup da VM que você deseja restaurar.
        *   Clique no botão "**Restore**".
    2.  No diálogo "Restore":
        *   **VM ID:** Você pode restaurar para o VM ID original (sobrescrevendo a VM existente, se houver e estiver desligada) ou para um **novo VM ID** (criando uma nova VM a partir do backup).
        *   **Storage:** Escolha onde o disco da VM restaurada será armazenado (e.g., `local-lvm`).
        *   Outras opções como `MAC address` (gerar novo ou usar o do backup), `Start after restore`.
    3.  Clique em "Restore". Monitore a tarefa na parte inferior da UI.

### 3. Dados Persistentes dos Containers Docker (Volumes NFS)

Estes são os dados críticos que residem nos seus datasets ZFS (e.g., `/data/docker-volumes`, `/data/media`, `/data/downloads`, `/data/rag_sources`) e são montados nas VMs via NFS para os containers Docker.

#### A. Bancos de Dados das Aplicações (PostgreSQL para Authelia, Nextcloud, Grafana)

É **altamente recomendado** fazer dumps lógicos dos seus bancos de dados, além do backup do volume ZFS onde os arquivos do banco de dados residem. Dumps lógicos são mais portáteis e podem ser mais fáceis de restaurar para diferentes versões do PostgreSQL.

*   **Como Fazer Backup (Scripts Agendados na `core-services-vm`):**
    *   Para cada banco de dados (Authelia, Nextcloud, Grafana), crie um script shell na `core-services-vm` que use `docker exec` para executar o comando `pg_dump` dentro do container Docker do respectivo banco de dados.
    *   Salve os arquivos de dump (`.sql.gz`) em um subdiretório do seu montado NFS de backups (e.g., `/mnt/pve_data_zfs/{{ zfs_backups_dataset_name }}/db_dumps/nextcloud/`, `/mnt/pve_data_zfs/{{ zfs_backups_dataset_name }}/db_dumps/authelia/`, etc.).
    *   **Exemplo de Script para Nextcloud DB (já detalhado na subseção desta própria página sobre backup lógico do PostgreSQL e na [Rotina de Manutenção 01](01-rotinas-manutencao.md#exemplo-de-script-backup_postgres_nextcloudsh)):**
        ```bash
        #!/bin/bash
        # /opt/homelab_scripts/backup_postgres_nextcloud.sh (na core-services-vm)
        DB_CONTAINER_NAME="nextcloud_db"
        DB_USER="nextcloud"
        DB_NAME="nextcloud"
        BACKUP_DEST_PARENT="/mnt/pve_data_zfs/backups/db_dumps" # Ajuste se seu dataset de backup for diferente
        APP_BACKUP_DIR="${BACKUP_DEST_PARENT}/nextcloud"
        TIMESTAMP=$(date +%Y%m%d-%H%M%S)
        BACKUP_FILE="${APP_BACKUP_DIR}/nextcloud_db_${TIMESTAMP}.sql.gz"

        mkdir -p "$APP_BACKUP_DIR"
        echo "Fazendo backup do Nextcloud DB ($DB_NAME) para $BACKUP_FILE..."

        # Assumindo que a senha está em uma variável de ambiente ou .pgpass dentro do container
        # ou que o usuário pode dumpar localmente sem senha.
        # Se NEXTCLOUD_DB_PASSWORD_FROM_PORTAINER_ENV foi usado para criar o usuário no DB,
        # essa senha é necessária aqui. Uma forma é passá-la para o script de forma segura,
        # ou usar .pgpass no container (mais complexo de automatizar com Ansible).
        # Exemplo tentando usar PGPASSWORD (verifique se sua imagem postgres suporta isso para pg_dump):
        # docker exec -e PGPASSWORD="${NEXTCLOUD_DB_PASSWORD_PLAIN}" \
        #   -t "$DB_CONTAINER_NAME" pg_dump -U "$DB_USER" -d "$DB_NAME" -h localhost | gzip > "$BACKUP_FILE"
        # Simplificando, assumindo que a conexão local do usuário funciona:
        docker exec -t "$DB_CONTAINER_NAME" pg_dump -U "$DB_USER" -d "$DB_NAME" | gzip > "$BACKUP_FILE"

        if [ $? -eq 0 ]; then
          echo "Backup do Nextcloud DB concluído: ${BACKUP_FILE}"
          find "$APP_BACKUP_DIR" -name "nextcloud_db_*.sql.gz" -type f -mtime +7 -delete # Retenção de 7 dias
        else
          echo "ERRO: Backup do Nextcloud DB falhou."
        fi
        ```
        Adapte e crie scripts similares para `authelia_db` e `grafana_db`.
    *   Agende esses scripts com `cron` na `core-services-vm` para rodarem diariamente.
*   **Como Restaurar um Banco de Dados PostgreSQL de um Dump:**
    1.  Certifique-se de que o container do banco de dados e o usuário/banco de dados vazios existem na stack Docker (o `docker-compose.yml` deve criá-los se não existirem ao iniciar).
    2.  Copie o arquivo de dump `.sql.gz` mais recente para a `core-services-vm` (e.g., para `/tmp`).
    3.  Execute o comando de restauração (exemplo para Nextcloud):
        ```bash
        # Na core-services-vm
        gunzip < /tmp/nextcloud_db_YYYYMMDD-HHMMSS.sql.gz | docker exec -i nextcloud_db psql -U nextcloud -d nextcloud
        ```
        (Substitua os nomes e usuários conforme o banco de dados que está restaurando).

#### B. Volumes de Arquivos (Configs Docker, Mídia, Downloads, Modelos RAG)

Estes são os diretórios e arquivos dentro dos seus datasets ZFS (`/data/docker-volumes`, `/data/media`, etc.).

*   **Como Fazer Backup (Ferramentas Executadas no Host Proxmox, que tem acesso direto aos datasets ZFS):**
    *   **Opção 1: `borgbackup` (Altamente Recomendado para Eficiência e Criptografia):**
        *   **Vantagens:** Backups incrementais (apenas blocos alterados são enviados após o primeiro backup completo), deduplicação global (economiza muito espaço se houver dados repetidos entre os backups), compressão e criptografia do lado do cliente (seus dados são criptografados antes de saírem do seu servidor).
        *   **Setup Básico:**
            1.  **Instale Borg no host Proxmox:** `sudo apt install borgbackup`.
            2.  **Inicialize um Repositório Borg:** Este repositório pode estar em um HD externo conectado ao Proxmox, em outro servidor na sua LAN com acesso SSH, ou em um storage remoto (como Backblaze B2 via `rclone` como backend para Borg, mais avançado).
                ```bash
                # Exemplo para um HD externo montado em /mnt/borg_backup_repo
                # Use --encryption=repokey (requer passphrase na primeira vez e para cada acesso)
                # ou --encryption=keyfile (requer um arquivo de chave exportado). repokey é comum.
                export BORG_PASSPHRASE='SUA_PASSPHRASE_FORTE_E_UNICA_PARA_O_REPO_BORG'
                borg init --encryption=repokey /mnt/borg_backup_repo/meu_repo_borg_data
                unset BORG_PASSPHRASE # Boa prática
                ```
            3.  **Crie um Script de Backup com Borg (e.g., `/usr/local/sbin/backup_zfs_data_with_borg.sh`):**
                ```bash
                #!/bin/bash
                export BORG_REPO='/mnt/borg_backup_repo/meu_repo_borg_data'
                # Para automação, é melhor usar BORG_PASSCOMMAND para buscar a passphrase de um local seguro,
                # ou uma chave SSH se o repo Borg for remoto. Para simplicidade aqui, assumimos BORG_PASSPHRASE.
                # CUIDADO: Não deixe a passphrase em texto plano em um script sem permissões restritas.
                export BORG_PASSPHRASE='SUA_PASSPHRASE_FORTE_E_UNICA_PARA_O_REPO_BORG'

                # Nome do arquivo de backup (archive)
                ARCHIVE_NAME="homelab_data-{now:%Y-%m-%d_%H-%M-%S}"

                echo "Iniciando backup Borg para o repositório ${BORG_REPO} como ${ARCHIVE_NAME}..."

                borg create --verbose --stats --list --progress \
                    --compression lz4 \
                    ::"${ARCHIVE_NAME}" \
                    {{ zfs_base_pool_path }}/docker-volumes \
                    {{ zfs_base_pool_path }}/media \
                    {{ zfs_base_pool_path }}/downloads \
                    {{ zfs_base_pool_path }}/rag_sources \
                    --exclude '{{ zfs_base_pool_path }}/backups' # NÃO FAÇA BACKUP DO DIRETÓRIO DE BACKUPS EM SI!
                    # Adicione outros --exclude para caches, arquivos temporários grandes, etc.
                    # Ex: --exclude '**/node_modules' --exclude '**/*.pyc' --exclude '**/cache'

                BACKUP_EXIT_CODE=$?

                # Poda de backups antigos (exemplo: manter 7 diários, 4 semanais, 3 mensais)
                echo "Podando backups antigos do repositório ${BORG_REPO}..."
                borg prune -v --list --show-rc \
                    --keep-daily=7 \
                    --keep-weekly=4 \
                    --keep-monthly=3 \
                    --keep-yearly=1 # Opcional: manter 1 anual

                PRUNE_EXIT_CODE=$?

                # Verificar integridade do repositório (opcional, mas bom de vez em quando)
                # borg check -v --show-rc

                unset BORG_PASSPHRASE

                if [ ${BACKUP_EXIT_CODE} -eq 0 ] && [ ${PRUNE_EXIT_CODE} -eq 0 ]; then
                  echo "Backup Borg e poda concluídos com sucesso."
                  /opt/homeserver/scripts/notify.sh ok "Backup Borg concluído" "${ARCHIVE_NAME}" borg
                else
                  echo "ERRO: Backup Borg ou poda falhou. Código de saída do Backup: ${BACKUP_EXIT_CODE}, Poda: ${PRUNE_EXIT_CODE}"
                  /opt/homeserver/scripts/notify.sh critical "Backup Borg falhou" "backup=${BACKUP_EXIT_CODE} poda=${PRUNE_EXIT_CODE}" borg
                fi
                ```
            4.  Torne o script executável e agende-o com `cron`. O aviso no Telegram vem do `scripts/notify.sh` (copie-o para `/opt/homeserver/scripts/` no host e configure `/etc/default/homeserver-notify`, ver [Painel e Notificações](../01-manual-implementacao/09-painel-notificacoes.md)).
    *   **Opção 2: `rsync` (Mais Simples, para Sincronização/Cópia Direta):**
        *   Bom para criar uma cópia espelhada dos seus dados em outro local (e.g., HD externo, outro servidor NAS). Não oferece deduplicação ou versionamento histórico como Borg, a menos que combinado com snapshots ou outras lógicas.
        *   **Exemplo de Script (sincronizar `/data/docker-volumes` para um HD externo):**
            ```bash
            #!/bin/bash
            SOURCE_DIR="{{ zfs_base_pool_path }}/docker-volumes/" # Note a barra no final!
            DEST_DIR="/mnt/meu_hd_externo_backup/docker-volumes/" # Note a barra no final!
            LOG_FILE="/var/log/rsync_backup_docker_volumes.log"

            echo "Iniciando rsync de ${SOURCE_DIR} para ${DEST_DIR} em $(date)" >> "${LOG_FILE}"
            rsync -avz --delete --human-readable --info=progress2 \
                "${SOURCE_DIR}" \
                "${DEST_DIR}" >> "${LOG_FILE}" 2>&1
            # --delete: remove arquivos no destino que não existem mais na origem
            # -a: modo archive (preserva permissões, links, etc.)
            # -v: verboso
            # -z: compressão durante a transferência

            if [ $? -eq 0 ]; then
              echo "Rsync de docker-volumes concluído com sucesso em $(date)" >> "${LOG_FILE}"
              /opt/homeserver/scripts/notify.sh ok "Rsync de docker-volumes concluído" "Destino: ${DEST_DIR}" rsync
            else
              echo "ERRO: Rsync de docker-volumes falhou em $(date)" >> "${LOG_FILE}"
              /opt/homeserver/scripts/notify.sh critical "Rsync de docker-volumes falhou" "Veja ${LOG_FILE}" rsync
            fi
            ```
        *   Agende com `cron`.
*   **Como Restaurar Volumes de Arquivos:**
    *   **BorgBackup:**
        *   Listar arquivos: `borg list /caminho/para/repo_borg::nome_do_archive`
        *   Montar um archive como sistema de arquivos (para navegar e copiar):
            `borg mount /caminho/para/repo_borg::nome_do_archive /mnt/borg_restore_temp`
            (Depois `fusermount -u /mnt/borg_restore_temp` para desmontar).
        *   Extrair (restaurar) arquivos/diretórios para um local:
            `borg extract --verbose --list /caminho/para/repo_borg::nome_do_archive caminho_relativo_dentro_do_archive`
            (Extrai para o diretório atual, ou use `--target /caminho/destino/absoluto`).
    *   **Rsync:** Simplesmente copie os arquivos de volta do seu destino de backup rsync para o local original.

### 4. ZFS Snapshots (Proteção Local Rápida no Host Proxmox)

Como detalhado no [Guia Prático de Snapshots ZFS](../03-guias-sustentacao/12-guia-snapshots-zfs.md), os snapshots ZFS são uma forma rápida e eficiente de proteger seus datasets (`/data/docker-volumes`, `/data/media`, etc.) contra erros humanos (deleção acidental) ou corrupção de software.

*   **Como Fazer Snapshots:**
    *   **Manual (para ações pontuais):** `sudo zfs snapshot data/docker-volumes@antes_de_uma_mudanca_arriscada`
    *   **Automatizado com `zfs-auto-snapshot` (ou `sanoid`):**
        *   O pacote `zfs-auto-snapshot` (geralmente instalado com `zfsutils-linux` no Debian/Ubuntu) configura scripts cron para tirar e podar snapshots automaticamente (e.g., horários, diários, semanais, mensais).
        *   Verifique a configuração em `/etc/cron.*/zfs-auto-snapshot` e, se existir, `/etc/default/zfs-auto-snapshot`.
        *   Para controle mais avançado e integração com replicação, considere [Sanoid/Syncoid](https://github.com/jimsalterjrs/sanoid).
*   **Como Restaurar de um Snapshot ZFS:**
    *   **Rollback (Reverte o dataset inteiro - CUIDADO!):** `sudo zfs rollback data/docker-volumes@nome_do_snapshot`
    *   **Acessar Arquivos de um Snapshot (Método Seguro, Não Destrutivo):**
        Os snapshots são montados automaticamente em um diretório oculto `.zfs/snapshot/` dentro do ponto de montagem do dataset ativo.
        Exemplo: Para restaurar `/data/docker-volumes/meuapp/config.txt` do snapshot `@snap1`:
        `sudo cp /data/docker-volumes/.zfs/snapshot/snap1/meuapp/config.txt /data/docker-volumes/meuapp/config.txt`

### 5. Repositório Ansible Git (`home-server/`)

Sua configuração de Infraestrutura como Código é um ativo crítico.

*   **Como Fazer Backup:**
    *   Regularmente (após cada mudança significativa) execute `git add .`, `git commit -m "Sua mensagem descritiva"`, e **`git push` para um repositório Git remoto** (e.g., GitHub, GitLab, Gitea auto-hospedado).
    *   Isso serve como seu backup principal e off-site para toda a lógica de configuração da sua infraestrutura.
*   **Como Restaurar:**
    *   Em uma nova máquina de controle Ansible (ou na mesma, se o diretório local foi perdido), simplesmente execute `git clone URL_DO_SEU_REPO_REMOTO`.
    *   Certifique-se de ter sua senha do Ansible Vault para descriptografar o `vault.yml`.

### 6. Cópia Off-site (Essencial para Cumprir a Regra 3-2-1)

Ter pelo menos uma cópia dos seus backups mais importantes **fora da sua residência** é o que protege contra desastres locais (incêndio, roubo, inundação, surto elétrico que destrói tudo).

*   **O Que Enviar Off-site:**
    *   Seu repositório Borg (se usar Borg para os volumes ZFS).
    *   Os arquivos de backup das VMs Proxmox (`.vma.zst`).
    *   Os dumps dos seus bancos de dados.
    *   O backup da configuração do host Proxmox.
    *   Seu repositório Git Ansible (o `git push` para um remote já é off-site).
*   **Métodos para Cópia Off-site:**
    *   **`rclone` para Armazenamento em Nuvem (Recomendado para Automação):**
        *   [rclone](https://rclone.org/) é uma ferramenta de linha de comando extremamente versátil para sincronizar arquivos e diretórios com dezenas de provedores de armazenamento em nuvem (e.g., Backblaze B2, Amazon S3/Glacier, Google Cloud Storage, Wasabi, Storj, etc.).
        *   **Setup:**
            1.  Instale `rclone` no seu host Proxmox (ou em uma VM dedicada para backups).
            2.  Configure um "remote" no `rclone` para o seu provedor de nuvem escolhido: `rclone config`. Siga as instruções para autenticar.
            3.  **Use a Criptografia do `rclone` (`crypt` remote):** É **altamente recomendado** criar um remote do tipo `crypt` que fica "em cima" do seu remote do provedor de nuvem. Isso garante que seus dados sejam criptografados **antes** de serem enviados para a nuvem, e apenas você tem a chave de descriptografia.
        *   **Comandos para Sincronizar/Copiar:**
            ```bash
            # Exemplo: Sincronizar o diretório de backups de VMs para um remote crypt 'nuvem_criptografada:'
            # que aponta para um bucket no Backblaze B2.
            rclone sync /data/backups/vms/ nuvem_criptografada:meu_servidor/proxmox_vm_backups/ --progress --checksum --transfers=4 --checkers=8
            # --checksum: verifica arquivos baseados em checksum em vez de apenas tamanho/modtime
            # --transfers, --checkers: ajusta paralelismo
            ```
        *   Agende seus comandos `rclone` com `cron` no host Proxmox para rodar após seus backups locais serem concluídos.
    *   **HD Externo Rotacionado Fisicamente:**
        *   Mantenha um (ou mais) HDs externos USB.
        *   Regularmente (e.g., semanalmente), conecte o HD ao host Proxmox, copie seus backups locais para ele (usando `rsync` ou Borg para um repositório no HD externo).
        *   **Guarde o HD externo em um local seguro e fisicamente separado** da sua casa (e.g., casa de um familiar, trabalho, cofre bancário). Rotacione com outro HD externo.
    *   **Servidor de Backup Remoto (Outro Local Físico):**
        Se você tiver acesso a outro servidor em um local diferente (e.g., casa de um amigo, outro escritório), você pode usar:
        *   `rsync` sobre SSH.
        *   Borg com um repositório remoto via SSH.
        *   `zfs send/recv` via SSH (se o destino também for ZFS).

## Testando Seus Backups e Procedimentos de Restauração

Repetindo pela última vez (mas não menos importante): **TESTE, TESTE, TESTE!**

*   **Agende Testes de Restauração:** Pelo menos uma vez por trimestre, ou após qualquer mudança significativa na sua estratégia de backup ou nos sistemas que você está backupeando.
*   **Simule Cenários de Falha:**
    *   "Perdi um arquivo importante no Nextcloud." -> Tente restaurá-lo de um snapshot ZFS ou do dump do banco de dados + backup de arquivos do Nextcloud.
    *   "Minha VM `core-services-vm` não inicia mais." -> Tente restaurá-la de um backup do Proxmox para um novo VM ID.
    *   "O host Proxmox inteiro morreu, mas meus HDDs do pool `/data` estão OK (ou tenho backup off-site)." -> Siga os passos de [Reconstruindo a Infraestrutura](04-reconstruindo-infraestrutura.md).
*   **Documente Seus Procedimentos de Restauração:** Enquanto você testa, anote os passos exatos. Em uma emergência real, você estará sob pressão e ter um guia passo a passo documentado por você mesmo será inestimável.

Uma estratégia de backup bem implementada e regularmente testada é o que lhe dará a verdadeira tranquilidade e a capacidade de se recuperar de quase qualquer eventualidade com seu servidor doméstico.

### 5. Backup Off-site para a Nuvem (Google Cloud Storage)

Esta é a etapa que completa nossa regra 3-2-1, garantindo que tenhamos uma cópia dos nossos dados mais críticos em um local geograficamente separado.

*   **O Que Fazer Backup:**
    *   Os backups da **configuração do host Proxmox** gerados pelo script local.
    *   Os backups das **VMs** gerados pelo Proxmox.
    *   Os **snapshots ZFS** dos seus datasets de dados.

*   **Como Fazer Backup:**
    *   Use `rclone` para sincronizar os backups para outro disco ou servidor remoto.

*   **Como Restaurar:**
    *   Reconstrua o host Proxmox do zero, importe os backups de VM e restaure os snapshots ZFS conforme descrito em [Reconstruindo a Infraestrutura](04-reconstruindo-infraestrutura.md).
