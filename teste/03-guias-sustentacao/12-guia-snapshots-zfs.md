# Guia Prático de Snapshots ZFS

Snapshots ZFS são uma das funcionalidades mais poderosas e úteis do ZFS, oferecendo uma maneira incrivelmente eficiente de capturar o estado de um dataset (sistema de arquivos ou volume ZFS) em um ponto específico no tempo. Eles são cruciais para proteção contra erros humanos, corrupção de software e como base para estratégias de backup eficientes.

Este guia prático foca em como criar, listar, gerenciar e utilizar snapshots ZFS no seu host Proxmox, onde o pool `/data` e seus datasets residem.

## 1. O Que é um Snapshot ZFS?

*   **Cópia Point-in-Time Read-Only:** Um snapshot captura o estado exato de um dataset no momento em que é criado. Ele é read-only, significando que você não pode modificar diretamente o conteúdo de um snapshot.
*   **Eficiência de Espaço (Copy-on-Write):** Inicialmente, um snapshot não consome quase nenhum espaço adicional. ZFS usa um mecanismo de "copy-on-write" (CoW). Quando os dados no dataset ativo são modificados *após* a criação do snapshot, os blocos de dados originais (que o snapshot referencia) são preservados, e as novas escritas vão para novos blocos. O snapshot então "consome" espaço apenas para os blocos de dados que seriam sobrescritos ou deletados no dataset ativo, mas que ele precisa manter para preservar o estado daquele ponto no tempo.
*   **Não é um Backup Completo (Sozinho):** Embora excelentes para recuperação rápida e proteção local, snapshots residem no mesmo pool ZFS que os dados originais. Se o pool inteiro falhar (e.g., falha de múltiplos discos além da redundância do RAID), os snapshots também serão perdidos. Eles devem ser *parte* de uma estratégia de backup mais ampla que inclua [cópias off-pool e off-site](../04-manutencao-recuperacao/02-backup-restore-estrategia.md).
*   **Base para Replicação:** Snapshots são a base para o `zfs send` e `zfs recv`, permitindo backups incrementais eficientes para outros pools ou hosts.

## 2. Comandos Essenciais para Snapshots ZFS

Execute estes comandos no **shell do host Proxmox VE**, como `root`.

### Criando Snapshots

*   **Sintaxe Básica:** `sudo zfs snapshot <pool>/<dataset>@<nome_do_snapshot>`
*   **Exemplos:**
    *   Tirar um snapshot do dataset `docker-volumes`:
        ```bash
        sudo zfs snapshot data/docker-volumes@antes_da_atualizacao_portainer
        ```
    *   Tirar um snapshot do dataset `media` com data/hora no nome:
        ```bash
        sudo zfs snapshot data/media@$(date +%Y%m%d-%H%M%S)
        # Isso criaria algo como: data/media@20230815-143000
        ```
    *   **Snapshot Recursivo (`-r`):** Tirar um snapshot de um dataset pai e de todos os seus datasets filhos com o mesmo nome de snapshot.
        ```bash
        # Tira snapshot de 'data/docker-volumes' e todos os seus sub-datasets (se existirem)
        sudo zfs snapshot -r data/docker-volumes@backup_semanal
        # Tira snapshot de todo o pool 'data' e todos os seus datasets
        sudo zfs snapshot -r data@checkpoint_sistema_completo
        ```

### Listando Snapshots

*   **Sintaxe:** `sudo zfs list -t snapshot`
*   **Exemplos:**
    *   Listar todos os snapshots em todos os pools:
        ```bash
        sudo zfs list -t snapshot
        ```
    *   Listar snapshots apenas para o dataset `data/docker-volumes`:
        ```bash
        sudo zfs list -t snapshot -r data/docker-volumes
        # O -r aqui mostra snapshots do dataset especificado e seus filhos,
        # mas se você quer apenas os snapshots *desse* dataset:
        sudo zfs list -t snapshot data/docker-volumes
        ```
    *   Ver o espaço usado por snapshots (coluna `USED` e `REFER`):
        A coluna `USED` para um snapshot mostra o espaço que *apenas* aquele snapshot está segurando (blocos que foram modificados ou deletados no dataset ativo desde que o snapshot foi criado). A coluna `REFER` mostra o tamanho dos dados referenciados pelo snapshot, que é o tamanho do dataset no momento da criação do snapshot.

### Destruindo Snapshots

Quando um snapshot não é mais necessário, você pode destruí-lo para liberar o espaço que ele ocupa (os blocos de dados que ele estava preservando e que não são mais referenciados por outros snapshots ou pelo dataset ativo).

*   **Sintaxe:** `sudo zfs destroy <pool>/<dataset>@<nome_do_snapshot>`
*   **Exemplos:**
    *   Destruir um snapshot específico:
        ```bash
        sudo zfs destroy data/docker-volumes@snapshot_antigo_e_inutil
        ```
    *   **Destruir Recursivamente (`-r`):** Destruir um snapshot com o mesmo nome em um dataset pai e todos os seus datasets filhos.
        ```bash
        sudo zfs destroy -r data/docker-volumes@backup_semanal_obsoleto
        ```
    *   **Destruir um range de snapshots (requer ferramentas como `zfs-destroy-snapshots.sh` ou scripting):**
        ZFS não tem um comando nativo para destruir múltiplos snapshots por um padrão de nome ou data diretamente, mas você pode combinar `zfs list` com `xargs` ou um loop `for`.
        ```bash
        # Exemplo CUIDADOSO para destruir snapshots antigos de um dataset específico
        # (TESTE COM 'echo' PRIMEIRO!)
        # sudo zfs list -t snapshot -o name -S creation data/meudataset | grep 'data/meudataset@auto-' | tail -n +8 | xargs -n 1 sudo zfs destroy -v
        # Este exemplo manteria os 7 snapshots 'auto-' mais recentes e destruiria os mais antigos.
        ```
        !!! danger "Cuidado ao Destruir Snapshots"
            A destruição de um snapshot é **IRREVERSÍVEL**. Certifique-se de que você está destruindo o snapshot correto. Se um snapshot for a única referência a certos blocos de dados, esses dados serão perdidos.

### Renomeando Snapshots

*   **Sintaxe:** `sudo zfs rename <pool>/<dataset>@<nome_antigo> <pool>/<dataset>@<nome_novo>`
*   **Recursivo (`-r`):** Para renomear snapshots com o mesmo nome em datasets filhos também.
*   **Exemplo:**
    ```bash
    sudo zfs rename data/docker-volumes@snap_temp data/docker-volumes@snap_importante
    ```

## 3. Utilizando Snapshots para Recuperação

Snapshots são extremamente úteis para reverter alterações indesejadas ou recuperar arquivos.

### Rollback de um Dataset para um Snapshot

O comando `zfs rollback` reverte um dataset inteiro para o estado exato de um snapshot específico.

*   **Sintaxe:** `sudo zfs rollback [-rR] <pool>/<dataset>@<nome_do_snapshot>`
*   **Opções:**
    *   `-r`: Destrói quaisquer snapshots mais recentes que o snapshot para o qual você está revertendo.
    *   `-R`: Destrói quaisquer snapshots mais recentes e quaisquer clones baseados nesses snapshots mais recentes.
*   **Exemplo:**
    ```bash
    # Suponha que você fez uma alteração ruim no data/docker-volumes
    # e quer reverter para 'data/docker-volumes@antes_da_mudanca_ruim'

    # Primeiro, liste os snapshots para confirmar o nome e a ordem
    sudo zfs list -t snapshot -r data/docker-volumes -o name,creation -S creation

    # CUIDADO: Este comando DESTRUIRÁ quaisquer snapshots feitos DEPOIS de '@antes_da_mudanca_ruim'
    # E todas as MUDANÇAS no dataset data/docker-volumes feitas DEPOIS daquele snapshot serão PERDIDAS.
    sudo zfs rollback -r data/docker-volumes@antes_da_mudanca_ruim
    ```
    !!! danger "Rollback é Destrutivo para Mudanças Posteriores"
        O rollback apaga todas as alterações e snapshots feitos *após* o snapshot de destino. **Use com extrema cautela e apenas se tiver certeza.** Faça um novo snapshot *antes* de um rollback se quiser uma chance de reverter o rollback.

### Acessando Arquivos de um Snapshot (Sem Rollback)

Esta é a maneira mais segura de recuperar arquivos individuais ou diretórios de um snapshot.

*   **Como Funciona:** Para cada dataset ZFS, há um diretório oculto `.zfs/snapshot/` no seu ponto de montagem. Dentro dele, cada snapshot aparece como um diretório read-only.
*   **Exemplo:**
    Suponha que você deletou acidentalmente um arquivo importante em `/data/docker-volumes/meu_app/config.yml`.
    Você tem um snapshot chamado `data/docker-volumes@backup_diario_ontem`.

    1.  Navegue até o diretório do snapshot:
        ```bash
        cd /data/docker-volumes/.zfs/snapshot/backup_diario_ontem/meu_app/
        ```
    2.  Liste os arquivos. Você deve ver seu `config.yml` como ele estava quando o snapshot foi tirado.
    3.  Copie o arquivo de volta para o dataset ativo:
        ```bash
        sudo cp config.yml /data/docker-volumes/meu_app/config.yml
        ```
*   Este método é não destrutivo para o estado atual do seu dataset ativo.

### Clonando um Snapshot

Um clone cria um novo dataset gravável que inicialmente compartilha todos os seus blocos com o snapshot de origem. Alterações no clone são escritas em novos blocos (copy-on-write).

*   **Sintaxe:** `sudo zfs clone <pool>/<dataset>@<snapshot_origem> <pool>/<novo_dataset_clone>`
*   **Exemplo:**
    ```bash
    # Criar um clone do estado de docker-volumes para teste ou recuperação
    sudo zfs clone data/docker-volumes@snapshot_estavel data/docker-volumes-clone-teste
    ```
*   **Uso:**
    *   Testar atualizações ou mudanças em um ambiente isolado (o clone) sem afetar o dataset original.
    *   Montar o clone, recuperar dados e depois destruir o clone.
*   **Importante:** Um clone depende do seu snapshot de origem. Você não pode destruir o snapshot de origem enquanto um clone dele existir. Para "promover" um clone para ser independente, você pode usar `sudo zfs promote data/docker-volumes-clone-teste`.

## 4. Automação de Snapshots (`zfs-auto-snapshot`)

Manter snapshots manuais é tedioso. O pacote `zfs-auto-snapshot` (geralmente instalado com `zfsutils-linux` no Debian/Ubuntu ou disponível separadamente) automatiza a criação e poda de snapshots.

*   **Como Funciona:**
    *   Ele instala scripts cron (e.g., em `/etc/cron.hourly/`, `/etc/cron.daily/`, `/etc/cron.weekly/`, `/etc/cron.monthly/`).
    *   Esses scripts tiram snapshots de todos os seus datasets ZFS (ou dos especificados) com nomes padronizados (e.g., `...@zfs-auto-snap_hourly-YYYY-MM-DD-HHMM`).
    *   Os scripts também podam (destroem) snapshots antigos com base em uma política de retenção (e.g., manter X snapshots horários, Y diários, etc.).
*   **Configuração:**
    *   Verifique se está instalado: `dpkg -l | grep zfs-auto-snapshot`.
    *   A configuração padrão geralmente é razoável. Você pode customizar a frequência e a retenção editando os scripts cron ou, se disponível, um arquivo de configuração como `/etc/default/zfs-auto-snapshot`.
    *   Para desabilitar snapshots automáticos para um dataset específico:
        `sudo zfs set com.sun:auto-snapshot=false data/meu_dataset_temporario`
    *   Para habilitar novamente:
        `sudo zfs set com.sun:auto-snapshot=true data/meu_dataset_temporario`
*   **Verificando Snapshots Automáticos:**
    Use `sudo zfs list -t snapshot` para ver os snapshots criados automaticamente.

!!! tip "Sanoid para Gerenciamento Avançado de Snapshots"
    Para políticas de snapshot e retenção mais granulares e poderosas, e para fácil integração com replicação (usando `Syncoid`), considere a ferramenta [Sanoid](../05-guia-estudos/02-aprofundamento-zfs.md#4-sanoid-e-syncoid-gerenciamento-de-snapshots-e-replicação).

## 5. Considerações Importantes

*   **Espaço em Disco:** Snapshots consomem espaço. Monitore o espaço usado pelos snapshots (`sudo zfs list -t snapshot -o name,used,refer,creation`) e ajuste suas políticas de retenção para não ficar sem espaço no pool.
*   **Performance:** Tirar um snapshot é quase instantâneo. No entanto, ter um número *muito* grande de snapshots pode, em teoria, adicionar um pequeno overhead a algumas operações de metadados. Para homelabs, isso raramente é um problema com políticas de retenção sensatas.
*   **Snapshots e Backups:** Reafirmando, snapshots são ótimos para recuperação rápida local, mas não substituem backups em mídias separadas e off-site. Use `zfs send/recv` ou ferramentas como Borg para fazer backup dos seus datasets (incluindo seus snapshots) para outros locais.

Dominar os snapshots ZFS lhe dará uma grande confiança na integridade e recuperabilidade dos seus dados. Use-os sabiamente!
