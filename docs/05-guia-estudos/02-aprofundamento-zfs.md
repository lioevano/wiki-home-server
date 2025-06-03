# Aprofundamento em ZFS

ZFS é um sistema de arquivos e gerenciador de volumes lógicos extremamente poderoso e resiliente, sendo uma escolha popular para servidores domésticos e empresariais. O manual de implementação cobriu a criação básica de um pool espelhado e datasets. Esta seção explora comandos mais avançados, conceitos e ferramentas para tirar o máximo proveito do ZFS no seu host Proxmox.

## 1. Comandos ZFS Essenciais e Avançados

Familiarize-se com estes comandos para gerenciar seus pools e datasets ZFS a partir do shell do host Proxmox (como `root`).

### Gerenciamento de Pools (`zpool`)

*   **Status do Pool:**
    ```bash
    sudo zpool status # Status de todos os pools
    sudo zpool status data # Status do pool 'data'
    sudo zpool status -v data # Status verboso, incluindo erros de checksum se houver
    ```
*   **Listar Pools:**
    ```bash
    sudo zpool list
    ```
*   **Histórico de Comandos do Pool:**
    ```bash
    sudo zpool history data
    ```
*   **I/O Stats do Pool:**
    ```bash
    sudo zpool iostat data 1 # Mostra stats a cada 1 segundo
    ```
*   **Scrubbing (Verificação de Integridade):**
    ```bash
    sudo zpool scrub data # Inicia um scrub
    sudo zpool status data # Para ver o progresso do scrub
    sudo zpool scrub -s data # Para um scrub (se um estiver em andamento)
    ```
    !!! tip "Agende Scrubs Regulares"
        É crucial rodar `zpool scrub` periodicamente (e.g., mensalmente) para detectar e corrigir erros silenciosos de dados em pools redundantes.

*   **Exportar e Importar Pools (para mover discos para outro sistema):**
    ```bash
    sudo zpool export data # Desmonta e exporta o pool 'limpamente'
    # (Após mover os discos para o novo sistema)
    sudo zpool import # Lista pools importáveis
    sudo zpool import data # Importa o pool 'data'
    sudo zpool import -f data # Força a importação se não foi exportado limpamente (USE COM CUIDADO)
    ```
*   **Substituir um Disco Defeituoso em um Espelho:**
    Suponha que `/dev/disk/by-id/ata-HDD_VELHO_ID` no pool `data` (espelhado com `ata-HDD_BOM_ID`) falhou:
    1.  Coloque o disco offline (se ainda não estiver): `sudo zpool offline data ata-HDD_VELHO_ID`
    2.  Fisicamente substitua o disco defeituoso por um novo (de tamanho igual ou maior). Anote o ID do novo disco (`ata-HDD_NOVO_ID`).
    3.  Substitua o disco no pool:
        ```bash
        sudo zpool replace data ata-HDD_VELHO_ID ata-HDD_NOVO_ID
        ```
    4.  Monitore o processo de "resilvering" (reconstrução do espelho): `sudo zpool status data`. Isso pode levar tempo.

### Gerenciamento de Datasets e Volumes ZFS (`zfs`)

*   **Listar Datasets e Volumes:**
    ```bash
    sudo zfs list # Lista todos os datasets e ZVOLs
    sudo zfs list -t filesystem # Apenas datasets (sistemas de arquivos)
    sudo zfs list -t volume # Apenas ZVOLs (volumes de bloco, e.g., para discos de VM se não usar qcow2)
    sudo zfs list -t snapshot # Apenas snapshots
    sudo zfs list -r data # Lista o pool 'data' e todos os seus datasets recursivamente
    ```
*   **Criar um Dataset:**
    ```bash
    sudo zfs create data/meu_novo_dataset
    ```
*   **Destruir um Dataset (CUIDADO: APAGA DADOS IRREVERSIVELMENTE):**
    ```bash
    sudo zfs destroy data/meu_novo_dataset
    sudo zfs destroy -r data/meu_novo_dataset # Destrói o dataset e seus snapshots/clones filhos
    ```
*   **Obter/Definir Propriedades de um Dataset:**
    ```bash
    sudo zfs get all data/docker-volumes # Mostra todas as propriedades
    sudo zfs get compression data/docker-volumes # Mostra a propriedade de compressão
    sudo zfs set compression=lz4 data/docker-volumes # Habilita compressão lz4
    sudo zfs set quota=100G data/media # Define uma cota de 100GB para o dataset 'media'
    sudo zfs set recordsize=1M data/media # Exemplo: define recordsize para 1MB (pode ser bom para arquivos grandes de mídia)
    sudo zfs inherit compression data/docker-volumes # Remove a config local, herda do pai
    ```
    Propriedades comuns: `mountpoint`, `compression`, `dedup` (geralmente não recomendado para homelab devido ao alto uso de RAM), `recordsize`, `atime`, `quota`, `reservation`.
*   **Snapshots:**
    ```bash
    sudo zfs snapshot data/docker-volumes@antes_da_atualizacao
    sudo zfs list -t snapshot # Listar snapshots
    sudo zfs destroy data/docker-volumes@snapshot_antigo # Destruir um snapshot
    sudo zfs rollback data/docker-volumes@antes_da_atualizacao # REVERTE o dataset para o estado do snapshot (PERDE MUDANÇAS POSTERIORES)
    ```
    Para acessar arquivos de um snapshot sem rollback, navegue para o diretório `.zfs/snapshot/NOME_DO_SNAPSHOT` dentro do ponto de montagem do dataset.
*   **Clones (Cópias Graváveis de Snapshots):**
    ```bash
    sudo zfs clone data/docker-volumes@meu_snapshot data/docker-volumes-clone
    ```
    O clone inicialmente compartilha blocos com o snapshot, economizando espaço.

## 2. Tipos de VDEVs ZFS (Virtual Devices)

Um pool ZFS é construído a partir de um ou mais VDEVs. Cada VDEV fornece um certo nível de redundância ou performance.

*   **Single Disk:** Um VDEV com um único disco. **Sem redundância.** Se o disco falhar, o pool é perdido. Não recomendado para dados importantes.
*   **Mirror (RAID 1):** O que usamos para nosso pool `data`. Mínimo de 2 discos. Os dados são escritos em todos os discos do espelho.
    *   **Capacidade:** A do menor disco no espelho.
    *   **Redundância:** Pode sobreviver à falha de N-1 discos (onde N é o número de discos no espelho). Para um espelho de 2 discos, pode perder 1.
    *   **Performance de Leitura:** Pode ser melhorada lendo de múltiplos discos simultaneamente.
    *   **Performance de Escrita:** Similar à de um único disco.
*   **RAIDZ1 (Similar ao RAID 5):** Mínimo de 3 discos. Distribui dados e um bloco de paridade entre os discos.
    *   **Capacidade:** (N-1) * tamanho do menor disco.
    *   **Redundância:** Pode sobreviver à falha de 1 disco.
    *   **Performance:** Geralmente boa, mas a reconstrução (resilvering) pode ser lenta e estressante para os discos restantes ("RAID 5 write hole" é menos preocupante com CoW do ZFS, mas a performance de escrita degradada durante resilvering é real).
*   **RAIDZ2 (Similar ao RAID 6):** Mínimo de 4 discos. Usa paridade dupla.
    *   **Capacidade:** (N-2) * tamanho do menor disco.
    *   **Redundância:** Pode sobreviver à falha de 2 discos. Mais seguro que RAIDZ1.
*   **RAIDZ3:** Mínimo de 5 discos. Paridade tripla.
    *   **Capacidade:** (N-3) * tamanho do menor disco.
    *   **Redundância:** Pode sobreviver à falha de 3 discos. Muito seguro.
*   **Stripe (RAID 0):** Múltiplos discos ou VDEVs combinados para aumentar a capacidade e (potencialmente) a performance. **Sem redundância.** Se qualquer disco/VDEV no stripe falhar, o pool inteiro é perdido. **NÃO USE PARA DADOS IMPORTANTES SEM OUTRA FORMA DE REDUNDÂNCIA.**
    *   Você pode criar um stripe de mirrors (RAID 10): `zpool create meupool mirror /dev/sda /dev/sdb mirror /dev/sdc /dev/sdd`.
*   **Special VDEV:** Um VDEV rápido (geralmente SSDs NVMe) usado para armazenar metadados e, opcionalmente, pequenos blocos de arquivos. Pode acelerar significativamente operações dependentes de metadados (listagem de diretórios, snapshots) em pools de HDDs lentos.
*   **Log VDEV (SLOG - Separate Log Device):** Um VDEV rápido (SSD) usado para armazenar o ZFS Intent Log (ZIL). Ajuda a acelerar escritas síncronas. Para a maioria dos homelabs com `sync=disabled` ou `sync=standard` nos datasets, o benefício pode não justificar o custo/complexidade, a menos que você tenha cargas de trabalho muito específicas (e.g., DBs com muitas escritas síncronas). Nosso NFS export usa `sync=standard` (ou `sync` no exemplo), então um SLOG *poderia* ajudar, mas a RAM do host atuando como ARC e ZIL buffer é geralmente suficiente.

!!! tip "Escolhendo VDEVs"
    Para homelabs, **mirrors** são frequentemente uma boa escolha pela simplicidade de expansão (adicionar outro par espelhado) e reconstrução mais rápida. **RAIDZ1/2** pode ser mais eficiente em termos de espaço para um número maior de discos.

## 3. `zfs send` e `zfs recv` (Replicação ZFS)

Uma das features mais poderosas do ZFS é a capacidade de enviar snapshots incrementais (ou completos) de um dataset para outro local (outro pool no mesmo host, ou outro host ZFS na rede). Isso é a base para backups ZFS nativos e eficientes.

*   **Como Funciona:**
    1.  Tire um snapshot do dataset de origem: `sudo zfs snapshot data/meudataset@snap1`.
    2.  **Primeiro Envio (Completo):**
        ```bash
        # Enviar para outro pool 'backup_pool' no mesmo host:
        sudo zfs send data/meudataset@snap1 | sudo zfs recv backup_pool/meudataset_backup

        # Enviar para outro host ZFS via SSH (host_remoto tem 'backup_pool'):
        sudo zfs send data/meudataset@snap1 | ssh usuario@host_remoto 'sudo zfs recv backup_pool/meudataset_backup'
        ```
    3.  Tire um segundo snapshot no dataset de origem: `sudo zfs snapshot data/meudataset@snap2`.
    4.  **Envio Incremental (Apenas diferenças entre snap1 e snap2):**
        ```bash
        # Para o mesmo host:
        sudo zfs send -i data/meudataset@snap1 data/meudataset@snap2 | sudo zfs recv backup_pool/meudataset_backup

        # Para host remoto:
        sudo zfs send -i @snap1 @snap2 data/meudataset | ssh usuario@host_remoto 'sudo zfs recv backup_pool/meudataset_backup'
        # (A sintaxe de -i com nome de snapshot curto só funciona se o destino já existir e tiver o snapshot base)
        # Forma mais robusta para incremental:
        # sudo zfs send -I data/meudataset@snap1 data/meudataset@snap2 | ssh usuario@host_remoto 'sudo zfs recv -Fdu backup_pool/meudataset_backup'
        # -I: envia todos os snapshots intermediários
        # -Fdu no recv: força rollback se necessário, -d descarta o prefixo do pool de origem, -u não monta o dataset recebido
        ```
*   **Casos de Uso:**
    *   Backups para outro pool ZFS no mesmo sistema (e.g., de um pool NVMe rápido para um pool HDD lento de arquivamento).
    *   Backups para um servidor de backup ZFS dedicado (como um NAS com ZFS ou outro Proxmox).
    *   Replicação off-site.
*   **Ferramentas de Automação:** Ferramentas como `Sanoid` (para gerenciamento de snapshots) e `Syncoid` (para replicação baseada em `zfs send/recv`) simplificam muito a automação desses processos.

## 4. Sanoid e Syncoid (Gerenciamento de Snapshots e Replicação)

*   **Sanoid:** Uma ferramenta de política para gerenciamento de snapshots ZFS. Você define em um arquivo de configuração com que frequência tirar snapshots e por quanto tempo mantê-los (e.g., manter snapshots horários por 24h, diários por 30d, mensais por 1 ano).
    *   Roda via cron.
*   **Syncoid:** Uma ferramenta para simplificar a replicação ZFS (`zfs send/recv`) entre hosts ou pools. Ele pode lidar com a criação de snapshots intermediários e garantir uma replicação consistente.
    *   Exemplo: `syncoid data/meudataset usuario@host_remoto:backup_pool/meudataset_backup --recursive --skip-parent`
*   **Instalação e Configuração:** Envolve clonar o repositório do GitHub, copiar os scripts para `/usr/local/sbin/` e configurar `/etc/sanoid/sanoid.conf`.
*   **Por que Usar?** Simplificam drasticamente a automação de uma estratégia robusta de snapshots e replicação ZFS, que é muito superior a backups baseados em arquivos para datasets ZFS.

## 5. Monitorando a Saúde e Performance do ZFS

*   **`zpool status -v`**: Seu principal comando para verificar a saúde.
*   **`zpool iostat -v 1`**: Para ver IOPS, largura de banda, latência por disco/vdev.
*   **`arc_summary` (do pacote `zfsutils-linux` ou `zfs-zed`):** Mostra estatísticas detalhadas sobre o ARC (Adaptive Replacement Cache - cache de RAM do ZFS).
    ```bash
    sudo arc_summary
    ```
    Ajuda a entender se seu ARC está bem dimensionado ou se está sofrendo muita pressão.
*   **`arcstat.py` ou `arcstat` (se disponível):** Mostra estatísticas do ARC em tempo real.
*   **Node Exporter (`--collector.zfs`):** O Node Exporter que instalamos no host Proxmox coleta métricas ZFS que podem ser visualizadas no Grafana (e.g., saúde do pool, uso de capacidade, ARC hits/misses).
*   **`zfs-zed` (ZFS Event Daemon):** Um daemon que pode monitorar eventos do ZFS (como erros de disco) e executar ações (e.g., enviar um email). Geralmente instalado com `zfsutils-linux`. Verifique `/etc/zfs/zed.d/` para scripts de notificação.

## 6. Considerações de Performance do ZFS

*   **RAM é Rei:** ZFS ama RAM, especialmente para o ARC. Quanto mais RAM o host Proxmox tiver disponível para o ARC (após alocação para VMs e o próprio PVE), melhor será a performance de leitura, pois dados frequentemente acessados serão servidos da RAM.
    *   Com 16GB no total, o ARC no host será limitado.
*   **`ashift=12`:** Já configuramos nosso pool com `ashift=12` (para setores de 4K), o que é bom para HDDs modernos.
*   **`recordsize`:**
    *   O tamanho do bloco padrão do ZFS é 128KB.
    *   Para datasets com arquivos grandes (e.g., `data/media`, backups de VMs), um `recordsize` maior (e.g., 1MB) pode melhorar a performance de leitura/escrita sequencial e economizar um pouco de metadados.
    *   Para datasets com muitos arquivos pequenos ou acesso aleatório (e.g., alguns bancos de dados, `data/docker-volumes` se muitas configs pequenas), o `recordsize` padrão ou um menor pode ser melhor. Mudar o `recordsize` só afeta novos arquivos escritos.
*   **Compressão (`compression=lz4`):** `lz4` é o algoritmo de compressão recomendado para ZFS. É muito rápido e geralmente tem um impacto positivo na performance (menos dados para ler/escrever no disco) com baixo overhead de CPU. Vale a pena habilitar em todos os datasets de dados.
*   **`atime` (Access Time Updates):**
    *   Por padrão, `atime=on` atualiza o timestamp de acesso de um arquivo toda vez que ele é lido. Isso pode gerar muitas escritas desnecessárias.
    *   Definir `sudo zfs set atime=off data` (no pool pai, para herança) pode melhorar a performance, especialmente em cargas de trabalho com muita leitura. O NFS também tem opções (`noatime`, `nodiratime`) que configuramos no cliente.

ZFS é um sistema de arquivos profundo com muitas opções de tunning. Para a maioria dos homelabs, as configurações padrão com `ashift=12` e `compression=lz4` são um ótimo ponto de partida. A exploração de `zfs send/recv` com `sanoid/syncoid` para backups é onde o ZFS realmente brilha para proteção de dados.