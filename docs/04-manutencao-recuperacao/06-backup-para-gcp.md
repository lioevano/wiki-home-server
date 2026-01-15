---

## 6. Backup Off-site Automatizado para o Google Cloud Storage

Seguindo a regra de ouro dos backups (3-2-1), ter uma cópia off-site (fora do local físico do servidor) é um componente não-negociável de uma estratégia de dados resiliente. Para nosso home server, o Google Cloud Storage (GCS) serve como um destino de backup ideal: é econômico, durável e acessível de qualquer lugar.

Nesta seção, vamos configurar e automatizar o processo de envio dos nossos backups locais (configurações do Proxmox, backups de VMs e snapshots ZFS) para um bucket no GCS. Usaremos a ferramenta **rclone**, um canivete suíço da linha de comando para gerenciamento de armazenamento em nuvem. Ele suporta dezenas de provedores, oferece criptografia do lado do cliente e possui funcionalidades avançadas de sincronização.

!!! tip "rclone vs. gsutil"
    Embora o `gsutil` seja a ferramenta de linha de comando nativa do Google para interagir com o GCS, optamos pelo `rclone` por três motivos principais:
    1.  **Agnóstico ao Provedor:** Se um dia você decidir mudar do GCS para o Backblaze B2 ou AWS S3, basta alterar a configuração do `rclone`, sem reescrever seus scripts.
    2.  **Criptografia do Lado do Cliente:** O `rclone` pode criptografar o conteúdo dos seus arquivos *antes* de enviá-los para a nuvem. Isso significa que nem mesmo o Google pode ler seus dados, oferecendo uma camada de privacidade superior.
    3.  **Simplicidade de Sincronização:** Comandos como `rclone sync` são extremamente poderosos e intuitivos para manter um diretório local e um remoto em sincronia.

### 1. Preparação na Google Cloud Platform

Antes de configurar o `rclone`, precisamos preparar o ambiente no GCP.

1.  **Crie um Projeto no GCP:** Se ainda não tiver um, crie um novo projeto no [console do GCP](https://console.cloud.google.com/).
2.  **Crie um Bucket no Cloud Storage:**
    *   Navegue até o Cloud Storage e crie um novo bucket.
    *   **Nome:** Escolha um nome globalmente único (ex: `meu-home-server-backups-2026`).
    *   **Localização:** Escolha uma região geograficamente distante da sua localização física para maximizar a proteção contra desastres regionais (ex: se você está na América do Sul, escolha uma região na Europa ou América do Norte).
    *   **Classe de Armazenamento:** Para backups que você acessará raramente (idealmente, nunca), escolha uma classe de armazenamento mais barata, como `Archive` (Arquivamento). O custo de armazenamento é muito baixo, mas há um custo maior para recuperação e um tempo de espera. Para testes de restauração mais frequentes, `Coldline` ou `Standard` podem ser mais apropriados inicialmente.
    *   **Controle de Acesso:** Mantenha o modelo de "Controle de acesso uniforme".
3.  **Crie uma Conta de Serviço (Service Account):**
    *   É uma má prática usar sua conta de usuário principal para automação. Em vez disso, crie uma conta de serviço dedicada para o `rclone`.
    *   Navegue para "IAM e Admin" -> "Contas de Serviço".
    *   Crie uma nova conta de serviço (ex: `rclone-backup-agent`).
    *   **Conceda a ela o papel (Role) de "Administrador de objetos do Storage" (`Storage Object Admin`)**. Isso dará à conta permissão para ler, escrever e excluir objetos no seu bucket.
    *   **Crie uma chave para a conta de serviço:** Na aba "Chaves" da conta de serviço, crie uma nova chave no formato JSON. Um arquivo `.json` será baixado para o seu computador. **Este arquivo é extremamente sensível. Trate-o como uma senha.**

### 2. Configuração do rclone no Host Proxmox

Vamos instalar e configurar o `rclone` diretamente no host Proxmox, pois é ele que tem acesso direto a todos os datasets ZFS e backups.

1.  **Instale o rclone:**

    ```bash
    # No shell do host Proxmox
    sudo apt-get update
    sudo apt-get install -y rclone
    ```

2.  **Transfira a Chave da Conta de Serviço:**
    Copie o arquivo `.json` da chave da conta de serviço que você baixou para um local seguro no seu host Proxmox, por exemplo, `/root/.config/rclone/gcp_key.json`. Use `scp` ou uma ferramenta segura para a transferência.

3.  **Configure o rclone:**
    Execute `rclone config` no host Proxmox para iniciar o assistente de configuração interativo.

    *   `n` (New remote)
    *   `name`: Dê um nome para o seu remote do GCS (ex: `gcs_backup`).
    *   `Storage`: Escolha `Google Cloud Storage (gcs)`.
    *   `project_number`: Deixe em branco.
    *   `service_account_file`: Insira o caminho para o seu arquivo de chave JSON (`/root/.config/rclone/gcp_key.json`).
    *   `object_acl` e `bucket_acl`: Deixe em branco para usar os padrões do bucket.
    *   `location`: Deixe em branco.
    *   `storage_class`: Deixe em branco (o `rclone` usará a classe padrão do bucket).
    *   `Edit advanced config?`: `n` (Não).
    *   Revise a configuração e confirme com `y`.

4.  **(Recomendado) Crie um Remote Criptografado:**
    Agora, vamos criar um segundo remote do `rclone` do tipo `crypt`. Este remote irá "envelopar" o remote do GCS que acabamos de criar, garantindo que tudo enviado através dele seja criptografado.

    *   Execute `rclone config` novamente.
    *   `n` (New remote)
    *   `name`: Dê um nome para o remote criptografado (ex: `gcs_backup_crypt`).
    *   `Storage`: Escolha `crypt`.
    *   `Remote to encrypt/decrypt`: Especifique o remote do GCS que você criou, seguido pelo nome do bucket e um subdiretório (ex: `gcs_backup:meu-home-server-backups-2026/encrypted_data`). O `rclone` irá criar este diretório no bucket.
    *   `How to encrypt the filenames?`: `2` (Obfuscate) é uma boa opção para esconder a estrutura de diretórios.
    *   `Password`: Escolha uma senha forte e segura. **SE VOCÊ PERDER ESTA SENHA, SEUS DADOS SERÃO IRRECUPERÁVEIS.** Salve-a no seu gerenciador de senhas e no Ansible Vault.
    *   `Salt`: Escolha uma segunda senha (salt). Mesma advertência acima.
    *   `Edit advanced config?`: `n` (Não).
    *   Confirme com `y`.

### 3. Script de Backup Automatizado

Agora podemos criar um script que usa o `rclone` para sincronizar nossos backups locais para a nuvem. Crie o arquivo `/usr/local/sbin/sync_backups_to_gcs.sh` no host Proxmox.

```bash
#!/bin/bash
# /usr/local/sbin/sync_backups_to_gcs.sh

# Configuração
LOG_FILE="/var/log/rclone_sync.log"
REMOTE_CRYPT="gcs_backup_crypt:"

# Diretórios de origem dos backups no host Proxmox
# (Correspondem aos destinos dos scripts de backup locais)
PROXMOX_HOST_CONFIG_BACKUPS="/data/backups/proxmox_host_config"
PROXMOX_VM_BACKUPS="/data/backups/dump"
ZFS_SNAPSHOTS_BACKUPS="/data/backups/zfs_snapshots"

# Função para logar mensagens
log() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') - $1" | tee -a $LOG_FILE
}

# Função para executar a sincronização com rclone
sync_dir() {
    local src=$1
    local dest_subfolder=$2
    log "Iniciando sincronização de ${src} para ${REMOTE_CRYPT}${dest_subfolder}"
    
    # Usamos 'sync' que só copia arquivos novos ou modificados.
    # --create-empty-src-dirs garante que a estrutura de diretórios seja mantida.
    # --fast-list usa menos transações para listar arquivos em buckets grandes.
    # --progress mostra o progresso no log.
    rclone sync "${src}" "${REMOTE_CRYPT}${dest_subfolder}" --create-empty-src-dirs --fast-list --progress >> $LOG_FILE 2>&1
    
    if [ $? -eq 0 ]; then
        log "Sincronização de ${src} concluída com sucesso."
    else
        log "ERRO na sincronização de ${src}. Verifique o log para detalhes."
    fi
}

log "======================================"
log "Iniciando ciclo de backup off-site para GCS"

# Sincronizar cada diretório de backup para uma subpasta no remote
sync_dir "$PROXMOX_HOST_CONFIG_BACKUPS" "proxmox_host_config"
sync_dir "$PROXMOX_VM_BACKUPS" "proxmox_vm_backups"
sync_dir "$ZFS_SNAPSHOTS_BACKUPS" "zfs_snapshots"

log "Ciclo de backup off-site concluído."
log "======================================"

# (Opcional) Limpeza de logs antigos
find $LOG_FILE -mtime +30 -delete
```

**Torne o script executável:**

```bash
chmod +x /usr/local/sbin/sync_backups_to_gcs.sh
```

### 4. Agendamento com Cron

Finalmente, agende a execução deste script usando o cron do host Proxmox.

1.  Execute `crontab -e` como root.
2.  Adicione uma linha para agendar o backup. Fazer isso durante a madrugada é uma boa prática. O exemplo abaixo executa o script todos os dias às 3:30 da manhã.

    ```cron
    # Executa o script de sincronização de backup off-site para o GCS diariamente
    30 3 * * * /usr/local/sbin/sync_backups_to_gcs.sh
    ```

Com isso, você agora tem um sistema de backup off-site totalmente automatizado e criptografado. Seus dados mais críticos estão protegidos contra falhas de hardware e desastres locais, e você pode dormir um pouco mais tranquilo sabendo que sua vida digital tem uma apólice de seguro robusta na nuvem.

Para aprender a restaurar a partir desses backups em um cenário de desastre, consulte a seção [Reconstruindo a Infraestrutura a Partir do Zero](04-reconstruindo-infraestrutura.md).
