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

**Serviço principal** é o primeiro da coluna Serviços. Regras de roteamento e autenticação valem para ele; aplicações `ansible:<role>` têm a evidência nas tasks/labels do role, não em compose.

---

## roteamento

| Campo | Valor |
|---|---|
| Provedor | `traefik` |
| Aplica-se a | Exposição ≠ interna |
| Arquivos | `docker/stacks/<stack>/docker-compose.yml` (labels do serviço principal); para `ansible:<role>`, `ansible/roles/<role>/tasks/main.yml` |
| Páginas | página da aplicação; `01-manual-implementacao/05-rede-segura.md` |
| Manual | — |

### Regras
- **ROT-1** — o serviço principal tem `traefik.enable: "true"` e um router com regra ``Host(`<Subdomínio>.${BASE_DOMAIN_FROM_VAULT}`)`` (ou ``Host(`<Subdomínio>.{{ base_domain }}`)`` em role Ansible; `${N8N_SUBDOMAIN}` conta como o subdomínio `n8n`). *Evidência:* labels do serviço.
- **ROT-2** — o serviço principal está na rede `proxy`. *Evidência:* `networks:` do serviço (para role Ansible: `networks` do task do container).
- **ROT-3 (sobra)** — nenhum serviço com `traefik.enable: "true"` pertence a aplicação `interna` ou está fora do catálogo; nenhum router aponta para subdomínio diferente do catálogo. *Evidência:* todos os composes e roles.

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
- **AUT-1** — Exposição `protegida`: o router do serviço principal inclui o middleware `authelia-forwardauth@docker` (pode haver outros na lista). *Evidência:* label `traefik.http.routers.<r>.middlewares`.
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
| Manual | Public Hostname `<Subdomínio>` → `https://traefik:443` no túnel, **ou** hostname curinga `*` já configurado |

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
| Provedor | `loki` (coleta pelo `promtail`) |
| Aplica-se a | todas |
| Arquivos | compose do consumidor; `ansible/templates/promtail-config.yml.j2` |
| Páginas | `01-manual-implementacao/07-deploy-apps.md` |
| Manual | — |

### Regras
- **LOG-1** — nenhum serviço da aplicação sobrescreve `logging:` (o Promtail lê os logs JSON padrão do Docker em `/var/lib/docker/containers`). *Evidência:* compose do serviço.
- **LOG-2** — há um `promtail` rodando na **mesma VM** da aplicação (hoje só na `core-services-vm`, stack `apps`). *Evidência:* catálogo (Stack/VM do `promtail`) × Stack/VM da aplicação.

### Ao adicionar (por consumidor)
1. Não definir `logging:` no compose.
2. Se a VM ainda não tem `promtail`: apontar a lacuna no plano (`LOG-2`) e propor ao usuário.

### Ao remover (por consumidor)
Nada a fazer.

### Ao remover o provedor
Remover `loki`/`promtail` e `promtail-config.yml.j2`/`loki-local-config.yaml.j2` (via wiki); avisar que os logs deixam de ser centralizados; revisar datasources do `grafana`.

---

## dados

| Campo | Valor |
|---|---|
| Provedor | infra (ZFS no host Proxmox, exportado por NFS) |
| Aplica-se a | Dados ≠ nenhum |
| Arquivos | compose do consumidor (`volumes:`); playbook `ansible/playbooks/setup-<stack>-volumes.yml` correspondente |
| Páginas | página da aplicação; `04-manutencao-recuperacao/02-backup-restore-estrategia.md` |
| Manual | — |

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
- **VAR-1** — toda `${VAR}` (inclusive `${VAR:-padrão}`) usada nos serviços da aplicação existe no `.env.template`. *Evidência:* compose × `.env.template`.
- **VAR-2** — toda variável da aplicação no `.env.template` é produzida por um playbook (tarefa que gera o `.env` ou `environment:` do deploy). *Evidência:* `grep` da variável em `ansible/playbooks/`.
- **VAR-3 (sobra)** — nenhuma variável do `.env.template` deixou de ser usada por todos os composes. *Evidência:* `grep` em `docker/stacks/*/docker-compose.yml`.

### Ao adicionar (por consumidor)
1. Variáveis novas no bloco literal do `.env.template` (página 00) → `dev.py sync`.
2. Geração no playbook da stack.

### Ao remover (por consumidor)
1. Remover do `.env.template` e do playbook **somente** as variáveis que nenhum outro serviço usa (`grep` em todos os composes antes). Variáveis compartilhadas como `SYSTEM_TIMEZONE`, `DOCKER_PUID`, `DOCKER_PGID`, `BASE_DOMAIN_FROM_VAULT` permanecem.

### Ao remover o provedor
Não se aplica.

---

## llm

| Campo | Valor |
|---|---|
| Provedor | `litellm` |
| Aplica-se a | `+llm` |
| Arquivos | compose do consumidor (`environment:`); `ansible/templates/litellm_config.yaml.j2` |
| Páginas | `01-manual-implementacao/08-stack-ia.md`; `02-visao-geral-arquitetura/08-apis-llm-estrategia.md` |
| Manual | — |

### Regras
- **LLM-1** — o consumidor aponta para o LiteLLM (variável com `http://litellm:4000`) e depende do serviço `litellm`. *Evidência:* `environment:` e `depends_on:`.
- **LLM-2** — o consumidor não recebe chaves de provedores externos (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`); só o `litellm` as recebe. *Evidência:* `environment:`.
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
