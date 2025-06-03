# Adicionando um Novo Serviço Docker à Infraestrutura

Uma das grandes vantagens de uma arquitetura baseada em Docker e Portainer, com um proxy reverso como Traefik, é a facilidade de adicionar novos serviços. Este guia fornece um checklist e um exemplo prático para integrar uma nova aplicação containerizada.

## Checklist de Passos para Adicionar um Novo Serviço

Siga este checklist para uma integração suave e consistente:

1.  **Planejamento e Pesquisa do Novo Serviço:**
    *   **Identifique a Imagem Docker:** Qual imagem Docker oficial ou comunitária usar (e.g., do Docker Hub, `lscr.io` da LinuxServer.io, `ghcr.io`)? Verifique a popularidade, manutenção e tags de versão estáveis.
    *   **Recursos Necessários:** Avalie o consumo de CPU, RAM e disco do novo serviço. Ele se encaixa nos recursos da sua `core-services-vm` ou requer uma VM dedicada (ou a `ai-desktop-vm`)?
    *   **Persistência de Dados:** O serviço precisa armazenar dados permanentemente?
        *   Se sim, planeje os volumes necessários. Geralmente, um subdiretório em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/<nome_do_novo_servico>/` é uma boa prática para configurações e dados.
    *   **Configuração de Rede:**
        *   O serviço precisa ser acessado externamente? Se sim, qual subdomínio será usado (e.g., `novoservico.{{ base_domain }}`)?
        *   Será protegido pelo [Authelia](../02-visao-geral-arquitetura/01-fluxo-rede-acesso-externo.md#4-authelia-servidor-de-autenticação-e-autorização)?
        *   Precisa se comunicar com outros serviços internos (e.g., um banco de dados, outro container na rede `internal_services`)?
    *   **Variáveis de Ambiente:** Quais variáveis de ambiente são obrigatórias ou recomendadas para configurar o serviço (e.g., PUID, PGID, TZ, senhas, caminhos específicos, opções de features)? Consulte a documentação da imagem Docker.

2.  **Preparação de Volumes e Arquivo `.env` (Ansible - Opcional, mas Recomendado para Consistência):**
    *   No seu projeto `infra-servidor-domestico/ansible/`:
        *   Crie um novo playbook, por exemplo, `ansible/playbooks/setup-novoservico-volumes.yml`.
        *   Este playbook deve:
            *   Ser executado contra a VM de destino (e.g., `core-services-vm`).
            *   Usar o módulo `ansible.builtin.file` para criar os diretórios necessários no caminho NFS (e.g., `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/novoservico/config`) com as permissões corretas (`owner: {{ docker_puid }}`, `group: {{ docker_pgid }}`, `mode: '0755'` ou `0775`).
            *   Usar o módulo `ansible.builtin.template` para gerar um arquivo `.env` para o novo serviço em `{{ portainer_env_files_dest_path_on_vm }}/novoservico.env` na VM. Este `.env` deve conter PUID, PGID, TZ, caminhos de volume, e outras variáveis não sensíveis, usando o template `ansible/templates/portainer_stack_env.j2` como base.
    *   Execute o novo playbook Ansible: `ansible-playbook ansible/playbooks/setup-novoservico-volumes.yml --ask-vault-pass`.

3.  **Escrever o Arquivo `docker-compose.yml` para a Nova Stack:**
    *   Crie um novo diretório para a stack, por exemplo, `infra-servidor-domestico/docker/stacks/novoservico/`.
    *   Dentro dele, crie o arquivo `docker-compose.yml`.
    *   **Estrutura Típica:**
        ```yaml
        version: '3.9' # Ou a versão mais recente suportada

        networks:
          proxy: # Se for exposto via Traefik
            external: true
          internal_services: # Se precisar se comunicar com outros backends
            external: true

        services:
          novoservico: # Nome do serviço dentro do compose
            image: usuario/imagem-do-servico:tag-estavel
            container_name: nome_do_container_novoservico
            restart: unless-stopped
            networks: # Conecte às redes necessárias
              - proxy
              # - internal_services
            volumes:
              # Use variáveis do .env que serão carregadas no Portainer
              - "${NOVOSERVICO_CONFIG_PATH}:/config" # Mapeia o volume de config
              - "${NOVOSERVICO_DATA_PATH}:/data"   # Mapeia o volume de dados (exemplo)
              # Adicione outros volumes conforme necessário
            environment:
              - PUID=${DOCKER_PUID} # Do .env
              - PGID=${DOCKER_PGID} # Do .env
              - TZ=${SYSTEM_TIMEZONE} # Do .env
              # - OUTRA_VARIAVEL_CONFIG=${VALOR_DA_VARIAVEL} # Do .env ou definida no Portainer
              # - SENHA_ESPECIFICA=${SENHA_DO_NOVOSERVICO_APP} # Esta será definida no Portainer
            labels: # Labels para Traefik (se exposto)
              # --- Labels Traefik ---
              traefik.enable: "true" # Habilita Traefik para este serviço

              # Roteador HTTP
              traefik.http.routers.novoservico.rule: "Host(`novoservico.{{ base_domain }}`)" # Substitua {{ base_domain }} pelo seu domínio real
              traefik.http.routers.novoservico.entrypoints: "websecure" # Usa o entrypoint HTTPS
              traefik.http.routers.novoservico.tls.certresolver: "letsencrypt" # Usa Let's Encrypt

              # Middlewares (e.g., Authelia para proteção)
              # Se precisar de múltiplos middlewares, separe por vírgula: "authelia@docker,meu-outro-middleware@file"
              traefik.http.routers.novoservico.middlewares: "authelia@docker"

              # Serviço (como Traefik deve se conectar ao container)
              traefik.http.services.novoservico.loadbalancer.server.port: "8000" # Porta INTERNA que o container 'novoservico' escuta
              # traefik.http.services.novoservico.loadbalancer.server.scheme: "http" # Se o container escuta em HTTP (padrão)
        ```
    !!! tip "Nomenclatura de Labels Traefik"
        Use nomes consistentes e descritivos para seus roteadores e serviços Traefik (e.g., `traefik.http.routers.nomedoservico...`). O `{{ base_domain }}` nos labels pode ser substituído pelo valor real ou, se o `.env` carregado no Portainer contiver `BASE_DOMAIN`, você pode usar `${BASE_DOMAIN}` no `docker-compose.yml`.

4.  **Deploy da Nova Stack via Portainer:**
    *   Acesse sua instância Portainer.
    *   Selecione o **endpoint Docker correto** (e.g., `local` para `core-services-vm`).
    *   Vá para "Stacks" -> "+ Add stack".
    *   **Nome:** Dê um nome para a stack (e.g., `novoservico-stack`).
    *   **Build method:** "Web editor".
    *   **Web editor:** Cole o conteúdo do seu `docker-stacks/novoservico/docker-compose.yml`.
    *   **Environment variables (Advanced mode):**
        *   **Load variables from .env file:**
            *   Forneça o caminho **DENTRO DA VM** para o arquivo `.env` que foi preparado pelo Ansible (e.g., `/opt/portainer_stack_envs/novoservico.env`).
        *   **Adicionar Secrets Manualmente:**
            *   Para quaisquer senhas ou tokens de API (e.g., `SENHA_DO_NOVOSERVICO_APP` referenciada no compose), adicione-os aqui como variáveis de ambiente. **NÃO** coloque segredos diretamente no `docker-compose.yml` ou no arquivo `.env` versionado.
    *   Clique em "**Deploy the stack**".

5.  **Configuração de DNS na Cloudflare (se exposto externamente):**
    *   Se você usa uma Ingress Rule wildcard (`*.{{ base_domain }}`) no seu Cloudflare Tunnel apontando para Traefik, este passo pode não ser necessário, pois o novo subdomínio (`novoservico.{{ base_domain }}`) já será coberto.
    *   Caso contrário, adicione manualmente um registro **CNAME** no painel DNS da Cloudflare:
        *   **Type:** `CNAME`
        *   **Name:** `novoservico` (o subdomínio do seu novo serviço).
        *   **Target:** O hostname do seu Cloudflare Tunnel (e.g., `SEU_TUNNEL_UUID.cfargotunnel.com`).
        *   **Proxy Status:** Certifique-se de que está **Laranja (Proxied)**.
    *   Aguarde alguns minutos para a propagação do DNS.

6.  **Teste e Pós-Configuração:**
    *   Acesse `https://novoservico.{{ base_domain }}`.
    *   Se protegido por Authelia, você será redirecionado para login.
    *   Verifique os logs do novo container no Portainer para quaisquer erros de inicialização.
    *   Realize qualquer configuração inicial necessária dentro da interface do próprio novo serviço.

## Exemplo Prático: Adicionando `FileBrowser`

FileBrowser é um gerenciador de arquivos web simples e eficaz.

1.  **Planejamento:**
    *   Leve, roda bem na `core-services-vm`.
    *   Dados: Precisa de um diretório para sua configuração (`/config`) e um diretório para os arquivos que ele gerenciará (`/data`). Vamos mapear `/data` para um subdiretório do nosso NFS `docker-volumes` ou até mesmo para `/mnt/pve_data_zfs/media` se quisermos navegar na mídia.
    *   Subdomínio: `files.{{ base_domain }}`.
    *   Proteger com Authelia.

2.  **Preparação Ansible:**
    *   Criar `ansible/playbooks/setup-filebrowser-volumes.yml`.
    *   Tasks para criar `/mnt/pve_data_zfs/docker-volumes/filebrowser/config` e `/mnt/pve_data_zfs/docker-volumes/filebrowser/data` (ou o caminho desejado para os arquivos).
    *   Gerar `/opt/portainer_stack_envs/filebrowser.env` com PUID, PGID, TZ, e os caminhos:
        ```env
        # /opt/portainer_stack_envs/filebrowser.env
        DOCKER_PUID=1000
        DOCKER_PGID=1000
        SYSTEM_TIMEZONE=America/Sao_Paulo
        FILEBROWSER_CONFIG_PATH=/mnt/pve_data_zfs/docker-volumes/filebrowser/config
        FILEBROWSER_DATA_PATH=/mnt/pve_data_zfs/docker-volumes/filebrowser/data # Ou /mnt/pve_data_zfs/media
        ```

3.  **`docker-compose.yml` para FileBrowser:**
    ```yaml
    # docker/stacks/filebrowser/docker-compose.yml
    version: '3.9'
    networks: { proxy: { external: true } }
    services:
      filebrowser:
        image: filebrowser/filebrowser:v2.29.0 # Verifique a tag mais recente
        container_name: filebrowser
        restart: unless-stopped
        networks: [proxy]
        volumes:
          - "${FILEBROWSER_CONFIG_PATH}:/config"
          - "${FILEBROWSER_DATA_PATH}:/srv" # FileBrowser usa /srv como raiz por padrão
          # Opcional: Mapear o banco de dados de config para um arquivo específico
          # - "${FILEBROWSER_CONFIG_PATH}/filebrowser.db:/database/filebrowser.db"
        environment:
          - PUID=${DOCKER_PUID}
          - PGID=${DOCKER_PGID}
          - TZ=${SYSTEM_TIMEZONE}
          - FB_BASEURL=/ # Se não estiver rodando em um sub-path
          # - FB_ADDRESS=0.0.0.0 # Escuta em todas as interfaces dentro do container
          # - FB_PORT=80 # Porta interna do container
        # O usuário/grupo padrão dentro do container FileBrowser pode ser root.
        # Se PUID/PGID são usados, garanta que eles tenham permissão nos volumes mapeados.
        # user: "${DOCKER_PUID}:${DOCKER_PGID}" # Descomente se a imagem suportar rodar como não-root via PUID/PGID
        labels:
          traefik.enable: "true"
          traefik.http.routers.filebrowser.rule: "Host(`files.{{ base_domain }}`)"
          traefik.http.routers.filebrowser.entrypoints: "websecure"
          traefik.http.routers.filebrowser.tls.certresolver: "letsencrypt"
          traefik.http.routers.filebrowser.middlewares: "authelia@docker"
          traefik.http.services.filebrowser.loadbalancer.server.port: "80" # Porta interna padrão do FileBrowser
    ```

4.  **Deploy via Portainer:** Siga os passos, carregue `/opt/portainer_stack_envs/filebrowser.env`. Não há secrets adicionais para FileBrowser por padrão.

5.  **DNS:** Adicione CNAME `files` para o túnel (se não coberto por wildcard).

6.  **Teste:** Acesse `https://files.{{ base_domain }}`. O login padrão do FileBrowser é `admin`/`admin` (**MUDE IMEDIATAMENTE** após o primeiro login na UI do FileBrowser!).

Seguindo este processo, você pode expandir seu servidor doméstico com uma variedade de aplicações úteis!
