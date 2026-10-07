# Seção 5: Implementação da Rede Segura (Traefik, Cloudflare Tunnel, Authelia)

Esta seção é fundamental para expor seus serviços auto-hospedados à internet de forma segura, controlada e gerenciada. Implementaremos uma stack de rede robusta na `core-services-vm` composta por:

* **Traefik Proxy:** Atuará como nosso proxy reverso, roteando o tráfego externo para os containers Docker corretos e gerenciando automaticamente os certificados SSL/TLS com Let's Encrypt.
* **Cloudflare Tunnel (`cloudflared`):** Criará uma conexão de saída segura da nossa rede local para a rede global da Cloudflare. Isso elimina a necessidade de abrir portas no roteador doméstico e protege nosso endereço IP público.
* **Authelia:** Servirá como um portal de autenticação e autorização centralizado, adicionando uma camada de segurança com Single Sign-On (SSO) e autenticação de dois fatores (2FA) para os serviços que escolhermos proteger.

Todos esses componentes rodarão como containers Docker na `core-services-vm`, gerenciados via Docker Compose e, posteriormente, Portainer.

## 5.1. Entendendo o Fluxo de Tráfego e o Conceito de Proxy Reverso

Antes de mergulharmos na configuração, é vital entender como o tráfego de um usuário externo alcançará seus serviços internos:

1. **Requisição do Usuário:** O usuário digita `https://meuservico.{{ base_domain }}` no navegador (e.g., `https://nextcloud.meuhomelab.com`).
2. **Resolução DNS via Cloudflare:** Os nameservers do seu domínio estão configurados para a Cloudflare. A Cloudflare não resolverá o subdomínio para o seu IP doméstico, mas para um endpoint da rede Cloudflare associado ao seu Cloudflare Tunnel.
3. **Cloudflare Edge Network:** A requisição do usuário chega à rede global da Cloudflare. Aqui, ela pode se beneficiar de proteções como mitigação de DDoS e Web Application Firewall (WAF) básico da Cloudflare. Seu IP doméstico real permanece oculto.
4. **Cloudflare Tunnel (`cloudflared` Agent):** O container `cloudflared` rodando na sua `core-services-vm` mantém uma conexão de **saída** persistente e criptografada com o data center da Cloudflare mais próximo. O tráfego destinado aos seus subdomínios configurados no túnel é "puxado" do Cloudflare Edge, através desta conexão segura, para o container `cloudflared` na sua rede local. **Nenhuma porta de entrada precisa ser aberta no seu roteador doméstico.**
5. **`cloudflared` para Traefik:** O container `cloudflared` recebe o tráfego do túnel e o encaminha para o container Traefik. No nosso `docker-compose.yml`, o `cloudflared` é configurado para enviar o tráfego para o serviço Docker `traefik` na porta `80` (dentro da rede Docker `proxy` compartilhada).
6. **Traefik (Proxy Reverso):**
    * Traefik escuta nas portas `80` (HTTP) e `443` (HTTPS) na `core-services-vm` (mapeadas do host da VM para o container Traefik).
    * **Redirecionamento HTTP para HTTPS:** Traefik está configurado para redirecionar automaticamente todo o tráfego chegando na porta `80` para HTTPS na porta `443`.
    * **Roteamento Baseado em Host:** Traefik inspeciona o cabeçalho `Host` da requisição HTTP (e.g., `nextcloud.meuhomelab.com`).
    * **Middleware de Autenticação (Authelia):** Se a rota do Traefik para o serviço estiver configurada com o middleware Authelia (e.g., `authelia@docker`), Traefik primeiro consulta o container Authelia para verificar a autenticação do usuário.
        * Se o usuário não estiver logado, Authelia instrui Traefik a redirecionar o usuário para o portal de login do Authelia (e.g., `https://auth.meuhomelab.com`).
        * Após o login bem-sucedido (incluindo 2FA), Authelia estabelece uma sessão (via cookie) e informa ao Traefik que o usuário está autenticado.
    * **Gerenciamento de Certificados SSL/TLS (Let's Encrypt):** Traefik automaticamente solicita, renova e gerencia certificados SSL/TLS da Let's Encrypt para todos os seus subdomínios expostos. Ele utiliza o **desafio DNS-01** com a API da Cloudflare (usando o token API que configuraremos), o que é robusto e não requer que portas HTTP estejam abertas para o mundo. Os certificados são armazenados no arquivo `acme.json` (em um volume NFS).
    * **Roteamento para o Serviço Docker de Destino:** Com base nas *labels* Docker definidas no `docker-compose.yml` do serviço de destino (e após autenticação bem-sucedida, se aplicável), Traefik encaminha a requisição para o container Docker correto e sua porta interna.
7. **Serviço Docker:** O container da aplicação (e.g., Nextcloud) processa a requisição e envia a resposta de volta pelo mesmo caminho.

!!! tip "Diagrama Visual do Fluxo"
    Para uma representação gráfica detalhada deste fluxo, consulte o diagrama na seção [Fluxo de Rede e Acesso Externo da Visão Geral da Arquitetura](../02-visao-geral-arquitetura/01-fluxo-rede-acesso-externo.md).

## 5.2. Docker Compose para a Stack Core (`docker/stacks/core/docker-compose.yml`)

Esta stack fundamental inclui os containers Traefik e Cloudflared. Crie o arquivo `home-server/docker/stacks/core/docker-compose.yml` com o seguinte conteúdo:

```yaml
# docker/stacks/core/docker-compose.yml
version: '3.9'

networks:
  proxy: # Rede para Traefik e serviços expostos
    name: proxy # Nome da rede que foi criada pelo Ansible na Seção 4.2
    external: true # Indica que a rede 'proxy' já existe e será usada por esta stack

services:
  traefik:
    image: traefik:v2.11.2 # Use uma versão específica e estável. Verifique por atualizações.
    container_name: traefik
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true # Boa prática de segurança, impede escalação de privilégios
    networks:
      - proxy # Conecta Traefik à rede proxy
    ports:
      # Mapeia as portas do Traefik no IP da core-services-vm.
      # A variável ${CORE_SERVICES_VM_IP_VAR} virá do arquivo .env carregado pelo Portainer.
      - "${CORE_SERVICES_VM_IP_VAR}:80:80"   # HTTP (será redirecionado para HTTPS por Traefik)
      - "${CORE_SERVICES_VM_IP_VAR}:443:443" # HTTPS (ponto de entrada principal para serviços)
      # - "${CORE_SERVICES_VM_IP_VAR}:8080:8080" # Opcional: Se você quiser expor a API/Dashboard do Traefik
                                               # diretamente nesta porta, mas é melhor expô-la via rota segura HTTPS.
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock:ro" # Permite Traefik detectar containers Docker e suas labels
      # Caminhos para configs e certs DENTRO DA VM (que são montagens NFS do host Proxmox).
      # As variáveis (e.g., ${VM_NFS_MOUNT_BASE_PATH}) virão do .env.
      - "${VM_NFS_MOUNT_BASE_PATH}/${ZFS_DOCKER_VOLUMES_DATASET_NAME}/traefik/data:/data" # Para acme.json (certificados SSL) e logs Traefik
      - "${VM_NFS_MOUNT_BASE_PATH}/${ZFS_DOCKER_VOLUMES_DATASET_NAME}/traefik/config/traefik.yml:/traefik.yml:ro" # Configuração estática do Traefik (readonly)
      - "${VM_NFS_MOUNT_BASE_PATH}/${ZFS_DOCKER_VOLUMES_DATASET_NAME}/traefik/config/dynamic:/etc/traefik/dynamic_configs:ro" # Configs dinâmicas (middlewares, etc., readonly)
      - "/etc/localtime:/etc/localtime:ro" # Sincroniza o fuso horário do container com o da VM
    environment:
      # Token da API Cloudflare para o desafio DNS-01 (Let's Encrypt).
      # Esta variável ${CLOUDFLARE_API_TOKEN_FROM_VAULT} será injetada pelo .env
      # (que por sua vez é preenchido por Ansible com o valor do vault.yml).
      - CF_DNS_API_TOKEN=${CLOUDFLARE_API_TOKEN_FROM_VAULT}
      # Algumas configurações DNS podem exigir o email ou um token API específico da zona.
      # Para DNS Challenge com API Token global, apenas CF_DNS_API_TOKEN é geralmente necessário.
      # - CF_API_EMAIL=${LETSENCRYPT_EMAIL_FROM_VAULT}
      # - CF_ZONE_API_TOKEN=${CLOUDFLARE_ZONE_API_TOKEN_FROM_VAULT} # Se usar token específico da zona
    labels:
      # --- Labels para Traefik gerenciar o próprio Traefik (Dashboard) ---
      traefik.enable: "true" # Permite Traefik gerenciar este container (ele mesmo)
      # Roteador para o Dashboard do Traefik
      traefik.http.routers.traefik-dashboard.rule: "Host(`traefik.${BASE_DOMAIN_FROM_VAULT}`)" # ${BASE_DOMAIN_FROM_VAULT} do .env
      traefik.http.routers.traefik-dashboard.entrypoints: "websecure" # Acessível apenas via HTTPS
      traefik.http.routers.traefik-dashboard.service: "api@internal" # Serviço interno especial do Traefik para o dashboard/API
      traefik.http.routers.traefik-dashboard.tls.certresolver: "letsencrypt" # Usar Let's Encrypt
      traefik.http.routers.traefik-dashboard.middlewares: "authelia@docker" # Proteger o dashboard com Authelia
    healthcheck: # Define um healthcheck para o container Traefik
      test: ["CMD", "traefik", "healthcheck", "--ping"] # Comando para verificar a saúde
      interval: 10s # Intervalo entre verificações
      timeout: 2s   # Timeout para a verificação
      retries: 3    # Número de tentativas antes de marcar como "unhealthy"
      start_period: 15s # Período inicial de tolerância antes de falhas no healthcheck contarem

  cloudflared:
    image: cloudflare/cloudflared:2024.5.0 # Use uma versão específica e estável. Verifique por atualizações.
    container_name: cloudflared
    restart: unless-stopped
    networks:
      - proxy # Precisa estar na mesma rede que Traefik para poder encaminhar tráfego para ele
    # O comando para rodar o túnel.
    # O token ${CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT} será injetado pelo .env.
    # A flag `--url http://traefik:80` direciona todo o tráfego do túnel para o serviço Docker 'traefik' na porta 80.
    # A flag `--hostname ${BASE_DOMAIN_FROM_VAULT}` tenta registrar este hostname (e um wildcard) para o túnel.
    # Se você preferir gerenciar os Ingress Rules (Public Hostnames) exclusivamente no dashboard da Cloudflare,
    # remova `--hostname` e `--url`, e use apenas 'run --token ${CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT}'.
    command: tunnel --no-autoupdate --metrics 0.0.0.0:2000 --protocol http2 --hostname ${BASE_DOMAIN_FROM_VAULT} --url http://traefik:80 run --token ${CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT}
    # Exemplo de comando para Ingress Rules gerenciadas no dashboard Cloudflare:
    # command: tunnel --no-autoupdate --metrics 0.0.0.0:2000 run --token ${CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT}
    # E então, no Cloudflare Zero Trust Dashboard > Access > Tunnels > Seu Túnel > Public Hostnames:
    # - Hostname: app.seudominio.com, Service: http://traefik:80
    # - Hostname: *.seudominio.com, Service: http://traefik:80 (para um catch-all)
    depends_on: # Garante que Traefik esteja saudável antes de iniciar cloudflared
      traefik:
        condition: service_healthy # Espera o healthcheck do Traefik passar
```

!!! note "Variáveis de Ambiente no Docker Compose"
    Variáveis como `${CORE_SERVICES_VM_IP_VAR}`, `${VM_NFS_MOUNT_BASE_PATH}`, `${ZFS_DOCKER_VOLUMES_DATASET_NAME}`, `${CLOUDFLARE_API_TOKEN_FROM_VAULT}`, `${BASE_DOMAIN_FROM_VAULT}`, e `${CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT}` são placeholders que serão substituídos:
    *Pelo Ansible quando ele gerar um arquivo `.env` para esta stack na `core-services-vm`.
    *   Ou, se você não usar um `.env` gerado por Ansible para esta stack específica, você precisaria definir essas variáveis diretamente como "Environment variables" da stack no Portainer. O método recomendado é via arquivo `.env` preparado por Ansible para consistência.

## 5.3. Authelia (parte de `docker/stacks/core/docker-compose.yml`)

Authelia fornecerá o portal de autenticação e o serviço de 2FA. O conteúdo está incluído em `docker/stacks/core/docker-compose.yml` junto com Traefik e Cloudflared.
```yaml
# docker/stacks/core/docker-compose.yml (serviços Authelia)
version: '3.9'

networks:
  proxy: # Para Traefik alcançar o portal Authelia e o endpoint de verificação
    name: proxy
    external: true
  internal_services: # Rede para o banco de dados PostgreSQL do Authelia
    name: internal_services
    external: true

services:
  authelia:
    image: authelia/authelia:4.38.0 # Use uma versão específica e estável. Verifique por atualizações.
    container_name: authelia
    restart: unless-stopped
    volumes:
      # Caminho NFS para as configurações do Authelia.
      # As variáveis ${VM_NFS_MOUNT_BASE_PATH} e ${ZFS_DOCKER_VOLUMES_DATASET_NAME} virão do .env.
      - "${VM_NFS_MOUNT_BASE_PATH}/${ZFS_DOCKER_VOLUMES_DATASET_NAME}/authelia/config:/config"
      - "/etc/localtime:/etc/localtime:ro" # Sincroniza fuso horário
    networks:
      - proxy
      - internal_services
    expose:
      # Expõe a porta interna do Authelia para outros containers na mesma rede Docker,
      # mas não a mapeia para o host da VM. Traefik acessará esta porta.
      - "9091"
    environment:
      - TZ=${SYSTEM_TIMEZONE_FROM_VAULT} # Injetado pelo .env
      # Outras variáveis de ambiente podem ser definidas aqui se o configuration.yml do Authelia
      # estiver configurado para lê-las (e.g., segredos, embora seja melhor no config.yml).
      # AUTHELIA_JWT_SECRET: ${AUTHELIA_JWT_SECRET_FROM_VAULT} # Exemplo
      # AUTHELIA_SESSION_SECRET: ${AUTHELIA_SESSION_SECRET_FROM_VAULT} # Exemplo
    depends_on: # Garante que o banco de dados esteja saudável antes de iniciar Authelia
      authelia_db:
        condition: service_healthy
    labels: # Labels Traefik para expor o portal Authelia e definir o middleware de autenticação
      traefik.enable: "true"
      # --- Roteador para o portal Authelia (e.g., auth.meuhomelab.com) ---
      traefik.http.routers.authelia-portal.rule: "Host(`auth.${BASE_DOMAIN_FROM_VAULT}`)"
      traefik.http.routers.authelia-portal.entrypoints: "websecure"
      traefik.http.routers.authelia-portal.tls.certresolver: "letsencrypt"
      traefik.http.routers.authelia-portal.service: "authelia-svc"
      # --- Serviço Traefik para o portal Authelia ---
      traefik.http.services.authelia-svc.loadbalancer.server.port: "9091" # Porta interna do Authelia
      # --- Middleware de Forward Authentication Authelia ---
      # Este middleware será referenciado por outros serviços que precisam ser protegidos.
      # O nome 'authelia@docker' é como outros containers (via suas labels) referenciarão este middleware.
      traefik.http.middlewares.authelia.forwardauth.address: "http://authelia:9091/api/verify?rd=https://auth.${BASE_DOMAIN_FROM_VAULT}/"
      traefik.http.middlewares.authelia.forwardauth.trustForwardHeader: "true" # Confia nos headers X-Forwarded-* do Traefik
      traefik.http.middlewares.authelia.forwardauth.authResponseHeaders: "Remote-User,Remote-Groups,Remote-Name,Remote-Email" # Headers a serem passados para o serviço backend após auth

  authelia_db: # Banco de dados PostgreSQL para Authelia
    image: postgres:15.6-alpine # Use uma versão específica e estável.
    container_name: authelia_db
    restart: unless-stopped
    volumes:
      # Caminho NFS para os dados do banco de dados do Authelia. As variáveis virão do .env.
      - "${VM_NFS_MOUNT_BASE_PATH}/${ZFS_DOCKER_VOLUMES_DATASET_NAME}/authelia/db_pg:/var/lib/postgresql/data"
    networks:
      - internal_services # Apenas na rede interna, não acessível diretamente pelo Traefik ou externamente
    environment:
      - POSTGRES_DB=authelia
      - POSTGRES_USER=authelia
      - POSTGRES_PASSWORD=${AUTHELIA_STORAGE_POSTGRES_PASSWORD_FROM_VAULT} # Injetado pelo .env
      - TZ=${SYSTEM_TIMEZONE_FROM_VAULT} # Injetado pelo .env
    healthcheck: # Verifica se o banco de dados PostgreSQL está pronto para aceitar conexões
      test: ["CMD-SHELL", "pg_isready -U authelia -d authelia -h localhost"] # -h localhost pois roda dentro do container
      interval: 10s
      timeout: 5s
      retries: 5
```

## 5.4. Playbook `ansible/playbooks/setup-core-networking.yml`

Este playbook Ansible orquestra a preparação dos arquivos de configuração e o deploy das stacks `core` e `authelia`.

**Principais Ações do Playbook:**

  1. **Cria Redes Docker:** Garante que as redes `proxy` e `internal_services` existam na `core-services-vm`.
  2. **Executa Role `infra/traefik-config`:**
      * Cria os diretórios de configuração e dados para Traefik no volume NFS.
      * Copia o `traefik.yml` (config estática) templateado.
      * Copia os arquivos de configuração dinâmica (middlewares como `security_headers.yml`, `nextcloud_middleware.yml`, e o roteamento para RAG services `rag_services.yml`) para o diretório apropriado.
      * Garante que o arquivo `acme.json` (para certificados SSL) exista com as permissões corretas.
  3. **Deploy da Stack `core`:** Usa o módulo `community.docker.docker_compose_v2` para fazer deploy da stack `core` (Traefik, Cloudflared), injetando as variáveis de ambiente necessárias do Ansible Vault/`main.yml`.
  4. **Aguarda Traefik:** Espera o healthcheck do Traefik passar antes de prosseguir.
  5. **Executa Role `infra/authelia-config`:**
      * Cria o diretório de configuração para Authelia no volume NFS.
      * Copia o `configuration.yml` e `users_database.yml` (exemplo) templateados.
  6. **Deploy da Stack `authelia`:** Usa `community.docker.docker_compose_v2` para fazer deploy da stack `authelia` (Authelia app, Authelia DB), injetando as variáveis de ambiente.

### Ações Preparatórias: Roles Ansible para Configuração

Antes de criar o playbook, precisamos dos roles que preparam os arquivos de configuração.

#### Role: `ansible/roles/infra/traefik-config/`

Este role prepara os arquivos de configuração do Traefik.

##### `tasks/main.yml`

```yaml
# ansible/roles/infra/traefik-config/tasks/main.yml
- name: "Garantir que diretórios de configuração do Traefik existam na VM (via NFS)"
  ansible.builtin.file:
    path: "{{ item }}"
    state: directory
    owner: "{{ docker_puid }}" # PUID/PGID para que o container Traefik possa ler/escrever (e.g., acme.json)
    group: "{{ docker_pgid }}"
    mode: '0750' # Mais restritivo para diretórios de config
  loop:
    # Caminhos DENTRO da VM, que são montagens NFS.
    # Correspondem aos volumes no docker-compose do Traefik.
    - "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/traefik/config" # Para traefik.yml
    - "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/traefik/config/dynamic" # Para configs dinâmicas (middlewares)
    - "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/traefik/data" # Para acme.json e logs

- name: "Copiar configuração estática do Traefik (traefik.yml)"
  ansible.builtin.template:
    src: traefik.yml.j2
    dest: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/traefik/config/traefik.yml"
    owner: "{{ docker_puid }}"
    group: "{{ docker_pgid }}"
    mode: '0640' # Traefik só precisa ler este

- name: "Copiar configuração de headers de segurança para Traefik (dinâmica)"
  ansible.builtin.template:
    src: security_headers.yml.j2
    dest: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/traefik/config/dynamic/security_headers.yml"
    owner: "{{ docker_puid }}"
    group: "{{ docker_pgid }}"
    mode: '0640'

- name: "Copiar configuração dinâmica para serviços RAG (se ai-desktop-vm existir)"
  ansible.builtin.template:
    src: dynamic_rag_services.yml.j2 # Para rotear para OpenWebUI na ai-desktop-vm
    dest: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/traefik/config/dynamic/rag_services.yml"
    owner: "{{ docker_puid }}"
    group: "{{ docker_pgid }}"
    mode: '0640'
  when: "'ai-desktop-vm' in groups['virtual_machines']" # Só cria se a VM AI estiver no inventário

- name: "Copiar middleware para Nextcloud (dinâmico)"
  ansible.builtin.template:
    src: nextcloud_middleware.yml.j2 # Headers recomendados para Nextcloud
    dest: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/traefik/config/dynamic/nextcloud_middleware.yml"
    owner: "{{ docker_puid }}"
    group: "{{ docker_pgid }}"
    mode: '0640'

- name: "Garantir que acme.json existe e tem permissões corretas para Traefik"
  ansible.builtin.file:
    path: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/traefik/data/acme.json"
    state: touch # Cria se não existir, não modifica se existir (Traefik gerencia o conteúdo)
    owner: "{{ docker_puid }}" # Usuário que o container Traefik usa (ou root se PUID/PGID não for setado no container)
    group: "{{ docker_pgid }}" # Certifique-se que as permissões do NFS squash para este PUID/PGID
    mode: '0600' # Permissões restritas para o arquivo de certificados SSL
```

##### `templates/traefik.yml.j2` (Configuração Estática)

```yaml
# ansible/roles/infra/traefik-config/templates/traefik.yml.j2
# Configuração Estática do Traefik (gerada por Ansible)

global:
  checkNewVersion: true
  sendAnonymousUsage: false # Desabilitar telemetria para privacidade

# API e Dashboard do Traefik (será acessível via rota segura definida nas labels do container Traefik)
api:
  dashboard: true
  # insecure: true # APENAS para debug local em ambiente isolado. NUNCA em produção. Removido.

# EntryPoints (Pontos de Entrada HTTP e HTTPS)
entryPoints:
  web: # Entrypoint para HTTP na porta 80
    address: ":80"
    http:
      redirections: # Redirecionar todo tráfego HTTP para HTTPS
        entryPoint:
          to: "websecure" # Nome do entrypoint HTTPS
          scheme: "https"
          permanent: true # Usa redirecionamento 301 (permanente)
  websecure: # Entrypoint principal para HTTPS na porta 443
    address: ":443"
    http:
      tls:
        certResolver: "letsencrypt" # Resolvedor padrão para certificados TLS
        domains: # Opcional: Define domínios para os quais gerar certificados "on-demand"
          - main: "{{ base_domain }}" # Seu domínio principal
            sans: # Subdomínios alternativos (SANs)
              - "*.{{ base_domain }}" # Wildcard para todos os subdomínios
      middlewares: # Middlewares globais aplicados a TODAS as rotas no entrypoint websecure
        - "securityHeaders@file" # Referencia o middleware de headers de segurança (definido em dynamic/security_headers.yml)

# Provedores de Configuração (Docker e Arquivos para configs dinâmicas)
providers:
  docker:
    endpoint: "unix:///var/run/docker.sock" # Socket Docker para detectar containers
    exposedByDefault: false # APENAS containers com label 'traefik.enable=true' são expostos
    network: "proxy" # Rede Docker padrão onde Traefik procura por containers a serem expostos
    # watch: true # Padrão, Traefik monitora eventos Docker
  file:
    # Diretório para arquivos de configuração dinâmica (e.g., middlewares, serviços manuais)
    # O caminho é DENTRO do container Traefik, mapeado do volume NFS.
    directory: "/etc/traefik/dynamic_configs" # Corresponde ao volume montado no docker-compose do Traefik
    watch: true # Traefik monitora este diretório por mudanças e recarrega dinamicamente

# Resolvedores de Certificados (Let's Encrypt)
certificatesResolvers:
  letsencrypt: # Nome do resolvedor (usado em entrypoints e routers)
    acme:
      email: "{{ letsencrypt_email }}" # Email para notificações da Let's Encrypt (do vault.yml)
      storage: "/data/acme.json"      # Onde os certificados são armazenados (DENTRO do container Traefik)
      # Desafio DNS-01 usando Cloudflare API Token
      # O token é passado como variável de ambiente para o container Traefik.
      dnsChallenge:
        provider: "cloudflare"
        # delayBeforeCheck: 0 # Padrão geralmente funciona bem
        # resolvers: # Opcional: especificar servidores DNS para verificação do desafio
        #  - "1.1.1.1:53"
        #  - "8.8.8.8:53"

# Configurações de Log (opcional, mas útil para debug)
log:
  level: INFO # Níveis: DEBUG, INFO, WARNING, ERROR, FATAL, PANIC
  filePath: "/data/traefik.log" # Caminho DENTRO do container Traefik (mapeado para volume NFS)
  format: json # Ou common
accessLog:
  filePath: "/data/access.log" # Caminho DENTRO do container Traefik
  format: json # Ou common
  bufferingSize: 100 # Número de linhas de log para bufferizar antes de escrever

# Healthcheck para o container Traefik (usado por depends_on: condition: service_healthy no docker-compose)
ping: {} # Habilita o entrypoint /ping para healthchecks do Traefik
```

##### `templates/security_headers.yml.j2` (Middleware de Segurança)

```yaml
# ansible/roles/infra/traefik-config/templates/security_headers.yml.j2
# (Copiado para /etc/traefik/dynamic_configs/security_headers.yml no container Traefik)
# Define um middleware para adicionar headers de segurança HTTP.
http:
  middlewares:
    securityHeaders: # Nome do middleware (referenciado em entrypoints ou routers)
      headers:
        # Habilita o filtro XSS do navegador (obsoleto em navegadores modernos, mas não prejudicial)
        browserXssFilter: true
        # Impede que o navegador tente adivinhar o tipo de conteúdo (MIME-sniffing)
        contentTypeNosniff: true
        # Força o uso de HSTS (HTTP Strict Transport Security)
        forceSTSHeader: true
        stsIncludeSubdomains: true # Aplica HSTS a todos os subdomínios
        stsPreload: true           # Permite que seu domínio seja incluído na lista de preload HSTS
        stsSeconds: 31536000       # Duração do HSTS em segundos (1 ano). CUIDADO: habilite apenas quando tudo estiver funcionando 100% em HTTPS.
        # Previne clickjacking, permitindo iframes apenas do mesmo domínio.
        customFrameOptionsValue: "SAMEORIGIN"
        # Content-Security-Policy (CSP) - ALTAMENTE RECOMENDADO, mas requer ajuste fino por aplicação.
        # Este é um exemplo básico. Você precisará ajustá-lo para seus serviços específicos.
        # contentSecurityPolicy: "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'self' *.{{ base_domain }};"
        # Controla quais informações de referer são enviadas.
        referrerPolicy: "strict-origin-when-cross-origin"
        # Controla o acesso a APIs do navegador.
        permissionsPolicy: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), vr=()"
        # Adiciona outros headers de segurança conforme necessário
        # X-Content-Type-Options: "nosniff" (já coberto por contentTypeNosniff)
        # Strict-Transport-Security: (já coberto por stsSeconds, etc.)
```

!!! warning "Content-Security-Policy (CSP)"
    O `contentSecurityPolicy` é um header muito poderoso para mitigar XSS e outros ataques de injeção. No entanto, configurá-lo incorretamente pode quebrar a funcionalidade das suas aplicações. O exemplo acima é muito básico. Você precisará pesquisar e testar as diretivas CSP apropriadas para cada um dos seus serviços (Nextcloud, Grafana, etc.) ou começar com uma política menos restritiva e aumentá-la gradualmente.

##### `templates/dynamic_rag_services.yml.j2` (Roteamento para VM de IA)

```yaml
# ansible/roles/infra/traefik-config/templates/dynamic_rag_services.yml.j2
# (Copiado para /etc/traefik/dynamic_configs/rag_services.yml no container Traefik)
# Define roteamento para serviços rodando na ai-desktop-vm (e.g., OpenWebUI).
# Usa o File Provider do Traefik para definir serviços que não são descobertos via Docker (porque estão em outra VM).
http:
  routers:
    openwebui-dynamic: # Roteador para OpenWebUI
      entryPoints: ["websecure"] # Usa o entrypoint HTTPS
      rule: "Host(`openwebui.{{ base_domain }}`)" # Subdomínio para OpenWebUI
      service: "openwebui-svc-dynamic" # Nome do serviço Traefik definido abaixo
      tls:
        certResolver: "letsencrypt" # Usa Let's Encrypt
      middlewares:
        - "authelia@docker" # Protegido por Authelia (middleware definido no compose do Authelia)

    # Adicione aqui roteadores para outros serviços RAG/AI na ai-desktop-vm se necessário
    # Exemplo para um hipotético OpenNotebookLM
    # opennotebooklm-dynamic:
    #   entryPoints: ["websecure"]
    #   rule: "Host(`notebooklm.{{ base_domain }}`)"
    #   service: "opennotebooklm-svc-dynamic"
    #   tls: { certResolver: "letsencrypt" }
    #   middlewares: ["authelia@docker"]

  services:
    openwebui-svc-dynamic: # Serviço Traefik para OpenWebUI
      loadBalancer:
        servers:
          # Aponta para o IP da ai-desktop-vm e a porta interna do container OpenWebUI.
          # A variável ai_desktop_vm_ip_var vem do inventário Ansible (hosts.ini).
          - url: "http://{{ ai_desktop_vm_ip_var }}:8080" # Porta que OpenWebUI expõe na ai-desktop-vm

    # opennotebooklm-svc-dynamic:
    #   loadBalancer:
    #     servers:
    #       - url: "http://{{ ai_desktop_vm_ip_var }}:7860" # Porta interna do Open-NotebookLM
```

##### `templates/nextcloud_middleware.yml.j2` (Middleware para Nextcloud)

```yaml
# ansible/roles/infra/traefik-config/templates/nextcloud_middleware.yml.j2
# (Copiado para /etc/traefik/dynamic_configs/nextcloud_middleware.yml no container Traefik)
# Define um middleware com headers recomendados para Nextcloud.
http:
  middlewares:
    nextcloud-headers: # Nome do middleware
      headers:
        # Headers de segurança recomendados pelo Nextcloud para .htaccess, adaptados para Traefik
        # https://docs.nextcloud.com/server/latest/admin_manual/installation/harden_server.html#security-headers
        # Strict-Transport-Security já é tratado globalmente, mas pode ser reforçado aqui se necessário.
        # Referrer-Policy já é tratado globalmente.
        # X-Content-Type-Options: nosniff (já tratado globalmente)
        # X-Frame-Options: SAMEORIGIN (já tratado globalmente)
        # X-Permitted-Cross-Domain-Policies: none
        # X-Robots-Tag: none
        # X-XSS-Protection: 1; mode=block (já tratado globalmente)
        # Adicione outros específicos se Nextcloud evoluir suas recomendações.
        # Este middleware pode ser combinado com 'authelia@docker' e 'securityHeaders@file'
        # usando um chain middleware se necessário, ou aplicado diretamente.
        # Exemplo:
        # traefik.http.routers.nextcloud.middlewares: "authelia@docker,nextcloud-headers@file"
        # Se os headers globais já cobrem, este middleware pode não ser estritamente necessário,
        # mas pode ser usado para ajustes finos específicos para Nextcloud.
        # Por enquanto, pode ser deixado vazio ou com headers muito específicos que não são globais.
        # Exemplo de header que poderia ser específico:
        # customRequestHeaders:
        #   X-My-Nextcloud-Header: "true" # Exemplo, não é um header real do Nextcloud
        # Ou, para redirecionamentos .well-known para CalDAV/CardDAV se não tratados de outra forma:
        # (Mas Traefik faria isso com routers, não headers)
        pass: true # Middleware vazio por enquanto, para estrutura. Adicione headers específicos se necessário.
```

!!! note "Nextcloud Headers"
    Nextcloud tem recomendações específicas de headers de segurança, muitas das quais podem já estar cobertas pelos `securityHeaders@file` globais. Este middleware `nextcloud-headers@file` pode ser usado para adicionar ou sobrescrever headers especificamente para o Nextcloud se necessário. Consulte a documentação do Nextcloud para os headers mais recentes.

#### Role: `ansible/roles/infra/authelia-config/`

Este role prepara os arquivos de configuração do Authelia.

##### `tasks/main.yml`

```yaml
# ansible/roles/infra/authelia-config/tasks/main.yml
- name: "Garantir que diretórios de configuração do Authelia existam na VM (via NFS)"
  ansible.builtin.file:
    path: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/authelia/config"
    state: directory
    owner: "{{ docker_puid }}" # PUID/PGID para que o container Authelia possa ler
    group: "{{ docker_pgid }}"
    mode: '0750' # Authelia só precisa ler (e talvez escrever logs se configurado para arquivos)

- name: "Copiar configuração principal do Authelia (configuration.yml)"
  ansible.builtin.template:
    src: configuration.yml.j2
    dest: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/authelia/config/configuration.yml"
    owner: "{{ docker_puid }}"
    group: "{{ docker_pgid }}"
    mode: '0640' # Authelia só precisa ler este

- name: "Copiar banco de dados de usuários inicial do Authelia (users_database.yml)"
  ansible.builtin.template:
    src: users_database.yml.j2
    dest: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/authelia/config/users_database.yml"
    owner: "{{ docker_puid }}"
    group: "{{ docker_pgid }}"
    mode: '0640'
  # Este arquivo só é usado se o backend de autenticação do Authelia for 'file'.
  # No nosso caso, usaremos PostgreSQL, então este arquivo serve mais como um exemplo
  # ou um backup se mudarmos para o backend 'file'.
```

##### `templates/configuration.yml.j2` (Configuração Principal Authelia)

```yaml
# ansible/roles/infra/authelia-config/templates/configuration.yml.j2
# Configuração Principal do Authelia (gerada por Ansible)

# Nome da instância exibido em alguns locais (e.g., título da página)
instance_name: "Meu Servidor Doméstico"

# URL de redirecionamento padrão se Authelia não souber para onde enviar o usuário
# Geralmente o próprio portal Authelia.
default_redirection_url: "https://auth.{{ base_domain }}/"

# Tema da interface Authelia (opções: light, dark, grey)
theme: dark

# Segredos JWT e de Sessão (do vault.yml)
jwt_secret: "{{ authelia_jwt_secret }}"

# Método 2FA padrão para novos usuários (pode ser sobrescrito por usuário)
# Opções: "totp" (Time-based One-Time Password), "webauthn" (FIDO2/Passkeys)
default_2fa_method: "totp"

# Configuração da Sessão
session:
  name: "homelab_authelia_session" # Nome do cookie de sessão
  secret: "{{ authelia_session_secret }}" # Secret para criptografar o cookie (do vault.yml)
  expiration: 1h # Duração da sessão (e.g., 1h, 8h, 30d). Aumente se desejar sessões mais longas.
  inactivity: 10m  # Duração da inatividade antes de exigir re-autenticação (login novamente).
  # Domínio do cookie. Importante para SSO entre subdomínios.
  # DEVE ser o domínio pai (e.g., seudominio.com, NÃO auth.seudominio.com).
  domain: "{{ base_domain }}"
  # Se usar Redis para sessões distribuídas (não coberto neste guia simples):
  # redis:
  #   host: authelia_redis # Nome do serviço Docker do Redis
  #   port: 6379
  #   password: "SENHA_DO_REDIS_SE_HOUVER"
  #   database_index: 1 # Índice do banco de dados Redis

# Armazenamento de Dados do Usuário (PostgreSQL)
# Authelia usará este banco de dados para armazenar informações de usuários, dispositivos 2FA, etc.
storage:
  postgres:
    address: "tcp://authelia_db:5432" # Nome do serviço Docker do banco de dados Authelia e porta
    database: authelia # Nome do banco de dados
    username: authelia # Usuário do banco de dados
    password: "{{ authelia_storage_postgres_password }}" # Senha do usuário do DB (do vault.yml)
    timeout: 5s # Timeout para conexão com o DB
    # Para SSL com o DB (se configurado no PostgreSQL e você tiver os certificados):
    # schema: public # Padrão
    # ssl:
    #   mode: require # ou verify-ca, verify-full
    #   root_certificate: /config/certs/db_ca.pem
    #   client_certificate: /config/certs/db_client.crt
    #   client_key: /config/certs/db_client.key

# Backend de Autenticação
# Define como Authelia verifica as credenciais do usuário.
# Com 'storage.postgres' configurado, Authelia usará o mesmo DB para autenticação.
# Se você quisesse usar um arquivo YAML para usuários (users_database.yml):
# authentication_backend:
#   file:
#     path: /config/users_database.yml # Caminho DENTRO do container Authelia
#     # Configurações de hashing de senha (argon2id é o padrão e recomendado)
#     password:
#       algorithm: argon2id
#       iterations: 3
#       memory: 65536 # KiB (64MB)
#       parallelism: 4 # Número de threads
#       salt_length: 16
#       key_length: 32

# Regras de Controle de Acesso
# Define quais domínios/subdomínios são protegidos e qual política aplicar.
access_control:
  default_policy: deny # Política padrão se nenhuma regra corresponder (deny, one_factor, two_factor, bypass)
  rules:
    # Regra para o próprio portal Authelia (auth.seudominio.com)
    # Usuários precisam acessá-lo para logar, então não deve ser protegido pelo próprio Authelia.
    - domain: "auth.{{ base_domain }}"
      policy: bypass # Não requer autenticação para acessar o portal de login

    # Regra geral para todos os outros subdomínios do seu domínio base: requer dois fatores.
    - domain: "*.{{ base_domain }}"
      policy: two_factor # Requer login bem-sucedido com primeiro e segundo fator

    # Exemplo: Permitir acesso da rede local sem Authelia (bypass) para certos serviços.
    # Cuidado ao usar bypass, pois anula a proteção do Authelia para essas condições.
    # - domain: "servico_local.{{ base_domain }}"
    #   networks: # IPs ou CIDRs da sua rede local
    #     - "192.168.1.0/24"
    #   policy: bypass

# Notificador (para reset de senha, alertas de segurança, etc.) - ALTAMENTE RECOMENDADO
# Configure para receber notificações por email.
# notifier:
#   smtp:
#     address: "smtp.seuprovedor.com:587" # Servidor SMTP e porta (587 para STARTTLS, 465 para SSL/TLS direto)
#     username: "seu_email_de_envio@example.com"
#     password: "SENHA_DO_SEU_EMAIL_DE_ENVIO_APP_PASSWORD" # Use senha de aplicativo se o provedor exigir
#     sender: "Authelia <authelia@{{ base_domain }}>" # Remetente exibido nos emails
#     subject: "[Authelia - {{ base_domain }}] {title}" # Assunto do email (pode usar placeholders)
#     # Para TLS (STARTTLS é geralmente usado na porta 587):
#     # tls:
#     #   server_name: "smtp.seuprovedor.com" # Se diferente do address
#     #   skip_verify: false # Mantenha false para segurança, a menos que seja um servidor interno com cert autoassinado
#     #   minimum_version: "TLS1.2"
#     # Para verificar a configuração do notificador ao iniciar Authelia:
#     # startup_check_address: "email_de_teste_para_receber_notificacao@example.com"

# Configuração TOTP (Time-based One-Time Password)
totp:
  issuer: "Homelab {{ base_domain }}" # Nome exibido no app autenticador (e.g., Google Authenticator, Authy)
  algorithm: SHA1 # Padrão (SHA256, SHA512 também são opções)
  digits: 6       # Padrão (número de dígitos no código TOTP)
  period: 30      # Padrão (período de validade do código em segundos)
  skew: 1         # Permite uma pequena dessincronização de relógio (1 período para frente ou para trás)

# Regulação (Proteção contra Brute-Force nas tentativas de login)
regulation:
  max_retries: 3  # Número de tentativas de login falhas antes do banimento temporário.
  find_time: 2m   # Janela de tempo para contar as tentativas falhas (e.g., 3 falhas em 2 minutos).
  ban_time: 5m    # Duração do banimento temporário.
```

##### `templates/users_database.yml.j2` (Exemplo de Usuários - se backend `file`)

```yaml
# ansible/roles/infra/authelia-config/templates/users_database.yml.j2
# Arquivo de Banco de Dados de Usuários Locais do Authelia (gerado por Ansible)
# Hashes de senha DEVEM ser gerados com 'authelia crypto hash generate argon2'
# !!! NOTA IMPORTANTE !!!
# Este arquivo SÓ É USADO se 'authentication_backend.file' estiver configurado em configuration.yml.
# Com a configuração atual usando PostgreSQL para 'storage', Authelia gerenciará os usuários
# diretamente no banco de dados. O primeiro usuário (admin) será criado com base nas
# variáveis de ambiente passadas para o container Authelia na primeira execução, ou
# você precisará registrar o admin via UI/API do Authelia se essa funcionalidade existir.
# Este arquivo é mantido aqui como um exemplo ou fallback.

users:
  # Usuário administrador inicial (do vault.yml)
  "{{ authelia_admin_user_initial }}": # Nome do usuário
    displayname: "Administrador"
    # O hash da senha já foi gerado e está na variável do vault.yml
    password: "{{ authelia_admin_password_hash_initial }}"
    email: "{{ letsencrypt_email }}" # Email para notificações, reset de senha
    groups: # Grupos para controle de acesso (podem ser usados nas regras de access_control)
      - admins
      - users
  # Adicione outros usuários aqui conforme necessário, se usar o backend 'file':
  # "outro_usuario":
  #   displayname: "Outro Usuário"
  #   password: "$argon2id$v=19$m=..." # Hash gerado para a senha deste usuário
  #   email: "outro_usuario@example.com"
  #   groups:
  #     - users
  #     - media_users # Exemplo de grupo customizado
```

### Playbook `ansible/playbooks/setup-core-networking.yml`

Este playbook orquestra o deploy da stack de rede. Authelia agora está consolidado na mesma stack `core`.

```yaml
# ansible/playbooks/setup-core-networking.yml
- hosts: core-services-vm
  become: yes
  vars_files:
    - ../inventories/home/group_vars/all/vault.yml

  tasks:
    - name: "Garantir que redes Docker globais (proxy, internal_services) existam"
      community.docker.docker_network:
        name: "{{ item }}"
        state: present
      loop:
        - proxy
        - internal_services

    - name: "Incluir role para configs do Traefik"
      ansible.builtin.include_role:
        name: infra/traefik-config

    - name: "Incluir role para configs do Authelia"
      ansible.builtin.include_role:
        name: infra/authelia-config

    - name: "Deploy Core Stack (Traefik, Cloudflared, Authelia)"
      community.docker.docker_compose_v2:
        project_src: "{{ playbook_dir }}/../../docker/stacks/core/"
        files:
          - docker-compose.yml
        state: present
        remove_orphans: true
        pull: always
      environment:
        # Traefik
        CLOUDFLARE_API_TOKEN_FROM_VAULT: "{{ cloudflare_api_token }}"
        BASE_DOMAIN_FROM_VAULT: "{{ base_domain }}"
        LETSENCRYPT_EMAIL_FROM_VAULT: "{{ letsencrypt_email }}"
        # Cloudflared
        CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT: "{{ cloudflare_tunnel_token }}"
        # Authelia
        SYSTEM_TIMEZONE: "{{ system_timezone }}"
        AUTHELIA_STORAGE_POSTGRES_PASSWORD_FROM_VAULT: "{{ authelia_storage_postgres_password }}"
        # Volumes NFS
        VM_NFS_MOUNT_BASE_PATH: "{{ vm_nfs_mount_base_path }}"
        ZFS_DOCKER_VOLUMES_DATASET_NAME: "{{ zfs_docker_volumes_dataset_name }}"
        CORE_SERVICES_VM_IP_VAR: "{{ core_services_vm_ip_var }}"
      register: core_stack_deploy_result

    - name: "Aguardar Traefik estar saudável"
      community.docker.docker_container_info:
        name: traefik
      register: traefik_container_status
      until: traefik_container_status.container.State.Health.Status == "healthy"
      retries: 15
      delay: 10
      when: core_stack_deploy_result.changed
```

### Executando o Playbook de Configuração da Rede Core

1. **Verifique os Roles e Templates:** Certifique-se de que todos os arquivos de role (`infra/traefik-config`, `infra/authelia-config`) e seus respectivos templates (`.j2` arquivos) estão criados e preenchidos com o código correto no seu projeto Ansible.
2. **Execute a Partir da Máquina de Controle:** Na sua máquina de controle Ansible, navegue até a raiz do seu projeto `home-server/`.
3. **Execute o Playbook:**

    ```bash
    ansible-playbook ansible/playbooks/setup-core-networking.yml --ask-vault-pass
    ```

    Você será solicitado a fornecer a senha do Ansible Vault.

## 5.5. Configuração de DNS na Cloudflare

Após o deploy bem-sucedido da stack de rede, especialmente do container `cloudflared` (Cloudflare Tunnel), você precisa configurar seus registros DNS na Cloudflare para que seus subdomínios (e.g., `portainer.meuhomelab.com`, `traefik.meuhomelab.com`, `auth.meuhomelab.com`) apontem corretamente para o seu túnel.

**Abordagem Recomendada: Usar Ingress Rules no Cloudflare Zero Trust Dashboard**

Esta abordagem oferece a maior flexibilidade e é gerenciada centralmente no painel da Cloudflare. Assumindo que seu comando `cloudflared` no `docker-compose.yml` é:
`command: tunnel --no-autoupdate --metrics 0.0.0.0:2000 run --token ${CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT}`
(ou seja, sem as flags `--hostname` e `--url` que tentam gerenciar DNS automaticamente).

1. **Acesse o Cloudflare Zero Trust Dashboard:** Vá para [one.dash.cloudflare.com](https://one.dash.cloudflare.com/).
2. No menu lateral, navegue para **Access -> Tunnels**.
3. Localize e selecione o túnel que foi criado (você deve ter criado um ao obter o `CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT`).
4. Clique na aba "**Public Hostnames**".
5. Clique em "**+ Add a public hostname**" para cada serviço que você deseja expor.
    * **Subdomain:** O prefixo do seu serviço (e.g., `portainer`, `traefik`, `auth`, `nextcloud`, `hass`, `grafana`, `openwebui`, etc.).
    * **Domain:** Selecione seu domínio base (`{{ base_domain }}` e.g., `meuhomelab.com`).
    * **Path:** Deixe em branco (a menos que você queira rotear caminhos específicos para serviços diferentes, o que é mais avançado e geralmente tratado pelo Traefik).
    * **Service Type:** `HTTP`.
    * **Service URL:** `traefik:80`
        * Isso instrui o Cloudflare Tunnel a encaminhar o tráfego para o serviço Docker chamado `traefik` (o container Traefik) na porta `80` (dentro da rede Docker `proxy` onde ambos, `cloudflared` e `traefik`, estão conectados).
    * Clique em "Save hostname".

**Exemplos de Public Hostnames a Adicionar Inicialmente:**

* `portainer.{{ base_domain }}` -> `http://traefik:80`
* `traefik.{{ base_domain }}` -> `http://traefik:80` (para o dashboard do Traefik)
* `auth.{{ base_domain }}` -> `http://traefik:80` (para o portal do Authelia)
* (Opcional, mas recomendado) **Catch-all com Wildcard:**
    * Subdomain: `*`
    * Domain: `{{ base_domain }}`
    * Service: `http://traefik:80`
    !!! tip "Vantagem do Catch-All (`*`)"
        Configurar um hostname público com o subdomínio `*` (wildcard) significa que qualquer subdomínio de `{{ base_domain }}` que não tenha uma regra de Public Hostname mais específica na Cloudflare será automaticamente encaminhado para o Traefik. O Traefik então usará suas próprias regras de roteamento (definidas por labels Docker ou File Provider) para direcionar para o container correto. Isso simplifica muito a adição de novos serviços no futuro: você só precisa configurar as labels no Traefik, e não precisará adicionar um novo Public Hostname na Cloudflare toda vez (a menos que queira configurações de túnel muito específicas por subdomínio, como políticas de acesso Cloudflare).

**Opção Alternativa: Usando a flag `--hostname` no `cloudflared`**

Se o seu comando `cloudflared` no `docker-compose.yml` inclui:
`--hostname {{ base_domain }} --url http://traefik:80`
O `cloudflared` tentará criar e gerenciar automaticamente um registro CNAME para `{{ base_domain }}` e um CNAME wildcard `*.{{ base_domain }}` apontando para o seu túnel.

* **Ação:** Verifique no painel DNS da Cloudflare (não no Zero Trust, mas na seção DNS do seu domínio) se esses CNAMEs foram criados (e.g., `seudominio.com CNAME <TUNNEL_ID>.cfargotunnel.com` e `* CNAME <TUNNEL_ID>.cfargotunnel.com`). O `<TUNNEL_ID>` é o UUID do seu túnel.
* **Menos Flexível:** Esta abordagem é mais simples, mas oferece menos controle granular do que as Ingress Rules/Public Hostnames no dashboard Zero Trust.

**Verificação Importante (em ambos os casos):**

* **Status do Proxy Cloudflare (Nuvem Laranja):** Para todos os registros DNS (CNAMEs) relacionados aos seus serviços expostos, certifique-se de que o "Proxy status" na Cloudflare está **habilitado (nuvem laranja)**. Isso garante que o tráfego passe pela rede da Cloudflare, beneficiando-se de suas proteções e permitindo que o túnel funcione.

Pode levar alguns minutos para que quaisquer novas configurações de DNS ou Public Hostnames se propaguem globalmente.

Com a stack de rede segura implementada e o DNS configurado, você está pronto para o [Deploy Core](06-deploy-core.md).