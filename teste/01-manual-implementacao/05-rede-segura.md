# Seção 5: Implementação da Rede Segura (Traefik, Cloudflare Tunnel, Authelia)

Esta seção é crucial para expor seus serviços auto-hospedados à internet de forma segura e gerenciada. Utilizaremos:
*   **Traefik:** Como proxy reverso para rotear o tráfego para seus containers Docker e gerenciar certificados SSL/TLS.
*   **Cloudflare Tunnel (`cloudflared`):** Para criar uma conexão segura de saída da sua rede local para a Cloudflare, eliminando a necessidade de abrir portas no roteador e protegendo seu IP público.
*   **Authelia:** Como um portal de autenticação e autorização para adicionar uma camada de segurança (incluindo 2FA) aos seus serviços.

Todos esses componentes rodarão como containers Docker na `core-services-vm`.

## 5.1. Entendendo o Fluxo de Tráfego e o Proxy Reverso

Antes de configurar, é importante entender como o tráfego fluirá:

1.  **Usuário Acessa:** O usuário digita `https://meuservico.{{ base_domain }}` no navegador.
2.  **DNS Cloudflare:** A Cloudflare resolve o subdomínio para o seu Cloudflare Tunnel, não para o seu IP doméstico.
3.  **Cloudflare Edge:** A requisição chega à rede global da Cloudflare, onde pode passar por proteções como WAF e DDoS mitigation.
4.  **Cloudflare Tunnel (`cloudflared`):** O container `cloudflared` na sua `core-services-vm` mantém uma conexão de SAÍDA segura com a Cloudflare. O tráfego destinado aos seus subdomínios é "puxado" do Cloudflare Edge para sua rede local através deste túnel.
5.  **`cloudflared` para Traefik:** O `cloudflared` recebe o tráfego do túnel e o encaminha para o Traefik, que está escutando nas portas 80 e 443 da `core-services-vm` (dentro da rede Docker `proxy`).
6.  **Traefik (Proxy Reverso):**
    *   Traefik inspeciona o nome do Host da requisição (e.g., `meuservico.{{ base_domain }}`).
    *   **Authelia (Middleware):** Se a rota para `meuservico` estiver protegida por Authelia, Traefik primeiro consulta Authelia.
        *   Se o usuário não estiver logado, Authelia redireciona para o portal de login (`auth.{{ base_domain }}`).
        *   Após login bem-sucedido (com 2FA), Authelia informa ao Traefik que o usuário está autenticado.
    *   **Roteamento para Serviço Docker:** Com base nas labels Docker do container de destino (e autenticação bem-sucedida), Traefik roteia a requisição para o container Docker correto (e.g., Nextcloud, Grafana).
    *   **SSL/TLS (Let's Encrypt):** Traefik gerencia automaticamente os certificados SSL/TLS para todos os seus subdomínios usando Let's Encrypt através do desafio DNS-01 com a API da Cloudflare.

!!! tip "Diagrama Visual"
    Para uma representação visual deste fluxo, consulte o diagrama na seção [Fluxo de Rede e Acesso Externo da Visão Geral da Arquitetura](../02-visao-geral-arquitetura/01-fluxo-rede-acesso-externo.md).

## 5.2. Docker Compose para a Stack Core (`docker/stacks/core/docker-compose.yml`)

Esta stack inclui Traefik e Cloudflared. Crie o arquivo `infra-servidor-domestico/docker/stacks/core/docker-compose.yml`:

```yaml
# docker/stacks/core/docker-compose.yml
version: '3.9'

networks:
  proxy: # Rede para Traefik e serviços expostos
    name: proxy # Nome da rede que foi criada pelo Ansible
    external: true # Indica que a rede 'proxy' já existe e será usada

services:
  traefik:
    image: traefik:v2.11.2 # Use uma versão específica e estável. Verifique a mais recente.
    container_name: traefik
    restart: unless-stopped
    security_opt: [no-new-privileges:true]
    networks:
      - proxy # Conecta Traefik à rede proxy
    ports:
      # Mapeia as portas do Traefik no IP da core-services-vm.
      # As variáveis injetadas (e.g., CORE_SERVICES_VM_IP_VAR) virão do .env ou Ansible.
      - "${CORE_SERVICES_VM_IP_VAR}:80:80"   # HTTP (será redirecionado para HTTPS)
      - "${CORE_SERVICES_VM_IP_VAR}:443:443" # HTTPS (ponto de entrada principal)
      # - "${CORE_SERVICES_VM_IP_VAR}:8080:8080" # Opcional: Porta para a API/Dashboard do Traefik (se não exposta via rota segura)
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock:ro" # Permite Traefik detectar containers Docker
      # Caminhos para configs e certs DENTRO DA VM (que são montagens NFS do host Proxmox)
      # As variáveis (e.g., VM_NFS_MOUNT_BASE_PATH) virão do .env ou Ansible.
      - "${VM_NFS_MOUNT_BASE_PATH}/${ZFS_DOCKER_VOLUMES_DATASET_NAME}/traefik/data:/data" # Para acme.json (certificados) e logs
      - "${VM_NFS_MOUNT_BASE_PATH}/${ZFS_DOCKER_VOLUMES_DATASET_NAME}/traefik/config/traefik.yml:/traefik.yml:ro" # Configuração estática do Traefik
      - "${VM_NFS_MOUNT_BASE_PATH}/${ZFS_DOCKER_VOLUMES_DATASET_NAME}/traefik/config/dynamic:/etc/traefik/dynamic_configs:ro" # Configs dinâmicas (middlewares, etc.)
      - "/etc/localtime:/etc/localtime:ro" # Sincroniza o fuso horário
    environment:
      # Token da API Cloudflare para o desafio DNS-01 (Let's Encrypt)
      # Esta variável será injetada pelo Ansible ou definida no Portainer.
      - CF_DNS_API_TOKEN=${CLOUDFLARE_API_TOKEN_FROM_VAULT}
      # - CF_API_EMAIL=${LETSENCRYPT_EMAIL_FROM_VAULT} # Para alguns provedores DNS mais antigos, não Cloudflare com token.
      # - CF_ZONE_API_TOKEN=${CLOUDFLARE_ZONE_API_TOKEN_FROM_VAULT} # Alternativa ao token global
    labels:
      traefik.enable: "true" # Permite Traefik gerenciar o próprio Traefik
      # Dashboard Traefik (protegido por Authelia)
      traefik.http.routers.traefik-dashboard.rule: "Host(`traefik.${BASE_DOMAIN_FROM_VAULT}`)" # BASE_DOMAIN_FROM_VAULT injetado
      traefik.http.routers.traefik-dashboard.entrypoints: "websecure"
      traefik.http.routers.traefik-dashboard.service: "api@internal" # Serviço interno do Traefik para o dashboard
      traefik.http.routers.traefik-dashboard.tls.certresolver: "letsencrypt"
      traefik.http.routers.traefik-dashboard.middlewares: "authelia@docker" # Protegido por Authelia
    healthcheck: # Define um healthcheck para o container Traefik
      test: ["CMD", "traefik", "healthcheck", "--ping"]
      interval: 10s
      timeout: 2s
      retries: 3
      start_period: 5s # Período inicial antes de considerar falhas no healthcheck

  cloudflared:
    image: cloudflare/cloudflared:2024.5.0 # Use uma versão específica e estável. Verifique a mais recente.
    container_name: cloudflared
    restart: unless-stopped
    networks:
      - proxy # Precisa estar na mesma rede que Traefik para encaminhar tráfego
    # O comando para rodar o túnel.
    # O token será injetado pelo Ansible ou Portainer.
    # A flag --url http://traefik:80 direciona todo o tráfego do túnel para o serviço 'traefik' na porta 80.
    # Se você preferir gerenciar os Ingress Rules no dashboard da Cloudflare, remova --hostname e --url,
    # e use apenas 'run --token ${CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT}'.
    command: tunnel --no-autoupdate --metrics 0.0.0.0:2000 --protocol http2 --hostname ${BASE_DOMAIN_FROM_VAULT} --url http://traefik:80 run --token ${CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT}
    # Exemplo de comando para Ingress Rules gerenciadas no dashboard Cloudflare:
    # command: tunnel --no-autoupdate --metrics 0.0.0.0:2000 run --token ${CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT}
    # E então, no Cloudflare Zero Trust Dashboard > Access > Tunnels > Seu Túnel > Public Hostnames:
    # - Hostname: app.seudominio.com, Service: http://traefik:80
    # - Hostname: *.seudominio.com, Service: http://traefik:80 (para um catch-all)
    depends_on: # Garante que Traefik esteja saudável antes de iniciar cloudflared
      traefik:
        condition: service_healthy
```
!!! note "Variáveis de Ambiente no Compose"
    Variáveis como `${CORE_SERVICES_VM_IP_VAR}`, `${VM_NFS_MOUNT_BASE_PATH}`, `${ZFS_DOCKER_VOLUMES_DATASET_NAME}`, `${CLOUDFLARE_API_TOKEN_FROM_VAULT}`, `${BASE_DOMAIN_FROM_VAULT}`, e `${CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT}` serão substituídas:
    *   Pelo Ansible ao gerar um arquivo `.env` para esta stack.
    *   Ou definidas diretamente como variáveis de ambiente da stack no Portainer.

## 5.3. Docker Compose para a Stack Authelia (`docker/stacks/authelia/docker-compose.yml`)

Authelia fornecerá autenticação 2FA. Crie o arquivo `infra-servidor-domestico/docker/stacks/authelia/docker-compose.yml`:

```yaml
# docker/stacks/authelia/docker-compose.yml
version: '3.9'

networks:
  proxy: { name: proxy, external: true } # Para ser acessado por Traefik
  internal_services: # Rede para o banco de dados do Authelia
    name: internal_services
    external: true

services:
  authelia:
    image: authelia/authelia:4.38.0 # Use uma versão específica e estável. Verifique a mais recente.
    container_name: authelia
    restart: unless-stopped
    volumes:
      # Caminho NFS para configs do Authelia. As variáveis virão do .env ou Ansible.
      - "${VM_NFS_MOUNT_BASE_PATH}/${ZFS_DOCKER_VOLUMES_DATASET_NAME}/authelia/config:/config"
      - "/etc/localtime:/etc/localtime:ro"
    networks:
      - proxy # Para Traefik alcançar o portal Authelia e o endpoint de verificação
      - internal_services # Para Authelia alcançar seu banco de dados
    expose:
      - "9091" # Porta interna do Authelia, não precisa ser mapeada para o host diretamente. Traefik acessa.
    environment:
      - TZ=${SYSTEM_TIMEZONE_FROM_VAULT} # Injetado pelo .env ou Ansible
      # Outras variáveis podem ser necessárias dependendo da sua config/configuration.yml do Authelia
    depends_on: # Garante que o DB esteja saudável antes de iniciar Authelia
      authelia_db:
        condition: service_healthy
    labels: # Labels Traefik para expor o portal Authelia e definir o middleware
      traefik.enable: "true"
      # --- Roteador para o portal Authelia (auth.seudominio.com) ---
      traefik.http.routers.authelia-portal.rule: "Host(`auth.${BASE_DOMAIN_FROM_VAULT}`)"
      traefik.http.routers.authelia-portal.entrypoints: "websecure"
      traefik.http.routers.authelia-portal.tls.certresolver: "letsencrypt"
      traefik.http.routers.authelia-portal.service: "authelia-svc"
      # --- Serviço para o portal Authelia ---
      traefik.http.services.authelia-svc.loadbalancer.server.port: "9091" # Porta interna do Authelia
      # --- Middleware Authelia (a ser referenciado por outros serviços) ---
      # O nome 'authelia@docker' é como outros containers (via labels) referenciarão este middleware.
      traefik.http.middlewares.authelia.forwardauth.address: "http://authelia:9091/api/verify?rd=https://auth.${BASE_DOMAIN_FROM_VAULT}/"
      traefik.http.middlewares.authelia.forwardauth.trustForwardHeader: "true"
      traefik.http.middlewares.authelia.forwardauth.authResponseHeaders: "Remote-User,Remote-Groups,Remote-Name,Remote-Email"

  authelia_db: # Banco de dados PostgreSQL para Authelia
    image: postgres:15.6-alpine # Use uma versão específica e estável.
    container_name: authelia_db
    restart: unless-stopped
    volumes:
      # Caminho NFS para o banco de dados do Authelia. As variáveis virão do .env ou Ansible.
      - "${VM_NFS_MOUNT_BASE_PATH}/${ZFS_DOCKER_VOLUMES_DATASET_NAME}/authelia/db_pg:/var/lib/postgresql/data"
    networks:
      - internal_services # Apenas na rede interna, não acessível externamente
    environment:
      - POSTGRES_DB=authelia
      - POSTGRES_USER=authelia
      - POSTGRES_PASSWORD=${AUTHELIA_STORAGE_POSTGRES_PASSWORD_FROM_VAULT} # Injetado
      - TZ=${SYSTEM_TIMEZONE_FROM_VAULT} # Injetado
    healthcheck: # Verifica se o banco de dados está pronto
      test: ["CMD-SHELL", "pg_isready -U authelia -d authelia"]
      interval: 10s
      timeout: 5s
      retries: 5
```

## 5.4. Playbook `ansible/playbooks/setup-core-networking.yml`

Este playbook Ansible será responsável por:
1.  Criar as redes Docker `proxy` e `internal_services` (se ainda não existirem).
2.  Copiar os arquivos de configuração para Traefik (estática e dinâmica) e Authelia para os volumes NFS.
3.  Fazer o deploy das stacks `core` (Traefik, Cloudflared) e `authelia` usando o módulo `docker_compose_v2`.

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

Este playbook orquestra o deploy da stack de rede.

```yaml
# ansible/playbooks/setup-core-networking.yml
- hosts: core-services-vm # Todas estas stacks rodam na core-services-vm
  become: yes # Para gerenciar Docker e arquivos de configuração no sistema de arquivos
  vars_files:
    - ../inventories/home/group_vars/all/vault.yml
  # Variáveis de group_vars/all/main.yml são carregadas automaticamente

  tasks:
    - name: "Garantir que redes Docker globais (proxy, internal_services) existam"
      community.docker.docker_network:
        name: "{{ item }}"
        state: present # Cria se não existir, não faz nada se já existir
      loop:
        - proxy
        - internal_services

    - name: "Incluir role para criar diretórios e copiar configs para Traefik"
      ansible.builtin.include_role:
        name: infra/traefik-config

    - name: "Deploy Core Stack (Traefik, Cloudflared)"
      community.docker.docker_compose_v2: # Módulo Ansible para Docker Compose v2
        project_src: "{{ playbook_dir }}/../../docker/stacks/core/" # Caminho para o diretório da stack
        files:
          - docker-compose.yml # Arquivo compose a ser usado
        state: present # Garante que a stack está rodando conforme definido
        remove_orphans: true # Remove containers órfãos se o compose mudar
        pull: always # Sempre tenta puxar a imagem mais recente (respeitando a tag especificada)
      environment: # Injeta variáveis Ansible/Vault no ambiente do docker-compose
        # Estas variáveis são usadas dentro do docker-compose.yml da stack 'core'
        # Para Traefik:
        CLOUDFLARE_API_TOKEN_FROM_VAULT: "{{ cloudflare_api_token }}"
        BASE_DOMAIN_FROM_VAULT: "{{ base_domain }}"
        LETSENCRYPT_EMAIL_FROM_VAULT: "{{ letsencrypt_email }}" # Usado por Traefik
        # Para Cloudflared:
        CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT: "{{ cloudflare_tunnel_token }}"
        # Para caminhos de volume NFS (usados por Traefik):
        VM_NFS_MOUNT_BASE_PATH: "{{ vm_nfs_mount_base_path }}"
        ZFS_DOCKER_VOLUMES_DATASET_NAME: "{{ zfs_docker_volumes_dataset_name }}"
        # IP da VM para mapeamento de portas no Traefik (se referenciado no compose):
        CORE_SERVICES_VM_IP_VAR: "{{ core_services_vm_ip_var }}"
      register: core_stack_deploy_result

    - name: "Aguardar Traefik estar saudável após deploy/atualização"
      community.docker.docker_container_info:
        name: traefik # Nome do container Traefik
      register: traefik_container_status
      until: traefik_container_status.container.State.Health.Status == "healthy" # Espera pelo healthcheck do Traefik
      retries: 15 # Número de tentativas
      delay: 10   # Segundos de espera entre tentativas
      when: core_stack_deploy_result.changed # Só espera se a stack Traefik foi realmente alterada/deployada

    - name: "Incluir role para criar diretórios e copiar configs para Authelia"
      ansible.builtin.include_role:
        name: infra/authelia-config

    - name: "Deploy Authelia Stack"
      community.docker.docker_compose_v2:
        project_src: "{{ playbook_dir }}/../../docker/stacks/authelia/"
        files:
          - docker-compose.yml
        state: present
        remove_orphans: true
        pull: always
      environment: # Variáveis para a stack Authelia
        SYSTEM_TIMEZONE_FROM_VAULT: "{{ system_timezone }}"
        BASE_DOMAIN_FROM_VAULT: "{{ base_domain }}"
        AUTHELIA_STORAGE_POSTGRES_PASSWORD_FROM_VAULT: "{{ authelia_storage_postgres_password }}"
        AUTHELIA_JWT_SECRET_FROM_VAULT: "{{ authelia_jwt_secret }}" # Necessário se Authelia lê do env
        AUTHELIA_SESSION_SECRET_FROM_VAULT: "{{ authelia_session_secret }}" # Necessário se Authelia lê do env
        # Se for criar o admin inicial via ENV (algumas versões do Authelia suportam isso)
        # AUTHELIA_IDENTITY_PROVIDERS_OIDC_CLIENTS_0_ID: admin # Exemplo, verifique a doc do Authelia
        # AUTHELIA_IDENTITY_PROVIDERS_OIDC_CLIENTS_0_DESCRIPTION: Admin User
        # AUTHELIA_IDENTITY_PROVIDERS_OIDC_CLIENTS_0_SECRET: "{{ authelia_admin_password_hash_initial }}" # Não é o ideal
        # AUTHELIA_USERS_ADMIN_PASSWORD: "{{ authelia_admin_password_hash_initial }}" # Não é o ideal
        # É melhor que o configuration.yml (template) já tenha os segredos e hashes.
        # As variáveis PUID/PGID e de caminho NFS também devem ser passadas se referenciadas no compose Authelia
        VM_NFS_MOUNT_BASE_PATH: "{{ vm_nfs_mount_base_path }}"
        ZFS_DOCKER_VOLUMES_DATASET_NAME: "{{ zfs_docker_volumes_dataset_name }}"
```

### Executando o Playbook de Rede

1.  Certifique-se de que os roles `infra/traefik-config` e `infra/authelia-config` estão criados com os arquivos detalhados.
2.  Na sua máquina de controle Ansible, navegue até a raiz do projeto `infra-servidor-domestico/`.
3.  Execute o playbook:
    ```bash
    ansible-playbook ansible/playbooks/setup-core-networking.yml --ask-vault-pass
    ```

## 5.5. Configuração de DNS na Cloudflare

Após o deploy da stack de rede, especialmente do Cloudflare Tunnel, você precisa configurar seus registros DNS na Cloudflare para que seus subdomínios apontem para o túnel.

**Opção 1: Usando a flag `--hostname` no `cloudflared` (como no `docker-compose.yml` da Seção 5.2)**

Se o seu comando `cloudflared` no `docker-compose.yml` inclui:
`--hostname ${BASE_DOMAIN_FROM_VAULT} --url http://traefik:80`
ou similar, o `cloudflared` tentará criar automaticamente um registro CNAME para `${BASE_DOMAIN_FROM_VAULT}` (e.g., `seudominio.com`) e possivelmente um wildcard (`*.seudominio.com`) apontando para o seu túnel.

*   **Ação:** Verifique no painel DNS da Cloudflare se um registro CNAME como `seudominio.com CNAME <TUNNEL_ID>.cfargotunnel.com` e/ou `* CNAME <TUNNEL_ID>.cfargotunnel.com` foi criado. O `<TUNNEL_ID>` é o UUID do seu túnel.

**Opção 2: Gerenciamento Manual de Ingress Rules no Cloudflare Zero Trust Dashboard (Recomendado para Flexibilidade)**

Se o seu comando `cloudflared` é apenas `run --token ...` (sem `--hostname` ou `--url`), você controlará os subdomínios publicamente acessíveis através do dashboard Cloudflare Zero Trust.

1.  Acesse o [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/).
2.  Vá para **Access -> Tunnels**.
3.  Selecione seu túnel na lista.
4.  Clique na aba **Public Hostnames**.
5.  Clique em **"+ Add a public hostname"**.
    *   **Subdomain:** O prefixo do seu serviço (e.g., `portainer`, `traefik`, `auth`, `nextcloud`). Use `*` como wildcard para um catch-all para todos os subdomínios não especificados.
    *   **Domain:** Selecione seu `{{ base_domain }}`.
    *   **Path:** Deixe em branco (a menos que você queira rotear caminhos específicos para serviços diferentes).
    *   **Service Type:** `HTTP`.
    *   **Service URL:** `traefik:80` (se `cloudflared` e `traefik` estão na mesma rede Docker `proxy` e o serviço Docker `traefik` está acessível por esse nome e porta). Se Traefik estivesse escutando em HTTPS internamente (não é o nosso caso aqui), seria `https://traefik:443`.
    *   Clique em "Save hostname".

    **Exemplos de Public Hostnames a serem adicionados:**
    *   Subdomain: `portainer`, Domain: `{{ base_domain }}`, Service: `http://traefik:80`
    *   Subdomain: `traefik` (para o dashboard), Domain: `{{ base_domain }}`, Service: `http://traefik:80`
    *   Subdomain: `auth` (para Authelia), Domain: `{{ base_domain }}`, Service: `http://traefik:80`
    *   Subdomain: `*` (catch-all), Domain: `{{ base_domain }}`, Service: `http://traefik:80`
        !!! tip "Usando o Catch-All (`*`)"
            Se você configurar um hostname público com o subdomínio `*`, ele atuará como um catch-all. Qualquer subdomínio de `{{ base_domain }}` que não tenha uma regra mais específica será encaminhado para o serviço especificado (neste caso, Traefik). Traefik então usará suas próprias regras de roteamento baseadas em host para direcionar para o container correto. Isso simplifica a adição de novos serviços, pois você só precisa configurar as labels no Traefik, sem precisar adicionar um novo Public Hostname na Cloudflare toda vez (a menos que queira configurações de túnel específicas por subdomínio).

**Verificação Importante:**
*   **Proxy Status:** Em todos os casos (CNAMEs automáticos ou Ingress Rules), certifique-se de que o status do proxy na Cloudflare (a nuvem laranja) está **habilitado** para esses registros/hostnames. Isso garante que o tráfego passe pela rede da Cloudflare, beneficiando-se de suas proteções e do túnel.

Pode levar alguns minutos para as mudanças de DNS se propagarem globalmente.

Com a rede segura implementada, você está pronto para começar a implantar suas aplicações usando o [Portainer](06-deploy-portainer-geral.md).
