# Seção 1: Configuração da Máquina de Controle Ansible

A máquina de controle Ansible é o cérebro da sua automação. É a partir dela que você executará os playbooks para provisionar, configurar e gerenciar toda a sua infraestrutura de servidor doméstico.

## Pré-requisitos

*   Uma máquina (PC/Notebook) com Linux, macOS ou Windows (usando WSL2).
*   Acesso à Internet para baixar pacotes.
*   O projeto `infra-servidor-domestico` clonado ou com a estrutura de diretórios criada conforme a [Seção 0.2](00-preparacao-planejamento.md#02-estrutura-do-repositório-git-infra-servidor-domestico).

## 1.1. Instalação do Ambiente de Controle (`scripts/bootstrap.sh`)

Para simplificar a configuração inicial da sua máquina de controle, utilizaremos um script `bootstrap.sh`.

### Conteúdo do Script `scripts/bootstrap.sh`

Crie o arquivo `infra-servidor-domestico/scripts/bootstrap.sh` com o seguinte conteúdo:

```bash
#!/bin/bash
# scripts/bootstrap.sh
# Configura a máquina de controle Ansible (Linux/macOS)

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Iniciando a configuração do ambiente de controle Ansible...${NC}"

# 1. Verifica e atualiza o gerenciador de pacotes do sistema
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "${YELLOW}Detectado macOS. Verificando e atualizando Homebrew...${NC}"
    if ! command -v brew &> /dev/null; then
        echo -e "${RED}Homebrew não encontrado. Por favor, instale o Homebrew primeiro.${NC}"
        echo "Visite https://brew.sh/"
        exit 1
    fi
    brew update && brew upgrade
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Assumindo Debian/Ubuntu. Adapte para outros gerenciadores (yum, dnf) se necessário.
    echo -e "${YELLOW}Detectado Linux (Debian/Ubuntu based). Atualizando apt...${NC}"
    sudo apt update && sudo apt upgrade -y
else
    echo -e "${RED}Sistema operacional não suportado por este script (apenas macOS e Linux baseados em Debian/Ubuntu).${NC}"
    exit 1
fi

# 2. Instala Python 3, Pip e Venv (se não existirem)
echo -e "${YELLOW}Verificando Python 3, Pip e Venv...${NC}"
if ! command -v python3 &> /dev/null || ! python3 -m pip --version &> /dev/null || ! python3 -m venv --help &> /dev/null; then
    echo -e "${YELLOW}Python 3, Pip ou Venv não encontrados ou incompletos. Instalando...${NC}"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install python@3.11 # Ou a versão LTS mais recente suportada pelo Ansible
    fi
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt install -y python3 python3-pip python3-venv
    fi
else
    echo -e "${GREEN}Python 3, Pip e Venv já instalados.${NC}"
fi
# Garante que pip esteja associado ao python3 e atualizado
python3 -m ensurepip --upgrade

# 3. Instala Ansible
echo -e "${YELLOW}Verificando e instalando Ansible...${NC}"
if ! command -v ansible &> /dev/null; then
    echo -e "${YELLOW}Ansible não encontrado. Instalando Ansible...${NC}"
    # Recomendado instalar Ansible em um ambiente virtual Python para isolamento,
    # mas para simplificar este guia, instalaremos globalmente (via pip para o usuário ou sistema).
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install ansible
    fi
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Instalar via pip para ter uma versão mais recente que a dos repositórios do SO
        sudo python3 -m pip install ansible
    fi
else
    echo -e "${GREEN}Ansible já instalado.${NC}"
fi

# 4. Instala coleções Ansible necessárias
echo -e "${YELLOW}Instalando/Atualizando coleções Ansible: community.general, community.docker, community.proxmox...${NC}"
ansible-galaxy collection install community.general community.docker community.proxmox --force # --force para garantir a atualização

# 5. Instala SDK Docker para Python (necessário para módulos Docker do Ansible)
echo -e "${YELLOW}Instalando/Atualizando Docker SDK para Python...${NC}"
python3 -m pip install --user --upgrade docker # --user para instalar no diretório do usuário

# 6. Instala Proxmoxer SDK para Python (necessário para módulos Proxmox do Ansible)
echo -e "${YELLOW}Instalando/Atualizando Proxmoxer SDK para Python...${NC}"
python3 -m pip install --user --upgrade proxmoxer

echo -e "\n${GREEN}Configuração do ambiente de controle concluída!${NC}"
echo -e "${YELLOW}--------------------------------------------------------------------------------${NC}"
echo -e "${YELLOW}Próximos Passos Manuais IMPORTANTES:${NC}"
echo -e "${YELLOW}1. Gere uma chave SSH dedicada para este homelab se ainda não tiver:${NC}"
echo -e "   ${GREEN}ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_homelab -C \"homelab_ansible_key\"${NC}"
echo -e "${YELLOW}   (Pressione Enter para não definir passphrase se quiser automação total sem ssh-agent, ou defina uma passphrase e use ssh-agent).${NC}"
echo -e "${YELLOW}2. A chave pública (~/.ssh/id_ed25519_homelab.pub) precisará ser copiada para o host Proxmox e para as VMs.${NC}"
echo -e "${YELLOW}   O playbook de setup do Proxmox ajudará a configurar o acesso para o usuário Ansible no host Proxmox.${NC}"
echo -e "${YELLOW}   Para acesso inicial ao Proxmox (como root), você fará isso manualmente APÓS instalar o Proxmox e ANTES de rodar o primeiro playbook no Proxmox.${NC}"
echo -e "${YELLOW}--------------------------------------------------------------------------------${NC}"
```

### Executando o Script

1.  **Torne o script executável:**
    Na raiz do seu projeto `infra-servidor-domestico/`:
    ```bash
    chmod +x scripts/bootstrap.sh
    ```
2.  **Execute o script:**
    ```bash
    ./scripts/bootstrap.sh
    ```
    O script solicitará sua senha `sudo` se precisar instalar pacotes no sistema.

3.  **Verifique a instalação do Ansible:**
    ```bash
    ansible --version
    ```
    Você deve ver a versão do Ansible instalada e detalhes do Python.

### Ação Chave SSH (Crucial para Automação)

O Ansible se conectará aos seus servidores (Proxmox host e VMs) via SSH. É altamente recomendado usar autenticação baseada em chaves SSH.

1.  **Gere um par de chaves SSH dedicado para este projeto (se ainda não tiver uma que queira usar):**
    ```bash
    ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_homelab -C "homelab_ansible_key"
    ```
    *   `-t ed25519`: Especifica o tipo de chave (moderno e seguro).
    *   `-f ~/.ssh/id_ed25519_homelab`: Especifica o arquivo para salvar a chave privada (e `.pub` para a pública). Use um nome descritivo.
    *   `-C "homelab_ansible_key"`: Um comentário para identificar a chave.

2.  **Passphrase da Chave:**
    *   **Sem Passphrase (Mais fácil para automação total):** Pressione Enter quando solicitado pela passphrase. A chave privada não será protegida por senha.
        !!! warning "Segurança da Chave Privada sem Passphrase"
            Se você não definir uma passphrase, qualquer pessoa com acesso ao arquivo da chave privada (`~/.ssh/id_ed25519_homelab`) poderá acessar seus servidores. Proteja bem este arquivo!
    *   **Com Passphrase (Mais seguro, requer `ssh-agent`):** Digite uma passphrase forte. Você precisará usar o `ssh-agent` para evitar digitar a passphrase toda vez que o Ansible se conectar.
        Para usar `ssh-agent`:
        ```bash
        eval "$(ssh-agent -s)"
        ssh-add ~/.ssh/id_ed25519_homelab # Você digitará a passphrase aqui uma vez por sessão
        ```

A chave pública (`~/.ssh/id_ed25519_homelab.pub`) será copiada para os servidores remotos para permitir o login sem senha.

## 1.2. Criação e Gerenciamento de Variáveis Sensíveis (Ansible Vault)

Dados sensíveis como senhas, tokens de API, etc., não devem ser armazenados em texto plano no seu repositório Git. O Ansible Vault permite criptografar esses dados.

1.  **Crie o arquivo Vault:**
    Na raiz do seu projeto `infra-servidor-domestico/`, execute:
    ```bash
    ansible-vault create ansible/inventories/home/group_vars/all/vault.yml
    ```
    *   Você será solicitado a criar uma **senha para o Vault**. Escolha uma senha forte e **guarde-a com segurança**. Você precisará dela para editar o arquivo ou executar playbooks que o utilizem.

2.  **Adicione suas variáveis sensíveis ao `vault.yml`:**
    Após criar o arquivo, ele será aberto no seu editor padrão. Cole o conteúdo abaixo, **substituindo TODOS os placeholders** com seus valores reais.

    ```yaml
    # ansible/inventories/home/group_vars/all/vault.yml
    # Edite SEMPRE com: ansible-vault edit ansible/inventories/home/group_vars/all/vault.yml

    # --- Credenciais Proxmox ---
    # Usuário e senha para a API do Proxmox.
    # Inicialmente, pode ser root@pam, mas é recomendado criar um usuário API dedicado no Proxmox
    # com um token API após a configuração inicial do host.
    proxmox_api_user: "root@pam"
    proxmox_api_password: "SENHA_DO_ROOT_DO_PROXMOX_OU_SEGREDO_DO_TOKEN_API"
    # Se optar por usar um Token API do Proxmox (mais seguro a longo prazo):
    # proxmox_api_user: "ansible_api_user@pve!myapitokenid" # Exemplo: usuario_api@pve!nome_do_token
    # proxmox_api_token_id: "myapitokenid" # O nome/ID do seu token API
    # proxmox_api_token_secret: "SEGREDO_DO_TOKEN_API_PROXMOX" # O segredo do token gerado

    # --- Credenciais VMs ---
    # Senha para o usuário Ansible que será criado nas VMs.
    vm_ansible_user_password_plain: "SENHA_FORTE_E_UNICA_PARA_USUARIO_ANSIBLE_NAS_VMS"

    # --- Cloudflare ---
    # Token de API da Cloudflare com permissões para editar DNS no seu domínio.
    # Crie em: My Profile > API Tokens > Create Token > Use "Edit zone DNS" template.
    cloudflare_api_token: "TOKEN_API_CLOUDFLARE_COM_PERMISSAO_DNS_EDIT_PARA_SEU_DOMINIO"
    # Token do Cloudflare Tunnel. Obtido ao criar um túnel no dashboard Cloudflare Zero Trust.
    # Exemplo: cloudflared tunnel login -> copie o URL, visite-o, autorize, depois
    # cloudflared tunnel create <nome-do-tunel> -> anote o ID do túnel
    # cloudflared tunnel token <ID-ou-nome-do-tunel> -> este é o token para o daemon.
    cloudflare_tunnel_token: "TOKEN_LONGO_ALFANUMERICO_DO_CLOUDFLARE_TUNNEL"
    # O ID do túnel (UUID) será útil para referenciar nos registros DNS CNAME se não usar
    # a funcionalidade de --hostname ou Ingress Rules que criam DNS automaticamente.
    # cloudflare_tunnel_id: "ID_ALFANUMERICO_DO_TUNNEL_CLOUDFLARE_EX_AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"

    # --- Authelia ---
    # Segredos para JWT e Sessão. Gere com: openssl rand -base64 64
    authelia_jwt_secret: "SEU_SECRET_JWT_GERADO_ALEATORIAMENTE_PARA_AUTHELIA"
    authelia_session_secret: "SEU_SECRET_DE_SESSAO_GERADO_ALEATORIAMENTE_PARA_AUTHELIA"
    # Usuário administrador inicial do Authelia
    authelia_admin_user_initial: "admin"
    # Hash da senha do administrador. Gere com:
    # docker run --rm authelia/authelia:latest authelia crypto hash generate argon2 --password 'SUA_SENHA_ADMIN_AUTHELIA_FORTE'
    authelia_admin_password_hash_initial: "$argon2id$v=19$m=65536,t=3,p=4$SEU_SALT_GERADO$SEU_HASH_GERADO"
    # Senha para o usuário 'authelia' no banco de dados PostgreSQL do Authelia
    authelia_storage_postgres_password: "SENHA_FORTE_PARA_USUARIO_AUTHELIA_NO_DB_POSTGRES"

    # --- Configurações Gerais ---
    # Email para notificações do Let's Encrypt (renovação de certificados, etc.)
    letsencrypt_email: "seu_email_valido@example.com"
    # Seu domínio base, SEM https:// (e.g., seudominio.com)
    base_domain: "seudominio.com"
    # Fuso horário para os sistemas. Veja `timedatectl list-timezones` no Linux.
    system_timezone: "America/Sao_Paulo"

    # --- Docker User/Group IDs (Numéricos) ---
    # Usados para garantir consistência de permissões nos volumes NFS.
    # Geralmente 1000 para o primeiro usuário não-root criado em um sistema Linux.
    # Verifique o UID/GID do usuário que você deseja que seja o "dono" dos arquivos Docker.
    docker_puid: 1000
    docker_pgid: 1000

    # --- Senhas de Bancos de Dados de Aplicações (Adicione conforme necessário) ---
    nextcloud_db_password: "SENHA_FORTE_E_UNICA_PARA_DB_NEXTCLOUD"
    # Adicione a senha do usuário admin inicial do Nextcloud também
    nextcloud_admin_initial_password: "SENHA_FORTE_PARA_ADMIN_INICIAL_NEXTCLOUD"

    grafana_db_password: "SENHA_FORTE_E_UNICA_PARA_DB_GRAFANA"
    grafana_admin_initial_password: "SENHA_INICIAL_PARA_USUARIO_ADMIN_GRAFANA"
    ```
    !!! important "Como Editar o Vault"
        Para editar o arquivo `vault.yml` no futuro, use:
        ```bash
        ansible-vault edit ansible/inventories/home/group_vars/all/vault.yml
        ```
        Você será solicitado pela senha do Vault.

3.  **Salve e feche o editor.** O arquivo `vault.yml` agora está criptografado.
4.  **Verifique se `vault.yml` está no `.gitignore`** como medida de precaução extra.

## 1.3. Configuração do Inventário Ansible

O inventário Ansible define os hosts que o Ansible gerenciará e como se conectar a eles.

### Arquivo de Hosts (`ansible/inventories/home/hosts.ini`)

Crie o arquivo `infra-servidor-domestico/ansible/inventories/home/hosts.ini` com o seguinte conteúdo, **ajustando os IPs e nomes conforme sua rede e escolhas:**

```ini
# ansible/inventories/home/hosts.ini

# Grupo para o(s) seu(s) host(s) Proxmox VE
[proxmox_hosts]
# 'proxmox_main_host' é um nome lógico que você usará nos playbooks.
# 'ansible_host' é o IP real ou hostname DNS do seu host Proxmox.
# 'ansible_user' é o usuário que o Ansible usará para se conectar (criado na Seção 2).
proxmox_main_host ansible_host=192.168.1.10 ansible_user={{ proxmox_ansible_user_on_host }} # {{ proxmox_ansible_user_on_host }} virá de group_vars

# Grupo para suas máquinas virtuais
# Ajustado para o cenário de 16GB RAM:
# - core-services-vm: Para Docker, Portainer, Traefik, Authelia, Nextcloud, *arrs, Monitoramento.
# - ai-desktop-vm: Opcional, para LLMs/RAG com GPU Passthrough.
[virtual_machines]
core-services-vm ansible_host=192.168.1.11
ai-desktop-vm ansible_host=192.168.1.12 GUI_ENABLED=true # 'GUI_ENABLED' é uma var de host, usada condicionalmente

# Grupo 'filho' que inclui todas as VMs que rodam Ubuntu (para aplicar roles comuns)
[ubuntu_vms:children]
core-services-vm
ai-desktop-vm # Inclua aqui se for criar esta VM

# Variáveis globais aplicadas a TODOS os hosts (all)
[all:vars]
# Usuário Ansible padrão para se conectar às VMs (criado via Cloud-Init)
ansible_user="{{ vm_ansible_user_name }}" # Virá de group_vars/all/main.yml
# Caminho para a chave SSH privada gerada anteriormente
ansible_ssh_private_key_file="~/.ssh/id_ed25519_homelab"
# Método para escalação de privilégios (tornar-se root)
ansible_become_method=sudo
# Se o usuário Ansible nas VMs não tiver NOPASSWD: ALL no sudoers,
# você precisaria descomentar e fornecer a senha (do vault).
# Mas Cloud-Init configurará NOPASSWD.
# ansible_become_pass="{{ vm_ansible_user_password_plain }}"

# --- IPs para Referência em Templates ---
# Estes são IPs que podem ser usados em templates de configuração,
# distintos dos 'ansible_host' que são para conexão.
# Eles devem corresponder aos IPs definidos acima para consistência.
proxmox_host_ip_var: 192.168.1.10
core_services_vm_ip_var: 192.168.1.11
ai_desktop_vm_ip_var: 192.168.1.12
```
!!! note "Nomes de Hosts vs IPs"
    *   `proxmox_main_host`, `core-services-vm`, `ai-desktop-vm` são nomes lógicos (apelidos) que você usará nos seus playbooks Ansible para se referir aos hosts.
    *   `ansible_host` especifica o endereço IP real (ou hostname DNS se você tiver DNS local configurado) que o Ansible usará para se conectar ao host.
    *   As variáveis `*_ip_var` são uma convenção para ter os IPs disponíveis em templates sem depender da resolução de `ansible_host` em tempo de execução do template.

### Variáveis Globais Não Sensíveis (`ansible/inventories/home/group_vars/all/main.yml`)

Crie o arquivo `infra-servidor-domestico/ansible/inventories/home/group_vars/all/main.yml` para variáveis que se aplicam a todos os hosts e não são secretas.

```yaml
# ansible/inventories/home/group_vars/all/main.yml

# --- Proxmox Host ---
# Nome do usuário Ansible a ser criado no host Proxmox (diferente do root)
proxmox_ansible_user_on_host: "proxmox_ansible_user"
# CIDRs permitidos para SSH e Web UI no firewall do Proxmox Host
proxmox_ssh_allowed_cidrs: "192.168.1.0/24"     # AJUSTE PARA SUA REDE LOCAL
proxmox_web_ui_allowed_cidrs: "192.168.1.0/24"  # AJUSTE PARA SUA REDE LOCAL
# Bridge de rede padrão no Proxmox (geralmente vmbr0)
proxmox_default_bridge: "vmbr0"
# Storage no Proxmox onde os discos das VMs serão armazenados (geralmente local-lvm no NVMe)
proxmox_storage_vm_disks: "local-lvm"
# Storage no Proxmox onde ISOs e templates de VM são armazenados (geralmente local no NVMe)
proxmox_storage_iso_templates: "local"
# Nome do template Ubuntu Cloud-Init que será criado no Proxmox
proxmox_ubuntu_template_name: "ubuntu-2204-cloudinit-template-v1"

# --- Configurações Padrão para VMs ---
# Nome do usuário Ansible a ser criado nas VMs via Cloud-Init
vm_ansible_user_name: "vm_ansible_user"
# Gateway padrão para as VMs (IP do seu roteador)
vm_cloud_init_gateway: "192.168.1.1" # AJUSTE PARA SEU GATEWAY
# Servidores DNS para as VMs
vm_cloud_init_nameservers: "1.1.1.1,8.8.8.8" # Ou seu DNS preferido (e.g., Pi-hole)
# Defaults conservadores de recursos para VMs devido aos 16GB de RAM no host.
# Estes podem ser sobrescritos por VM no playbook `vm-deploy.yml`.
vm_default_cores: 2
vm_default_memory_mb: 2048 # 2GB
vm_default_disk_gb: 32     # Tamanho do disco da VM em GB

# --- Docker User/Group nas VMs ---
# Nomes para o usuário e grupo dedicados para rodar containers e possuir volumes NFS.
# Os IDs numéricos (PUID/PGID) estão no vault.yml.
docker_user_name_on_vm: "dockeruser"
docker_group_name_on_vm: "dockergroup"

# --- Caminhos ZFS no Proxmox Host ---
# Onde os datasets ZFS são criados e montados.
# '/data' é o ponto de montagem do pool ZFS criado nos HDDs.
zfs_base_pool_path: "/data"
# Nomes dos datasets ZFS a serem criados (montados sob /data/)
zfs_docker_volumes_dataset_name: "docker-volumes" # e.g., /data/docker-volumes
zfs_media_dataset_name: "media"                   # e.g., /data/media
zfs_downloads_dataset_name: "downloads"
zfs_rag_sources_dataset_name: "rag_sources"       # Para a VM de IA, se usada
zfs_backups_dataset_name: "backups"

# --- Caminhos de Montagem NFS DENTRO das VMs ---
# Ponto de montagem base DENTRO das VMs para os datasets ZFS compartilhados do Host Proxmox.
vm_nfs_mount_base_path: "/mnt/pve_data_zfs"

# --- Configuração NFS ---
# IPs ou CIDRs das VMs que terão permissão para montar os compartilhamentos NFS do Proxmox Host.
# Deve cobrir os IPs de todas as suas VMs.
vm_nfs_allowed_clients_cidr: "192.168.1.0/24" # AJUSTE PARA SUA SUB-REDE DE VMs

# --- Caminhos para Templates `.env` para Stacks Portainer ---
# Usado por playbooks para preparar arquivos .env para as stacks Docker.
# Template genérico que será preenchido com variáveis Ansible.
portainer_env_template_src: "templates/portainer_stack_env.j2" # Caminho relativo ao diretório de roles/playbooks
# Onde os arquivos .env resolvidos serão colocados na VM (core-services-vm ou ai-desktop-vm).
# Portainer lerá estes arquivos ao criar as stacks.
portainer_env_files_dest_path_on_vm: "/opt/portainer_stack_envs"
```

Com a máquina de controle Ansible configurada e o inventário pronto, você pode prosseguir para a [Instalação e Configuração Base do Proxmox VE](02-proxmox-ve-host.md).