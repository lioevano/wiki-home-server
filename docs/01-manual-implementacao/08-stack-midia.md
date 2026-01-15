# Seção 8: Stack de Mídia (Plex/Jellyfin, \*arrs)

Esta seção detalha a implementação da sua suíte de entretenimento digital, comumente conhecida como "stack de mídia". Ela incluirá:

*   Um **servidor de mídia** para organizar, transmitir e permitir o acesso à sua coleção de filmes, séries de TV, músicas e fotos. As principais opções que abordaremos são **Plex** e **Jellyfin**.
*   O conjunto de aplicações **"\*arr"** (Sonarr, Radarr, Lidarr, Prowlarr, Bazarr) para gerenciamento automatizado e download de conteúdo de mídia.
*   Um **cliente de torrent** (qBittorrent) para lidar com os downloads.

Todos esses serviços rodarão como containers Docker na sua `core-services-vm`. Os dados de configuração de cada aplicação e, mais importante, seus arquivos de mídia, serão armazenados de forma persistente nos volumes NFS, que por sua vez residem no pool ZFS `/data` do seu host Proxmox (com aproximadamente 500GB de capacidade útil, lembre-se!).

!!! warning "Limitações de Armazenamento e Performance de Transcoding"
    *   **Armazenamento:** Com um pool de dados ZFS de ~500GB, o espaço para sua biblioteca de mídia será limitado. Gerencie este espaço com atenção e considere futuras expansões se sua coleção crescer.
    *   **Transcoding de Vídeo:** A transcodificação (converter vídeo de um formato/resolução para outro em tempo real para compatibilidade com o dispositivo cliente) é uma tarefa intensiva em CPU.
        *   **CPU (Ryzen 5 5600G):** É capaz de fazer transcoding de software para alguns streams 1080p, mas terá dificuldades com 4K ou múltiplos streams simultâneos.
        *   **Priorize Direct Play/Stream:** Configure seus clientes de mídia (Plex, Jellyfin apps) para "Direct Play" ou "Direct Stream" sempre que possível. Isso significa que o cliente reproduz o arquivo no formato original sem necessidade de transcodificação pelo servidor, economizando muitos recursos.
        *   **Hardware Transcoding (iGPU Vega do 5600G):**
            *   **Jellyfin:** Suporta bem hardware transcoding com a iGPU AMD Vega via VAAPI no Linux. O `docker-compose.yml` incluirá o mapeamento de `/dev/dri` para o container Jellyfin.
            *   **Plex:** O hardware transcoding com Plex Pass pode funcionar com iGPUs AMD no Linux, mas historicamente tem sido menos direto de configurar e com menos suporte oficial do que com GPUs Intel Quick Sync Video (QSV) ou NVIDIA NVENC.
        *   **GPU Dedicada (RX 5600XT):** Se não estiver sendo usada pela `ai-desktop-vm`, teoricamente poderia ser passada para a `core-services-vm` para transcoding. No entanto, isso adiciona complexidade significativa ao setup da VM e ao gerenciamento de drivers, e pode não ser o uso mais eficiente dos recursos se a IA for uma prioridade. Este guia foca na iGPU para Jellyfin.

## 8.1. Preparação com Ansible para a Stack de Mídia

Antes de implantar a stack de mídia no Portainer, o Ansible precisa preparar os diretórios nos volumes NFS onde as configurações das aplicações e os próprios arquivos de mídia serão armazenados. Ele também criará o arquivo `.env` específico para esta stack.

### Playbook `setup-media-stack-volumes.yml`

Este playbook, que será executado contra a `core-services-vm`, realizará as seguintes tarefas:

1.  **Criação de Diretórios de Configuração:**
    *   No dataset ZFS `docker-volumes` (montado em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/` na VM), criará subdiretórios para cada aplicação da stack de mídia. Exemplos:
        *   `.../plex/config`
        *   `.../jellyfin/config`
        *   `.../sonarr/config`
        *   `.../radarr/config`
        *   `.../qbittorrent/config`
        *   (E para Prowlarr, Bazarr, etc., se você os incluir)
    *   Esses diretórios terão permissões definidas para `owner: {{ docker_puid }}` e `group: {{ docker_pgid }}`.
2.  **Criação de Diretórios de Mídia:**
    *   No dataset ZFS `media` (montado em `{{ vm_nfs_mount_base_path }}/{{ zfs_media_dataset_name }}/` na VM), criará subdiretórios para organizar sua mídia. Exemplos:
        *   `.../movies`
        *   `.../tvshows` (ou `series`)
        *   `.../music`
        *   `.../photos` (opcional)
3.  **Criação do Diretório de Downloads:**
    *   Garantirá que o diretório no dataset ZFS `downloads` (montado em `{{ vm_nfs_mount_base_path }}/{{ zfs_downloads_dataset_name }}/` na VM) exista para o qBittorrent.
4.  **Preparação do Arquivo `.env`:**
    *   Gerará o arquivo `/opt/portainer_stack_envs/media.env` na `core-services-vm`. Este arquivo conterá os caminhos completos para todos os volumes mencionados acima, além de PUID/PGID, TZ, e outras variáveis comuns. O template `ansible/templates/portainer_stack_env.j2` será usado, com `stack_name: "media"`.

**Ação:** Execute o playbook a partir da sua máquina de controle Ansible:
```bash
ansible-playbook ansible/playbooks/setup-media-stack-volumes.yml --ask-vault-pass
```

## 8.2. Deploy da Stack de Mídia via Portainer (`docker/stacks/media/docker-compose.yml`)

Com os volumes e o arquivo `.env` preparados pelo Ansible, podemos agora implantar a stack de mídia usando o Portainer.

**Ação:**

1.  **Acesse o Portainer e Selecione o Endpoint Correto:**
    *   Navegue para `https://portainer.{{ base_domain }}`.
    *   Certifique-se de que está conectado ao endpoint `local` (que corresponde à `core-services-vm`).

2.  **Adicionar uma Nova Stack:**
    *   No menu lateral, clique em "**Stacks**".
    *   Clique no botão "**+ Add stack**".

3.  **Configurar a Stack:**
    *   **Name:** Dê um nome descritivo, e.g., `media-services`.
    *   **Build method:** Selecione "**Web editor**".
    *   **Web editor:** Cole o conteúdo completo do arquivo `home-server/docker/stacks/media/docker-compose.yml` (fornecido na Seção 8.2 do seu documento original).

    ```yaml
    # docker/stacks/media/docker-compose.yml
    version: '3.9'

    networks:
      proxy: # Para serviços expostos via Traefik (Jellyfin, *arrs, qBit WebUI)
        name: proxy
        external: true
      internal_services: # Para comunicação interna entre *arrs e qBittorrent
        name: internal_services
        external: true

    services:
      # --- Servidor de Mídia: Plex OU Jellyfin (escolha um ou rode ambos com cuidado com os recursos) ---

      plex:
        image: plexinc/pms-docker:1.40.2.8395-c67dce28e # Verifique a tag mais recente/estável
        container_name: plex
        restart: unless-stopped
        # network_mode: host # Plex geralmente funciona melhor com network_mode: host para descoberta e relay.
                              # No entanto, para integração com Cloudflare Tunnel (sem expor IP) e Traefik,
                              # é preferível NÃO usar host mode e expor as portas necessárias.
                              # Se você ABSOLUTAMENTE precisa de host mode, o acesso externo terá que ser
                              # configurado no Cloudflare Tunnel apontando diretamente para IP_VM:32400,
                              # e Traefik não seria usado para Plex.
        ports: # Apenas necessário se NÃO usar network_mode: host.
               # As variáveis (e.g., CORE_SERVICES_VM_IP_VAR) virão do .env.
          - "${CORE_SERVICES_VM_IP_VAR}:32400:32400/tcp" # UI Web e API principal
          - "${CORE_SERVICES_VM_IP_VAR}:3005:3005/tcp"   # Plex Home Theater via Plex Companion
          - "${CORE_SERVICES_VM_IP_VAR}:8324:8324/tcp"   # Plex Companion player control
          - "${CORE_SERVICES_VM_IP_VAR}:32469:32469/tcp" # Plex DLNA Server
          - "${CORE_SERVICES_VM_IP_VAR}:1900:1900/udp"   # Plex DLNA Server (discovery)
          - "${CORE_SERVICES_VM_IP_VAR}:32410:32410/udp" # GDM network discovery
          - "${CORE_SERVICES_VM_IP_VAR}:32412:32412/udp" # GDM network discovery
          - "${CORE_SERVICES_VM_IP_VAR}:32413:32413/udp" # GDM network discovery
          - "${CORE_SERVICES_VM_IP_VAR}:32414:32414/udp" # GDM network discovery
        # Se não usar network_mode: host, conecte à rede proxy para Traefik (opcional para Plex)
        # networks:
        #   - proxy
        volumes: # Caminhos NFS definidos no .env carregado no Portainer
          - "${MEDIA_STACK_PLEX_CONFIG_PATH}:/config" # Configuração do Plex
          # Para transcoding, um SSD local na VM seria ideal. Se usar NFS, pode ser lento.
          # /tmp do container (RAM da VM) é uma opção para transcode se houver MUITA RAM livre.
          - "${MEDIA_STACK_PLEX_TRANSCODE_PATH}:/transcode" # Diretório para arquivos de transcodificação temporários
          # Mapeia as bibliotecas de mídia (somente leitura para segurança, Plex só precisa ler)
          - "${MEDIA_STACK_MOVIES_PATH}:/data/movies:ro"
          - "${MEDIA_STACK_TVSHOWS_PATH}:/data/tvshows:ro"
          - "${MEDIA_STACK_MUSIC_PATH}:/data/music:ro"
          # Adicione outros mapeamentos de mídia conforme necessário (e.g., /data/photos)
        environment:
          - PLEX_UID=${DOCKER_PUID} # Do .env
          - PLEX_GID=${DOCKER_PGID} # Do .env
          - TZ=${SYSTEM_TIMEZONE}   # Do .env
          # PLEX_CLAIM_TOKEN: Obtenha um token de plex.tv/claim e defina esta variável no Portainer.
          # É usado para vincular o servidor à sua conta Plex na primeira execução.
          - PLEX_CLAIM=${PLEX_CLAIM_TOKEN_FROM_PORTAINER_ENV}
          # - PLEX_ADVERTISE_IP=https://plex.{{ base_domain }}:443 # Se exposto via Traefik/Tunnel
        # Labels Traefik se for expor via Traefik (NÃO recomendado para a UI principal do Plex devido a possíveis problemas com clientes)
        # Acesso externo ao Plex é geralmente melhor via Plex Relay ou configurando Cloudflare Tunnel
        # para apontar diretamente para IP_DA_VM_CORE_SERVICES:32400/tcp.
        # Se ainda quiser tentar com Traefik:
        # labels:
        #   traefik.enable: "true"
        #   traefik.http.routers.plex.rule: "Host(`plex.${BASE_DOMAIN_FROM_VAULT}`)"
        #   traefik.http.routers.plex.entrypoints: "websecure"
        #   traefik.http.routers.plex.tls.certresolver: "letsencrypt"
        #   traefik.http.routers.plex.service: "plex-svc"
        #   traefik.http.services.plex-svc.loadbalancer.server.port: "32400"
        #   # Plex com Authelia é complicado e geralmente não é feito.

      jellyfin:
        image: jellyfin/jellyfin:10.8.13 # Verifique a tag mais recente/estável
        container_name: jellyfin
        restart: unless-stopped
        networks:
          - proxy # Para ser exposto via Traefik
        # user: "${DOCKER_PUID}:${DOCKER_PGID}" # Jellyfin pode rodar como não-root. Garanta permissões nos volumes.
        volumes: # Caminhos NFS do .env
          - "${MEDIA_STACK_JELLYFIN_CONFIG_PATH}:/config" # Configuração do Jellyfin
          - "${MEDIA_STACK_MOVIES_PATH}:/data/movies:ro"
          - "${MEDIA_STACK_TVSHOWS_PATH}:/data/tvshows:ro"
          - "${MEDIA_STACK_MUSIC_PATH}:/data/music:ro"
          # Para Hardware Transcoding com iGPU Intel/AMD no Linux (se Proxmox host permitir acesso da VM ao /dev/dri)
          # 1. Proxmox host: `chmod o+rw /dev/dri/*` (menos seguro) ou adicione usuário da VM ao grupo 'render'/'video'.
          # 2. VM config: Passe o dispositivo /dev/dri para a VM (e.g., cgroup permissions ou lxc.cgroup2.devices.allow).
          # 3. Docker compose: Mapeie /dev/dri.
          - "/dev/dri:/dev/dri"
        environment:
          - PUID=${DOCKER_PUID} # Do .env
          - PGID=${DOCKER_PGID} # Do .env
          - TZ=${SYSTEM_TIMEZONE} # Do .env
          # JELLYFIN_PublishedServerUrl é importante se Jellyfin estiver atrás de um proxy reverso.
          - JELLYFIN_PublishedServerUrl=https://jellyfin.${BASE_DOMAIN_FROM_VAULT} # BASE_DOMAIN_FROM_VAULT do .env
        labels: # Labels para Traefik
          traefik.enable: "true"
          traefik.http.routers.jellyfin.rule: "Host(`jellyfin.${BASE_DOMAIN_FROM_VAULT}`)"
          traefik.http.routers.jellyfin.entrypoints: "websecure"
          traefik.http.routers.jellyfin.tls.certresolver: "letsencrypt"
          traefik.http.routers.jellyfin.service: "jellyfin-svc"
          traefik.http.services.jellyfin-svc.loadbalancer.server.port: "8096" # Porta HTTP interna padrão do Jellyfin
          traefik.http.routers.jellyfin.middlewares: "authelia@docker" # Protegido por Authelia

      # --- *arr Suite (Sonarr, Radarr, etc.) ---
      # Usam imagens da linuxserver.io que são populares e bem mantidas.

      sonarr: # Gerenciador de séries de TV
        image: lscr.io/linuxserver/sonarr:v3.0.10 # Ou :latest para v4 se estável. Verifique a versão.
        container_name: sonarr
        restart: unless-stopped
        networks:
          - proxy # Para acesso à UI via Traefik
          - internal_services # Para comunicação com qBittorrent
        volumes: # Caminhos NFS do .env
          - "${MEDIA_STACK_SONARR_CONFIG_PATH}:/config" # Configuração do Sonarr
          - "${MEDIA_STACK_TVSHOWS_PATH}:/tv" # Onde Sonarr gerencia os arquivos finais de séries
          # Diretório de downloads (onde qBittorrent baixa os arquivos).
          # Sonarr precisa de acesso para importar após o download.
          # A variável ZFS_DOWNLOADS_DATASET_NAME_NFS_PATH é construída no .env:
          # {{ vm_nfs_mount_base_path }}/{{ zfs_downloads_dataset_name }}
          - "${ZFS_DOWNLOADS_DATASET_NAME_NFS_PATH}:/downloads"
        environment:
          - PUID=${DOCKER_PUID}
          - PGID=${DOCKER_PGID}
          - TZ=${SYSTEM_TIMEZONE}
        labels: # Labels para Traefik
          traefik.enable: "true"
          traefik.http.routers.sonarr.rule: "Host(`sonarr.${BASE_DOMAIN_FROM_VAULT}`)"
          traefik.http.routers.sonarr.entrypoints: "websecure"
          traefik.http.routers.sonarr.tls.certresolver: "letsencrypt"
          traefik.http.routers.sonarr.service: "sonarr-svc"
          traefik.http.services.sonarr-svc.loadbalancer.server.port: "8989" # Porta interna do Sonarr
          traefik.http.routers.sonarr.middlewares: "authelia@docker"
        depends_on: # Opcional, para influenciar a ordem de inicialização
          - qbittorrent

      radarr: # Gerenciador de filmes (similar ao Sonarr)
        image: lscr.io/linuxserver/radarr:v5.2.6 # Verifique a versão mais recente/estável.
        container_name: radarr
        restart: unless-stopped
        networks:
          - proxy
          - internal_services
        volumes:
          - "${MEDIA_STACK_RADARR_CONFIG_PATH}:/config"
          - "${MEDIA_STACK_MOVIES_PATH}:/movies" # Onde Radarr gerencia os arquivos finais de filmes
          - "${ZFS_DOWNLOADS_DATASET_NAME_NFS_PATH}:/downloads"
        environment:
          - PUID=${DOCKER_PUID}
          - PGID=${DOCKER_PGID}
          - TZ=${SYSTEM_TIMEZONE}
        labels:
          traefik.enable: "true"
          traefik.http.routers.radarr.rule: "Host(`radarr.${BASE_DOMAIN_FROM_VAULT}`)"
          traefik.http.routers.radarr.entrypoints: "websecure"
          traefik.http.routers.radarr.tls.certresolver: "letsencrypt"
          traefik.http.routers.radarr.service: "radarr-svc"
          traefik.http.services.radarr-svc.loadbalancer.server.port: "7878" # Porta interna do Radarr
          traefik.http.routers.radarr.middlewares: "authelia@docker"
        depends_on:
          - qbittorrent

      # --- Cliente de Torrent ---
      qbittorrent:
        image: lscr.io/linuxserver/qbittorrent:4.6.5 # Verifique a versão mais recente/estável.
        container_name: qbittorrent
        restart: unless-stopped
        networks:
          - proxy # Para acesso à WebUI via Traefik
          - internal_services # Para ser alcançado pelos *arrs
        ports: # Portas para conexões P2P.
               # Mapear no IP da VM se não usar VPN dentro do container.
               # Se usar VPN no container, estas portas podem não precisar ser expostas no host.
          - "${CORE_SERVICES_VM_IP_VAR}:6881:6881/tcp"
          - "${CORE_SERVICES_VM_IP_VAR}:6881:6881/udp"
        volumes: # Caminhos NFS do .env
          - "${MEDIA_STACK_QBITTORRENT_CONFIG_PATH}:/config" # Configuração do qBittorrent
          - "${ZFS_DOWNLOADS_DATASET_NAME_NFS_PATH}:/downloads" # Diretório padrão de downloads
        environment:
          - PUID=${DOCKER_PUID}
          - PGID=${DOCKER_PGID}
          - TZ=${SYSTEM_TIMEZONE}
          - WEBUI_PORT=8088 # Porta interna para a WebUI do qBittorrent (Traefik apontará para esta)
          # - VPN_ENABLED=false # Se usar um container VPN separado ou VPN no host
          # - LAN_NETWORK=192.168.1.0/24 # Se precisar especificar sua LAN
        labels:
          traefik.enable: "true"
          traefik.http.routers.qbittorrent.rule: "Host(`qbittorrent.${BASE_DOMAIN_FROM_VAULT}`)"
          traefik.http.routers.qbittorrent.entrypoints: "websecure"
          traefik.http.routers.qbittorrent.tls.certresolver: "letsencrypt"
          traefik.http.routers.qbittorrent.service: "qbittorrent-svc"
          traefik.http.services.qbittorrent-svc.loadbalancer.server.port: "8088" # Porta WEBUI_PORT definida acima
          traefik.http.routers.qbittorrent.middlewares: "authelia@docker"

      # --- Opcionais Adicionais (Prowlarr, Bazarr, Lidarr) ---
      # Prowlarr: Gerenciador de indexadores para os *arrs
      # prowlarr:
      #   image: lscr.io/linuxserver/prowlarr:develop # Ou :latest
      #   container_name: prowlarr
      #   (...) # Configs similares a Sonarr/Radarr

      # Bazarr: Gerenciador de legendas
      # bazarr:
      #   image: lscr.io/linuxserver/bazarr:latest
      #   container_name: bazarr
      #   (...)

      # Lidarr: Gerenciador de músicas (se você tem uma grande coleção e quer automação)
      # lidarr:
      #   image: lscr.io/linuxserver/lidarr:latest
      #   container_name: lidarr
      #   (...)
    ```

        **Pontos Chave do Compose:**
        *   **Escolha Plex ou Jellyfin:** O compose de exemplo inclui ambos. Você pode comentar ou remover um deles se quiser rodar apenas um, para economizar recursos. Rodar ambos é possível com 48GB de RAM, mas monitore o uso.
        *   **Network Mode para Plex:** O exemplo não usa `network_mode: host` para Plex, optando por mapear portas individuais. Isso é geralmente melhor para integração com Traefik/Cloudflare Tunnel. Se você optar por `network_mode: host` para Plex, o acesso externo precisará ser configurado no Cloudflare Tunnel apontando diretamente para `IP_DA_CORE_SERVICES_VM:32400`, e Traefik não será usado para Plex.
        *   **Hardware Transcoding para Jellyfin:** O mapeamento `- "/dev/dri:/dev/dri"` está incluído para permitir que Jellyfin tente usar a iGPU para transcoding.
        *   **Redes `proxy` e `internal_services`:** Usadas para expor UIs e permitir comunicação interna.
        *   **Volumes:** Todos os volumes usam as variáveis de caminho (e.g., `${MEDIA_STACK_PLEX_CONFIG_PATH}`, `${ZFS_DOWNLOADS_DATASET_NAME_NFS_PATH}`) que virão do arquivo `.env`.
        *   **Labels Traefik:** Definidas para Jellyfin, Sonarr, Radarr e qBittorrent para exposição via `https.SUBDOMINIO.{{ base_domain }}` e proteção com Authelia. Plex é deixado sem labels Traefik no exemplo, assumindo acesso direto ou Plex Relay.
        *   **Variáveis de Ambiente:** PUID, PGID, TZ são definidos usando variáveis do `.env`.

4.  **Variáveis de Ambiente e Secrets no Portainer:**
    *   **Carregue o Arquivo `.env`:**
        *   Na seção "Environment variables" (modo avançado), clique em "Load variables from .env file".
        *   **Path on disk:** `/opt/portainer_stack_envs/media.env` (este arquivo foi criado pelo Ansible na `core-services-vm`).
        *   Isso preencherá automaticamente: `CORE_SERVICES_VM_IP_VAR`, `DOCKER_PUID`, `DOCKER_PGID`, `SYSTEM_TIMEZONE`, `BASE_DOMAIN_FROM_VAULT` (usada indiretamente pelos placeholders `{{ base_domain }}` nas labels Traefik, que o Portainer não resolve, mas o Traefik sim se `BASE_DOMAIN_FROM_VAULT` for passado para o container Traefik), e todos os caminhos de volume (`MEDIA_STACK_*_PATH`, `ZFS_DOWNLOADS_DATASET_NAME_NFS_PATH`).
            !!! note "Resolução de `{{ base_domain }}` nas Labels Traefik"
                As labels Traefik no `docker-compose.yml` usam `Host(\`sonarr.{{ base_domain }}\`)`. Este `{{ base_domain }}` **não** é resolvido pelo Portainer a partir do `.env`. Ele deve ser resolvido pelo Traefik se o próprio container Traefik tiver acesso a uma variável de ambiente `BASE_DOMAIN`. No nosso setup do Traefik (Seção 5.2), passamos `BASE_DOMAIN_FROM_VAULT` para o container Traefik, que ele pode usar. Alternativamente, você pode hardcodar seu domínio nas labels ou usar `${BASE_DOMAIN_FROM_VAULT}` se essa variável estiver no `.env` carregado para esta stack de mídia também. Para manter o exemplo do documento original, assumimos que `{{ base_domain }}` será interpretado corretamente pelo Traefik com base na sua própria configuração.
    *   **Adicione Secrets Manualmente:**
        *   `PLEX_CLAIM_TOKEN_FROM_PORTAINER_ENV`: Vá para [plex.tv/claim](https://www.plex.tv/claim) para obter um novo token de claim. Copie este token e cole-o como o valor para esta variável de ambiente no Portainer.
            !!! important "Token de Claim do Plex"
                O token de claim do Plex é de uso único e expira rapidamente (geralmente em poucos minutos). Obtenha-o **imediatamente antes** de clicar em "Deploy the stack" para o Plex. Se o Plex não conseguir se vincular à sua conta, você pode precisar parar o container Plex, remover seu volume de configuração (ou o arquivo `Preferences.xml` dentro dele), obter um novo token de claim, e redeployar a stack.

5.  **Deploy da Stack de Mídia:**
    *   Clique em "**Deploy the stack**".
    *   Monitore os logs de cada container no Portainer para verificar se há erros durante a inicialização.

6.  **Configuração Pós-Deploy (Dentro de Cada Aplicação):**

    Após os containers estarem rodando, você precisará configurar cada aplicação individualmente acessando suas interfaces web:

    *   **Plex (`http://{{ core_services_vm_ip_var }}:32400` para setup inicial local, ou via app.plex.tv):**
        *   Siga o assistente de configuração inicial do Plex. Ele deve detectar o servidor vinculado pelo token de claim.
        *   Dê um nome ao seu servidor Plex.
        *   **Adicionar Bibliotecas:** Crie bibliotecas para Filmes, Séries de TV, Música, etc. Ao adicionar uma biblioteca, aponte para os caminhos *dentro do container Plex* que você mapeou nos volumes:
            *   Filmes: `/data/movies`
            *   Séries: `/data/tvshows`
            *   Música: `/data/music`
        *   Configure o acesso remoto nas configurações do Plex se não estiver usando um túnel direto ou Traefik.
    *   **Jellyfin (`https://jellyfin.{{ base_domain }}` via Traefik/Authelia):**
        *   Siga o assistente de configuração inicial. Crie um usuário administrador.
        *   **Adicionar Bibliotecas:** Similar ao Plex, aponte para os caminhos dentro do container: `/data/movies`, `/data/tvshows`, `/data/music`.
        *   **Configurar Hardware Transcoding (se desejado):** Vá para Dashboard -> Playback. Selecione "AMD AMF" ou "VAAPI" como acelerador de hardware e escolha o dispositivo correto (e.g., `/dev/dri/renderD128`). Teste para garantir que funciona.
    *   **Sonarr (`https://sonarr.{{ base_domain }}`):**
        *   **Configurações -> Media Management:**
            *   Verifique "Advanced Settings".
            *   Configure Root Folders: Adicione `/tv` (este é o caminho *dentro do container Sonarr* para sua biblioteca de séries).
        *   **Configurações -> Download Clients:**
            *   Adicione qBittorrent:
                *   Nome: `qbittorrent`
                *   Host: `qbittorrent` (nome do serviço Docker na rede `internal_services`)
                *   Port: `8088` (a `WEBUI_PORT` do qBittorrent)
                *   Usuário/Senha: As credenciais da WebUI do qBittorrent (lembre-se de mudar o padrão `admin/adminadmin`!).
                *   Directory: `/downloads` (o caminho que qBittorrent usa para downloads *dentro do seu próprio container*).
        *   **Configurações -> Indexers:** Adicione seus indexadores de torrent/usenet (Prowlarr pode ajudar a gerenciar isso centralmente).
    *   **Radarr (`https://radarr.{{ base_domain }}`):**
        *   Configuração muito similar ao Sonarr, mas para filmes.
        *   Root Folder: `/movies`.
        *   Download Client: qBittorrent (host `qbittorrent`, port `8088`, directory `/downloads`).
    *   **qBittorrent (`https://qbittorrent.{{ base_domain }}`):**
        *   **MUDE A SENHA PADRÃO!** Login inicial: `admin` / `adminadmin`. Vá para Tools -> Options -> Web UI e mude a senha.
        *   **Configurar Diretórios de Download:** Em Options -> Downloads, certifique-se de que o "Default Save Path" está configurado para `/downloads` (o caminho dentro do container qBittorrent).
        *   Configure outras preferências (limites de velocidade, portas de escuta se não usar VPN no container).

Com esta stack configurada, você terá um sistema de gerenciamento e streaming de mídia poderoso e automatizado!

Próximo passo: [Stack de Produtividade e Automação (Nextcloud, Home Assistant)](09-stack-produtividade-automacao.md).