# Design: painel (Homepage) e notificações (n8n → Telegram)

- **Data:** 2026-10-14
- **Autor:** Léo Ivan (com Claude)
- **Status:** aguardando revisão
- **Caminho:** arquitetural — sub-projeto **B**. Usa o ferramental do sub-projeto A (catálogo, índice de integrações, skills `add-app`/`add-integration`/`audit-integrations`).
- **Depende de:** `2026-10-12-catalogo-integracoes-agentes-design.md`.

## 1. Objetivo

1. **Notificações no Telegram** para quatro classes de evento: serviço/VM fora do ar; recursos no limite; atualizações, backups e certificados; eventos das aplicações.
2. **Painel** (Homepage) com atalho, status e widgets de dados de cada aplicação.
3. Ambos como **integrações do índice** (`notificacoes` e `painel`), ligadas a cada aplicação do catálogo pelo fluxo `add-integration`, declarativas e versionadas, seguindo wiki-first.

### Critérios de pronto

- Catálogo com as apps novas (`homepage`, `docker-socket-proxy`, `blackbox-exporter`, `diun`) e `n8n` com `Provê = notificacoes`, `homepage` com `Provê = painel`.
- Índice com as seções `notificacoes` (regras `NTF`) e `painel` (regras `PNL`) no formato fixo.
- `audit-integrations` com `integração=notificacoes` e `integração=painel`: nenhum `❌`/`⚠️` (só `✋` para passos manuais documentados).
- Arquivos de provisioning do Grafana (alertas), `services.yaml.j2` da Homepage e workflow do n8n gerados pelo Ansible, com YAML/JSON válidos.
- Página `01-manual-implementacao/09-painel-notificacoes.md` com deploy, passos manuais e teste de ponta a ponta.
- `dev.py test`, `check` (só o aviso `REF-PENDING` do vault), `build` e `lint` passam.

## 2. Decisões

| # | Decisão | Escolha |
|---|---|---|
| B1 | Canal | Telegram (bot próprio); n8n é o único ponto de saída, exceto o alerta "n8n fora do ar". |
| B2 | Motor de alertas | **Grafana Alerting** (já existe; alerta sobre Prometheus e Loki); regras provisionadas por arquivo. |
| B3 | Disponibilidade | `blackbox-exporter` (HTTP de cada app + validade de certificado) raspado pelo Prometheus. |
| B4 | Atualizações | Diun, uma instância por VM (`diun` na `core-services-vm`, `diun_ai` na `ai-desktop-vm`), observando todos os containers. |
| B5 | Painel | Homepage com **um único `services.yaml` gerado pelo Ansible** a partir de template (sem labels nos composes); chaves de widget via `{{HOMEPAGE_VAR_*}}` no ambiente da Homepage. |
| B6 | Estado de containers no painel | `docker-socket-proxy` só leitura na `core-services-vm` (rede interna, sem porta publicada); apps da VM de IA só com `siteMonitor`. |
| B7 | Entrada de eventos | Um webhook `POST /webhook/notificar` no n8n, autenticado por token em cabeçalho; caminho `^/webhook/` com `bypass` no Authelia. |
| B8 | Workflow | Um workflow `notificar` versionado como template JSON, importado pelo playbook do n8n; segredos lidos de variáveis de ambiente do n8n. |

## 3. Aplicações novas (catálogo)

| Aplicação | Categoria | Stack / VM | Serviços | Exposição | Subdomínio | Dados | Métricas | Provê |
|---|---|---|---|---|---|---|---|---|
| `homepage` | infra | apps / core-services-vm | `homepage` | protegida | `home` | nfs (config gerada) | não | `painel` |
| `docker-socket-proxy` | infra | apps / core-services-vm | `docker-socket-proxy` | interna | — | nenhum | não | — |
| `blackbox-exporter` | monitoramento | apps / core-services-vm | `blackbox-exporter` | interna | — | nfs (config) | sim | — |
| `diun` | monitoramento | apps / core-services-vm; ai / ai-desktop-vm | `diun`, `diun_ai` | interna | — | nfs (db) | não | — |

`n8n` passa a `Provê = notificacoes`. Os novos serviços entram no playbook de monitoramento (`setup-monitoring-stack-volumes.yml`: Homepage, blackbox, Diun, alertas do Grafana) e no da IA (`diun_ai`); o workflow do n8n no `setup-n8n-volumes.yml`. Cada app entra pela skill `add-app` (compose, volumes, variáveis, página, catálogo).

- **Homepage:** `HOMEPAGE_ALLOWED_HOSTS=home.<domínio>`; config (`settings.yaml`, `services.yaml`, `docker.yaml`) em NFS, gerada por template; `docker.yaml` aponta para `docker-socket-proxy:2375`.
- **docker-socket-proxy:** `CONTAINERS=1`, `POST=0`, demais APIs negadas; só na rede `internal_services`.
- **blackbox-exporter:** módulo `http_2xx` (aceita 2xx/3xx e 401 de apps atrás do Authelia) e probe de TLS; job `blackbox_http` no `prometheus.yml.j2` com a lista de alvos.
- **Diun:** provider Docker com `watchByDefault: true`, notificador webhook para o n8n; agenda diária.

## 4. Integração `notificacoes` (regras `NTF`)

| Campo | Valor |
|---|---|
| Provedor | `n8n` (workflow `notificar`); coletores: Grafana Alerting, `blackbox-exporter`, `diun` |
| Aplica-se a | todas, exceto `-notificacoes` em Ajustes |
| Arquivos | `ansible/templates/prometheus.yml.j2` (alvos), `grafana/provisioning/alerting/*.yml` (gerados), template do workflow n8n, compose do consumidor (webhook nativo, se houver) |
| Páginas | página da app; `01-manual-implementacao/09-painel-notificacoes.md` |
| Manual | webhook configurado na interface da app (NTF-3), quando a app não aceita configuração por arquivo/variável |

**Regras**
- **NTF-1** — app com interface HTTP tem alvo no job `blackbox_http` (URL pública `https://<Subdomínio>.<domínio>` se `publica`/`protegida`; URL interna `http://<serviço>:<porta>` se `interna`). Uma regra genérica do Grafana ("fora do ar há 3 min") cobre todos os alvos.
- **NTF-2** — existe `diun` na mesma VM da app (catálogo: Stack/VM do `diun` × da app).
- **NTF-3** — app com webhook nativo (lista no índice: `radarr`, `sonarr`, `homeassistant`, `jellyfin` via plugin) tem na sua página o passo "apontar webhook para o n8n"; senão `✋`.
- **NTF-4 (sobra)** — nenhum alvo do blackbox nem regra de alerta por app sem aplicação correspondente no catálogo.

**Alertas globais** (no provedor, arquivo único de limites): disco > 85%; RAM > 90% por 10 min; CPU > 90% por 15 min; pool ZFS degradado (métrica `node_zfs_zpool_state` do node_exporter do host — validar na implementação; alternativa: textfile collector); host/VM sem node_exporter; certificado < 14 dias (`probe_ssl_earliest_cert_expiry`); > 5 logins falhos no Authelia em 10 min (Loki).

**Backups e Proxmox:** um script `scripts/notify.sh` (POST no webhook com token) é chamado pelos exemplos de backup/snapshot da wiki ao terminar (sucesso ou falha); falha no envio só registra em log. Backups do Proxmox (vzdump) usam o destino de notificação *webhook* nativo do PVE → passo manual documentado.

## 5. Integração `painel` (regras `PNL`)

| Campo | Valor |
|---|---|
| Provedor | `homepage` |
| Aplica-se a | Exposição `publica`/`protegida`; `interna` só com `+painel` |
| Arquivos | `ansible/templates/homepage/services.yaml.j2`; `.env` da Homepage (chaves) |
| Páginas | página da app; `01-manual-implementacao/09-painel-notificacoes.md` |
| Manual | gerar a chave de API na interface da app e gravá-la no vault (PNL-2) |

**Regras**
- **PNL-1** — a app tem entrada no `services.yaml.j2`, no grupo da sua Categoria, com `href` `https://<Subdomínio>.<domínio>` (ou URL da LAN para `+painel`), `siteMonitor`, e `server`/`container` quando roda na `core-services-vm`.
- **PNL-2** — app com widget oficial da Homepage (lista no índice: `jellyfin`, `radarr`, `sonarr`, `qbittorrent`, `nextcloud`, `homeassistant`, `grafana`, `prometheus`, `portainer`, `traefik`) tem `widget` na entrada, com chave `{{HOMEPAGE_VAR_<APP>_KEY}}`; a variável vem do vault (`homepage_widget_keys.<app>`) pelo playbook (segue "Origem dos valores").
- **PNL-3 (sobra)** — nenhuma entrada no template sem aplicação correspondente.

## 6. Fluxo do workflow `notificar`

1. **Webhook** `POST /webhook/notificar`, *Header Auth* com `notificacoes_webhook_token`.
2. **Origem** (Switch): Grafana (payload de alerta agrupado, `status` firing/resolved), Diun (imagem/tag), Arr/Home Assistant (eventos), genérico (`{titulo, mensagem, gravidade, app}` — usado pelo `notify.sh`).
3. **Mensagem**: emoji por gravidade (🔴 crítico, 🟠 aviso, 🟢 resolvido/ok, ℹ️ info), título, app, link.
4. **Telegram** `sendMessage` via HTTP Request com `$env.TELEGRAM_BOT_TOKEN` e `$env.TELEGRAM_CHAT_ID`.

Sem estado no n8n: agrupamento e "resolvido" vêm do Grafana.

## 7. Segredos e variáveis

Chaves novas no vault (placeholders no `vault.yml.example`): `telegram_bot_token`, `telegram_chat_id`, `notificacoes_webhook_token`, `homepage_widget_keys.<app>`. Emitidas pelos playbooks no `.env` das stacks (`0600`), seguindo "Origem dos valores". O Grafana recebe token e chat ID para o ponto de contato direto (B1).

## 8. Falhas

- **n8n fora do ar:** a regra de disponibilidade do `n8n` usa uma rota própria para o ponto de contato **Telegram nativo do Grafana**.
- Grafana e Diun reenviam webhooks com falha; `notify.sh` tenta uma vez e registra em log, sem afetar o backup.
- Chave de widget vazia: widget mostra erro; atalho e status continuam.

## 9. Segurança

Token no webhook; `bypass` do Authelia restrito a `n8n.<domínio>` + `^/webhook/`; socket proxy só leitura e sem porta publicada; Homepage `protegida`; `.env` com segredos `0600`; nenhum segredo no JSON do workflow nem em labels.

## 10. Verificação

- `dev.py check/sync/lint/build/test`; parse dos YAML de provisioning e do JSON do workflow.
- `audit-integrations` para `notificacoes` e `painel` até não restar `❌`/`⚠️`.
- Teste de ponta a ponta documentado na página 09: `curl` com token no webhook → mensagem no Telegram; "Test" do ponto de contato no Grafana.

## 11. Fora de escopo

Dashboards do Grafana; alertas específicos por app além de disponibilidade; comandos recebidos pelo Telegram (silenciar etc.); unificação dos `.env` da stack `apps` (reestruturação).

## 12. Riscos

- Payloads de Grafana/Diun/Arr mudam entre versões → o Switch do workflow trata campos ausentes como genérico.
- Métrica de ZFS pode não existir na versão do node_exporter → alternativa textfile collector.
- Alertas ruidosos no início → limites num único arquivo para ajuste.
