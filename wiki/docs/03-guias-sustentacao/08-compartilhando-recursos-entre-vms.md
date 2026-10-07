# Compartilhando Recursos Entre VMs ou com a Rede Local

Em um ambiente de servidor doméstico, frequentemente surge a necessidade de compartilhar arquivos, bancos de dados ou outros recursos não apenas entre containers Docker dentro de uma mesma VM, mas também entre diferentes máquinas virtuais (VMs) ou entre suas VMs e outros dispositivos na sua rede local (como seu desktop, laptop ou media players).

Esta página explora algumas das abordagens mais comuns para realizar esse compartilhamento de recursos.

## 1. NFS (Network File System) - Já em Uso na Arquitetura

Nossa arquitetura já utiliza extensivamente o NFS. O host Proxmox VE atua como um servidor NFS, exportando os datasets ZFS (como `data/docker-volumes`, `data/media`, `data/downloads`) para a `core-services-vm` e a `ai-desktop-vm`. Essas VMs, por sua vez, atuam como clientes NFS, montando esses compartilhamentos para que os containers Docker possam usar os dados persistentes.

*   **Caso de Uso Principal na Arquitetura Atual:** Compartilhar grandes volumes de dados (configurações Docker, bibliotecas de mídia, downloads, modelos de IA) do host Proxmox para as VMs Linux que rodam os containers.
*   **Estendendo para Novas VMs ou Entre VMs:**
    Você pode usar o mesmo princípio para compartilhar dados entre VMs ou de uma VM para outra, ou do host Proxmox para uma nova VM.
    *   **Compartilhar de uma VM para Outra:**
        1.  **VM Servidora:** Instale `nfs-kernel-server` na VM que compartilhará os dados.
        2.  Crie o diretório a ser compartilhado (e.g., `/shared_data_from_vm1`).
        3.  Edite `/etc/exports` na VM servidora para exportar o diretório para o IP da VM cliente.
        4.  Inicie/reinicie o serviço `nfs-kernel-server` na VM servidora.
        5.  Configure o firewall UFW na VM servidora para permitir conexões NFS da VM cliente.
        6.  **VM Cliente:** Instale `nfs-common`, crie um ponto de montagem, e adicione a entrada ao `/etc/fstab` para montar o compartilhamento da VM servidora.
*   **Como Configurar um Novo Compartilhamento NFS do Host Proxmox para uma Nova VM (Exemplo):**
    1.  **No Host Proxmox (Servidor NFS):**
        *   **Crie um Novo Dataset ZFS (se for um novo conjunto de dados):**
            ```bash
            sudo zfs create data/novo_compartilhamento_para_vmX
            ```
        *   **Edite `/etc/exports` (Idealmente via Ansible):**
            Atualize o template `ansible/roles/infra/proxmox-host-config/templates/etc_exports.j2` e adicione uma nova linha para o compartilhamento. Suponha que a nova VM terá o IP `192.168.15.X`.
            ```exports
            # ... outros exports ...
            /data/novo_compartilhamento_para_vmX 192.168.15.X/32(rw,sync,no_subtree_check,all_squash,anonuid={{ docker_puid }},anongid={{ docker_pgid }})
            ```
            Se for para uma sub-rede inteira de novas VMs de teste, você pode usar o CIDR delas.
        *   **Aplique as Mudanças no Servidor NFS:**
            Execute o playbook `setup-proxmox-host.yml` para que o Ansible atualize `/etc/exports` e recarregue os exports NFS (ou manualmente `sudo exportfs -ra`).
    2.  **Na Nova VM (Cliente NFS):**
        *   **Instale o Cliente NFS:** O role `common` do Ansible já faz isso (`sudo apt install nfs-common`).
        *   **Crie um Ponto de Montagem:**
            ```bash
            sudo mkdir -p /mnt/host_proxmox/novo_compartilhamento
            ```
        *   **Adicione uma Entrada ao `/etc/fstab` (Idealmente via Ansible):**
            Se você tem um role Ansible que configura esta nova VM, adicione uma task de montagem similar à do role `common`.
            ```fstab
            # Exemplo de linha no /etc/fstab da nova VM
            {{ proxmox_host_ip_var }}:/data/novo_compartilhamento_para_vmX  /mnt/host_proxmox/novo_compartilhamento  nfs  rw,sync,hard,intr,bg,noatime,nodiratime,rsize=1048576,wsize=1048576,vers=4.2  0  0
            ```
        *   **Monte o Compartilhamento:**
            ```bash
            sudo mount -a # Monta tudo no fstab
            # Ou, para montar apenas este:
            # sudo mount {{ proxmox_host_ip_var }}:/data/novo_compartilhamento_para_vmX /mnt/host_proxmox/novo_compartilhamento
            ```
*   **Prós:**
    *   Bom para compartilhamento robusto de arquivos entre sistemas Linux.
    *   Já integrado em nossa arquitetura para os volumes Docker.
    *   Performance geralmente boa em redes locais gigabit.
*   **Contras:**
    *   Gerenciamento de permissões pode ser um pouco complexo devido ao mapeamento de UID/GID (embora o `all_squash` com `anonuid`/`anongid` simplifique para nosso caso de uso Docker).
    *   Menos amigável para acesso nativo por clientes Windows (requer o "Client for NFS" feature no Windows ou ferramentas de terceiros).

## 2. Samba/CIFS (Para Compatibilidade com Windows e Outros Dispositivos)

Samba permite que um servidor Linux compartilhe arquivos e impressoras usando o protocolo SMB/CIFS (Server Message Block / Common Internet File System), que é o padrão para compartilhamento de arquivos em redes Windows e amplamente suportado por macOS e outros dispositivos.

*   **Casos de Uso Comuns:**
    *   Compartilhar arquivos do seu servidor Proxmox (ou de uma VM Linux) com computadores Windows na sua rede local.
    *   Criar um "NAS virtual" simples para acesso fácil de múltiplos tipos de dispositivos.
    *   Compartilhar bibliotecas de mídia com dispositivos que suportam SMB (e.g., alguns media players, TVs).
    *   Backup de máquinas Windows para um compartilhamento no servidor.
*   **Onde Instalar o Servidor Samba:**
    *   **Opção A: Diretamente no Host Proxmox:**
        Se você quer compartilhar diretórios do seu pool ZFS `/data` diretamente.
        *   Pró: Acesso direto aos dados ZFS.
        *   Contra: Adiciona um serviço extra ao host Proxmox, o que alguns preferem evitar para manter o hypervisor o mais "limpo" possível.
    *   **Opção B: Em uma VM Linux Dedicada para "File Server" (Recomendado para Isolamento):**
        1.  Crie uma nova VM Linux (e.g., usando nosso template Ubuntu).
        2.  Monte os datasets ZFS desejados do host Proxmox nesta VM via NFS (como já fazemos para a `core-services-vm`).
        3.  Instale e configure o Samba servidor *dentro* desta VM "File Server".
        *   Pró: Isola o serviço Samba do host Proxmox. Mais flexível se você quiser dedicar recursos específicos para o Samba.
        *   Contra: Adiciona um pequeno overhead de uma VM e uma camada extra de NFS.
*   **Configuração Básica do Servidor Samba (Exemplo dentro de uma VM "File Server"):**
    1.  **Instale o Samba:**
        ```bash
        # Na VM que será o servidor Samba
        sudo apt update
        sudo apt install samba
        ```
    2.  **Crie os Diretórios a Serem Compartilhados:**
        Suponha que você montou um dataset NFS do Proxmox (e.g., `media`) em `/mnt/nfs_media_from_host` nesta VM.
        ```bash
        # Você pode compartilhar diretamente o ponto de montagem NFS ou subdiretórios dele.
        # Ou crie diretórios locais na VM se o storage for local à VM.
        # Exemplo: sudo mkdir -p /srv/samba/public_share /srv/samba/private_share
        ```
    3.  **Edite o Arquivo de Configuração do Samba (`/etc/samba/smb.conf`):**
        Faça um backup do original: `sudo cp /etc/samba/smb.conf /etc/samba/smb.conf.orig`.
        Exemplo de configuração:
        ```ini
        [global]
           workgroup = WORKGROUP # Ou o nome do seu grupo de trabalho Windows
           server string = %h server (Samba, Ubuntu)
           # netbios name = fileserver_vm # Opcional
           dns proxy = no
           log file = /var/log/samba/log.%m
           max log size = 1000
           panic action = /usr/share/samba/panic-action %d

           # Segurança - 'user' é geralmente recomendado.
           # Requer que os usuários se autentiquem com um usuário Samba.
           security = user
           # map to guest = bad user # Se 'security = user', o guest não funcionará facilmente

           # Restringir interfaces de rede (opcional, mas bom para segurança)
           # interfaces = lo eth0 192.168.15.0/24 # Substitua eth0 e o CIDR pela sua config de rede da VM
           # bind interfaces only = yes

        # --- Exemplo de Compartilhamento Público (Leitura para Convidados, Escrita para Usuário Específico) ---
        [PublicFiles]
           comment = Publicly Accessible Files
           path = /mnt/nfs_media_from_host/public_files # Exemplo: um subdiretório do seu montado NFS
           browsable = yes
           guest ok = yes # Permite acesso de convidado (sem senha)
           read only = yes # Convidados só podem ler
           # Se quiser permitir escrita para um usuário específico:
           # write list = nome_usuario_samba
           # force user = nome_usuario_linux_dono # Garante que arquivos criados tenham este proprietário
           # force group = nome_grupo_linux_dono

        # --- Exemplo de Compartilhamento Privado (Requer Autenticação) ---
        [PrivateShare-{{ ansible_user }}] # Exemplo: compartilhamento para o usuário Ansible
           comment = Private Files for {{ ansible_user }}
           path = /home/{{ ansible_user }}/samba_private # Diretório home do usuário ou outro local
           valid users = {{ ansible_user }} # Apenas este usuário pode acessar
           # Ou use @grupo para um grupo de usuários: valid users = @smb_users
           guest ok = no
           writable = yes
           browsable = yes
           create mask = 0664 # Permissões para novos arquivos
           directory mask = 0775 # Permissões para novos diretórios
        ```
    4.  **Crie os Diretórios e Ajuste Permissões:**
        Certifique-se de que os diretórios especificados em `path = ...` existem e que os usuários Linux correspondentes (ou o usuário `force user`) tenham as permissões corretas nesses diretórios.
    5.  **Crie Usuários Samba:**
        Os usuários Samba devem primeiro existir como usuários do sistema Linux na VM onde o Samba está rodando.
        ```bash
        # Exemplo: Criar um usuário Linux 'sambashareuser' (sem login shell, sem home dir se não precisar)
        # sudo useradd -M -s /usr/sbin/nologin sambashareuser
        # Se for usar o diretório home de um usuário existente como {{ vm_ansible_user_name }}:
        # O usuário Linux {{ vm_ansible_user_name }} já existe.

        # Adicione o usuário Linux ao banco de dados de senhas do Samba e defina uma senha Samba:
        sudo smbpasswd -a {{ vm_ansible_user_name }}
        # (Digite a senha para este usuário Samba quando solicitado)
        ```
    6.  **Teste a Configuração do Samba e Reinicie os Serviços:**
        ```bash
        testparm # Verifica a sintaxe do smb.conf
        sudo systemctl restart smbd.service nmbd.service
        sudo systemctl enable smbd.service nmbd.service
        ```
    7.  **Configure o Firewall UFW na VM Servidora Samba:**
        Permita o tráfego Samba:
        ```bash
        sudo ufw allow Samba # Ou permitir as portas específicas: 137/udp, 138/udp, 139/tcp, 445/tcp
        ```
*   **Acessando os Compartilhamentos Samba:**
    *   **Windows:** No Explorador de Arquivos, digite `\\IP_DA_VM_SAMBA\NomeDoCompartilhamento` (e.g., `\\192.168.15.X\PublicFiles`). Autentique se necessário.
    *   **Linux:**
        *   Linha de comando: `smbclient //IP_DA_VM_SAMBA/NomeDoCompartilhamento -U nome_usuario_samba`
        *   Montagem (requer `cifs-utils`): `sudo apt install cifs-utils`
          `sudo mkdir /mnt/meu_samba_share`
          `sudo mount -t cifs //IP_DA_VM_SAMBA/PrivateShare-{{ ansible_user }} /mnt/meu_samba_share -o username={{ ansible_user }},password=SUA_SENHA_SAMBA,uid=$(id -u),gid=$(id -g)`
          Para `/etc/fstab`:
          `//IP_DA_VM_SAMBA/PrivateShare-{{ ansible_user }} /mnt/meu_samba_share cifs username={{ ansible_user }},password=SUA_SENHA_SAMBA,uid=$(id -u),gid=$(id -g),nofail 0 0`
          (Armazenar senhas no fstab não é ideal; use um arquivo de credenciais).
    *   **macOS:** No Finder, vá em "Go" -> "Connect to Server..." e digite `smb://IP_DA_VM_SAMBA/NomeDoCompartilhamento`.
*   **Prós do Samba:**
    *   Excelente compatibilidade com clientes Windows, macOS e muitos outros dispositivos de rede.
    *   Funcionalidades robustas de permissão e autenticação.
*   **Contras do Samba:**
    *   A configuração pode ser mais complexa que NFS, especialmente o gerenciamento de permissões e usuários.
    *   A performance pode variar dependendo da configuração e da carga.

## 3. Pastas Compartilhadas VirtIO-FS (9P) - Host Proxmox para VM KVM Específica

VirtIO-FS é um sistema de arquivos compartilhado projetado especificamente para VMs KVM, permitindo compartilhar um diretório do host Proxmox diretamente com uma VM de forma mais eficiente e integrada do que NFS para este caso de uso host-para-VM_única.

*   **Caso de Uso:** Compartilhamento de alta performance e baixa latência de um diretório específico do host Proxmox para uma **única** VM KVM. Bom para arquivos de configuração, scripts, ou dados que precisam ser acessados rapidamente pela VM a partir do host.
*   **Configuração (Simplificada):**
    1.  **No Host Proxmox:**
        *   O diretório que você deseja compartilhar deve existir (e.g., `/mnt/meu_diretorio_para_vm100`).
    2.  **Na Configuração da VM (via UI Proxmox ou editando `/etc/pve/qemu-server/VMID.conf`):**
        *   **UI Proxmox:** Selecione a VM -> Hardware -> Add -> VirtIO FS.
            *   **VirtIO FS ID:** Escolha um ID (e.g., `0`).
            *   **Host Path:** O caminho absoluto para o diretório no host Proxmox (e.g., `/mnt/meu_diretorio_para_vm100`).
            *   **Tag:** Um nome de tag único para este compartilhamento (e.g., `hostshare0`). Este nome será usado para montar dentro da VM.
        *   **Exemplo em `VMID.conf`:**
            `virtio0: /mnt/meu_diretorio_para_vm100,tag=hostshare0`
            (O `virtio0` refere-se ao VirtIO FS ID. Se já tiver outros dispositivos VirtIO, o número pode ser diferente).
    3.  **Dentro da VM Convidada (Linux):**
        *   O kernel da VM precisa de suporte a `9pnet_virtio` e `9p` (geralmente incluído em kernels Linux modernos).
        *   **Monte o Compartilhamento:**
            ```bash
            # Crie um ponto de montagem dentro da VM
            sudo mkdir -p /mnt/from_host

            # Monte o compartilhamento usando a tag definida no Proxmox
            sudo mount -t 9p -o trans=virtio,version=9p2000.L,msize=262144 hostshare0 /mnt/from_host
            # 'msize' (tamanho máximo do pacote) pode ser ajustado para performance.
            # 'version=9p2000.L' especifica a versão do protocolo 9P.
            ```
        *   **Para Montagem Automática no Boot (adicione ao `/etc/fstab` da VM):**
            ```fstab
            hostshare0  /mnt/from_host  9p  trans=virtio,version=9p2000.L,msize=262144,rw,nofail  0  0
            ```
*   **Prós do VirtIO-FS:**
    *   Potencialmente melhor performance e menor latência que NFS para compartilhamento direto host-VM, pois é projetado para virtualização.
    *   Mais simples de configurar para um compartilhamento único host-VM do que um servidor NFS completo no host apenas para essa finalidade.
    *   Integração mais "nativa" com KVM/QEMU.
*   **Contras do VirtIO-FS:**
    *   Específico para VMs KVM no Proxmox (ou outros ambientes KVM/QEMU).
    *   Menos flexível que NFS para compartilhar com múltiplas VMs ou outros hosts na rede.
    *   O gerenciamento de permissões (UID/GID) pode precisar de atenção, dependendo de como o VirtIO-FS as mapeia (pode usar `mapped-file` ou outros modos de segurança).

## 4. Bancos de Dados Compartilhados entre Aplicações/VMs

Se múltiplas aplicações (rodando em diferentes VMs ou até mesmo em diferentes containers dentro da mesma VM, mas em stacks Docker separadas) precisam acessar o **mesmo** banco de dados.

*   **Estratégia Geral: Centralizar o Banco de Dados.**
    1.  **VM Dedicada ao Banco de Dados (Abordagem Robusta):**
        *   Crie uma VM Linux separada (e.g., `db-server-vm` usando nosso template Ubuntu).
        *   Instale o servidor de banco de dados desejado (e.g., PostgreSQL, MariaDB/MySQL) diretamente nesta VM.
        *   Configure o servidor de banco de dados para escutar em seu endereço IP na rede da VM (e.g., `0.0.0.0` ou o IP específico da `db-server-vm`, em vez de apenas `localhost`).
        *   No arquivo de configuração do servidor de banco de dados (e.g., `postgresql.conf` para PostgreSQL, `my.cnf` para MySQL/MariaDB), ajuste o `listen_addresses`.
        *   No arquivo de controle de acesso do banco de dados (e.g., `pg_hba.conf` para PostgreSQL), adicione regras para permitir conexões dos IPs das VMs/aplicações que precisam de acesso, usando os usuários e bancos de dados corretos.
        *   Crie bancos de dados, usuários e senhas específicos para cada aplicação cliente. Conceda apenas as permissões estritamente necessárias para cada usuário em seus respectivos bancos de dados.
        *   Configure o firewall UFW na `db-server-vm` para permitir conexões na porta do banco de dados (e.g., `5432/tcp` para PostgreSQL, `3306/tcp` para MySQL) **apenas** dos IPs das VMs/aplicações que precisam de acesso.
    2.  **Containers de Aplicação (Clientes do Banco de Dados):**
        *   Nas configurações de conexão com o banco de dados das suas aplicações (geralmente definidas por variáveis de ambiente nos `docker-compose.yml`), aponte para o **endereço IP da `db-server-vm`** e a porta correta, usando as credenciais específicas da aplicação.
*   **Exemplo Simplificado: PostgreSQL em `db-server-vm` (IP `192.168.15.20`) acessado pela `core-services-vm` (IP `192.168.15.11`):**
    *   **Na `db-server-vm`:**
        *   Em `/etc/postgresql/VERSION/main/postgresql.conf`: `listen_addresses = '192.168.15.20, localhost'` (ou `'*'`).
        *   Em `/etc/postgresql/VERSION/main/pg_hba.conf`:
            `host    nomedb_app_A    usuario_app_A    192.168.15.11/32    scram-sha-256`
            `host    nomedb_app_B    usuario_app_B    192.168.15.11/32    scram-sha-256`
        *   `sudo systemctl restart postgresql`
        *   `sudo ufw allow from 192.168.15.11 to any port 5432 proto tcp comment 'Allow App VM to PostgreSQL'`
    *   **No `docker-compose.yml` de uma aplicação na `core-services-vm`:**
        ```yaml
        services:
          minha_app_A:
            environment:
              - DB_HOST=192.168.15.20 # IP da db-server-vm
              - DB_PORT=5432
              - DB_USER=usuario_app_A
              - DB_PASSWORD=senha_app_A_do_vault
              - DB_NAME=nomedb_app_A
        ```
*   **Prós de um DB Centralizado:**
    *   Centraliza o gerenciamento, backup e manutenção do banco de dados.
    *   Pode ser mais eficiente em termos de recursos do que rodar múltiplos containers de banco de dados idênticos.
    *   Permite que múltiplas aplicações compartilhem dados de forma estruturada (se projetado para isso).
*   **Contras:**
    *   Adiciona outra VM para gerenciar (ou um container Docker dedicado se você preferir rodar o DB como container, mas ainda acessível pela rede).
    *   A rede se torna o caminho de comunicação com o banco de dados, o que pode introduzir uma pequena latência comparado a um DB na mesma rede Docker interna de uma aplicação.
    *   Configuração de firewall e acesso de rede precisa ser cuidadosa.

## 5. Sincronização de Arquivos entre Dispositivos/VMs (e.g., Syncthing, Nextcloud)

Em vez de montagens de rede diretas para todos os casos, você pode usar ferramentas de sincronização de arquivos para manter diretórios consistentes entre múltiplas VMs, seu desktop, laptop, etc.

*   **Syncthing:**
    *   **Propósito:** Sincronização de arquivos contínua, descentralizada e peer-to-peer (P2P).
    *   **Como Funciona:** Instale o Syncthing como um serviço nativo ou container Docker em cada VM ou dispositivo que precisa compartilhar/sincronizar uma ou mais pastas. Você "conecta" esses dispositivos Syncthing entre si (usando seus IDs de dispositivo) e depois define quais pastas são compartilhadas com quais dispositivos. Os arquivos são sincronizados diretamente entre os peers.
    *   **Vantagens:** Excelente para manter pastas pessoais sincronizadas, muito privado (sem servidor central para dados, a menos que relays sejam usados para NAT traversal, mas os dados são E2E criptografados), leve.
    *   **Desvantagens:** Não é um "servidor de arquivos" no sentido tradicional (sem acesso web direto aos arquivos, sem compartilhamento público por link). Requer que os dispositivos estejam online para sincronizar (ter uma instância Syncthing 24/7 no seu servidor pode atuar como um nó sempre online para seus outros dispositivos).
*   **Nextcloud (Cliente de Sincronização):**
    *   **Propósito:** Sua instância Nextcloud (rodando na `core-services-vm`) já atua como um servidor central de arquivos.
    *   **Como Funciona:** Instale os clientes de sincronização do Nextcloud em suas outras VMs (se tiverem GUI) ou em seus desktops/laptops/celulares. Configure os clientes para sincronizar pastas específicas com o servidor Nextcloud.
    *   **Vantagens:** Integra-se com todo o ecossistema Nextcloud (compartilhamento, apps, etc.).
    *   **Desvantagens:** A sincronização depende do servidor Nextcloud estar online e performante.

A escolha do método de compartilhamento de recursos depende muito do seu caso de uso específico, dos tipos de dispositivos envolvidos (Linux, Windows, macOS), dos requisitos de performance e da complexidade de configuração que você está disposto a gerenciar. Para volumes Docker, o NFS do host Proxmox para as VMs é a nossa base. Para outros cenários, Samba, VirtIO-FS ou ferramentas de sincronização podem ser mais apropriadas.