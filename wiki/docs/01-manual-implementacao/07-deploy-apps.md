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
6. Em **Env**, carregue o arquivo `apps.env` gerado pelo Ansible (`setup-productivity-automation-volumes.yml`, `setup-media-stack-volumes.yml`, `setup-n8n-volumes.yml`)
7. Clique em **Deploy the stack**

## Preparação dos Volumes

Os volumes são criados pelos playbooks Ansible:

```bash
# Volumes Nextcloud + automação
ansible-playbook -i ansible/inventories/home/hosts.ini ansible/playbooks/setup-productivity-automation-volumes.yml

# Volumes mídia
ansible-playbook -i ansible/inventories/home/hosts.ini ansible/playbooks/setup-media-stack-volumes.yml

# Volumes n8n
ansible-playbook -i ansible/inventories/home/hosts.ini ansible/playbooks/setup-n8n-volumes.yml
```

## Ativando/Desativando Serviços

Para desativar um serviço que não usa, adicione `enabled: false` nas labels do Traefik do serviço no compose, ou comente o bloco inteiro do serviço.

**Exemplo: remover Plex** — o compose consolidado já inclui apenas Jellyfin. Se preferir Plex, substitua o bloco `jellyfin` por `plex` (veja a seção de referência rápida para configurações).

## Notas por Serviço

- **Nextcloud**: Requer Postgres e Redis. Dados em NFS. `trusted_domains` configurado automaticamente.
- **Jellyfin**: Hardware transcoding via `/dev/dri` (iGPU). Se usar CPU, remova o device.
- **Sonarr/Radarr**: Dependem do qBittorrent para downloads. Configure o client de torrent no Sonarr/Radarr após o deploy.
- **Grafana**: Login inicial `admin` / senha definida no `.env`. Adicione o datasource Prometheus apontando para `http://prometheus:9090`.
- **Loki/Promtail**: Coletam logs de containers para visualizar no Grafana.
- **n8n**: Webhook URL configurado automaticamente para `https://n8n.seudominio.com/`.
- **Home Assistant**: `devices` para USB (Zigbee/Zwave). Ajuste `/dev/ttyUSB0` para seu dispositivo.