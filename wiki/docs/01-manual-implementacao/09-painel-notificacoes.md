---
description: "Painel Homepage e notificações no Telegram via n8n: Grafana Alerting, blackbox-exporter, Diun, workflow notificar, passos manuais e teste de ponta a ponta."
---

# Seção 9: Painel e Notificações

Duas integrações transversais do [Índice de Integrações](../02-visao-geral-arquitetura/10-indice-integracoes.md): `notificacoes` (n8n → Telegram) e `painel` (Homepage). As aplicações envolvidas estão no [Catálogo](../02-visao-geral-arquitetura/09-catalogo-aplicacoes.md): `homepage`, `docker-socket-proxy`, `blackbox-exporter`, `diun` e o `n8n` como provedor das notificações.

## Visão geral

```
Prometheus ── blackbox (no ar? certificado?) ─┐
Prometheus ── node_exporter (disco/RAM/CPU/ZFS)┼─► Grafana Alerting ─┐
Loki ── logs (login falho no Authelia) ───────┘                     │
Diun (core e IA) ── imagem nova ────────────────────────────────────┤
scripts/notify.sh (backups) e Proxmox ──────────────────────────────┼─► n8n /webhook/notificar ─► Telegram
Radarr, Sonarr, Home Assistant, Jellyfin ── webhook da app ─────────┘
```

O alerta "n8n fora do ar" vai direto do Grafana ao Telegram, sem passar pelo n8n.

## Deploy

### Disponibilidade (blackbox-exporter)

O serviço `blackbox-exporter` (stack `apps`, rede `internal_services`, sem porta publicada) testa a URL de cada aplicação. A configuração vem de `ansible/templates/blackbox.yml.j2`, gerada pelo `ansible/playbooks/setup-monitoring-stack-volumes.yml` em `<NFS>/blackbox/config/blackbox.yml`. O módulo `http_2xx` aceita 200, 301, 302, 401 e 403: uma aplicação protegida responde com o redirecionamento para o Authelia, e isso conta como "no ar".

Os alvos ficam no job `blackbox_http` de `ansible/templates/prometheus.yml.j2`, um por aplicação, com `labels: {app: <id do catálogo>}` (regra NTF-1). Para conferir no Prometheus: `probe_success` (1 = no ar) e `probe_ssl_earliest_cert_expiry` (validade do certificado).

### Alertas (Grafana Alerting)

O `setup-monitoring-stack-volumes.yml` gera em `<NFS>/grafana/provisioning/alerting/` três arquivos, a partir de `ansible/templates/grafana/alerting/`:

| Arquivo | Conteúdo |
|---|---|
| `rules.yml` | 9 regras na pasta **Homeserver**: `servico-fora-do-ar`, `n8n-fora-do-ar`, `certificado-vencendo`, `disco-cheio`, `ram-alta`, `cpu-alta`, `host-sem-resposta`, `zfs-degradado`, `authelia-logins-falhos` |
| `contact-points.yml` | `n8n` (webhook interno com `Authorization: Bearer`) e `telegram-direto` (bot do Telegram) |
| `policies.yml` | tudo vai para `n8n`, agrupado por `alertname` e `app`; só `n8n-fora-do-ar` vai para `telegram-direto` |

**Limites** (disco 85%, RAM 90% por 10 min, CPU 90% por 15 min, fora do ar há 3 min, certificado com menos de 14 dias, mais de 5 logins falhos em 10 min) ficam no topo de `ansible/templates/grafana/alerting/rules.yml.j2`. Regras sem dados ficam em `OK` (não disparam).

Os segredos não ficam nos arquivos: o Grafana recebe `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` e `NOTIFICACOES_WEBHOOK_TOKEN` pelo `monitoring.env` e o provisioning os interpola. Por isso as anotações usam `$$labels` (escape de `$`).

!!! warning "Pool ZFS"
    A regra `zfs-degradado` usa a métrica `node_zfs_zpool_state` do node_exporter do host. Confira se ela existe: `curl -s http://<proxmox_host_ip_var>:9100/metrics | grep node_zfs_zpool_state`. Se não existir, a regra fica sem dados (não dispara); a alternativa é publicar o estado do pool pelo *textfile collector* do node_exporter.

### Workflow `notificar` (n8n)

O workflow fica no repositório como arquivo estático, `ansible/files/n8n/notificar.json` (id `HsNotificar00001`), e o `ansible/playbooks/setup-n8n-volumes.yml` o copia para `<NFS>/n8n/config/workflows/notificar.json` (dentro do container: `/home/node/.n8n/workflows/notificar.json`). Nós:

1. **Webhook** — `POST /webhook/notificar`.
2. **Autorizado?** — confere `Authorization: Bearer <NOTIFICACOES_WEBHOOK_TOKEN>`; sem o token certo responde **401** e não envia nada.
3. **Formatar** — reconhece Grafana (lista `alerts`), Diun (`diun_version`), Radarr/Sonarr (`eventType`) ou genérico (`titulo`, `mensagem`, `gravidade`, `app`) e monta a mensagem: 🔴 crítico, 🟠 aviso, 🟢 resolvido/ok, ℹ️ informação. Payload desconhecido vira notificação genérica.
4. **Telegram** — `sendMessage` com `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`, lidos do ambiente do n8n (`N8N_BLOCK_ENV_ACCESS_IN_NODE=false`).

O Authelia libera só `n8n.<domínio>/webhook/…` (regra `bypass` com `resources`, em `ansible/roles/infra/authelia-config/templates/configuration.yml.j2`); a interface do n8n continua protegida.

### Atualizações (Diun)

Um Diun por VM, observando **todos** os containers (`DIUN_PROVIDERS_DOCKER_WATCHBYDEFAULT=true`), uma vez por dia às 9h:

| Serviço | Stack / VM | Webhook |
|---|---|---|
| `diun` | `apps` / `core-services-vm` | `http://n8n:5678/webhook/notificar` (rede `proxy`) |
| `diun_ai` | `ai` / `ai-desktop-vm` | `https://n8n.<domínio>/webhook/notificar` |

Ambos enviam `Authorization: Bearer ${NOTIFICACOES_WEBHOOK_TOKEN}`; o banco do Diun fica em `<NFS>/diun/data` e `<NFS>/diun-ai/data` (variáveis `MONITORING_DIUN_DATA_PATH` e `AI_STACK_DIUN_DATA_PATH`).

### Painel (Homepage)

A Homepage (`https://home.<domínio>`, protegida pelo Authelia) roda na stack `apps` e lê três arquivos gerados pelo `setup-monitoring-stack-volumes.yml` em `<NFS>/homepage/config/`, a partir de `ansible/templates/homepage/`:

| Arquivo | Conteúdo |
|---|---|
| `settings.yaml` | título, idioma e tema |
| `docker.yaml` | `core` → `docker-socket-proxy:2375` (estado dos containers da `core-services-vm`) |
| `services.yaml` | uma entrada por aplicação `publica`/`protegida` do catálogo (regra PNL-1), agrupada pela Categoria, com atalho, `siteMonitor` e widget quando houver (PNL-2) |

O `docker-socket-proxy` dá à Homepage acesso **só de leitura** à lista de containers (`CONTAINERS=1`, `POST=0`), sem porta publicada. As aplicações da `ai-desktop-vm` mostram só o `siteMonitor`.

As credenciais dos widgets não ficam no `services.yaml`: lá aparecem só os placeholders `HOMEPAGE_VAR_*` (entre chaves duplas), que a Homepage substitui pelo seu ambiente (`monitoring.env`, gerado do vault). O Traefik fica sem widget: a API dele só existe atrás do Authelia.

### Backups e Proxmox

Scripts (backups, snapshots, rotinas no host) avisam pelo `scripts/notify.sh`, que faz `POST` do formato genérico (`gravidade`, `titulo`, `mensagem`, `app`) no webhook. Ele nunca interrompe quem o chama: se o envio falhar, só escreve em stderr. Os exemplos de [backup](../04-manutencao-recuperacao/02-backup-restore-estrategia.md) chamam o script ao terminar, a partir de uma cópia em `/opt/homeserver/scripts/notify.sh` no host.

```bash title="scripts/notify.sh"
#!/bin/bash
# scripts/notify.sh — envia uma notificação ao webhook do n8n (integração notificacoes).
# Uso: notify.sh <gravidade> <titulo> <mensagem> [app]
#   gravidade: critical | warning | ok | info
# Configuração (variáveis de ambiente ou /etc/default/homeserver-notify, modo 600):
#   NOTIFICACOES_WEBHOOK_URL   ex.: https://n8n.seudominio.com/webhook/notificar
#   NOTIFICACOES_WEBHOOK_TOKEN vault: notificacoes_webhook_token
# Nunca falha o chamador: erro de envio só vai para stderr e o script sai com 0.

if [ -r /etc/default/homeserver-notify ]; then
  # shellcheck disable=SC1091
  . /etc/default/homeserver-notify
fi

json_escape() {
  local s=$1
  s=${s//\\/\\\\}
  s=${s//\"/\\\"}
  s=${s//$'\n'/\\n}
  s=${s//$'\r'/}
  s=${s//$'\t'/\\t}
  printf '%s' "$s"
}

gravidade=${1:-info}
titulo=${2:-Notificação}
mensagem=${3:-}
app=${4:-}

if [ -z "${NOTIFICACOES_WEBHOOK_URL:-}" ] || [ -z "${NOTIFICACOES_WEBHOOK_TOKEN:-}" ]; then
  echo "notify.sh: NOTIFICACOES_WEBHOOK_URL/NOTIFICACOES_WEBHOOK_TOKEN não definidos; notificação não enviada" >&2
  exit 0
fi

body="{\"gravidade\":\"$(json_escape "$gravidade")\",\"titulo\":\"$(json_escape "$titulo")\",\"mensagem\":\"$(json_escape "$mensagem")\",\"app\":\"$(json_escape "$app")\"}"

if ! curl -fsS --max-time 10 -X POST "$NOTIFICACOES_WEBHOOK_URL" \
  -H "Authorization: Bearer ${NOTIFICACOES_WEBHOOK_TOKEN}" \
  -H "Content-Type: application/json" \
  --data-binary "$body" -o /dev/null; then
  echo "notify.sh: falha ao enviar notificação para ${NOTIFICACOES_WEBHOOK_URL}" >&2
fi
exit 0
```

Para não repetir as variáveis em cada cron, grave-as em `/etc/default/homeserver-notify` (no host Proxmox e nas VMs que rodam scripts), com `chmod 600`:

```bash
NOTIFICACOES_WEBHOOK_URL=https://n8n.seudominio.com/webhook/notificar
NOTIFICACOES_WEBHOOK_TOKEN=<notificacoes_webhook_token do vault>
```

**Backups do Proxmox (vzdump):** em **Datacenter → Notifications → Add → Webhook** (PVE 8.3+), aponte para a mesma URL, método `POST`, cabeçalho `Authorization: Bearer <token>` e corpo JSON `{"titulo": "{{ title }}", "mensagem": "{{ message }}", "gravidade": "{{ severity }}", "app": "proxmox"}`; associe o destino ao *matcher* dos jobs de backup. Confira na documentação do PVE da sua versão a sintaxe de escape das variáveis de template no corpo JSON.

## Passos manuais

### Bot do Telegram e importação do workflow

1. No Telegram, fale com **@BotFather** → `/newbot` → guarde o token em `telegram_bot_token` no vault.
2. Mande qualquer mensagem ao bot e abra `https://api.telegram.org/bot<TOKEN>/getUpdates`: o `chat.id` vai em `telegram_chat_id`.
3. Gere o token do webhook (`openssl rand -hex 32`) em `notificacoes_webhook_token`.
4. Rode os playbooks de n8n e monitoramento e atualize a stack `apps` no Portainer (página 07).
5. Importe e ative o workflow (na `core-services-vm`):
   ```bash
   sudo docker exec n8n_app n8n import:workflow --input=/home/node/.n8n/workflows/notificar.json
   sudo docker exec n8n_app n8n update:workflow --id=HsNotificar00001 --active=true
   sudo docker restart n8n_app
   ```
   Ao mudar o arquivo no repositório, repita os três comandos.

### Chaves de API dos widgets

Depois do primeiro acesso a cada aplicação, gere a credencial e grave-a no vault (`ansible-vault edit …/vault.yml`, chave `homepage_widget_keys`); depois rode o `setup-monitoring-stack-volumes.yml` e atualize a stack `apps`:

| Aplicação | Onde gerar | Chave no vault |
|---|---|---|
| Jellyfin | Painel → Chaves de API | `homepage_widget_keys.jellyfin` |
| Radarr / Sonarr | Settings → General → API Key | `homepage_widget_keys.radarr` / `.sonarr` |
| Nextcloud | app *serverinfo*: `occ config:app:set serverinfo token --value <token>` | `homepage_widget_keys.nextcloud` |
| Home Assistant | Perfil → Tokens de acesso de longa duração | `homepage_widget_keys.homeassistant` |
| Portainer | Conta → Access tokens | `homepage_widget_keys.portainer` |
| qBittorrent | usuário e senha da Web UI | `homepage_widget_keys.qbittorrent_user` / `_password` |
| Grafana | usa `admin` + `grafana_admin_initial_password` | — |

Sem a chave, o widget mostra erro; atalho e status continuam funcionando.

## Teste de ponta a ponta

```bash
# deve chegar uma mensagem no Telegram (resposta 200)
curl -s -o /dev/null -w '%{http_code}\n' -X POST "https://n8n.<domínio>/webhook/notificar" \
  -H "Authorization: Bearer <notificacoes_webhook_token>" -H "Content-Type: application/json" \
  -d '{"titulo":"Teste","mensagem":"Webhook funcionando","gravidade":"ok"}'

# sem o token: 401 e nenhuma mensagem
curl -s -o /dev/null -w '%{http_code}\n' -X POST "https://n8n.<domínio>/webhook/notificar" -d '{}'
```

No Grafana: **Alerting → Contact points → n8n → Test** (e o mesmo em `telegram-direto`).
