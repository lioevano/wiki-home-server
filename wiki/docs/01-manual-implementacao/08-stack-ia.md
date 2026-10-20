---
description: "Stack de IA na ai-desktop-vm: gateway LiteLLM com apelidos de modelo, chaves por cliente e uso, Jev, Open WebUI com OIDC, Ollama com Vulkan e o Claude Code."
---

# Seção 8: Stack de IA (gateway LiteLLM, Open WebUI, Ollama e Claude Code)

A stack de IA roda na `ai-desktop-vm` (`docker/stacks/ai/docker-compose.yml`), gerenciada pelo Portainer da `core-services-vm` pelo Portainer Agent ([seção 4.2](04-configuracao-base-vms-ubuntu.md#42-role-ansible-docker-ansiblerolesinfradocker)). O centro é o **LiteLLM**: um gateway único para todos os modelos, que guarda as chaves dos provedores, dá a cada cliente uma chave própria com orçamento e registra cada chamada (tokens, custo, latência).

```
Open WebUI ────────────┐                          ┌──► Anthropic (Claude) · OpenAI · Gemini
Claude Code (claude-gw)┼──► LiteLLM :4000 (LAN) ──┼──► TypeSafe (Jev, decisões)
n8n / agentes (4c) ────┘     │ Postgres (uso, chaves)└──► Ollama (local, Vulkan na RX 5600 XT)
                             └► métricas :4001 → Prometheus · tela de uso em llm. (Authelia)
```

| Serviço | Papel | Acesso |
|---|---|---|
| `litellm` (container `litellm_proxy`) | Gateway: API OpenAI, API Anthropic (`/v1/messages`) e passagem do Jev (`/typesafe/...`) | API em `http://<ai_desktop_vm_ip_var>:4000`, só na LAN; tela em `https://llm.seudominio.com` (Authelia) |
| `litellm_db` | Postgres: chaves virtuais, orçamentos e registro de uso | interno; disco local da VM |
| `ollama` | Modelos locais pequenos (Vulkan; CPU se a GPU não pegar) | interno (sem porta publicada) |
| `open-webui` | Chat no navegador e no celular (PWA) | `https://openwebui.seudominio.com` (Authelia + OIDC) |
| `diun_ai` | Avisa de imagens novas (n8n → Telegram) | — |

Logs e métricas do host e dos containers vão pelo Grafana Alloy da VM ([seção 4.4](04-configuracao-base-vms-ubuntu.md#44-coleta-com-grafana-alloy-ansiblerolesinfraalloy)); as métricas do LiteLLM saem na porta 4001 para o job `litellm` do Prometheus.

## Modelos e apelidos

Os clientes não citam o modelo do provedor, e sim um **apelido**. Para trocar de LLM a qualquer momento, mude o `model` do apelido em `llm_models` (`group_vars/all/main.yml`, [seção 1](01-maquina-controle-ansible.md)), rode o `setup-ai-volumes.yml` e `docker restart litellm_proxy`; nenhum cliente muda.

| Apelido | Para quê | Modelo inicial |
|---|---|---|
| `principal` | qualidade | `anthropic/claude-sonnet-5-5` (fallback: `gpt-6.1-sol`) |
| `rapido` | barato e ágil | `anthropic/claude-haiku-5-5` (fallback: `gpt-6-luna`) |
| `local` | privado, sem sair de casa | `ollama_chat/llama3.2:3b` |
| `decisao` | decisões rápidas e tipadas (Jev) | `typesafe/jev-latest` |

Os modelos também ficam disponíveis pelo nome próprio (`claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`, `gpt-6.1-sol`, `gpt-6-luna`, `gemini-3.8-flash`). A fonte da verdade é o código: o LiteLLM roda com `store_model_in_db: false`, então modelos criados pela tela não sobrevivem a um restart.

**Jev (`decisao`).** O Jev, da TypeSafe AI, não conversa: recebe um estado e uma pergunta e devolve uma decisão tipada (sim/não com probabilidade, uma escolha entre opções ou uma nota), com confiança. É barato e rápido, bom para triagem, roteamento e "aprovar ou não" dentro de automações e agentes (4c). Os clientes o chamam pela rota unificada `POST http://<ai_desktop_vm_ip_var>:4000/v1/systemone` com `"model": "decisao"` no corpo e a chave virtual do cliente no `Authorization: Bearer`; o LiteLLM resolve o apelido, troca pela `TYPESAFE_API_KEY` e registra o custo. A rota `/typesafe/...` também existe, mas é passagem crua para a API da TypeSafe (não consulta os apelidos; use o nome do modelo deles). Não há streaming.

### Configuração do LiteLLM

O `config.yaml` é gerado pelo `ansible/playbooks/setup-ai-volumes.yml` a partir do template abaixo e de `llm_models`/`llm_fallbacks`. Ele **não tem segredos**: as chaves dos provedores, a chave mestra e o endereço do banco entram pelo ambiente do container (`os.environ/...`), que só o `litellm` recebe.

```yaml title="ansible/templates/litellm_config.yaml.j2"
# ansible/templates/litellm_config.yaml.j2
# Gerado pelo setup-ai-volumes.yml em <NFS>/litellm/config/config.yaml, a partir de llm_models e
# llm_fallbacks (group_vars/all/main.yml). Sem segredos: chaves, chave mestra e banco vêm do ambiente
# do container (os.environ/...), que só o litellm recebe.
model_list:
{% for m in llm_models %}
  - model_name: "{{ m.name }}"
    litellm_params:
      model: "{{ m.model }}"
{% if m.chave is defined %}
      api_key: "os.environ/{{ m.chave }}"
{% endif %}
{% if m.api_base is defined %}
      api_base: "{{ m.api_base }}"
{% endif %}
{% endfor %}

router_settings:
  fallbacks:
{% for f in llm_fallbacks %}
{% for apelido, destinos in f.items() %}
    - {{ apelido }}: {{ destinos | to_json }}
{% endfor %}
{% endfor %}

litellm_settings:
  callbacks: ["prometheus"] # métricas no servidor separado da porta 4001 (--prometheus_metrics_port)

general_settings:
  master_key: "os.environ/LITELLM_MASTER_KEY"
  database_url: "os.environ/DATABASE_URL"
  store_model_in_db: false # a fonte da verdade dos modelos é este arquivo (llm_models)
```

## Deploy

1. **Vault** (`ansible-vault edit inventories/home/group_vars/all/vault.yml`; modelo na [seção 1](01-maquina-controle-ansible.md)): `litellm_master_key`, `litellm_db_password`, `llm_api_keys.{anthropic,openai,google_gemini,typesafe}`, `litellm_client_keys.{openwebui,claude_code,n8n}` (`echo sk-$(openssl rand -hex 24)`), `openwebui_secret_key` e `oidc_clients.openwebui` (`secret` e `secret_digest`, gerados como os do Immich e do Nextcloud na [seção 11](11-fotos-arquivos.md#deploy)).
2. **Authelia:** rode o `setup-core-networking.yml` (cliente OIDC `openwebui` e router `llm.`) e `docker restart authelia traefik`.
3. **Volumes, imagem do Ollama e `ai.env`** (primeiro com `--check`):
   ```bash
   ansible-playbook -i inventories/home/hosts.ini playbooks/setup-ai-volumes.yml --ask-vault-pass --check
   ansible-playbook -i inventories/home/hosts.ini playbooks/setup-ai-volumes.yml --ask-vault-pass
   ```
   O playbook aplica o role `ansible/roles/apps/ml-tools/` (constrói `localhost/homeserver/ollama-vulkan:<ollama_version>` a partir de `ansible/roles/apps/ml-tools/templates/Dockerfile.ollama-vulkan.j2`: a imagem oficial mais o driver Vulkan da AMD), gera o `config.yaml`, cria o banco local do LiteLLM em `/opt/local-data/litellm-db`, instala o dump diário (`ansible/templates/backup-postgres.sh.j2`, timer `backup-litellm-db.timer`) e grava o `/opt/portainer_stack_envs/ai.env` (`0600`).
4. **Portainer:** adicione o ambiente da ai-desktop-vm (**Environments → Add environment → Docker Standalone → Agent**, endereço `<ai_desktop_vm_ip_var>:9001`; o `AGENT_SECRET` vem de `portainer_agent_secret`), depois **Stacks → Add Stack** `ai` com `docker/stacks/ai/docker-compose.yml` e o `ai.env` → **Deploy the stack**.
5. **Chaves dos clientes:** com o LiteLLM no ar, crie as chaves virtuais e seus orçamentos:
   ```bash
   ansible-playbook -i inventories/home/hosts.ini playbooks/setup-ai-keys.yml --ask-vault-pass
   ```
6. **Modelo local:** `docker exec -it ollama ollama pull llama3.2:3b`.

!!! warning "Banco do LiteLLM fora dos snapshots ZFS"
    O Postgres do LiteLLM fica no disco local da VM (`/opt/local-data/litellm-db`), fora dos snapshots ZFS, como os do Immich e do Nextcloud (regra DAD-5). O backup dele é o dump diário do timer `backup-litellm-db.timer` em `docker-volumes/litellm/db-dumps/` (duas semanas), listado na [estratégia de backup](../04-manutencao-recuperacao/02-backup-restore-estrategia.md). As chaves dos clientes também podem ser recriadas a qualquer momento pelo `setup-ai-keys.yml`.

### Variáveis da stack

| Variável | Origem |
|---|---|
| `AI_STACK_LITELLM_CONFIG_PATH`, `AI_STACK_OLLAMA_MODELS_PATH`, `AI_STACK_OPENWEBUI_DATA_PATH`, `AI_STACK_DIUN_DATA_PATH` | NFS + `docker-volumes` |
| `AI_STACK_LITELLM_DB_PATH` | `vm_local_data_path` + `litellm-db` (disco local) |
| `AI_DESKTOP_VM_IP` | `ai_desktop_vm_ip_var` do `hosts.ini` |
| `AI_RENDER_GID` | GID do grupo `render` da VM (lido pelo playbook) |
| `OLLAMA_IMAGE` | `localhost/homeserver/ollama-vulkan:{{ ollama_version }}` |
| `LITELLM_MASTER_KEY`, `LITELLM_DB_PASSWORD` | vault `litellm_master_key`, `litellm_db_password` |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `TYPESAFE_API_KEY` | vault `llm_api_keys.*` (só o `litellm` recebe) |
| `LITELLM_KEY_OPENWEBUI` | vault `litellm_client_keys.openwebui` |
| `OPENWEBUI_SECRET_KEY`, `OPENWEBUI_OAUTH_CLIENT_SECRET` | vault `openwebui_secret_key`, `oidc_clients.openwebui.secret` |
| `OPENWEBUI_LOGIN_FORM` | `openwebui_login_form` (`group_vars`) |
| `NOTIFICACOES_WEBHOOK_TOKEN` | vault (Diun) |

Para mudar variáveis ou segredos: edite o vault ou o `group_vars` pela wiki, rode o `setup-ai-volumes.yml` (sem `--diff`, que imprimiria os segredos), recarregue o `ai.env` em **Env** e **Update the stack**.

## Chaves, orçamentos e uso

Cada cliente tem uma **chave virtual** própria (`litellm_client_keys`), nunca a chave mestra: `openwebui`, `claude_code` e `n8n` (os agentes da próxima etapa ganham as suas). O `ansible/playbooks/setup-ai-keys.yml` cria no LiteLLM as que faltam (inclusive as apagadas pela tela), troca a chave de um cliente quando o valor no vault muda (apaga a antiga pelo alias e cria a nova) e ajusta o orçamento das que mudaram (`litellm_key_budgets`, US$ por mês, renovado a cada 30 dias); pode rodar de novo a qualquer momento. Quando o orçamento de uma chave acaba, aquele cliente recebe erro até a renovação ou até você aumentar o valor e rodar o playbook.

**Ver o uso:** `https://llm.seudominio.com` (atrás do Authelia; entre com a `litellm_master_key`) mostra gasto, tokens e chamadas por chave e por modelo. O Prometheus raspa as métricas do LiteLLM (job `litellm`, porta 4001), e o alerta `llm-gasto-alto` avisa no Telegram quando o gasto das últimas 24 h passa de `llm_gasto_diario_alerta` (US$ 5 por padrão).

## Open WebUI

O Open WebUI fala só com o LiteLLM (com a chave `openwebui`) — o acesso direto ao Ollama fica desligado, então todo uso aparece na tela do LiteLLM. Ele roda com `ENABLE_PERSISTENT_CONFIG=false`: a configuração vem sempre do compose (chave, conexões, formulário de login), e mudanças feitas em *Admin → Settings* nessas áreas não sobrevivem a um restart. Os modelos que aparecem nele são os do `llm_models`, inclusive os apelidos.

O login é o **OIDC do Authelia** (cliente `openwebui`), além do forward-auth na frente: só entra quem está no grupo `admins` do Authelia, que vira administrador. No primeiro acesso:

1. Abra `https://openwebui.seudominio.com` e entre por **Authelia**; se já existia uma conta local com o mesmo e-mail, as duas se juntam.
2. Desligue o formulário local: `openwebui_login_form: false` no `group_vars` (pela wiki), rode o `setup-ai-volumes.yml`, recarregue o `ai.env` e **Update the stack**. Se o Authelia cair, volte para `true` do mesmo jeito.

### Ferramentas: notas

O compose declara, em `TOOL_SERVER_CONNECTIONS`, os dois MCPs do [segundo cérebro](12-segundo-cerebro.md): **Notas (busca)** (`http://qmd:8181/mcp`) e **Notas (escrita)** (`http://notes_escrita:8000/mcp`). O `open-webui` entra na rede `notes_mcp`, criada pela stack `notes`, então a stack `notes` precisa subir **antes** de um novo deploy da stack `ai`. Sem `access_grants`, só administradores usam as ferramentas. Na conversa, ligue-as pelo ícone de ferramentas (ou em *Workspace → Models*, por modelo).

## Claude Code no seu PC

O Claude Code roda no seu PC Linux e tem dois modos:

* **`claude`** — o login da sua assinatura Claude, direto na Anthropic. É o uso do dia a dia; não passa pelo gateway.
* **`claude-gw`** — pelo gateway, com a chave `claude_code`: aparece na tela de uso, respeita o orçamento e serve para automações. Funciona na LAN (de fora, pela VPN quando ela existir). A Anthropic só suporta o Claude Code com modelos Claude, então este perfil usa os nomes reais (`claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`), não os apelidos.

Crie o alias no `~/.bashrc` (a chave fica só no seu PC; nunca num `.claude/settings.json` de repositório):

```bash title="Exemplo: alias claude-gw no ~/.bashrc"
alias claude-gw='ANTHROPIC_BASE_URL=http://<ai_desktop_vm_ip_var>:4000 \
  ANTHROPIC_AUTH_TOKEN=<litellm_client_keys.claude_code> \
  ANTHROPIC_DEFAULT_OPUS_MODEL=claude-opus-5-5 \
  ANTHROPIC_DEFAULT_SONNET_MODEL=claude-sonnet-5-5 \
  ANTHROPIC_DEFAULT_HAIKU_MODEL=claude-haiku-5-5 \
  claude'
```

Com o `ANTHROPIC_AUTH_TOKEN` definido, o Claude Code usa a chave do gateway em vez da assinatura (o login continua salvo e volta quando você usa `claude`). Para conferir: teste o gateway com `curl` e, dentro do Claude Code, `/status` mostra `Anthropic base URL` e `Auth token`:

```bash title="Exemplo: teste do gateway no formato do Claude Code"
curl -sS -w '\n%{http_code}\n' -X POST "http://<ai_desktop_vm_ip_var>:4000/v1/messages" \
  -H "Authorization: Bearer <litellm_client_keys.claude_code>" \
  -H "anthropic-version: 2023-06-01" -H "content-type: application/json" \
  -d '{"model": "claude-haiku-5-5", "max_tokens": 1, "messages": [{"role": "user", "content": "."}]}'
```

Se um recurso novo do Claude Code der erro `400` pelo gateway (campos que o LiteLLM ainda não repassa), use `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` no alias até atualizar o LiteLLM. Mais detalhes na [documentação do Claude Code sobre gateways](https://code.claude.com/docs/en/llm-gateway-connect).

## Ollama e a GPU (Vulkan)

A RX 5600 XT (RDNA1, `gfx1010`) não tem suporte oficial no ROCm; o Ollama usa a GPU por **Vulkan**, com o driver RADV do Mesa que a imagem local `localhost/homeserver/ollama-vulkan` acrescenta à oficial. O prefixo `localhost/` e o `pull_policy: never` garantem que ela nunca venha de um registro (no Portainer, não use *Re-pull image* nela), e o Diun a ignora. O container recebe só `/dev/dri` e o grupo `render`.

* **Conferir:** `docker logs ollama | grep -i -E "vulkan|gpu"` deve listar a placa; com um modelo carregado, `docker exec ollama ollama ps` mostra `GPU` na coluna de processador.
* **Se não pegar:** o Ollama roda em CPU sozinho — mais lento, mas funciona. Para forçar CPU (por exemplo, para liberar a GPU), acrescente `OLLAMA_VULKAN=0` ao `environment` do `ollama`.
* **Atualizar o Ollama:** troque `ollama_version`, rode o `setup-ai-volumes.yml` (constrói a imagem nova) e **Update the stack**.
* **Baixar modelos:** `docker exec -it ollama ollama pull <modelo>`; os 6 GB de VRAM comportam modelos de até uns 7–8B quantizados. Para usá-lo pelos clientes, aponte o apelido `local` (ou um item novo de `llm_models`) para `ollama_chat/<modelo>`.

## Falhas

| Situação | Comportamento | O que fazer |
|---|---|---|
| Provedor fora do ar | O LiteLLM tenta o fallback do apelido | Nada; a tela de uso mostra o desvio |
| Orçamento de uma chave esgotado | Aquele cliente recebe erro de orçamento | Aumente `litellm_key_budgets` e rode o `setup-ai-keys.yml` |
| Gateway fora | Open WebUI e `claude-gw` param | `claude` (assinatura) continua; `docker logs litellm_proxy` |
| GPU não reconhecida | Ollama em CPU | Ver a seção do Vulkan acima |
| Banco do LiteLLM perdido | Histórico de uso perdido | Restaure o dump de `docker-volumes/litellm/db-dumps/` (`pg_restore`) ou recrie as chaves com o `setup-ai-keys.yml` |
| Authelia fora | Login novo no Open WebUI falha | `openwebui_login_form: true` e o fluxo acima |

## Teste de ponta a ponta

1. `curl -s http://<ai_desktop_vm_ip_var>:4000/health/liveliness` responde; `curl -s http://<ai_desktop_vm_ip_var>:4001/metrics | head` mostra métricas `litellm_`.
2. No Open WebUI (entrando pelo Authelia), converse com `principal`, `rapido` e `local`; na tela `llm.`, as três chamadas aparecem na chave `openwebui`.
3. `claude-gw` responde e `/status` mostra o gateway; a chamada aparece na chave `claude_code`.
4. Uma chamada a `/v1/systemone` com `"model": "decisao"` volta uma decisão com confiança.
5. `docker exec ollama ollama ps` mostra o modelo local na GPU (ou CPU, se o Vulkan não pegou).
6. `sudo systemctl start backup-litellm-db.service` cria um `litellm-<data>.dump` em `docker-volumes/litellm/db-dumps/`.
