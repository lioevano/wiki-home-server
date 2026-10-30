---
description: "Rede segura na core-services-vm: Traefik como proxy reverso, Cloudflare Tunnel para acesso externo e Authelia para 2FA."
---

# Seção 5: Implementação da Rede Segura (Traefik, Cloudflare Tunnel, Authelia)

Esta seção é fundamental para expor seus serviços auto-hospedados à internet de forma segura, controlada e gerenciada. Implementaremos uma stack de rede robusta na `core-services-vm` composta por:

* **Traefik Proxy:** Atuará como nosso proxy reverso, roteando o tráfego externo para os containers Docker corretos e gerenciando automaticamente os certificados SSL/TLS com Let's Encrypt.
* **Cloudflare Tunnel (`cloudflared`):** Criará uma conexão de saída segura da nossa rede local para a rede global da Cloudflare. Isso elimina a necessidade de abrir portas no roteador doméstico e protege nosso endereço IP público.
* **Authelia:** Servirá como um portal de autenticação e autorização centralizado, adicionando uma camada de segurança com Single Sign-On (SSO) e autenticação de dois fatores (2FA) para os serviços que escolhermos proteger.

Todos esses componentes rodarão como containers Docker na `core-services-vm`, implantados pelo Ansible (playbook `setup-core-networking.yml`) com Docker Compose. As stacks `apps` e `ai` são implantadas depois, pelo Portainer.

## 5.1. Entendendo o Fluxo de Tráfego e o Conceito de Proxy Reverso

Antes de mergulharmos na configuração, é vital entender como o tráfego de um usuário externo alcançará seus serviços internos:

1. **Requisição do Usuário:** O usuário digita `https://meuservico.{{ base_domain }}` no navegador (e.g., `https://nextcloud.seudominio.com`).
2. **Resolução DNS via Cloudflare:** Os nameservers do seu domínio estão configurados para a Cloudflare. A Cloudflare não resolverá o subdomínio para o seu IP doméstico, mas para um endpoint da rede Cloudflare associado ao seu Cloudflare Tunnel.
3. **Cloudflare Edge Network:** A requisição do usuário chega à rede global da Cloudflare. Aqui, ela pode se beneficiar de proteções como mitigação de DDoS e Web Application Firewall (WAF) básico da Cloudflare. Seu IP doméstico real permanece oculto.
4. **Cloudflare Tunnel (`cloudflared` Agent):** O container `cloudflared` rodando na sua `core-services-vm` mantém uma conexão de **saída** persistente e criptografada com o data center da Cloudflare mais próximo. O tráfego destinado aos seus subdomínios configurados no túnel é "puxado" do Cloudflare Edge, através desta conexão segura, para o container `cloudflared` na sua rede local. **Nenhuma porta de entrada precisa ser aberta no seu roteador doméstico.**
5. **`cloudflared` para Traefik:** O container `cloudflared` recebe o tráfego do túnel e o encaminha para o container Traefik. No nosso `docker-compose.yml`, o Public Hostname do túnel envia o tráfego para `https://traefik:443` (serviço Docker `traefik` na rede `proxy` compartilhada, com *No TLS Verify*; ver a [seção 5.5](#55-configuração-de-dns-na-cloudflare)).
6. **Traefik (Proxy Reverso):**
    * Traefik escuta nas portas `80` (HTTP) e `443` (HTTPS) na `core-services-vm` (mapeadas do host da VM para o container Traefik).
    * **Redirecionamento HTTP para HTTPS:** Traefik está configurado para redirecionar automaticamente todo o tráfego chegando na porta `80` para HTTPS na porta `443`.
    * **Roteamento Baseado em Host:** Traefik inspeciona o cabeçalho `Host` da requisição HTTP (e.g., `nextcloud.seudominio.com`).
    * **Middleware de Autenticação (Authelia):** Se a rota do Traefik para o serviço estiver configurada com o middleware Authelia (e.g., `authelia-forwardauth@docker`), Traefik primeiro consulta o container Authelia para verificar a autenticação do usuário.
        * Se o usuário não estiver logado, Authelia instrui Traefik a redirecionar o usuário para o portal de login do Authelia (e.g., `https://auth.seudominio.com`).
        * Após o login bem-sucedido (incluindo 2FA), Authelia estabelece uma sessão (via cookie) e informa ao Traefik que o usuário está autenticado.
    * **Gerenciamento de Certificados SSL/TLS (Let's Encrypt):** Traefik automaticamente solicita, renova e gerencia certificados SSL/TLS da Let's Encrypt para todos os seus subdomínios expostos. Ele utiliza o **desafio DNS-01** com a API da Cloudflare (usando o token API que configuraremos), o que é robusto e não requer que portas HTTP estejam abertas para o mundo. Os certificados são armazenados no arquivo `acme.json` (em um volume NFS).
    * **Roteamento para o Serviço Docker de Destino:** Com base nas *labels* Docker definidas no `docker-compose.yml` do serviço de destino (e após autenticação bem-sucedida, se aplicável), Traefik encaminha a requisição para o container Docker correto e sua porta interna.
7. **Serviço Docker:** O container da aplicação (e.g., Nextcloud) processa a requisição e envia a resposta de volta pelo mesmo caminho.

!!! tip "Diagrama Visual do Fluxo"
    Para uma representação gráfica detalhada deste fluxo, consulte o diagrama na seção [Fluxo de Rede e Acesso Externo da Visão Geral da Arquitetura](../02-visao-geral-arquitetura/01-fluxo-rede-acesso-externo.md).

## 5.2. Docker Compose para a Stack Core (`docker/stacks/core/docker-compose.yml`)

Esta stack fundamental inclui os containers Traefik e Cloudflared. Crie o arquivo `server/docker/stacks/core/docker-compose.yml` com o seguinte conteúdo:

```yaml title="docker/stacks/core/docker-compose.yml"
# docker/stacks/core/docker-compose.yml
# Infraestrutura base: Traefik + Cloudflare Tunnel + Authelia
# Roda na core-services-vm
version: '3.9'

networks:
  proxy:
    name: proxy
    external: true
  internal_services:
    name: internal_services
    external: true

services:
  traefik:
    image: traefik:v3.7.16
    container_name: traefik
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    networks:
      - proxy
    ports:
      - "${CORE_SERVICES_VM_IP_VAR}:80:80"
      - "${CORE_SERVICES_VM_IP_VAR}:443:443"
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock:ro"
      - "${VM_NFS_MOUNT_BASE_PATH}/${ZFS_DOCKER_VOLUMES_DATASET_NAME}/traefik/data:/data"
      - "${VM_NFS_MOUNT_BASE_PATH}/${ZFS_DOCKER_VOLUMES_DATASET_NAME}/traefik/config/traefik.yml:/traefik.yml:ro"
      - "${VM_NFS_MOUNT_BASE_PATH}/${ZFS_DOCKER_VOLUMES_DATASET_NAME}/traefik/config/dynamic:/etc/traefik/dynamic_configs:ro"
      - "/etc/localtime:/etc/localtime:ro"
    environment:
      - CF_DNS_API_TOKEN=${CLOUDFLARE_API_TOKEN_FROM_VAULT}
    labels:
      traefik.enable: "true"
      traefik.http.routers.traefik-dashboard.rule: "Host(`traefik.${BASE_DOMAIN_FROM_VAULT}`)"
      traefik.http.routers.traefik-dashboard.entrypoints: websecure
      traefik.http.routers.traefik-dashboard.service: api@internal
      traefik.http.routers.traefik-dashboard.tls.certresolver: letsencrypt
      traefik.http.routers.traefik-dashboard.middlewares: authelia-forwardauth@docker
    healthcheck:
      test: ["CMD", "traefik", "healthcheck", "--ping"]
      interval: 10s
      timeout: 2s
      retries: 3
      start_period: 15s

  cloudflared:
    image: cloudflare/cloudflared:2026.10.5
    container_name: cloudflared
    restart: unless-stopped
    networks:
      - proxy
    command: tunnel --no-autoupdate --metrics 0.0.0.0:2000 run --token ${CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT} # métricas para o job cloudflared:2000 do Prometheus
    depends_on:
      traefik:
        condition: service_healthy

  authelia_db:
    image: postgres:17-alpine
    labels:
      diun.watch_repo: "false" # tag de série: vigia o digest da própria tag (rebuilds de segurança)
      diun.include_tags: ".*"
      diun.notify_on: "new;update"
    container_name: authelia_db
    restart: unless-stopped
    volumes:
      - "${AUTHELIA_DB_PATH}:/var/lib/postgresql/data" # disco local da VM; dump diário para o NFS
    networks:
      - internal_services
    environment:
      - POSTGRES_DB=authelia
      - POSTGRES_USER=authelia
      - POSTGRES_PASSWORD=${AUTHELIA_STORAGE_POSTGRES_PASSWORD_FROM_VAULT}
      - TZ=${SYSTEM_TIMEZONE}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U authelia -d authelia -h localhost"]
      interval: 10s
      timeout: 5s
      retries: 5

  authelia:
    image: authelia/authelia:4.39.28
    container_name: authelia
    restart: unless-stopped
    volumes:
      - "${VM_NFS_MOUNT_BASE_PATH}/${ZFS_DOCKER_VOLUMES_DATASET_NAME}/authelia/config:/config"
      - "/etc/localtime:/etc/localtime:ro"
    networks:
      - proxy
      - internal_services
    expose:
      - "9091"
    environment:
      - TZ=${SYSTEM_TIMEZONE}
    depends_on:
      authelia_db:
        condition: service_healthy
    labels:
      traefik.enable: "true"
      traefik.http.routers.authelia-portal.rule: "Host(`auth.${BASE_DOMAIN_FROM_VAULT}`)"
      traefik.http.routers.authelia-portal.entrypoints: websecure
      traefik.http.routers.authelia-portal.tls.certresolver: letsencrypt
      traefik.http.routers.authelia-portal.service: authelia-svc
      traefik.http.services.authelia-svc.loadbalancer.server.port: "9091"
      traefik.http.middlewares.authelia-forwardauth.forwardauth.address: "http://authelia:9091/api/authz/forward-auth"
      # false: o Traefik monta o X-Forwarded-Host/-Uri/-Method/-Proto do pedido real. Com true, um X-Forwarded-Host
      # forjado pela internet (o cloudflared é proxy confiável e repassa os cabeçalhos do visitante) faria o
      # Authelia avaliar outro domínio (ex.: um bypass) enquanto o Traefik entrega o domínio real.
      traefik.http.middlewares.authelia-forwardauth.forwardauth.trustForwardHeader: "false"
      traefik.http.middlewares.authelia-forwardauth.forwardauth.maxResponseBodySize: "8192"
      traefik.http.middlewares.authelia-forwardauth.forwardauth.authResponseHeaders: "Remote-User,Remote-Groups,Remote-Name,Remote-Email"
```

!!! note "Variáveis de Ambiente no Docker Compose"
    Variáveis como `${CORE_SERVICES_VM_IP_VAR}`, `${VM_NFS_MOUNT_BASE_PATH}`, `${AUTHELIA_DB_PATH}`, `${ZFS_DOCKER_VOLUMES_DATASET_NAME}`, `${CLOUDFLARE_API_TOKEN_FROM_VAULT}`, `${BASE_DOMAIN_FROM_VAULT}`, e `${CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT}` são placeholders que serão substituídos:
    pelos valores que o playbook `setup-core-networking.yml` passa no bloco `environment:` da tarefa de deploy (vault, inventário e `group_vars`). A stack `core` não tem `.env` em disco nem é criada no Portainer.

## 5.3. Authelia (parte de `docker/stacks/core/docker-compose.yml`)

Authelia fornecerá o portal de autenticação e o serviço de 2FA. O conteúdo está incluído em `docker/stacks/core/docker-compose.yml` junto com Traefik e Cloudflared.

!!! warning "Banco do Authelia fora dos snapshots ZFS"
    O Postgres do Authelia (`authelia_db`: dispositivos 2FA, sessões e consentimentos OIDC) fica no disco local da `core-services-vm`, em `/opt/local-data/authelia-db`: o Postgres exige ser dono dos arquivos, o que o NFS com `all_squash` não permite (regra DAD-5). O backup é o dump diário `backup-authelia-db` (03:15) em `docker-volumes/authelia/db-dumps/`, instalado pelo `setup-core-networking.yml` ([backup](../04-manutencao-recuperacao/02-backup-restore-estrategia.md#bancos-de-dados-dumps-diários)). Os usuários (`users_database.yml`) e a configuração ficam no NFS.

Os serviços `authelia` e `authelia_db` estão no bloco da [seção 5.2](#52-docker-compose-para-a-stack-core-dockerstackscoredocker-composeyml). O que importa neles:

| Item | Valor | Por quê |
|---|---|---|
| Imagem | `authelia/authelia:4.39.28` | Versão fixada (política de versões). Comandos do Authelia: `docker exec authelia authelia …` |
| Middleware `authelia-forwardauth` | `http://authelia:9091/api/authz/forward-auth` | Endpoint atual do forward-auth (o `/api/verify` é legado). A URL do portal vem de `session.cookies[].authelia_url` |
| `trustForwardHeader` | `false` | O Traefik monta o `X-Forwarded-Host`, `-Uri`, `-Method` e `-Proto` que o Authelia avalia a partir do pedido real. Com `true`, um visitante mandaria um `X-Forwarded-Host` forjado (o cloudflared é proxy confiável e repassa os cabeçalhos) e o Authelia avaliaria outro domínio, por exemplo um com `bypass`, enquanto o Traefik entrega o domínio pedido. O preço: o Authelia vê o IP do cloudflared, não o do visitante (o bloqueio por tentativas erradas é por usuário) |
| `maxResponseBodySize` | `8192` | Limite da resposta do Authelia (o exemplo oficial); sem ele, o Traefik aceitaria qualquer tamanho |
| `authResponseHeaders` | `Remote-User,Remote-Groups,Remote-Name,Remote-Email` | Quem passou pelo Authelia chega ao backend com esses cabeçalhos (um app que confie no proxy pode usar o `Remote-User`) |
| Banco | `postgres:17-alpine` em `${AUTHELIA_DB_PATH}`, só na rede `internal_services` | Disco local (DAD-5), dump diário no NFS |


## 5.4. Playbook `ansible/playbooks/setup-core-networking.yml`

Este playbook Ansible prepara os arquivos de configuração e faz o deploy da stack `core` (Traefik, Cloudflared e Authelia, num único compose).

**Principais Ações do Playbook:**

  1. **Cria Redes Docker:** Garante que as redes `proxy` e `internal_services` existam na `core-services-vm`.
  2. **Executa Role `infra/traefik-config`:**
      * Cria os diretórios de configuração e dados para Traefik no volume NFS.
      * Copia o `traefik.yml` (config estática) templateado.
      * Copia os arquivos de configuração dinâmica (middlewares como `security_headers.yml`, `nextcloud_middleware.yml`, e o roteamento para os serviços da VM de IA em `ai_services.yml`) para o diretório apropriado.
      * Garante que o arquivo `acme.json` (para certificados SSL) exista com as permissões corretas.
  3. **Executa Role `infra/authelia-config`:**
      * Cria o diretório de configuração do Authelia no volume NFS e o do banco no disco local da VM (`/opt/local-data/authelia-db`).
      * Copia o `configuration.yml` e o `users_database.yml` (base de usuários do backend `file`) templateados.
  4. **Copia o compose para a VM:** o módulo de deploy roda na `core-services-vm`, então o `docker/stacks/core/docker-compose.yml` do repositório é copiado para `/opt/stacks/core/` na VM.
  5. **Deploy da Stack `core`:** Usa o módulo `community.docker.docker_compose_v2` sobre `/opt/stacks/core/`, injetando as variáveis de ambiente do Ansible Vault, do inventário e de `group_vars`.
  6. **Aguarda Traefik:** Espera o healthcheck do Traefik passar.
  7. **Dump diário do banco do Authelia:** instala o `backup-authelia-db` (03:15) pelo `ansible/playbooks/tasks/dump-postgres.yml` ([backup](../04-manutencao-recuperacao/02-backup-restore-estrategia.md#bancos-de-dados-dumps-diários)).

### Ações Preparatórias: Roles Ansible para Configuração

Antes de criar o playbook, precisamos dos roles que preparam os arquivos de configuração.

Os dois roles (`traefik-config` e `authelia-config`) só geram arquivos de configuração: não têm `defaults/`. As versões das imagens da stack `core` ficam num lugar só, o compose da [seção 5.2](#52-docker-compose-para-a-stack-core-dockerstackscoredocker-composeyml).

#### Role: `ansible/roles/infra/traefik-config/`

Este role prepara os arquivos de configuração do Traefik.

##### `tasks/main.yml`

```yaml title="ansible/roles/infra/traefik-config/tasks/main.yml"
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

- name: "Copiar o roteamento dos serviços da ai-desktop-vm (se ela existir)"
  ansible.builtin.template:
    src: dynamic_ai_services.yml.j2 # LiteLLM, Open WebUI, Langfuse e segundo cérebro, em outra VM
    dest: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/traefik/config/dynamic/ai_services.yml"
    owner: "{{ docker_puid }}"
    group: "{{ docker_pgid }}"
    mode: '0640'
  when: "'ai-desktop-vm' in groups['virtual_machines']" # Só cria se a VM AI estiver no inventário
  no_log: true # contém o segredo do kanban. (posto_chave_proxy)

# Middlewares dos agentes (página 16) com segredo: no arquivo, e não em label, para não aparecer no docker inspect.
- name: "Copiar os middlewares dos agentes (segredo da tela de aprovações)"
  ansible.builtin.template:
    src: dynamic_agents.yml.j2
    dest: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/traefik/config/dynamic/agents.yml"
    owner: "{{ docker_puid }}"
    group: "{{ docker_pgid }}"
    mode: '0640'
  no_log: true

# Nome antigo do mesmo arquivo (rag_services.yml): sairia em dobro no Traefik (routers repetidos).
- name: "Remover o arquivo de roteamento com o nome antigo"
  ansible.builtin.file:
    path: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/traefik/config/dynamic/rag_services.yml"
    state: absent

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

```yaml title="ansible/roles/infra/traefik-config/templates/traefik.yml.j2"
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
      aliasHeadersStrategy: delete # descarta nomes com '_', '.' etc. (ex.: Remote_User forjado); v3.7 avisa se faltar
  websecure: # Entrypoint principal para HTTPS na porta 443
    address: ":443"
    # O cloudflared chega pela rede Docker 'proxy' (172.16.0.0/12) e informa o IP real do visitante em
    # X-Forwarded-For. Confiar só nessa faixa deixa as aplicações (ex.: Jellyfin) distinguirem acesso
    # da internet de acesso local; clientes da LAN chegam com o próprio IP e não podem forjar o cabeçalho.
    forwardedHeaders:
      trustedIPs:
        - "172.16.0.0/12"
    http:
      # Cabeçalhos com '_', '.' ou outro caractere fora de letra/dígito/hífen são descartados: um Remote_User forjado
      # não chega ao backend como se fosse o Remote-User do forward-auth do Authelia.
      aliasHeadersStrategy: delete
      tls:
        certResolver: "letsencrypt" # Resolvedor padrão para certificados TLS
        domains: # Opcional: Define domínios para os quais gerar certificados "on-demand"
          - main: "{{ base_domain }}" # Seu domínio principal
            sans: # Subdomínios alternativos (SANs)
              - "*.{{ base_domain }}" # Wildcard para todos os subdomínios
      middlewares: # Middlewares globais aplicados a TODAS as rotas no entrypoint websecure
        - "securityHeaders@file" # Referencia o middleware de headers de segurança (definido em dynamic/security_headers.yml)

  traefik: # Entrypoint interno do /ping (healthcheck do compose), na 8080 do container; não é publicado
    address: ":8080"
    http:
      aliasHeadersStrategy: delete

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
        # propagation:
        #   delayBeforeChecks: 0s # Padrão geralmente funciona bem (nome da v3.3+; antes, delayBeforeCheck)
        # resolvers: # Opcional: especificar servidores DNS para verificação do desafio
        #  - "1.1.1.1:53"
        #  - "8.8.8.8:53"

# Configurações de Log (opcional, mas útil para debug)
log:
  level: INFO # Níveis: TRACE, DEBUG, INFO, WARN, ERROR, FATAL, PANIC
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

```yaml title="ansible/roles/infra/traefik-config/templates/security_headers.yml.j2"
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

##### `templates/dynamic_ai_services.yml.j2` (Roteamento para VM de IA)

```yaml title="ansible/roles/infra/traefik-config/templates/dynamic_ai_services.yml.j2"
# ansible/roles/infra/traefik-config/templates/dynamic_ai_services.yml.j2
# (Copiado para /etc/traefik/dynamic_configs/ai_services.yml no container Traefik)
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
        - "authelia-forwardauth@docker" # Protegido por Authelia (middleware definido no compose do Authelia)

    litellm-dynamic: # Tela de uso e administração do LiteLLM (llm.); a API fica só na LAN
      entryPoints: ["websecure"]
      rule: "Host(`llm.{{ base_domain }}`)"
      service: "litellm-svc-dynamic"
      tls:
        certResolver: "letsencrypt"
      middlewares:
        - "authelia-forwardauth@docker"

    langfuse-dynamic: # Rastreio de LLM e ferramentas (página 13); login do Langfuse pelo OIDC do mesmo Authelia
      entryPoints: ["websecure"]
      rule: "Host(`langfuse.{{ base_domain }}`)"
      service: "langfuse-svc-dynamic"
      tls:
        certResolver: "letsencrypt"
      middlewares:
        - "authelia-forwardauth@docker"

    # Posto de agentes (página 16): o Vibe Kanban não tem login próprio; o Authelia (grupo admins) é a porta, e o
    # segredo injetado depois dela é o que o Caddy do posto exige (sem ele, 403).
    kanban-dynamic:
      entryPoints: ["websecure"]
      rule: "Host(`kanban.{{ base_domain }}`)"
      service: "kanban-svc-dynamic"
      tls:
        certResolver: "letsencrypt"
      middlewares:
        - "authelia-forwardauth@docker"
        - "posto-chave"

    # Segundo cérebro (página 12). notas. e escrita. sem Authelia: o mcp-auth-proxy faz o OAuth do claude.ai e
    # manda o login para o OIDC do Authelia (regras bypass no configuration.yml). sync. é o painel do Syncthing.
    notas-dynamic:
      entryPoints: ["websecure"]
      rule: "Host(`notas.{{ base_domain }}`)"
      service: "notas-svc-dynamic"
      tls:
        certResolver: "letsencrypt"

    escrita-dynamic:
      entryPoints: ["websecure"]
      rule: "Host(`escrita.{{ base_domain }}`)"
      service: "escrita-svc-dynamic"
      tls:
        certResolver: "letsencrypt"

    syncthing-dynamic:
      entryPoints: ["websecure"]
      rule: "Host(`sync.{{ base_domain }}`)"
      service: "syncthing-svc-dynamic"
      tls:
        certResolver: "letsencrypt"
      middlewares:
        - "authelia-forwardauth@docker"

    # Adicione aqui roteadores para outros serviços da ai-desktop-vm se necessário
    # Exemplo para um hipotético OpenNotebookLM
    # opennotebooklm-dynamic:
    #   entryPoints: ["websecure"]
    #   rule: "Host(`notebooklm.{{ base_domain }}`)"
    #   service: "opennotebooklm-svc-dynamic"
    #   tls: { certResolver: "letsencrypt" }
    #   middlewares: ["authelia-forwardauth@docker"]

  middlewares:
    posto-chave: # o Caddy do posto só repassa ao Vibe Kanban o que trouxer este segredo (página 16)
      headers:
        customRequestHeaders:
          X-Posto-Chave: "{{ posto_chave_proxy }}"

  services:
    openwebui-svc-dynamic: # Serviço Traefik para OpenWebUI
      loadBalancer:
        servers:
          # Aponta para o IP da ai-desktop-vm e a porta que o compose da stack ai publica (3000 -> 8080 no container).
          # A variável ai_desktop_vm_ip_var vem do inventário Ansible (hosts.ini).
          - url: "http://{{ ai_desktop_vm_ip_var }}:3000"

    litellm-svc-dynamic:
      loadBalancer:
        servers:
          - url: "http://{{ ai_desktop_vm_ip_var }}:4000"

    langfuse-svc-dynamic:
      loadBalancer:
        servers:
          - url: "http://{{ ai_desktop_vm_ip_var }}:3100"

    kanban-svc-dynamic: # Caddy da stack posto; a porta 3005 só aceita a core (firewall das portas do Docker)
      loadBalancer:
        servers:
          - url: "http://{{ ai_desktop_vm_ip_var }}:3005"

    notas-svc-dynamic: # mcp_auth_busca (stack notes)
      loadBalancer:
        servers:
          - url: "http://{{ ai_desktop_vm_ip_var }}:8481"

    escrita-svc-dynamic: # mcp_auth_escrita (stack notes)
      loadBalancer:
        servers:
          - url: "http://{{ ai_desktop_vm_ip_var }}:8482"

    syncthing-svc-dynamic:
      loadBalancer:
        servers:
          - url: "http://{{ ai_desktop_vm_ip_var }}:8384"

    # opennotebooklm-svc-dynamic:
    #   loadBalancer:
    #     servers:
    #       - url: "http://{{ ai_desktop_vm_ip_var }}:7860" # Porta interna do Open-NotebookLM
```

##### `templates/dynamic_agents.yml.j2` (Segredo da tela de aprovações)

O `aprovador` ([seção 16](16-posto-agentes.md#aprovação-humana)) declara o router `aprovacoes.` por labels, como qualquer serviço da core, mas o segredo que só o Traefik injeta mora neste arquivo: um label aparece para quem lê o `docker inspect` (o `ops` e o observador listam containers).

```yaml title="ansible/roles/infra/traefik-config/templates/dynamic_agents.yml.j2"
# ansible/roles/infra/traefik-config/templates/dynamic_agents.yml.j2
# (Copiado para dynamic/agents.yml no container Traefik.) Middlewares dos agentes com segredo (página 16).
http:
  middlewares:
    aprovador-chave: # a tela do aprovador só aceita requisições com este segredo (outro container da rede proxy não)
      headers:
        customRequestHeaders:
          X-Aprovador-Chave: "{{ aprovador_chave_proxy }}"
```

##### `templates/nextcloud_middleware.yml.j2` (Middleware para Nextcloud)

```yaml title="ansible/roles/infra/traefik-config/templates/nextcloud_middleware.yml.j2"
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
        # Uso no router do Nextcloud (stack cloud, página 11; sem Authelia, o login é o OIDC):
        # traefik.http.routers.nextcloud.middlewares: "nextcloud-dav@file,nextcloud-headers@file"
        # Os headers globais (securityHeaders@file) cobrem o geral; aqui ficam só os específicos do Nextcloud.
        # Exemplo de header que poderia ser específico:
        # customRequestHeaders:
        #   X-My-Nextcloud-Header: "true" # Exemplo, não é um header real do Nextcloud
        # Ou, para redirecionamentos .well-known para CalDAV/CardDAV se não tratados de outra forma:
        # (Mas Traefik faria isso com routers, não headers)
        # Headers que o painel de administração do Nextcloud verifica e que não são globais:
        customResponseHeaders:
          X-Robots-Tag: "noindex, nofollow"
          X-Permitted-Cross-Domain-Policies: "none"
    # Descoberta de CalDAV/CardDAV (DAVx⁵ e o aviso do painel de administração do Nextcloud):
    # /.well-known/caldav e /.well-known/carddav levam ao endpoint WebDAV do Nextcloud.
    nextcloud-dav:
      redirectRegex:
        regex: "^https://(.*)/.well-known/(?:card|cal)dav"
        replacement: "https://${1}/remote.php/dav/"
        permanent: true
```

!!! note "Nextcloud Headers"
    Nextcloud tem recomendações específicas de headers de segurança, muitas das quais podem já estar cobertas pelos `securityHeaders@file` globais. Este middleware `nextcloud-headers@file` pode ser usado para adicionar ou sobrescrever headers especificamente para o Nextcloud se necessário. Consulte a documentação do Nextcloud para os headers mais recentes.

#### Role: `ansible/roles/infra/authelia-config/`

Este role prepara os arquivos de configuração do Authelia.

##### `tasks/main.yml`

```yaml title="ansible/roles/infra/authelia-config/tasks/main.yml"
# ansible/roles/infra/authelia-config/tasks/main.yml
- name: "Garantir que diretórios de configuração do Authelia existam na VM (via NFS)"
  ansible.builtin.file:
    path: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/authelia/config"
    state: directory
    owner: "{{ docker_puid }}" # PUID/PGID para que o container Authelia possa ler
    group: "{{ docker_pgid }}"
    mode: '0750' # Authelia só precisa ler (e talvez escrever logs se configurado para arquivos)

# Disco local, não NFS: o Postgres exige ser dono dos arquivos, o que o NFS com all_squash não permite
# (regra DAD-5). O backup é o dump diário do setup-core-networking.yml.
- name: "Garantir que o diretório de dados do PostgreSQL do Authelia exista no disco local da VM"
  ansible.builtin.file:
    path: "{{ vm_local_data_path }}/authelia-db"
    state: directory
    mode: '0700' # sem owner: o entrypoint do Postgres assume o diretório; reexecutar o role não desfaz isso

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
  # Base de usuários do backend 'file' (authentication_backend no configuration.yml).
```

##### `templates/configuration.yml.j2` (Configuração Principal Authelia)

```yaml title="ansible/roles/infra/authelia-config/templates/configuration.yml.j2"
# ansible/roles/infra/authelia-config/templates/configuration.yml.j2
# Configuração Principal do Authelia (gerada por Ansible)

# Tema da interface Authelia (opções: light, dark, grey)
theme: dark

# Segredo do link de redefinição de senha (do vault.yml). Na 4.39 fica aqui, não mais na raiz (jwt_secret).
identity_validation:
  reset_password:
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
  # Um cookie por domínio. O domínio é o pai (seudominio.com, não auth.seudominio.com): o login vale para todos
  # os subdomínios. O authelia_url é o portal: o forward-auth (/api/authz/forward-auth) manda para ele quem
  # ainda não entrou. O default_redirection_url é para onde vai quem abre o portal direto (o painel); não pode
  # ser o próprio portal.
  cookies:
    - domain: "{{ base_domain }}"
      authelia_url: "https://auth.{{ base_domain }}"
      default_redirection_url: "https://home.{{ base_domain }}"
  # Se usar Redis para sessões distribuídas (não coberto neste guia simples):
  # redis:
  #   host: authelia_redis # Nome do serviço Docker do Redis
  #   port: 6379
  #   password: "SENHA_DO_REDIS_SE_HOUVER"
  #   database_index: 1 # Índice do banco de dados Redis

# Armazenamento de Dados do Usuário (PostgreSQL)
# Authelia usará este banco de dados para armazenar informações de usuários, dispositivos 2FA, etc.
storage:
  encryption_key: "{{ authelia_storage_encryption_key }}" # Obrigatório (mín. 20 caracteres); cifra dados sensíveis no banco. Não troque depois de criado o banco.
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
# Define onde ficam os usuários e senhas. O PostgreSQL (storage) guarda sessões,
# preferências e registros de 2FA — ele NÃO é um backend de usuários.
# Usamos o backend 'file' com o users_database.yml gerado pelo role.
authentication_backend:
  file:
    path: /config/users_database.yml # Caminho DENTRO do container Authelia
    password:
      algorithm: argon2
      argon2:
        variant: argon2id
        iterations: 3
        memory: 65536 # KiB (64MB)
        parallelism: 4
        key_length: 32
        salt_length: 16

# Regras de Controle de Acesso
# Define quais domínios/subdomínios são protegidos e qual política aplicar.
access_control:
  default_policy: deny # Política padrão se nenhuma regra corresponder (deny, one_factor, two_factor, bypass)
  rules:
    # Regra para o próprio portal Authelia (auth.seudominio.com)
    # Usuários precisam acessá-lo para logar, então não deve ser protegido pelo próprio Authelia.
    - domain: "auth.{{ base_domain }}"
      policy: bypass # Não requer autenticação para acessar o portal de login

    # Webhooks do n8n (integração notificacoes): quem chama não faz login; a proteção é o token
    # no cabeçalho Authorization, conferido pelo próprio workflow. Só o caminho /webhook/ é liberado.
    - domain: "n8n.{{ base_domain }}"
      resources:
        - "^/webhook/.*$"
      policy: bypass

    # Aplicações públicas (Exposição = publica no catálogo), com login próprio: os apps do Jellyfin
    # não passam pelo Authelia, e o Seerr entra com a conta do Jellyfin (página 10).
    - domain: "jellyfin.{{ base_domain }}"
      policy: bypass
    - domain: "pedidos.{{ base_domain }}"
      policy: bypass
    # Fotos e arquivos (página 11): login próprio de cada app pelo OIDC deste Authelia (identity_providers
    # abaixo, com two_factor), que funciona também nos apps de celular e desktop. O Collabora (office.) é
    # aberto pelo navegador dentro do Nextcloud e protegido pelo token WOPI que o Nextcloud gera.
    - domain: "fotos.{{ base_domain }}"
      policy: bypass
    - domain: "nextcloud.{{ base_domain }}"
      policy: bypass
    - domain: "office.{{ base_domain }}"
      policy: bypass
    # Conectores MCP do segundo cérebro (página 12): o claude.ai e o Claude Code fazem OAuth com o mcp-auth-proxy,
    # que manda o login para o OIDC deste Authelia (cliente 'mcp', two_factor, só o grupo admins).
    - domain: "notas.{{ base_domain }}"
      policy: bypass
    - domain: "escrita.{{ base_domain }}"
      policy: bypass
    # Conector Servidor (base dos agentes, página 13): rota de leitura do hub de MCPs, mesmo esquema (cliente 'mcp').
    - domain: "servidor.{{ base_domain }}"
      policy: bypass

    # Painéis de administração (authelia_dominios_admins, página 01): só o grupo admins entra. A regra com
    # subject só casa com quem está no grupo; a seguinte recusa os demais (sem ela, eles cairiam no curinga).
    - domain:
{% for sub in authelia_dominios_admins %}
        - "{{ sub }}.{{ base_domain }}"
{% endfor %}
      subject: "group:admins"
      policy: two_factor
    - domain:
{% for sub in authelia_dominios_admins %}
        - "{{ sub }}.{{ base_domain }}"
{% endfor %}
      policy: deny

    # Regra geral para todos os outros subdomínios do seu domínio base: requer dois fatores.
    - domain: "*.{{ base_domain }}"
      policy: two_factor # Requer login bem-sucedido com primeiro e segundo fator

    # Exemplo: Permitir acesso da rede local sem Authelia (bypass) para certos serviços.
    # Cuidado ao usar bypass, pois anula a proteção do Authelia para essas condições.
    # - domain: "servico_local.{{ base_domain }}"
    #   networks: # IPs ou CIDRs da sua rede local
    #     - "192.168.15.0/24"
    #   policy: bypass

# Notificador (para reset de senha, alertas de segurança, etc.) - ALTAMENTE RECOMENDADO
# Configure para receber notificações por email.
# Notificador (obrigatório): envia códigos de registro de 2FA e de redefinição de senha.
# Padrão: arquivo dentro do volume de configuração (leia com: cat <NFS>/authelia/config/notification.txt).
# Para e-mail, troque 'filesystem' pelo bloco 'smtp' comentado abaixo.
notifier:
  filesystem:
    filename: /config/notification.txt
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

# Provedor OpenID Connect (SSO): Immich e Nextcloud (página 11) e Open WebUI (página 08) entram com a conta e o 2FA deste Authelia.
# Segredos no vault: hmac_secret, a chave RSA de assinatura (jwks) e, de cada cliente, só o digest
# pbkdf2-sha512 do segredo (o segredo em claro fica com o app).
identity_providers:
  oidc:
    hmac_secret: "{{ authelia_oidc_hmac_secret }}"
    jwks:
      - key_id: "principal"
        algorithm: "RS256"
        use: "sig"
        key: |
          {{ authelia_oidc_jwks_key | indent(10) }}
    # Quem pode entrar em cada aplicação pelo OIDC (além do 2FA): sem a política, qualquer usuário do Authelia
    # ganharia conta no Nextcloud ou no Immich.
    # Na 4.39 o ID token só traz os claims padrão; o resto fica no userinfo. Os clientes daqui foram configurados
    # contra o comportamento da 4.38 (o Langfuse e o mcp-auth-proxy leem o perfil do ID token), então todos usam
    # a política "legado", que devolve ao ID token os claims de antes (documentação do Authelia, "Restore
    # Functionality Prior to Claims Parameter").
    claims_policies:
      legado:
        id_token: ["rat", "groups", "email", "email_verified", "alt_emails", "preferred_username", "name"]
    authorization_policies:
      so_admins:
        default_policy: deny
        rules:
          - policy: two_factor
            subject: "group:admins"
      familia: # fotos e arquivos: quem estiver no grupo users
        default_policy: deny
        rules:
          - policy: two_factor
            subject: "group:users"
    clients:
      - client_id: "immich"
        client_name: "Immich"
        client_secret: "{{ oidc_clients.immich.secret_digest }}"
        public: false
        authorization_policy: "familia"
        claims_policy: "legado"
        pre_configured_consent_duration: "1y" # consentimento lembrado (sem tela a cada login)
        require_pkce: true
        pkce_challenge_method: "S256"
        redirect_uris:
          - "https://fotos.{{ base_domain }}/auth/login"
          - "https://fotos.{{ base_domain }}/user-settings"
          - "app.immich:///oauth-callback" # app do celular
        scopes: ["openid", "profile", "email"]
        response_types: ["code"]
        grant_types: ["authorization_code"]
        userinfo_signed_response_alg: "none"
        token_endpoint_auth_method: "client_secret_basic"
      - client_id: "nextcloud"
        client_name: "Nextcloud"
        client_secret: "{{ oidc_clients.nextcloud.secret_digest }}"
        public: false
        authorization_policy: "familia"
        claims_policy: "legado"
        pre_configured_consent_duration: "1y" # consentimento lembrado (sem tela a cada login)
        require_pkce: true
        pkce_challenge_method: "S256"
        redirect_uris:
          - "https://nextcloud.{{ base_domain }}/apps/user_oidc/code"
        scopes: ["openid", "profile", "email", "groups"]
        response_types: ["code"]
        grant_types: ["authorization_code"]
        userinfo_signed_response_alg: "none"
        token_endpoint_auth_method: "client_secret_post"
      - client_id: "openwebui"
        client_name: "Open WebUI"
        client_secret: "{{ oidc_clients.openwebui.secret_digest }}"
        public: false
        authorization_policy: "so_admins"
        claims_policy: "legado"
        pre_configured_consent_duration: "1y" # consentimento lembrado (sem tela a cada login)
        require_pkce: true
        pkce_challenge_method: "S256"
        redirect_uris:
          - "https://openwebui.{{ base_domain }}/oauth/oidc/callback"
        scopes: ["openid", "profile", "groups", "email"] # groups: o Open WebUI só aceita quem está em 'admins'
        response_types: ["code"]
        grant_types: ["authorization_code"]
        userinfo_signed_response_alg: "none"
        token_endpoint_auth_method: "client_secret_basic"
      # Os dois mcp-auth-proxy do segundo cérebro (página 12). Sem PKCE: o proxy não o envia ao provedor; ele
      # mesmo exige PKCE dos clientes MCP (claude.ai, Claude Code). Só quem está no grupo admins passa.
      - client_id: "mcp"
        client_name: "Conectores MCP (notas e servidor)"
        client_secret: "{{ oidc_clients.mcp.secret_digest }}"
        public: false
        authorization_policy: "so_admins"
        claims_policy: "legado"
        pre_configured_consent_duration: "1y" # consentimento lembrado (sem tela a cada login)
        require_pkce: false
        redirect_uris:
          - "https://notas.{{ base_domain }}/.auth/oidc/callback"
          - "https://escrita.{{ base_domain }}/.auth/oidc/callback"
          - "https://servidor.{{ base_domain }}/.auth/oidc/callback"
        scopes: ["openid", "profile", "email", "groups"]
        response_types: ["code"]
        grant_types: ["authorization_code"]
        userinfo_signed_response_alg: "none"
        token_endpoint_auth_method: "client_secret_basic"
      # Langfuse (página 13): rastreio das chamadas de LLM e de ferramentas; login só pelo SSO.
      - client_id: "langfuse"
        client_name: "Langfuse"
        client_secret: "{{ oidc_clients.langfuse.secret_digest }}"
        public: false
        authorization_policy: "so_admins"
        claims_policy: "legado"
        pre_configured_consent_duration: "1y" # consentimento lembrado (sem tela a cada login)
        require_pkce: true
        pkce_challenge_method: "S256"
        redirect_uris:
          - "https://langfuse.{{ base_domain }}/api/auth/callback/custom"
        scopes: ["openid", "profile", "email", "groups"]
        response_types: ["code"]
        grant_types: ["authorization_code"]
        userinfo_signed_response_alg: "none"
        token_endpoint_auth_method: "client_secret_basic"

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

!!! info "Grupos: quem entra onde"
    - **`admins`**: os painéis de administração listados em `authelia_dominios_admins` (página 01: Traefik, Portainer, Grafana, Prometheus, n8n, LiteLLM, Open WebUI, Langfuse, Syncthing, as *arr e o qBittorrent) e os clientes OIDC da política `so_admins` (Open WebUI, conectores MCP, Langfuse). Um usuário fora do grupo recebe **acesso negado**, mesmo com 2FA.
    - **`users`**: os clientes OIDC da política `familia` (Immich e Nextcloud). Só ganha conta neles quem está neste grupo.
    - Os demais subdomínios protegidos (`home.`, `hass.`) aceitam qualquer usuário com 2FA.

    O consentimento de cada cliente OIDC é lembrado por um ano (`pre_configured_consent_duration`), então a tela "permitir acesso" não aparece a cada login.

##### `templates/users_database.yml.j2` (Usuários do backend `file`)

```yaml title="ansible/roles/infra/authelia-config/templates/users_database.yml.j2"
# ansible/roles/infra/authelia-config/templates/users_database.yml.j2
# Arquivo de Banco de Dados de Usuários Locais do Authelia (gerado por Ansible)
# Hashes de senha: 'authelia crypto hash generate argon2' (ou pbkdf2-sha512, como o do scripts/gerar_vault.py)
# Base de usuários do backend 'file' (authentication_backend em configuration.yml).
# O PostgreSQL ('storage') guarda sessões e 2FA, não os usuários.

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

```yaml title="ansible/playbooks/setup-core-networking.yml"
# ansible/playbooks/setup-core-networking.yml
- hosts: core-services-vm
  become: yes
  vars_files:
    - ../inventories/home/group_vars/all/vault.yml
  vars:
    core_stack_dir_on_vm: "/opt/stacks/core"

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

    # O módulo de deploy roda na VM: o compose do repositório (máquina de controle) é copiado para lá.
    - name: "Garantir diretório da stack core na VM"
      ansible.builtin.file:
        path: "{{ core_stack_dir_on_vm }}"
        state: directory
        owner: root
        group: root
        mode: "0755"

    - name: "Copiar o compose da stack core para a VM"
      ansible.builtin.copy:
        src: "{{ playbook_dir }}/../../docker/stacks/core/docker-compose.yml"
        dest: "{{ core_stack_dir_on_vm }}/docker-compose.yml"
        owner: root
        group: root
        mode: "0644"

    - name: "Deploy Core Stack (Traefik, Cloudflared, Authelia)"
      community.docker.docker_compose_v2:
        project_src: "{{ core_stack_dir_on_vm }}"
        files:
          - docker-compose.yml
        state: present
        remove_orphans: true
        pull: always
      environment:
        # Traefik
        CLOUDFLARE_API_TOKEN_FROM_VAULT: "{{ cloudflare_api_token }}"
        BASE_DOMAIN_FROM_VAULT: "{{ base_domain }}"
        # Cloudflared
        CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT: "{{ cloudflare_tunnel_token }}"
        # Authelia
        SYSTEM_TIMEZONE: "{{ system_timezone }}"
        AUTHELIA_STORAGE_POSTGRES_PASSWORD_FROM_VAULT: "{{ authelia_storage_postgres_password }}"
        # Volumes NFS
        VM_NFS_MOUNT_BASE_PATH: "{{ vm_nfs_mount_base_path }}"
        ZFS_DOCKER_VOLUMES_DATASET_NAME: "{{ zfs_docker_volumes_dataset_name }}"
        CORE_SERVICES_VM_IP_VAR: "{{ core_services_vm_ip_var }}"
        # Banco do Authelia no disco local
        AUTHELIA_DB_PATH: "{{ vm_local_data_path }}/authelia-db"
      register: core_stack_deploy_result

    # Dump diário do banco do Authelia (2FA, sessões, consentimentos OIDC) para o NFS, copiado pelo restic.
    - name: "Dump diário do Postgres do Authelia"
      ansible.builtin.include_tasks: tasks/dump-postgres.yml
      vars:
        dump_nome: authelia
        dump_descricao: "do Authelia (página 05)"
        dump_container: authelia_db
        dump_db: authelia
        dump_user: authelia
        dump_destino: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/authelia/db-dumps"
        dump_horario: "*-*-* 03:15:00"

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
2. **Execute a Partir da Máquina de Controle:** Na sua máquina de controle Ansible, entre na pasta `server/ansible` do repositório.
3. **Execute o Playbook:**

    ```bash
    ansible-playbook -i inventories/home/hosts.ini playbooks/setup-core-networking.yml --ask-vault-pass
    ```

    Você será solicitado a fornecer a senha do Ansible Vault.

## 5.5. Configuração de DNS na Cloudflare

Após o deploy bem-sucedido da stack de rede, especialmente do container `cloudflared` (Cloudflare Tunnel), você precisa configurar seus registros DNS na Cloudflare para que seus subdomínios (e.g., `portainer.seudominio.com`, `traefik.seudominio.com`, `auth.seudominio.com`) apontem corretamente para o seu túnel.

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
    * **Domain:** Selecione seu domínio base (`{{ base_domain }}` e.g., `seudominio.com`).
    * **Path:** Deixe em branco (a menos que você queira rotear caminhos específicos para serviços diferentes, o que é mais avançado e geralmente tratado pelo Traefik).
    * **Service Type:** `HTTPS`.
    * **Service URL:** `traefik:443`
        * Isso instrui o Cloudflare Tunnel a encaminhar o tráfego para o container `traefik` na porta `443` (rede Docker `proxy`, onde `cloudflared` e `traefik` estão). Não use `traefik:80`: o entrypoint `web` redireciona tudo para HTTPS e os routers só escutam em `websecure`, o que causaria redirecionamento em loop.
    * **Additional application settings → TLS → No TLS Verify:** ativado. O `cloudflared` conecta pelo nome `traefik`, que não corresponde ao certificado Let's Encrypt do domínio; o trecho Cloudflare → túnel continua cifrado.
    * Clique em "Save hostname".

**Exemplos de Public Hostnames a Adicionar Inicialmente:**

* `portainer.{{ base_domain }}` -> `https://traefik:443`
* `traefik.{{ base_domain }}` -> `https://traefik:443` (para o dashboard do Traefik)
* `auth.{{ base_domain }}` -> `https://traefik:443` (para o portal do Authelia)
* **Catch-all com Wildcard** (é o que o índice de integrações assume para novas aplicações):
    * Subdomain: `*`
    * Domain: `{{ base_domain }}`
    * Service: `https://traefik:443` (com *No TLS Verify*)
    * Confira no DNS do domínio que existe o registro `CNAME` `*` → `<TUNNEL_ID>.cfargotunnel.com`; crie-o se o painel não o criar.
    !!! tip "Vantagem do Catch-All (`*`)"
        Configurar um hostname público com o subdomínio `*` (wildcard) significa que qualquer subdomínio de `{{ base_domain }}` que não tenha uma regra de Public Hostname mais específica na Cloudflare será automaticamente encaminhado para o Traefik. O Traefik então usará suas próprias regras de roteamento (definidas por labels Docker ou File Provider) para direcionar para o container correto. Isso simplifica muito a adição de novos serviços no futuro: você só precisa configurar as labels no Traefik, e não precisará adicionar um novo Public Hostname na Cloudflare toda vez (a menos que queira configurações de túnel muito específicas por subdomínio, como políticas de acesso Cloudflare).

**Opção Alternativa: Usando a flag `--hostname` no `cloudflared`**

Se o seu comando `cloudflared` no `docker-compose.yml` inclui:
`--hostname {{ base_domain }} --url https://traefik:443` (com `--no-tls-verify`)
O `cloudflared` tentará criar e gerenciar automaticamente um registro CNAME para `{{ base_domain }}` e um CNAME wildcard `*.{{ base_domain }}` apontando para o seu túnel.

* **Ação:** Verifique no painel DNS da Cloudflare (não no Zero Trust, mas na seção DNS do seu domínio) se esses CNAMEs foram criados (e.g., `seudominio.com CNAME <TUNNEL_ID>.cfargotunnel.com` e `* CNAME <TUNNEL_ID>.cfargotunnel.com`). O `<TUNNEL_ID>` é o UUID do seu túnel.
* **Menos Flexível:** Esta abordagem é mais simples, mas oferece menos controle granular do que as Ingress Rules/Public Hostnames no dashboard Zero Trust.

**Verificação Importante (em ambos os casos):**

* **Status do Proxy Cloudflare (Nuvem Laranja):** Para todos os registros DNS (CNAMEs) relacionados aos seus serviços expostos, certifique-se de que o "Proxy status" na Cloudflare está **habilitado (nuvem laranja)**. Isso garante que o tráfego passe pela rede da Cloudflare, beneficiando-se de suas proteções e permitindo que o túnel funcione.

Pode levar alguns minutos para que quaisquer novas configurações de DNS ou Public Hostnames se propaguem globalmente.

Com a stack de rede segura implementada e o DNS configurado, você está pronto para o [Deploy Core](06-deploy-core.md).