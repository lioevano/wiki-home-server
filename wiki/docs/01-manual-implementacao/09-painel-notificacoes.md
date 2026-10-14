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

## Passos manuais

## Teste de ponta a ponta
