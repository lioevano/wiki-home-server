# Seção 10: Stack de Monitoramento (Glances, Prometheus, Grafana, Loki)

Uma stack de monitoramento abrangente é indispensável para manter a saúde, entender a performance, identificar gargalos e solucionar problemas no seu servidor doméstico. Nesta seção, implementaremos um conjunto poderoso de ferramentas open-source:

*   **Node Exporter:** Já instalado no host Proxmox e em cada VM pelos playbooks Ansible anteriores. Ele coleta uma vasta gama de métricas do sistema operacional e do hardware.
*   **Glances:** Um monitor de sistema "tudo em um" que fornece uma visão geral em tempo real (com interface web) e também pode exportar suas métricas para o Prometheus.
*   **Prometheus:** Um sistema de monitoramento e alerta líder de mercado. Ele coleta (via "scraping" de endpoints) e armazena métricas como séries temporais, permitindo consultas poderosas com a linguagem PromQL.
*   **Grafana:** Uma plataforma de visualização e análise de dados extremamente popular. Usaremos o Grafana para criar dashboards interativos e informativos a partir dos dados coletados pelo Prometheus e pelo Loki.
*   **Loki:** Um sistema de agregação de logs inspirado no Prometheus, projetado para ser eficiente e fácil de integrar com Grafana. Ele foca em indexar metadados (labels) dos logs em vez do conteúdo completo.
*   **Promtail:** Um agente leve que coleta logs de arquivos locais ou do systemd journal e os envia para a sua instância Loki.

Todos os componentes principais desta stack de monitoramento (Prometheus, Grafana, Loki, Promtail e Glances) rodarão como containers Docker na sua `core-services-vm`.

## 10.1. Preparação com Ansible para a Stack de Monitoramento

Antes de implantar a stack de monitoramento no Portainer, o Ansible precisa realizar algumas tarefas preparatórias cruciais na `core-services-vm`:

1.  **Criação de Diretórios nos Volumes NFS:** Para configurações e dados persistentes de cada componente.
2.  **Copia de Arquivos de Configuração Templateados:** Para Prometheus, Grafana (provisionamento de datasources e dashboards), Loki e Promtail.
3.  **Preparação do Arquivo `.env`:** Para a stack de monitoramento no Portainer.

### Playbook `setup-monitoring-stack-volumes.yml`

Este playbook Ansible, que será executado contra a `core-services-vm`, cuidará de todas essas preparações.

*   **Criação de Diretórios:** No dataset ZFS `docker-volumes` (montado em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/` na VM), serão criados subdiretórios como:
    *   `.../prometheus/config` e `.../prometheus/data`
    *   `.../grafana/data`, `.../grafana/db_pg` (para o DB do Grafana), `.../grafana/provisioning/datasources`, `.../grafana/provisioning/dashboards`
    *   `.../loki/config` e `.../loki/data`
    *   `.../promtail/config` e `.../promtail/positions`
    *   (Opcional) `.../glances/config`
*   **Copia de Arquivos de Configuração:** O Ansible usará templates Jinja2 para gerar os arquivos de configuração iniciais e copiá-los para os diretórios NFS apropriados. Os detalhes desses arquivos de configuração foram abordados na Seção 10.1 do seu documento original.
    *   **`prometheus.yml`:** Define os alvos (targets) que o Prometheus irá "raspar" para coletar métricas (Node Exporters, Glances, Cloudflared, o próprio Prometheus).
    *   **Provisionamento do Grafana:**
        *   `datasources/prometheus.yml` e `datasources/loki.yml`: Configuram automaticamente o Prometheus e o Loki como fontes de dados no Grafana.
        *   `dashboards/dashboards.yml` e arquivos JSON de dashboards: Permitem pré-carregar dashboards úteis no Grafana.
    *   **`loki-local-config.yaml`:** Configuração principal do Loki.
    *   **`promtail-config.yml`:** Define de onde o Promtail coletará logs (e.g., journald, logs de containers Docker) e como rotulá-los.
*   **Preparação do Arquivo `.env`:** Gerará o arquivo `/opt/portainer_stack_envs/monitoring.env` na `core-services-vm` com os caminhos e variáveis PUID/PGID, TZ, etc.

**Ação:** Execute o playbook a partir da sua máquina de controle Ansible:
```bash
ansible-playbook ansible/playbooks/setup-monitoring-stack-volumes.yml --ask-vault-pass
```
### Detalhes dos Arquivos de Configuração Gerados por Ansible

#### Configuração do Prometheus (`prometheus.yml.j2`)

O Ansible usará um template (e.g., `ansible/roles/infra/prometheus-config/templates/prometheus.yml.j2`) para gerar o arquivo de configuração do Prometheus, que será copiado para `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/prometheus/config/prometheus.yml`.

```yaml
# Exemplo de ansible/roles/infra/prometheus-config/templates/prometheus.yml.j2
global:
  scrape_interval: 15s # Com que frequência buscar métricas por padrão
  evaluation_interval: 15s # Com que frequência avaliar regras de alerta

scrape_configs:
  - job_name: 'prometheus' # Monitora o próprio Prometheus
    static_configs:
      - targets: ['localhost:9090'] # Prometheus escuta em localhost:9090 dentro do seu container

  - job_name: 'node_exporter_proxmox_host'
    static_configs:
      - targets: ['{{ proxmox_host_ip_var }}:9100'] # IP do host Proxmox (de hosts.ini)
        labels:
          instance: 'proxmox_main_host'

  - job_name: 'node_exporter_core_services_vm'
    static_configs:
      - targets: ['{{ core_services_vm_ip_var }}:9100'] # IP da core-services-vm
        labels:
          instance: 'core-services-vm'

  {% if 'ai-desktop-vm' in groups['virtual_machines'] %}
  - job_name: 'node_exporter_ai_desktop_vm'
    static_configs:
      - targets: ['{{ ai_desktop_vm_ip_var }}:9100'] # IP da ai-desktop-vm
        labels:
          instance: 'ai-desktop-vm'
  {% endif %}

  - job_name: 'cloudflared_tunnel' # Métricas do Cloudflare Tunnel
    static_configs:
      # 'cloudflared' é o nome do serviço Docker do container cloudflared.
      # Prometheus, rodando na mesma rede Docker 'proxy', pode resolvê-lo.
      - targets: ['cloudflared:2000'] # Porta de métricas do cloudflared
        labels:
          instance: 'cloudflared_tunnel_metrics'

  - job_name: 'glances' # Métricas do Glances
    static_configs:
      # 'glances' é o nome do serviço Docker do container Glances.
      - targets: ['glances:61208'] # Porta web do Glances
        metrics_path: /api/3/metrics # Endpoint de métricas Prometheus do Glances
        labels:
          instance: 'glances_core_services_vm'

  # Adicione aqui jobs para cAdvisor (monitoramento de containers Docker) se decidir usá-lo.
  # - job_name: 'cadvisor'
  #   static_configs:
  #     - targets: ['cadvisor:8080'] # Se cAdvisor estiver rodando como um serviço 'cadvisor'

  # Adicione aqui jobs para monitorar aplicações específicas que expõem métricas Prometheus.
```

#### Provisionamento do Grafana (Datasources e Dashboards)

O Ansible criará arquivos na `core-services-vm` em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/grafana/provisioning/` que o Grafana usará para configurar automaticamente datasources e dashboards ao iniciar.

*   **Datasources:**
    *   `.../grafana/provisioning/datasources/prometheus.yml`:
        ```yaml
        #apiVersion: 1 # Desnecessário se o arquivo for nomeado com .yaml e no diretório correto
        datasources:
          - name: Prometheus
            type: prometheus
            access: proxy # Grafana acessa Prometheus através do seu backend
            url: http://prometheus:9090 # Nome do serviço Docker do Prometheus
            isDefault: true
            jsonData:
              timeInterval: "15s" # Sugestão de intervalo para queries
            editable: true # Permite editar na UI do Grafana
        ```
    *   `.../grafana/provisioning/datasources/loki.yml`:
        ```yaml
        #apiVersion: 1
        datasources:
          - name: Loki
            type: loki
            access: proxy
            url: http://loki:3100 # Nome do serviço Docker do Loki
            jsonData:
              maxLines: 1000 # Limite de linhas para queries de log
            editable: true
        ```
*   **Dashboards:**
    *   Você pode colocar arquivos JSON de dashboards (exportados de outras instâncias Grafana ou baixados de grafana.com/dashboards) em `.../grafana/provisioning/dashboards/`.
    *   O Ansible também pode criar um arquivo `.../grafana/provisioning/dashboards/dashboards.yml` para definir como esses dashboards JSON são carregados:
        ```yaml
        #apiVersion: 1
        providers:
          - name: 'default' # Nome do provedor de dashboards
            orgId: 1
            folder: '' # Pasta no Grafana onde os dashboards serão importados (vazio para Geral)
            type: file
            disableDeletion: false # Se true, dashboards removidos do disco não são removidos do Grafana
            editable: true
            options:
              path: /etc/grafana/provisioning/dashboards # Caminho DENTRO do container Grafana
        ```

#### Configuração do Loki (`loki-local-config.yaml.j2`)

Local: `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/loki/config/loki-local-config.yaml`
Um exemplo básico para rodar Loki em modo single-binary:

```yaml
# Exemplo de ansible/roles/infra/loki-config/templates/loki-local-config.yaml.j2
auth_enabled: false # Autenticação desabilitada para simplicidade interna. Grafana acessa.

server:
  http_listen_port: 3100
  grpc_listen_port: 9096

common:
  path_prefix: /loki # Onde Loki armazena seus dados (índice, chunks)
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1 # Single instance, sem replicação
  ring:
    instance_addr: 127.0.0.1 # Para modo single-binary
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper # Armazena índice e chunks no sistema de arquivos
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

ruler:
  alertmanager_url: http://localhost:9093 # Se usar Alertmanager com Loki (não coberto em detalhe aqui)

# Se usar Table Manager para retenção (opcional para setup simples)
# table_manager:
#   retention_deletes_enabled: true
#   retention_period: 336h # Ex: 14 dias (336h)
```

#### Configuração do Promtail (`promtail-config.yml.j2`)

Local: `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/promtail/config/config.yml`

```yaml
# Exemplo de ansible/roles/infra/promtail-config/templates/promtail-config.yml.j2
server:
  http_listen_port: 9080 # Porta para a API do Promtail (métrica, etc.)
  grpc_listen_port: 0 # Desabilita gRPC se não for necessário

positions:
  filename: /tmp/positions/positions.yaml # Onde Promtail armazena a última posição lida nos arquivos de log

clients:
  - url: http://loki:3100/loki/api/v1/push # Endpoint do Loki para enviar logs

scrape_configs:
  - job_name: system_journal # Coleta logs do journald da VM core-services-vm
    journal:
      max_age: 12h # Tempo máximo para buscar logs antigos
      path: /var/log/journal # Se journald estiver configurado para persistir aqui
      labels:
        job: system_journal
        host: "{{ core_services_vm_ip_var }}" # Ou inventory_hostname
    relabel_configs:
      - source_labels: ['__journal__systemd_unit']
        target_label: 'unit'

  - job_name: docker_logs # Coleta logs de todos os containers Docker na VM
    static_configs:
      - targets:
          - localhost # Promtail precisa saber onde encontrar os logs Docker
        labels:
          job: docker_logs
          host: "{{ core_services_vm_ip_var }}" # Ou inventory_hostname
          __path__: /var/lib/docker/containers/*/*-json.log # Caminho para os arquivos de log JSON dos containers
          # (Este __path__ é um padrão que o Docker log driver usa)
    pipeline_stages:
      - docker: {} # Processa logs no formato Docker JSON
      # Extrai 'app' e 'container_name' como labels se existirem no log Docker
      - json:
          expressions:
            app: log.attrs.container_name # Pode variar dependendo da config do log driver
            # output: log_message
      - labels:
          app:
          # container_name: # O Docker log driver já pode adicionar 'container_name'

  - job_name: var_log_messages # Coleta logs de /var/log/messages ou syslog
    static_configs:
      - targets:
          - localhost
        labels:
          job: var_log
          host: "{{ core_services_vm_ip_var }}"
          __path__: /var/log/{messages,syslog,auth.log,kern.log} # Vários arquivos de log comuns
```

## 10.2. Deploy da Stack de Monitoramento via Portainer (`docker/stacks/monitoring/docker-compose.yml`)

Com os volumes e arquivos de configuração devidamente preparados pelo Ansible, podemos agora implantar a stack de monitoramento usando o Portainer.

**Ação:**

1.  **Acesse o Portainer e Selecione o Endpoint `local`** (`core-services-vm`).
2.  Vá para "Stacks" -> "+ Add stack".
3.  **Nome da Stack:** `monitoring-services`.
4.  **Web editor:** Cole o conteúdo do arquivo `home-server/docker/stacks/monitoring/docker-compose.yml` (fornecido na Seção 10.2 do seu documento original).

    ```yaml
    # docker/stacks/monitoring/docker-compose.yml
    version: '3.9'

    networks:
      proxy: # Para expor UIs (Prometheus, Grafana, Glances) via Traefik
        name: proxy
        external: true
      internal_services: # Para comunicação interna entre componentes (e.g., Grafana -> Prometheus/Loki)
        name: internal_services
        external: true

    services:
      prometheus:
        image: prom/prometheus:v2.51.2 # Verifique a tag da versão estável mais recente
        container_name: prometheus
        restart: unless-stopped
        # user: "${DOCKER_PUID}:${DOCKER_PGID}" # Prometheus geralmente roda como 'nobody'.
                                              # Certifique-se que o diretório de dados NFS tem permissões apropriadas.
                                              # Pode ser mais simples deixar Prometheus rodar como root dentro do container
                                              # e confiar nas permissões do volume NFS (que squasha para PUID/PGID).
        networks:
          - proxy # Para a UI do Prometheus ser acessível via Traefik
          - internal_services # Para Grafana e outros poderem acessá-lo
        volumes: # Caminhos NFS do .env
          - "${MONITORING_PROMETHEUS_DATA_PATH}:/prometheus" # Dados TSDB do Prometheus
          - "${MONITORING_PROMETHEUS_CONFIG_PATH}/prometheus.yml:/etc/prometheus/prometheus.yml:ro" # Config principal
          # - "${MONITORING_PROMETHEUS_CONFIG_PATH}/alert.rules.yml:/etc/prometheus/alert.rules.yml:ro" # Opcional, se usar regras de alerta
        command:
          - '--config.file=/etc/prometheus/prometheus.yml'
          - '--storage.tsdb.path=/prometheus'
          - '--web.console.libraries=/usr/share/prometheus/console_libraries'
          - '--web.console.templates=/usr/share/prometheus/consoles'
          - '--web.enable-lifecycle' # Permite recarregar config via API POST /-/reload (útil)
          - '--web.listen-address=:9090' # Prometheus escuta nesta porta internamente
        labels: # Labels para Traefik expor a UI do Prometheus
          traefik.enable: "true"
          traefik.http.routers.prometheus.rule: "Host(`prometheus.{{ base_domain }}`)"
          traefik.http.routers.prometheus.entrypoints: "websecure"
          traefik.http.routers.prometheus.tls.certresolver: "letsencrypt"
          traefik.http.routers.prometheus.service: "prometheus-svc"
          traefik.http.services.prometheus-svc.loadbalancer.server.port: "9090"
          traefik.http.routers.prometheus.middlewares: "authelia@docker"

      grafana_db: # Banco de dados PostgreSQL para Grafana (alternativa ao SQLite padrão)
        image: postgres:15.6-alpine
        container_name: grafana_db
        restart: unless-stopped
        volumes:
          - "${MONITORING_GRAFANA_DB_PATH}:/var/lib/postgresql/data" # Dados do DB Grafana
        environment:
          - POSTGRES_DB=grafana
          - POSTGRES_USER=grafana
          - POSTGRES_PASSWORD=${GRAFANA_DB_PASSWORD_FROM_PORTAINER_ENV} # Definir no Portainer
          - TZ=${SYSTEM_TIMEZONE}
        networks:
          - internal_services # Apenas na rede interna
        healthcheck:
          test: ["CMD-SHELL", "pg_isready -U grafana -d grafana"]
          interval: 10s
          timeout: 5s
          retries: 5

      grafana:
        image: grafana/grafana-oss:10.4.2 # Verifique a tag da versão estável mais recente
        container_name: grafana
        restart: unless-stopped
        user: "${DOCKER_PUID}:${DOCKER_PGID}" # Grafana suporta rodar como não-root.
                                             # Garanta que o PUID/PGID tem permissão de escrita no volume de dados.
        networks:
          - proxy # Para a UI do Grafana ser acessível via Traefik
          - internal_services # Para Grafana acessar Prometheus, Loki, e seu DB
        volumes: # Caminhos NFS do .env
          - "${MONITORING_GRAFANA_DATA_PATH}:/var/lib/grafana" # Dados do Grafana (dashboards, configs, plugins)
          # Provisionamento automático de datasources e dashboards
          - "${MONITORING_GRAFANA_PROVISIONING_PATH}/datasources:/etc/grafana/provisioning/datasources:ro"
          - "${MONITORING_GRAFANA_PROVISIONING_PATH}/dashboards:/etc/grafana/provisioning/dashboards:ro"
        environment:
          - GF_SECURITY_ADMIN_USER=admin # Usuário admin padrão do Grafana
          - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_INITIAL_PASSWORD_FROM_PORTAINER_ENV} # Definir no Portainer
          # Configuração do Banco de Dados Externo (PostgreSQL)
          - GF_DATABASE_TYPE=postgres
          - GF_DATABASE_HOST=grafana_db # Nome do serviço do container grafana_db
          - GF_DATABASE_NAME=grafana
          - GF_DATABASE_USER=grafana
          - GF_DATABASE_PASSWORD=${GRAFANA_DB_PASSWORD_FROM_PORTAINER_ENV} # Definir no Portainer
          - GF_DATABASE_SSL_MODE=disable # Ou 'require' se o DB estiver configurado com SSL
          - TZ=${SYSTEM_TIMEZONE}
          # - GF_INSTALL_PLUGINS=grafana-clock-panel,grafana-worldmap-panel # Exemplo para instalar plugins
        depends_on:
          grafana_db: # Garante que o DB esteja saudável antes de iniciar Grafana
            condition: service_healthy
        labels: # Labels para Traefik expor a UI do Grafana
          traefik.enable: "true"
          traefik.http.routers.grafana.rule: "Host(`grafana.{{ base_domain }}`)"
          traefik.http.routers.grafana.entrypoints: "websecure"
          traefik.http.routers.grafana.tls.certresolver: "letsencrypt"
          traefik.http.routers.grafana.service: "grafana-svc"
          traefik.http.services.grafana-svc.loadbalancer.server.port: "3000" # Porta interna do Grafana
          traefik.http.routers.grafana.middlewares: "authelia@docker"

      loki:
        image: grafana/loki:2.9.5 # Verifique a tag da versão estável mais recente
        container_name: loki
        restart: unless-stopped
        # user: "${DOCKER_PUID}:${DOCKER_PGID}" # Loki também pode rodar como não-root.
        networks:
          - internal_services # Acessado por Promtail e Grafana, não precisa de acesso externo direto
        volumes: # Caminhos NFS do .env
          - "${MONITORING_LOKI_CONFIG_PATH}/loki-local-config.yaml:/etc/loki/config.yaml:ro" # Config do Loki
          - "${MONITORING_LOKI_DATA_PATH}:/loki" # Para chunks de log e índice
        command: -config.file=/etc/loki/config.yaml
        # Não precisa de labels Traefik, pois Grafana acessa Loki internamente.

      promtail:
        image: grafana/promtail:2.9.5 # Verifique a tag da versão estável mais recente
        container_name: promtail
        restart: unless-stopped
        # user: root # Promtail frequentemente precisa de acesso root para ler logs do sistema e de outros containers.
        networks:
          - internal_services # Para enviar logs para Loki
        volumes:
          # Mapeia diretórios de log da VM core-services-vm para dentro do Promtail.
          - "/var/log:/var/log:ro" # Logs do sistema da VM (e.g., syslog, auth.log)
          - "/var/lib/docker/containers:/var/lib/docker/containers:ro" # Logs de todos os containers Docker na VM
          - "${MONITORING_PROMTAIL_CONFIG_PATH}/config.yml:/etc/promtail/config.yml:ro" # Config do Promtail
          - "${MONITORING_PROMTAIL_POSITIONS_PATH}:/tmp/positions" # Para Promtail rastrear a última posição lida
        command: -config.file=/etc/promtail/config.yml
        # Não precisa de labels Traefik.

      glances:
        image: nicolargo/glances:v4.0.7 # Verifique a tag com modo webserver e exportador Prometheus.
        container_name: glances
        restart: unless-stopped
        pid: host # Necessário para Glances monitorar processos do host (VM core-services-vm)
        networks:
          - proxy # Para ser acessado via Traefik (UI Web e endpoint de métricas)
        # ports: # Não precisa mapear portas diretamente se usar Traefik, mas útil para Prometheus acessar diretamente.
        #   - "${CORE_SERVICES_VM_IP_VAR}:61208:61208" # Porta da UI Web e API do Glances
        volumes:
          - "/var/run/docker.sock:/var/run/docker.sock:ro" # Para Glances monitorar containers Docker
          - "/etc/os-release:/etc/os-release:ro" # Para Glances identificar o SO
          # - "${MONITORING_GLANCES_CONFIG_PATH}/glances.conf:/glances/conf/glances.conf:ro" # Opcional, para config customizada
        environment:
          # GLANCES_OPT para rodar em modo webserver e habilitar exportador Prometheus (geralmente habilitado por padrão em versões recentes).
          - GLANCES_OPT=--webserver --quiet --export-prometheus
          - TZ=${SYSTEM_TIMEZONE}
        labels: # Labels para Traefik expor a UI Web do Glances
          traefik.enable: "true"
          traefik.http.routers.glances.rule: "Host(`glances.{{ base_domain }}`)"
          traefik.http.routers.glances.entrypoints: "websecure"
          traefik.http.routers.glances.tls.certresolver: "letsencrypt"
          traefik.http.routers.glances.service: "glances-svc"
          traefik.http.services.glances-svc.loadbalancer.server.port: "61208" # Porta interna do Glances
          traefik.http.routers.glances.middlewares: "authelia@docker"
    ```
    
        **Pontos Chave do Compose de Monitoramento:**
        *   **Prometheus:** Mapeia o volume de dados (`${MONITORING_PROMETHEUS_DATA_PATH}`) e o arquivo de configuração (`${MONITORING_PROMETHEUS_CONFIG_PATH}/prometheus.yml`). Expõe sua UI via Traefik.
        *   **Grafana:** Usa um container PostgreSQL (`grafana_db`) para seu banco de dados (mais robusto que o SQLite padrão). Mapeia volumes para dados, DB, e os diretórios de provisionamento de datasources e dashboards. Expõe sua UI via Traefik.
        *   **Loki:** Mapeia seu arquivo de configuração e volume de dados. Não é exposto diretamente via Traefik, pois o Grafana o acessa internamente.
        *   **Promtail:** Mapeia seu arquivo de configuração, um volume para `positions` (para rastrear onde parou de ler os logs), e os diretórios de log da VM host (`/var/log` e `/var/lib/docker/containers`) em modo `readonly`.
        *   **Glances:** Roda com `pid: host` para monitorar processos da VM. Mapeia o socket Docker para monitorar containers. Expõe sua UI web e o endpoint de métricas Prometheus via Traefik.

5.  **Variáveis de Ambiente e Secrets no Portainer:**
    *   **Carregue o Arquivo `.env`:**
        *   Na seção "Environment variables" (modo avançado), clique em "Load variables from .env file".
        *   **Path on disk:** `/opt/portainer_stack_envs/monitoring.env`.
        *   Isso fornecerá `CORE_SERVICES_VM_IP_VAR`, `DOCKER_PUID`, `DOCKER_PGID`, `SYSTEM_TIMEZONE`, `base_domain` (indiretamente para Traefik), e todos os caminhos `MONITORING_*_PATH`.
    *   **Adicione Secrets Manualmente:**
        *   `GRAFANA_DB_PASSWORD_FROM_PORTAINER_ENV`: Cole aqui o valor da variável `grafana_db_password` do seu Ansible Vault (a senha para o usuário `grafana` no PostgreSQL).
        *   `GRAFANA_ADMIN_INITIAL_PASSWORD_FROM_PORTAINER_ENV`: Cole aqui o valor da variável `grafana_admin_initial_password` do seu Ansible Vault (a senha para o usuário `admin` inicial do Grafana).

6.  **Deploy da Stack de Monitoramento:**
    *   Clique em "**Deploy the stack**".
    *   Monitore os logs de cada container no Portainer para verificar se há erros durante a inicialização. O Prometheus pode levar um momento para começar a raspar os alvos. O Grafana dependerá do `grafana_db` estar saudável.

7.  **Configuração Pós-Deploy e Acesso às Interfaces:**

    *   **Prometheus UI:**
        *   Acesse: `https://prometheus.{{ base_domain }}` (após autenticar com Authelia).
        *   Navegue para **Status -> Targets**. Verifique se todos os seus alvos configurados no `prometheus.yml` (Node Exporters no Proxmox e VMs, Glances, Cloudflared, o próprio Prometheus) estão listados com o estado "**UP**". Se algum estiver "DOWN", verifique os logs do Prometheus e a conectividade com o alvo.
    *   **Grafana UI:**
        *   Acesse: `https://grafana.{{ base_domain }}` (após autenticar com Authelia).
        *   **Primeiro Login:** Use o usuário `admin` e a senha que você definiu em `GRAFANA_ADMIN_INITIAL_PASSWORD_FROM_PORTAINER_ENV`. O Grafana solicitará que você altere esta senha no primeiro login.
        *   **Verificar Datasources:** Vá para Configuration (ícone de engrenagem) -> Data Sources. Você deve ver "Prometheus" e "Loki" listados e configurados (graças aos arquivos de provisionamento). Teste a conexão com cada um.
        *   **Explorar Dashboards:**
            *   Se você incluiu arquivos JSON de dashboards no diretório de provisionamento, eles já devem estar disponíveis.
            *   Você pode importar dashboards populares da comunidade Grafana. Acesse [grafana.com/grafana/dashboards/](https://grafana.com/grafana/dashboards/) e procure por dashboards para "Node Exporter Full" (e.g., ID 1860), "Docker and System Monitoring" (e.g., ID 179) ou dashboards específicos para as tecnologias que você usa. Para importar, vá em Dashboards (ícone de quatro quadrados) -> + Import, e cole o ID do dashboard ou o JSON.
        *   **Explorar Logs com Loki:** Vá para "Explore" (ícone de bússola), selecione o datasource "Loki". Use LogQL para consultar seus logs (e.g., `{job="docker_logs"}`).
    *   **Glances WebUI:**
        *   Acesse: `https://glances.{{ base_domain }}` (após autenticar com Authelia).
        *   Você verá uma visão geral em tempo real dos recursos da sua `core-services-vm` e dos containers Docker rodando nela.
    *   **Promtail Logs:**
        *   Verifique os logs do container `promtail` no Portainer para garantir que ele está conseguindo ler os arquivos de log especificados e enviá-los para o Loki sem erros.

Com esta stack de monitoramento configurada e funcionando, você terá uma visibilidade crucial sobre a saúde, o desempenho e os eventos do seu servidor doméstico e suas aplicações. Isso é fundamental para a manutenção proativa e para o troubleshooting eficaz.