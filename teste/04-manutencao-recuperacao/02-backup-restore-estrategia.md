# Estratégia de Backup e Procedimentos de Restauração

Uma estratégia de backup abrangente e testada é a sua rede de segurança contra perda de dados devido a falhas de hardware, corrupção de software, erros humanos ou ataques maliciosos (como ransomware). Este guia detalha o que fazer backup, como fazê-lo e, crucialmente, como restaurar.

## A Regra de Ouro: 3-2-1

Lembre-se sempre da regra 3-2-1 para backups:

*   **3 Cópias dos Dados:** Tenha pelo menos três cópias de qualquer dado importante (o original + dois backups).
*   **2 Mídias Diferentes:** Armazene as cópias em pelo menos dois tipos diferentes de mídia de armazenamento (e.g., HD interno, HD externo, fita, armazenamento em nuvem).
*   **1 Cópia Off-site:** Mantenha pelo menos uma cópia do backup fisicamente separada do local original (e.g., na nuvem, na casa de um amigo/familiar, em um cofre).

!!! critical "Teste Seus Backups!"
    Um backup não testado é pouco melhor que nenhum backup. **Regularmente teste seu processo de restauração** para garantir que você pode recuperar seus dados quando precisar.

## O Que Fazer Backup e Como

Vamos detalhar o backup para cada componente crítico da nossa infraestrutura:

### 1. Configuração do Host Proxmox VE

Isto inclui as configurações do próprio hypervisor, rede, ZFS, NFS, etc.

*   **O Que Fazer Backup:**
    *   `/etc/pve/` (configurações de VMs, storage, cluster)
    *   `/etc/hostname`, `/etc/hosts`
    *   `/etc/network/interfaces` (configuração de rede do host)
    *   `/etc/resolv.conf` (se não gerenciado por DHCP/systemd-resolved)
    *   `/etc/default/grub`, `/etc/kernel/cmdline` (opções de boot)
    *   `/etc/modules`, `/etc/modprobe.d/` (módulos do kernel, blacklists)
    *   `/etc/cron*` (tarefas agendadas do host)
    *   `/etc/ssh/sshd_config` (configuração do servidor SSH)
    *   `/etc/smartd.conf` (configuração do S.M.A.R.T.)
    *   `/etc/zfs/` (configuração do ZFS, embora o pool em si seja mais importante)
    *   `/etc/exports` (configuração do servidor NFS)
    *   Outros arquivos de configuração importantes que você possa ter modificado.
*   **Como Fazer Backup (Script Agendado no Host Proxmox):**
    *   Crie um script, por exemplo, `/usr/local/sbin/backup_proxmox_host_config.sh`:
    ```bash
    #!/bin/bash
    # /usr/local/sbin/backup_proxmox_host_config.sh

    # Destino do backup (no pool ZFS /data/backups)
    BACKUP_BASE_DIR="{{ zfs_base_pool_path }}/{{ zfs_backups_dataset_name }}" # e.g., /data/backups
    BACKUP_DEST="${BACKUP_BASE_DIR}/proxmox_host_config"
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    FILENAME="proxmox_etc_backup_${TIMESTAMP}.tar.gz"

    mkdir -p "$BACKUP_DEST"

    echo "Iniciando backup da configuração do host Proxmox para ${BACKUP_DEST}/${FILENAME}..."

    tar czfP ${BACKUP_DEST}/${FILENAME} \
        /etc/pve \
        /etc/hostname \
        /etc/hosts \
        /etc/network/interfaces \
        /etc/resolv.conf \
        /etc/default/grub \
        /etc/kernel/cmdline \
        /etc/modules \
        /etc/modprobe.d \
        /etc/cron* \
        /etc/issue* \
        /etc/ssh/sshd_config \
        /etc/smartd.conf \
        /etc/zfs \
        /etc/exports \
        /etc/systemd/system/ollama.service.d/override.conf # Se Ollama no host
        # Adicione outros arquivos/diretórios importantes

    if [ $? -eq 0 ]; then
      echo "Backup da configuração do host Proxmox concluído com sucesso."
      # Opcional: Remover backups antigos (e.g., manter os últimos 7)
      find "$BACKUP_DEST" -name "proxmox_etc_backup_*.tar.gz" -type f -mtime +7 -delete
    else
      echo "ERRO: Backup da configuração do host Proxmox falhou."
      # Adicione notificação por email aqui se desejar
    fi
    ```
    *   Torne executável: `sudo chmod +x /usr/local/sbin/backup_proxmox_host_config.sh`.
    *   Agende com `cron` (e.g., `sudo crontab -e`):
        `0 3 * * * /usr/local/sbin/backup_proxmox_host_config.sh` (Todo dia às 3 AM).
*   **Como Restaurar:**
    1.  Após uma reinstalação limpa do Proxmox VE (mesma versão ou compatível).
    2.  Copie o arquivo `.tar.gz` de backup para o novo host.
    3.  Extraia com cuidado os arquivos para seus locais originais. **Seja MUITO CUIDADOSO ao sobrescrever arquivos existentes.** É melhor restaurar seletivamente o que você precisa.
    4.  Pode ser necessário ajustar configurações (e.g., `interfaces` de rede se o hardware mudou).
    5.  Reboot.

### 2. Máquinas Virtuais (VMs) do Proxmox

Proxmox VE tem um sistema de backup integrado excelente.

*   **Como Fazer Backup:**
    *   **Via Interface Web do Proxmox:**
        1.  Datacenter -> Backup -> Add.
        2.  **Node:** Selecione seu host Proxmox.
        3.  **Storage:** Selecione o storage de destino para os backups. Crie um "Directory" storage no Proxmox apontando para o seu dataset ZFS de backups (e.g., `/data/backups/vms`).
        4.  **Schedule:** Defina a frequência (e.g., diário, semanal).
        5.  **Selection mode:** Escolha as VMs a serem incluídas.
        6.  **Mode:** `Snapshot` (consistente para VMs rodando). `Suspend` ou `Stop` são mais consistentes mas causam downtime.
        7.  **Compression:** `ZSTD (good)` é uma boa escolha.
        8.  **Retention:** Defina quantas cópias manter (e.g., 7 diárias, 4 semanais, 3 mensais).
    *   **Via Linha de Comando (`vzdump` no host Proxmox):**
        ```bash
        # Exemplo para fazer backup da VM 100 para /data/backups/vms
        vzdump 100 --storage local_backup_storage --mode snapshot --compress zstd --notes-template "Backup {{vmid}} {{ ટકાવારી }}"
        ```
        (Assumindo que `local_backup_storage` está configurado no Proxmox para `/data/backups/vms`).
*   **Como Restaurar:**
    *   **Via Interface Web do Proxmox:**
        1.  Selecione o storage de backup onde o arquivo de backup da VM está.
        2.  Encontre o arquivo de backup -> "Restore".
        3.  Escolha o VMID para a VM restaurada (pode ser o original ou um novo).
        4.  Configure outras opções se necessário.
    *   **Via Linha de Comando (`qmrestore` no host Proxmox):**
        ```bash
        # Exemplo para restaurar um backup para a VM 105
        qmrestore /data/backups/vms/vzdump-qemu-100-YYYY_MM_DD-HH_MM_SS.vma.zst 105
        ```

### 3. Dados Persistentes dos Containers Docker (Volumes NFS)

Estes são os dados armazenados nos seus datasets ZFS como `/data/docker-volumes`, `/data/media`, etc., que são montados nas VMs via NFS.

#### Bancos de Dados (PostgreSQL de Authelia, Nextcloud, Grafana)

É crucial fazer backup dos bancos de dados de forma consistente.

*   **Como Fazer Backup (Scripts Agendados na `core-services-vm`):**
    *   Para cada banco de dados, crie um script que use `docker exec` para rodar `pg_dump` dentro do container do banco de dados.
    *   Salve os dumps em um subdiretório de `/mnt/pve_data_zfs/{{ zfs_backups_dataset_name }}/db_dumps/` (que é o montado NFS para o dataset de backups do Proxmox).
    *   **Exemplo de script (`/opt/homelab_scripts/backup_postgres_nextcloud.sh` na `core-services-vm`):**
        ```bash
        #!/bin/bash
        DB_CONTAINER_NAME="nextcloud_db" # Nome do container Docker do DB Nextcloud
        DB_USER="nextcloud"
        DB_NAME="nextcloud"
        # Caminho NFS para o diretório de backups de DB
        BACKUP_BASE_DIR="/mnt/pve_data_zfs/{{ zfs_backups_dataset_name }}/db_dumps"
        APP_BACKUP_DIR="${BACKUP_BASE_DIR}/nextcloud"
        TIMESTAMP=$(date +%Y%m%d-%H%M%S)
        BACKUP_FILE="${APP_BACKUP_DIR}/nextcloud_db_${TIMESTAMP}.sql.gz"

        mkdir -p "$APP_BACKUP_DIR"
        echo "Fazendo backup do banco de dados Nextcloud ($DB_NAME) para $BACKUP_FILE"

        # Garante que o comando pg_dump tenha o $PGPASSWORD (se necessário e não no .pgpass)
        # A senha é passada via variável de ambiente para o comando pg_dump dentro do container.
        # A variável NEXTCLOUD_DB_PASSWORD_FROM_PORTAINER_ENV é a senha real do DB.
        # Este script precisaria ter acesso a essa senha de alguma forma segura,
        # ou assumir que o .pgpass está configurado dentro do container (menos provável para setups simples).
        # Para este exemplo, vamos assumir que o usuário 'nextcloud' pode dumpar sem senha explícita
        # se conectado localmente, ou que a senha foi configurada de outra forma.
        # Uma forma mais segura seria usar um arquivo de senha do pg_dump se suportado.
        # Simplificando aqui:
        docker exec -t "$DB_CONTAINER_NAME" pg_dump -U "$DB_USER" -d "$DB_NAME" | gzip > "$BACKUP_FILE"

        if [ $? -eq 0 ]; then
          echo "Backup do Nextcloud DB concluído com sucesso."
          find "$APP_BACKUP_DIR" -name "nextcloud_db_*.sql.gz" -type f -mtime +7 -delete # Mantém 7 dias
        else
          echo "ERRO: Backup do Nextcloud DB falhou."
          # Adicione notificação
        fi
        ```
    *   Crie scripts similares para `authelia_db` e `grafana_db`.
    *   Agende-os com `cron` na `core-services-vm`. Ex: `0 4 * * * /opt/homelab_scripts/backup_postgres_nextcloud.sh`.
*   **Como Restaurar um Banco de Dados PostgreSQL:**
    1.  Certifique-se que o container do banco de dados e o schema/usuário existem.
    2.  Copie o arquivo de dump `.sql.gz` para a VM.
    3.  Execute (exemplo para Nextcloud):
        ```bash
        # Na core-services-vm
        gunzip < nextcloud_db_YYYYMMDD-HHMMSS.sql.gz | docker exec -i nextcloud_db psql -U nextcloud -d nextcloud
        ```

#### Volumes de Arquivos (Configs Docker, Mídia, etc.)

Estes são os diretórios nos seus datasets ZFS (e.g., `/data/docker-volumes`, `/data/media`).

*   **Como Fazer Backup (Ferramentas no Host Proxmox):**
    *   **`borgbackup` (Altamente Recomendado):**
        *   **Vantagens:** Backups incrementais (apenas mudanças são salvas), deduplicação (economiza espaço), compressão, criptografia.
        *   **Setup:**
            1.  Instale Borg: `sudo apt install borgbackup` no host Proxmox.
            2.  Inicialize um repositório Borg (pode ser em um HD externo conectado ao Proxmox, ou um destino remoto via SSH):
                `borg init --encryption=repokey /caminho/para/repo_borg`
            3.  Crie um script de backup (e.g., `/usr/local/sbin/backup_zfs_data_with_borg.sh`):
                ```bash
                #!/bin/bash
                export BORG_REPO='/caminho/para/repo_borg'
                export BORG_PASSPHRASE='sua_passphrase_do_repo_borg_aqui' # Ou use BORG_PASSCOMMAND

                borg create --verbose --stats --compression lz4 \
                    ::'{hostname}-{now:%Y-%m-%d_%H:%M:%S}' \
                    /data/docker-volumes \
                    /data/media \
                    /data/downloads \
                    /data/rag_sources \
                    # Exclua o dataset de backups de VMs para não fazer backup de backups
                    --exclude '/data/backups'

                # Poda de backups antigos (ex: manter 7 diários, 4 semanais, 3 mensais)
                borg prune -v --list --keep-daily=7 --keep-weekly=4 --keep-monthly=3
                ```
            4.  Agende com `cron`.
    *   **`rsync` (Mais Simples, para Sincronização):**
        *   Bom para criar uma cópia espelhada em outro local (e.g., HD externo, outro servidor).
        *   Exemplo: `rsync -avz --delete /data/docker-volumes/ /mnt/hd_externo_backup/docker-volumes/`
*   **Como Restaurar Volumes de Arquivos:**
    *   **Borg:** `borg extract /caminho/para/repo_borg::archive_name caminho/para/restaurar` ou `borg mount` para navegar.
    *   **Rsync:** Copie os arquivos de volta do destino do rsync.

### 4. ZFS Snapshots (no Host Proxmox)

Snapshots ZFS são uma forma rápida e eficiente de proteger seus datasets contra erros humanos (deleção acidental) ou corrupção de software. Eles não substituem backups completos (especialmente off-site), mas são uma ótima primeira linha de defesa.

*   **Como Fazer Snapshots:**
    *   **Manual:** `sudo zfs snapshot data/docker-volumes@meu_snapshot_manual`
    *   **Automatizado com `zfs-auto-snapshot`:**
        1.  Instale no host Proxmox: `sudo apt install zfs-auto-snapshot`
        2.  Este pacote instala scripts cron em `/etc/cron.hourly/`, `/etc/cron.daily/`, etc., que automaticamente tiram snapshots dos seus pools ZFS.
        3.  Você pode configurar a frequência e retenção editando esses scripts ou as variáveis em `/etc/default/zfs-auto-snapshot` (se existir) ou diretamente nos scripts cron.
*   **Como Restaurar de um Snapshot ZFS:**
    *   **Listar Snapshots:** `sudo zfs list -t snapshot`
    *   **Rollback (Reverte o dataset inteiro para o estado do snapshot - CUIDADO, PERDE MUDANÇAS POSTERIORES):**
        `sudo zfs rollback data/docker-volumes@nome_do_snapshot`
    *   **Clonar Snapshot (Cria uma cópia gravável do snapshot):**
        `sudo zfs clone data/docker-volumes@nome_do_snapshot data/docker-volumes-restaurado`
    *   **Acessar Arquivos de um Snapshot (Sem Rollback):**
        Snapshots são montados automaticamente em um diretório `.zfs/snapshot/` dentro do ponto de montagem do dataset.
        Ex: `cd /data/docker-volumes/.zfs/snapshot/nome_do_snapshot/`
        Você pode então copiar arquivos de lá para o dataset ativo.

### 5. Repositório Ansible Git

*   Seu repositório `infra-servidor-domestico` (contendo toda a configuração Ansible) é um componente crítico.
*   **Como Fazer Backup:** Regularmente faça `git push` para um repositório Git remoto (GitHub, GitLab, Gitea auto-hospedado). Isso serve como backup off-site da sua configuração de infraestrutura.
*   **Como Restaurar:** `git clone` do repositório remoto para uma nova máquina de controle Ansible.

### 6. Cópia Off-site (Essencial para a Regra 3-2-1)

Ter uma cópia dos seus backups mais importantes fora da sua residência protege contra desastres locais (incêndio, roubo, inundação).

*   **Métodos:**
    *   **`rclone` para Armazenamento em Nuvem:**
        *   `rclone` é uma ferramenta de linha de comando poderosa para sincronizar arquivos e diretórios com diversos provedores de armazenamento em nuvem (Backblaze B2, Amazon S3, Google Drive, etc.).
        *   **Setup:**
            1.  Instale `rclone`.
            2.  Configure um "remote" para o seu provedor de nuvem: `rclone config`.
            3.  Use `rclone sync` ou `rclone copy` para enviar seus backups locais (e.g., os arquivos de backup de VMs do Proxmox, os dumps de DB, o repositório Borg) para o remote na nuvem.
            4.  **Criptografia:** `rclone` suporta criptografia do lado do cliente (`crypt` remote), para que seus dados sejam enviados para a nuvem já criptografados.
        *   Agende com `cron`.
    *   **HD Externo Rotacionado:** Mantenha um HD externo com backups e guarde-o em um local seguro fora de casa, atualizando-o periodicamente.
    *   **Servidor de Backup Remoto (Outro Local):** Se você tiver acesso a outro local com um servidor, pode usar `rsync` sobre SSH ou Borg para fazer backups remotos.

## Testando Seus Backups

Repetindo: **TESTE SEUS PROCEDIMENTOS DE RESTAURAÇÃO REGULARMENTE!**

*   Escolha um serviço não crítico ou crie um ambiente de teste.
*   Simule uma falha (e.g., delete um arquivo de configuração, pare um container, delete uma VM de teste).
*   Siga seu procedimento de restauração documentado para recuperar o serviço/dados.
*   Verifique se tudo voltou ao normal.
*   Anote quaisquer problemas encontrados e refine seu processo de backup/restauração.

Uma estratégia de backup bem planejada e testada é o que lhe dará tranquilidade sabendo que seus dados e sua infraestrutura estão protegidos.