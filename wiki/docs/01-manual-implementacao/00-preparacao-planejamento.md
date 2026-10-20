---
description: "Pré-requisitos, estrutura do repositório (server/, wiki/, tools/), .gitignore e modelo de variáveis das stacks antes de começar."
---

# Seção 0: Preparação e Planejamento

Antes de sair apertando botão, um planejamento cuidadoso e a preparação do ambiente são fundamentais para o sucesso do seu servidor doméstico. ~~Tipo eu que elaborei esta wiki antes mesmo de começar a implementar.~~ Esta seção aborda os pré-requisitos, a organização do projeto e considerações iniciais de segurança e resiliência.

## 0.0. Glossário de Termos Essenciais

Aqui estão algumas palavras difíceis que vão aparecer frequentemente durante a implementação:

*   **[Ansible](../05-referencia-rapida.md):** É a nossa grande ferramenta de automação. Ela automatiza configurações e instalações inteiras, criando todo o contexto para o uso a partir de código (Infraestrutura como Código - IaC).
*   **[Ansible Vault](../05-referencia-rapida.md):** Recurso do Ansible que permite criptografar arquivos YAML inteiros ou variáveis específicas que contêm dados sensíveis, como senhas e chaves de API.
*   **Cloudflare Tunnel:** Serviço da Cloudflare que cria um túnel seguro e criptografado de saída da sua rede local para a rede global da Cloudflare. Isso permite que você exponha serviços internos à internet sem abrir portas no seu roteador e sem expor seu IP público.
*   **[Container (Docker)](../05-referencia-rapida.md):** Empacota uma aplicação para rodar isolada do sistema. Atribui a ela um endereço de IP e configurações de rede, comportando-se como se fosse uma máquina virtual, ~~mas é só uma aplicação com suas dependências.~~
*   **Docker Compose:** Um arquivo no formato YAML que configura um container ou uma "stack" inteira (um conjunto de containers). Define redes (onde os containers interagem apenas com quem você definir), serviços (os próprios containers) e volumes (locais onde os dados dos containers ficam armazenados).
*   **[Proxmox VE](../05-referencia-rapida.md):** É um sistema operacional baseado em Debian, otimizado para rodar máquinas virtuais (KVM) e containers Linux (LXC). É a minha escolha para este projeto, visando a experimentação com diversas ferramentas.
*   **Portainer:** Um gerenciador de containers com interface gráfica leve e intuitiva.
*   **[Traefik](../05-referencia-rapida.md):** Proxy reverso moderno e dinâmico, e também um balanceador de carga.
*   **[ZFS](../05-referencia-rapida.md):** Sistema de arquivos avançado e gerenciador de volumes lógicos, conhecido por sua resiliência e funcionalidades.
*   **NFS (Network File System):** Protocolo para compartilhar diretórios através de uma rede. Usaremos para compartilhar datasets ZFS do host Proxmox com as VMs para os volumes Docker.
*   **Ollama:** Plataforma para rodar e gerenciar modelos de linguagem grandes (LLMs) localmente.
*   **VM (Máquina Virtual):** Emulação de um sistema de computador completo, rodando seu próprio sistema operacional.
*   **RAG (Retrieval Augmented Generation):** Técnica de Inteligência Artificial que combina as capacidades de LLMs com a busca de informação em uma base de dados externa para gerar respostas mais contextuais e precisas.
*   **[Authelia](../05-referencia-rapida.md):** Servidor de autenticação e autorização, usado aqui para fornecer Single Sign-On (SSO) e autenticação de dois fatores (2FA).

## 0.1. Hardware e Software Necessários

Para esta implementação, estou utilizando o seguinte setup:

### Hardware do Servidor Físico (Host Proxmox)

*   **CPU:** AMD Ryzen 5 5600G (com iGPU Vega e suporte a virtualização AMD-V).
*   **GPU (para passthrough):** AMD RX 5600XT.
*   **RAM:** **48GB DDR4**.
!!! note "Upgrade de RAM"
    Os 48GB permitem 16GB para cada VM (`core-services-vm` e `ai-desktop-vm`) e ainda sobram para o host e o cache ARC do ZFS.
*   **Armazenamento Primário (Proxmox OS e Discos das VMs):** SSD NVMe 1TB.
*   **Armazenamento Secundário (Pool de Dados ZFS `/data`):** 2x HDDs de 500GB. Serão configurados em um pool ZFS espelhado (RAID 1) para redundância.
!!! note "Espaço Útil ZFS para Dados"
    Com 2x HDDs de 500GB em espelho (RAID 1), você terá aproximadamente **500GB de espaço útil** para os dados das suas aplicações Docker (configs, mídia, downloads, etc.). Planeje de acordo.

### Máquina de Controle Ansible

Para esta função, você precisará de uma máquina secundária (ou sua máquina principal) para executar os comandos Ansible remotamente.

*   Um computador pessoal ou notebook.
*   **Sistema Operacional Suportado:**
    *   Linux (Ubuntu, Fedora, etc.)
    *   macOS
    *   Windows com WSL2 (Windows Subsystem for Linux 2)

### Rede Doméstica

*   Roteador com servidor DHCP habilitado (para atribuição inicial de IPs, embora usemos IPs estáticos para os servidores).
*   Conexão à Internet.

### Software e Contas (Antes de Iniciar)

*   **ISO do Proxmox VE:** Baixe a versão estável mais recente do [site oficial do Proxmox](https://www.proxmox.com/en/downloads).
*   **Ferramenta para Pendrive Bootável:**
    *   [Ventoy](https://www.ventoy.net/en/download.html) (Windows, macOS, Linux) _<- Minha escolha pessoal pela flexibilidade._
    *   [Rufus](https://rufus.ie/) (Windows)
    *   [Balena Etcher](https://www.balena.io/etcher/) (Windows, macOS, Linux)
*   **Cliente SSH:**
    *   OpenSSH (nativo em Linux e macOS).
    *   PuTTY (popular para Windows, ou use o cliente SSH nativo do Windows Terminal/PowerShell).
    *   **Domínio Próprio Registrado:** (e.g., `seudominio.com`)
    !!! important "Domínio Próprio é Essencial"
        Este guia depende de um domínio próprio para acesso externo seguro via Cloudflare Tunnel e para a correta emissão de certificados SSL/TLS.
    *   **Conta Cloudflare:** Crie uma [conta gratuita na Cloudflare](https://www.cloudflare.com/).
    *   Você precisará configurar seu domínio para usar os **nameservers da Cloudflare**.

## 0.2. Estrutura do Repositório Git do Projeto (`homeserver`)

Graças ao Ansible, vamos adotar a Infraestrutura como Código (IaC), gerenciando todas as configurações e scripts em um repositório Git.

### Estrutura de Diretórios Proposta

A estrutura do repositório é:
```text
homeserver/                 # repositório lioevano/wiki-home-server
├── server/                 # implementação (reflete a wiki)
│   ├── ansible/
│   │   ├── ansible.cfg
│   │   ├── inventories/home/
│   │   │   ├── hosts.ini
│   │   │   └── group_vars/all/
│   │   │       ├── main.yml
│   │   │       ├── vault.yml.example   # modelo versionado
│   │   │       └── vault.yml           # criptografado (ansible-vault)
│   │   ├── playbooks/          # setup-*.yml, vm-deploy.yml, full-deploy.yml
│   │   ├── roles/
│   │   │   ├── common/
│   │   │   ├── infra/          # docker, proxmox-host-config, proxmox-vm, traefik-config, authelia-config
│   │   │   ├── apps/           # desktop-environment, ml-tools
│   │   │   └── tools/          # ai-cli-tools
│   │   └── templates/          # prometheus, loki, grafana, homepage, litellm, portainer_stack_env
│   ├── docker/stacks/
│   │   ├── .env.template
│   │   ├── core/               # Traefik, Cloudflared, Authelia
│   │   ├── apps/               # Nextcloud, mídia, monitoramento, n8n, Home Assistant
│   │   └── ai/                 # LiteLLM (+ Postgres), Ollama, Open WebUI, Diun
│   └── scripts/
│       ├── bootstrap.sh
│       ├── restore.sh
│       └── validation/
├── wiki/                   # esta documentação (MkDocs): mkdocs.yml, docs/
├── tools/                  # dev.py (tarefas) e wikisync (wiki -> server)
├── .agents/skills/         # skills canônicas (agnósticas de LLM)
├── .claude/skills/         # invólucros das skills para o Claude Code
├── AGENTS.md               # entrada canônica para agentes (CLAUDE.md só importa)
├── CLAUDE.md
├── INDEX.md                # mapa do repositório (mantido pela skill update-index)
├── .gitignore
└── README.md
```

!!! info "Convenções usadas na wiki"
    *   **Comandos Ansible** rodam a partir da pasta `server/ansible` (onde está o `ansible.cfg`), na forma `ansible-playbook -i inventories/home/hosts.ini playbooks/<playbook>.yml`. Caminhos de arquivos do server são relativos a `server/` (ex.: `ansible/playbooks/...`, `docker/stacks/...`).
    *   **Domínio:** no texto, `seudominio.com` representa o seu domínio; nos templates Jinja e blocos literais aparece `{{ base_domain }}`.
    *   **Rede:** os exemplos usam a LAN `192.168.15.0/24` (host Proxmox `192.168.15.66`, `core-services-vm` `192.168.15.67`, `ai-desktop-vm` `192.168.15.68`, como no `hosts.ini`).

### Ações Imediatas para Estruturação do Projeto

Na sua máquina de controle Ansible:

1.  **Clone o repositório** (ou um fork seu) e entre nele:
```bash
git clone https://github.com/lioevano/wiki-home-server.git homeserver && cd homeserver
```
2.  **Começando do zero, sem clonar:** crie a pasta e inicialize o Git:
```bash
mkdir homeserver && cd homeserver && git init
```
3.  **Crie a estrutura de diretórios** da árvore acima (o clone já a traz). Use `mkdir -p` para eficiência.
Exemplo parcial:
```bash
mkdir -p server/ansible/inventories/home/group_vars/all server/ansible/playbooks server/ansible/roles/common server/docker/stacks/core server/scripts wiki/docs
```
4.  **Crie o arquivo `.gitignore` com o seguinte conteúdo:**
```gitignore title=".gitignore (raiz do repositório)"
# Ambientes Python
.venv/
venv/
wiki/venv/
__pycache__/
*.pyc
.pytest_cache/

# Build da wiki
wiki/site/
site/

# Ansible
*.retry
*.safe
.ansible/
# vault.yml é versionado SOMENTE criptografado; cópias abertas nunca:
*.decrypted*

# Docker: .env reais (com segredos) nunca são versionados; o .env.template sim.
.env
server/docker/stacks/.env
server/docker/stacks/*/.env

# Rascunho de execução do Claude (superpowers)
.superpowers/

# Sistema operacional e editores
.DS_Store
Thumbs.db
.vscode/
.idea/
```

5.  **Crie o modelo de variáveis das stacks Docker** em `docker/stacks/.env.template`. Ele documenta todas as variáveis `${...}` usadas pelos `docker-compose.yml`; os `.env` reais (gerados pelo Ansible) nunca são versionados.

```bash title="docker/stacks/.env.template"
# docker/stacks/.env.template
# Contrato de variáveis usadas pelos docker-compose.yml das stacks (core, apps, ai, notes).
# Este MODELO pode ser versionado; os arquivos .env REAIS nunca são commitados.
# Em produção, os .env das stacks apps e ai são gerados pelo Ansible (templates/portainer_stack_env.j2,
# playbooks setup-*-volumes.yml); a stack core recebe as variáveis no playbook setup-core-networking.yml.

# --- Comuns ---
SYSTEM_TIMEZONE=America/Sao_Paulo
BASE_DOMAIN_FROM_VAULT=
DOCKER_PUID=1000
DOCKER_PGID=1000
CORE_SERVICES_VM_IP_VAR=
VM_NFS_MOUNT_BASE_PATH=/mnt/pve_data_zfs
ZFS_DOCKER_VOLUMES_DATASET_NAME=docker-volumes

# --- Stack core (Traefik, Cloudflared, Authelia) ---
CLOUDFLARE_API_TOKEN_FROM_VAULT=
CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT=
AUTHELIA_STORAGE_POSTGRES_PASSWORD_FROM_VAULT=

# --- Stack cloud (Nextcloud, cron, Collabora; página 11) ---
# Banco no disco local da VM; dados no dataset files (NFS).
NEXTCLOUD_MAJOR=
CLOUD_STACK_NEXTCLOUD_HTML_PATH=
CLOUD_STACK_NEXTCLOUD_CONFIG_PATH=
CLOUD_STACK_NEXTCLOUD_HOOKS_PATH=
CLOUD_STACK_NEXTCLOUD_DATA_PATH=
CLOUD_STACK_NEXTCLOUD_DB_PATH=
NEXTCLOUD_DB_PASSWORD_FROM_PORTAINER_ENV=
NEXTCLOUD_ADMIN_PASSWORD_FROM_PORTAINER_ENV=
NEXTCLOUD_OIDC_CLIENT_SECRET=

# --- Stack media (Jellyfin, Seerr, Sonarr, Radarr, Lidarr, Prowlarr, Bazarr, Recyclarr, gluetun, qBittorrent) ---
# /data: dataset único de mídia (torrents/ e media/), para importar por hardlink.
MEDIA_STACK_DATA_PATH=
MEDIA_STACK_JELLYFIN_CONFIG_PATH=
MEDIA_STACK_SEERR_CONFIG_PATH=
MEDIA_STACK_SONARR_CONFIG_PATH=
MEDIA_STACK_RADARR_CONFIG_PATH=
MEDIA_STACK_LIDARR_CONFIG_PATH=
MEDIA_STACK_PROWLARR_CONFIG_PATH=
MEDIA_STACK_BAZARR_CONFIG_PATH=
MEDIA_STACK_GLUETUN_CONFIG_PATH=
MEDIA_STACK_QBITTORRENT_CONFIG_PATH=
MEDIA_STACK_RECYCLARR_CONFIG_PATH=
SONARR_API_KEY=
RADARR_API_KEY=
LIDARR_API_KEY=
PROWLARR_API_KEY=
PROTONVPN_WIREGUARD_PRIVATE_KEY=

# --- Stack photos (Immich; página 11) ---
# Banco e cache de modelos no disco local da VM; uploads no dataset photos (NFS).
IMMICH_VERSION=
PHOTOS_STACK_UPLOAD_PATH=
PHOTOS_STACK_CONFIG_PATH=
PHOTOS_STACK_DB_PATH=
PHOTOS_STACK_MODEL_CACHE_PATH=
IMMICH_DB_PASSWORD=

# --- Stack apps: monitoramento (Prometheus, Grafana, Loki, blackbox, Diun, Homepage) ---
MONITORING_PROMETHEUS_CONFIG_PATH=
MONITORING_PROMETHEUS_DATA_PATH=
MONITORING_GRAFANA_DATA_PATH=
MONITORING_GRAFANA_DB_PATH=
MONITORING_GRAFANA_PROVISIONING_PATH=
MONITORING_LOKI_CONFIG_PATH=
MONITORING_LOKI_DATA_PATH=
MONITORING_BLACKBOX_CONFIG_PATH=
MONITORING_DIUN_DATA_PATH=
MONITORING_HOMEPAGE_CONFIG_PATH=

# --- Painel (Homepage): credenciais dos widgets ---
HOMEPAGE_VAR_JELLYFIN_KEY=
HOMEPAGE_VAR_RADARR_KEY=
HOMEPAGE_VAR_SONARR_KEY=
HOMEPAGE_VAR_LIDARR_KEY=
HOMEPAGE_VAR_PROWLARR_KEY=
HOMEPAGE_VAR_BAZARR_KEY=
HOMEPAGE_VAR_SEERR_KEY=
HOMEPAGE_VAR_NEXTCLOUD_KEY=
HOMEPAGE_VAR_IMMICH_KEY=
HOMEPAGE_VAR_HOMEASSISTANT_KEY=
HOMEPAGE_VAR_PORTAINER_KEY=
HOMEPAGE_VAR_QBITTORRENT_USER=
HOMEPAGE_VAR_QBITTORRENT_PASSWORD=
HOMEPAGE_VAR_GRAFANA_PASSWORD=

# --- Notificações (Telegram via n8n; também usadas pelo Grafana e pelo Diun) ---
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
NOTIFICACOES_WEBHOOK_TOKEN=
GRAFANA_DB_PASSWORD_FROM_PORTAINER_ENV=
GRAFANA_ADMIN_INITIAL_PASSWORD_FROM_PORTAINER_ENV=

# --- Stack apps: automação (n8n, Home Assistant) ---
N8N_SUBDOMAIN=n8n
N8N_CONFIG_PATH=
AUTO_STACK_HOMEASSISTANT_CONFIG_PATH=

# --- Stack ai (LiteLLM + Postgres, Ollama com Vulkan, Open WebUI, Diun; página 08) ---
AI_DESKTOP_VM_IP=
AI_STACK_LITELLM_CONFIG_PATH=
AI_STACK_LITELLM_DB_PATH=
AI_STACK_OLLAMA_MODELS_PATH=
AI_STACK_OPENWEBUI_DATA_PATH=
AI_STACK_DIUN_DATA_PATH=
AI_RENDER_GID=
OLLAMA_IMAGE=
LITELLM_MASTER_KEY=
LITELLM_DB_PASSWORD=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
TYPESAFE_API_KEY=
LITELLM_KEY_OPENWEBUI=
OPENWEBUI_SECRET_KEY=
OPENWEBUI_OAUTH_CLIENT_SECRET=
OPENWEBUI_LOGIN_FORM=

# --- Stack notes (segundo cérebro: Syncthing, qmd, escrita, mcp-auth-proxy; página 12) ---
CORE_SERVICES_VM_IP=
NOTES_STACK_DATA_PATH=
NOTES_STACK_SYNCTHING_CONFIG_PATH=
NOTES_STACK_SYNCTHING_DB_PATH=
NOTES_STACK_QMD_CONFIG_PATH=
NOTES_STACK_QMD_CACHE_PATH=
NOTES_STACK_DOCUMENTOS_PATH=
NOTES_STACK_MCP_AUTH_BUSCA_PATH=
NOTES_STACK_MCP_AUTH_ESCRITA_PATH=
QMD_IMAGE=
NOTES_ESCRITA_IMAGE=
SYNCTHING_API_KEY=
MCP_OIDC_CLIENT_SECRET=
MCP_AUTH_HMAC_SECRET=

# --- Stack agents (base dos agentes: hub, mcp-grafana, ops; core-services-vm; página 13) ---
CORE_SERVICES_VM_IP_VAR=
AI_DESKTOP_VM_IP=
OPS_IMAGE=
OPS_DATA_PATH=
OPS_ENDPOINTS=
OPS_CONTAINERS_PROTEGIDOS=
OPS_STACKS_PROTEGIDAS=
OPS_PLAYBOOKS=
PORTAINER_API_KEY=
GRAFANA_SA_TOKEN_LEITURA=
GRAFANA_SA_TOKEN_CONTROLE=
NOTIFICACOES_WEBHOOK_TOKEN=
AGENTGATEWAY_CONFIG_PATH=
AGENTGATEWAY_DATA_PATH=
MCP_AUTH_SERVIDOR_DATA_PATH=
AGENTS_TOKEN_BACKENDS=
AGENTS_TOKEN_PROXY=

# --- Stack langfuse (rastreio; ai-desktop-vm; página 13) e callback do LiteLLM (stack ai) ---
LANGFUSE_DATA_PATH=
LANGFUSE_SALT=
LANGFUSE_ENCRYPTION_KEY=
LANGFUSE_NEXTAUTH_SECRET=
LANGFUSE_DB_PASSWORD=
LANGFUSE_CLICKHOUSE_PASSWORD=
LANGFUSE_REDIS_PASSWORD=
LANGFUSE_MINIO_PASSWORD=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_OIDC_CLIENT_SECRET=
LANGFUSE_OTEL_HOST=
LANGFUSE_OTEL_AUTH=
```
!!! important "Segurança de Segredos com .gitignore"
    O arquivo `ansible/inventories/home/group_vars/all/vault.yml` conterá segredos e só é versionado **criptografado** (começa com `$ANSIBLE_VAULT;`); por isso ele não está no `.gitignore`. Cópias abertas (`*.decrypted*`) são bloqueadas pelo `.gitignore`. Arquivos `.env` reais com segredos (gerados pelo Ansible nas VMs) **NUNCA** devem ser commitados.
5.  **Crie um arquivo `README.md` inicial** na raiz do projeto com uma breve descrição.
6.  **Adicione todos os arquivos criados e faça o primeiro commit:**
```bash
git add .
git commit -m "Estrutura inicial do projeto homeserver e IaC"
```
7.  **(Recomendado)** Configure um repositório Git remoto (e.g., GitHub, GitLab) e envie (`push`) suas alterações.

## 0.3. Considerações de Segurança e Resiliência

Estes são os pilares que sustentam a arquitetura:

*   **Segurança:**
    *   **Princípio do Menor Privilégio:** Cada componente e usuário terá apenas as permissões estritamente necessárias.
    *   **Atualizações Constantes:** Manteremos Proxmox, VMs, imagens Docker e aplicações atualizadas.
    *   **Senhas Fortes e Únicas:** Gerenciadas pelo Ansible Vault para a infraestrutura e um gerenciador pessoal para contas de usuário.
    *   **Autenticação de Dois Fatores (2FA):** Implementada com Authelia para proteger o acesso aos serviços.
    *   **Isolamento de Rede e Firewall:** Uso de redes Docker distintas e firewalls (Proxmox PVE Firewall e UFW nas VMs).
*   **Resiliência:**
    *   **Estratégia de Backup 3-2-1:** Pelo menos 3 cópias dos dados, em 2 mídias diferentes, com 1 cópia off-site. Detalhado na [Seção de Manutenção e Recuperação](../04-manutencao-recuperacao/index.md).
    *   **ZFS para Proteção de Dados Local:** O pool `/data` com RAID 1 e snapshots ZFS.
    *   **Monitoramento:** Acompanhamento da saúde do sistema para detecção proativa de problemas.
    *   **Infraestrutura como Código (IaC):** Ansible permite reconstruir a infraestrutura de forma consistente e rápida.

Com este planejamento e estrutura inicial, você está pronto para avançar para a configuração da sua [Máquina de Controle Ansible](01-maquina-controle-ansible.md).

