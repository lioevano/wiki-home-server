# Aprofundamento em ZFS

ZFS (Zettabyte File System) é muito mais do que um simples sistema de arquivos; é um **gerenciador de volumes lógicos e sistema de arquivos combinado**, conhecido por sua robustez, integridade de dados, escalabilidade e um conjunto impressionante de funcionalidades avançadas. No nosso servidor doméstico, o ZFS é a espinha dorsal do nosso armazenamento de dados no host Proxmox VE, com o pool `/data` (e seus datasets) hospedando os volumes NFS para nossos containers Docker, backups de VMs, e outros dados importantes.

O [Manual de Implementação](../01-manual-implementacao/02-proxmox-ve-host.md#22-configuração-do-pool-zfs-data-e-datasets) cobriu a criação básica de um pool espelhado e alguns datasets. Esta seção visa aprofundar seu conhecimento sobre o ZFS, explorando comandos mais avançados, conceitos de VDEVs, a poderosa replicação com `zfs send/recv`, e ferramentas úteis como `Sanoid/Syncoid`.

Para um guia prático sobre como usar snapshots ZFS no dia-a-dia, consulte também o [Guia Prático de Snapshots ZFS](../03-guias-sustentacao/12-guia-snapshots-zfs.md).

## 1. Comandos ZFS Essenciais e Avançados

Familiarize-se com estes comandos para gerenciar seus pools e datasets ZFS de forma eficaz a partir do shell do seu host Proxmox VE (geralmente como `root` ou usando `sudo`).

### Gerenciamento de Pools ZFS (`zpool` command)

O comando `zpool` é usado para gerenciar seus pools de armazenamento ZFS.

*   **Verificar o Status de Todos os Pools:**
    ```bash
    sudo zpool status
    ```
*   **Verificar o Status de um Pool Específico (e.g., `data`):**
    ```bash
    sudo zpool status data
    # Para uma saída mais verbosa, incluindo contagem de erros de checksum se houver:
    sudo zpool status -v data
    ```
    !!! tip "Monitore `zpool status` Regularmente!"
        A saída de `zpool status` é crucial. Ela informa se o pool está `ONLINE`, `DEGRADED` (um disco falhou em um VDEV redundante, mas o pool ainda funciona), `FAULTED` (pool inacessível, perda de dados provável se não houver redundância suficiente), ou se há erros de dados.
*   **Listar Pools ZFS Disponíveis no Sistema:**
    ```bash
    sudo zpool list
    # NAME    SIZE  ALLOC   FREE  CKPOINT  EXPANDSZ   FRAG    CAP  DEDUP    HEALTH  ALTROOT
    # data   464G   150G   314G        -         -     2%    32%   1.00x   ONLINE  -
    ```
*   **Ver o Histórico de Comandos Executados em um Pool:**
    Útil para rastrear quando pools foram criados, discos adicionados, scrubs iniciados, etc.
    ```bash
    sudo zpool history data
    ```
*   **Exibir Estatísticas de I/O para um Pool (em Tempo Real):**
    ```bash
    sudo zpool iostat data 1
    # Mostra operações de leitura/escrita, largura de banda e latência a cada 1 segundo. Ctrl+C para parar.
    # Use -v para ver estatísticas por VDEV/disco:
    sudo zpool iostat -v data 1
    ```
*   **Scrubbing (Verificação de Integridade de Dados):**
    Um "scrub" lê todos os dados em um pool ZFS e verifica sua integridade contra os checksums armazenados. Em pools redundantes (como nosso espelho `data`), o ZFS tentará corrigir automaticamente quaisquer erros encontrados.
    ```bash
    # Iniciar um scrub no pool 'data':
    sudo zpool scrub data

    # Verificar o progresso do scrub (veja a saída de 'zpool status'):
    sudo zpool status data
    # scan: scrub in progress since [data] ... X% done, XhXm to go

    # Parar um scrub em andamento (geralmente não necessário):
    # sudo zpool scrub -s data
    ```
    !!! important "Agende Scrubs Regulares!"
        É **altamente recomendado** realizar um scrub do seu pool ZFS periodicamente (e.g., **mensalmente**) para detectar e corrigir proativamente "bit rot" (corrupção silenciosa de dados) e outros problemas de integridade. Adicione ao `cron` do host Proxmox:
        `0 1 1 * * /sbin/zpool scrub data # Ex: Todo primeiro dia do mês às 01:00`
*   **Exportar um Pool ZFS (para mover discos para outro sistema ou desativar temporariamente):**
    Isso desmonta todos os datasets no pool e marca o pool como exportado, permitindo que ele seja importado em outro sistema ZFS.
    ```bash
    sudo zpool export data
    ```
*   **Importar um Pool ZFS (após conectar os discos a um sistema):**
    ```bash
    # Listar pools que podem ser importados (ZFS escaneia os discos conectados)
    sudo zpool import

    # Importar o pool 'data' se encontrado
    sudo zpool import data

    # Se o pool não foi exportado "limpamente" (e.g., devido a uma falha do sistema antigo),
    # você pode precisar forçar a importação. USE COM CUIDADO e apenas se souber o que está fazendo.
    # sudo zpool import -f data

    # Se estiver importando em um sistema diferente e os pontos de montagem antigos conflitarem:
    # sudo zpool import -R /novo/ponto_de_montagem_raiz data
    ```
*   **Substituindo um Disco Defeituoso em um VDEV Espelhado (Mirror):**
    Suponha que no seu pool `data` (que é um espelho de `hdd1_id` e `hdd2_id`), o disco `hdd1_id` falhou. O `zpool status data` mostrará `hdd1_id` como `FAULTED` ou `UNAVAIL` e o pool estará `DEGRADED`.
    1.  **Coloque o Disco Falho Offline (se o ZFS já não o fez):**
        ```bash
        sudo zpool offline data /dev/disk/by-id/ata-HDD1_MODEL_SERIAL_ID_FALHO
        ```
    2.  **Fisicamente Substitua o Disco Defeituoso:** Desligue o servidor, substitua o HDD defeituoso por um novo HDD de capacidade igual ou maior. Anote o ID persistente do novo disco (e.g., `/dev/disk/by-id/ata-HDD_NOVO_MODEL_SERIAL_ID`).
    3.  **Execute o Comando `zpool replace`:**
        ```bash
        # Sintaxe: zpool replace <pool> <dispositivo_antigo_ou_guid> <dispositivo_novo>
        sudo zpool replace data /dev/disk/by-id/ata-HDD1_MODEL_SERIAL_ID_FALHO /dev/disk/by-id/ata-HDD_NOVO_MODEL_SERIAL_ID
        # Se o disco antigo não estiver mais visível, você pode precisar usar o GUID numérico do disco
        # que aparece em 'zpool status -v'.
        ```
    4.  **Monitore o Processo de "Resilvering":** O ZFS começará a reconstruir os dados no novo disco a partir do disco saudável restante no espelho. Este processo é chamado de "resilvering".
        ```bash
        sudo zpool status data
        # scan: resilver in progress since [data] ... X% done, XhXm to go
        ```
        O tempo de resilvering depende do tamanho do pool e da velocidade dos discos. Durante o resilvering, o pool ainda está em estado `DEGRADED`, mas funcional. A performance pode ser reduzida. Se o disco restante também falhar *durante* o resilvering, você perderá o pool.

### Gerenciamento de Datasets e Volumes ZFS (`zfs` command)

O comando `zfs` é usado para gerenciar datasets (sistemas de arquivos), ZVOLs (volumes de bloco) e snapshots.

*   **Listar Datasets, ZVOLs e Snapshots:**
    ```bash
    sudo zfs list # Lista todos os datasets e ZVOLs com informações básicas (tamanho, usado, disponível, ponto de montagem)
    sudo zfs list -t filesystem # Mostra apenas datasets (sistemas de arquivos)
    sudo zfs list -t volume     # Mostra apenas ZVOLs (volumes de bloco)
    sudo zfs list -t snapshot   # Mostra apenas snapshots
    sudo zfs list -r data       # Lista recursivamente o pool 'data' e todos os seus datasets e snapshots filhos
    sudo zfs list -o name,mountpoint,compression,used,available,referenced,quota # Customiza colunas
    ```
*   **Criar um Novo Dataset (Sistema de Arquivos):**
    ```bash
    # Cria um novo dataset 'meu_app_data' dentro do dataset 'docker-volumes' do pool 'data'
    sudo zfs create data/docker-volumes/meu_app_data
    # Por padrão, ele herda propriedades do pai e é montado em /data/docker-volumes/meu_app_data
    ```
*   **Destruir um Dataset ou ZVOL (CUIDADO: APAGA OS DADOS IRREVERSIVELMENTE!):**
    ```bash
    sudo zfs destroy data/docker-volumes/dataset_para_deletar
    # Para destruir um dataset e TODOS os seus snapshots e clones filhos:
    sudo zfs destroy -r data/docker-volumes/dataset_para_deletar
    # Para destruir recursivamente, mas com uma etapa de confirmação para cada item:
    # sudo zfs destroy -R data/docker-volumes/dataset_para_deletar # -R pede confirmação
    ```
*   **Obter e Definir Propriedades de um Dataset/ZVOL:**
    ZFS tem muitas propriedades configuráveis por dataset.
    ```bash
    # Ver todas as propriedades de um dataset
    sudo zfs get all data/docker-volumes

    # Ver uma propriedade específica
    sudo zfs get compression data/docker-volumes

    # Definir uma propriedade
    sudo zfs set compression=lz4 data/docker-volumes # Habilita compressão lz4 (recomendado)
    sudo zfs set quota=100G data/media # Define uma cota de 100GB para o dataset 'media'
    sudo zfs set recordsize=1M data/media # Ex: define recordsize para 1MB (pode ser bom para arquivos de vídeo grandes)
                                        # Padrão é 128K. Alterar só afeta novos arquivos.
    sudo zfs set atime=off data/docker-volumes # Desabilita atualização de tempo de acesso (pode melhorar performance)

    # Herdar uma propriedade do dataset pai (remove a configuração local)
    sudo zfs inherit compression data/docker-volumes/meu_app_data
    ```
    Propriedades comuns incluem: `mountpoint`, `compression`, `dedup` (geralmente **NÃO recomendado** para homelabs devido ao alto uso de RAM e possíveis problemas de performance, a menos que você saiba exatamente o que está fazendo e tenha um caso de uso muito específico), `recordsize`, `atime`, `readonly`, `quota`, `reservation`, `logbias`, `sync`.
*   **Snapshots (Criar, Listar, Destruir, Rollback):**
    Consulte o [Guia Prático de Snapshots ZFS](../03-guias-sustentacao/12-guia-snapshots-zfs.md) para um detalhamento completo.
*   **Clones (Cópias Graváveis de Snapshots):**
    ```bash
    # Cria um clone gravável do snapshot 'data/docker-volumes@snap_estavel'
    # como um novo dataset 'data/docker-volumes_clone_para_teste'
    sudo zfs clone data/docker-volumes@snap_estavel data/docker-volumes_clone_para_teste
    ```
    O clone inicialmente compartilha todos os seus blocos com o snapshot de origem (copy-on-write).

## 2. Entendendo VDEVs ZFS (Virtual Devices)

Um pool ZFS é construído a partir de um ou mais **VDEVs (Virtual Devices)**. Cada VDEV, por sua vez, é composto por um ou mais dispositivos físicos (discos). A forma como os VDEVs são configurados determina a redundância, capacidade e, em parte, a performance do seu pool.

*   **Single Disk VDEV:**
    *   Um VDEV com um único disco.
    *   **Redundância: NENHUMA.** Se este disco falhar, o pool inteiro é perdido (a menos que seja um tipo de VDEV especial como cache ou log).
    *   Não recomendado para dados primários.
*   **Mirror VDEV (RAID 1):**
    *   O que usamos para nosso pool `data` (com 2 discos). Pode ter mais de 2 discos (e.g., espelho de 3 vias).
    *   Dados são escritos identicamente em todos os discos do espelho.
    *   **Capacidade:** A capacidade do menor disco no espelho.
    *   **Redundância:** Pode sobreviver à falha de N-1 discos (onde N é o número de discos no espelho). Para um espelho de 2 discos, pode perder 1 disco.
    *   **Performance de Leitura:** Pode ser melhorada, pois o ZFS pode ler de qualquer disco no espelho.
    *   **Performance de Escrita:** Similar à de um único disco no espelho.
    *   **Expansão:** Para expandir um pool de mirrors, você adiciona outro VDEV espelhado ao pool (e.g., mais 2 discos em espelho). Você não pode simplesmente adicionar um único disco a um VDEV mirror existente para aumentar sua capacidade.
*   **RAIDZ1 VDEV (Similar ao RAID 5):**
    *   Requer um mínimo de 3 discos. Distribui dados e um bloco de paridade entre os discos.
    *   **Capacidade:** (N-1) * (tamanho do menor disco).
    *   **Redundância:** Pode sobreviver à falha de 1 disco qualquer no VDEV.
    *   **Performance:** Geralmente boa para leituras sequenciais e escritas, mas escritas pequenas/aleatórias podem sofrer com o "read-modify-write" da paridade.
    *   **Resilvering (Reconstrução):** Pode ser lento e colocar estresse nos discos restantes.
*   **RAIDZ2 VDEV (Similar ao RAID 6):**
    *   Requer um mínimo de 4 discos (ou 3 se você realmente precisar, mas 4+ é mais comum). Usa paridade dupla.
    *   **Capacidade:** (N-2) * (tamanho do menor disco).
    *   **Redundância:** Pode sobreviver à falha de 2 discos quaisquer no VDEV. Significativamente mais seguro que RAIDZ1, especialmente com discos grandes.
*   **RAIDZ3 VDEV:**
    *   Requer um mínimo de 5 discos (ou 4 se precisar). Usa paridade tripla.
    *   **Capacidade:** (N-3) * (tamanho do menor disco).
    *   **Redundância:** Pode sobreviver à falha de 3 discos quaisquer no VDEV. Extremamente seguro.
*   **Stripe VDEV (RAID 0) - Agrupando Múltiplos VDEVs:**
    *   Um pool ZFS pode ser composto por múltiplos VDEVs que são "striped" juntos. Por exemplo, um pool pode ser um stripe de dois VDEVs espelhados (isso é efetivamente um RAID 10).
        `sudo zpool create meupool mirror c1t0d0 c1t1d0 mirror c2t0d0 c2t1d0`
    *   Se você adicionar VDEVs a um pool existente, eles são efetivamente stripados com os VDEVs existentes.
    *   **NÃO CRIE UM VDEV que seja ele mesmo um stripe de discos únicos** se você precisa de redundância. Um VDEV stripe de discos únicos não tem redundância; a falha de qualquer disco nesse VDEV resulta na perda do pool inteiro.
*   **VDEVs Especiais (para Performance):**
    *   **Log VDEV (SLOG - Separate Log Device):**
        *   Um disco rápido (geralmente um SSD pequeno e com alta resistência à escrita, como os de nível empresarial ou Optane) usado para armazenar o **ZIL (ZFS Intent Log)**.
        *   O ZIL é usado para armazenar temporariamente escritas **síncronas** antes que elas sejam confirmadas nos discos principais do pool. Isso melhora a latência e a consistência para aplicações que fazem muitas escritas síncronas (e.g., alguns bancos de dados, NFS com `sync=always`).
        *   **Para homelab:** Se a maioria das suas escritas são assíncronas (padrão para muitos datasets ZFS), ou se você usa `sync=disabled` ou `sync=standard` (padrão para datasets), o benefício de um SLOG pode ser mínimo e não justificar o custo/complexidade. Nossa exportação NFS usa `sync=standard` (implícito com `sync`), então um SLOG *poderia* ajudar, mas a RAM do host atuando como ARC e buffer para o ZIL é geralmente suficiente para cargas de trabalho de homelab.
        *   **Importante:** Um SLOG é para performance de escrita síncrona, **não para segurança de dados.** Se o SLOG falhar, você pode perder as últimas poucas transações síncronas que ainda não foram escritas no pool principal, mas o pool em si não será corrompido. Use um SLOG espelhado se a disponibilidade dessas últimas transações for crítica.
    *   **Cache VDEV (L2ARC - Level 2 Adaptive Replacement Cache):**
        *   Um disco rápido (SSD) usado como uma segunda camada de cache de leitura, após o ARC (que está na RAM).
        *   O ZFS move blocos de dados frequentemente acessados do ARC (RAM) para o L2ARC (SSD) para liberar espaço no ARC para dados ainda mais "quentes". Se houver um L2ARC hit, a leitura é muito mais rápida do que ir aos HDDs.
        *   **Para homelab:**
            *   Pode ser útil se você tem um grande volume de dados "quentes" que não cabem no ARC (RAM), e um SSD rápido disponível.
            *   **Cuidado:** Adicionar um L2ARC consome RAM do ARC para seus próprios metadados. Se você não tem muita RAM para o ARC em primeiro lugar (como no nosso caso com 48GB total, onde uma boa parte vai para VMs), um L2ARC pode até *piorar* a performance se roubar RAM preciosa do ARC.
            *   Geralmente, **mais RAM para o ARC é melhor do que um L2ARC**, a menos que você já tenha maximizado a RAM e ainda precise de mais cache de leitura.
    *   **Special Allocation Class VDEV (Metadata VDEV):**
        *   Um VDEV rápido (SSDs NVMe são ideais) dedicado a armazenar metadados ZFS e, opcionalmente, pequenos blocos de arquivos (configurável com `special_small_blocks`).
        *   Pode acelerar significativamente operações que são intensivas em metadados (e.g., `ls -l` em diretórios com milhões de arquivos, snapshots, `zfs send/recv`, algumas cargas de trabalho de banco de dados) em pools compostos principalmente por HDDs lentos.
        *   **Importante:** A perda de um Special VDEV é a **perda do pool inteiro**, então ele **DEVE ser redundante** (e.g., um espelho de dois SSDs NVMe).
        *   Para nosso homelab com um pool de dados relativamente pequeno (500GB em HDDs) e poucas VMs, o benefício pode não justificar a complexidade e o custo de SSDs NVMe dedicados e espelhados para isso.

!!! tip "Escolhendo VDEVs para Homelab"
    *   Para simplicidade, resiliência e facilidade de expansão (adicionando outro par espelhado), **mirrors (RAID 1)** são uma excelente escolha para homelabs, como fizemos para nosso pool `/data`.
    *   Se você tiver mais discos (e.g., 4-6+), **RAIDZ2** oferece um bom equilíbrio entre capacidade utilizável e redundância (permitindo a falha de 2 discos). RAIDZ1 pode ser arriscado com discos grandes devido aos longos tempos de resilvering.
    *   SLOG e L2ARC são otimizações. Avalie cuidadosamente se sua carga de trabalho realmente se beneficiará deles antes de adicionar a complexidade. Mais RAM para o ARC é geralmente o primeiro lugar para investir.

## 3. Replicação ZFS com `zfs send` e `zfs recv`

Uma das funcionalidades mais poderosas e distintas do ZFS é sua capacidade de realizar **replicação eficiente e incremental baseada em snapshots** usando os comandos `zfs send` e `zfs recv`. Isso é a base para backups ZFS nativos e muito robustos.

*   **Como Funciona (Conceitualmente):**
    1.  Você tira um **snapshot** do seu dataset de origem (e.g., `data/docker-volumes@snap1`).
    2.  O comando `zfs send` serializa os dados contidos nesse snapshot (ou as diferenças entre dois snapshots) em um stream.
    3.  Este stream pode ser:
        *   Canalizado (`|`) diretamente para um comando `zfs recv` em outro pool ZFS no mesmo sistema.
        *   Canalizado através de SSH para um comando `zfs recv` em um host ZFS remoto.
        *   Salvo em um arquivo, transportado para outro local, e depois alimentado para `zfs recv`.
    4.  O comando `zfs recv` recebe o stream e recria o dataset e/ou aplica as mudanças incrementais no dataset de destino.
*   **Primeiro Envio (Backup Completo de um Snapshot):**
    ```bash
    # Exemplo: Enviar o snapshot 'data/docker-volumes@initial_backup'
    # para um novo dataset 'backup_pool/docker_volumes_replica' em outro pool no mesmo host.
    sudo zfs send data/docker-volumes@initial_backup | sudo zfs recv backup_pool/docker_volumes_replica

    # Exemplo: Enviar para um host remoto (chamado 'remote-backup-server')
    # que tem um pool chamado 'offsite_zfs_pool'.
    # Requer SSH configurado para login sem senha ou com chave para o usuário.
    sudo zfs send data/docker-volumes@initial_backup | \
      ssh usuario@remote-backup-server 'sudo zfs recv -Fdu offsite_zfs_pool/homelab_backups/docker_volumes'
    # Opções comuns para recv:
    # -F: Força um rollback do destino se necessário (CUIDADO).
    # -d: Descarta o nome do pool de origem do nome do dataset recebido.
    # -u: Não monta o dataset recebido após a conclusão.
    ```
*   **Envios Subsequentes (Backups Incrementais):**
    Após o primeiro envio completo, você só precisa enviar as diferenças entre o último snapshot enviado e um novo snapshot.
    1.  Tire um novo snapshot no dataset de origem: `sudo zfs snapshot data/docker-volumes@daily_update_20230816`.
    2.  Envie o incremento:
        ```bash
        # Sintaxe: zfs send -i @snapshot_antigo @snapshot_novo <dataset_origem>
        # Ou:      zfs send -I @snapshot_antigo @snapshot_novo <dataset_origem> (envia todos os intermediários)

        # Exemplo incremental para o mesmo host:
        sudo zfs send -i data/docker-volumes@initial_backup data/docker-volumes@daily_update_20230816 | \
          sudo zfs recv backup_pool/docker_volumes_replica

        # Exemplo incremental para host remoto:
        sudo zfs send -I data/docker-volumes@initial_backup data/docker-volumes@daily_update_20230816 | \
          ssh usuario@remote-backup-server 'sudo zfs recv -Fdu offsite_zfs_pool/homelab_backups/docker_volumes'
        ```
*   **Casos de Uso:**
    *   **Backups Locais para Outro Pool:** Faça backup de um pool NVMe rápido para um pool HDD de arquivamento maior e mais lento no mesmo sistema.
    *   **Backups para um Servidor de Backup ZFS Dedicado:** Se você tem um NAS com ZFS (TrueNAS, ou outro Proxmox configurado como servidor de backup), esta é a forma ideal de fazer backup.
    *   **Replicação Off-site:** Envie seus snapshots para um servidor ZFS em um local geograficamente diferente para proteção contra desastres.
*   **Vantagens:**
    *   **Extremamente Eficiente:** Apenas os blocos de dados alterados são enviados nos backups incrementais.
    *   **Consistente:** Baseado em snapshots atômicos.
    *   **Rápido:** Especialmente para incrementais.
    *   **Preserva Propriedades ZFS:** O dataset de destino pode herdar propriedades como compressão, snapshots, etc.

## 4. Sanoid e Syncoid: Ferramentas para Gerenciamento Automatizado de Snapshots e Replicação ZFS

Embora `zfs snapshot` e `zfs send/recv` sejam poderosos, automatizar um esquema robusto de snapshots e replicação pode envolver scripting complexo. **Sanoid** e **Syncoid** são ferramentas de terceiros (desenvolvidas por Jim Salter - jimsalter.com) que simplificam enormemente esses processos.

*   **Sanoid (`sanoid`):**
    *   **Propósito:** Uma ferramenta de política para gerenciamento automatizado de **snapshots ZFS**.
    *   **Como Funciona:** Você define em um arquivo de configuração simples (`/etc/sanoid/sanoid.conf`) para quais datasets você quer tirar snapshots, com que frequência (e.g., horários, diários, semanais, mensais), e por quanto tempo manter cada tipo de snapshot.
    *   Sanoid é então executado via `cron` (e.g., `sudo sanoid --cron`) para criar e podar (deletar) snapshots automaticamente de acordo com suas políticas.
    *   **Exemplo de Configuração (`sanoid.conf`):**
        ```ini
        [data/docker-volumes]
            use_template = production
            recursive = yes

        [data/media]
            use_template = home_media
            recursive = yes

        # --- TEMPLATES ---
        [template_production]
            frequently = 0 # Desabilita snapshots frequentes (a cada X minutos)
            hourly = 36  # Mantém 36 snapshots horários
            daily = 30   # Mantém 30 snapshots diários
            monthly = 3  # Mantém 3 snapshots mensais
            yearly = 0
            autosnap = yes # Habilita snapshots automáticos para este template
            autoprune = yes # Habilita poda automática

        [template_home_media]
            frequently = 0
            hourly = 0
            daily = 14
            monthly = 2
            yearly = 0
            autosnap = yes
            autoprune = yes
        ```
*   **Syncoid (`syncoid`):**
    *   **Propósito:** Uma ferramenta para simplificar a **replicação ZFS incremental** (usando `zfs send/recv` por baixo dos panos) entre pools ZFS no mesmo host ou entre hosts diferentes via SSH.
    *   **Como Funciona:** `syncoid` automatiza a lógica de encontrar os snapshots comuns entre a origem e o destino, calcular o incremento correto, e executar os comandos `zfs send/recv`.
    *   **Exemplo de Uso:**
        ```bash
        # Replicar recursivamente data/docker-volumes para backup_pool/docker-volumes_repl no mesmo host
        sudo syncoid --recursive data/docker-volumes backup_pool/docker-volumes_repl

        # Replicar para um host remoto via SSH (para o usuário 'backupuser' no 'remoteserver')
        # --no-sync-snap: não cria um novo snapshot sincronizado na origem antes de enviar, usa os existentes
        # --sendoptions="w" : passa -w (raw send) para zfs send, útil se criptografado
        sudo syncoid --recursive --no-sync-snap data/docker-volumes backupuser@remoteserver:backup_zfs_pool/docker_volumes_prod_backup
        ```
    *   Pode ser agendado via `cron` para replicação regular (e.g., diária).
*   **Instalação:**
    Geralmente envolve clonar o repositório do Sanoid/Syncoid do GitHub, copiar os scripts para `/usr/local/sbin/` (ou similar), e criar os arquivos de configuração.
    ```bash
    # Exemplo de instalação (verifique a documentação oficial para os passos mais recentes)
    # sudo apt install pv lzop mbuffer # Dependências comuns
    # git clone https://github.com/jimsalterjrs/sanoid.git
    # cd sanoid
    # sudo cp sanoid syncoid /usr/local/sbin/
    # sudo chmod +x /usr/local/sbin/sanoid /usr/local/sbin/syncoid
    # sudo mkdir -p /etc/sanoid
    # sudo cp sanoid.conf.example /etc/sanoid/sanoid.conf
    # sudo cp sanoid.defaults.conf.example /etc/sanoid/sanoid.defaults.conf
    # (Edite /etc/sanoid/sanoid.conf conforme suas necessidades)
    ```
*   **Por que Usar Sanoid/Syncoid?**
    Eles simplificam drasticamente a implementação de uma estratégia de snapshots e replicação ZFS robusta e automatizada, que é muito superior a backups tradicionais baseados em arquivos para a proteção de datasets ZFS.

## 5. Monitorando a Saúde e Performance do ZFS

Manter um olho na saúde e performance do seu ZFS é crucial.

*   **Comandos Chave:**
    *   `sudo zpool status -v data`: Para verificar a saúde geral e erros.
    *   `sudo zpool iostat -v data 1`: Para I/O em tempo real.
*   **`arc_summary` (do pacote `zfsutils-linux` ou `zfs-zed` no Debian/Ubuntu):**
    Fornece um resumo detalhado das estatísticas do **ARC (Adaptive Replacement Cache)**, que é o cache de leitura principal do ZFS em RAM.
    ```bash
    sudo arc_summary
    ```
    Ajuda a entender se seu ARC está bem dimensionado (tamanho, hit rate) ou se está sofrendo muita pressão (evicções frequentes).
*   **`arcstat.py` ou `arcstat` (se disponível na sua distro ou via `zfs-tools`):**
    Mostra estatísticas do ARC em tempo real (hits, misses, tamanho, etc.).
*   **Node Exporter (`--collector.zfs`):**
    O Node Exporter que instalamos no nosso host Proxmox ([Seção 2.3 do Manual de Implementação](../01-manual-implementacao/02-proxmox-ve-host.md#instalação-do-node-exporter-host-proxmox-para-prometheus)) já está configurado para coletar uma variedade de métricas ZFS. Essas métricas podem ser visualizadas no Grafana usando dashboards apropriados (e.g., dashboards para ZFS ou Node Exporter que incluam seções ZFS).
    *   Métricas comuns incluem: saúde do pool, capacidade usada/livre, IOPS de leitura/escrita, largura de banda, ARC hits/misses, tamanho do ARC.
*   **`zfs-zed` (ZFS Event Daemon):**
    *   Um daemon que monitora eventos do kernel relacionados ao ZFS (como erros de disco, falhas de pool) e pode executar scripts em resposta a esses eventos (e.g., enviar uma notificação por email).
    *   Geralmente instalado como parte do pacote `zfsutils-linux` (ou `zfs-zed` separadamente).
    *   Verifique os scripts de configuração em `/etc/zfs/zed.d/` (e.g., `zed.rc` para configurar email).

## 6. Considerações de Performance do ZFS (Revisão e Adendos)

*   **RAM é o Rei para ZFS:** O ARC (cache de leitura em RAM) é crucial para a performance do ZFS. Quanto mais RAM o host Proxmox tiver disponível para o ARC (após a alocação para as VMs e para o próprio sistema operacional Proxmox), melhor será a performance de leitura, pois dados frequentemente acessados serão servidos diretamente da RAM.
    *   Com 48GB de RAM no host, há uma quantidade razoável para o ARC, mesmo com VMs consumindo uma boa parte. O ZFS tentará usar até ~50% da RAM total do sistema para o ARC por padrão, mas este limite é dinâmico e pode ser ajustado (via `zfs_arc_max` no `/etc/modprobe.d/zfs.conf`).
*   **`ashift=12` (ou `ashift=13` para discos 8K):**
    Já configuramos nosso pool `data` com `ashift=12` (para setores físicos de 4KB), o que é ideal para a maioria dos HDDs modernos "Advanced Format" e SSDs. Usar o `ashift` correto no momento da criação do pool é crucial para o alinhamento e a performance. Não pode ser alterado após a criação do pool (sem recriar o pool).
*   **`recordsize` (Tamanho do Bloco ZFS):**
    *   O tamanho do bloco padrão do ZFS para datasets é `128KB`.
    *   **Para datasets com arquivos predominantemente grandes** (e.g., nosso `data/media` com vídeos, `data/backups` com arquivos de backup de VMs), usar um `recordsize` maior (e.g., `1M` - 1 Megabyte) pode melhorar a performance de leitura/escrita sequencial e economizar um pouco de metadados.
        ```bash
        sudo zfs set recordsize=1M data/media
        sudo zfs set recordsize=1M data/backups
        ```
    *   **Para datasets com muitos arquivos pequenos ou acesso muito aleatório** (e.g., alguns tipos de bancos de dados, ou `data/docker-volumes` se contiver muitas pequenas configurações), o `recordsize` padrão de `128K` ou até um menor (e.g., `16K`, `32K` - mas teste cuidadosamente) pode ser mais apropriado. Mudar o `recordsize` de um dataset só afeta os **novos arquivos** escritos nele; arquivos existentes mantêm o `recordsize` com que foram criados.
    *   Para ZVOLs (usados como discos virtuais para VMs se não usar qcow2), o `volblocksize` (equivalente ao `recordsize`) também pode ser ajustado.
*   **Compressão (`compression=lz4`):**
    *   `lz4` é o algoritmo de compressão recomendado para ZFS na maioria dos casos. É extremamente rápido (baixo overhead de CPU) e oferece uma boa taxa de compressão para muitos tipos de dados (especialmente texto, logs, dados de configuração).
    *   **Habilitar em todos os datasets de dados é geralmente uma boa ideia:**
        ```bash
        sudo zfs set compression=lz4 data # Habilita no pool pai, para herança
        # Verifique se os datasets filhos herdaram ou defina explicitamente:
        sudo zfs set compression=lz4 data/docker-volumes
        sudo zfs set compression=lz4 data/media
        # ... e assim por diante
        ```
    *   A compressão pode, na verdade, **melhorar a performance de I/O**, pois menos dados precisam ser lidos/escritos fisicamente nos discos.
*   **`atime` (Access Time Updates):**
    *   Por padrão, muitos sistemas de arquivos (incluindo ZFS com `atime=on`) atualizam o timestamp de último acesso de um arquivo toda vez que ele é lido. Isso pode gerar muitas operações de escrita desnecessárias, especialmente para arquivos que são lidos frequentemente.
    *   **Desabilitar `atime` pode melhorar a performance:**
        ```bash
        sudo zfs set atime=off data # No pool pai, para herança
        # Verifique se os datasets filhos herdaram
        ```
        Nossas opções de montagem NFS (`noatime`, `nodiratime`) já lidam com isso do lado do cliente NFS para os compartilhamentos, mas definir no ZFS também é uma boa prática.
*   **`dedup` (Deduplicação):**
    *   A deduplicação ZFS pode, em teoria, economizar muito espaço se você tiver muitos blocos de dados idênticos em seu pool.
    *   !!! danger "Deduplicação ZFS: Use com Extrema Cautela (Provavelmente NÃO para Homelab)"
        A deduplicação no ZFS tem requisitos de **RAM muito altos** (para armazenar a Dedup Table - DDT). Se a DDT não couber na RAM (no ARC), a performance pode degradar **severamente** (conhecido como "DDT ZFS performance cliff").
        *   A remoção de dados deduplicados também pode ser lenta.
        *   Para a maioria dos homelabs, os riscos de performance e os requisitos de RAM **NÃO justificam o uso de `dedup`**. É melhor usar compressão e ter um bom esquema de snapshots/backups. **Não habilite `dedup` a menos que você tenha pesquisado extensivamente, entendido completamente as implicações, e tenha um caso de uso muito específico e RAM de sobra.**

ZFS é um sistema de arquivos incrivelmente capaz e profundo, com muitas opções de otimização e funcionalidades. Para um homelab, começar com as configurações padrão (com `ashift=12` e `compression=lz4`) e um bom esquema de snapshots (manual e/ou automatizado com `zfs-auto-snapshot` ou `sanoid`) já fornece uma base extremamente sólida e resiliente. Explorar `zfs send/recv` com `syncoid` para backups é onde o ZFS realmente mostra seu poder para proteção de dados robusta e eficiente.