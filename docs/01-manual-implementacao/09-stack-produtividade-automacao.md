# Seção 9: Stack de Produtividade e Automação (Nextcloud, Home Assistant)

Esta seção foca na implementação de dois serviços auto-hospedados extremamente populares e úteis para aumentar sua produtividade pessoal e automatizar aspectos da sua casa digital:

*   **Nextcloud:** Uma suíte completa de produtividade e colaboração, oferecendo sincronização e compartilhamento de arquivos (similar ao Google Drive/Dropbox), calendário, contatos, notas, chat/vídeo conferência (Nextcloud Talk), e muito mais através de um vasto ecossistema de "Apps".
*   **Home Assistant:** Uma plataforma de automação residencial open-source poderosa e flexível, que prioriza o controle local e a privacidade, permitindo integrar e automatizar uma imensa variedade de dispositivos inteligentes.

Ambos os serviços rodarão como containers Docker na sua `core-services-vm`, com todos os seus dados e configurações persistidos nos volumes NFS, garantindo a segurança e durabilidade dos dados no seu pool ZFS.

## 9.1. Preparação com Ansible para as Stacks

Antes de implantar o Nextcloud e o Home Assistant no Portainer, o Ansible precisa preparar os diretórios nos volumes NFS onde as configurações e dados dessas aplicações serão armazenados. Ele também criará os arquivos `.env` específicos para cada stack.

### Playbook `setup-productivity-automation-volumes.yml`

Este playbook Ansible, que será executado contra a `core-services-vm`, realizará as seguintes tarefas:

1.  **Criação de Diretórios de Configuração e Dados para Nextcloud:**
    *   No dataset ZFS `docker-volumes` (montado em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/` na VM), criará os seguintes subdiretórios (ou garantirá que existam com as permissões corretas):
        *   `.../nextcloud/html` (para o código principal do Nextcloud)
        *   `.../nextcloud/data` (para os dados dos usuários do Nextcloud)
        *   `.../nextcloud/config` (para o arquivo `config.php` e outras configurações do Nextcloud)
        *   `.../nextcloud/db_pg` (para os dados do banco de dados PostgreSQL do Nextcloud)
        *   (Opcional) `.../nextcloud/redis_data` se você planeja persistir dados do Redis, embora para cache muitas vezes não seja necessário.
    *   Esses diretórios terão permissões definidas para `owner: {{ docker_puid }}` e `group: {{ docker_pgid }}`.
2.  **Criação do Diretório de Configuração para Home Assistant:**
    *   No mesmo dataset ZFS `docker-volumes`, criará o diretório `.../homeassistant/config`.
    *   Permissões também para `{{ docker_puid }}:{{ docker_pgid }}`.
3.  **Preparação dos Arquivos `.env`:**
    *   Gerará o arquivo `/opt/portainer_stack_envs/productivity.env` na `core-services-vm` para a stack do Nextcloud.
    *   Gerará o arquivo `/opt/portainer_stack_envs/automation.env` na `core-services-vm` para a stack do Home Assistant.
    *   Esses arquivos conterão os caminhos completos para todos os volumes mencionados acima, além de PUID/PGID, TZ, e outras variáveis comuns. O template `ansible/templates/portainer_stack_env.j2` (detalhado na Seção 6.2) será usado, passando `stack_name: "productivity"` e `stack_name: "automation"` respectivamente.

**Ação:** Execute o playbook a partir da sua máquina de controle Ansible:
```bash
ansible-playbook ansible/playbooks/setup-productivity-automation-volumes.yml --ask-vault-pass
```

## 9.2. Deploy das Stacks via Portainer

Com os volumes e arquivos `.env` preparados pelo Ansible, podemos agora implantar as stacks de Produtividade (Nextcloud) e Automação (Home Assistant) usando o Portainer.

### Stack de Produtividade: Nextcloud (`docker/stacks/productivity/docker-compose.yml`)

Nextcloud é uma aplicação mais complexa que geralmente consiste em:
*   O container da aplicação Nextcloud principal (baseado em PHP).
*   Um container de banco de dados (usaremos PostgreSQL, conforme configurado no Ansible Vault e `main.yml`).
*   (Altamente Recomendado) Um container Redis para cache e bloqueio de arquivos, o que melhora significativamente a performance.

**Ação:**

1.  **Acesse o Portainer e Selecione o Endpoint `local`** (`core-services-vm`).
2.  Vá para "Stacks" -> "+ Add stack".
3.  **Nome da Stack:** `productivity-services` (ou `nextcloud-stack`).
4.  **Web editor:** Cole o conteúdo do arquivo `home-server/docker/stacks/productivity/docker-compose.yml` (fornecido na Seção 9.2 do seu documento original).

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

        **Pontos Chave do Compose do Nextcloud:**
        *   **Banco de Dados PostgreSQL (`nextcloud_db`):** Usa a imagem `postgres:15-alpine`. O volume de dados é mapeado para `${PROD_STACK_NEXTCLOUD_DB_PATH}`. A senha do usuário `nextcloud` no DB é passada pela variável de ambiente `${NEXTCLOUD_DB_PASSWORD_FROM_PORTAINER_ENV}`.
        *   **Redis (`nextcloud_redis`):** **É altamente recomendado descomentar e usar este serviço.** Usa a imagem `redis:7-alpine`. Não requer persistência de volume para cache por padrão, mas pode ser adicionado se necessário.
        *   **Aplicação Nextcloud (`nextcloud_app`):** Usa a imagem oficial `nextcloud`.
            *   Mapeia volumes para HTML, dados do usuário e configuração.
            *   Define variáveis de ambiente para conectar ao DB e Redis, e para o usuário administrador inicial (`NEXTCLOUD_ADMIN_USER`, `NEXTCLOUD_ADMIN_PASSWORD_FROM_PORTAINER_ENV`).
            *   `NEXTCLOUD_TRUSTED_DOMAINS` é crucial e deve incluir o subdomínio que você usará (e.g., `nextcloud.{{ base_domain }}`), `localhost`, e o IP da `core-services-vm` para acesso inicial ou direto.
            *   `PHP_MEMORY_LIMIT` e `PHP_UPLOAD_LIMIT` podem precisar de ajuste.
            *   Labels Traefik são definidas para expor o Nextcloud via `https://nextcloud.{{ base_domain }}`, usando Authelia e o middleware `nextcloud-headers@file` (que você preparou na [Seção 5.4](../01-manual-implementacao/05-rede-segura.md#role-ansiblerolesinfratraefik-config)).

5.  **Variáveis de Ambiente e Secrets no Portainer (para a stack Nextcloud):**
    *   **Carregue o Arquivo `.env`:**
        *   Na seção "Environment variables" (modo avançado), clique em "Load variables from .env file".
        *   **Path on disk:** `/opt/portainer_stack_envs/productivity.env`.
        *   Isso fornecerá `CORE_SERVICES_VM_IP_VAR`, `DOCKER_PUID`, `DOCKER_PGID`, `SYSTEM_TIMEZONE`, `base_domain` (indiretamente para Traefik), e todos os caminhos `PROD_STACK_NEXTCLOUD_*_PATH`.
    *   **Adicione Secrets Manualmente:**
        *   `NEXTCLOUD_DB_PASSWORD_FROM_PORTAINER_ENV`: Cole aqui o valor da variável `nextcloud_db_password` do seu Ansible Vault.
        *   `NEXTCLOUD_ADMIN_PASSWORD_FROM_PORTAINER_ENV`: Cole aqui o valor da variável `nextcloud_admin_initial_password` do seu Ansible Vault.
        *   (Se você habilitou senha no Redis) `NEXTCLOUD_REDIS_PASSWORD_FROM_PORTAINER_ENV`: Defina a senha para o Redis.

6.  **Deploy da Stack Nextcloud:**
    *   Clique em "**Deploy the stack**".
    *   Monitore os logs dos containers no Portainer, especialmente `nextcloud_db` (para a criação inicial do banco de dados) e `nextcloud_app` (para a configuração inicial do Nextcloud). A primeira inicialização do `nextcloud_app` pode levar alguns minutos.

7.  **Configuração Pós-Deploy do Nextcloud:**
    *   Acesse `https://nextcloud.{{ base_domain }}` no seu navegador.
    *   Você deverá ser redirecionado para Authelia para login. Após autenticar, você deve ver a tela de login do Nextcloud ou, se for a primeira vez e as variáveis de ambiente funcionaram, você poderá ser logado automaticamente como o admin ou ser apresentado a uma tela final de configuração.
    *   Faça login com o usuário administrador (`{{ NEXTCLOUD_ADMIN_USER }}` que você definiu, e.g., `ncadmin`) e a senha (`{{ NEXTCLOUD_ADMIN_PASSWORD_FROM_PORTAINER_ENV }}`).
    *   **Configurar Cache com Redis (Importante!):**
        *   Após o login, você precisará editar manualmente o arquivo `config.php` do Nextcloud para instruí-lo a usar o Redis.
        *   Conecte-se à `core-services-vm` via SSH.
        *   Edite o arquivo: `sudo nano {{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/nextcloud/config/config.php`
        *   Adicione as seguintes linhas **dentro** do array `$CONFIG = array (` e antes do `);` final:
            ```php
            'memcache.local' => '\OC\Memcache\APCu', // Se APCu estiver habilitado no PHP do container Nextcloud
            'memcache.distributed' => '\OC\Memcache\Redis',
            'memcache.locking' => '\OC\Memcache\Redis', // Essencial para bloqueio de arquivos e performance
            'redis' => [
                'host' => 'nextcloud_redis', // Nome do serviço do container Redis
                'port' => 6379,
                // 'password' => 'SUA_SENHA_REDIS_SE_CONFIGUROU_UMA', // Descomente e ajuste se Redis tiver senha
                'timeout' => 0.0, // Sem timeout para operações Redis
            ],
            ```
        *   Salve o arquivo. A mudança deve ter efeito imediato ou após o próximo acesso ao Nextcloud.
    *   **Verificar Configurações:** No Nextcloud, vá para "Administração" -> "Visão Geral". Ele fará uma verificação de segurança e configuração e poderá listar avisos ou recomendações (e.g., sobre cache, PHP OPcache, etc.). Tente resolver esses avisos para otimizar sua instância.
    *   **Instalar Apps:** Explore a loja de apps do Nextcloud para adicionar funcionalidades como Calendário, Contatos, Notas, Talk, etc.

### Stack de Automação: Home Assistant (`docker/stacks/automation/docker-compose.yml`)

Home Assistant (HASS) é o cérebro da sua automação residencial.

**Ação:**

1.  No Portainer (endpoint `local` - `core-services-vm`), vá para "Stacks" -> "+ Add stack".
2.  **Nome da Stack:** `automation-services` (ou `home-assistant-stack`).
3.  **Web editor:** Cole o conteúdo do arquivo `home-server/docker/stacks/automation/docker-compose.yml` (fornecido na Seção 9.2 do seu documento original).

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

        **Pontos Chave do Compose do Home Assistant:**
        *   Usa a imagem oficial `ghcr.io/home-assistant/home-assistant`.
        *   Mapeia o volume de configuração para `${AUTO_STACK_HOMEASSISTANT_CONFIG_PATH}`.
        *   Inclui a seção `devices` (comentada por padrão) para passthrough de dispositivos USB (como dongles Zigbee/Zwave) da VM para o container.
        *   Labels Traefik são definidas para expor o Home Assistant via `https://hass.{{ base_domain }}` e protegê-lo com Authelia.

4.  **Variáveis de Ambiente no Portainer (para a stack Home Assistant):**
    *   **Carregue o Arquivo `.env`:**
        *   Path on disk: `/opt/portainer_stack_envs/automation.env`.
        *   Isso fornecerá `CORE_SERVICES_VM_IP_VAR`, `DOCKER_PUID`, `DOCKER_PGID`, `SYSTEM_TIMEZONE`, `base_domain` (indiretamente para Traefik), e o caminho `AUTO_STACK_HOMEASSISTANT_CONFIG_PATH`.
    *   **Secrets Adicionais:** Geralmente, não há secrets críticos para definir como variáveis de ambiente para um setup básico do Home Assistant, a menos que integrações específicas que você adicione posteriormente exijam tokens de API via variáveis de ambiente.

5.  **Passthrough de Dispositivos USB (se for usar Zigbee/Zwave):**
    Se você planeja usar um dongle USB para Zigbee (e.g., ConBee II, Sonoff Zigbee 3.0 Dongle Plus) ou Z-Wave com Home Assistant, siga estes passos **antes** de implantar a stack:
    1.  **Passthrough do Host Proxmox para a VM `core-services-vm`:**
        *   Conecte o dongle USB ao seu servidor Proxmox.
        *   No shell do seu host Proxmox, use `lsusb` para identificar o `VENDOR_ID:PRODUCT_ID` do seu dongle USB (e.g., `1cf1:0030` para um ConBee II).
        *   Na UI do Proxmox, selecione sua `core-services-vm` -> Hardware -> Add -> USB Device.
        *   Escolha "Use USB Vendor/Device ID" e insira os IDs.
        *   Reinicie a `core-services-vm` para que ela reconheça o dispositivo.
    2.  **Identifique o Dispositivo Dentro da `core-services-vm`:**
        *   Após a VM reiniciar, conecte-se a ela via SSH.
        *   Use `ls /dev/tty*` ou `dmesg | grep tty` para ver qual dispositivo foi criado (e.g., `/dev/ttyUSB0`, `/dev/ttyACM0`).
    3.  **Mapeie o Dispositivo no `docker-compose.yml` do Home Assistant:**
        *   No Portainer, ao editar o compose da stack do Home Assistant (antes do deploy final), **descomente e ajuste** a seção `devices:`:
            ```yaml
            services:
              homeassistant:
                # ...
                devices:
                  - "/dev/ttyACM0:/dev/ttyACM0" # Substitua pelo caminho real do seu dispositivo na VM
            ```
    4.  **Permissões (Opcional, mas pode ser necessário):**
        O usuário dentro do container Home Assistant (geralmente roda como `root` ou um usuário `homeassistant` interno) precisa de permissão para acessar o dispositivo `/dev/tty*` mapeado. Na `core-services-vm`, o usuário `{{ vm_ansible_user_name }}` (que tem o PUID `{{ docker_puid }}`) ou o usuário `root` devem ter acesso. Se o container Home Assistant não rodar como root, pode ser necessário adicionar o PUID/PGID com que ele roda ao grupo `dialout` na `core-services-vm`:
        `sudo usermod -aG dialout {{ docker_user_name_on_vm }}` (se HASS usa PUID/PGID).
        Ou, às vezes, é mais simples garantir que o container HASS tenha os privilégios necessários (o que a imagem oficial geralmente já faz).

6.  **Deploy da Stack Home Assistant:**
    *   Com o `docker-compose.yml` ajustado (especialmente a seção `devices` se aplicável), clique em "**Deploy the stack**" no Portainer.
    *   Monitore os logs do container `homeassistant`.

7.  **Configuração Pós-Deploy do Home Assistant:**
    *   Acesse `https://hass.{{ base_domain }}` no seu navegador.
    *   Siga o assistente de configuração inicial para criar seu usuário administrador do Home Assistant, definir o nome da sua casa, localização, unidades, etc.
    *   **Adicionar Integrações:** Comece a adicionar integrações para seus dispositivos inteligentes. Se você passou um dongle Zigbee/Zwave e mapeou-o corretamente, você deverá conseguir adicionar a integração correspondente (e.g., ZHA - Zigbee Home Automation, ou Z-Wave JS).

Com Nextcloud e Home Assistant configurados, você terá uma base sólida para sua produtividade digital e automação residencial, tudo hospedado e controlado por você!

Próximo passo: [Stack de Monitoramento (Glances, Prometheus, Grafana, Loki)](10-stack-monitoramento.md).