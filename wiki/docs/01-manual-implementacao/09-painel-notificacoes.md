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

## Passos manuais

## Teste de ponta a ponta
