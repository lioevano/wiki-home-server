# Compartilhando Recursos Entre VMs ou com a Rede Local

Em um ambiente de servidor doméstico, frequentemente surge a necessidade de compartilhar arquivos, bancos de dados ou outros recursos entre diferentes máquinas virtuais (VMs) ou entre VMs e outros dispositivos na sua rede local. Esta página explora algumas maneiras de fazer isso.

## 1. NFS (Network File System) - Já em Uso

Nossa arquitetura já utiliza extensivamente o NFS para compartilhar os datasets ZFS do host Proxmox com a `core-services-vm` e a `ai-desktop-vm` para os volumes Docker.

*   **Caso de Uso Principal:** Compartilhar grandes volumes de dados (configs Docker, mídia, downloads) do host Proxmox para as VMs Linux.
*   **Como Configurar um Novo Compartilhamento NFS do Host para uma Nova VM:**
    1.  **No Host Proxmox:**
        *   Crie um novo dataset ZFS se necessário: `sudo zfs create data/novo_compartilhamento`.
        *   Edite `/etc/exports` (idealmente via Ansible, atualizando o template `etc_exports.j2` no role `proxmox-host-config` e rodando o playbook):
            Adicione uma linha para o novo compartilhamento, permitindo acesso ao IP ou sub-rede da nova VM:
            ```
            /data/novo_compartilhamento IP_DA_NOVA_VM_OU_SUBNET(rw,sync,no_subtree_check,all_squash,anonuid={{ docker_puid }},anongid={{ docker_pgid }})
            ```
        *   Aplique as mudanças: `sudo exportfs -ra`.
    2.  **Na Nova VM:**
        *   Instale o cliente NFS: `sudo apt install nfs-common`.
        *   Crie um ponto de montagem: `sudo mkdir /mnt/novo_compartilhamento_nfs`.
        *   Adicione uma entrada ao `/etc/fstab` (idealmente via Ansible, no role `common` ou um role específico para a nova VM):
            ```
            IP_DO_PROXMOX_HOST:/data/novo_compartilhamento /mnt/novo_compartilhamento_nfs nfs rw,sync,hard,intr,bg,noatime,nodiratime,rsize=1048576,wsize=1048576,vers=4.2 0 0
            ```
        *   Monte: `sudo mount -a` ou reinicie a VM.
*   **Prós:** Bom para compartilhamento entre Linux, já integrado na nossa arquitetura.
*   **Contras:** Gerenciamento de permissões pode ser complexo (UID/GID mapping); menos amigável para clientes Windows nativamente.

## 2. Samba/CIFS (Para Compatibilidade com Windows e Outros Dispositivos)

Samba permite que um servidor Linux compartilhe arquivos e impressoras usando o protocolo SMB/CIFS, que é o padrão para compartilhamento de arquivos em redes Windows.

*   **Caso de Uso:**
    *   Compartilhar arquivos do seu servidor Proxmox (ou de uma VM Linux) com máquinas Windows na sua rede.
    *   Criar um "NAS virtual" simples.
    *   Compartilhar mídia com dispositivos que suportam SMB (e.g., alguns media players).
*   **Onde Instalar o Servidor Samba:**
    *   **No Host Proxmox:** Diretamente no host se você quer compartilhar dados do ZFS pool.
    *   **Em uma VM Dedicada "File Server":** Crie uma VM Linux, monte os datasets ZFS nela via NFS (ou dê a ela discos virtuais grandes), e instale o Samba nela. Isso isola o serviço Samba do host Proxmox.
*   **Configuração Básica do Servidor Samba (Exemplo na VM File Server):**
    1.  Instale Samba: `sudo apt install samba`.
    2.  Edite `/etc/samba/smb.conf`. Exemplo de um compartilhamento simples:
        ```ini
        [global]
           workgroup = WORKGROUP
           server string = Samba Server %v
           netbios name = meusamba
           security = user # Requer usuários Samba para acesso
           map to guest = bad user
           dns proxy = no

        [MeuCompartilhamentoPublico]
           comment = Compartilhamento Publico de Teste
           path = /srv/samba/publico # Crie este diretório
           browsable = yes
           writable = yes
           guest ok = yes # Permite acesso anônimo (convidado)
           read only = no
           # force user = someuser # Força arquivos a serem criados como 'someuser'

        [MeuCompartilhamentoPrivado]
           comment = Compartilhamento Privado
           path = /srv/samba/privado # Crie este diretório
           valid users = @smbgroup # Apenas usuários no grupo 'smbgroup'
           # ou valid users = usuario1, usuario2
           guest ok = no
           writable = yes
           browsable = yes
        ```
    3.  Crie os diretórios (e.g., `/srv/samba/publico`, `/srv/samba/privado`) e ajuste suas permissões.
    4.  Crie usuários Samba (eles devem ser usuários do sistema Linux primeiro):
        ```bash
        sudo useradd -M -s /sbin/nologin usuario_samba
        sudo smbpasswd -a usuario_samba # Define a senha Samba para o usuário
        # Crie grupos e adicione usuários se usar 'valid users = @smbgroup'
        # sudo groupadd smbgroup
        # sudo usermod -aG smbgroup usuario_samba
        ```
    5.  Reinicie o serviço Samba: `sudo systemctl restart smbd nmbd`.
    6.  Configure o firewall UFW na VM para permitir tráfego Samba (portas 137/udp, 138/udp, 139/tcp, 445/tcp).
*   **Acessando de Clientes:**
    *   **Windows:** `\\IP_DO_SERVIDOR_SAMBA\MeuCompartilhamentoPublico` no Explorer.
    *   **Linux:** `smbclient //IP_DO_SERVIDOR_SAMBA/MeuCompartilhamentoPublico -U guest` ou monte com `cifs-utils`.
    *   **macOS:** Finder -> Go -> Connect to Server -> `smb://IP_DO_SERVIDOR_SAMBA`.
*   **Prós:** Ótima compatibilidade com Windows e muitos dispositivos.
*   **Contras:** Configuração pode ser mais complexa que NFS; performance pode variar.

## 3. Pastas Compartilhadas VirtIO-FS (9P) - Host Proxmox para VM KVM

VirtIO-FS (baseado no protocolo 9P) é um sistema de arquivos compartilhado projetado para VMs KVM, permitindo compartilhar um diretório do host Proxmox diretamente com uma VM de forma mais eficiente que NFS para este caso de uso específico.

*   **Caso de Uso:** Compartilhamento de alta performance de um diretório específico do host Proxmox para uma única VM KVM.
*   **Configuração (Simplificada):**
    1.  **No Host Proxmox:** O diretório que você quer compartilhar deve existir (e.g., `/mnt/host_share_for_vm100`).
    2.  **Na Configuração da VM (via UI Proxmox ou `/etc/pve/qemu-server/VMID.conf`):**
        *   Você adiciona um "VirtIO FS" passthrough.
        *   Precisa especificar uma "tag" para o compartilhamento (e.g., `my_shared_folder_tag`) e o caminho no host.
        *   Exemplo em `VMID.conf`:
            `virtio1: /mnt/host_share_for_vm100,tag=my_shared_folder_tag`
            (O `virtio1` pode precisar ser um número diferente se você já tiver outros dispositivos VirtIO).
    3.  **Dentro da VM:**
        *   O kernel da VM precisa de suporte a 9P e VirtIO-FS (geralmente incluído em kernels Linux modernos).
        *   Monte o compartilhamento usando a tag:
            ```bash
            sudo mkdir /mnt/host_files
            sudo mount -t 9p -o trans=virtio,version=9p2000.L,msize=131072 my_shared_folder_tag /mnt/host_files
            # msize pode ser ajustado para performance.
            ```
        *   Adicione ao `/etc/fstab` para montagem automática:
            `my_shared_folder_tag /mnt/host_files 9p trans=virtio,version=9p2000.L,msize=131072,rw 0 0`
*   **Prós:** Potencialmente melhor performance que NFS para compartilhamento host-VM; mais simples que configurar um servidor NFS completo apenas para uma VM.
*   **Contras:** Específico para KVM no Proxmox; menos flexível que NFS para compartilhar com múltiplas VMs ou outros hosts.

## 4. Bancos de Dados Compartilhados

Se múltiplas aplicações (em diferentes VMs ou containers) precisam acessar o mesmo banco de dados.

*   **Estratégia:**
    1.  **VM Dedicada ao Banco de Dados (Recomendado):**
        *   Crie uma VM Linux (e.g., usando o template Ubuntu).
        *   Instale o servidor de banco de dados desejado (PostgreSQL, MariaDB/MySQL).
        *   Configure o servidor de banco de dados para escutar em seu endereço IP na VM (e.g., `0.0.0.0` ou o IP específico da VM, em vez de apenas `localhost`).
        *   Crie bancos de dados, usuários e senhas específicos para cada aplicação que irá acessá-lo. Conceda apenas as permissões necessárias para cada usuário.
        *   Configure o firewall UFW na VM do banco de dados para permitir conexões na porta do banco de dados (e.g., 5432 para PostgreSQL, 3306 para MySQL) apenas dos IPs das VMs/aplicações que precisam de acesso.
    2.  **Containers de Aplicação:**
        *   Configure os containers das suas aplicações para apontar para o IP da VM do banco de dados e a porta correta, usando as credenciais apropriadas.
*   **Exemplo: PostgreSQL em VM dedicada (e.g., `db-vm` com IP `192.168.1.20`)**
    *   Na `db-vm`, em `/etc/postgresql/VERSION/main/postgresql.conf`:
        `listen_addresses = '192.168.1.20,localhost'` (ou `'*'`)
    *   Na `db-vm`, em `/etc/postgresql/VERSION/main/pg_hba.conf`:
        Adicione linhas para permitir conexões das VMs das aplicações:
        `host    meu_db    app_user    IP_DA_VM_APP/32    scram-sha-256` (ou `md5`)
    *   No `docker-compose.yml` da sua aplicação na `core-services-vm`:
        ```yaml
        environment:
          - DB_HOST=192.168.1.20
          - DB_PORT=5432
          - DB_USER=app_user
          - DB_PASSWORD=senha_app_user
          - DB_NAME=meu_db
        ```
*   **Prós:** Centraliza o gerenciamento do banco de dados; pode ser mais eficiente para múltiplas aplicações.
*   **Contras:** Adiciona outra VM para gerenciar; a rede se torna o caminho de comunicação com o DB.

## 5. Sincronização de Arquivos (e.g., Syncthing, Nextcloud)

Em vez de montagens de rede diretas, você pode usar ferramentas de sincronização de arquivos.

*   **Syncthing:**
    *   **Propósito:** Sincronização P2P de arquivos entre múltiplos dispositivos/VMs.
    *   **Como:** Instale o Syncthing como um container Docker ou serviço nativo em cada VM/dispositivo que precisa compartilhar/sincronizar uma pasta. Configure os "Remotes" e as pastas a serem sincronizadas.
*   **Nextcloud:**
    *   **Propósito:** Seu Nextcloud (na `core-services-vm`) já é um hub central de arquivos.
    *   **Como:** Use os clientes de sincronização do Nextcloud nas suas VMs (se tiverem GUI) ou em outros dispositivos para manter pastas sincronizadas com o servidor Nextcloud.

Escolha o método de compartilhamento que melhor se adapta ao seu caso de uso, considerando a compatibilidade do cliente, requisitos de performance e complexidade de configuração.