# Seção 8: Stack de Mídia (Plex/Jellyfin, \*arrs)

Esta seção aborda a implementação da sua stack de mídia, que incluirá um servidor de mídia como Plex ou Jellyfin, e o conjunto de aplicações "\*arr" (Sonarr, Radarr, etc.) para gerenciamento e automação de downloads de mídia. Todos esses serviços rodarão como containers Docker na `core-services-vm`, com seus dados e configurações persistidos nos volumes NFS (pool de ~500GB).

!!! warning "Limitação de Armazenamento e Transcoding"
    *   **Armazenamento:** O pool ZFS `/data` de aproximadamente 500GB será o principal limitador para a quantidade de mídia que você pode armazenar. Gerencie este espaço com cuidado.
    *   **Transcoding:** Com 16GB de RAM total no host e o CPU Ryzen 5 5600G, o transcoding de vídeo pesado (especialmente 4K para múltiplos streams) será um desafio.
        *   **Plex/Jellyfin:** Priorize o "Direct Play" ou "Direct Stream" sempre que possível, configurando seus clientes para suportar os formatos de mídia originais.
        *   **Hardware Transcoding (iGPU):** A iGPU Vega do Ryzen 5 5600G pode ser usada para hardware transcoding no Jellyfin se configurada corretamente (passando `/dev/dri` para o container). Para Plex, o hardware transcoding com iGPUs AMD no Linux pode ser mais complexo de configurar e pode exigir Plex Pass.
        *   **GPU Dedicada (RX 5600XT):** Se a RX 5600XT não estiver sendo usada pela `ai-desktop-vm`, ela *poderia* ser passada para a `core-services-vm` para transcoding, mas isso aumenta a complexidade do setup e pode não ser o melhor uso dado o foco na IA.

## 8.1. Preparação com Ansible

Antes de implantar a stack de mídia no Portainer, o Ansible preparará os diretórios NFS e o arquivo `.env` necessário.

### Playbook `setup-media-stack-volumes.yml`

Este playbook, executado contra a `core-services-vm`, irá:
*   Criar os subdiretórios necessários no dataset ZFS `docker-volumes` (montado em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/`) para as configurações de cada aplicação da stack de mídia (Plex, Jellyfin, Sonarr, Radarr, qBittorrent, etc.).
*   Criar os subdiretórios para a mídia em si no dataset ZFS `media` (montado em `{{ vm_nfs_mount_base_path }}/{{ zfs_media_dataset_name }}/`), como `movies`, `tvshows`, `music`.
*   Garantir que o diretório de downloads exista no dataset ZFS `downloads`.
*   Preparar o arquivo `/opt/portainer_stack_envs/media.env` na `core-services-vm` com os caminhos e variáveis PUID/PGID, TZ, etc.

**Ação:** Execute o playbook a partir da sua máquina de controle Ansible:
```bash
ansible-playbook ansible/playbooks/setup-media-stack-volumes.yml --ask-vault-pass
```
Este playbook utilizará o template `ansible/templates/portainer_stack_env.j2` (detalhado na Seção 6.2), passando `stack_name: "media"` para gerar os caminhos corretos no arquivo `.env`.

## 8.2. Deploy da Stack de Mídia via Portainer (`docker/stacks/media/docker-compose.yml`)

Com os volumes preparados, vamos implantar a stack de mídia.

**Ação:**
1.  No Portainer, certifique-se de que está conectado ao endpoint `local` (correspondente à `core-services-vm`).
2.  Vá para "Stacks" -> "+ Add stack".
3.  **Nome:** `media-services`.
4.  **Web editor:** Cole o conteúdo do arquivo `infra-servidor-domestico/docker/stacks/media/docker-compose.yml`:

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

    !!! tip "Escolha Plex ou Jellyfin (ou ambos com cautela)"
        Se você tem recursos limitados, pode ser melhor escolher um servidor de mídia principal (Plex ou Jellyfin) em vez de rodar ambos. Plex é conhecido por sua facilidade de uso e compatibilidade de clientes, enquanto Jellyfin é totalmente open-source e oferece mais opções de personalização.

    !!! note "Hardware Transcoding para Jellyfin com iGPU AMD"
        Para habilitar o hardware transcoding no Jellyfin usando a iGPU Vega do Ryzen 5 5600G:
        1.  **No Host Proxmox:**
            *   Certifique-se que os drivers de kernel para a iGPU AMD estão carregados.
            *   O dispositivo `/dev/dri` deve existir.
            *   O usuário dentro da VM `core-services-vm` que o Docker usa (ou root) precisa de permissão para acessar `/dev/dri`. Uma forma é adicionar o usuário `kvm` (ou o usuário que roda a VM) aos grupos `render` e `video` no host Proxmox: `sudo usermod -aG render kvm` e `sudo usermod -aG video kvm`. Isso é para LXC, para VMs KVM é mais sobre passar o dispositivo.
        2.  **Na Configuração da VM `core-services-vm` (Proxmox):**
            *   Você precisa garantir que a VM tenha acesso ao dispositivo `/dev/dri` do host. Isso pode envolver editar a configuração da VM (`/etc/pve/qemu-server/VMID.conf`) para adicionar linhas como:
                ```
                lxc.cgroup2.devices.allow: c 226:0 rwm  # /dev/dri/card0
                lxc.cgroup2.devices.allow: c 226:128 rwm # /dev/dri/renderD128
                lxc.mount.entry: /dev/dri dev/dri none bind,optional,create=dir
                ```
                (Isto é mais para LXC, para KVM você pode precisar de um passthrough de dispositivo PCI para a iGPU, o que é complexo e pode conflitar com o console do Proxmox, ou configurar o kernel da VM para carregar os módulos corretos).
            *   Uma abordagem mais simples para KVM pode ser garantir que o kernel da VM carregue os módulos `amdgpu`.
        3.  **No Docker Compose do Jellyfin:**
            *   O mapeamento `- "/dev/dri:/dev/dri"` já está presente.
        4.  **Dentro do Jellyfin:**
            *   Vá para Dashboard -> Playback -> Transcoding.
            *   Selecione "AMD AMF" ou "VAAPI" como acelerador de hardware.
            *   Selecione o dispositivo VAAPI correto (geralmente `/dev/dri/renderD128`).
        O hardware transcoding pode ser temperamental. Verifique os logs do Jellyfin para erros.

5.  **Variáveis de Ambiente e Secrets no Portainer:**
    *   **Carregue o arquivo `.env`:**
        *   Path on disk: `/opt/portainer_stack_envs/media.env`.
        *   Isso fornecerá `CORE_SERVICES_VM_IP_VAR`, `DOCKER_PUID`, `DOCKER_PGID`, `SYSTEM_TIMEZONE`, `BASE_DOMAIN_FROM_VAULT`, e todos os caminhos `MEDIA_STACK_*_PATH` e `ZFS_DOWNLOADS_DATASET_NAME_NFS_PATH`.
    *   **Adicione Secrets Manualmente:**
        *   `PLEX_CLAIM_TOKEN_FROM_PORTAINER_ENV`: Obtenha um token de [plex.tv/claim](https://www.plex.tv/claim) e cole o valor aqui. Este token é de uso único e expira rapidamente, então obtenha-o pouco antes de fazer o deploy do Plex.

6.  **Deploy da Stack:**
    *   Clique em "Deploy the stack".

7.  **Configuração Pós-Deploy (Dentro de cada Aplicação):**
    *   **Plex/Jellyfin:**
        *   Acesse a UI web (e.g., `IP_DA_VM_CORE_SERVICES:32400` para Plex localmente, ou `https://jellyfin.{{ base_domain }}` via Traefik).
        *   Siga o assistente de configuração inicial.
        *   Adicione suas bibliotecas de mídia, apontando para os caminhos mapeados dentro do container (e.g., `/data/movies`, `/data/tvshows`).
    *   **Sonarr/Radarr:**
        *   Acesse suas UIs (e.g., `https://sonarr.{{ base_domain }}`).
        *   Configure indexadores (Prowlarr pode ajudar a centralizar isso).
        *   Configure clientes de download (aponte para qBittorrent, usando o nome do serviço `qbittorrent` e a porta `8088` se estiverem na mesma rede `internal_services`).
        *   Configure Root Folders (e.g., `/tv` para Sonarr, `/movies` para Radarr).
        *   Configure mapeamento de caminhos se Sonarr/Radarr e qBittorrent veem o diretório de downloads com caminhos diferentes (geralmente não é necessário se ambos usam `/downloads` internamente).
    *   **qBittorrent:**
        *   Acesse a WebUI (e.g., `https://qbittorrent.{{ base_domain }}`).
        *   Senha padrão (usuário: `admin`, senha: `adminadmin` - **MUDE IMEDIATAMENTE!**).
        *   Configure o diretório de downloads padrão para `/downloads` (se não for o padrão).
        *   Configure portas de escuta (se não usar VPN no container).

Gerenciar sua mídia pode ser muito gratificante. Aproveite sua nova stack!

Próximo passo: [Stack de Produtividade e Automação (Nextcloud, Home Assistant)](09-stack-produtividade-automacao.md).