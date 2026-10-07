# Integrando Novos Serviços a Stacks Docker Existentes

Em muitos casos, ao adicionar uma nova funcionalidade ou um pequeno utilitário ao seu servidor doméstico, você pode não querer criar uma stack Docker completamente nova (ou seja, um novo arquivo `docker-compose.yml` e um novo "Stack" no Portainer) apenas para um único container. Em vez disso, pode ser mais lógico e organizado adicionar o novo serviço a uma **stack Docker já existente**, especialmente se o novo serviço estiver intimamente relacionado ou for um "companion" para os serviços já presentes naquela stack.

Este guia descreve o processo e as considerações para adicionar um novo serviço (container) a um arquivo `docker-compose.yml` de uma stack existente e, em seguida, atualizar essa stack via Portainer.

## Cenários Comuns para Adicionar a Stacks Existentes

*   **Serviços "Companion" ou Auxiliares:**
    *   Adicionar um container de tema ou plugin a uma aplicação principal (e.g., um tema customizado para o [Homer Dashboard](https://github.com/bastienwirtz/homer) se você o usa, ou um plugin que roda como um container separado para uma aplicação como [Paperless-ngx](https://github.com/paperless-ngx/paperless-ngx)).
    *   Adicionar um container de exportador de métricas Prometheus específico para uma aplicação já existente na stack.
*   **Pequenos Utilitários Relacionados:**
    *   Adicionar um container `cron` que executa tarefas agendadas relacionadas aos dados ou serviços de uma stack específica.
    *   Adicionar uma ferramenta de linha de comando ou uma pequena API que interage com os outros serviços da stack.
*   **Consolidação Lógica:**
    *   Se você inicialmente separou microserviços muito pequenos em stacks diferentes e percebe que eles estão tão interligados que gerenciá-los em um único `docker-compose.yml` seria mais simples.

## Passos para Adicionar um Novo Serviço a uma Stack Existente

O processo é bastante similar a [adicionar uma stack completamente nova](01-adicionando-novo-servico-docker.md), mas com o foco em modificar um `docker-compose.yml` já existente.

1.  **Planejamento do Novo Serviço (Mesmos Princípios):**
    *   **Imagem Docker:** Qual imagem e tag de versão específica?
    *   **Recursos:** O novo serviço é leve o suficiente para ser adicionado à VM onde a stack existente roda sem causar sobrecarga?
    *   **Persistência de Dados (Volumes):**
        *   O novo serviço precisa de volumes persistentes?
        *   Se sim, crie (ou planeje criar via Ansible) um subdiretório para ele **dentro da estrutura de volumes da stack existente**.
            *   Exemplo: Se a stack `media-services` usa `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/media_stack_configs/`, você poderia criar `.../media_stack_configs/novo_servico_midia/config` para o novo serviço.
        *   Adicione as variáveis de caminho para estes novos volumes ao arquivo `.env` da stack existente (e.g., `/opt/portainer_stack_envs/media.env`) se você usa variáveis para caminhos no seu compose.
    *   **Configuração de Rede:**
        *   A quais redes Docker (já definidas ou usadas pela stack existente) o novo serviço precisa se conectar? (e.g., `proxy`, `internal_services`, ou uma rede interna específica daquela stack).
        *   Precisa ser exposto via Traefik? Se sim, qual subdomínio? Será protegido por Authelia?
    *   **Variáveis de Ambiente:** Quais são necessárias para o novo serviço?
    *   **Dependências:** O novo serviço depende de outros serviços já existentes na stack para iniciar corretamente? (Use `depends_on`).

2.  **Preparação de Novos Volumes e Atualização do `.env` da Stack (Via Ansible - Se Aplicável):**
    *   Se o novo serviço requer novos diretórios de volume persistente ou novas variáveis de ambiente não sensíveis no arquivo `.env` da stack:
        1.  Edite o playbook Ansible correspondente à **stack existente** (e.g., `ansible/playbooks/setup-media-stack-volumes.yml`).
        2.  Adicione tasks `ansible.builtin.file` para criar os novos subdiretórios de volume.
        3.  Modifique a task `ansible.builtin.template` que gera o arquivo `.env` da stack para incluir as novas variáveis de caminho ou outras variáveis necessárias para o novo serviço.
        4.  Execute o playbook Ansible atualizado: `ansible-playbook ansible/playbooks/setup-media-stack-volumes.yml --ask-vault-pass`.
            Isso garante que os diretórios e o arquivo `.env` na VM estejam prontos antes de atualizar a stack no Portainer.

3.  **Modifique o Arquivo `docker-compose.yml` da Stack Existente:**
    *   Localize o arquivo `docker-compose.yml` da stack que você deseja modificar no seu projeto Git (e.g., `home-server/docker/stacks/apps/docker-compose.yml`).
    *   Abra-o em um editor de texto.
    *   **Adicione a Definição do Novo Serviço:**
        *   Na seção `services:` do `docker-compose.yml`, adicione uma nova entrada (um novo bloco de serviço) para o seu novo container. Siga a mesma estrutura e indentação dos serviços já existentes.
        ```yaml
        # Exemplo: Modificando docker/stacks/apps/docker-compose.yml
        version: '3.9'

        networks:
          proxy:
            external: true
          internal_services:
            external: true
          # media_internal_net: # Exemplo de rede interna da stack, se existir

        services:
          sonarr:
            # ... (configuração do Sonarr como já existe) ...

          radarr:
            # ... (configuração do Radarr como já existe) ...

          # --- NOVO SERVIÇO ADICIONADO À STACK 'media-services' ---
          meu_novo_utilitario_midia:
            image: alguma_imagem/utilitario_midia:tag_especifica
            container_name: utilitario_midia
            restart: unless-stopped
            networks: # Conecte às redes que fazem sentido para este utilitário
              # - proxy # Se precisar de UI exposta via Traefik
              - internal_services # Se precisar interagir com Sonarr/Radarr/qBit
              # - media_internal_net
            volumes:
              # Use variáveis do .env da stack de mídia existente
              - "${MEDIA_STACK_UTILITARIO_CONFIG_PATH}:/config"
            environment:
              - PUID=${DOCKER_PUID} # Herda PUID/PGID do .env da stack de mídia
              - PGID=${DOCKER_PGID}
              - TZ=${SYSTEM_TIMEZONE}
              # - VAR_ESPECIFICA_UTILITARIO=${VALOR_UTILITARIO} # Definir no .env ou Portainer
            # labels: # Se precisar de Traefik para uma UI deste utilitário
            #   traefik.enable: "true"
            #   traefik.http.routers.utilitariomidia.rule: "Host(`utilmidia.{{ base_domain }}`)"
            #   # ... (outras labels Traefik e middleware Authelia se necessário) ...
            depends_on: # Se este utilitário depende, por exemplo, do Sonarr estar rodando
              - sonarr
        ```
    *   **Verifique as Redes:** Se o novo serviço precisa se conectar a uma rede que já está definida na seção `networks:` de nível superior do compose (e marcada como `external: true` ou definida localmente para a stack), apenas adicione-a à seção `networks:` do novo serviço. Se for uma rede nova apenas para este serviço e outros dentro da stack, defina-a no nível superior.
    *   **Verifique as Variáveis de Ambiente:**
        *   O novo serviço pode reutilizar variáveis já presentes no `.env` da stack (como `DOCKER_PUID`, `DOCKER_PGID`, `SYSTEM_TIMEZONE`).
        *   Se ele precisar de novas variáveis não sensíveis, adicione-as ao arquivo `.env` da stack (e ao playbook Ansible que o gera).
        *   Se ele precisar de novos **secrets**, você os adicionará manualmente na UI do Portainer no próximo passo.

4.  **Atualize a Stack Existente via Portainer:**
    *   Acesse sua instância Portainer.
    *   Selecione o endpoint Docker correto.
    *   Vá para "**Stacks**".
    *   Localize e clique na stack existente que você modificou (e.g., `media-services`).
    *   Clique em "**Editor**".
    *   **Substitua o conteúdo do editor web** pelo conteúdo completo do seu arquivo `docker-compose.yml` atualizado (que agora inclui o novo serviço).
    *   **Variáveis de Ambiente:**
        *   Se você modificou o arquivo `.env` da stack na VM (via Ansible), o Portainer *deveria* recarregá-lo automaticamente se você usou a opção "Load variables from .env file" originalmente. Para ter certeza, você pode re-especificar o caminho para o arquivo `.env` da stack (e.g., `/opt/portainer_stack_envs/media.env`).
        *   Adicione manualmente quaisquer **novos secrets** (senhas, tokens de API) que o novo serviço possa requerer.
    *   Clique no botão "**Update the stack**".
        *   !!! important "Opções de Atualização"
            Ao atualizar, o Portainer geralmente oferece opções como:
            *   **"Pull latest image versions" / "Re-pull image and redeploy":** Marque esta opção se você quer que o Portainer puxe a imagem do novo serviço (e potencialmente atualize imagens de serviços existentes se as tags permitirem ou se você as alterou).
            *   Portainer irá comparar o novo `docker-compose.yml` com o estado atual da stack e aplicará apenas as diferenças: ele criará e iniciará o novo serviço, e poderá recriar outros serviços na stack se suas definições (volumes, redes, env vars) mudaram. Os serviços cujas definições não mudaram geralmente não são reiniciados, a menos que dependam de um serviço que foi recriado.

5.  **Configuração de DNS e Testes (se o novo serviço for exposto externamente):**
    *   Se o novo serviço foi configurado com labels Traefik para ser exposto externamente (e.g., `utilmidia.{{ base_domain }}`):
        *   Siga os passos de configuração de DNS na Cloudflare (CNAME ou verifique sua Ingress Rule wildcard) como faria para uma nova stack (ver [Seção 5.5 do Manual de Implementação](../01-manual-implementacao/05-rede-segura.md#55-configuração-de-dns-na-cloudflare)).
    *   Acesse o novo serviço pelo seu subdomínio (se aplicável) ou verifique sua funcionalidade de outra forma.
    *   Examine os logs do novo container no Portainer para quaisquer erros de inicialização ou operacionais.
    *   Verifique também os logs dos serviços existentes na stack para garantir que não foram impactados negativamente pela adição do novo serviço.

## Exemplo Prático: Adicionando `Bazarr` (Gerenciador de Legendas) à Stack de Mídia

Suponha que você já tem Sonarr, Radarr e qBittorrent rodando na sua stack `media-services` e agora quer adicionar o [Bazarr](https://www.bazarr.media/) para gerenciar e baixar legendas automaticamente.

1.  **Planejamento (Bazarr):**
    *   Imagem: `lscr.io/linuxserver/bazarr:latest` (ou uma tag de versão específica).
    *   Recursos: Relativamente leve.
    *   Persistência: Precisa de um volume para sua configuração (e.g., `/config`).
    *   Rede: Precisa se conectar à rede `proxy` (para sua UI via Traefik) e à rede `internal_services` (para se comunicar com Sonarr e Radarr para obter informações sobre a mídia). Subdomínio: `bazarr.{{ base_domain }}`, proteger com Authelia.
    *   Variáveis: PUID, PGID, TZ.

2.  **Preparação Ansible (Atualizar `setup-media-stack-volumes.yml`):**
    *   Adicione uma task `ansible.builtin.file` para criar o diretório `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/bazarr/config`.
    *   Atualize a task `ansible.builtin.template` que gera `/opt/portainer_stack_envs/media.env` para incluir:
        ```env
        # ... (variáveis existentes para Plex, Sonarr, etc.) ...
        MEDIA_STACK_BAZARR_CONFIG_PATH={{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/bazarr/config
        ```
    *   Execute o playbook `setup-media-stack-volumes.yml` atualizado.

3.  **Modificar `docker/stacks/apps/docker-compose.yml`:**
    Adicione o serviço `bazarr`:
    ```yaml
    # ... (serviços Plex, Jellyfin, Sonarr, Radarr, qBittorrent) ...

      bazarr:
        image: lscr.io/linuxserver/bazarr:latest # Considere uma tag de versão específica
        container_name: bazarr
        restart: unless-stopped
        networks:
          - proxy
          - internal_services
        volumes:
          - "${MEDIA_STACK_BAZARR_CONFIG_PATH}:/config"
          # Bazarr precisa de acesso de LEITURA às pastas de mídia para encontrar os arquivos de vídeo
          - "${MEDIA_STACK_MOVIES_PATH}:/movies:ro"
          - "${MEDIA_STACK_TVSHOWS_PATH}:/tv:ro"
        environment:
          - PUID=${DOCKER_PUID}
          - PGID=${DOCKER_PGID}
          - TZ=${SYSTEM_TIMEZONE}
        labels:
          traefik.enable: "true"
          traefik.http.routers.bazarr.rule: "Host(`bazarr.{{ base_domain }}`)"
          traefik.http.routers.bazarr.entrypoints: "websecure"
          traefik.http.routers.bazarr.tls.certresolver: "letsencrypt"
          traefik.http.routers.bazarr.middlewares: "authelia@docker"
          traefik.http.services.bazarr.loadbalancer.server.port: "6767" # Porta interna do Bazarr
        depends_on: # Bazarr geralmente precisa que Sonarr/Radarr estejam disponíveis
          - sonarr
          - radarr
    ```

4.  **Atualizar Stack `media-services` no Portainer:**
    *   Vá para a stack `media-services` -> Editor.
    *   Cole o `docker-compose.yml` completo e atualizado (com Bazarr incluído).
    *   Verifique se o "Path on disk" para o `/opt/portainer_stack_envs/media.env` está correto (ele deve ser recarregado ou as novas variáveis como `MEDIA_STACK_BAZARR_CONFIG_PATH` não serão reconhecidas, a menos que você as defina manualmente na UI do Portainer). Para garantir, você pode re-especificar o caminho.
    *   Clique em "Update the stack", marcando "Re-pull image and redeploy".

5.  **DNS e Testes:**
    *   Se o wildcard DNS está configurado, nenhuma mudança de DNS é necessária. Caso contrário, adicione CNAME `bazarr` para o túnel.
    *   Acesse `https://bazarr.{{ base_domain }}`. Autentique com Authelia.
    *   Na UI do Bazarr, vá para Settings -> Sonarr / Radarr e configure a conexão com seus servidores Sonarr e Radarr (usando os nomes dos serviços Docker, e.g., `http://sonarr:8989`, e as API keys deles).
    *   Configure seus provedores de legendas.

Adicionar serviços a stacks existentes é uma maneira eficiente de evoluir sua configuração Docker sem multiplicar o número de stacks a serem gerenciadas individualmente no Portainer, mantendo os serviços relacionados logicamente agrupados.