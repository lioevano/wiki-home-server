---
description: "Deploy das aplicações na stack apps: Nextcloud, mídia, monitoramento, n8n e Home Assistant, com preparação de volumes via Ansible."
---

# Seção 7: Deploy de Aplicações (Nextcloud, Mídia, Monitoramento, n8n, Home Assistant)

Todas as aplicações são agora gerenciadas em um único compose file: `docker/stacks/apps/docker-compose.yml`.

## Visão Geral dos Serviços

| Categoria | Serviços | Acesso |
|---|---|---|
| Produtividade | Nextcloud (+ Postgres, Redis) | `nextcloud.seudominio.com` |
| Mídia | Jellyfin, Sonarr, Radarr, qBittorrent | `jellyfin.`, `sonarr.`, `radarr.`, `qbittorrent.` |
| Monitoramento | Prometheus, Grafana (+ Postgres), Loki, Promtail | `prometheus.`, `grafana.` |
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
| `productivity.env` | `setup-productivity-automation-volumes.yml` | `NEXTCLOUD_DB_PASSWORD_FROM_PORTAINER_ENV` (vault `nextcloud_db_password`), `NEXTCLOUD_ADMIN_PASSWORD_FROM_PORTAINER_ENV` (vault `nextcloud_admin_initial_password`), `CORE_SERVICES_VM_IP_VAR` (`core_services_vm_ip_var` do `hosts.ini`) |
| `automation.env` | `setup-productivity-automation-volumes.yml` | caminhos do Home Assistant |
| `media.env` | `setup-media-stack-volumes.yml` | caminhos de mídia |
| `n8n.env` | `setup-n8n-volumes.yml` | `N8N_ADMIN_USER_FROM_PORTAINER_ENV` (vault `n8n_admin_user`), `N8N_ADMIN_PASSWORD_FROM_PORTAINER_ENV` (vault `n8n_admin_password`) |
| `monitoring.env` | `setup-monitoring-stack-volumes.yml` | `GRAFANA_DB_PASSWORD_FROM_PORTAINER_ENV` (vault `grafana_db_password`), `GRAFANA_ADMIN_INITIAL_PASSWORD_FROM_PORTAINER_ENV` (vault `grafana_admin_initial_password`) |

### Passos manuais ao mudar variáveis ou segredos

1. Confira no vault real (`ansible-vault edit ansible/inventories/home/group_vars/all/vault.yml`) que as chaves da tabela acima estão preenchidas (evite `$`, `#`, aspas e espaços nos segredos: o `.env` não usa aspas).
2. Rode cada playbook primeiro com `--check` e depois sem (não use `--diff`, que imprimiria os segredos do `.env` no terminal):
   ```bash
   for pb in setup-productivity-automation-volumes setup-media-stack-volumes setup-n8n-volumes setup-monitoring-stack-volumes; do
     ansible-playbook -i ansible/inventories/home/hosts.ini ansible/playbooks/$pb.yml --ask-vault-pass --check
   done
   # sem erros? repita o laço sem --check
   ```
   Depois junte os arquivos num só `apps.env` para o Portainer (contém segredos: `0600`):
   ```bash
   # na core-services-vm
   sudo sh -c 'umask 077; cd /opt/portainer_stack_envs && cat productivity.env automation.env media.env n8n.env monitoring.env > apps.env && chmod 600 apps.env'
   ```
3. No Portainer, abra a stack `apps`, recarregue `apps.env` em **Env** e clique em **Update the stack**.

## Preparação dos Volumes

Os volumes são criados pelos playbooks Ansible:

```bash
# Volumes Nextcloud + automação
ansible-playbook -i ansible/inventories/home/hosts.ini ansible/playbooks/setup-productivity-automation-volumes.yml

# Volumes mídia
ansible-playbook -i ansible/inventories/home/hosts.ini ansible/playbooks/setup-media-stack-volumes.yml

# Volumes n8n
ansible-playbook -i ansible/inventories/home/hosts.ini ansible/playbooks/setup-n8n-volumes.yml

# Volumes monitoramento (gera prometheus.yml, Loki e Promtail a partir de templates)
ansible-playbook -i ansible/inventories/home/hosts.ini ansible/playbooks/setup-monitoring-stack-volumes.yml
```

O playbook de monitoramento renderiza as configurações a partir de `ansible/templates/prometheus.yml.j2`, `ansible/templates/loki-local-config.yaml.j2` e `ansible/templates/promtail-config.yml.j2`, e o `.env` da stack a partir de `ansible/templates/portainer_stack_env.j2`.

## Ativando/Desativando Serviços

Para desativar um serviço que não usa, adicione `enabled: false` nas labels do Traefik do serviço no compose, ou comente o bloco inteiro do serviço.

**Exemplo: remover Plex** — o compose consolidado já inclui apenas Jellyfin. Se preferir Plex, substitua o bloco `jellyfin` por `plex` (veja a seção de referência rápida para configurações).

## Notas por Serviço

- **Nextcloud**: Requer Postgres e Redis. Dados em NFS. `trusted_domains` configurado automaticamente.
- **Jellyfin**: Hardware transcoding via `/dev/dri` (iGPU). Se usar CPU, remova o device.
- **Sonarr/Radarr**: Dependem do qBittorrent para downloads. Configure o client de torrent no Sonarr/Radarr após o deploy.
- **Grafana**: Login inicial `admin` / senha definida no `.env`. Adicione o datasource Prometheus apontando para `http://prometheus:9090`.
- **Loki/Promtail**: Coletam logs de containers para visualizar no Grafana. O Loki publica a porta 3100 no IP da `core-services-vm` (`${CORE_SERVICES_VM_IP_VAR}:3100`) para receber os logs do `promtail_ai` da `ai-desktop-vm`; ele não tem autenticação, então a porta só deve ser alcançável pela LAN (não crie rota no Traefik nem no túnel para ela). Portas publicadas pelo Docker não passam pelo UFW da VM, então a proteção é a própria LAN.
- **n8n**: Webhook URL configurado automaticamente para `https://n8n.seudominio.com/`.
- **Home Assistant**: `devices` para USB (Zigbee/Zwave). Ajuste `/dev/ttyUSB0` para seu dispositivo.