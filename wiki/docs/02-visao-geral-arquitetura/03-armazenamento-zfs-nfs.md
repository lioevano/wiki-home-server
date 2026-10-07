# Estratégia de Armazenamento com ZFS e NFS

Uma estratégia de armazenamento robusta e resiliente é vital para a segurança e disponibilidade dos dados do seu servidor doméstico. Nesta arquitetura, utilizamos o ZFS no host Proxmox para gerenciamento avançado de discos e o NFS para compartilhar esse armazenamento com as máquinas virtuais.

## ZFS (Zettabyte File System) no Host Proxmox

ZFS é mais do que apenas um sistema de arquivos; é também um gerenciador de volumes lógicos. Ele oferece inúmeras vantagens para um ambiente de servidor:

*   **Integridade de Dados:** ZFS usa checksums para todos os dados e metadados, detectando e corrigindo automaticamente "bit rot" (corrupção silenciosa de dados) em configurações redundantes (como nosso espelho).
*   **Snapshots e Clones:**
    *   **Snapshots:** São cópias point-in-time altamente eficientes (copy-on-write) de um dataset ou volume. Permitem reverter rapidamente para um estado anterior ou acessar arquivos de um ponto específico no tempo. São a base para backups eficientes.
    *   **Clones:** Um clone é uma cópia gravável de um snapshot.
*   **RAID por Software (ZRAID):** ZFS implementa níveis de RAID em software, eliminando a necessidade de controladoras RAID de hardware caras. Nesta arquitetura, usamos:
    *   **Espelhamento (RAID 1):** O pool `/data` é criado com dois HDDs de 500GB em espelho. Se um disco falhar, os dados permanecem acessíveis no outro disco. A capacidade útil é a de um único disco (500GB).
*   **Compressão:** ZFS pode comprimir dados em tempo real (e.g., com `lz4`, que é rápido e eficiente), economizando espaço em disco com impacto mínimo na performance. Pode ser habilitado por dataset.
*   **Copy-on-Write (CoW):** Dados nunca são sobrescritos no lugar. Novas escritas são feitas em blocos livres, e os metadados são atualizados. Isso melhora a consistência em caso de falha de energia e é fundamental para snapshots eficientes.
*   **Datasets:** Permitem particionar um pool ZFS em múltiplos sistemas de arquivos independentes, cada um com suas próprias propriedades (compressão, cotas, snapshots, pontos de montagem, etc.).

### Pool `/data` e Seus Datasets

No host Proxmox, criamos um pool ZFS chamado `data` usando os dois HDDs de 500GB. Dentro deste pool, organizamos os dados com os seguintes datasets principais:

*   `data/docker-volumes`: Armazena os dados persistentes de configuração e aplicação dos containers Docker. É o mais crítico para as operações dos serviços.
*   `data/media`: Contém seus arquivos de mídia (filmes, séries, músicas).
*   `data/downloads`: Usado pelo cliente de torrent (qBittorrent) para armazenar downloads em andamento e concluídos antes de serem processados pelos *arrs.
*   `data/rag_sources`: (Se a `ai-desktop-vm` for usada) Para armazenar os modelos LLM do Ollama e as fontes de dados para aplicações RAG.
*   `data/backups`: Destino para backups de VMs do Proxmox e, potencialmente, dumps de bancos de dados das aplicações.

Estes datasets são montados automaticamente pelo ZFS no host Proxmox sob o diretório `/data` (e.g., `/data/docker-volumes`, `/data/media`).

## NFS (Network File System) para Compartilhamento com VMs

Enquanto o ZFS gerencia o armazenamento no host Proxmox, precisamos de uma forma de tornar esses dados acessíveis às máquinas virtuais onde os containers Docker rodarão. O NFS é usado para este propósito.

*   **Servidor NFS no Host Proxmox:**
    *   O pacote `nfs-kernel-server` é instalado no host Proxmox.
    *   O arquivo `/etc/exports` no host Proxmox define quais datasets ZFS são compartilhados, para quais clientes (as VMs) e com quais permissões.
    *   **Exemplo de entrada em `/etc/exports` (gerado por Ansible):**
        ```
        /data/docker-volumes 192.168.1.0/24(rw,sync,no_subtree_check,all_squash,anonuid=1000,anongid=1000)
        ```
        Isto compartilha o dataset `/data/docker-volumes` com qualquer cliente na sub-rede `192.168.1.0/24` com permissões de leitura/escrita (`rw`), modo síncrono (`sync`), e mapeia todos os acessos para o UID 1000 e GID 1000 no servidor (correspondendo ao `dockeruser:dockergroup` nas VMs).
*   **Cliente NFS nas VMs (`core-services-vm`, `ai-desktop-vm`):**
    *   O pacote `nfs-common` é instalado nas VMs.
    *   O Ansible configura o arquivo `/etc/fstab` em cada VM para montar automaticamente os compartilhamentos NFS do host Proxmox durante o boot.
    *   **Exemplo de montagem na VM:** O dataset `/data/docker-volumes` do host Proxmox é montado na VM em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}` (e.g., `/mnt/pve_data_zfs/docker-volumes`).

### Fluxo de Dados para Volumes Docker

Este diagrama ilustra como um volume Docker persistente é gerenciado:

```mermaid
graph TD
    subgraph "Host Proxmox VE (IP: {{ proxmox_host_ip_var }})"
        ZFS_Pool[ZFS Pool 'data' (HDDs RAID 1)] -->|Contém| ZFS_Dataset[Dataset 'data/docker-volumes']
        ZFS_Dataset -->|Montado em| Host_Mount_Point[/data/docker-volumes]
        Host_Mount_Point -->|Exportado via NFS| NFS_Server[Servidor NFS]
    end

    subgraph "VM: core-services-vm (IP: {{ core_services_vm_ip_var }})"
        NFS_Client[Cliente NFS] -->|Monta de {{ proxmox_host_ip_var }}:/data/docker-volumes| VM_Mount_Point[/mnt/pve_data_zfs/docker-volumes]
        Docker_Engine[Docker Engine] -->|Usa como source para volume| Container_Volume
        VM_Mount_Point --> Docker_Engine
    end

    subgraph "Container Docker (e.g., Nextcloud)"
        Container_Volume[Volume Docker: -v /mnt/pve_data_zfs/docker-volumes/nextcloud/config:/config] --> App_Config[/config dentro do container]
        App_Config <--> Nextcloud_App[Aplicação Nextcloud]
    end

    NFS_Server <-->|Rede Local| NFS_Client

    style ZFS_Pool fill:#e96900,color:#fff
    style VM_Mount_Point fill:#2496ed,color:#fff
```

1.  O container Docker (e.g., Nextcloud) é configurado para usar um volume mapeado para um caminho na VM (e.g., `/mnt/pve_data_zfs/docker-volumes/nextcloud/config`).
2.  Este caminho na VM é um ponto de montagem NFS que aponta para o dataset ZFS `/data/docker-volumes/nextcloud/config` (ou um subdiretório dele) no host Proxmox.
3.  Quando o container Nextcloud escreve em `/config`, os dados são enviados via NFS para o host Proxmox e escritos no pool ZFS.

## Considerações de Performance e Alternativas

*   **Performance do NFS:** NFS sobre uma rede Gigabit local geralmente oferece performance suficiente para a maioria das aplicações de homelab. Para cargas de trabalho muito intensivas em I/O (como bancos de dados muito ativos ou transcodificação de vídeo frequente), o NFS pode se tornar um gargalo.
    *   **Otimizações:** Usar `vers=4.2` (ou a versão mais alta suportada), ajustar `rsize` e `wsize` nas opções de montagem, e garantir uma rede estável pode ajudar.
    *   **Localização de Transcode:** Para Plex/Jellyfin, o diretório de transcodificação (`/transcode`) foi mapeado para um subdiretório em `docker-volumes`. Se a performance de transcodificação via NFS for um problema, alternativas incluem:
        *   Usar o armazenamento local da VM (no SSD NVMe) para transcodificação (e.g., mapear para `/tmp/transcode` na VM). Isso é mais rápido mas consome espaço no SSD da VM e os dados são perdidos se a VM for recriada sem esse diretório.
        *   Usar o `/tmp` do próprio container (que reside na RAM da VM, se houver RAM suficiente).
*   **Alternativas ao NFS para Compartilhamento com VMs:**
    *   **Discos Virtuais Adicionais:** Poderíamos criar discos virtuais (`.qcow2` ou raw) para cada VM diretamente no pool ZFS do host e formatá-los dentro da VM. Isso evita o NFS mas pode ser menos flexível para compartilhar o mesmo conjunto de dados entre múltiplas VMs (não é nosso caso aqui) ou para acessar os dados diretamente do host Proxmox.
    *   **ZFS Passthrough (para LXC):** Se usássemos containers LXC em vez de VMs KVM, poderíamos passar datasets ZFS diretamente para os LXCs de forma mais nativa (bind mounts).
    *   **VirtFS/9P:** Outro protocolo de compartilhamento de arquivos para VMs KVM, com diferentes características de performance e complexidade.

Para este guia, a combinação ZFS no host + NFS para as VMs oferece um bom equilíbrio entre resiliência de dados, flexibilidade de gerenciamento e simplicidade de configuração para os volumes Docker.