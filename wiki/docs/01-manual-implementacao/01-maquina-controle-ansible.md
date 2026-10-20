---
description: "Prepara a máquina de controle: Ansible, chaves SSH, Ansible Vault, inventário hosts.ini e variáveis globais em group_vars."
---

# Seção 1: Configuração da Máquina de Controle Ansible

A máquina de controle Ansible é o seu "cockpit" para automação. É a partir dela que você executará os playbooks Ansible para provisionar, configurar e gerenciar toda a sua infraestrutura de servidor doméstico.

## Pré-requisitos

*   Uma máquina (PC/Notebook) com Linux, macOS ou Windows (usando WSL2).
*   Acesso à Internet para baixar pacotes e coleções Ansible.
*   O repositório `homeserver` clonado do seu repositório Git, ou com a estrutura de diretórios criada conforme a [Seção 0.2: Estrutura do Repositório Git](00-preparacao-planejamento.md#02-estrutura-do-repositório-git-do-projeto-homeserver).

## 1.1. Instalação do Ambiente de Controle (`scripts/bootstrap.sh`)

Para simplificar e padronizar a configuração da sua máquina de controle, utilizaremos o script `bootstrap.sh` fornecido no projeto.

### Conteúdo do Script `scripts/bootstrap.sh`

O arquivo `server/scripts/bootstrap.sh` contém:
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
if ! command -v python3 &> /dev/null || ! python3 -m pip --version &> /dev/null # Venv check removido pois ensurepip instala venv
then
    echo -e "${YELLOW}Python 3 ou Pip não encontrados. Instalando...${NC}"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install python@3.11 # Ou a versão LTS mais recente suportada pelo Ansible
    fi
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt install -y python3 python3-pip python3-venv # Venv ainda é útil ter explicitamente
    fi
else
    echo -e "${GREEN}Python 3 e Pip já instalados.${NC}"
fi
# Garante que pip e venv estejam associados ao python3 e atualizados
python3 -m ensurepip --upgrade

# 3. Instala Ansible
echo -e "${YELLOW}Verificando e instalando Ansible...${NC}"
if ! command -v ansible &> /dev/null; then
    echo -e "${YELLOW}Ansible não encontrado. Instalando Ansible...${NC}"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install ansible
    fi
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo python3 -m pip install ansible # Instalar via pip para versão mais recente
    fi
else
    echo -e "${GREEN}Ansible já instalado.${NC}"
    # Opcional: Atualizar Ansible se já estiver instalado
    # if [[ "$OSTYPE" == "linux-gnu"* ]]; then sudo python3 -m pip install --upgrade ansible; fi
    # if [[ "$OSTYPE" == "darwin"* ]]; then brew upgrade ansible; fi
fi

# 4. Instala coleções Ansible necessárias
echo -e "${YELLOW}Instalando/Atualizando coleções Ansible (ansible/requirements.yml)...${NC}"
ansible-galaxy collection install -r ansible/requirements.yml --force # coleções listadas em ansible/requirements.yml

# 5. Instala SDK Docker para Python (necessário para módulos Docker do Ansible)
echo -e "${YELLOW}Instalando/Atualizando Docker SDK para Python...${NC}"
python3 -m pip install --user --upgrade docker # --user para instalar no diretório do usuário

# 6. Instala Proxmoxer SDK para Python (necessário para módulos Proxmox do Ansible)
echo -e "${YELLOW}Instalando/Atualizando Proxmoxer SDK para Python...${NC}"
python3 -m pip install --user --upgrade proxmoxer

echo -e "\n${GREEN}Configuração do ambiente de controle Ansible concluída!${NC}"
echo -e "${YELLOW}--------------------------------------------------------------------------------${NC}"
echo -e "${YELLOW}Próximos Passos Manuais IMPORTANTES:${NC}"
echo -e "${YELLOW}1. Gere uma chave SSH dedicada para este homelab se ainda não tiver:${NC}"
echo -e "   ${GREEN}ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_homelab -C \"homelab_ansible_key\"${NC}"
echo -e "${YELLOW}   (Pressione Enter para não definir passphrase para automação total sem ssh-agent, ou defina uma e use ssh-agent).${NC}"
echo -e "${YELLOW}2. A chave pública (~/.ssh/id_ed25519_homelab.pub) precisará ser copiada para o host Proxmox e para as VMs.${NC}"
echo -e "${YELLOW}   O acesso inicial ao Proxmox (como root) para copiar a chave será manual, ANTES de rodar o primeiro playbook nele.${NC}"
echo -e "${YELLOW}--------------------------------------------------------------------------------${NC}"
```

### Executando o Script `bootstrap.sh`

1.  **Torne o script executável:**
    Na pasta `server/` do repositório:
    ```bash
    chmod +x scripts/bootstrap.sh
    ```
2.  **Execute o script:**
    ```bash
    ./scripts/bootstrap.sh
    ```
    O script poderá solicitar sua senha `sudo` para instalar pacotes no sistema.

3.  **Verifique a instalação do Ansible:**
    ```bash
    ansible --version
    ```
    Você deverá ver a versão do Ansible, a versão do Python utilizada e os caminhos de configuração.

### Ação Chave SSH (Essencial para Automação)

Ansible se conecta aos servidores (Proxmox host e VMs) via SSH. A autenticação baseada em chaves SSH é o método preferido e mais seguro.

1.  **Gere um par de chaves SSH dedicado para este projeto:**
    Se você ainda não tem uma chave SSH que deseja usar especificamente para este homelab, gere uma nova:
    ```bash
    ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_homelab -C "homelab_ansible_key"
    ```
    *   `-t ed25519`: Especifica o algoritmo de chave (moderno e seguro).
    *   `-f ~/.ssh/id_ed25519_homelab`: Local e nome do arquivo para a chave privada (a pública terá `.pub` adicionado). Use um nome descritivo.
    *   `-C "homelab_ansible_key"`: Um comentário para identificar a chave facilmente.

2.  **Sobre a Passphrase da Chave:**
    *   **Sem Passphrase (Mais fácil para automação total):** Pressione Enter quando solicitado pela passphrase. A chave privada não será protegida por uma senha adicional.
    !!! warning "Segurança da Chave Privada sem Passphrase"
        Se você optar por não usar uma passphrase, qualquer pessoa com acesso ao arquivo da sua chave privada (`~/.ssh/id_ed25519_homelab`) poderá acessar seus servidores como se fosse você. **Proteja este arquivo com permissões restritas** (e.g., `chmod 600 ~/.ssh/id_ed25519_homelab`).
    *   **Com Passphrase (Mais seguro, requer `ssh-agent` para conveniência):** Digite uma passphrase forte e única. Se você definir uma passphrase, precisará:
        *   Digitar a passphrase toda vez que o Ansible usar a chave.
        *   Ou usar o `ssh-agent` para armazenar a chave descriptografada na memória durante sua sessão de login.
            Para usar `ssh-agent`:
            ```bash
            eval "$(ssh-agent -s)"  # Inicia o ssh-agent
            ssh-add ~/.ssh/id_ed25519_homelab # Adiciona sua chave ao agent (você digitará a passphrase aqui)
            ```

A chave pública (`~/.ssh/id_ed25519_homelab.pub`) será o que você copiará para os servidores remotos para permitir o login sem senha via Ansible.

### Coleções Ansible do projeto

Os módulos usados pelos roles vêm destas coleções, instaladas pelo script acima (e pelo `python tools/dev.py lint`, que precisa delas para o `--syntax-check`):

```yaml title="ansible/requirements.yml"
# ansible/requirements.yml
# Coleções Ansible usadas pelos roles e playbooks.
# Instale com: ansible-galaxy collection install -r ansible/requirements.yml
collections:
  - name: community.general
  - name: community.docker
  - name: community.proxmox
  - name: ansible.posix
```

## 1.2. Criação e Gerenciamento de Variáveis Sensíveis (Ansible Vault)

Dados sensíveis como senhas, tokens de API e chaves privadas não devem ser armazenados em texto plano no seu repositório Git. O Ansible Vault é a ferramenta integrada do Ansible para criptografar esses dados.

1.  **Crie o Arquivo Vault:**
    Na pasta `server/ansible` do repositório (onde está o `ansible.cfg`), execute:
    ```bash
    ansible-vault create inventories/home/group_vars/all/vault.yml
    ```
    *   Você será solicitado a **criar e confirmar uma senha para o Vault**. Escolha uma senha forte e única.
!!! critical "Guarde Bem a Senha do Vault!"
    Esta senha é essencial. Sem ela, você não poderá acessar ou modificar os segredos no arquivo `vault.yml`, nem executar playbooks que dependam dele. Armazene-a em um gerenciador de senhas seguro.

2.  **Adicione suas Variáveis Sensíveis ao `vault.yml`:**
    O modelo abaixo está versionado em `ansible/inventories/home/group_vars/all/vault.yml.example`. Como alternativa ao `create`, copie o modelo, preencha e criptografe: `cp vault.yml.example vault.yml && ansible-vault encrypt vault.yml` (dentro de `group_vars/all/`).

    Após o comando `create`, o arquivo será aberto no seu editor de texto padrão (geralmente `vi` ou `nano`). Cole o conteúdo abaixo, **substituindo TODOS os placeholders em MAIÚSCULAS** com seus valores reais e secretos.

    ```yaml title="ansible/inventories/home/group_vars/all/vault.yml.example"
    # ansible/inventories/home/group_vars/all/vault.yml.example
    # MODELO versionado. Copie para vault.yml, preencha e criptografe:
    #   cp vault.yml.example vault.yml && ansible-vault encrypt vault.yml
    # Depois, edite SEMPRE com: ansible-vault edit inventories/home/group_vars/all/vault.yml

    # --- Credenciais Proxmox ---
    # Usuário e senha para a API do Proxmox.
    # Inicialmente, pode ser root@pam. Após o setup inicial do host Proxmox,
    # é recomendado criar um usuário API dedicado no Proxmox com um token API.
    proxmox_api_user: "root@pam"
    proxmox_api_password: "SENHA_DO_ROOT_DO_PROXMOX_DEFINIDA_NA_INSTALACAO"
    # Se optar por usar um Token API do Proxmox (mais seguro a longo prazo):
    # proxmox_api_user: "ansible_api_user@pve!meuapitokenid" # Formato: usuario@realm!TokenID
    # proxmox_api_token_id: "meuapitokenid"                   # O ID do token
    # proxmox_api_token_secret: "SEGREDO_LONGO_DO_TOKEN_API_PROXMOX" # O segredo gerado

    # --- Credenciais VMs ---
    # Senha para o usuário Ansible ('{{ vm_ansible_user_name }}') que será criado nas VMs via Cloud-Init.
    vm_ansible_user_password_plain: "SENHA_FORTE_E_UNICA_PARA_USUARIO_ANSIBLE_NAS_VMS"

    # --- Cloudflare ---
    # Token de API da Cloudflare com permissões para editar registros DNS no seu domínio.
    # Crie em: Cloudflare Dashboard > My Profile > API Tokens > Create Token > Use "Edit zone DNS" template.
    cloudflare_api_token: "TOKEN_API_CLOUDFLARE_PARA_EDICAO_DNS_DO_SEU_DOMINIO"
    # Token do Cloudflare Tunnel. Obtido ao criar um túnel no dashboard Cloudflare Zero Trust.
    # Siga: Zero Trust > Access > Tunnels > Create a tunnel. Após criado, você verá o comando para
    # rodar o conector, que inclui o token. Ou use `cloudflared tunnel token <TUNNEL_NAME_OR_ID>`.
    cloudflare_tunnel_token: "TOKEN_LONGO_ALFANUMERICO_DO_SEU_CLOUDFLARE_TUNNEL"
    # O ID do túnel (UUID) pode ser útil para referência, mas o token é o principal para o conector.
    # cloudflare_tunnel_id: "UUID_DO_SEU_TUNNEL_CLOUDFLARE_EX_AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"

    # --- Authelia ---
    # Segredos para JWT (JSON Web Token) e Sessão. Gere strings aleatórias longas e seguras.
    # Exemplo de geração: openssl rand -base64 64
    authelia_jwt_secret: "SEU_SECRET_JWT_PARA_AUTHELIA_MUITO_LONGO_E_ALEATORIO"
    authelia_session_secret: "SEU_SECRET_DE_SESSAO_PARA_AUTHELIA_MUITO_LONGO_E_ALEATORIO"
    # Usuário administrador inicial do Authelia.
    authelia_admin_user_initial: "admin" # Ou seu nome de admin preferido
    # Hash da senha do administrador do Authelia. Gere com o comando Docker:
    # docker run --rm authelia/authelia:latest authelia crypto hash generate argon2 --password 'SUA_SENHA_ADMIN_AUTHELIA_FORTE'
    # Copie a saída completa, incluindo o $argon2id$...
    authelia_admin_password_hash_initial: "$argon2id$v=19$m=65536,t=3,p=4$SEU_SALT_GERADO_PELO_COMANDO$SEU_HASH_GERADO_PELO_COMANDO"
    # Senha para o usuário 'authelia' no banco de dados PostgreSQL do Authelia.
    authelia_storage_postgres_password: "SENHA_FORTE_PARA_O_USUARIO_AUTHELIA_NO_DB_POSTGRES"
    # Chave de criptografia do storage do Authelia (mín. 20 caracteres; gere com: openssl rand -hex 32).
    authelia_storage_encryption_key: "CHAVE_DE_CRIPTOGRAFIA_DO_STORAGE_DO_AUTHELIA"

    # --- Authelia como provedor OIDC (login do Immich e do Nextcloud; página 11) ---
    # hmac_secret: texto aleatório (openssl rand -hex 32).
    authelia_oidc_hmac_secret: "SEGREDO_HMAC_DO_OIDC_64_CARACTERES"
    # Chave privada RSA 2048 que assina os tokens: openssl genrsa 2048 (cole o PEM inteiro).
    authelia_oidc_jwks_key: |
      -----BEGIN PRIVATE KEY-----
      COLE_AQUI_A_CHAVE_PRIVADA_RSA_GERADA
      -----END PRIVATE KEY-----
    # Um cliente por app. 'secret' (só letras e números: openssl rand -hex 32) vai para o app;
    # 'secret_digest' é o hash do mesmo segredo, que o Authelia guarda. Gere o digest com a imagem fixada:
    #   docker run --rm authelia/authelia:4.38.0 authelia crypto hash generate pbkdf2 --variant sha512 --password <secret>
    # e copie o valor depois de "Digest: ".
    oidc_clients:
      immich:
        secret: "SEGREDO_DO_CLIENTE_IMMICH"
        secret_digest: "$pbkdf2-sha512$310000$SALT$HASH_DO_SEGREDO_DO_IMMICH"
      nextcloud:
        secret: "SEGREDO_DO_CLIENTE_NEXTCLOUD"
        secret_digest: "$pbkdf2-sha512$310000$SALT$HASH_DO_SEGREDO_DO_NEXTCLOUD"
      openwebui:
        secret: "SEGREDO_DO_CLIENTE_OPENWEBUI"
        secret_digest: "$pbkdf2-sha512$310000$SALT$HASH_DO_SEGREDO_DO_OPENWEBUI"
      # Conectores MCP do segundo cérebro (página 12): os dois mcp-auth-proxy usam o mesmo cliente.
      mcp:
        secret: "SEGREDO_DO_CLIENTE_MCP"
        secret_digest: "$pbkdf2-sha512$310000$SALT$HASH_DO_SEGREDO_DO_MCP"
      # Langfuse (página 13).
      langfuse:
        secret: "SEGREDO_DO_CLIENTE_LANGFUSE"
        secret_digest: "$pbkdf2-sha512$310000$SALT$HASH_DO_SEGREDO_DO_LANGFUSE"

    # --- Configurações Gerais ---
    # Email para notificações do Let's Encrypt (renovação de certificados, problemas).
    letsencrypt_email: "seu_email_valido_para_lets_encrypt@example.com"
    # Seu domínio base, SEM https:// ou www (e.g., seudominio.com).
    base_domain: "seudominio.com"
    # Fuso horário para os sistemas. Encontre o seu com `timedatectl list-timezones` no Linux.
    system_timezone: "America/Sao_Paulo" # Exemplo, ajuste para o seu.

    # --- Docker User/Group IDs (Numéricos) ---
    # Usados para consistência de permissões nos volumes NFS e dentro dos containers.
    # Geralmente 1000 para o primeiro usuário não-root criado em um sistema Linux.
    # Verifique o UID/GID do usuário que você deseja que seja o "dono" dos arquivos Docker.
    docker_puid: 1000
    docker_pgid: 1000

    # --- Senhas de Bancos de Dados de Aplicações (Adicione conforme necessário) ---
    nextcloud_db_password: "SENHA_FORTE_E_UNICA_PARA_O_DB_DO_NEXTCLOUD"
    # Senha para o usuário administrador inicial do Nextcloud (criado na primeira execução).
    nextcloud_admin_initial_password: "SENHA_FORTE_PARA_O_ADMIN_INICIAL_DO_NEXTCLOUD"
    # Senha do Postgres do Immich (stack photos; página 11). Só letras e números.
    immich_db_password: "SENHA_FORTE_PARA_O_DB_DO_IMMICH"

    grafana_db_password: "SENHA_FORTE_E_UNICA_PARA_O_DB_DO_GRAFANA"
    grafana_admin_initial_password: "SENHA_FORTE_PARA_O_ADMIN_INICIAL_DO_GRAFANA"

    # --- APIs de LLM (LiteLLM e Gemini CLI) ---
    # Chave mestra do proxy LiteLLM (gere com: openssl rand -hex 32).
    litellm_master_key: "CHAVE_MESTRA_DO_LITELLM"
    llm_api_keys:
      openai: "SUA_CHAVE_OPENAI"
      anthropic: "SUA_CHAVE_ANTHROPIC"
      google_gemini: "SUA_CHAVE_GEMINI"
      typesafe: "SUA_CHAVE_TYPESAFE" # Jev (modelo de decisão); console da TypeSafe AI
    # Senha do Postgres do LiteLLM (stack ai; página 08). Só letras e números.
    litellm_db_password: "SENHA_FORTE_PARA_O_DB_DO_LITELLM"
    # Uma chave virtual do LiteLLM por cliente (gere com: echo sk-$(openssl rand -hex 24)). Os clientes usam
    # estas, nunca a litellm_master_key; o setup-ai-keys.yml as cria no LiteLLM com o orçamento de cada uma.
    litellm_client_keys:
      openwebui: "sk-CHAVE_DO_OPEN_WEBUI"
      claude_code: "sk-CHAVE_DO_CLAUDE_CODE"
      n8n: "sk-CHAVE_DO_N8N"
    # Chave de sessão do Open WebUI (gere com: openssl rand -hex 32).
    openwebui_secret_key: "CHAVE_SECRETA_DO_OPEN_WEBUI"

    # --- Notificações (Telegram via n8n) ---
    # Token do bot criado no @BotFather e ID do chat que recebe as mensagens.
    telegram_bot_token: "TOKEN_DO_BOT_DO_TELEGRAM"
    telegram_chat_id: "ID_DO_CHAT_DO_TELEGRAM"
    # Token que autentica quem chama o webhook do n8n (gere com: openssl rand -hex 32).
    notificacoes_webhook_token: "TOKEN_DO_WEBHOOK_DE_NOTIFICACOES"

    # --- Segundo cérebro (stack notes, página 12) ---
    # Senha do painel do Syncthing (usuário em syncthing_gui_user) e chave da API dele (openssl rand -hex 24).
    syncthing_gui_password: "SENHA_DO_PAINEL_DO_SYNCTHING"
    syncthing_api_key: "CHAVE_DA_API_DO_SYNCTHING"
    # Assina os tokens OAuth emitidos pelos mcp-auth-proxy (openssl rand -base64 32). Fixo: trocar invalida os logins.
    mcp_auth_hmac_secret: "BASE64_DE_32_BYTES"

    # --- Mídia (stack media, página 10) ---
    # Chaves de API das *arr, fixadas por variável de ambiente (gere cada uma com: openssl rand -hex 16).
    arr_api_keys:
      sonarr: "CHAVE_DE_API_DO_SONARR_32_HEX"
      radarr: "CHAVE_DE_API_DO_RADARR_32_HEX"
      lidarr: "CHAVE_DE_API_DO_LIDARR_32_HEX"
      prowlarr: "CHAVE_DE_API_DO_PROWLARR_32_HEX"
    # PrivateKey da configuração WireGuard da ProtonVPN gerada com NAT-PMP (Port Forwarding) ligado.
    protonvpn_wireguard_private_key: "CHAVE_PRIVADA_WIREGUARD_DA_PROTONVPN"

    # --- Portainer Agent (ai-desktop-vm; seção 4) ---
    # Segredo compartilhado entre o Portainer da core-services-vm e o agente das outras VMs (openssl rand -hex 32).
    portainer_agent_secret: "SEGREDO_COMPARTILHADO_DO_PORTAINER_AGENT"

    # --- Painel (Homepage): credenciais dos widgets ---
    # Geradas na interface de cada aplicação depois do primeiro acesso (página 09).
    # O widget do Grafana usa o admin e grafana_admin_initial_password.
    homepage_widget_keys:
      # Sonarr, Radarr, Lidarr e Prowlarr usam arr_api_keys (acima).
      jellyfin: "CHAVE_DE_API_DO_JELLYFIN"
      bazarr: "CHAVE_DE_API_DO_BAZARR"
      seerr: "CHAVE_DE_API_DO_SEERR"
      nextcloud: "NC_TOKEN_DO_NEXTCLOUD"
      immich: "CHAVE_DE_API_DO_IMMICH" # Conta › Configurações da conta › Chaves de API (página 11)
      homeassistant: "TOKEN_DE_LONGA_DURACAO_DO_HOME_ASSISTANT"
      portainer: "CHAVE_DE_API_DO_PORTAINER"
      qbittorrent_user: "admin"
      qbittorrent_password: "SENHA_DO_QBITTORRENT"

    # --- Agentes: base (página 13) ---
    # Chaves dos clientes da rota de controle do hub (LAN): "ag-" + openssl rand -hex 24. No config do hub só vai o hash.
    agents_api_keys:
      claude_code: "ag-CHAVE_DO_CLAUDE_CODE"
      agentes: "ag-CHAVE_DOS_AGENTES"
    # Tokens de service account do Grafana: leitura (papel Viewer) e controle (papel Editor). Página 13.
    grafana_sa_tokens:
      leitura: "glsa_TOKEN_VIEWER"
      controle: "glsa_TOKEN_EDITOR"
    # Token de longa duração do Home Assistant (Perfil › Segurança) usado pelo hub no /api/mcp.
    homeassistant_mcp_token: "TOKEN_DE_LONGA_DURACAO_DO_HOME_ASSISTANT_PARA_O_MCP"
    # Token do n8n em Settings › Instance-level MCP › API key.
    n8n_mcp_token: "TOKEN_DO_MCP_DO_N8N"
    # Chave de API do Portainer (Minha conta › Access tokens) usada pelo ops.
    portainer_api_key: "ptr_CHAVE_DE_API_DO_PORTAINER_PARA_O_OPS"
    # Chave SSH própria do runner do ops (ssh-keygen -t ed25519 -C ops-runner); a pública vai para os hosts.
    ops_ssh_private_key: |
      -----BEGIN OPENSSH PRIVATE KEY-----
      CHAVE_PRIVADA_DO_RUNNER
      -----END OPENSSH PRIVATE KEY-----
    # A mesma senha do ansible-vault deste repositório (o runner descriptografa o vault.yml).
    ops_vault_password: "SENHA_DO_ANSIBLE_VAULT"
    # Langfuse: salt e segredos (openssl rand -base64 32), encryption_key (openssl rand -hex 32), senhas dos
    # bancos e as chaves do projeto criadas na primeira subida (pk-lf-/sk-lf- + openssl rand -hex 16).
    langfuse_secrets:
      salt: "SALT_DO_LANGFUSE"
      encryption_key: "64_HEX_DO_LANGFUSE"
      nextauth_secret: "SEGREDO_DE_SESSAO_DO_LANGFUSE"
      db_password: "SENHA_DO_POSTGRES_DO_LANGFUSE"
      clickhouse_password: "SENHA_DO_CLICKHOUSE_DO_LANGFUSE"
      redis_password: "SENHA_DO_REDIS_DO_LANGFUSE"
      minio_password: "SENHA_DO_MINIO_DO_LANGFUSE"
      public_key: "pk-lf-CHAVE_PUBLICA_DO_PROJETO"
      secret_key: "sk-lf-CHAVE_SECRETA_DO_PROJETO"
    ```
    !!! important "Como Editar o Arquivo Vault no Futuro"
        Para editar o arquivo `vault.yml` após sua criação, SEMPRE use o comando:
        ```bash
        ansible-vault edit inventories/home/group_vars/all/vault.yml
        ```
        Você será solicitado a fornecer a senha do Vault que você definiu. **Não tente editar o arquivo criptografado diretamente.**

3.  **Salve e feche o editor.** O arquivo `vault.yml` agora estará criptografado no seu sistema de arquivos.
4.  **Nunca commite o `vault.yml` em texto puro.** O arquivo criptografado *deve* ser commitado no Git; cópias descriptografadas (`*.decrypted*`) já são ignoradas pelo `.gitignore` do repositório, e o `python tools/dev.py check` (e o CI) falham se o `vault.yml` não começar com `$ANSIBLE_VAULT;`.

## 1.3. Configuração do Inventário Ansible

O inventário Ansible é o coração da sua automação. Ele define:

*   Quais hosts (servidores, VMs) o Ansible gerenciará.
*   Como o Ansible se conectará a esses hosts (IPs, usuários, chaves SSH).
*   Como os hosts são agrupados para aplicar configurações em conjunto.
*   Variáveis específicas de hosts ou grupos.

### Arquivo de Hosts (`ansible/inventories/home/hosts.ini`)

Crie o arquivo `server/ansible/inventories/home/hosts.ini`. Este arquivo define seus servidores e VMs. **Ajuste os endereços IP e nomes de host conforme sua rede e preferências.**

```ini title="ansible/inventories/home/hosts.ini"
# ansible/inventories/home/hosts.ini

# Host Proxmox VE.
# 'proxmox_main_host' é o nome lógico usado nos playbooks (setup-proxmox-host.yml, vm-deploy.yml).
# A variável '{{ proxmox_ansible_user_on_host }}' vem de group_vars/all/main.yml.
[proxmox_hosts]
proxmox_main_host ansible_host=192.168.15.66 ansible_user="{{ proxmox_ansible_user_on_host }}"

# VM de serviços principais (Traefik, Authelia, Portainer, apps).
[core_services]
core-services-vm ansible_host=192.168.15.67

# VM de IA (Ollama, LiteLLM, Open WebUI). GUI_ENABLED é uma variável de host.
[ai_desktop]
ai-desktop-vm ansible_host=192.168.15.68 GUI_ENABLED=true

# Todas as VMs gerenciadas pelo Proxmox (usado por vm-deploy.yml).
[virtual_machines:children]
core_services
ai_desktop

# VMs Ubuntu Server que recebem os roles comuns (setup-base-ubuntu.yml).
[ubuntu_vms:children]
core_services
ai_desktop

# Variáveis globais aplicadas a TODOS os hosts deste inventário.
[all:vars]
# Usuário Ansible nas VMs (criado via Cloud-Init); vem de group_vars/all/main.yml.
ansible_user="{{ vm_ansible_user_name }}"
# Chave SSH privada gerada na máquina de controle.
ansible_ssh_private_key_file="~/.ssh/id_ed25519_homelab"
ansible_become_method=sudo
# Se o usuário Ansible nas VMs não tiver 'NOPASSWD: ALL', descomente e use a senha do vault.yml.
# ansible_become_pass="{{ vm_ansible_user_password_plain }}"

# --- IPs para referência em templates (devem bater com os ansible_host acima) ---
proxmox_host_ip_var=192.168.15.66
core_services_vm_ip_var=192.168.15.67
ai_desktop_vm_ip_var=192.168.15.68
```
!!! note "Nomes de Hosts vs. IPs de Conexão"
    *   `proxmox_main_host`, `core-services-vm`, `ai-desktop-vm` são nomes lógicos (apelidos) que você usará nos seus playbooks Ansible para se referir aos hosts.
    *   `ansible_host` especifica o endereço IP real (ou hostname DNS, se você tiver DNS local configurado e funcionando) que o Ansible usará para se conectar ao host.
    *   As variáveis `*_ip_var` são uma convenção para ter os IPs facilmente acessíveis em templates, sem depender da resolução de `ansible_host` dentro do template.

### Variáveis Globais Não Sensíveis (`ansible/inventories/home/group_vars/all/main.yml`)

!!! info "Configuração do Ansible do projeto"
    O arquivo `ansible/ansible.cfg` define o inventário padrão (`inventories/home/hosts.ini`), o `roles_path` e opções como `host_key_checking`. Rode os comandos `ansible-playbook` a partir de `server/ansible/` para que ele seja carregado.

Crie o arquivo `server/ansible/inventories/home/group_vars/all/main.yml`. Este arquivo define variáveis que se aplicam a todos os hosts no seu inventário e que não são secretas (segredos vão no `vault.yml`).

```yaml title="ansible/inventories/home/group_vars/all/main.yml"
# ansible/inventories/home/group_vars/all/main.yml

# --- Configurações do Host Proxmox ---
# Nome do usuário Ansible dedicado a ser criado no host Proxmox.
proxmox_ansible_user_on_host: "proxmox_ansible_user"
# CIDRs da sua rede local permitidos para SSH e acesso à Web UI do Proxmox.
# AJUSTE ESTES VALORES PARA CORRESPONDER À SUA REDE LOCAL!
proxmox_ssh_allowed_cidrs: "192.168.15.0/24"
proxmox_web_ui_allowed_cidrs: "192.168.15.0/24"
# Bridge de rede padrão no Proxmox (geralmente vmbr0, conectada à sua LAN).
proxmox_default_bridge: "vmbr0"
proxmox_node_name: "pve" # Nome do nó no Proxmox (Datacenter > nó); usado pela API para clonar VMs e criar regras de firewall
# Storage no Proxmox onde os discos virtuais das VMs serão armazenados (geralmente 'local-lvm' no SSD NVMe).
proxmox_storage_vm_disks: "local-lvm"
# Storage no Proxmox onde ISOs e templates de VM são armazenados (geralmente 'local' no SSD NVMe).
proxmox_storage_iso_templates: "local"
# Nome do template Ubuntu Cloud-Init que será criado no Proxmox.
proxmox_ubuntu_template_name: "ubuntu-2404-cloudinit-template-v1"

# --- Configurações Padrão para Máquinas Virtuais (VMs) ---
# Nome do usuário Ansible a ser criado nas VMs via Cloud-Init.
vm_ansible_user_name: "vm_ansible_user"
# Gateway padrão para as VMs (geralmente o IP do seu roteador doméstico).
# AJUSTE ESTE VALOR PARA O SEU GATEWAY!
vm_cloud_init_gateway: "192.168.15.1"
# Servidores DNS para as VMs.
vm_cloud_init_nameservers: "1.1.1.1,8.8.8.8" # Ou seu DNS local preferido (e.g., Pi-hole IP).
# Recursos padrão para VMs. Estes podem ser sobrescritos por VM no playbook `vm-deploy.yml`.
# Com 48GB de RAM no host, temos mais flexibilidade.
vm_default_cores: 2
vm_default_memory_mb: 4096 # 4GB como padrão (ajustaremos para VMs específicas)
vm_default_disk_gb: 50     # Tamanho do disco da VM em GB como padrão

# --- Docker User/Group nas VMs ---
# Nomes para o usuário e grupo dedicados que serão proprietários dos arquivos nos volumes NFS
# e com cujos PUID/PGID os containers Docker rodarão.
# Os IDs numéricos (PUID/PGID) estão definidos no vault.yml.
docker_user_name_on_vm: "dockeruser"
docker_group_name_on_vm: "dockergroup"

# --- Caminhos e Nomes de Datasets ZFS no Host Proxmox ---
# O pool ZFS principal (criado nos HDDs) será montado em /data.
zfs_base_pool_path: "/data"
# Nomes dos datasets ZFS a serem criados sob o pool 'data'.
# Estes serão montados em, por exemplo, /data/docker-volumes, /data/media, etc.
zfs_docker_volumes_dataset_name: "docker-volumes"
zfs_media_dataset_name: "media"             # Mídia e torrents no mesmo dataset (/data na stack media; hardlinks).
zfs_rag_sources_dataset_name: "rag_sources"       # Para a VM de IA, se usada.
zfs_backups_dataset_name: "backups"
zfs_photos_dataset_name: "photos"           # Fotos do Immich (uploads, miniaturas e dumps do banco). Criado com cota.
zfs_files_dataset_name: "files"             # Diretório de dados do Nextcloud. Criado com cota.
zfs_notes_dataset_name: "notes"             # Vaults do Obsidian (segundo cérebro, página 12). Só na VM de IA; snapshots automáticos.

# --- Disco local das VMs ---
# Bancos que não podem ficar em NFS (o Immich exige disco local) ficam aqui, fora dos snapshots ZFS;
# o backup deles são os dumps diários gravados no NFS (página 11).
vm_local_data_path: "/opt/local-data"

# --- Caminhos de Montagem NFS DENTRO das VMs ---
# Ponto de montagem base DENTRO das VMs para os datasets ZFS compartilhados do Host Proxmox.
vm_nfs_mount_base_path: "/mnt/pve_data_zfs"

# --- Configuração do Servidor NFS (no Host Proxmox) ---
# IPs ou CIDRs das VMs que terão permissão para montar os compartilhamentos NFS.
# Deve cobrir os IPs de todas as suas VMs que precisarão de acesso NFS.
# AJUSTE ESTE VALOR PARA A SUB-REDE DAS SUAS VMs!
vm_nfs_allowed_clients_cidr: "192.168.15.0/24"

# --- Caminhos para Templates `.env` para Stacks Portainer ---
# Usado por playbooks Ansible para preparar arquivos .env para as stacks Docker.
# portainer_env_template_src: "templates/portainer_stack_env.j2" # Caminho relativo ao diretório de roles/playbooks
# Onde os arquivos .env resolvidos (preenchidos pelo Ansible) serão colocados na VM
# para o Portainer usar ao criar/atualizar stacks.
portainer_env_files_dest_path_on_vm: "/opt/portainer_stack_envs"

# --- Subdomínios de serviços ---
# Subdomínio do n8n (resulta em n8n.<base_domain>).
n8n_subdomain: "n8n"

# --- Grafana Alloy (coletor de logs e métricas; role infra/alloy) ---
# Série fixada: aceita correções (1.20.x); para mudar de série, troque o valor e rode os playbooks.
alloy_version: "1.20.*"

# --- Fotos e arquivos (página 11) ---
# Versão do Immich: todos os containers usam a mesma; atualize de propósito, lendo as notas da release.
immich_version: "v3.3.3"
# Versão principal do Nextcloud (imagem nextcloud:<major>-apache). Suba uma versão principal por vez.
nextcloud_major: "34"
# Login por senha do Immich: ligado só até vincular a conta ao Authelia (OIDC); depois, false.
immich_password_login: true
# Ajustes da configuração do Immich, mesclados por cima da base do immich.json (chaves da documentação do Immich).
immich_config_overrides: {}

# --- IA: gateway LiteLLM (página 08) ---
# Modelos servidos pelo LiteLLM. 'chave' é o nome da variável de ambiente do provedor (o valor vem do vault
# e só o container do LiteLLM o recebe). Os apelidos (principal, rapido, local, decisao) são o que os clientes
# usam: para trocar de LLM, mude o 'model' do apelido e rode o setup-ai-volumes.yml + docker restart litellm_proxy.
llm_models:
  # Por nome próprio
  - { name: "claude-opus-5-5", model: "anthropic/claude-opus-5-5", chave: "ANTHROPIC_API_KEY" }
  - { name: "claude-sonnet-5-5", model: "anthropic/claude-sonnet-5-5", chave: "ANTHROPIC_API_KEY" }
  - { name: "claude-haiku-5-5", model: "anthropic/claude-haiku-5-5", chave: "ANTHROPIC_API_KEY" }
  - { name: "gpt-6.1-sol", model: "openai/gpt-6.1-sol", chave: "OPENAI_API_KEY" }
  - { name: "gpt-6-luna", model: "openai/gpt-6-luna", chave: "OPENAI_API_KEY" }
  - { name: "gemini-3.8-flash", model: "gemini/gemini-3.8-flash", chave: "GEMINI_API_KEY" }
  # Apelidos
  - { name: "principal", model: "anthropic/claude-sonnet-5-5", chave: "ANTHROPIC_API_KEY" } # qualidade
  - { name: "rapido", model: "anthropic/claude-haiku-5-5", chave: "ANTHROPIC_API_KEY" }     # barato e ágil
  - { name: "local", model: "ollama_chat/llama3.2:3b", api_base: "http://ollama:11434" }  # privado (Ollama)
  - { name: "decisao", model: "typesafe/jev-latest", chave: "TYPESAFE_API_KEY" }          # Jev: decisões tipadas
# Se um modelo do apelido falhar, o LiteLLM tenta estes, em ordem.
llm_fallbacks:
  - { principal: ["gpt-6.1-sol"] }
  - { rapido: ["gpt-6-luna"] }
# Alerta do Grafana quando o gasto com LLM em 24 h passa deste valor (US$).
llm_gasto_diario_alerta: 5
# Orçamento mensal (US$) de cada chave virtual do LiteLLM (setup-ai-keys.yml). Estourou: o cliente recebe erro.
litellm_key_budgets:
  openwebui: 20
  claude_code: 50
  n8n: 10
# Versão do Ollama; o role ml-tools constrói localhost/homeserver/ollama-vulkan:<versão> (oficial + Mesa/RADV).
ollama_version: "0.40.6"
# Formulário de login local do Open WebUI: ligado só até vincular o admin pelo OIDC do Authelia; depois, false.
openwebui_login_form: true

# --- Segundo cérebro (página 12) ---
# Versões fixadas: imagens públicas e as locais construídas pelo setup-notes-volumes.yml.
syncthing_version: "2.1.6"
qmd_version: "2.8.3"                 # localhost/homeserver/qmd:<versão> (busca local, Vulkan)
mcp_filesystem_version: "2.0.0"      # localhost/homeserver/notes-escrita:<versão> (server-filesystem + supergateway)
supergateway_version: "4.2.0"
markitdown_version: "0.1.8"          # localhost/homeserver/notes-conversor:<versão>
mcp_auth_proxy_version: "v2.10.2"
# Usuário do painel do Syncthing (a senha fica no vault).
syncthing_gui_user: "admin"
# Id do seu usuário no Nextcloud (docker exec -u www-data nextcloud_app php occ user:list). Os arquivos dele
# (<files>/<id>/files) são convertidos para Markdown e indexados.
notes_nextcloud_usuario: "TROQUE-PELO-ID"
# Extensões convertidas (imagem, vídeo e áudio ficam de fora) e tamanho máximo por arquivo (MB).
notes_documentos_extensoes: [pdf, docx, pptx, xlsx, html, htm, csv, txt, md]
notes_documentos_max_mb: 50
# Modelos do qmd ({} = padrões do qmd). Ex.: {embed: "hf:Qwen/Qwen3-Embedding-0.6B-GGUF/Qwen3-Embedding-0.6B-Q8_0.gguf"}
qmd_modelos: {}

# --- Agentes: base (página 13) ---
# Versões fixadas: hub de MCPs, MCP do Grafana, imagem local do ops (FastMCP + ansible-core) e Langfuse.
agentgateway_version: "v1.6.0"
mcp_grafana_version: "2.1.1"
ops_fastmcp_version: "4.1.2"
ops_ansible_core_version: "2.21.5"
langfuse_version: "4.66.0"
# Rota de leitura do hub (conector Servidor, aberto pela internet): o que cada alvo pode mostrar.
# "*" = todas as ferramentas do alvo (só vale para alvos que rodam em instância somente leitura).
agents_leitura:
  grafana: "*"
  ops: "*"
  homeassistant: ["GetLiveContext"]
  n8n: ["search_workflows"]
# O ops recusa reiniciar estes containers e redeployar estas stacks (o caminho de controle da própria IA).
ops_containers_protegidos: [traefik, authelia, cloudflared, portainer, agentgateway, mcp_auth_servidor, ops_leitura, ops_controle]
ops_stacks_protegidas: [core, agents]
# Playbooks que a IA pode simular (ansible_check) e aplicar (ansible_aplicar). Fora da lista: criação de VMs,
# host Proxmox, rede core (Traefik/Authelia) e o deploy completo.
ops_playbooks_permitidos:
  - { nome: setup-base-ubuntu.yml, descricao: "Configuração base das VMs Ubuntu (pacotes, montagens NFS, Docker, Alloy)" }
  - { nome: setup-monitoring-stack-volumes.yml, descricao: "Configs de Prometheus, Grafana, alertas e Homepage" }
  - { nome: setup-n8n-volumes.yml, descricao: "Diretórios e variáveis do n8n" }
  - { nome: setup-productivity-automation-volumes.yml, descricao: "Diretórios e variáveis de Home Assistant e afins" }
  - { nome: setup-media-stack-volumes.yml, descricao: "Configs e variáveis da stack de mídia" }
  - { nome: setup-photos-stack-volumes.yml, descricao: "Configs e variáveis do Immich" }
  - { nome: setup-cloud-stack-volumes.yml, descricao: "Configs e variáveis do Nextcloud e do Collabora" }
  - { nome: setup-ai-volumes.yml, descricao: "Configs e variáveis da stack de IA (LiteLLM, Open WebUI, Ollama)" }
  - { nome: setup-ai-keys.yml, descricao: "Chaves virtuais do LiteLLM por cliente" }
  - { nome: setup-notes-volumes.yml, descricao: "Segundo cérebro: Syncthing, qmd, conversor e timers" }
  - { nome: setup-agents-volumes.yml, descricao: "Base dos agentes: config do hub, imagem do ops e agents.env" }
# Nomes dos ambientes no Portainer (Environments): a core é o 'local'; a de IA, o agente.
ops_endpoints:
  core: "local"
  ai: "ai-desktop-vm"
# Repositório que o runner do ops clona e atualiza (git pull) antes de cada execução.
ops_repo_url: "https://github.com/lioevano/wiki-home-server.git"
# Minutos em que um ansible_check vale para o ansible_aplicar.
ops_plano_validade_min: 30
# Dias de traces guardados no Langfuse.
langfuse_retencao_dias: 30
```

Com a máquina de controle Ansible devidamente configurada, o inventário definido e os segredos guardados no Vault, você está pronto para prosseguir para a próxima etapa: [Instalação e Configuração Base do Proxmox VE](02-proxmox-ve-host.md).
