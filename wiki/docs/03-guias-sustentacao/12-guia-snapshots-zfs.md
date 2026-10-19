---
description: "Guia prático de snapshots ZFS: criar, listar, reverter, automatizar e usá-los antes de mudanças arriscadas."
---

# Guia Prático de Snapshots ZFS

Os snapshots ZFS são uma das funcionalidades mais poderosas e distintivas do ZFS, oferecendo uma maneira incrivelmente eficiente e rápida de capturar o estado de um dataset (seja um sistema de arquivos ZFS ou um ZVOL - ZFS Volume) em um ponto específico no tempo. Eles são uma ferramenta crucial para:

*   **Proteção contra Erros Humanos:** Deleção acidental de arquivos, modificações incorretas.
*   **Recuperação de Corrupção de Software:** Se uma atualização de software ou uma configuração errada corromper dados.
*   **Base para Estratégias de Backup Eficientes:** Especialmente para backups incrementais com `zfs send` e `zfs recv`.
*   **Testes e Rollbacks:** Permitem testar mudanças e reverter facilmente se algo der errado.

Este guia prático foca em como criar, listar, gerenciar e utilizar snapshots ZFS no seu **host Proxmox VE**, onde reside nosso pool ZFS principal `/data` e seus datasets (como `data/docker-volumes`, `data/media`, etc.).

## 1. O Que é (e o que NÃO é) um Snapshot ZFS?

*   **Cópia Point-in-Time Read-Only:** Um snapshot ZFS é uma imagem **somente leitura** do estado exato de um dataset no exato momento em que o snapshot é criado. Você não pode modificar diretamente o conteúdo de um snapshot existente.
*   **Extremamente Eficiente em Espaço (Inicialmente):**
    *   Graças ao mecanismo de **Copy-on-Write (CoW)** do ZFS, a criação de um snapshot é quase instantânea e, inicialmente, não consome quase nenhum espaço adicional no disco.
    *   Quando os dados no dataset ativo (o sistema de arquivos "ao vivo") são modificados ou deletados *após* a criação do snapshot, o ZFS preserva os blocos de dados originais que o snapshot referencia. As novas escritas vão para novos blocos no pool.
    *   O snapshot então "consome" espaço apenas para os blocos de dados que foram alterados ou deletados no dataset ativo desde a sua criação, mas que ele precisa manter para preservar o estado daquele ponto no tempo.
*   **NÃO é um Backup Completo (Isoladamente):**
    *   Embora sejam excelentes para recuperação rápida local e proteção contra muitos tipos de perda de dados, os snapshots ZFS residem no **mesmo pool ZFS** que os dados originais.
    *   Se o pool ZFS inteiro falhar (e.g., falha de múltiplos discos além da capacidade de redundância do seu RAIDZ ou espelho, ou uma falha catastrófica do controlador), os snapshots também serão perdidos.
    *   Portanto, snapshots devem ser *parte* de uma estratégia de backup mais ampla que inclua [cópias dos seus dados (e idealmente dos snapshots) para um pool ZFS diferente, um disco externo, ou um local off-site](../04-manutencao-recuperacao/02-backup-restore-estrategia.md).
*   **Base Fundamental para Replicação ZFS:** Snapshots são a unidade fundamental para usar os comandos `zfs send` e `zfs recv`, que permitem backups incrementais extremamente eficientes para outros pools ZFS ou outros hosts ZFS.

## 2. Comandos Essenciais para Gerenciamento de Snapshots ZFS

Execute estes comandos no **shell do seu host Proxmox VE**, como usuário `root` (ou usando `sudo`).

### Criando Snapshots

*   **Sintaxe Básica:**
    `zfs snapshot <pool_ou_dataset>/<filesystem_ou_volume>@<nome_do_snapshot>`
*   **Convenção de Nomenclatura para Snapshots:**
    *   Use nomes descritivos e consistentes. Incluir data e hora é uma prática comum.
    *   Ex: `@backup_diario_2023-08-15`, `@antes_upgrade_app_X`, `@config_estavel_v1`
*   **Exemplos Práticos:**
    *   Tirar um snapshot do dataset `docker-volumes` antes de uma grande atualização de containers:
        ```bash
        sudo zfs snapshot data/docker-volumes@pre_atualizacao_containers_20230815
        ```
    *   Tirar um snapshot do dataset `media` usando a data e hora atuais no nome:
        ```bash
        # Usando substituição de comando para gerar o nome do snapshot
        sudo zfs snapshot data/media@$(date +%Y-%m-%d_%H-%M-%S)
        # Isso criaria algo como: data/media@2023-08-15_14-30-00
        ```
    *   **Snapshot Recursivo (`-r`):**
        Esta opção é muito útil. Ela tira um snapshot de um dataset pai e, simultaneamente, de **todos os seus datasets filhos (aninhados)**, usando o mesmo nome de snapshot para todos.
        ```bash
        # Tira um snapshot de 'data/docker-volumes' e de quaisquer datasets filhos que ele possa ter
        # (e.g., se você tivesse data/docker-volumes/nextcloud_data como um dataset separado)
        sudo zfs snapshot -r data/docker-volumes@checkpoint_semanal

        # Tira um snapshot de TODO o pool 'data' e de TODOS os seus datasets
        # (docker-volumes, media, rag_sources, backups)
        sudo zfs snapshot -r data@backup_sistema_completo_20230815
        ```

### Listando Snapshots Existentes

*   **Sintaxe Principal:** `zfs list -t snapshot`
*   **Exemplos:**
    *   Listar **todos** os snapshots em todos os pools ZFS do sistema:
        ```bash
        sudo zfs list -t snapshot
        ```
    *   Listar snapshots apenas para o dataset `data/docker-volumes` (e seus filhos, se houver, devido ao comportamento padrão de `zfs list` para datasets):
        ```bash
        sudo zfs list -t snapshot -r data/docker-volumes
        # Para ver apenas os snapshots do dataset data/docker-volumes e não de seus filhos:
        # (Este comando pode não mostrar nada se não houver snapshots *diretamente* nesse dataset
        # sem também usar -r se os snapshots estiverem em filhos)
        # A forma mais precisa de listar snapshots de um dataset específico,
        # incluindo os de seus filhos se o snapshot foi feito recursivamente, é:
        # sudo zfs list -t snapshot | grep '^data/docker-volumes@' # Se snapshots não recursivos
        # sudo zfs list -t snapshot | grep 'data/docker-volumes.*@' # Se snapshots recursivos
        ```
        Uma forma mais simples e comum de ver todos os snapshots *relacionados* a um dataset é:
        ```bash
        sudo zfs list -r -t snapshot data/docker-volumes
        ```
    *   **Visualizar o Espaço Usado por Snapshots:**
        A saída de `zfs list -t snapshot` inclui colunas importantes:
        *   `NAME`: O nome completo do snapshot (e.g., `data/docker-volumes@snap1`).
        *   `USED`: O espaço em disco que está sendo consumido **exclusivamente** por este snapshot. São os blocos de dados que foram modificados ou deletados no dataset ativo desde que este snapshot foi criado, e que este snapshot (e possivelmente outros mais antigos) ainda precisa preservar.
        *   `REFER`: O tamanho dos dados que o snapshot referenciava no momento da sua criação (o tamanho do dataset naquele ponto no tempo).
        *   `MOUNTPOINT`: Snapshots não têm pontos de montagem diretos da mesma forma que datasets.
    *   **Ordenar Snapshots por Data de Criação:**
        ```bash
        sudo zfs list -r -t snapshot -o name,creation -S creation data/docker-volumes
        # -o name,creation: mostra apenas nome e data de criação
        # -S creation: ordena pela data de criação (maiúscula S para descendente, minúscula s para ascendente)
        ```

### Destruindo (Deletando) Snapshots

Quando um snapshot não é mais necessário (e.g., é muito antigo, ou você já fez um backup dele para outro local), você pode destruí-lo para liberar o espaço em disco que ele estava ocupando (os blocos de dados que ele estava exclusivamente preservando).

*   **Sintaxe:** `sudo zfs destroy <pool>/<dataset>@<nome_do_snapshot>`
*   **Exemplos:**
    *   Destruir um snapshot específico:
        ```bash
        sudo zfs destroy data/docker-volumes@snapshot_antigo_e_desnecessario
        ```
    *   **Destruir Recursivamente (`-r`):** Destruir um snapshot com o mesmo nome em um dataset pai e em todos os seus datasets filhos. Útil se você criou snapshots recursivos.
        ```bash
        sudo zfs destroy -r data/docker-volumes@checkpoint_semanal_obsoleto
        ```
    *   **Destruir Múltiplos Snapshots (e.g., um range ou por padrão):**
        ZFS não tem um comando nativo para destruir um range de snapshots diretamente por nome (e.g., `snap1%snap5`). Você precisaria listar e destruir individualmente ou usar scripting.
        *   **Para destruir todos os snapshots entre `snapA` e `snapB` (inclusive `snapA`, exclusivo `snapB`) em um dataset:**
            ```bash
            # Use com CUIDADO EXTREMO. TESTE COM 'echo' primeiro!
            # sudo zfs list -H -t snapshot -o name -S creation data/meudataset | \
            #   awk -v snapA="data/meudataset@snapA" -v snapB="data/meudataset@snapB" \
            #   '$0 == snapA {p=1} $0 == snapB {exit} p {print}' | \
            #   xargs -n 1 sudo zfs destroy -v
            ```
            Ferramentas como `zfs-destroy-snapshots.sh` (disponíveis online) ou scripts customizados são melhores para gerenciamento complexo de poda. `sanoid` (discutido abaixo) também lida com isso.
        *   **Destruir o snapshot mais antigo de um dataset:**
            ```bash
            # sudo zfs list -H -t snapshot -o name -s creation data/meudataset | head -n 1 | xargs sudo zfs destroy -v
            ```

    !!! danger "A Destruição de Snapshots é IRREVERSÍVEL!"
        Uma vez que um snapshot é destruído, os dados que eram exclusivamente referenciados por ele (e não por outros snapshots ou pelo dataset ativo) são marcados como espaço livre e serão eventualmente sobrescritos. **Não há lixeira.** Certifique-se de que você está destruindo o snapshot correto e que não precisa mais dos dados daquele ponto no tempo.

### Renomeando Snapshots

*   **Sintaxe:** `sudo zfs rename <pool>/<dataset>@<nome_antigo> <pool>/<dataset>@<nome_novo>`
*   **Recursivo (`-r`):** Para renomear snapshots com o mesmo nome antigo para o mesmo nome novo em datasets filhos também.
*   **Exemplo:**
    ```bash
    sudo zfs rename data/docker-volumes@temp_snap_123 data/docker-volumes@backup_importante_20230815
    ```

## 3. Utilizando Snapshots para Recuperação de Dados

A principal utilidade dos snapshots é a capacidade de recuperar dados ou reverter o estado de um sistema.

### Rollback de um Dataset Inteiro para um Snapshot

O comando `zfs rollback` reverte um dataset (sistema de arquivos) inteiro para o estado exato de um snapshot específico.

*   **Sintaxe:** `sudo zfs rollback [-rR] <pool>/<dataset>@<nome_do_snapshot>`
*   **Opções Importantes:**
    *   `-r`: **Destrói quaisquer snapshots que foram tirados *depois* do snapshot para o qual você está revertendo.**
    *   `-R`: Similar ao `-r`, mas também destrói quaisquer **clones** que foram criados a partir desses snapshots mais recentes.
*   **Exemplo:**
    Suponha que você fez uma alteração desastrosa no seu dataset `data/docker-volumes` e quer reverter para um estado anterior salvo no snapshot `data/docker-volumes@config_estavel_antes_da_mudanca`.
    ```bash
    # 1. (Opcional, mas Recomendado) Faça um NOVO snapshot do estado ATUAL antes do rollback,
    #    caso você se arrependa do rollback ou precise de algo do estado atual.
    sudo zfs snapshot data/docker-volumes@antes_do_rollback_para_config_estavel

    # 2. Verifique os snapshots existentes para confirmar o nome e a data do snapshot de destino.
    sudo zfs list -r -t snapshot -o name,creation -S creation data/docker-volumes

    # 3. Execute o rollback.
    #    CUIDADO: Este comando DESTRUIRÁ quaisquer snapshots feitos DEPOIS de '@config_estavel_antes_da_mudanca'
    #    (a menos que você omita -r e não haja snapshots posteriores).
    #    E, mais importante, todas as MUDANÇAS no dataset data/docker-volumes feitas DEPOIS
    #    daquele snapshot serão PERDIDAS e substituídas pelo conteúdo do snapshot.
    sudo zfs rollback -r data/docker-volumes@config_estavel_antes_da_mudanca
    ```
    !!! danger "Rollback é uma Operação Destrutiva para Mudanças Posteriores!"
        O `zfs rollback` é poderoso, mas **apaga irreversivelmente todas as alterações e snapshots feitos *após* o snapshot para o qual você está revertendo** (se a opção `-r` for usada, o que geralmente é necessário se existem snapshots posteriores). Use com extrema cautela e apenas se tiver certeza absoluta de que quer perder essas mudanças posteriores. Ter um snapshot do estado *imediatamente antes* do rollback (como no passo 1 do exemplo) é uma boa rede de segurança.

### Acessando e Recuperando Arquivos Individuais de um Snapshot (Método Seguro)

Esta é a maneira **mais segura e comum** de recuperar arquivos ou diretórios específicos de um snapshot, sem reverter o dataset inteiro.

*   **Como Funciona:** Para cada dataset ZFS que tem snapshots, o ZFS automaticamente torna os snapshots acessíveis através de um diretório oculto especial chamado `.zfs/snapshot/` localizado no ponto de montagem do dataset. Dentro deste diretório `.zfs/snapshot/`, cada snapshot aparece como um subdiretório somente leitura, contendo os arquivos como eles estavam no momento da criação daquele snapshot.
*   **Exemplo Prático:**
    Suponha que você deletou acidentalmente o arquivo `/data/docker-volumes/nextcloud/config/config.php` no seu dataset ativo.
    Felizmente, você tem um snapshot recente chamado `data/docker-volumes@backup_diario_20230815_0300`.

    1.  **Navegue até o diretório do snapshot dentro do ponto de montagem do dataset:**
        O dataset `data/docker-volumes` está montado em `/data/docker-volumes`.
        ```bash
        # No shell do host Proxmox
        cd /data/docker-volumes/.zfs/snapshot/backup_diario_20230815_0300/nextcloud/config/
        ```
    2.  **Liste os arquivos:**
        ```bash
        ls -l
        ```
        Você deve ver o arquivo `config.php` como ele existia no momento em que o snapshot `backup_diario_20230815_0300` foi tirado.
    3.  **Copie o arquivo de volta para o dataset ativo (o local original):**
        ```bash
        sudo cp config.php /data/docker-volumes/nextcloud/config/config.php
        ```
        Verifique as permissões do arquivo copiado e ajuste se necessário.
*   Este método é **não destrutivo** para o estado atual do seu dataset ativo; você está apenas copiando arquivos de uma versão "congelada" do passado.

### Clonando um Snapshot ZFS

Um clone ZFS cria um novo dataset **gravável** que inicialmente compartilha todos os seus blocos de dados com o snapshot de origem (usando copy-on-write). Alterações feitas no clone são escritas em novos blocos, não afetando o snapshot original nem o dataset de onde o snapshot veio.

*   **Sintaxe:** `sudo zfs clone <pool>/<dataset>@<snapshot_de_origem> <pool>/<novo_dataset_para_o_clone>`
*   **Exemplo:**
    ```bash
    # Criar um clone do estado de 'data/docker-volumes@config_estavel_antes_da_mudanca'
    # para um novo dataset chamado 'data/docker-volumes_teste_recuperacao'
    sudo zfs clone data/docker-volumes@config_estavel_antes_da_mudanca data/docker-volumes_teste_recuperacao
    ```
*   **Casos de Uso:**
    *   **Testar atualizações de software ou configurações arriscadas:** Crie um clone do seu dataset de produção, monte o clone, e realize os testes nele. Se algo der errado, você pode simplesmente destruir o clone sem afetar os dados originais.
    *   **Recuperação de dados granular:** Monte o clone, navegue pelos arquivos, copie o que precisa, e depois destrua o clone.
    *   **Provisionar ambientes de desenvolvimento/teste rapidamente.**
*   **Importante sobre Clones e Snapshots de Origem:**
    *   Um clone mantém uma dependência do seu snapshot de origem. Você **não pode destruir o snapshot de origem** enquanto um clone dele existir.
    *   Para tornar um clone um dataset independente (rompendo a dependência do snapshot de origem), você pode "promover" o clone usando `sudo zfs promote <pool>/<dataset_do_clone>`. Após a promoção, o dataset original (de onde o snapshot veio) se torna um clone do dataset promovido, e o snapshot original pode ser destruído se não houver outros dependentes. Isso é mais avançado e geralmente usado em cenários de failover ou divisão de datasets.

## 4. Automação de Snapshots ZFS com `zfs-auto-snapshot`

Manter snapshots manualmente é funcional para ações pontuais, mas para uma proteção contínua, a automação é essencial. O pacote `zfs-auto-snapshot` (geralmente incluído com `zfsutils-linux` no Debian/Ubuntu, ou disponível como um pacote separado) é uma forma simples de automatizar a criação e a poda (deleção) de snapshots.

*   **Como Funciona:**
    *   O pacote `zfs-auto-snapshot` instala scripts `cron` que rodam em intervalos predefinidos (e.g., a cada 15 minutos, hora, dia, semana, mês).
    *   Esses scripts automaticamente tiram snapshots de todos os seus datasets ZFS (a menos que um dataset seja explicitamente excluído) com nomes padronizados que incluem o intervalo e o timestamp (e.g., `...@zfs-auto-snap_hourly-2023-08-15-1400`).
    *   Os mesmos scripts também **podam (destroem) snapshots antigos** com base em uma política de retenção configurável (e.g., manter X snapshots horários mais recentes, Y diários, Z semanais, etc.).
*   **Configuração e Uso:**
    1.  **Verifique se está Instalado:**
        ```bash
        dpkg -l | grep zfs-auto-snapshot
        ```
        Se não estiver, instale: `sudo apt update && sudo apt install zfs-auto-snapshot`.
    2.  **Verifique os Scripts Cron:**
        Olhe em diretórios como `/etc/cron.hourly/`, `/etc/cron.daily/`, `/etc/cron.weekly/`, `/etc/cron.monthly/` por scripts chamados `zfs-auto-snapshot`.
    3.  **Configuração da Retenção (Pode Variar):**
        *   A política de retenção (quantos snapshots de cada tipo manter) pode ser definida de algumas maneiras, dependendo da versão/distribuição:
            *   Editando diretamente os scripts cron (e.g., `/etc/cron.daily/zfs-auto-snapshot`). Eles geralmente têm variáveis no topo para `HOURLY`, `DAILY`, `WEEKLY`, `MONTHLY` que definem quantos manter.
            *   Algumas instalações podem usar um arquivo de configuração central como `/etc/default/zfs-auto-snapshot` ou `/etc/conf.d/zfs-auto-snapshot`.
            *   Você também pode controlar a política por dataset usando propriedades ZFS, mas isso é menos comum para `zfs-auto-snapshot` e mais para `sanoid`.
        *   **Exemplo de Retenção (Comum):** Manter 24 snapshots horários, 7 diários, 4 semanais, e 3 mensais. Ajuste conforme suas necessidades de retenção e espaço em disco.
    4.  **Desabilitar Snapshots Automáticos para um Dataset Específico:**
        Se você tem um dataset para o qual não quer snapshots automáticos (e.g., um dataset de swap temporário, ou um dataset que já tem sua própria política de snapshot muito específica), você pode desabilitá-los:
        ```bash
        sudo zfs set com.sun:auto-snapshot=false data/meu_dataset_sem_auto_snap
        ```
        Para habilitar novamente (o padrão é `true` se a propriedade não estiver definida ou se for herdada):
        ```bash
        # Para herdar do pai (se o pai tiver auto-snapshot=true)
        sudo zfs inherit com.sun:auto-snapshot data/meu_dataset_sem_auto_snap
        # Ou para definir explicitamente como true
        # sudo zfs set com.sun:auto-snapshot=true data/meu_dataset_sem_auto_snap
        ```
    5.  **Verificando Snapshots Automáticos:**
        Use `sudo zfs list -t snapshot` e procure por snapshots com nomes como `...@zfs-auto-snap_daily-...`.

!!! tip "Considerando `sanoid` para Gerenciamento Avançado de Snapshots e Replicação"
    Para políticas de snapshot e retenção ainda mais granulares, considere a combinação [**Sanoid e Syncoid**](https://github.com/jimsalterjrs/sanoid).

## 5. Considerações Importantes ao Trabalhar com Snapshots

*   **Consumo de Espaço em Disco:**
    *   Snapshots consomem espaço em disco à medida que os dados no dataset ativo divergem do estado capturado pelo snapshot. Se você fizer muitas alterações ou deletar muitos dados, os snapshots mais antigos podem "segurar" uma quantidade significativa de espaço.
    *   **Monitore o espaço usado pelos snapshots regularmente:**
        ```bash
        sudo zfs list -r -t snapshot -o name,used,refer,creation -S used data
        # -S used: ordena pelo espaço 'USED' pelo snapshot, do maior para o menor
        ```
    *   Ajuste suas políticas de retenção de snapshots (seja do `zfs-auto-snapshot` ou `sanoid`) para equilibrar a profundidade do histórico de snapshots com o espaço em disco disponível no seu pool.
*   **Impacto na Performance (Mínimo para a Maioria dos Casos):**
    *   Tirar um snapshot é uma operação quase instantânea e tem impacto mínimo na performance.
    *   Ter um número *extremamente* grande de snapshots (muitos milhares) em um dataset pode, teoricamente, adicionar um pequeno overhead a algumas operações de metadados ZFS. No entanto, para a maioria dos homelabs e com políticas de retenção sensatas (e.g., algumas centenas de snapshots por dataset), isso raramente é um problema perceptível.
*   **Snapshots e Backups são Complementares, Não Substitutos:**
    *   Reafirmando: Snapshots são fantásticos para recuperação rápida local de erros ou deleções acidentais.
    *   Eles **NÃO** protegem contra falha física do pool ZFS inteiro (e.g., múltiplos discos falhando além da redundância, falha do controlador, desastre físico no local).
    *   **Sua estratégia de backup completa DEVE incluir a cópia dos seus dados importantes (e/ou dos snapshots ZFS via `zfs send`) para um local de armazenamento fisicamente separado (outro pool ZFS, um HD externo, um servidor de backup remoto, ou armazenamento em nuvem).**

Dominar os snapshots ZFS é uma habilidade valiosa que lhe dará uma grande confiança na integridade dos seus dados e na capacidade de se recuperar de imprevistos. Use-os de forma inteligente e como parte de uma estratégia de proteção de dados mais ampla!