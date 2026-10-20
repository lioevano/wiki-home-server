# Design: IA — fundação (gateway LiteLLM, chaves e uso, Open WebUI, Claude Code, Ollama)

- **Data:** 2026-10-20
- **Autor:** Léo Ivan (com Claude)
- **Status:** aguardando revisão
- **Caminho:** arquitetural — sub-projeto **4a** da refatoração do server (1 Alloy ✓, 2 mídia ✓, 3 fotos e arquivos ✓, 4 IA). A IA foi dividida em **4a fundação** (este), **4b segundo cérebro e RAG** e **4c agentes**; a VPN (Tailscale) é sub-projeto à parte.
- **Depende de:** catálogo e índice, painel e notificações, Alloy, fotos e arquivos (Authelia OIDC), correção da base (Docker e Portainer Agent na `ai-desktop-vm`, commit `27e6a878`).

## 1. Objetivo

Um ponto único de acesso a modelos de linguagem — para o Léo e para os agentes futuros — **controlável por código e por IA**, **observável** e **modular** (trocar de LLM a qualquer momento sem mexer nos clientes). Uso **principalmente por API** (Claude em primeiro lugar); modelos locais só para tarefas leves ou privadas.

Usos cobertos nesta etapa: chat no navegador e no celular (Open WebUI), programação no PC (Claude Code), decisões rápidas (Jev) e ver o uso (tokens, custo, latência por cliente e modelo).

### Critérios de pronto

- Stack `ai` com `litellm`, `litellm_db`, `ollama`, `open-webui` e `diun_ai`; sem `openclaw` e `openclaude`; imagens com versão fixada.
- `config.yaml` do LiteLLM gerado de `llm_models` (`group_vars`), com os apelidos `principal`, `rapido`, `local`, `decisao` e fallbacks; `store_model_in_db: false`.
- Uma chave virtual por cliente, com orçamento mensal, criada/atualizada pelo playbook `setup-ai-keys.yml` (idempotente); nenhum cliente recebe chave de provedor nem a chave mestra.
- Open WebUI com login OIDC do Authelia (terceiro cliente `openwebui`), falando só com o LiteLLM.
- Tela de uso do LiteLLM em `llm.<domínio>` (Authelia); API só na LAN.
- Página 08 reescrita (gateway, apelidos, chaves, Jev, uso, Claude Code, Ollama/Vulkan), catálogo e índice atualizados, `audit-integrations` sem ❌/⚠️.
- `dev.py test`, `check` (só `REF-PENDING`), `build` estrito e `lint` passam.

## 2. Decisões

| # | Decisão | Escolha |
|---|---|---|
| I1 | Divisão | 4a fundação → 4b segundo cérebro e RAG → 4c agentes. Ver seção 10. |
| I2 | Onde | Tudo na `ai-desktop-vm` (16 GB quase livres), gerenciada pelo Portainer central via Portainer Agent; Open WebUI e a tela do LiteLLM expostos pelo Traefik da `core-services-vm` (file provider). |
| I3 | Gateway | **LiteLLM** com Postgres: API OpenAI, API Anthropic (`/v1/messages`) e passagem do Jev (`/typesafe/…`). Versão fixada que já tenha a integração TypeSafe/Jev. |
| I4 | Modularidade | Apelidos estáveis (`principal`, `rapido`, `local`, `decisao`) declarados em `llm_models`; clientes usam apelidos (exceto o Claude Code, ver I8). Fonte da verdade = código (`store_model_in_db: false`). |
| I5 | Jev | Modelo `decisao` (provedor TypeSafe) e rota de passagem `/typesafe/v1/systemone`; chave em `llm_api_keys.typesafe`. Sem streaming (limitação do provedor). |
| I6 | Chaves | Uma chave virtual por cliente (`open-webui`, `claude-code`, `n8n`; agentes da 4c depois), valores no vault (`litellm_client_keys`), orçamento mensal (`budget_duration: 30d`); upsert pela API do LiteLLM no `setup-ai-keys.yml`. |
| I7 | Uso | Registro no Postgres do LiteLLM + tela de administração em `llm.`; métricas Prometheus do LiteLLM se forem livres na versão fixada (conferido no plano), com alerta de gasto. Rastreamento passo a passo (Langfuse) fica na 4c. |
| I8 | Claude Code | No PC Linux, dois modos: `claude` com a assinatura (direto na Anthropic) e o alias `claude-gw` pelo gateway (`ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` com a chave `claude-code`), usando **nomes reais de modelos Claude** — a Anthropic não suporta o Claude Code com modelos não-Claude via gateway. |
| I9 | Acesso externo | API só na LAN agora; de fora, pela VPN (sub-projeto próprio). Tela do LiteLLM e Open WebUI pelo túnel, atrás do Authelia. |
| I10 | GPU | Ollama oficial com **Vulkan** na RX 5600 XT (`/dev/dri`, grupo `render`); se o Vulkan não pegar, CPU. Sai o ROCm do role `ml-tools`. A GPU fica com o Ollama; o ML do Immich segue na CPU. |
| I11 | Saem | `openclaude` (é CLI do PC, documentado como cliente) e `openclaw` (volta na 4c com desenho de segurança próprio). |

## 3. Serviços (stack `ai`, `docker/stacks/ai/docker-compose.yml`)

| Serviço | Imagem | Rede | Portas | Dados |
|---|---|---|---|---|
| `litellm` | `ghcr.io/berriai/litellm-database:<versão fixada>` | `ai_network` | `${AI_DESKTOP_VM_IP}:4000:4000` (API na LAN; tela pelo Traefik) | `config.yaml` (ro) ← NFS |
| `litellm_db` | `postgres:16-alpine` | `ai_network` | — | `${AI_STACK_LITELLM_DB_PATH}` ← `{{ vm_local_data_path }}/litellm-db` |
| `ollama` | `ollama/ollama:<versão fixada>` (não a `rocm`) | `ai_network` | nenhuma | modelos ← NFS (como hoje) |
| `open-webui` | `ghcr.io/open-webui/open-webui:<versão fixada>` | `ai_network` | `${AI_DESKTOP_VM_IP}:3000:8080` (Traefik) | NFS (como hoje) |
| `diun_ai` | como hoje | `ai_network` | — | NFS |

- `litellm`: `DATABASE_URL` para `litellm_db`, `LITELLM_MASTER_KEY`, chaves de provedores (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `TYPESAFE_API_KEY`), `STORE_MODEL_IN_DB=False`; `depends_on: litellm_db (healthy)`.
- `ollama`: `devices: [/dev/dri]`, `group_add` do grupo `render` (GID do host, variável), sem `ports`.
- `open-webui`: `ENABLE_OLLAMA_API=false`; `OPENAI_API_BASE_URL=http://litellm:4000/v1`, `OPENAI_API_KEY=${LITELLM_KEY_OPENWEBUI}`; OIDC: `ENABLE_OAUTH_SIGNUP=true`, `OAUTH_MERGE_ACCOUNTS_BY_EMAIL=true`, `OAUTH_CLIENT_ID=openwebui`, `OAUTH_CLIENT_SECRET`, `OPENID_PROVIDER_URL=https://auth.<domínio>/.well-known/openid-configuration`, `OAUTH_PROVIDER_NAME=Authelia`, `OAUTH_SCOPES=openid email profile groups`; `ENABLE_LOGIN_FORM` controlado por variável (ligado só até vincular o admin).

## 4. Gateway: modelos, apelidos, Jev e chaves

**`llm_models`** (lista em `group_vars/all/main.yml`, pela wiki), renderizada em `ansible/templates/litellm_config.yaml.j2`:

- Por provedor: os modelos atuais da Anthropic (Opus, Sonnet, Haiku), OpenAI e Gemini, pelo nome próprio (nomes exatos conferidos no plano).
- Apelidos: `principal` → Claude Opus/Sonnet atual; `rapido` → Claude Haiku atual; `local` → modelo pequeno do Ollama (`http://ollama:11434`); `decisao` → Jev (`typesafe/…`).
- `router_settings.fallbacks`: `principal` → modelo equivalente de outro provedor; `rapido` → idem.
- `general_settings`: `master_key`, `database_url`, `store_model_in_db: false`.

**Chaves** (`litellm_client_keys` no vault, valores `sk-…` gerados com `openssl rand -hex 24`): `openwebui`, `claude_code`, `n8n`; cada uma com `max_budget` mensal (`litellm_key_budgets` em `group_vars`) e, quando fizer sentido, lista de modelos permitidos. O `setup-ai-keys.yml` roda **depois do deploy**, na máquina de controle ou na VM, e para cada chave: consulta `/key/info`; se não existe, `/key/generate` com o valor do vault; se existe, `/key/update` com orçamento e modelos. Idempotente (`changed_when` só quando cria ou altera).

## 5. Dados e backup

- `litellm_db` no disco local da `ai-desktop-vm` (`{{ vm_local_data_path }}/litellm-db`), regra DAD-5.
- Dump diário (`pg_dump -Fc`) por timer systemd em `docker-volumes/litellm/db-dumps/` (duas semanas). O script de dump do Nextcloud vira o modelo genérico `ansible/templates/backup-postgres.sh.j2` (container, banco, usuário, destino e arquivos extras como parâmetros), usado pelos dois; o timer do Nextcloud continua igual para quem já o instalou.
- Perder o banco = perder o histórico de uso; as chaves são recriadas pelo `setup-ai-keys.yml` a partir do vault.

## 6. Integrações

| Integração | Mudança |
|---|---|
| Authelia | Cliente OIDC `openwebui` (`two_factor`, PKCE S256, `client_secret_basic` ou o que o Open WebUI exigir — conferido no plano), redirect `https://openwebui.<domínio>/oauth/oidc/callback`; `oidc_clients.openwebui` no vault. |
| Traefik (file provider) | `dynamic_rag_services.yml.j2`: novo router `llm.<domínio>` → `http://{{ ai_desktop_vm_ip_var }}:4000`, com Authelia. Open WebUI como hoje. |
| Blackbox | `litellm` (`/health/liveliness`, já existe) e `open-webui` (`/health`) pela URL da LAN. |
| Homepage | `open-webui` e `litellm` (`llm.`) com `siteMonitor` pela LAN (PNL-1). |
| Catálogo | Saem `openclaw` e `openclaude`; `litellm` ganha `litellm_db`, Exposição `protegida`, Subdomínio `llm`; `ollama` e `open-webui` sem mudança de linha além da página. |
| Índice | Nova **LLM-4**: todo consumidor usa uma chave virtual própria (`LITELLM_KEY_<CLIENTE>`), nunca a `LITELLM_MASTER_KEY`. LLM-2 passa a citar `TYPESAFE_API_KEY`. |
| Vault | `litellm_client_keys.{openwebui,claude_code,n8n}`, `llm_api_keys.typesafe`, `oidc_clients.openwebui.{secret,secret_digest}`. |
| Role `ml-tools` | Sai a instalação do ROCm; fica garantir o grupo `render` e o acesso a `/dev/dri`. |

## 7. Páginas

- **08 (reescrita):** arquitetura, apelidos e como trocar de modelo, Jev (o que é, quando usar, rota de passagem), chaves e orçamentos (`setup-ai-keys.yml`), tela de uso, Open WebUI com OIDC, Ollama/Vulkan (como confirmar no log, como voltar para CPU, baixar modelos), Claude Code (assinatura × `claude-gw`, `~/.claude/settings.json` sem a chave em repositório, teste com `curl` em `/v1/messages`, `/status`), falhas, teste de ponta a ponta.
- **Editadas:** 01 (vault), 00 (`.env.template`), 05 (router `llm.` e cliente OIDC), 06 (segurança: API só na LAN, chaves por cliente), 09 (sondas e painel), backup, `02-visao-geral-arquitetura/07-apis-llm-estrategia.md`, catálogo, índice, `INDEX.md`.

## 8. Falhas

| Falha | Comportamento | O que fazer |
|---|---|---|
| Provedor fora | Fallback para outro provedor no mesmo apelido | Nada; a tela de uso mostra o desvio |
| Orçamento da chave esgotado | O cliente recebe erro de orçamento | Aumentar `litellm_key_budgets` e rodar `setup-ai-keys.yml` |
| Gateway fora | Open WebUI e `claude-gw` param | `claude` pela assinatura continua; `docker logs litellm_proxy` |
| Vulkan não reconhece a GPU | Ollama roda em CPU (mais lento) | Ver o log; documentado na página 08 |
| Banco do LiteLLM perdido | Histórico de uso perdido | Restaurar o dump; ou recriar as chaves com `setup-ai-keys.yml` |
| Authelia fora | Login novo no Open WebUI falha | Formulário local por variável (como no Immich) |

## 9. Verificação

- Novo `tools/wikisync/tests/test_ia.py`:
  - `litellm_config.yaml.j2` renderizado: apelidos presentes, `store_model_in_db: false`, fallbacks, Jev como `typesafe/…`, segredos só por variável;
  - compose: nenhum serviço além do `litellm` recebe chave de provedor ou `LITELLM_MASTER_KEY`; `open-webui` com `LITELLM_KEY_OPENWEBUI`; `ollama` sem `ports`, só `/dev/dri`; `litellm_db` em `{{ vm_local_data_path }}`; imagens sem `latest`/`main`; sem `openclaw`/`openclaude`;
  - Authelia com o cliente `openwebui` (e `validate-config` com o binário 4.38.0);
  - `setup-ai-keys.yml`: tarefas `uri` com `/key/info`, `/key/generate`, `/key/update`, `no_log: true`, `changed_when` controlado;
  - dump genérico renderizado para os dois bancos;
  - router `llm.` no file provider com Authelia; sondas e painel.
- `check`, `sync`, `test`, `build`, `lint`; skills `update-index` e `audit-integrations`.

## 10. Fora de escopo (próximos sub-projetos)

- **4b — Segundo cérebro e RAG:** vaults do Obsidian (vários), sincronização com o servidor (Syncthing, LiveSync ou Nextcloud — a decidir), indexação para perguntas, MCP para Claude/Claude Code lerem, buscarem e escreverem notas com escopo por vault; documentos do Nextcloud e `rag_sources`.
- **4c — Agentes:** orquestrador visual de agentes para Linux/web (equivalente ao Maestri, que é só macOS), posto de agentes Claude Code no servidor, servidores MCP para a IA controlar o homeserver (Docker/Portainer, Ansible, Prometheus/Loki/Grafana, Home Assistant, n8n), IA que observa o servidor, Langfuse, assistente sempre ligado (OpenClaw ou n8n) com desenho de segurança, Jev como roteador/decisor nos agentes.
- VPN (Tailscale), métricas de GPU, modelos locais grandes.

## 11. Riscos

- **Vulkan na RDNA1 dentro do container:** a imagem oficial pode não trazer o driver RADV; o plano confere o conteúdo da imagem e, se preciso, documenta a imagem/variável alternativa. Pior caso: CPU, sem perda funcional.
- **Integração TypeSafe/Jev nova no LiteLLM:** a versão fixada precisa tê-la; sem streaming. Se falhar, o apelido `decisao` cai para `rapido`.
- **Métricas Prometheus do LiteLLM podem ser recurso pago:** sem elas, a observação fica na tela do LiteLLM e nos logs (Loki).
- **Nomes de modelos mudam:** apelidos isolam os clientes; o Claude Code usa nomes reais e precisa de atualização quando a Anthropic lançar modelos.
- **Claude Code pelo gateway depende do LiteLLM repassar os recursos novos do Claude Code** (cabeçalhos beta, campos): a página documenta `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` como contorno.
