# Seção 9: Stack de Produtividade e Automação (Nextcloud, Home Assistant)

Esta seção foca na implementação de serviços para aumentar sua produtividade pessoal e automatizar aspectos da sua casa ou rotinas digitais. Os principais serviços abordados são:
*   **Nextcloud:** Uma plataforma de produtividade auto-hospedada para sincronização e compartilhamento de arquivos, calendário, contatos, notas e muito mais (similar ao Google Drive/Dropbox).
*   **Home Assistant:** Uma poderosa plataforma de automação residencial open-source que coloca o controle local e a privacidade em primeiro lugar.

Ambos rodarão como containers Docker na `core-services-vm`, com dados e configurações persistidos nos volumes NFS.

## 9.1. Preparação com Ansible

Antes de implantar as stacks no Portainer, o Ansible preparará os diretórios NFS e os arquivos `.env` necessários.

### Playbook `setup-productivity-automation-volumes.yml`

Este playbook, executado contra a `core-services-vm`, irá:
*   Criar os subdiretórios necessários no dataset ZFS `docker-volumes` (montado em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/`) para as configurações e dados de Nextcloud (HTML, dados do usuário, config, banco de dados) e Home Assistant (config).
*   Preparar os arquivos `.env` na `core-services-vm`:
    *   `/opt/portainer_stack_envs/productivity.env` (para Nextcloud)
    *   `/opt/portainer_stack_envs/automation.env` (para Home Assistant)
    Estes arquivos conterão os caminhos e variáveis PUID/PGID, TZ, etc.

**Ação:** Execute o playbook a partir da sua máquina de controle Ansible:
```bash
ansible-playbook ansible/playbooks/setup-productivity-automation-volumes.yml --ask-vault-pass
```
Este playbook utilizará o template `ansible/templates/portainer_stack_env.j2` (detalhado na Seção 6.2), passando `stack_name: "productivity"` e `stack_name: "automation"` respectivamente para gerar os caminhos corretos nos arquivos `.env`.

## 9.2. Deploy das Stacks via Portainer

Com os volumes preparados, vamos implantar as stacks de Produtividade (Nextcloud) e Automação (Home Assistant).

### Stack de Produtividade: Nextcloud (`docker/stacks/productivity/docker-compose.yml`)

Nextcloud requer um banco de dados (PostgreSQL neste guia) e o container da aplicação principal.

**Ação:**
1.  No Portainer, certifique-se de que está conectado ao endpoint `local` (`core-services-vm`).
2.  Vá para "Stacks" -> "+ Add stack".
3.  **Nome:** `productivity-services` (ou `nextcloud-stack`).
4.  **Web editor:** Cole o conteúdo do arquivo `infra-servidor-domestico/docker/stacks/productivity/docker-compose.yml`:

    ```yaml
    # docker/stacks/productivity/docker-compose.yml
    version: '3.9'

    networks:
      proxy: # Para expor Nextcloud via Traefik
        name: proxy
        external: true
      internal_services: # Para comunicação entre Nextcloud App e seu DB (e Redis se usado)
        name: internal_services
        external: true

    services:
      nextcloud_db: # Banco de dados PostgreSQL para Nextcloud
        image: postgres:15-alpine # Use uma versão específica e estável
        container_name: nextcloud_db
        restart: unless-stopped
        volumes:
          # Caminho NFS para o banco de dados do Nextcloud. A variável virá do .env.
          - "${PROD_STACK_NEXTCLOUD_DB_PATH}:/var/lib/postgresql/data"
        environment:
          - POSTGRES_DB=nextcloud
          - POSTGRES_USER=nextcloud
          # POSTGRES_PASSWORD será definido como secret no Portainer
          - POSTGRES_PASSWORD=${NEXTCLOUD_DB_PASSWORD_FROM_PORTAINER_ENV}
          - TZ=${SYSTEM_TIMEZONE} # Do .env
        networks:
          - internal_services # Apenas na rede interna
        healthcheck: # Verifica se o banco de dados está pronto
          test: ["CMD-SHELL", "pg_isready -U nextcloud -d nextcloud"]
          interval: 10s
          timeout: 5s
          retries: 5

      # Opcional, mas altamente recomendado para performance do Nextcloud: Redis
      nextcloud_redis:
        image: redis:7-alpine # Use uma versão específica e estável
        container_name: nextcloud_redis
        restart: unless-stopped
        networks:
          - internal_services # Apenas na rede interna
        # Se quiser senha no Redis (recomendado)
        # command: redis-server --requirepass ${NEXTCLOUD_REDIS_PASSWORD_FROM_PORTAINER_ENV}
        healthcheck:
          test: ["CMD", "redis-cli", "ping"]
          interval: 10s
          timeout: 5s
          retries: 3

      nextcloud_app: # Container principal da aplicação Nextcloud
        image: nextcloud:28.0.5 # Verifique a tag da versão estável mais recente
        container_name: nextcloud_app
        restart: unless-stopped
        networks:
          - proxy # Para ser alcançado por Traefik
          - internal_services # Para alcançar o DB e Redis
        # ports: # Não é necessário expor portas diretamente se usar Traefik
        #   - "${CORE_SERVICES_VM_IP_VAR}:8080:80" # Exemplo se quisesse acesso direto
        volumes: # Caminhos NFS do .env
          - "${PROD_STACK_NEXTCLOUD_HTML_PATH}:/var/www/html" # Código principal do Nextcloud
          - "${PROD_STACK_NEXTCLOUD_DATA_PATH}:/var/www/html/data" # Dados dos usuários
          - "${PROD_STACK_NEXTCLOUD_CONFIG_PATH}:/var/www/html/config" # Configuração do Nextcloud
        environment:
          - POSTGRES_HOST=nextcloud_db # Nome do serviço do container DB
          - POSTGRES_DB=nextcloud
          - POSTGRES_USER=nextcloud
          - POSTGRES_PASSWORD=${NEXTCLOUD_DB_PASSWORD_FROM_PORTAINER_ENV} # Definir no Portainer
          # Usuário administrador inicial do Nextcloud (será criado na primeira execução)
          - NEXTCLOUD_ADMIN_USER=ncadmin # Escolha seu nome de admin
          - NEXTCLOUD_ADMIN_PASSWORD=${NEXTCLOUD_ADMIN_PASSWORD_FROM_PORTAINER_ENV} # Definir no Portainer
          # Domínios confiáveis. Inclua o subdomínio que você usará, localhost e o IP da VM para acesso local inicial.
          - NEXTCLOUD_TRUSTED_DOMAINS=nextcloud.{{ base_domain }} localhost {{ core_services_vm_ip_var }} # Use suas vars
          - PHP_MEMORY_LIMIT=512M # Ajuste conforme a RAM disponível na VM. Pode precisar de mais para apps Nextcloud.
          - PHP_UPLOAD_LIMIT=4G   # Limite de upload de arquivos (e.g., 4GB). Ajuste conforme sua necessidade e config do Nginx/Apache interno.
          - TZ=${SYSTEM_TIMEZONE}
          # Configuração para Redis (se usado)
          - REDIS_HOST=nextcloud_redis # Nome do serviço do container Redis
          # - REDIS_HOST_PASSWORD=${NEXTCLOUD_REDIS_PASSWORD_FROM_PORTAINER_ENV} # Se Redis tiver senha
        depends_on: # Garante que DB e Redis (se usado) iniciem antes
          nextcloud_db:
            condition: service_healthy
          nextcloud_redis: # Descomente se usar Redis
            condition: service_healthy
        labels: # Labels para Traefik
          traefik.enable: "true"
          traefik.http.routers.nextcloud.rule: "Host(`nextcloud.{{ base_domain }}`)" # Use sua var base_domain
          traefik.http.routers.nextcloud.entrypoints: "websecure"
          traefik.http.routers.nextcloud.tls.certresolver: "letsencrypt"
          traefik.http.routers.nextcloud.service: "nextcloud-svc"
          # Middleware para headers de Nextcloud (definido em traefik/config/dynamic/nextcloud_middleware.yml)
          # E Authelia para proteção
          traefik.http.routers.nextcloud.middlewares: "authelia@docker,nextcloud-headers@file"
          # Configurações adicionais para Nextcloud (CalDAV, CardDAV, etc.)
          # Veja https://doc.traefik.io/traefik/routing/routers/#configuring-tcp-routers
          # e documentação do Nextcloud para URLs .well-known
          # Exemplo (pode precisar de ajustes e de um router TCP separado):
          # traefik.http.routers.nextcloud.priority: 10 # Prioridade se houver conflitos
          # traefik.http.middlewares.nextcloud-redirects.redirectregex.regex: "^https://(.*)/.well-known/(card|cal)dav"
          # traefik.http.middlewares.nextcloud-redirects.redirectregex.replacement: "https://\${1}/remote.php/dav/"
          # traefik.http.middlewares.nextcloud-redirects.redirectregex.permanent: "true"
          # Serviço para Nextcloud App
          traefik.http.services.nextcloud-svc.loadbalancer.server.port: "80" # Porta HTTP interna do container Nextcloud App
    ```
    !!! important "Configuração de Redis para Nextcloud"
        O uso de Redis com Nextcloud é **altamente recomendado** para melhorar a performance, especialmente para bloqueio de arquivos e cache. O compose acima inclui um serviço `nextcloud_redis` comentado. Para usá-lo:
        1.  Descomente o serviço `nextcloud_redis`.
        2.  Descomente as variáveis de ambiente `REDIS_HOST` (e `REDIS_HOST_PASSWORD` se você configurar uma senha no Redis) no serviço `nextcloud_app`.
        3.  Descomente a dependência de `nextcloud_redis` no serviço `nextcloud_app`.
        4.  Defina a variável `NEXTCLOUD_REDIS_PASSWORD_FROM_PORTAINER_ENV` no Portainer se você habilitar a senha no Redis.
        5.  Após o Nextcloud estar rodando, você precisará adicionar a configuração do Redis ao arquivo `config.php` do Nextcloud (localizado em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/nextcloud/config/config.php`).
            Exemplo de adição ao `config.php`:
            ```php
            'memcache.local' => '\OC\Memcache\APCu', // Se APCu estiver disponível e configurado no PHP do container
            'memcache.distributed' => '\OC\Memcache\Redis',
            'memcache.locking' => '\OC\Memcache\Redis', // Essencial para bloqueio de arquivos
            'redis' => [
                'host' => 'nextcloud_redis', // Nome do serviço do container Redis
                'port' => 6379,
                // 'password' => 'SUA_SENHA_REDIS_SE_CONFIGURADA', // Se você configurou uma senha
                'timeout' => 0.0,
            ],
            ```
            Consulte a [documentação do Nextcloud sobre configuração de cache de memória](https://docs.nextcloud.com/server/latest/admin_manual/configuration_server/caching_configuration.html) para detalhes.

5.  **Variáveis de Ambiente e Secrets no Portainer (para Nextcloud):**
    *   **Carregue o arquivo `.env`:**
        *   Path on disk: `/opt/portainer_stack_envs/productivity.env`.
        *   Isso fornecerá `CORE_SERVICES_VM_IP_VAR`, `DOCKER_PUID`, `DOCKER_PGID`, `SYSTEM_TIMEZONE`, `base_domain` (indiretamente, via `{{ base_domain }}` nos labels), e os caminhos `PROD_STACK_NEXTCLOUD_*_PATH`.
    *   **Adicione Secrets Manualmente:**
        *   `NEXTCLOUD_DB_PASSWORD_FROM_PORTAINER_ENV`: A senha que você definiu para o usuário `nextcloud` no PostgreSQL (variável `nextcloud_db_password` do seu Ansible Vault).
        *   `NEXTCLOUD_ADMIN_PASSWORD_FROM_PORTAINER_ENV`: A senha para o usuário administrador inicial do Nextcloud (variável `nextcloud_admin_initial_password` do seu Ansible Vault).
        *   (Se usar Redis com senha) `NEXTCLOUD_REDIS_PASSWORD_FROM_PORTAINER_ENV`: A senha que você configurou para o Redis.

6.  **Deploy da Stack Nextcloud:**
    *   Clique em "Deploy the stack".
    *   Monitore os logs, especialmente do `nextcloud_app` e `nextcloud_db`, para verificar a inicialização e criação do banco de dados.

7.  **Configuração Pós-Deploy do Nextcloud:**
    *   Acesse `https://nextcloud.{{ base_domain }}`.
    *   Você deverá ver a tela de login ou, na primeira vez, o assistente de configuração pode ser executado (embora as variáveis de ambiente já devam ter configurado o admin e o DB).
    *   Faça login com o usuário admin e senha que você definiu.
    *   Explore as configurações administrativas do Nextcloud (e.g., Apps, Visão Geral da Segurança & Configuração para verificar se há avisos).
    *   Se você habilitou Redis, verifique se a configuração no `config.php` está correta.

### Stack de Automação: Home Assistant (`docker/stacks/automation/docker-compose.yml`)

Home Assistant é o hub para sua automação residencial.

**Ação:**
1.  No Portainer (endpoint `local` - `core-services-vm`), vá para "Stacks" -> "+ Add stack".
2.  **Nome:** `automation-services` (ou `home-assistant-stack`).
3.  **Web editor:** Cole o conteúdo do arquivo `infra-servidor-domestico/docker/stacks/automation/docker-compose.yml`:

    ```yaml
    # docker/stacks/automation/docker-compose.yml
    version: '3.9'

    networks:
      proxy: # Para expor Home Assistant via Traefik
        name: proxy
        external: true

    services:
      homeassistant:
        image: ghcr.io/home-assistant/home-assistant:2024.5.5 # Verifique a tag da versão estável mais recente
        container_name: homeassistant
        restart: unless-stopped
        volumes:
          # Caminho NFS para a configuração do Home Assistant. A variável virá do .env.
          - "${AUTO_STACK_HOMEASSISTANT_CONFIG_PATH}:/config"
          - "/etc/localtime:/etc/localtime:ro" # Sincroniza o fuso horário
          # - "/run/dbus:/run/dbus:ro" # Necessário para algumas integrações que usam D-Bus (e.g., Bluetooth)
        # network_mode: host # Usar 'host' simplifica a descoberta de dispositivos na rede local (mDNS/SSDP),
                              # mas para integração com Traefik e Cloudflare Tunnel, é melhor NÃO usar 'host'
                              # e expor via Traefik. Se precisar de descoberta, pode ser necessário
                              # configurar mDNS repeater ou Avahi no host/VM e/ou Traefik.
        networks:
          - proxy
        # ports: # Não é necessário expor portas diretamente se usar Traefik
        #   - "${CORE_SERVICES_VM_IP_VAR}:8123:8123" # Porta padrão do Home Assistant
        # --- Passthrough de Dispositivos USB (Exemplo para stick Zigbee/Zwave) ---
        # 1. Certifique-se que o dispositivo USB está passado do Host Proxmox para a core-services-vm.
        #    No Proxmox Host, edite /etc/pve/qemu-server/VMID.conf da core-services-vm e adicione:
        #    usb0: host=VENDOR_ID:PRODUCT_ID (Use 'lsusb' no Proxmox host para encontrar os IDs)
        # 2. Dentro da core-services-vm, o dispositivo aparecerá (e.g., /dev/ttyUSB0).
        # 3. Mapeie este dispositivo para o container Home Assistant:
        devices:
           - "/dev/ttyUSB0:/dev/ttyUSB0" # Exemplo, substitua pelo caminho real do seu dispositivo na VM
        # privileged: true # Tente evitar. Apenas se estritamente necessário para acesso ao hardware.
                           # Para /dev/ttyUSB*, geralmente não é necessário se as permissões estiverem corretas.
                           # O usuário dentro do container (ou o PUID) pode precisar ser membro do grupo 'dialout' na VM.
        environment:
          - TZ=${SYSTEM_TIMEZONE} # Do .env
          # - PUID=${DOCKER_PUID} # Home Assistant geralmente roda como root dentro do container
          # - PGID=${DOCKER_PGID} # ou tem seu próprio gerenciamento de usuário.
        labels: # Labels para Traefik
          traefik.enable: "true"
          traefik.http.routers.homeassistant.rule: "Host(`hass.{{ base_domain }}`)" # Use sua var base_domain
          traefik.http.routers.homeassistant.entrypoints: "websecure"
          traefik.http.routers.homeassistant.tls.certresolver: "letsencrypt"
          traefik.http.routers.homeassistant.service: "homeassistant-svc"
          # Home Assistant usa WebSockets, Traefik geralmente lida bem com isso por padrão.
          traefik.http.services.homeassistant-svc.loadbalancer.server.port: "8123" # Porta interna do Home Assistant
          traefik.http.routers.homeassistant.middlewares: "authelia@docker" # Protegido por Authelia
    ```
    !!! important "Passthrough de Dispositivos USB para Home Assistant"
        Se você planeja usar um dongle USB para Zigbee (e.g., ConBee II, Sonoff Zigbee 3.0 Dongle Plus) ou Z-Wave com Home Assistant:
        1.  **Passthrough do Host Proxmox para a VM `core-services-vm`:**
            *   No shell do seu host Proxmox, use `lsusb` para identificar o `VENDOR_ID:PRODUCT_ID` do seu dongle USB.
            *   Edite a configuração da sua `core-services-vm` no Proxmox. Isso pode ser feito via UI (Hardware -> Add -> USB Device -> Use USB Vendor/Device ID) ou editando o arquivo `/etc/pve/qemu-server/VMID.conf` (substitua `VMID` pelo ID da sua `core-services-vm`) e adicionando uma linha como: `usb0: host=VENDOR_ID:PRODUCT_ID,usb3=yes` (se for um dispositivo USB 3).
            *   Reinicie a `core-services-vm`.
        2.  **Identifique o Dispositivo Dentro da `core-services-vm`:**
            *   Após a VM reiniciar, conecte-se a ela via SSH.
            *   Use `ls /dev/tty*` ou `dmesg | grep tty` para ver qual dispositivo foi criado (e.g., `/dev/ttyUSB0`, `/dev/ttyACM0`).
        3.  **Mapeie o Dispositivo para o Container Home Assistant:**
            *   No `docker-compose.yml` acima, descomente a seção `devices:` e ajuste o caminho para corresponder ao dispositivo que apareceu dentro da `core-services-vm` (e.g., `- "/dev/ttyUSB0:/dev/ttyUSB0"`).
        4.  **Permissões:** O usuário que roda o processo Home Assistant dentro do container (que pode ser root ou um usuário específico do Home Assistant) precisa de permissão para ler/escrever no dispositivo mapeado. Na `core-services-vm`, o usuário `{{ vm_ansible_user_name }}` (que geralmente tem o PUID `{{ docker_puid }}`) pode precisar ser adicionado ao grupo `dialout`: `sudo usermod -aG dialout {{ vm_ansible_user_name }}`. Se o container Home Assistant rodar como root, isso geralmente não é um problema.

4.  **Variáveis de Ambiente no Portainer (para Home Assistant):**
    *   **Carregue o arquivo `.env`:**
        *   Path on disk: `/opt/portainer_stack_envs/automation.env`.
        *   Isso fornecerá `CORE_SERVICES_VM_IP_VAR`, `DOCKER_PUID`, `DOCKER_PGID`, `SYSTEM_TIMEZONE`, `base_domain`, e `AUTO_STACK_HOMEASSISTANT_CONFIG_PATH`.
    *   Não há secrets críticos para definir como variáveis de ambiente para um setup básico do Home Assistant, a menos que integrações específicas exijam.

5.  **Deploy da Stack Home Assistant:**
    *   Clique em "Deploy the stack".
    *   Monitore os logs do container `homeassistant`.

6.  **Configuração Pós-Deploy do Home Assistant:**
    *   Acesse `https://hass.{{ base_domain }}`.
    *   Siga o assistente de configuração inicial para criar seu usuário administrador do Home Assistant e configurar nome da casa, localização, etc.
    *   Comece a adicionar integrações para seus dispositivos inteligentes. Se você passou um dongle Zigbee/Zwave, configure a integração correspondente (e.g., ZHA para Zigbee).

Com Nextcloud e Home Assistant rodando, sua produtividade e automação doméstica estão prontas para decolar!

Próximo passo: [Stack de Monitoramento (Glances, Prometheus, Grafana, Loki)](10-stack-monitoramento.md).