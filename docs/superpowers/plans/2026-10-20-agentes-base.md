# Agentes — base: Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hub de MCPs (agentgateway) na `core-services-vm` com rota `leitura` pública (via mcp-auth-proxy em `servidor.`) e rota `controle` só na LAN; MCP `ops` próprio (containers e stacks pela API do Portainer, Ansible pelo runner embutido); `mcp-grafana`; MCPs do Home Assistant e do n8n; Langfuse na `ai-desktop-vm` recebendo o LiteLLM e o hub.

**Architecture:** O `config.yaml` do agentgateway sai de um template Jinja alimentado pelo `group_vars` (alvos, lista de leitura) e pelo vault (só hashes das chaves; tokens dos alvos por `$VAR` do ambiente). O `ops` é um pacote Python pequeno cuja lógica (política, Portainer, runner, auditoria) é testável sem rede e sem FastMCP; `server.py` só registra as ferramentas do modo escolhido. Duas instâncias de cada MCP com escrita (`*_leitura`/`*_controle`) garantem que a rota pública só alcança código que não escreve.

**Tech Stack:** agentgateway v1.6.0, grafana/mcp-grafana 2.1.1, mcp-auth-proxy v2.10.2, Python 3.13 + FastMCP 4.1.2 + ansible-core 2.21.5, Portainer CE 2.19.4 (API), Home Assistant 2026.10.2 (`/api/mcp`), n8n 2.44.4 (`/mcp-server/http`), Grafana 13.2.4, Langfuse 4.66.0 (web, worker, Postgres 17, ClickHouse 25.12, Redis 7, MinIO), LiteLLM v1.106.0 (`langfuse_otel`), Authelia 4.38, pytest, MkDocs.

**Spec:** `docs/superpowers/specs/2026-10-20-agentes-base-design.md` (com a seção 14, "Ajustes do plano", acrescentada na Task 0).

## Global Constraints

- Wiki-first. **Literais:** `group_vars/all/main.yml` e `vault.yml.example` (01), `.env.template` (00), `configuration.yml.j2` do Authelia e `dynamic_rag_services.yml.j2` (05), `litellm_config.yaml.j2` (08), `ansible/templates/agents/*.j2` (página nova 13). **Estruturais** (citados com caminho na página 13): `docker/stacks/agents/docker-compose.yml`, `docker/stacks/langfuse/docker-compose.yml`, `docker/images/ops/**` (código do `ops`), `playbooks/setup-agents-volumes.yml`, `playbooks/setup-langfuse-volumes.yml`, `docker/stacks/apps/docker-compose.yml`, `docker/stacks/ai/docker-compose.yml`, `prometheus.yml.j2`, `homepage/services.yaml.j2`, `grafana/alerting/rules.yml.j2`.
- Ambiente: `export HOMESERVER_VENV=$HOME/.venvs/homeserver PATH=$HOME/.local/bin:$PATH`; `check` (só `REF-PENDING`) → `sync` → `sync --yes` → `test` → lint numa cópia local → build estrito num clone local do HEAD.
- Testes: `tools/wikisync/tests/test_agentes_base.py` (infra; helpers de `test_observabilidade`, `test_midia`, `test_fotos_arquivos`, `test_segundo_cerebro`) e `tools/wikisync/tests/test_ops.py` (unitários do `ops`; importa `server/docker/images/ops/ops` por `sys.path`; **sem** FastMCP, rede nem `ansible-playbook` reais).
- **Versões (`group_vars`):** `agentgateway_version: "v1.6.0"`, `mcp_grafana_version: "2.1.1"`, `ops_fastmcp_version: "4.1.2"`, `ops_ansible_core_version: "2.21.5"`, `langfuse_version: "4.66.0"`. Fixadas no compose `apps`: `grafana/grafana-oss:13.2.4`, `docker.n8n.io/n8nio/n8n:2.44.4`, `ghcr.io/home-assistant/home-assistant:2026.10.2`. Langfuse: `docker.langfuse.com/langfuse/langfuse:4.66.0` e `…/langfuse-worker:4.66.0`, `docker.io/clickhouse/clickhouse-server:25.12`, `docker.io/redis:7.4-alpine`, `docker.io/postgres:17-alpine`, MinIO pelo `cgr.dev/chainguard/minio@sha256:<digest do dia>` (sem tag `latest`).
- **Nomes e portas:** stack `agents` (core): `agentgateway` (rota `leitura` em `:4000` só na rede interna; rota `controle` em `${CORE_SERVICES_VM_IP_VAR}:4100:4100`; métricas `:15020` interna; admin `localhost:15000` não publicado), `mcp_auth_servidor`, `mcp_grafana_leitura`, `mcp_grafana_controle` (`:8000`), `ops_leitura`, `ops_controle` (`:8000`, caminho `/mcp`); rede `agents_internal`. Stack `langfuse` (ai): `langfuse_web` (`${AI_DESKTOP_VM_IP}:3100:3000`), `langfuse_worker`, `langfuse_db`, `langfuse_clickhouse`, `langfuse_redis`, `langfuse_minio`. Subdomínios `servidor` (MCP leitura) e `langfuse`. Imagem local `localhost/homeserver/ops:{{ ops_fastmcp_version }}`.
- **Alvos do hub (nomes = prefixo das ferramentas, `prefixMode: always`):** `grafana`, `ops`, `homeassistant` (`http://homeassistant:8123/api/mcp`, `backendAuth` `$HOMEASSISTANT_MCP_TOKEN`), `n8n` (`http://n8n:5678/mcp-server/http`, `$N8N_MCP_TOKEN`). Na rota `leitura`, `grafana`/`ops` apontam para `mcp_grafana_leitura`/`ops_leitura`; na `controle`, para os `_controle`.
- **`group_vars` (novas):** `agents_leitura: {grafana: "*", ops: "*", homeassistant: ["GetLiveContext"], n8n: ["search_workflows"]}`; `ops_containers_protegidos: [traefik, authelia, cloudflared, portainer, agentgateway, mcp_auth_servidor, ops_leitura, ops_controle]`; `ops_stacks_protegidas: [core, agents]`; `ops_playbooks_permitidos` (lista `{nome, descricao}`: os `setup-*-volumes.yml`, `setup-ai-keys.yml`, `setup-base-ubuntu.yml`, `setup-monitoring-stack-volumes.yml`; **sem** `vm-deploy.yml` e `setup-proxmox-host.yml`); `ops_endpoints: {core: "local", ai: "ai-desktop-vm"}` (nomes dos ambientes no Portainer); `ops_repo_url: "https://github.com/lioevano/wiki-home-server.git"`; `ops_plano_validade_min: 30`; `langfuse_retencao_dias: 30`.
- **Vault (novas):** `agents_api_keys.{claude_code,agentes}` (valores `ag-` + `openssl rand -hex 24`), `grafana_sa_tokens.{leitura,controle}`, `homeassistant_mcp_token`, `n8n_mcp_token`, `portainer_api_key`, `ops_ssh_private_key` (bloco PEM), `ops_vault_password`, `langfuse_secrets.{salt,encryption_key,nextauth_secret,db_password,clickhouse_password,redis_password,minio_password,public_key,secret_key}` (`public_key` começa com `pk-lf-`, `secret_key` com `sk-lf-`), `oidc_clients.langfuse.{secret,secret_digest}`.
- Cliente OIDC `langfuse`: `client_secret_basic`, `require_pkce: true`, `pkce_challenge_method: S256`, `two_factor`, escopos `openid profile email groups`, redirect `https://langfuse.{{ base_domain }}/api/auth/callback/custom`. Cliente `mcp` ganha o redirect `https://servidor.{{ base_domain }}/.auth/oidc/callback`.
- Nada de `docker compose up/down`, `ansible-playbook` sem `--check`/`--syntax-check`, `ansible-vault`, `ssh` ou `git push`. Commits com o trailer da sessão. Execução direta em `main`, com ledger.

## Review Focus

1. **Ferramenta de escrita alcançável pela rota pública:** a rota `leitura` só tem alvos `*_leitura` + HA/n8n com lista fechada; `ops_leitura` não registra ferramenta de controle; `mcp_grafana_leitura` com `--disable-write` → Tasks 2, 5.
2. **`ansible_aplicar` sem simulação equivalente:** `plano_id` inexistente, vencido, de outro playbook/limite ou com commit diferente → recusa; duas execuções simultâneas → a segunda recusa → Task 3.
3. **Chave de cliente ou token de alvo em texto puro no `config.yaml`** (NFS, `0644`): só `keyHash: "sha256:…"` e `$VAR` → Task 5.
4. **Saída de Ansible ou log de container vazando segredo ou estourando o contexto:** saídas truncadas (`OPS_LIMITE_SAIDA=20000` caracteres) e linhas com `vault`/`password`/`token`/`secret` (sem maiúsculas/minúsculas) mascaradas → Tasks 2, 3.
5. **Reinício do próprio caminho de controle** (Traefik, Authelia, Portainer, hub, `ops`) ou redeploy da stack `core`/`agents` pela IA: recusados com mensagem clara → Task 2.

---

### Task 0: Ajustes do plano na especificação

**Files:** Modify `docs/superpowers/specs/2026-10-20-agentes-base-design.md` (seção nova 14)

- [ ] **Step 1:** Seção "14. Ajustes do plano": **sem regra de UFW** para a 4100 (portas publicadas pelo Docker não passam pelo UFW — já documentado no role `docker`; a proteção é o bind no IP da LAN + chave); imagem `grafana/mcp-grafana:2.1.1` com `--allowed-hosts` do nome do serviço; Home Assistant e n8n por token Bearer (o MCP do HA aceita token de longa duração); Langfuse na porta 3100 da ai; callback `langfuse_otel` do LiteLLM (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_OTEL_HOST`); o runner aplica a chave SSH por `-e ansible_ssh_private_key_file=…` (variável do inventário vence o `--private-key`) e só funciona depois que o `vault.yml` criptografado existir no repositório.
- [ ] **Step 2: Commit** `docs(spec): ajustes do plano na base dos agentes`

### Task 1: Versões fixadas e variáveis da 4c1

**Files:**
- Modify: `server/docker/stacks/apps/docker-compose.yml` (imagens de `grafana`, `n8n`, `homeassistant` da Global Constraints)
- Modify: `main.yml` (versões, `agents_*`, `ops_*`, `langfuse_retencao_dias`) e `vault.yml.example` (todas as chaves da Global Constraints) — página 01; página 07 (versões fixadas e por quê)
- Test: `tools/wikisync/tests/test_agentes_base.py`

- [ ] **Step 1: Write the failing tests**
  - `test_versoes_fixadas_de_quem_o_hub_depende`: imagens de `grafana`, `n8n`, `homeassistant` no compose `apps` iguais às da Global Constraints.
  - `test_variaveis_agentes`: `main.yml` com `agents_leitura == {"grafana": "*", "ops": "*", "homeassistant": ["GetLiveContext"], "n8n": ["search_workflows"]}`; `ops_stacks_protegidas == ["core", "agents"]`; `{"traefik", "authelia", "cloudflared", "portainer", "agentgateway"} <= set(ops_containers_protegidos)`; nenhum item de `ops_playbooks_permitidos` com `nome` `vm-deploy.yml` ou `setup-proxmox-host.yml`, e todo `nome` existe em `server/ansible/playbooks/`; `vault.yml.example` com todas as chaves novas (`agents_api_keys.claude_code` começando com `ag-`, `langfuse_secrets.public_key` com `pk-lf-`, `secret_key` com `sk-lf-`).
- [ ] **Step 2: Run** `dev.py test` → FAIL.
- [ ] **Step 3: Implement** pela wiki (01, 07) e no compose `apps`; `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(agentes): versões fixadas de Grafana, n8n e Home Assistant e variáveis da base`

### Task 2: MCP `ops` — política, Portainer e auditoria

**Files:**
- Create: `server/docker/images/ops/ops/__init__.py`, `config.py`, `politica.py`, `portainer.py`, `auditoria.py`, `ferramentas.py`
- Test: `tools/wikisync/tests/test_ops.py`

**Interfaces:**
- Produces:
  - `config.py`: `@dataclass(frozen=True) Config(modo: Literal["leitura","controle"], portainer_url: str, portainer_api_key: str, endpoints: dict[str, str], containers_protegidos: frozenset[str], stacks_protegidas: frozenset[str], playbooks: dict[str, str], limite_saida: int, webhook_url: str, webhook_token: str, repo_dir: str, repo_url: str, inventario: str, chave_ssh: str, plano_validade_s: int)`; `Config.do_ambiente(env: Mapping[str, str]) -> Config` (variáveis `OPS_MODO`, `PORTAINER_URL`, `PORTAINER_API_KEY`, `OPS_ENDPOINTS` JSON, `OPS_CONTAINERS_PROTEGIDOS` e `OPS_STACKS_PROTEGIDAS` separados por vírgula, `OPS_PLAYBOOKS` JSON, `OPS_LIMITE_SAIDA` padrão `20000`, `NOTIFICACOES_WEBHOOK_URL`, `NOTIFICACOES_WEBHOOK_TOKEN`, `OPS_REPO_DIR`, `OPS_REPO_URL`, `OPS_INVENTARIO`, `OPS_CHAVE_SSH`, `OPS_PLANO_VALIDADE_MIN`).
  - `politica.py`: `class Recusado(Exception)`; `limpar_saida(texto: str, limite: int) -> str` (mascara linhas que contêm `vault`, `password`, `token` ou `secret`, sem maiúsculas/minúsculas, como `[linha omitida: possível segredo]`; trunca ao `limite` mantendo o **fim** e prefixo `[…truncado: N caracteres]`); `checar_container(nome: str, cfg: Config) -> None`; `checar_stack(nome: str, cfg: Config) -> None`.
  - `portainer.py`: `Http = Callable[[str, str, dict | None], tuple[int, bytes]]` (método, caminho, corpo JSON) e `class Portainer(cfg: Config, http: Http)` com `containers(vm: str | None) -> list[dict]` (campos `vm`, `nome`, `imagem`, `estado`, `saude`, `reinicios`), `logs(nome: str, linhas: int) -> str` (desmultiplexa o stream do Docker: cabeçalho de 8 bytes), `reiniciar(nome: str) -> None`, `stacks() -> list[dict]` (`nome`, `vm`, `estado`), `redeploy(nome: str, puxar_imagens: bool) -> None` (`GET /api/stacks/{id}/file` → `PUT /api/stacks/{id}?endpointId={eid}` com `stackFileContent`, `env` atual, `prune: false`, `pullImage`). Cabeçalho `X-API-Key`; endpoints resolvidos por nome via `GET /api/endpoints`; container localizado por nome nas duas VMs (`/api/endpoints/{eid}/docker/containers/json?all=1`).
  - `auditoria.py`: `registrar(acao: str, alvo: str, resultado: str, duracao_s: float, detalhe: str = "", enviar: Callable[[dict], None] | None = None) -> dict` — imprime uma linha JSON (`{"evento": "ops_acao", ...}`) e chama `enviar` (aviso no Telegram via webhook, `titulo`/`mensagem`, falha de envio só é registrada, nunca levanta).
  - `ferramentas.py`: `@dataclass Ferramenta(nome: str, funcao: Callable, destrutiva: bool, descricao: str)`; `ferramentas(cfg: Config, portainer: Portainer, runner: "Runner | None", enviar) -> dict[str, Ferramenta]` — modo `leitura`: `containers_listar`, `container_logs`, `stacks_listar`, `playbooks_listar`; modo `controle`: essas + `container_reiniciar`, `stack_redeploy`, `ansible_check`, `ansible_aplicar` (as quatro com `destrutiva=True` exceto `ansible_check`, que é `False`). Ferramentas de controle checam a política, chamam `auditoria.registrar` e devolvem texto curto.

- [ ] **Step 1: Write the failing tests** (Portainer falso: dicionário `(método, caminho) → (status, corpo)`; `enviar` coletando chamadas)
  - `test_modo_leitura_nao_tem_controle`: `set(ferramentas(cfg_leitura, …)) == {"containers_listar", "container_logs", "stacks_listar", "playbooks_listar"}`; modo `controle` tem as 8; `container_reiniciar`, `stack_redeploy`, `ansible_aplicar` com `destrutiva is True`.
  - `test_containers_protegidos_recusados`: `container_reiniciar("traefik")` → `Recusado`; nenhuma chamada `POST` no Portainer falso; `registrar` chamado com `resultado == "recusado"`.
  - `test_reiniciar_container`: `container_reiniciar("jellyfin")` → `POST /api/endpoints/<id da core>/docker/containers/<id>/restart`; aviso enviado com `jellyfin` no texto.
  - `test_stack_protegida_e_redeploy`: `stack_redeploy("core")` → `Recusado`; `stack_redeploy("media", puxar_imagens=True)` → `PUT /api/stacks/7?endpointId=1` com `pullImage is True`, `prune is False`, `stackFileContent` igual ao do `GET …/file` e `env` preservado.
  - `test_logs_desmultiplexa_e_limpa`: corpo com frames Docker (stdout e stderr), uma linha `DB_PASSWORD=x` e texto maior que o limite → a linha some (máscara), saída ≤ limite + prefixo, termina com a última linha do log.
  - `test_config_do_ambiente`: `Config.do_ambiente({...})` lê JSON e listas; `OPS_MODO` fora de `leitura`/`controle` → `ValueError`.
  - `test_aviso_que_falha_nao_derruba`: `enviar` que levanta → a ação conclui e a linha JSON tem `"aviso": "falhou"`.
- [ ] **Step 2: Run** `dev.py test` → FAIL.
- [ ] **Step 3: Implement** os módulos (só biblioteca padrão; `urllib.request` no `Http` real, montado em `server.py` na Task 3).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(agentes): MCP ops — containers e stacks pela API do Portainer, com política e auditoria`

### Task 3: MCP `ops` — runner Ansible, servidor e imagem

**Files:**
- Create: `server/docker/images/ops/ops/runner.py`, `server.py`, `server/docker/images/ops/Dockerfile`, `requirements.txt`
- Test: `tools/wikisync/tests/test_ops.py`

**Interfaces:**
- Consumes: Task 2 (`Config`, `Recusado`, `limpar_saida`, `auditoria.registrar`, `ferramentas`).
- Produces:
  - `runner.py`: `Executar = Callable[[list[str], str, int], tuple[int, str]]` (argv, cwd, timeout_s) e `class Runner(cfg: Config, executar: Executar, agora: Callable[[], float] = time.time)` com `check(playbook: str, limite: str | None) -> dict` (`git -C <repo> pull --ff-only`; commit por `git rev-parse HEAD`; `ansible-playbook -i <inventario> <playbook> --check --diff [-l limite] -e ansible_ssh_private_key_file=<chave>`; devolve `{"plano_id", "commit", "rc", "saida"}`) e `aplicar(plano_id: str) -> dict` (mesmo argv sem `--check --diff`; recusa se o plano não existe, passou de `plano_validade_s`, ou o `HEAD` após `pull` mudou; plano consumido após uso). Uma execução por vez (`threading.Lock` com `acquire(blocking=False)`; ocupado → `Recusado("outra execução em andamento")`). Playbook fora de `cfg.playbooks` → `Recusado`. Timeout: check 900 s, aplicar 3600 s.
  - `server.py`: `main()` — `Config.do_ambiente(os.environ)`; `Portainer` com `Http` real; `Runner` só no modo `controle`; registra cada `Ferramenta` no FastMCP com `annotations` (`readOnlyHint` = não destrutiva e não `ansible_check`; `destructiveHint` = `destrutiva`); `mcp.run(transport="http", host="0.0.0.0", port=8000, path="/mcp")`.
  - `Dockerfile`: `FROM python:3.13-slim`; `apt-get install -y --no-install-recommends git openssh-client`; `pip install --no-cache-dir -r requirements.txt` (`fastmcp=={{ ops_fastmcp_version }}`, `ansible-core=={{ ops_ansible_core_version }}` — o arquivo é template renderizado pelo playbook, ou `ARG`s passados no build), coleções `ansible.posix`, `community.general`, `community.docker` (`ansible-galaxy collection install` na imagem); `USER` não-root; `ENTRYPOINT ["python", "-m", "ops.server"]`.

- [ ] **Step 1: Write the failing tests** (`executar` falso registrando argv e devolvendo saídas programadas; `agora` controlado)
  - `test_check_gera_plano`: `check("setup-media-stack-volumes.yml", None)` → argv do `ansible-playbook` contém `--check`, `--diff`, `-i`, `-e`, `ansible_ssh_private_key_file=/segredos/id_ed25519`; `git pull --ff-only` antes; devolve `plano_id` e `commit`.
  - `test_aplicar_exige_plano_valido`: `aplicar("inexistente")` → `Recusado`; plano com `agora` 31 min depois → `Recusado`; `HEAD` diferente após `pull` → `Recusado`; plano válido → argv sem `--check`/`--diff`, mesmo playbook e limite; segundo `aplicar` do mesmo `plano_id` → `Recusado`.
  - `test_playbook_fora_da_lista`: `check("vm-deploy.yml", None)` → `Recusado`, nenhum `executar`.
  - `test_uma_execucao_por_vez`: com o lock ocupado, `check` → `Recusado("outra execução em andamento")`.
  - `test_saida_do_ansible_limpa`: saída com `vault_password: x` e 50 000 caracteres → máscara e truncamento.
  - `test_imagem_ops`: `Dockerfile` usa `python:3.13-slim`, instala `git` e `openssh-client`, não roda como root; `requirements.txt` (renderizado com as versões do `main.yml`) fixa `fastmcp==4.1.2` e `ansible-core==2.21.5`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(agentes): runner Ansible do ops com simulação obrigatória e servidor MCP`

### Task 4: Stack `agents` e preparação da core

**Files:**
- Create: `server/docker/stacks/agents/docker-compose.yml` (`mcp_grafana_leitura`, `mcp_grafana_controle`, `ops_leitura`, `ops_controle`; `agentgateway` e `mcp_auth_servidor` entram nas Tasks 5 e 6)
- Create: `server/ansible/playbooks/setup-agents-volumes.yml` (`hosts: core_services`): diretórios em `{{ vm_local_data_path }}/ops/{repo,segredos}` e `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/agentgateway`; `segredos/id_ed25519` (`ops_ssh_private_key`) e `segredos/vault_pass` (`ops_vault_password`) com `mode: '0400'`, dono `docker_puid`, `no_log: true`; `git clone` do `ops_repo_url` se não existir; build da imagem `ops` (Dockerfile e `requirements.txt` copiados para `/opt/ops-image`, `force_source` ligado aos `register`); `agents.env` `0600`
- Modify: `.env.template` (00)
- Test: `tools/wikisync/tests/test_agentes_base.py`

**Interfaces:**
- Produces: `http://mcp_grafana_leitura:8000/mcp`, `http://mcp_grafana_controle:8000/mcp`, `http://ops_leitura:8000/mcp`, `http://ops_controle:8000/mcp` na rede `agents_internal`; `agents.env` com `CORE_SERVICES_VM_IP_VAR`, `GRAFANA_SA_TOKEN_LEITURA`, `GRAFANA_SA_TOKEN_CONTROLE`, `PORTAINER_API_KEY`, `HOMEASSISTANT_MCP_TOKEN`, `N8N_MCP_TOKEN`, `NOTIFICACOES_WEBHOOK_TOKEN`, `OPS_IMAGE`, `OPS_DATA_PATH`, `AGENTGATEWAY_CONFIG_PATH`, `MCP_OIDC_CLIENT_SECRET`, `MCP_AUTH_HMAC_SECRET`, `MCP_AUTH_SERVIDOR_DATA_PATH`, `LANGFUSE_OTEL_AUTH` (Basic base64 de `public_key:secret_key`), `AI_DESKTOP_VM_IP`.

- [ ] **Step 1: Write the failing tests**
  - `test_grafana_mcp_leitura_e_controle`: imagem `grafana/mcp-grafana:2.1.1`; `command` do `leitura` contém `-t`, `streamable-http`, `--address`, `0.0.0.0:8000`, `--allowed-hosts`, `mcp_grafana_leitura:8000`, `--disable-write`; o `controle` igual sem `--disable-write`; env `GRAFANA_URL == "http://grafana:3000"` e tokens `${GRAFANA_SA_TOKEN_LEITURA}`/`${GRAFANA_SA_TOKEN_CONTROLE}`; redes `agents_internal` e `internal_services`; sem `ports`.
  - `test_ops_leitura_sem_segredos_de_escrita`: `ops_leitura` com `OPS_MODO=leitura` e **nenhum** volume (sem `segredos`, sem `repo`); `ops_controle` com `OPS_MODO=controle`, `${OPS_DATA_PATH}/segredos:/segredos:ro`, `${OPS_DATA_PATH}/repo:/repo`; ambos com `PORTAINER_URL=http://portainer:9000`, redes `agents_internal` e `proxy`, sem `ports`, `image == "${OPS_IMAGE}"`, `pull_policy: never`; `OPS_PLAYBOOKS`, `OPS_CONTAINERS_PROTEGIDOS`, `OPS_STACKS_PROTEGIDAS`, `OPS_ENDPOINTS` vindos do `agents.env` (gerados do `group_vars`).
  - `test_segredos_do_runner`: tarefas `copy` da chave e da senha com `mode: '0400'`, `no_log: true`, `dest` em `{{ vm_local_data_path }}/ops/segredos/`; `agents.env` `0600`; `_vars_compose(AGENTS) <= set(_configs(PB_AGENTS, "agents.env")) | COMUNS`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS; lint.
- [ ] **Step 5: Commit** `feat(agentes): stack agents com mcp-grafana e ops em pares leitura/controle`

### Task 5: Hub (agentgateway)

**Files:**
- Create: `server/ansible/templates/agents/agentgateway.yaml.j2` (literal na página 13), renderizado pelo playbook em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/agentgateway/config.yaml` (`0644`)
- Modify: compose `agents` (serviço `agentgateway`, imagem `cr.agentgateway.dev/agentgateway:{{ agentgateway_version }}` literal `v1.6.0`, `-f /config/config.yaml`), playbook
- Test: `tools/wikisync/tests/test_agentes_base.py`

**Interfaces:**
- Consumes: Task 4 (alvos internos), vault (`agents_api_keys`).
- Produces: rota `leitura` em `http://agentgateway:4000/mcp`; rota `controle` em `http://<ip core>:4100/mcp`; métricas `agentgateway:15020`.

- [ ] **Step 1: Write the failing tests** (render com `agents_leitura` do `main.yml`, `agents_api_keys` falsos e `langfuse` de teste)
  - `test_rota_leitura_so_le`: bind `4000`: alvos `grafana → http://mcp_grafana_leitura:8000/mcp`, `ops → http://ops_leitura:8000/mcp`, `homeassistant`, `n8n`; nenhum alvo `_controle`; `mcpAuthorization.rules` só `allow`, exatamente `mcp.tool.target == "grafana"`, `mcp.tool.target == "ops"`, `mcp.tool.target == "homeassistant" && mcp.tool.name in ["GetLiveContext"]`, `mcp.tool.target == "n8n" && mcp.tool.name in ["search_workflows"]`; sem `apiKey` (o OAuth fica no proxy).
  - `test_rota_controle_com_chave`: bind `4100`: alvos `_controle` + `homeassistant` + `n8n`; `apiKey.mode == "strict"`, cabeçalho `Authorization` com prefixo `Bearer `, `keys` com `keyHash == "sha256:" + sha256(valor)` e `metadata.cliente` para `claude_code` e `agentes`; nenhum valor de chave em texto no render.
  - `test_hub_sem_segredos_e_tolerante`: o render não contém nenhum valor de `homeassistant_mcp_token`/`n8n_mcp_token` (só `$HOMEASSISTANT_MCP_TOKEN`/`$N8N_MCP_TOKEN` em `backendAuth.key`); todo backend `mcp` com `failureMode: failOpen` e `prefixMode: always`; `config.statsAddr == "0.0.0.0:15020"`; `config.tracing.otlpEndpoint` = `http://<ai_desktop_vm_ip_var>:3100/api/public/otel`, `otlpProtocol: http`, cabeçalho `Authorization: "Basic $LANGFUSE_OTEL_AUTH"`; `config.logging.format == "json"`.
  - `test_hub_no_compose`: `agentgateway` publica **só** `${CORE_SERVICES_VM_IP_VAR}:4100:4100`; não publica 15000 nem 4000; redes `agents_internal` e `proxy`; config montado `:ro`.
  - `test_hub_valida` (pula se o binário `agentgateway` não estiver no `PATH`): `agentgateway --validate-only -f <render>` retorna 0.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** pela página 13; `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(agentes): hub agentgateway com rota de leitura e rota de controle por chave`

### Task 6: Conector público `servidor.`

**Files:**
- Modify: compose `agents` (`mcp_auth_servidor`: imagem `ghcr.io/sigbit/mcp-auth-proxy:v2.10.2`, `command: ["http://agentgateway:4000/mcp"]`, labels Traefik `servidor` **sem** middleware do Authelia, dados em `${MCP_AUTH_SERVIDOR_DATA_PATH}` local)
- Modify: `configuration.yml.j2` (05): redirect novo no cliente `mcp`; `bypass` para `servidor.` antes da curinga
- Test: `tools/wikisync/tests/test_agentes_base.py`

- [ ] **Step 1: Write the failing tests**
  - `test_proxy_servidor`: env como no `test_proxies_mcp` da 4b com `EXTERNAL_URL == "https://servidor.${BASE_DOMAIN_FROM_VAULT}"`, `OIDC_ALLOWED_ATTRIBUTES == "/groups=admins"`, `TRUSTED_PROXIES` da rede do Traefik; labels com ``Host(`servidor.${BASE_DOMAIN_FROM_VAULT}`)`` e sem `authelia-forwardauth@docker`; sem `ports`.
  - `test_authelia_servidor`: cliente `mcp` com os três redirects (`notas`, `escrita`, `servidor`); regra `bypass` para `servidor.` antes da curinga; `test_authelia_validate_config` segue passando.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(agentes,autenticacao): conector Servidor com OAuth pelo Authelia`

### Task 7: Langfuse

**Files:**
- Create: `server/docker/stacks/langfuse/docker-compose.yml` (base: `docker-compose.yml` oficial da v4.66.0, com as imagens fixadas, dados em `{{ vm_local_data_path }}/langfuse/{postgres,clickhouse,minio,redis}`, sem portas além da `langfuse_web`)
- Create: `server/ansible/playbooks/setup-langfuse-volumes.yml` (`hosts: ai_desktop`; diretórios; `langfuse.env` `0600`)
- Modify: `configuration.yml.j2` (cliente `langfuse`); `dynamic_rag_services.yml.j2` (router `langfuse.` → `:3100` com Authelia); `litellm_config.yaml.j2` (`callbacks: ["prometheus", "langfuse_otel"]`); `setup-ai-volumes.yml` (`ai.env` com `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_OTEL_HOST=http://{{ ai_desktop_vm_ip_var }}:3100`); compose `ai` (as três no `litellm`)
- Test: `tools/wikisync/tests/test_agentes_base.py` (e `test_ia.py`, cujo teste de callbacks passa a esperar os dois)

- [ ] **Step 1: Write the failing tests**
  - `test_langfuse_stack`: serviços da Global Constraints; imagens fixadas (nenhuma `latest`, `:4`, `:7` sem patch); só `langfuse_web` publica, em `${AI_DESKTOP_VM_IP}:3100:3000`; volumes de dados começando com caminhos de `{{ vm_local_data_path }}/langfuse/`; env da web: `NEXTAUTH_URL == "https://langfuse.${BASE_DOMAIN_FROM_VAULT}"`, `AUTH_DISABLE_USERNAME_PASSWORD == "true"`, `AUTH_DISABLE_SIGNUP == "false"`, `AUTH_CUSTOM_ISSUER == "https://auth.${BASE_DOMAIN_FROM_VAULT}"`, `AUTH_CUSTOM_CLIENT_ID == "langfuse"`, `AUTH_CUSTOM_SCOPE == "openid profile email groups"`, `AUTH_CUSTOM_CHECKS == "pkce,state"`, `LANGFUSE_INIT_PROJECT_PUBLIC_KEY == "${LANGFUSE_PUBLIC_KEY}"`, `TELEMETRY_ENABLED == "false"`; segredos só por `${…}`.
  - `test_cliente_oidc_langfuse`: valores da Global Constraints; `validate-config` passa com cinco clientes.
  - `test_litellm_manda_para_o_langfuse`: `litellm_settings.callbacks == ["prometheus", "langfuse_otel"]`; env do `litellm` com `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_OTEL_HOST`; nenhum outro serviço do compose `ai` recebe `LANGFUSE_SECRET_KEY`.
  - `test_rota_langfuse`: router `langfuse.` → `http://<ip ai>:3100` com `authelia-forwardauth@docker`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; `check` → `sync --yes`.
- [ ] **Step 4: Run** → PASS (inclusive `test_ia.py`).
- [ ] **Step 5: Commit** `feat(agentes,ia): Langfuse com login pelo Authelia recebendo o LiteLLM e o hub`

### Task 8: Métricas, sondas, alerta e painel

**Files:**
- Modify: `prometheus.yml.j2` (job `agentgateway` → `agentgateway:15020`; blackbox `http://mcp_auth_servidor:80/.well-known/oauth-protected-resource` com `app: agentgateway`, `http://<ip ai>:3100/api/public/health` com `app: langfuse`); `grafana/alerting/rules.yml.j2` (`ops-acao-falhou`: Loki `sum(count_over_time({job="docker_logs"} |= "\"evento\": \"ops_acao\"" |= "\"resultado\": \"erro\"" [10m]))` `> 0`, `warning`); `homepage/services.yaml.j2` (`servidor`, `langfuse`)
- Test: `tools/wikisync/tests/test_agentes_base.py`

- [ ] **Step 1: Write the failing test** `test_observabilidade_agentes`: job, alvos com os `app`, regra `ops-acao-falhou` com o filtro acima, Homepage com as duas entradas.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(agentes): métricas do hub, sondas, alerta de ação falha e painel`

### Task 9: Página 13, catálogo, índice e demais páginas

**Files:**
- Create: `wiki/docs/01-manual-implementacao/13-agentes-base.md` (seção 8 da spec; cita todos os arquivos estruturais do `ops`, das stacks e dos playbooks; literais de `templates/agents/*.j2`)
- Modify: catálogo (`agentgateway` — stack `agents`, core, `agentgateway`/`mcp_auth_servidor`, publica, `servidor`, métricas sim; `ops` e `mcp-grafana` internos; `langfuse` protegida, `langfuse`, local); índice (regras **MCP-3** e **MCP-4**, provedor da integração `mcp` passa a citar a rota de controle; seção nova `ops` com **OPS-1** playbooks só da lista e **OPS-2** aplicar exige simulação; DAD-5 aceita dados descartáveis do Langfuse); páginas 00, 01, 05, 07, 08, 09, backup, `07-apis-llm-estrategia.md`; `INDEX.md`; `mkdocs.yml`
- Test: `tools/wikisync/tests/test_agentes_base.py`

- [ ] **Step 1: Write the failing test** `test_catalogo_e_pagina_agentes`: linhas do catálogo com Exposição e Subdomínio acima; página 13 na navegação; índice com `MCP-3`, `MCP-4`, `OPS-1`, `OPS-2`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; skills `update-index` e `audit-integrations` (sem ❌/⚠️); `check` → `sync --yes`.
- [ ] **Step 4: Run** `dev.py test`, `check`, lint, build estrito → passam.
- [ ] **Step 5: Commit** `docs(agentes): página 13, catálogo, índice e páginas da base dos agentes`

### Task 10: Revisão final e registro

- [ ] **Step 1:** Revisor único (Opus, contexto novo) sobre `<commit da spec>..HEAD` contra a spec e o Review Focus; corrigir Critical/Important com teste primeiro; menores no ledger.
- [ ] **Step 2:** `dev.py test`, `check`, lint, build estrito → passam.
- [ ] **Step 3:** Atualizar `claude/contexto-homeserver.md` no Project.
- [ ] **Step 4: Commit** `fix(agentes): correções da revisão final`.
