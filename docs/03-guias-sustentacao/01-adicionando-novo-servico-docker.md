# Adicionando um Novo Serviço Docker à Infraestrutura

Adicionar novos serviços é uma das partes mais recompensadoras de ter um servidor doméstico. Este guia fornece um checklist e um exemplo para integrar um novo serviço Docker à sua infraestrutura existente.

## Checklist de Passos

Siga estes passos para garantir uma integração suave:

1.  **Planejamento e Pesquisa:**
    *   **Recursos:** O serviço precisa de muitos recursos (CPU, RAM, disco)? Ele se encaixa nas capacidades da sua `core-services-vm` (ou `ai-desktop-vm` se for relacionado a IA)?
    *   **Persistência:** Onde os dados do serviço devem ser armazenados?
        *   Crie um novo subdiretório em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/<nome_do_servico>` na `core-services-vm` (ou `ai-desktop-vm`).
        *   Lembre-se que este caminho é um montado NFS do dataset ZFS no host Proxmox.
    *   **Rede:**
        *   O serviço precisa de acesso externo? Qual subdomínio será usado (e.g., `novoservico.{{ base_domain }}`)?
        *   Será protegido pelo Authelia?
        *   Precisa se comunicar com outros serviços internos (e.g., um banco de dados)?
    *   **Imagem Docker:** Qual imagem usar (oficial, linuxserver.io)? Verifique tags de versão estáveis.
    *   **Variáveis de Ambiente:** Quais são necessárias (PUID, PGID, TZ, senhas, configurações específicas)?

2.  **Preparação de Volumes e `.env` (Ansible - Opcional, mas Recomendado)**
    *   No seu projeto `infra-servidor-domestico/ansible/`:
        *   Crie ou adapte um playbook (e.g., `ansible/playbooks/setup-novoservico-volumes.yml`).
        *   Este playbook deve:
            *   Rodar contra a VM de destino (`core-services-vm` ou `ai-desktop-vm`).
            *   Usar o módulo `ansible.builtin.file` para criar os diretórios necessários no caminho NFS (e.g., `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/novoservico/config`) com `owner: {{ docker_puid }}`, `group: {{ docker_pgid }}`.
            *   Usar o módulo `ansible.builtin.template` para gerar um arquivo `.env` específico para o novo serviço em `{{ portainer_env_files_dest_path_on_vm }}/novoservico.env` na VM. Este `.env` deve conter PUID, PGID, TZ, caminhos de volume, etc., usando o template `portainer_stack_env.j2` como base.
    *   Execute este playbook Ansible: `ansible-playbook ansible/playbooks/setup-novoservico-volumes.yml --ask-vault-pass`.

3.  **Escrever o `docker-compose.yml`**
    *   Crie um novo arquivo, por exemplo, `docker/stacks/novoservico/docker-compose.yml`.
    *   Defina os serviços, imagem, volumes, redes, variáveis de ambiente e labels Traefik.

    ```yaml
    # Exemplo: docker/stacks/novoservico/docker-compose.yml
    version: '3.9'

    networks:
      proxy:
        external: true # Para Traefik
      # internal_services: # Se precisar se comunicar com outros backends
      #   external: true

    services:
      novoservico:
        image: alguma/imagem:tag-estavel
        container_name: novoservico
        restart: unless-stopped
        networks:
          - proxy
          # - internal_services
        volumes:
          # Use variáveis do .env que serão carregadas no Portainer
          - "${NOVOSERVICO_CONFIG_PATH}:/config"
          - "${NOVOSERVICO_DATA_PATH}:/data" # Exemplo
        environment:
          - PUID=${DOCKER_PUID} # Do .env
          - PGID=${DOCKER_PGID} # Do .env
          - TZ=${SYSTEM_TIMEZONE} # Do .env
          # - ALGUMA_SENHA_APP=${SENHA_DO_NOVOSERVICO_APP} # Definir no Portainer
        labels:
          # --- Labels Traefik ---
          traefik.enable: "true"
          # Roteador HTTP
          traefik.http.routers.novoservico.rule: "Host(`novoservico.{{ base_domain }}`)" # Substitua {{ base_domain }} pelo seu
          traefik.http.routers.novoservico.entrypoints: "websecure"
          traefik.http.routers.novoservico.tls.certresolver: "letsencrypt"
          # Middleware (Authelia)
          traefik.http.routers.novoservico.middlewares: "authelia@docker" # Ou um chain se precisar de outros
          # Serviço
          traefik.http.services.novoservico.loadbalancer.server.port: "8000" # Porta INTERNA do container
    ```
    !!! tip "Variáveis de Caminho no Compose"
        Use variáveis como `${NOVOSERVICO_CONFIG_PATH}` no seu `docker-compose.yml`. Essas variáveis serão preenchidas pelo arquivo `.env` que você carrega no Portainer. O arquivo `.env` é gerado pelo Ansible e contém os caminhos NFS corretos.

4.  **Deploy via Portainer**
    *   Acesse sua instância Portainer (`https://portainer.{{ base_domain }}`).
    *   Vá para "Stacks" -> "+ Add stack".
    *   **Nome:** `novoservico-stack` (ou similar).
    *   **Build method:** "Web editor". Cole o conteúdo do seu `docker/stacks/novoservico/docker-compose.yml`.
    *   **Variáveis de Ambiente:**
        *   Clique em "Load variables from .env file".
        *   Forneça o caminho para o arquivo `.env` na VM (e.g., `/opt/portainer_stack_envs/novoservico.env` se preparado por Ansible).
        *   Adicione manualmente quaisquer **secrets** (senhas, API keys) que não devem estar no arquivo `.env` versionado (e.g., `SENHA_DO_NOVOSERVICO_APP`).
    *   Clique em "Deploy the stack".
    *   Monitore os logs do novo container no Portainer para verificar se há erros.

5.  **Configuração de DNS (Cloudflare)**
    *   Vá ao seu painel Cloudflare -> DNS.
    *   Se você usa Ingress Rules abrangentes para seu túnel (e.g., `*.seudominio.com -> http://traefik:80`), este passo pode não ser necessário, pois o subdomínio já será coberto.
    *   Caso contrário, adicione um registro **CNAME**:
        *   **Type:** `CNAME`
        *   **Name:** `novoservico` (ou o subdomínio que você definiu na label Traefik).
        *   **Target:** O hostname do seu Cloudflare Tunnel (e.g., `UUID_DO_SEU_TUNEL.cfargotunnel.com`).
        *   **Proxy Status:** Laranja (Proxied).
    *   Aguarde alguns minutos para a propagação do DNS.

6.  **Teste e Pós-Configuração**
    *   Acesse `https://novoservico.{{ base_domain }}`.
    *   Você deve ser redirecionado para Authelia para login (se o middleware foi aplicado).
    *   Após o login, você deve ver seu novo serviço.
    *   Realize qualquer configuração inicial necessária dentro da UI do próprio serviço.

## Exemplo Prático: Adicionando `Whoogle Search`

Whoogle é um motor de busca auto-hospedado que respeita a privacidade.

1.  **Planejamento:**
    *   Leve, pode rodar na `core-services-vm`.
    *   Não precisa de persistência de dados complexa (configurações são gerenciadas por variáveis de ambiente ou um pequeno volume).
    *   Subdomínio: `search.{{ base_domain }}`.
    *   Proteger com Authelia.

2.  **Preparação Ansible (Opcional para Whoogle, pois não tem dados críticos):**
    *   Poderíamos criar um `setup-whoogle-volumes.yml` para gerar um `/opt/portainer_stack_envs/whoogle.env` apenas com PUID/PGID/TZ.

3.  **`docker-compose.yml` para Whoogle:**
    ```yaml
    # docker/stacks/whoogle/docker-compose.yml
    version: '3.9'
    networks: { proxy: { external: true } }
    services:
      whoogle:
        image: benbusby/whoogle-search:latest # Ou uma tag de versão específica
        container_name: whoogle_search
        restart: unless-stopped
        networks: [proxy]
        environment:
          - PUID=${DOCKER_PUID} # Do .env
          - PGID=${DOCKER_PGID} # Do .env
          - TZ=${SYSTEM_TIMEZONE} # Do .env
          - WHOOGLE_CONFIG_COUNTRY=BR # Exemplo de config Whoogle
          - WHOOGLE_CONFIG_LANGUAGE=pt-BR
          # - HTTPS_ONLY=true # Traefik já cuida do HTTPS
        labels:
          traefik.enable: "true"
          traefik.http.routers.whoogle.rule: "Host(`search.{{ base_domain }}`)"
          traefik.http.routers.whoogle.entrypoints: "websecure"
          traefik.http.routers.whoogle.tls.certresolver: "letsencrypt"
          traefik.http.routers.whoogle.middlewares: "authelia@docker"
          traefik.http.services.whoogle.loadbalancer.server.port: "5000" # Porta interna do Whoogle
    ```

4.  **Deploy via Portainer:**
    *   Siga os passos acima, nome da stack `whoogle-stack`.
    *   Carregue o `/opt/portainer_stack_envs/whoogle.env` (ou defina PUID/PGID/TZ manualmente).

5.  **DNS:** Adicione CNAME `search` para o túnel (se não coberto por wildcard).

6.  **Teste:** Acesse `https://search.{{ base_domain }}`.