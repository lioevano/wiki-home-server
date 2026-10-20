# Design: agentes — base (hub de MCPs, MCP de operações com runner Ansible, Langfuse)

- **Data:** 2026-10-20
- **Autor:** Léo Ivan (com Claude)
- **Status:** aguardando revisão
- **Caminho:** arquitetural — sub-projeto **4c1** da refatoração do server. A 4c foi dividida em **4c1 base** (este), **4c2 IA que observa o servidor**, **4c3 orquestrador visual e posto de agentes Claude Code**, **4c4 assistente sempre ligado**; a VPN (Tailscale) é sub-projeto à parte.
- **Depende de:** fundação de IA (LiteLLM), segundo cérebro (mcp-auth-proxy, cliente OIDC `mcp`), fotos e arquivos (Authelia OIDC), painel e notificações (n8n → Telegram), Alloy (logs no Loki).

## 1. Objetivo

Dar à IA (Claude Code, app Claude, agentes futuros) acesso **controlável, auditável e observável** ao homeserver, com **controle amplo**: ler métricas, logs, alertas, containers, a casa e as automações **de qualquer lugar**, e **agir** (reiniciar containers, redeployar stacks, rodar playbooks Ansible, comandar a casa, executar workflows) **só pela LAN** (e pela VPN quando existir). Toda chamada de LLM e de ferramenta fica rastreada no **Langfuse**.

### Critérios de pronto

- Stack `agents` na `core-services-vm` com o hub (`agentgateway`), `mcp_grafana_leitura`, `mcp_grafana_controle`, `ops_leitura`, `ops_controle` e `mcp_auth_servidor`; stack `langfuse` na `ai-desktop-vm`; imagens com versão fixada.
- Rota `leitura` do hub: só alcança instâncias somente leitura e uma lista explícita de ferramentas; publicada em `servidor.<domínio>` atrás do mcp-auth-proxy (Authelia, 2FA, grupo `admins`).
- Rota `controle`: todas as ferramentas; publicada só no IP da `core-services-vm` na LAN, com chave por cliente (hash no config); fora do Traefik e do túnel.
- MCP `ops` (código próprio, testado): containers e stacks pela API do Portainer, Ansible pelo runner embutido com lista de playbooks e `plano_id` obrigatório; containers essenciais protegidos; cada ação no Loki e no Telegram.
- Langfuse recebendo as chamadas do LiteLLM e os traces do hub; login OIDC do Authelia.
- Página nova **13 · Agentes: base**, catálogo e índice atualizados, `audit-integrations` sem ❌/⚠️.
- `dev.py test`, `check` (só `REF-PENDING`), `build` estrito e `lint` passam.

## 2. Decisões

| # | Decisão | Escolha |
|---|---|---|
| A1 | Divisão | 4c1 base → 4c2 observador → 4c3 orquestrador visual e posto Claude Code → 4c4 assistente sempre ligado. |
| A2 | Poder da IA | **Controle amplo** com aprovação: leitura em todo lugar; ações (containers, stacks, Ansible, casa, workflows) só na LAN/VPN. |
| A3 | Hub | **agentgateway 1.6** (Linux Foundation): configuração em YAML gerado pelo Ansible a partir da wiki; regras por ferramenta em CEL (`mcpAuthorization`), chaves por cliente com `keyHash` (`apiKey`), `failureMode: failOpen` (um MCP fora não derruba os outros), traces OTLP e métricas. MetaMCP/ContextForge descartados (configuração em banco, fora do git; instabilidade no MetaMCP). |
| A4 | Onde | Hub, `mcp-grafana` e `ops` na **`core-services-vm`**, na rede `proxy` — Grafana, Home Assistant, n8n e Portainer só são alcançáveis pela rede Docker de lá, e publicar as portas deles na LAN seria inseguro (o Grafana confia no cabeçalho do Authelia). **Langfuse na `ai-desktop-vm`** (memória livre e perto do LiteLLM). *Muda o "tudo na ai-desktop-vm" apresentado na conversa.* |
| A5 | Duas rotas | `leitura` (pública via `servidor.`) e `controle` (LAN, chave). Defesa em camadas: a rota `leitura` só tem alvos que **não sabem escrever** (instâncias somente leitura) **e** uma lista de ferramentas permitidas. |
| A6 | Observabilidade | **`mcp-grafana`** oficial (Prometheus, Loki, alertas, painéis): instância `leitura` com `--disable-write`, instância `controle` completa. |
| A7 | Containers, stacks e Ansible | **MCP `ops` próprio** (Python, FastMCP), poucas ferramentas e testadas; containers e stacks pela **API do Portainer** (sem expor socket do Docker); Ansible pelo runner embutido. O `portainer-mcp` oficial foi descartado (descontinuado; exige Portainer 2.45, o atual é 2.19.4). |
| A8 | Ansible | **Runner no servidor com cofre**: o `ops_controle` tem `ansible-core`, o repositório clonado do GitHub (`git pull` antes de cada execução), chave SSH própria (`ops_ssh_key`) autorizada nos hosts e a senha do vault em arquivo `0400`. Só playbooks de `ops_playbooks_permitidos`. `ansible_aplicar` exige um `plano_id` de `ansible_check` do mesmo playbook e do mesmo commit, feito há no máximo 30 min. |
| A9 | Casa e automações | MCP **embutido do Home Assistant** (`/api/mcp`, token de longa duração) e MCP **nativo do n8n** (`/mcp-server/http`, token); na rota `leitura` só as ferramentas de consulta (`GetLiveContext`, `search_workflows`). |
| A10 | Aprovação | Ferramentas que mudam algo têm `destructiveHint: true`; o Claude Code pede aprovação a cada uso (sem "sempre permitir" documentado para elas). Agentes autônomos (4c3/4c4) usam a mesma rota com chave própria; a aprovação humana para eles é desenhada na 4c3. |
| A11 | Auditoria | O `ops` grava cada ação em JSON no stdout (Alloy → Loki) e avisa no Telegram pelo webhook do n8n; o hub registra cada `tools/call` (cliente, ferramenta, resultado) no log. |
| A12 | Rastreio | **Langfuse v4** (web, worker, Postgres, ClickHouse, Redis, MinIO) no disco local da `ai-desktop-vm`; projeto e chaves por `LANGFUSE_INIT_*`; login OIDC (cliente `langfuse`); recebe o callback do LiteLLM e os traces OTLP do hub. Dados descartáveis (sem backup), com retenção limitada. |
| A13 | Versões dependentes | Grafana, n8n e Home Assistant saem de `:latest` e ficam fixados nas versões atuais (o hub depende das APIs deles; o MCP do n8n exige ≥ 2.33). |
| A14 | Notas (4b) | Ficam fora do hub: os conectores próprios continuam, e os agentes da 4c3 (na `ai-desktop-vm`) usam a rede `notes_mcp` diretamente. |

## 3. Serviços

### Stack `agents` (`docker/stacks/agents/docker-compose.yml`, `core-services-vm`)

| Serviço | Imagem | Redes | Portas | Observações |
|---|---|---|---|---|
| `agentgateway` | `cr.agentgateway.dev/agentgateway:v1.6.0` | `proxy`, `agents_internal` | `${CORE_SERVICES_VM_IP_VAR}:4100:4100` (rota `controle`, LAN) | config `config.yaml` (ro) gerado pelo Ansible; rota `leitura` na porta 4000 só na rede interna |
| `mcp_auth_servidor` | `ghcr.io/sigbit/mcp-auth-proxy:v2.10.2` | `proxy`, `agents_internal` | — (Traefik, `servidor.`) | backend `http://agentgateway:4000/mcp`; cliente OIDC `mcp` (redirect novo); `/groups=admins` |
| `mcp_grafana_leitura` | `mcp-grafana` oficial (versão 2.1.x fixada) | `agents_internal`, `internal_services` | — | `--disable-write`, `streamable-http`, token de service account só de leitura (papel Viewer) |
| `mcp_grafana_controle` | idem | idem | — | completo; service account Editor |
| `ops_leitura` | `localhost/homeserver/ops:<versão>` | `agents_internal`, `proxy` | — | `OPS_MODO=leitura`: só registra ferramentas de consulta; sem chave SSH nem senha do vault montadas |
| `ops_controle` | idem | idem | — | `OPS_MODO=controle`; monta chave SSH, senha do vault, clone do repositório |

- O Home Assistant e o n8n não ganham containers: o hub fala com `http://homeassistant:8123/api/mcp` e `http://n8n:5678/mcp-server/http` pela rede `proxy`, com os tokens do vault (`backendAuth`).
- A porta `4100` é liberada no UFW da `core-services-vm` só para `vm_nfs_allowed_clients_cidr` (LAN).

### Stack `langfuse` (`docker/stacks/langfuse/docker-compose.yml`, `ai-desktop-vm`)

`langfuse-web` (porta `${AI_DESKTOP_VM_IP}:3100`, Traefik `langfuse.` pelo file provider), `langfuse-worker`, `langfuse_db` (Postgres), `langfuse_clickhouse`, `langfuse_redis`, `langfuse_minio` — dados em `{{ vm_local_data_path }}/langfuse/*`. Versões fixadas (`langfuse` 4.x exata, ClickHouse, Redis, MinIO, Postgres).

## 4. Hub: rotas e regras

```
Internet ── túnel ── Traefik ── servidor.<dom> ── mcp_auth_servidor (OAuth/Authelia) ── agentgateway :4000 (leitura)
LAN ── <ip core>:4100 (chave por cliente) ── agentgateway (controle)
                         alvos leitura:  mcp_grafana_leitura, ops_leitura, homeassistant (só GetLiveContext), n8n (só search_workflows)
                         alvos controle: mcp_grafana_controle, ops_controle, homeassistant, n8n
```

- `prefixMode: always` (ferramentas nomeadas `<alvo>_<ferramenta>`), `failureMode: failOpen`, `statefulMode: stateless` onde os alvos permitirem.
- Rota `leitura`: `mcpAuthorization` só com regras `allow` (lista fechada, gerada de `agents_ferramentas_leitura` no `group_vars`); qualquer ferramenta fora da lista some do `tools/list` e é recusada no `tools/call`.
- Rota `controle`: `apiKey` com `keyHash` (`sha256:` do valor do vault) por cliente (`claude_code`, `agentes`), metadado `cliente`; `mcpAuthorization` permite tudo a quem tem chave válida.
- Tracing OTLP para o Langfuse (`http://<ip ai>:3100/api/public/otel`, cabeçalho Basic com as chaves do projeto); métricas do hub raspadas pelo Prometheus.
- A tela do agentgateway não é exposta (o playground chamaria ferramentas sem passar pelas chaves).

## 5. MCP `ops`

Código em `server/docker/images/ops/` (Python 3.13, FastMCP; imagem construída pelo playbook, como as da 4b). Duas instâncias da mesma imagem; o modo decide quais ferramentas existem.

| Ferramenta | Modo | O que faz |
|---|---|---|
| `containers_listar(vm?)` | leitura | containers das duas VMs (nome, imagem, estado, saúde, reinícios) pela API do Portainer |
| `container_logs(nome, linhas≤500)` | leitura | últimas linhas do log |
| `stacks_listar()` | leitura | stacks do Portainer e estado |
| `playbooks_listar()` | leitura | `ops_playbooks_permitidos` com descrição |
| `container_reiniciar(nome)` | controle | reinicia; recusa os de `ops_containers_protegidos` |
| `stack_redeploy(nome, puxar_imagens=false)` | controle | redeploy pela API do Portainer; recusa stacks protegidas (`core`) |
| `ansible_check(playbook, limite?)` | controle | `git pull`; `ansible-playbook --check --diff`; devolve diff resumido e `plano_id` |
| `ansible_aplicar(plano_id)` | controle | aplica o mesmo playbook/limite/commit do `plano_id` (≤ 30 min); recusa se o repositório mudou |

- Saída de Ansible e logs truncadas (limite de caracteres) e sem segredos (`no_log` respeitado; o vault nunca é impresso).
- Cada ferramenta de controle: registro JSON (`acao`, `cliente`, `alvo`, `resultado`, `duracao`) e aviso no Telegram via `NOTIFICACOES_WEBHOOK_TOKEN`.
- Uma execução de Ansible por vez (trava); `ansible_aplicar` com tempo limite.

## 6. Dados e backup

| Dado | Onde | Proteção |
|---|---|---|
| Config do hub, lista de ferramentas, playbooks permitidos | git/wiki → Ansible | o próprio repositório |
| Clone do repositório do runner | disco local da core (`{{ vm_local_data_path }}/ops/repo`) | regerável (`git clone`) |
| Chave SSH e senha do vault do runner | disco local da core, `0400`, dono `docker_puid` | vault (origem) |
| Estado OAuth do `mcp_auth_servidor` | disco local | regerável |
| Langfuse (Postgres, ClickHouse, MinIO, Redis) | disco local da ai | descartável; retenção limitada; regra DAD-5 com justificativa |

## 7. Integrações

| Integração | Mudança |
|---|---|
| Authelia | Cliente OIDC `mcp` ganha o redirect `https://servidor.{{ base_domain }}/.auth/oidc/callback`; cliente novo `langfuse` (`two_factor`, PKCE, `client_secret_*` conforme o Langfuse); regra `bypass` para `servidor.`. |
| Traefik | `servidor.` por labels do `mcp_auth_servidor` (sem forward-auth); `langfuse.` pelo file provider (com Authelia, como o Open WebUI). |
| UFW | Porta 4100 da `core-services-vm` aberta só para a LAN. |
| LiteLLM | Callback do Langfuse no `litellm_config.yaml.j2` (chaves por `os.environ/`); variáveis novas no `ai.env`. |
| Prometheus | Job `agentgateway` (métricas do hub); blackbox no `mcp_auth_servidor` e no `langfuse-web`. |
| Grafana (alertas) | `ops-acao-falhou` (logs do `ops` com `resultado="erro"`) e o genérico de serviço fora do ar pelas sondas. |
| Homepage | `langfuse` e `servidor`. |
| Catálogo | `agentgateway` (stack `agents`, publica, `servidor`), `ops`, `mcp-grafana` (internos), `langfuse` (protegida, `langfuse`). |
| Índice | **MCP-3**: rota de controle nunca passa pelo túnel; **MCP-4**: alvo da rota de leitura é instância somente leitura; regras OPS para o runner (playbooks permitidos, `plano_id`). |
| Vault | `agents_api_keys.{claude_code,agentes}`, `grafana_sa_tokens.{leitura,controle}`, `homeassistant_mcp_token`, `n8n_mcp_token`, `portainer_api_key`, `ops_ssh_private_key`, `ops_vault_password`, `langfuse_*` (segredos, chaves do projeto, banco, ClickHouse, MinIO, Redis), `oidc_clients.langfuse`. |
| Versões | Grafana, n8n e Home Assistant fixados (A13). |

## 8. Páginas

- **Nova: `01-manual-implementacao/13-agentes-base.md`** — arquitetura (rotas e por que duas), tokens a gerar (Grafana service accounts, Home Assistant, n8n, Portainer), ativar o MCP no Home Assistant e no n8n, chave SSH do runner e `authorized_keys` nos hosts, deploy, conectar o claude.ai (`servidor.`) e o Claude Code (`claude mcp add --transport http servidor http://<ip core>:4100/mcp --header "Authorization: Bearer …"`), aprovar ações, `ansible_check` → `ansible_aplicar`, Langfuse (login, o que aparece), falhas, teste de ponta a ponta.
- **Editadas:** 00, 01 (vault), 04 (UFW), 05 (Authelia, Traefik), 07 (versões fixadas de Grafana/n8n/HA), 08 (callback do Langfuse), 09 (sondas, alertas, painel), backup, `02-visao-geral-arquitetura/07-apis-llm-estrategia.md`, catálogo, índice, `INDEX.md`, navegação.

## 9. Falhas

| Falha | Comportamento | O que fazer |
|---|---|---|
| Um MCP alvo fora (HA, n8n, Grafana) | As ferramentas dele somem; o resto funciona (`failOpen`) | Ver a sonda/log |
| Hub fora | Conector `servidor.` e Claude Code sem ferramentas do servidor | `docker logs agentgateway`; Portainer |
| Portainer fora | `ops` responde erro claro nas ferramentas de containers | Restaurar o Portainer |
| `ansible_aplicar` com plano vencido ou repositório mudado | Recusa e pede novo `ansible_check` | Rodar o check de novo |
| Playbook falha no meio | Erro devolvido, aviso no Telegram, alerta | Ver o log; rodar de novo após corrigir |
| Langfuse fora | LiteLLM e hub seguem (envio assíncrono); rastreio perdido no período | Restaurar a stack |
| Authelia fora | Login novo no `servidor.` falha; rota `controle` (chave) segue | Restaurar o Authelia |

## 10. Segurança

- **Internet só lê:** a rota `leitura` tem só alvos que não registram ferramentas de escrita (camada 1) e uma lista fechada de ferramentas (camada 2); o login é OAuth + Authelia 2FA + grupo `admins`.
- **Ações só na LAN:** a porta 4100 não tem router no Traefik nem hostname no túnel; o UFW a restringe à LAN; chaves por cliente, guardadas só como hash no config.
- **Runner:** chave SSH própria e revogável; playbooks em lista; simulação obrigatória antes de aplicar; o vault nunca sai do container; uma execução por vez.
- **Injeção de prompt:** conteúdo lido (logs, notas, páginas) pode tentar induzir ações; a aprovação humana por chamada no Claude Code, os containers e stacks protegidos e o `plano_id` limitam o dano; agentes autônomos ganham aprovação própria na 4c3.
- **Tokens dos sistemas:** Grafana com service accounts separadas (Viewer na leitura); HA e n8n com tokens próprios, revogáveis.

## 11. Verificação

- Novo `tools/wikisync/tests/test_agentes_base.py`:
  - config do hub renderizado: rota `leitura` só com alvos `*_leitura`, `homeassistant` e `n8n`, e `mcpAuthorization` só `allow` com a lista de `agents_ferramentas_leitura`; rota `controle` com `apiKey` `keyHash` (nenhuma chave em texto puro), porta 4100; `failureMode: failOpen`; tracing para o Langfuse;
  - compose `agents`: `ops_leitura` sem a chave SSH, a senha do vault nem o repositório; `mcp_grafana_leitura` com `--disable-write`; só o `agentgateway` publica porta, e só a 4100 no IP da core; `mcp_auth_servidor` com `/groups=admins`; imagens sem `latest`;
  - testes unitários do `ops` (com Portainer e `ansible-playbook` falsos): modo leitura não registra ferramentas de controle; containers/stacks protegidos recusados; `plano_id` vencido, de outro playbook ou com commit diferente recusado; playbook fora da lista recusado; registro e aviso emitidos; saídas truncadas e sem segredos;
  - Authelia (`servidor.` no cliente `mcp`, cliente `langfuse`, `bypass`), Traefik, UFW, callback do LiteLLM, sondas, alertas, versões fixadas de Grafana/n8n/HA.
- `check`, `sync`, `test`, `build`, `lint`; skills `update-index` e `audit-integrations`.

## 12. Fora de escopo

- 4c2 (IA que observa o servidor), 4c3 (orquestrador visual, posto de agentes, aprovação humana para agentes autônomos, notas no hub), 4c4 (assistente sempre ligado).
- Tailscale; atualizar o Portainer; expor a tela do agentgateway.

## 13. Riscos

- **agentgateway muda rápido** (1.x): versão fixada; config validada com `--validate-only` no plano.
- **MCP embutido do Home Assistant e do n8n:** nomes de ferramentas podem mudar entre versões — versões fixadas (A13) e lista de leitura no `group_vars`.
- **Runner com a chave dos servidores** é alvo valioso: fica só na rota de controle, na LAN, com playbooks em lista e simulação obrigatória.
- **Langfuse pesado** (~3–4 GB de RAM): na `ai-desktop-vm`; se faltar memória, limitar ClickHouse e worker.
- **Portainer 2.19.4 antigo:** a API usada (stacks, proxy Docker por endpoint) é estável; atualizar o Portainer fica para depois.

## 14. Ajustes do plano

- **Sem regra de UFW para a porta 4100:** portas publicadas pelo Docker não passam pelo UFW (já registrado no role `docker`, para o Portainer Agent). A proteção da rota `controle` é o bind no IP da LAN da `core-services-vm` mais a chave por cliente. A linha "UFW" da seção 7 fica sem efeito.
- **`mcp-grafana`:** imagem `grafana/mcp-grafana:2.1.1` (sem `v`), `streamable-http` em `0.0.0.0:8000`, com `--allowed-hosts` igual ao nome do serviço (`mcp_grafana_leitura:8000`/`mcp_grafana_controle:8000`) — sem isso o servidor recusa o `Host` vindo do hub.
- **Home Assistant e n8n:** o hub usa token Bearer (`backendAuth`): o MCP do Home Assistant aceita o token de longa duração; o do n8n, o token da tela "Instance-level MCP".
- **Langfuse:** porta `3100` da `ai-desktop-vm`; o LiteLLM usa o callback `langfuse_otel` (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_OTEL_HOST`).
- **Runner:** a chave SSH vai por `-e ansible_ssh_private_key_file=…`, porque a variável do inventário (`hosts.ini`) vence a opção `--private-key`. O runner só funciona depois que o `vault.yml` criptografado existir no repositório (o Léo cria ao consolidar).
