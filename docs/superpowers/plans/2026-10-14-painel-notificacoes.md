# Painel (Homepage) e notificações (n8n → Telegram) — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Notificações no Telegram (via n8n) para disponibilidade, recursos, atualizações/backups/certificados e eventos das apps, e um painel Homepage com atalhos, status e widgets — ambos como integrações do índice.

**Architecture:** Grafana Alerting (Prometheus + Loki + blackbox-exporter) e Diun enviam a um único webhook do n8n, que formata e envia ao Telegram; o alerta "n8n fora do ar" vai direto do Grafana ao Telegram. A Homepage lê um `services.yaml` gerado pelo Ansible e o estado dos containers por um `docker-socket-proxy` só leitura. Tudo pelo fluxo wiki-first, com as skills `add-app`, `add-integration` e `audit-integrations`.

**Tech Stack:** Ansible (Jinja2), Docker Compose (Portainer), Grafana provisioning, Prometheus + blackbox-exporter, Diun, n8n, Homepage, MkDocs.

**Spec:** `docs/superpowers/specs/2026-10-14-painel-notificacoes-design.md`

## Global Constraints

- Wiki-first: blocos literais mudam na wiki → `python tools/dev.py check` → `sync` (dry-run) → `sync --yes`; arquivos estruturais (composes, playbooks e templates sem bloco literal) mudam direto e são citados com caminho completo na página.
- Ambiente: `export HOMESERVER_VENV=$HOME/.venvs/homeserver` antes de `python3 tools/dev.py ...`. `check` aceita só o aviso `REF-PENDING` do `vault.yml`.
- Nunca escrever valor real de segredo; segredos só no vault → `.env` da stack (`mode: '0600'`), seguindo "Origem dos valores" do índice. Nada de segredo em labels, JSON do workflow ou arquivos de provisioning (usar variáveis de ambiente).
- Templates Jinja que precisam emitir `{{...}}` literal (Homepage `{{HOMEPAGE_VAR_*}}`, expressões do n8n) usam `{% raw %}…{% endraw %}`; o workflow do n8n é arquivo **estático** (`ansible/files/n8n/notificar.json`, copiado, não templateado).
- Webhook: `POST /webhook/notificar`; cabeçalho `Authorization: Bearer <NOTIFICACOES_WEBHOOK_TOKEN>`. URL interna `http://n8n:5678/webhook/notificar` (stack `apps`); externa `https://n8n.<domínio>/webhook/notificar`.
- Variáveis novas (nome exato no compose e no `.env.template`): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `NOTIFICACOES_WEBHOOK_TOKEN`, `HOMEPAGE_VAR_JELLYFIN_KEY`, `HOMEPAGE_VAR_RADARR_KEY`, `HOMEPAGE_VAR_SONARR_KEY`, `HOMEPAGE_VAR_NEXTCLOUD_KEY`, `HOMEPAGE_VAR_HOMEASSISTANT_KEY`, `HOMEPAGE_VAR_PORTAINER_KEY`, `HOMEPAGE_VAR_QBITTORRENT_USER`, `HOMEPAGE_VAR_QBITTORRENT_PASSWORD`, `HOMEPAGE_VAR_GRAFANA_PASSWORD`, `MONITORING_BLACKBOX_CONFIG_PATH`, `MONITORING_HOMEPAGE_CONFIG_PATH`, `MONITORING_DIUN_DATA_PATH`, `AI_STACK_DIUN_DATA_PATH`.
- Chaves novas do vault: `telegram_bot_token`, `telegram_chat_id`, `notificacoes_webhook_token`, `homepage_widget_keys: {jellyfin, radarr, sonarr, nextcloud, homeassistant, portainer, qbittorrent_user, qbittorrent_password}` (Grafana usa `grafana_admin_initial_password`, já existente).
- Limites (arquivo único `ansible/templates/grafana/alerting/rules.yml.j2`, no topo como `{% set %}`): disco 85%; RAM 90% por 10m; CPU 90% por 15m; fora do ar 3m; certificado 14 dias; 5 logins falhos em 10m.
- **Desvio da spec (registrado):** o widget do `traefik` sai da lista de PNL-2 — a API do Traefik só existe atrás do router com Authelia (`api.insecure` desligado), então a Homepage não a alcança; o Traefik fica com atalho e status.
- **Verificação de template** (usada nas tasks; `<arquivo>` e `<vars>` mudam): `"$HOMESERVER_VENV/bin/python" -c "import jinja2,yaml,json,sys; t=jinja2.Environment(undefined=jinja2.StrictUndefined,loader=jinja2.FileSystemLoader('server/ansible/templates')).get_template('<arquivo>'); out=t.render(<vars>); (json.loads if '<arquivo>'.endswith('.json') else yaml.safe_load)(out); print('ok')"` → `ok`.
- Commits com o trailer da sessão (`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` e `Claude-Session: https://claude.ai/code/session_011krkX9xaiTppBasvKKgK5w`); sem `git push`.

## Review Focus

1. **App protegida atrás do Authelia aparecendo como "fora do ar":** a probe segue o redirect para `auth.<domínio>`; o módulo `http_2xx` deve aceitar 200/301/302/401/403 → Task 2 verifica o módulo.
2. **`{{HOMEPAGE_VAR_*}}` engolido pelo Jinja:** o `services.yaml` renderizado deve conter o texto literal `{{HOMEPAGE_VAR_JELLYFIN_KEY}}` → Task 6 verifica com `grep`.
3. **Webhook sem token ou com token errado:** o n8n deve responder 401 e não enviar nada → Task 4 testa a função de autorização e documenta o `curl` negativo na página 09.
4. **Payload desconhecido no webhook** (versão nova do Grafana/Diun/Arr): a mensagem cai no formato genérico em vez de quebrar → Task 4 testa o formatador com payload vazio e com campos ausentes.
5. **n8n fora do ar silencia tudo:** a regra `n8n-fora-do-ar` tem rota direta para o contato Telegram do Grafana → Task 3 verifica a política.

---

### Task 1: Contratos no índice e no catálogo

**Files:**
- Modify: `wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md` (novas seções `notificacoes` e `painel`)
- Modify: `wiki/docs/02-visao-geral-arquitetura/09-catalogo-aplicacoes.md`
- Create: `wiki/docs/01-manual-implementacao/09-painel-notificacoes.md` (esqueleto: Visão geral, Deploy, Passos manuais, Teste de ponta a ponta)
- Modify: `wiki/mkdocs.yml` (nav, após "Stack de IA")

**Interfaces:**
- Produces: ids `notificacoes` (regras NTF-1…NTF-4) e `painel` (PNL-1…PNL-3); linhas do catálogo `homepage`, `docker-socket-proxy`, `blackbox-exporter`, `diun`; `n8n` com `Provê = notificacoes`.

- [ ] **Step 1:** Escrever as duas seções no formato fixo, com o texto da spec §4/§5 e estas precisões: NTF-1 aplica-se a Exposição `publica`/`protegida` (URL pública) e às `interna` listadas — `litellm` (`http://<ai_desktop_vm_ip_var>:4000/health/liveliness`) e `loki` (`http://loki:3100/ready`); demais `interna` → `—`. Lista NTF-3: `radarr`, `sonarr`, `homeassistant`, `jellyfin`. Lista PNL-2: `jellyfin`, `radarr`, `sonarr`, `qbittorrent`, `nextcloud`, `homeassistant`, `grafana`, `prometheus`, `portainer`. Nota na seção `notificacoes`: a regra `bypass` do Authelia para `n8n.{{ base_domain }}` com `resources: ["^/webhook/.*$"]` é esperada (não é AUT-3/AUT-4). "Ao remover o provedor": desativar coletores e remover `alerting/`, Diun e o webhook.
- [ ] **Step 2:** Catálogo: as 4 linhas da spec §3 (Página = `../01-manual-implementacao/09-painel-notificacoes.md`); `n8n` → `Provê = notificacoes`; `homepage` → `Provê = painel`.
- [ ] **Step 3:** Página 09 com front-matter `description` e as quatro seções vazias de conteúdo técnico ainda (preenchidas nas tasks 2–7); nav no `mkdocs.yml`.
- [ ] **Step 4:** `python3 tools/dev.py check` → 0 erros; commit da página antes do build (o plugin git-revision avisa em página não commitada); `python3 tools/dev.py build` → 0 WARNING.
- [ ] **Step 5:** Commit `docs: contratos das integrações notificacoes e painel`.

### Task 2: blackbox-exporter e alvos de disponibilidade

**Files:**
- Modify: `server/docker/stacks/apps/docker-compose.yml` (serviço `blackbox-exporter`, imagem `prom/blackbox-exporter:latest`, rede `internal_services`, volume `${MONITORING_BLACKBOX_CONFIG_PATH}/blackbox.yml:/etc/blackbox_exporter/config.yml:ro`)
- Create: `server/ansible/templates/blackbox.yml.j2`
- Modify: `server/ansible/templates/prometheus.yml.j2` (job `blackbox_http`)
- Modify: `server/ansible/playbooks/setup-monitoring-stack-volumes.yml` (dir `blackbox/config`, template, `MONITORING_BLACKBOX_CONFIG_PATH`)
- Modify (literal, via wiki): `.env.template` (página 00)
- Modify: página 09 (seção Disponibilidade), página 07 (serviço novo)

**Interfaces:**
- Produces: métricas `probe_success{app="<id>"}` e `probe_ssl_earliest_cert_expiry{app="<id>"}` (label `app` = id do catálogo), consumidas pela Task 3.

- [ ] **Step 1:** `blackbox.yml.j2` com módulo `http_2xx`: `prober: http`, `timeout: 10s`, `http.valid_status_codes: [200, 301, 302, 401, 403]`, `preferred_ip_protocol: ip4`, `follow_redirects: true`.
- [ ] **Step 2:** Job `blackbox_http` (`metrics_path: /probe`, `params.module: [http_2xx]`, relabel `__address__`→`__param_target`, `__param_target`→`instance`, `__address__`=`blackbox-exporter:9115`), um `static_configs` por app com `labels: {app: <id>}`: as 14 apps `publica`/`protegida` (URL `https://<Subdomínio>.{{ base_domain }}`) + `litellm` e `loki` (URLs da Task 1).
- [ ] **Step 3:** Verificação de template de `blackbox.yml.j2` e `prometheus.yml.j2` (vars: `base_domain`, `ai_desktop_vm_ip_var`, `core_services_vm_ip_var`, `groups` com `ai_desktop`) → `ok`; `grep -c "app: " ` no render = 16.
- [ ] **Step 4:** Compose, playbook, `.env.template` (bloco da página 00), páginas 07/09; `check` → só divergências criadas; `sync --yes`; `check` → 0 erros; `lint` → OK.
- [ ] **Step 5:** Commit `feat(monitoramento): blackbox-exporter e alvos de disponibilidade`.

### Task 3: Grafana Alerting (regras, contatos, política)

**Files:**
- Create: `server/ansible/templates/grafana/alerting/rules.yml.j2`, `contact-points.yml.j2`, `policies.yml.j2`
- Modify: `server/ansible/playbooks/setup-monitoring-stack-volumes.yml` (dir `grafana/provisioning/alerting`, render dos 3 arquivos; datasources ganham `uid: prometheus` e `uid: loki`; emitir `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `NOTIFICACOES_WEBHOOK_TOKEN` no `monitoring.env`)
- Modify: `server/docker/stacks/apps/docker-compose.yml` (Grafana recebe as 3 variáveis no `environment`)
- Modify (literal, via wiki): `vault.yml.example` (página 01: `telegram_bot_token`, `telegram_chat_id`, `notificacoes_webhook_token`), `.env.template` (página 00)
- Modify: página 09 (Alertas: lista de regras e onde ajustar limites)

**Interfaces:**
- Consumes: `probe_success{app}`, `probe_ssl_earliest_cert_expiry{app}` (Task 2); `node_*` do node_exporter; Loki `{container_name="authelia"}`.
- Produces: contatos `n8n` (webhook `http://n8n:5678/webhook/notificar`, `authorization_scheme: Bearer`, `authorization_credentials: $NOTIFICACOES_WEBHOOK_TOKEN`) e `telegram-direto` (`bottoken: $TELEGRAM_BOT_TOKEN`, `chatid: $TELEGRAM_CHAT_ID`); política raiz → `n8n` com `group_by: [alertname, app]`, rota `object_matchers: [['alertname','=','n8n-fora-do-ar']]` → `telegram-direto`.

- [ ] **Step 1:** `rules.yml.j2` (`apiVersion: 1`, grupo `homeserver`, `folder: Homeserver`, `interval: 1m`), regras com `uid` fixo, `labels.severity` (`critical`/`warning`) e `annotations.summary`: `servico-fora-do-ar` (`probe_success{app!="n8n"} == 0`, `for: 3m`), `n8n-fora-do-ar` (`probe_success{app="n8n"} == 0`, `for: 3m`), `certificado-vencendo` (`(probe_ssl_earliest_cert_expiry - time())/86400 < 14`), `disco-cheio` (uso > 85% excluindo `tmpfs|overlay`), `ram-alta` (> 90%, `for: 10m`), `cpu-alta` (> 90%, `for: 15m`), `host-sem-resposta` (`up{job=~"node_exporter.*"} == 0`, `for: 3m`), `zfs-degradado` (`node_zfs_zpool_state{state!="online"} > 0`), `authelia-logins-falhos` (Loki: `sum(count_over_time({container_name="authelia"} |= "Unsuccessful" [10m])) > 5`). `noDataState: OK` e `execErrState: Error` em todas (se `node_zfs_zpool_state` não existir no host, a regra fica sem dados em vez de disparar; registrar na página 09 a alternativa textfile collector). Cada regra: dado `A` (consulta instantânea, `relativeTimeRange: {from: 600, to: 0}`) e condição `C` (`__expr__`, `type: threshold`, `> 0` sobre a expressão booleana).
- [ ] **Step 2:** `contact-points.yml.j2` e `policies.yml.j2` conforme Interfaces (valores de segredo como `$VAR`, interpolados pelo Grafana a partir do ambiente).
- [ ] **Step 3:** Verificação de template dos 3 arquivos → `ok`; `grep -c "uid:" ` em `rules` = 9; `grep "n8n-fora-do-ar"` em `policies` → 1 linha.
- [ ] **Step 4:** Playbook, compose, blocos literais (páginas 00/01), página 09; `check`/`sync --yes`/`check` → 0 erros; `lint` → OK.
- [ ] **Step 5:** Commit `feat(alertas): Grafana Alerting com rota direta para o Telegram`.

### Task 4: Workflow `notificar` no n8n e entrada do webhook

**Files:**
- Create: `server/ansible/files/n8n/notificar.json` (estático)
- Modify: `server/ansible/playbooks/setup-n8n-volumes.yml` (copiar para `{{ N8N config }}/workflows/notificar.json`; emitir `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `NOTIFICACOES_WEBHOOK_TOKEN` no `n8n.env`)
- Modify: `server/docker/stacks/apps/docker-compose.yml` (n8n: as 3 variáveis + `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`)
- Modify (literal, via wiki): `configuration.yml.j2` do Authelia (página 05) — regra antes da curinga: `domain: "n8n.{{ base_domain }}"`, `resources: ["^/webhook/.*$"]`, `policy: bypass`
- Modify: página 09 (importação/ativação, teste)

**Interfaces:**
- Consumes: payloads do Grafana (`status`, `alerts[].labels.{alertname,app,severity}`, `alerts[].annotations.summary`), Diun (`diun_version`, `image`, `hostname`, `hub_link`), Arr (`eventType`, `movie.title`/`series.title`), genérico (`titulo`, `mensagem`, `gravidade`, `app`).
- Produces: workflow id `HsNotificar00001`, nós `Webhook` (path `notificar`, `POST`, `responseMode: responseNode`) → `Autorizado?` (IF) → `Formatar` (Code) → `Telegram` (HTTP Request `POST https://api.telegram.org/bot{{$env.TELEGRAM_BOT_TOKEN}}/sendMessage`, corpo `{chat_id: $env.TELEGRAM_CHAT_ID, text, parse_mode: "HTML"}`) → `Responder 200`; ramo falso → `Responder 401`.

- [ ] **Step 1: Teste do formatador.** Extrair do JSON o `jsCode` do nó `Formatar` e rodá-lo com `node` (throwaway, fora do repo) contra 5 entradas, afirmando: Grafana firing `{alertname:'servico-fora-do-ar', app:'jellyfin', severity:'critical'}` → texto começa com `🔴` e contém `jellyfin`; Grafana `status:'resolved'` → começa com `🟢`; Diun → começa com `ℹ️` e contém o `image`; Arr `eventType:'Download'` com `movie.title:'X'` → contém `X`; `{}` → texto genérico `ℹ️ Notificação` sem exceção.
- [ ] **Step 2:** Rodar o teste antes do `jsCode` existir → falha (nó ausente).
- [ ] **Step 3:** Escrever `notificar.json` com os nós de Interfaces; `Autorizado?` compara `$json.headers.authorization` com `'Bearer ' + $env.NOTIFICACOES_WEBHOOK_TOKEN`; `Formatar` devolve `{text}` (HTML escapado) segundo os casos do Step 1 (gravidade → emoji: `critical` 🔴, `warning` 🟠, resolvido 🟢, demais ℹ️).
- [ ] **Step 4:** Teste do Step 1 → passa; `python3 -c "import json; json.load(open('server/ansible/files/n8n/notificar.json'))"` → sem erro; `grep -c "TELEGRAM_BOT_TOKEN\|Bearer" ` > 0 e nenhum valor de segredo no arquivo.
- [ ] **Step 5:** Playbook, compose, Authelia (página 05 → `sync`), página 09 com: `docker exec n8n_app n8n import:workflow --input=/home/node/.n8n/workflows/notificar.json`, `docker exec n8n_app n8n update:workflow --id=HsNotificar00001 --active=true`, reinício do n8n, e os testes `curl` positivo (mensagem chega) e negativo (sem token → 401).
- [ ] **Step 6:** `check`/`sync --yes`/`check` → 0 erros; `lint` → OK; commit `feat(n8n): workflow notificar e webhook autenticado`.

### Task 5: Diun nas duas VMs

**Files:**
- Modify: `server/docker/stacks/apps/docker-compose.yml` (serviço `diun`) e `server/docker/stacks/ai/docker-compose.yml` (serviço `diun_ai`)
- Modify: `setup-monitoring-stack-volumes.yml` (`diun/data`, `MONITORING_DIUN_DATA_PATH`) e `setup-ai-volumes.yml` (`diun-ai/data`, `AI_STACK_DIUN_DATA_PATH`, `NOTIFICACOES_WEBHOOK_TOKEN`, `BASE_DOMAIN_FROM_VAULT` já comum)
- Modify (literal, via wiki): `.env.template` (página 00); páginas 08 e 09

**Interfaces:**
- Consumes: webhook (Task 4).
- Produces: serviços `diun` (core) e `diun_ai` (IA), imagem `crazymax/diun:latest`, `command: serve`, volumes `/var/run/docker.sock:/var/run/docker.sock:ro` e `<DATA_PATH>:/data`, env `DIUN_WATCH_SCHEDULE=0 9 * * *`, `DIUN_PROVIDERS_DOCKER=true`, `DIUN_PROVIDERS_DOCKER_WATCHBYDEFAULT=true`, `DIUN_NOTIF_WEBHOOK_ENDPOINT` (core: URL interna; IA: `https://n8n.${BASE_DOMAIN_FROM_VAULT}/webhook/notificar`), `DIUN_NOTIF_WEBHOOK_METHOD=POST`, `DIUN_NOTIF_WEBHOOK_HEADERS_AUTHORIZATION=Bearer ${NOTIFICACOES_WEBHOOK_TOKEN}`, `TZ=${SYSTEM_TIMEZONE}`.

- [ ] **Step 1:** Composes e playbooks conforme Interfaces (`diun` na rede `proxy` para alcançar `n8n`; `diun_ai` na `ai_network`).
- [ ] **Step 2:** `.env.template` (página 00), páginas 08/09; `check`/`sync --yes`/`check` → 0 erros; `lint` → OK (inclui `docker compose config` se houver docker).
- [ ] **Step 3:** Commit `feat(notificacoes): Diun nas VMs core e IA`.

### Task 6: Homepage e docker-socket-proxy

**Files:**
- Modify: `server/docker/stacks/apps/docker-compose.yml` — `docker-socket-proxy` (`tecnativa/docker-socket-proxy:latest`, `CONTAINERS=1`, `POST=0`, socket `:ro`, rede `internal_services`, sem `ports`) e `homepage` (`ghcr.io/gethomepage/homepage:latest`, redes `proxy`+`internal_services`, volume `${MONITORING_HOMEPAGE_CONFIG_PATH}:/app/config`, env `HOMEPAGE_ALLOWED_HOSTS=home.${BASE_DOMAIN_FROM_VAULT}`, `PUID`/`PGID`, as 9 `HOMEPAGE_VAR_*`; labels Traefik com `Host(\`home.${BASE_DOMAIN_FROM_VAULT}\`)`, `websecure`, `letsencrypt`, middleware `authelia-forwardauth@docker`, porta `3000`)
- Create: `server/ansible/templates/homepage/settings.yaml.j2`, `docker.yaml.j2`, `services.yaml.j2`
- Modify: `setup-monitoring-stack-volumes.yml` (dir `homepage/config`, render dos 3, `MONITORING_HOMEPAGE_CONFIG_PATH` e as 9 `HOMEPAGE_VAR_*` do vault)
- Modify (literal, via wiki): `vault.yml.example` (`homepage_widget_keys`), `.env.template`; página 09 (Painel, chaves de API), página 07

**Interfaces:**
- Produces: `docker.yaml` → `core: {host: docker-socket-proxy, port: 2375}`; `services.yaml` com grupos = Categorias do catálogo; por app de PNL: `href`, `icon` (`<id>.png`), `siteMonitor` (mesma URL do alvo da Task 2), `server: core` + `container: <container_name>` na `core-services-vm`; widgets PNL-2 com URL interna (`http://<serviço>:<porta>`; portainer `https://portainer:9443`, env `1`) e chaves `{% raw %}{{HOMEPAGE_VAR_<APP>_KEY}}{% endraw %}`.

- [ ] **Step 1:** Escrever os 3 templates.
- [ ] **Step 2:** Verificação de template dos 3 → `ok`; `grep -c "{{HOMEPAGE_VAR_" ` no render de `services.yaml` = 9 (Review Focus 2); nenhuma entrada sem app no catálogo.
- [ ] **Step 3:** Compose, playbook, blocos literais (páginas 00/01), páginas 07/09; `check`/`sync --yes`/`check` → 0 erros; `lint` → OK.
- [ ] **Step 4:** Commit `feat(painel): Homepage com services.yaml gerado e socket proxy só leitura`.

### Task 7: Notificações de backup e do Proxmox

**Files:**
- Create (literal, via wiki): `server/scripts/notify.sh` (bloco `title="scripts/notify.sh"` na página 09)
- Modify: `wiki/docs/04-manutencao-recuperacao/02-backup-restore-estrategia.md` (exemplos chamam `notify.sh` no fim)
- Modify: página 09 (Proxmox: destino *webhook* nativo do PVE apontando para a URL externa com o cabeçalho)

**Interfaces:**
- Produces: `notify.sh <gravidade> <titulo> <mensagem> [app]` → `POST` JSON genérico `{titulo, mensagem, gravidade, app}` em `${NOTIFICACOES_WEBHOOK_URL:-https://n8n.<domínio>/webhook/notificar}` com `Authorization: Bearer ${NOTIFICACOES_WEBHOOK_TOKEN}`; `curl --max-time 10`; em falha escreve em stderr e sai 0.

- [ ] **Step 1:** Teste: `NOTIFICACOES_WEBHOOK_URL=http://127.0.0.1:9 NOTIFICACOES_WEBHOOK_TOKEN=x bash server/scripts/notify.sh info T M` → código de saída 0 e mensagem de falha em stderr; `bash -n` → ok.
- [ ] **Step 2:** Rodar antes do script existir → falha.
- [ ] **Step 3:** Bloco literal na página 09 → `sync --yes`; `chmod +x` no server; exemplos de backup chamando `notify.sh` (sucesso e falha).
- [ ] **Step 4:** Teste do Step 1 → passa; `check` → 0 erros; `build` → 0 WARNING.
- [ ] **Step 5:** Commit `feat(notificacoes): notify.sh para backups e webhook do Proxmox`.

### Task 8: Auditoria, índice e fechamento

**Files:**
- Modify: `INDEX.md`, `wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md` (se a auditoria exigir), documento de contexto do projeto Claude

- [ ] **Step 1:** Carregar e seguir `audit-integrations` com `integração=notificacoes` e `integração=painel` (sem script próprio) → nenhum `❌`/`⚠️` (só `✋` documentados); depois auditoria completa → nenhum `❌`/`⚠️` novo.
- [ ] **Step 2:** Corrigir o que a auditoria apontar pelo fluxo; repetir até limpar.
- [ ] **Step 3:** Skill `update-index`; `test`, `check`, `build`, `lint` → passam.
- [ ] **Step 4:** Commit `chore: auditoria e INDEX.md do painel e notificações`; atualizar `claude/contexto-homeserver.md` no projeto com estado e passos manuais (bot, chaves de API, webhooks nas apps, importação do workflow).
