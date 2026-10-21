---
description: "Deploy das aplicações na stack apps: monitoramento, n8n e Home Assistant, com preparação de volumes via Ansible."
---

# Seção 7: Deploy de Aplicações (Monitoramento, n8n, Home Assistant)

As aplicações ficam em um único compose: `docker/stacks/apps/docker-compose.yml`. A mídia tem stack própria (`media`), descrita na [Seção 10](10-midia.md); fotos e arquivos (Immich, Nextcloud e Collabora) também, nas stacks `photos` e `cloud` da [Seção 11](11-fotos-arquivos.md).

## Visão Geral dos Serviços

| Categoria | Serviços | Acesso |
|---|---|---|
| Monitoramento | Prometheus, Grafana (+ Postgres), Loki, blackbox-exporter, Diun, Homepage, docker-socket-proxy | `prometheus.`, `grafana.`, `home.` |
| Automação | n8n, Home Assistant | `n8n.`, `hass.` |

## Deploy via Portainer

1. Acesse o Portainer em `https://portainer.seudominio.com`
2. Vá em **Stacks** > **Add Stack**
3. Nome: `apps`
4. Selecione **Web editor**
5. Cole o conteúdo de `docker/stacks/apps/docker-compose.yml`
6. Em **Env**, carregue o arquivo `/opt/portainer_stack_envs/apps.env` montado conforme os passos manuais abaixo
7. Clique em **Deploy the stack**

### Variáveis da stack

A stack `apps` é um único compose, mas cada playbook gera o seu `.env` em `/opt/portainer_stack_envs/` (via `ansible/templates/portainer_stack_env.j2`). Os que contêm segredos são gravados com `mode: '0600'`.

| Arquivo | Playbook | Segredos e valores específicos |
|---|---|---|
| `productivity.env` | `setup-productivity-automation-volumes.yml` | só `CORE_SERVICES_VM_IP_VAR` (`core_services_vm_ip_var` do `hosts.ini`), usado pelo Prometheus para publicar a porta 9090 na LAN (o Nextcloud saiu para a stack `cloud`) |
| `automation.env` | `setup-productivity-automation-volumes.yml` | caminhos do Home Assistant |
| `n8n.env` | `setup-n8n-volumes.yml` | caminho de configuração e subdomínio; `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` e `NOTIFICACOES_WEBHOOK_TOKEN` (vault `telegram_bot_token`, `telegram_chat_id`, `notificacoes_webhook_token`) para o workflow de notificações. O login do n8n é a conta de dono criada no primeiro acesso, atrás do Authelia |
| `monitoring.env` | `setup-monitoring-stack-volumes.yml` | `GRAFANA_DB_PASSWORD_FROM_PORTAINER_ENV` (vault `grafana_db_password`), `GRAFANA_ADMIN_INITIAL_PASSWORD_FROM_PORTAINER_ENV` (vault `grafana_admin_initial_password`); `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` e `NOTIFICACOES_WEBHOOK_TOKEN` para os alertas do Grafana; credenciais dos widgets da Homepage (`HOMEPAGE_VAR_*`, vault `homepage_widget_keys` e `arr_api_keys`) |

### Passos manuais ao mudar variáveis ou segredos

1. Confira no vault real (`ansible-vault edit inventories/home/group_vars/all/vault.yml`) que as chaves da tabela acima estão preenchidas (evite `$`, `#`, aspas e espaços nos segredos: o `.env` não usa aspas).
2. Rode cada playbook primeiro com `--check` e depois sem (não use `--diff`, que imprimiria os segredos do `.env` no terminal):
   ```bash
   for pb in setup-productivity-automation-volumes setup-n8n-volumes setup-monitoring-stack-volumes; do
     ansible-playbook -i inventories/home/hosts.ini playbooks/$pb.yml --ask-vault-pass --check
   done
   # sem erros? repita o laço sem --check
   ```
   Depois junte os arquivos num só `apps.env` para o Portainer (contém segredos: `0600`). Os quatro repetem as variáveis comuns e as do Telegram com o mesmo valor; o `awk` mantém só a primeira de cada nome e tira os comentários:
   ```bash
   # na core-services-vm
   sudo sh -c 'umask 077; cd /opt/portainer_stack_envs && cat productivity.env automation.env n8n.env monitoring.env | awk -F= "/^[A-Za-z_]/ && !visto[\$1]++" > apps.env && chmod 600 apps.env'
   ```
3. No Portainer, abra a stack `apps`, recarregue `apps.env` em **Env** e clique em **Update the stack**.

### Versões fixadas

O Grafana (`13.2.4`), o n8n (`2.44.4`) e o Home Assistant (`2026.10.2`) têm versão fixada no compose: o hub de MCPs da [base dos agentes](13-agentes-base.md) usa as APIs deles (o MCP nativo do n8n exige 2.33 ou mais nova; o do Home Assistant é embutido). Para atualizar, troque a versão no compose, confira as notas da versão nova e teste as ferramentas pelo Claude Code (página 13) depois do redeploy.

## Preparação dos Volumes

Os volumes são criados pelos playbooks Ansible `ansible/playbooks/setup-productivity-automation-volumes.yml`, `ansible/playbooks/setup-n8n-volumes.yml` e `ansible/playbooks/setup-monitoring-stack-volumes.yml`. A partir de `server/ansible`:

```bash
# Volumes do Home Assistant (e IP da VM para o Prometheus)
ansible-playbook -i inventories/home/hosts.ini playbooks/setup-productivity-automation-volumes.yml

# Volumes n8n
ansible-playbook -i inventories/home/hosts.ini playbooks/setup-n8n-volumes.yml

# Volumes monitoramento (gera prometheus.yml, Loki, blackbox, alertas do Grafana, Diun e Homepage)
ansible-playbook -i inventories/home/hosts.ini playbooks/setup-monitoring-stack-volumes.yml
```

O playbook de monitoramento renderiza as configurações a partir de `ansible/templates/prometheus.yml.j2`, `ansible/templates/loki-local-config.yaml.j2`, `ansible/templates/blackbox.yml.j2`, `ansible/templates/grafana/alerting/` e `ansible/templates/homepage/` (ver [Painel e Notificações](09-painel-notificacoes.md)), e o `.env` da stack a partir de `ansible/templates/portainer_stack_env.j2`.

## Ativando/Desativando Serviços

Para desativar um serviço que não usa, adicione `enabled: false` nas labels do Traefik do serviço no compose, ou comente o bloco inteiro do serviço.


## Notas por Serviço

- **Nextcloud**: saiu desta stack; ver [Fotos e Arquivos](11-fotos-arquivos.md).
- **Prometheus**: Recebe as métricas dos Alloys por *remote write* (`--web.enable-remote-write-receiver`) e publica a porta 9090 no IP da `core-services-vm` (`${CORE_SERVICES_VM_IP_VAR}:9090`), só para a LAN, como o Loki; a interface continua em `prometheus.seudominio.com`, atrás do Authelia. O job `alloy` de `ansible/templates/prometheus.yml.j2` raspa o `/metrics` do Alloy de cada host (porta 12345) para saber se ele está vivo ([seção 4.4](04-configuracao-base-vms-ubuntu.md#44-coleta-com-grafana-alloy-ansiblerolesinfraalloy)).
- **Grafana**: Login inicial `admin` / senha do vault (`grafana_admin_initial_password`). Os datasources Prometheus (`http://prometheus:9090`) e Loki (`http://loki:3100`) são provisionados automaticamente pelo `setup-monitoring-stack-volumes.yml` (pasta `grafana/provisioning`, montada em `/etc/grafana/provisioning`).
- **Loki**: Guarda os logs que o Grafana Alloy coleta em cada host (containers, journal e `/var/log`; [seção 4.4](04-configuracao-base-vms-ubuntu.md#44-coleta-com-grafana-alloy-ansiblerolesinfraalloy)), que substituiu o Promtail. O Loki usa schema v13 com índice TSDB (`ansible/templates/loki-local-config.yaml.j2`), o formato exigido pelo Loki 3. O Loki publica a porta 3100 no IP da `core-services-vm` (`${CORE_SERVICES_VM_IP_VAR}:3100`) para receber os logs dos Alloys de todos os hosts; ele não tem autenticação, então a porta só deve ser alcançável pela LAN (não crie rota no Traefik nem no túnel para ela). Portas publicadas pelo Docker não passam pelo UFW da VM, então a proteção é a própria LAN.
- **n8n**: Webhook URL configurado automaticamente para `https://n8n.seudominio.com/`. O acesso passa pelo Authelia; no primeiro acesso o n8n pede a criação da conta de dono (a autenticação básica `N8N_BASIC_AUTH_*` não existe mais no n8n 1.x).
- **Home Assistant**: `devices` para USB (Zigbee/Zwave). Ajuste `/dev/ttyUSB0` para seu dispositivo.
  - *Notificações (NTF-3):* em `configuration.yaml`, um `rest_command` que faz `POST` em `http://n8n:5678/webhook/notificar` com `headers: {Authorization: "Bearer <token>"}`, `content_type: application/json` e `payload: '{"titulo": "{{ titulo }}", "mensagem": "{{ mensagem }}", "gravidade": "{{ gravidade }}", "app": "homeassistant"}'`; chame-o nas automações. Guarde o token em `secrets.yaml` do Home Assistant.