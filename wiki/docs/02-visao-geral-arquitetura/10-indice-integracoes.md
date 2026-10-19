---
description: "Índice declarativo das integrações entre aplicações: provedor, a quem se aplica, regras verificáveis e passos para adicionar ou remover."
---

# Índice de Integrações

Cada integração liga uma aplicação **provedora** (ex.: Traefik) às aplicações **consumidoras** que satisfazem a regra "Aplica-se a", avaliada sobre os fatos do [Catálogo de Aplicações](09-catalogo-aplicacoes.md). Este índice é lido e aplicado por agentes de IA por meio das skills `audit-integrations`, `add-app`, `remove-app`, `add-integration` e `remove-integration` (veja `AGENTS.md`).

## Legenda

**Aplica-se a** usa as colunas do catálogo:

- `<Coluna> = <valor>` / `<Coluna> ≠ <valor>` — ex.: `Exposição ≠ interna`, `Métricas = sim`.
- `todas` — toda aplicação do catálogo.
- `+<id>` — integração **opcional**: só se aplica a quem tem `+<id>` em Ajustes.
- `-<id>` em Ajustes **sempre exclui** a aplicação, mesmo que a regra se aplique.
- A aplicação provedora não é consumidora da própria integração, salvo indicação na seção.

**Regras** têm id `<PREFIXO>-<n>`. Regras marcadas **(sobra)** verificam o inverso: algo que ficou para trás e não deveria existir.

**Status da auditoria:** `✅` ok · `❌ <REGRA>` falta · `⚠️ <REGRA>` sobra · `✋` passo manual pendente · `—` não se aplica · `?` depende de valor `?` no catálogo.

Uma seção pode ter subseções extras **de referência** (ex.: `### Origem dos valores`) depois das cinco obrigatórias; as skills as seguem ao corrigir ou adicionar.

**Serviço principal** é o primeiro da coluna Serviços. Regras de roteamento e autenticação valem para ele; aplicações `ansible:<role>` têm a evidência nas tasks/labels do role, não em compose.

---

## roteamento

| Campo | Valor |
|---|---|
| Provedor | `traefik` |
| Aplica-se a | Exposição ≠ interna |
| Arquivos | `docker/stacks/<stack>/docker-compose.yml` (labels do serviço principal); para `ansible:<role>`, `ansible/roles/<role>/tasks/main.yml`; routers definidos por arquivo em `ansible/roles/infra/traefik-config/templates/*.yml.j2` |
| Páginas | página da aplicação; `01-manual-implementacao/05-rede-segura.md` |
| Manual | — |

### Regras
- **ROT-1** — o serviço principal tem `traefik.enable: "true"` e um router com regra ``Host(`<Subdomínio>.${BASE_DOMAIN_FROM_VAULT}`)`` (ou ``Host(`<Subdomínio>.{{ base_domain }}`)`` em role Ansible; `${N8N_SUBDOMAIN}` conta como o subdomínio `n8n`). Aplicação em **outra VM** que não a do Traefik: em vez das labels, um router no *file provider* (`ansible/roles/infra/traefik-config/templates/*.yml.j2`) com essa regra, apontando para `http://<ip da VM>:<porta publicada no compose>`. *Evidência:* labels do serviço ou template do *file provider*.
- **ROT-2** — o serviço principal está na rede `proxy`; aplicação em outra VM, roteada pelo *file provider*, publica a porta no IP da VM (`${<VM>_IP}:<porta>:<porta do container>`). *Evidência:* `networks:`/`ports:` do serviço (para role Ansible: `networks` do task do container).
- **ROT-3 (sobra)** — nenhum router (por label **ou** por arquivo do *file provider*) pertence a aplicação `interna`, a serviço fora do catálogo, ou usa subdomínio diferente do catálogo. *Evidência:* labels de todos os composes e roles, e `ansible/roles/infra/traefik-config/templates/*.yml.j2`.

### Ao adicionar (por consumidor)
1. Labels no serviço principal: `traefik.enable`, router `<app>` com a regra Host, `entrypoints`/`tls` iguais aos vizinhos, `loadbalancer.server.port` com a porta interna.
2. Rede `proxy` (externa) no serviço principal.

### Ao remover (por consumidor)
1. Remover as labels `traefik.*` do serviço (ou o serviço inteiro, se a aplicação sai).
2. Remover a rede `proxy` se o serviço continuar existindo como `interna`.

### Ao remover o provedor
Todas as aplicações com Exposição ≠ interna perdem acesso externo: remover `roteamento`, `autenticacao` e `acesso-externo` de todas, ou substituir o provedor antes.

---

## autenticacao

| Campo | Valor |
|---|---|
| Provedor | `authelia` |
| Aplica-se a | Exposição ≠ interna |
| Arquivos | labels do serviço principal; `ansible/roles/infra/authelia-config/templates/configuration.yml.j2` |
| Páginas | página da aplicação; `01-manual-implementacao/05-rede-segura.md` (bloco literal do `configuration.yml.j2`) |
| Manual | — |

### Regras
- **AUT-1** — Exposição `protegida`: o router do serviço principal inclui exatamente o middleware `authelia-forwardauth@docker` (pode haver outros na lista; nomes parecidos como `authelia@docker` **não** valem). *Evidência:* label `traefik.http.routers.<r>.middlewares` ou `middlewares:` do router no template do *file provider*.
- **AUT-2** — Exposição `protegida`: o subdomínio é coberto por uma regra `two_factor` em `access_control.rules` — a regra curinga `"*.{{ base_domain }}"` → `two_factor` satisfaz. *Evidência:* `configuration.yml.j2`.
- **AUT-3** — Exposição `publica`: existe regra `domain: "<Subdomínio>.{{ base_domain }}"` com `policy: bypass` **antes** da regra curinga, e o router **não** usa o middleware do Authelia. *Evidência:* `configuration.yml.j2` e labels. (O próprio `authelia` cumpre isso com a regra de `auth`.)
- **AUT-4 (sobra)** — nenhuma regra `bypass`/`one_factor` específica para subdomínio que não exista no catálogo. *Evidência:* `configuration.yml.j2`.

### Ao adicionar (por consumidor)
1. `protegida`: acrescentar `authelia-forwardauth@docker` aos middlewares do router; conferir que a curinga continua `two_factor`.
2. `publica`: adicionar a regra `bypass` no bloco literal do `configuration.yml.j2` (página 05) antes da curinga → `dev.py sync`.

### Ao remover (por consumidor)
1. Retirar a regra específica do subdomínio do `configuration.yml.j2` (via página 05), se houver.
2. Retirar o middleware das labels (ou o serviço).

### Ao remover o provedor
Toda aplicação `protegida` ficaria exposta sem login: **bloquear** até que cada uma vire `interna` ou outro provedor de autenticação seja adicionado.

---

## acesso-externo

| Campo | Valor |
|---|---|
| Provedor | `cloudflared` |
| Aplica-se a | Exposição ≠ interna |
| Arquivos | — (configuração do túnel é remota, no painel da Cloudflare) |
| Páginas | `01-manual-implementacao/05-rede-segura.md` (seção Public Hostnames) |
| Manual | Public Hostname `<Subdomínio>` → `https://traefik:443` (com *No TLS Verify*) no túnel, **ou** hostname curinga `*` já configurado |

### Regras
- **EXT-1** — a página 05 documenta o Public Hostname curinga `*` **ou** a página da aplicação registra o hostname específico a criar. Se nenhum dos dois: `✋` (passo manual pendente), não `❌`. *Evidência:* texto das páginas.

### Ao adicionar (por consumidor)
1. Se não houver curinga: registrar na página da aplicação o passo manual "criar Public Hostname `<Subdomínio>`" e listá-lo nos passos manuais do plano.

### Ao remover (por consumidor)
1. Se havia hostname específico: passo manual "remover Public Hostname `<Subdomínio>`" no plano; retirar a menção da página.

### Ao remover o provedor
Nenhuma aplicação fica acessível pela internet; tratar como remoção de `acesso-externo` de todos os consumidores (passos manuais) e avisar o usuário.

---

## metricas

| Campo | Valor |
|---|---|
| Provedor | `prometheus` |
| Aplica-se a | Métricas = sim |
| Arquivos | `ansible/templates/prometheus.yml.j2`; playbook `ansible/playbooks/setup-monitoring-stack-volumes.yml` (renderiza o template) |
| Páginas | página da aplicação; `01-manual-implementacao/07-deploy-apps.md` |
| Manual | — |

### Regras
- **MET-1** — existe um `job_name` em `prometheus.yml.j2` cujo target aponta para um serviço da aplicação (`<serviço>:<porta>`). O próprio `prometheus` cumpre com o job `prometheus` (`localhost:9090`). *Evidência:* `scrape_configs`.
- **MET-2 (sobra)** — todo job aponta para um serviço do catálogo com Métricas = sim, **exceto** jobs `node_exporter_*`, que monitoram hosts/VMs (não aplicações). *Evidência:* `scrape_configs`.

### Ao adicionar (por consumidor)
1. Confirmar na documentação oficial a porta/caminho de métricas; adicionar o job em `prometheus.yml.j2` (template estrutural) e citar na página da aplicação.

### Ao remover (por consumidor)
1. Remover o job do consumidor de `prometheus.yml.j2`.

### Ao remover o provedor
Remover `prometheus.yml.j2` e as tarefas que o renderizam no `setup-monitoring-stack-volumes.yml` (via wiki); colocar Métricas = não em todas as aplicações; avaliar o `grafana` (datasource Prometheus).

---

## logs

| Campo | Valor |
|---|---|
| Provedor | `loki` (coleta pelo `alloy`) |
| Aplica-se a | todas |
| Arquivos | compose do consumidor; `ansible/roles/infra/alloy/templates/config.alloy.j2` (role `infra/alloy`, aplicado por `setup-base-ubuntu.yml` e `setup-proxmox-host.yml`); `ansible/templates/loki-local-config.yaml.j2` |
| Páginas | `01-manual-implementacao/04-configuracao-base-vms-ubuntu.md` (seção 4.4); `01-manual-implementacao/07-deploy-apps.md` |
| Manual | — |

### Regras
- **LOG-1** — nenhum serviço da aplicação sobrescreve `logging:` (o Alloy lê os logs pela API do Docker, que depende do driver padrão). *Evidência:* compose do serviço.
- **LOG-2** — a VM da aplicação está num grupo do inventário que recebe o role `infra/alloy` (hoje `proxmox_hosts`, pelo `setup-proxmox-host.yml`, e `ubuntu_vms`, pelo `setup-base-ubuntu.yml`). *Evidência:* catálogo (Stack/VM da aplicação) × `hosts.ini` × playbooks.

### Ao adicionar (por consumidor)
1. Não definir `logging:` no compose.
2. Se a VM da aplicação não está em `ubuntu_vms`: apontar a lacuna no plano (`LOG-2`) e propor ao usuário incluí-la no grupo ou aplicar o role `infra/alloy` a ela.

### Ao remover (por consumidor)
Nada a fazer.

### Ao remover o provedor
Remover `loki` e `loki-local-config.yaml.j2` e os blocos `loki.*` do `config.alloy.j2` (via wiki); avisar que os logs deixam de ser centralizados; revisar datasources do `grafana` e a regra `authelia-logins-falhos`.

---

## dados

| Campo       | Valor                                                                                                     |
| ----------- | --------------------------------------------------------------------------------------------------------- |
| Provedor    | infra (ZFS no host Proxmox, exportado por NFS)                                                            |
| Aplica-se a | Dados ≠ nenhum                                                                                            |
| Arquivos    | compose do consumidor (`volumes:`); playbook `ansible/playbooks/setup-<stack>-volumes.yml` correspondente |
| Páginas     | página da aplicação; `04-manutencao-recuperacao/02-backup-restore-estrategia.md`                          |
| Manual      | —                                                                                                         |

### Regras
- **DAD-1** — Dados = `nfs`: os volumes de dados persistentes usam `${VM_NFS_MOUNT_BASE_PATH}/…` ou uma variável `*_PATH` criada pelo playbook de volumes da stack (que a aponta para o NFS). Binds de sistema (`/var/run/docker.sock`, `/etc/localtime`, logs do Docker) não contam. *Evidência:* `volumes:` + playbook.
- **DAD-2** — Dados = `local`: a página da aplicação tem aviso de que os dados ficam fora dos snapshots ZFS **e** a página de backup lista a aplicação. *Evidência:* as duas páginas.
- **DAD-3** — o playbook `setup-<stack>-volumes.yml` cria os diretórios usados pela aplicação. *Evidência:* tasks `ansible.builtin.file` do playbook.

### Ao adicionar (por consumidor)
1. `nfs`: diretórios no playbook de volumes e variável `*_PATH` (ver `variaveis`).
2. `local`: diretório local no playbook, aviso na página e entrada na página de backup.

### Ao remover (por consumidor)
1. Remover os diretórios/variáveis da aplicação do playbook; **não apagar dados** — registrar no plano um passo manual de arquivamento/remoção dos dados no NFS ou disco.
2. Retirar a aplicação da página de backup.

### Ao remover o provedor
Não se aplica (infraestrutura base).

---

## variaveis

| Campo | Valor |
|---|---|
| Provedor | infra (Ansible gera os `.env`; Portainer os carrega) |
| Aplica-se a | todas (exceto `ansible:<role>`) |
| Arquivos | `docker/stacks/.env.template`; `ansible/playbooks/setup-*-volumes.yml` e `setup-core-networking.yml` (geração do `.env`/`environment`); `ansible/templates/portainer_stack_env.j2` |
| Páginas | `01-manual-implementacao/00-preparacao-planejamento.md` (bloco literal do `.env.template`) |
| Manual | — |

### Regras
- **VAR-1** — toda `${VAR}` (inclusive `${VAR:-padrão}`) usada em **qualquer** serviço da aplicação existe no `.env.template`. *Evidência:* compose × `.env.template`.
- **VAR-2** — toda `${VAR}` usada em qualquer serviço da aplicação é produzida por um playbook (tarefa que gera o `.env` ou `environment:` do deploy). Variável **compartilhada** que não é produzida falha em **todas** as aplicações que a usam. "Produzida" = emitida **com o mesmo nome**; emissão condicional (`{% if X is defined %}`) só conta se algum playbook define `X`. *Evidência:* `grep` da variável em `ansible/playbooks/` e `ansible/templates/portainer_stack_env.j2`.
- **VAR-3 (sobra)** — nenhuma variável do `.env.template` deixou de ser usada por todos os composes. *Evidência:* `grep` em `docker/stacks/*/docker-compose.yml`.

### Ao adicionar (por consumidor)
1. Variáveis novas no bloco literal do `.env.template` (página 00) → `dev.py sync`.
2. Geração no playbook da stack.

### Ao remover (por consumidor)
1. Remover do `.env.template` e do playbook **somente** as variáveis que nenhum outro serviço usa (`grep` em todos os composes antes). Variáveis compartilhadas como `SYSTEM_TIMEZONE`, `DOCKER_PUID`, `DOCKER_PGID`, `BASE_DOMAIN_FROM_VAULT` permanecem.

### Ao remover o provedor
Não se aplica.

### Origem dos valores

Toda variável é emitida **pelo playbook da stack**, com o nome exato usado no compose, a partir de uma fonte versionada — nunca com valor fixo no playbook. A tabela descreve as stacks implantadas pelo Portainer (`apps`, `ai`), que usam `stack_configs`; na stack `core` toda variável — inclusive as comuns e os segredos — é uma entrada em `environment:` do deploy em `ansible/playbooks/setup-core-networking.yml`.

| Tipo | Como reconhecer | Fonte do valor | Como o playbook emite |
|---|---|---|---|
| Comum | `DOCKER_PUID`, `DOCKER_PGID`, `SYSTEM_TIMEZONE`, `BASE_DOMAIN_FROM_VAULT`, `VM_NFS_MOUNT_BASE_PATH`, `ZFS_*_DATASET_NAME` | vault / `group_vars/all/main.yml` | já emitidas por `ansible/templates/portainer_stack_env.j2` — nada a fazer |
| Segredo | senha, chave, token (`*_PASSWORD*`, `*_KEY`, `*_SECRET*`, `*_TOKEN*`) | `vault.yml`, chave `snake_case` (ex.: `litellm_master_key`); placeholder obrigatório em `vault.yml.example`; valor sem `$`, `#`, aspas ou espaços (o `.env` não usa aspas) | entrada `{ name: 'VAR', value: "{{ chave_vault }}" }` em `stack_configs`; o playbook carrega o vault (`vars_files`) e a tarefa que grava o `.env` usa `mode: '0600'` |
| IP de host/VM | `*_IP`, `*_IP_VAR` | `[all:vars]` do `hosts.ini` (`core_services_vm_ip_var`, `ai_desktop_vm_ip_var`, `proxmox_host_ip_var`) | entrada em `stack_configs` com a variável do inventário |
| Caminho | `*_PATH` | `group_vars/all/main.yml` (`vm_nfs_mount_base_path`, `zfs_*_dataset_name`) ou caminho local declarado no playbook | entrada em `stack_configs` concatenando as variáveis |
| Configuração | demais (subdomínios, nomes, flags) | `group_vars/all/main.yml` | entrada em `stack_configs` |

**Playbook de cada stack:** `core` → `environment:` do deploy em `ansible/playbooks/setup-core-networking.yml`; `apps` → `setup-productivity-automation-volumes.yml` (nextcloud, homeassistant), `setup-media-stack-volumes.yml` (mídia), `setup-monitoring-stack-volumes.yml` (monitoramento), `setup-n8n-volumes.yml` (n8n); `ai` → `setup-ai-volumes.yml`.

**Segredo novo** (sem chave no vault): proponha `snake_case` derivado do nome da variável e confirme com o usuário antes de criar.

---

## llm

| Campo | Valor |
|---|---|
| Provedor | `litellm` |
| Aplica-se a | `+llm` |
| Arquivos | compose do consumidor (`environment:`); `ansible/templates/litellm_config.yaml.j2` |
| Páginas | `01-manual-implementacao/08-stack-ia.md`; `02-visao-geral-arquitetura/07-apis-llm-estrategia.md` |
| Manual | — |

### Regras
- **LLM-1** — o consumidor aponta para o LiteLLM (variável com `http://litellm:4000`) e depende do serviço `litellm`. *Evidência:* `environment:` e `depends_on:`.
- **LLM-2** — o consumidor não recebe chaves de provedores externos (os valores `${OPENAI_API_KEY}`, `${ANTHROPIC_API_KEY}`, `${GEMINI_API_KEY}`); só o `litellm` as recebe. Uma variável do consumidor com nome de provedor que recebe `${LITELLM_MASTER_KEY}` (ex.: `OPENAI_API_KEY=${LITELLM_MASTER_KEY}` no Open WebUI) é a chave do proxy e é válida. *Evidência:* `environment:`.
- **LLM-3** — consumidor e `litellm` compartilham uma rede (`ai_network`). *Evidência:* `networks:`.

### Ao adicionar (por consumidor)
1. Variável de base URL do LiteLLM, `depends_on: [litellm]`, rede `ai_network`; modelos novos em `litellm_config.yaml.j2`, se necessário.

### Ao remover (por consumidor)
1. Retirar variáveis, `depends_on` e a rede (se não usada por outro motivo); remover do `litellm_config.yaml.j2` modelos usados só por ele.

### Ao remover o provedor
Consumidores ficam sem LLM: remover `+llm` de todos e decidir com o usuário se eles saem ou passam a usar APIs diretas.

---

## documentacao

| Campo | Valor |
|---|---|
| Provedor | wiki |
| Aplica-se a | todas |
| Arquivos | — |
| Páginas | `02-visao-geral-arquitetura/09-catalogo-aplicacoes.md`; página da aplicação; `INDEX.md` (seção Aplicações) |
| Manual | — |

### Regras
- **DOC-1** — a aplicação tem linha no catálogo com todas as colunas preenchidas (sem `?`).
- **DOC-2** — a página indicada na coluna Página existe e cita a aplicação (nome, serviço principal ou subdomínio).
- **DOC-3** — o `INDEX.md` lista a aplicação na seção Aplicações.
- **DOC-4 (sobra)** — todo serviço dos composes pertence a exatamente uma aplicação do catálogo. *Evidência:* `services:` de cada compose × coluna Serviços.
- **DOC-5 (sobra)** — todo serviço listado no catálogo existe no compose da stack (ou no role, para `ansible:<role>`).

### Ao adicionar (por consumidor)
1. Linha no catálogo; seção na página da stack; skill `update-index`.

### Ao remover (por consumidor)
1. Retirar a linha do catálogo e a seção/menções da página; skill `update-index`.

### Ao remover o provedor
Não se aplica.

---

## notificacoes

| Campo | Valor |
|---|---|
| Provedor | `n8n` (workflow `notificar`, arquivo `ansible/files/n8n/notificar.json`); coletores: Grafana Alerting (`ansible/templates/grafana/alerting/*.yml.j2`), `blackbox-exporter`, `diun` |
| Aplica-se a | todas |
| Arquivos | `ansible/templates/prometheus.yml.j2` (job `blackbox_http`); compose do consumidor (webhook nativo, se houver) |
| Páginas | página da aplicação; `01-manual-implementacao/09-painel-notificacoes.md` |
| Manual | webhook configurado na interface da aplicação (NTF-3), quando ela não aceita configuração por arquivo ou variável |

Entrada única: `POST /webhook/notificar` no n8n com `Authorization: Bearer <NOTIFICACOES_WEBHOOK_TOKEN>` — interna `http://n8n:5678/webhook/notificar` (stack `apps`), externa `https://n8n.seudominio.com/webhook/notificar`. A regra `bypass` do Authelia para `n8n.{{ base_domain }}` com `resources: ["^/webhook/.*$"]` é parte desta integração (não é desvio de AUT-3/AUT-4). Alertas globais (disco, RAM, CPU, ZFS, hosts, certificados, logins falhos no Authelia) ficam no provedor, em `ansible/templates/grafana/alerting/rules.yml.j2`, e não são por aplicação.

### Regras
- **NTF-1** — disponibilidade: aplicação com Exposição `publica`/`protegida` tem alvo pela **URL interna** do serviço principal (ex.: `http://n8n:5678/healthz`; a URL pública passa pelo Authelia e não mede a aplicação) com `labels: {app: <id>}` no job `blackbox_http`; o alvo do `traefik` usa o módulo `tls_traefik` (mede também o certificado). Das `interna`, só `litellm` (`http://<ai_desktop_vm_ip_var>:4000/health/liveliness`) e `loki` (`http://loki:3100/ready`) têm alvo — as demais `interna` → `—`. *Evidência:* `prometheus.yml.j2`.
- **NTF-2** — atualizações: existe um serviço do `diun` na mesma VM da aplicação (Stack/VM do `diun` × da aplicação). *Evidência:* catálogo e composes.
- **NTF-3** — eventos: aplicação com webhook nativo (`radarr`, `sonarr`, `homeassistant`, `jellyfin` via plugin) tem na sua página o passo "apontar o webhook para o n8n"; sem o passo documentado → `✋`. Demais → `—`.
- **NTF-4 (sobra)** — nenhum alvo do `blackbox_http` nem regra de alerta com `app` que não exista no catálogo. *Evidência:* `prometheus.yml.j2` e `rules.yml.j2`.

### Ao adicionar (por consumidor)
1. Alvo no `blackbox_http` (NTF-1), se aplicável.
2. Se a VM ainda não tem `diun`: apontar a lacuna no plano (NTF-2) e propor ao usuário.
3. Se a aplicação tem webhook nativo: passo manual na página dela (NTF-3).

### Ao remover (por consumidor)
1. Retirar o alvo do `blackbox_http` e o passo de webhook da página.

### Ao remover o provedor
Desativar os coletores (contato `n8n` do Grafana, webhook do Diun e do `scripts/notify.sh`), remover `ansible/files/n8n/notificar.json`, a regra `bypass` de `/webhook/` no Authelia e as variáveis `TELEGRAM_*`/`NOTIFICACOES_WEBHOOK_TOKEN`; avisar que as notificações param.

---

## painel

| Campo | Valor |
|---|---|
| Provedor | `homepage` |
| Aplica-se a | Exposição ≠ interna |
| Arquivos | `ansible/templates/homepage/services.yaml.j2`; `.env` da Homepage (chaves `HOMEPAGE_VAR_*`) |
| Páginas | página da aplicação; `01-manual-implementacao/09-painel-notificacoes.md` |
| Manual | gerar a chave de API na interface da aplicação e gravá-la no vault (PNL-2) |

Aplicação `interna` entra com `+painel` em Ajustes (atalho para a URL da LAN).

### Regras
- **PNL-1** — a aplicação tem entrada no `services.yaml.j2` (nome = id do catálogo), no grupo da sua Categoria, com `href` `https://<Subdomínio>.{{ base_domain }}` (ou URL da LAN para `+painel`) e status: na `core-services-vm`, `server: core` e `container: <container_name>` (estado do container); em outra VM, `siteMonitor` pela URL da LAN (a URL pública passa pelo Authelia). *Evidência:* template.
- **PNL-2** — aplicação com widget oficial da Homepage (`jellyfin`, `radarr`, `sonarr`, `qbittorrent`, `nextcloud`, `homeassistant`, `grafana`, `prometheus`, `portainer`) tem `widget` na entrada; credenciais só como `{{HOMEPAGE_VAR_<APP>_...}}`, com valor vindo do vault (`homepage_widget_keys.<app>`, ou `grafana_admin_initial_password`) pelo playbook. O `traefik` fica sem widget (a API só existe atrás do Authelia). *Evidência:* template, compose da Homepage e playbook.
- **PNL-3 (sobra)** — nenhuma entrada no `services.yaml.j2` sem aplicação correspondente no catálogo. *Evidência:* template.

### Ao adicionar (por consumidor)
1. Entrada no `services.yaml.j2` (PNL-1); se houver widget: entrada, variável `HOMEPAGE_VAR_*` no compose da Homepage, `.env.template`, chave em `homepage_widget_keys` no `vault.yml.example` e emissão no playbook (PNL-2); passo manual da chave na página 09.

### Ao remover (por consumidor)
1. Retirar a entrada, a variável `HOMEPAGE_VAR_*`, a chave do vault e a emissão.

### Ao remover o provedor
Remover `homepage`, `docker-socket-proxy` (se não usado por outro), os templates `ansible/templates/homepage/` e as variáveis `HOMEPAGE_VAR_*`.

---

## Pendências da auditoria inicial

Desvios encontrados na primeira auditoria (2026-10-13) que dependem de decisão ou de refatoração. Os mecânicos (VAR-2 e DAD-3) foram corrigidos pela skill `fix-integrations`.

Nenhuma pendência de regra em aberto: LOG-2, ROT-3 e MET-2 foram decididas em 2026-10-13 (Promtail na VM de IA, Open WebUI `protegida`, job `glances` removido).

**Fora das regras** (para a reestruturação): a stack `apps` é um compose único, mas recebe cinco `.env` separados (hoje unidos à mão num `apps.env`, ver página 07); portas publicadas pelo Docker (ex.: Loki 3100, LiteLLM 4000) contornam o UFW — a restrição real é a LAN. Os demais itens registrados na auditoria inicial foram corrigidos em 2026-10-13.
