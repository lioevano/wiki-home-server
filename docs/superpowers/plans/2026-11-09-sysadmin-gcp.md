# Sysadmin no GCP (5a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um sysadmin (Hermes + Honcho) numa e2-micro do GCP que implanta e opera o homeserver pelo Telegram, com um executor separado que guarda o vault e a chave SSH e só age com botão do Léo.

**Architecture:** VM configurada por `ansible-pull` da `main` (`setup-sysadmin.yml`), cinco containers num compose (`sysadmin`, `sysadmin_painel`, `executor`, `honcho_api`, `honcho_deriver`, `honcho_db`). O executor reaproveita o runner do `ops` e o registro e o Telegram do `aprovador`, roda ad-hoc e playbooks pela casa via Tailscale e acorda o Hermes por webhook (carteiro). Host Proxmox e core viram nós `tag:homeserver` do tailnet.

**Tech Stack:** Ansible (ansible-core 2.21.5 na imagem; 2.17 no venv de testes), Docker Compose, Python 3.13 (só biblioteca padrão no executor, mais FastMCP 4.1.2 e ansible-core), Hermes Agent v0.22.5, Honcho v3.6.0, pgvector 0.8.7-pg17, Tailscale, gcloud.

**Spec:** `docs/superpowers/specs/2026-11-09-sysadmin-gcp-design.md` (com as emendas da Task 1).

## Global Constraints

- Wiki é a fonte da verdade: blocos literais (`title="<caminho relativo a server/>"`) são editados na wiki e levados ao `server/` com `python tools/dev.py sync --yes`; arquivos sem bloco literal são citados pelo caminho completo numa página (senão `ORPHAN`).
- Português em código, comentários, mensagens e commits; UTF-8 sem BOM e LF.
- Toda imagem com versão fixada: `nousresearch/hermes-agent:v0.22.5` (= `hermes_version`), `ghcr.io/plastic-labs/honcho:v3.6.0`, `pgvector/pgvector:0.8.7-pg17`, `python:3.13-slim`; imagens locais `localhost/homeserver/<nome>:<versão>` e `diun.enable: "false"` nos serviços da VM do GCP (o Diun é de casa).
- Modelos: padrão `claude-sonnet-5-5`, auxiliar `claude-haiku-5-5`, reserva e Honcho `gemini-3.8-flash` (variáveis no `main.yml`).
- VM: `e2-micro`, `us-east1` (zona `us-east1-b`), Ubuntu 24.04, disco `pd-standard` 30 GB, swap 4 GB.
- Segredos só no Secret Manager (`sysadmin-segredos`, um JSON) e em `/run/sysadmin` (tmpfs, 0600/0400); nunca no git, nunca no disco da VM, nunca na conversa com o modelo.
- O container `sysadmin` não tem senha do vault nem chave SSH e não alcança `100.64.0.0/10`, `192.168.15.0/24` nem `169.254.169.254`.
- Toda ação que muda a casa passa pelo `Portao` do executor (botão no bot de aprovações, só ids de `TELEGRAM_CHAT_ID`/usuários, uso único, 30 min).
- Cada task termina com `python tools/dev.py test` verde; a última com `check` (0 erro), `build` e `lint` verdes.
- Commits pequenos, na `main`, terminando com as linhas de atribuição da sessão.

## Review Focus

- `diagnostico` com metacaracteres ou argumentos fora do formato (`journalctl -u x;rm`, `docker logs --tail 9999 x`, `$(...)`) → recusado antes de qualquer SSH (teste na Task 5).
- Léo manda o segredo como mensagem solta (sem responder ao pedido) ou de outra conta → a mensagem é apagada se for do Léo, nada é gravado, e ele recebe "responda à mensagem do pedido"; de outra conta, ignorada (teste na Task 6).
- Primeira execução do carteiro num `homeserver-equipe` com histórico → não acorda o sysadmin por atividade antiga (teste na Task 7).
- `vault_preencher` com chave fora do `vault.yml.example`, ou valor com aspas, barra invertida ou várias linhas → chave recusada; valores gravados de forma que `yaml.safe_load` devolve exatamente o valor (teste na Task 6).
- JSON do Secret Manager sem um campo, ou com campo vazio → `separar_segredos.py` sai com erro listando os campos e não grava nada (os containers não sobem com token vazio) (teste na Task 10).

---

### Task 1: Emendas da spec e esqueleto da página 19

As verificações do brainstorming (seção 13 da spec) foram feitas lendo o código do Hermes v0.22.5 e do Honcho v3.6.0. Esta task registra o que mudou.

**Files:**
- Modify: `docs/superpowers/specs/2026-11-09-sysadmin-gcp-design.md` (nova seção 16 "Emendas do plano")
- Create: `wiki/docs/01-manual-implementacao/19-sysadmin-gcp.md`
- Modify: `wiki/mkdocs.yml` (nav, depois do roteiro: `'Sysadmin no GCP': '01-manual-implementacao/19-sysadmin-gcp.md'`)
- Modify: `wiki/docs/01-manual-implementacao/index.md` (linha da seção 19 na lista de seções)

- [ ] **Step 1: Escrever a seção 16 da spec**, uma linha por emenda:
  - **E1 (S2, S6):** sem Vertex. O Honcho só fala `openai`, `anthropic` e `gemini` por chave (`LLM_GEMINI_API_KEY`), sem conta de serviço. Uma **chave do Gemini (AI Studio, plano pago)** serve ao deriver, aos *embeddings* (`gemini-embedding-001`, 1536 dimensões) e à reserva do Hermes (`fallback_providers: [{provider: gemini, model: gemini-3.8-flash}]`). Sai a conta de serviço do Vertex e o item 13.5.
  - **E2 (S6):** o modelo do Honcho é `gemini-3.8-flash` (o nome que o repositório já usa), trocável por `sysadmin_honcho_modelo`.
  - **E3 (S16):** o `gerar_vault.py` roda **no Cloud Shell**, dentro do `criar-sysadmin.sh`. As senhas "para anotar" aparecem só na tela do Léo. O `vault.yml` criptografado vai para `gs://<bucket>/entrada/vault.yml`, o host copia para `/opt/sysadmin/saida/vault.yml` e o sysadmin abre o PR. Sai `vault_gerar`.
  - **E4 (§5.4, §6):** sai `proxmox_preparar`. O executor manda pelo bot de aprovações o comando do host (`preparar_host`): `scripts/gcp/preparar-host.sh` instala o Tailscale, cria o usuário Ansible sem senha com a chave pública e o sudo. A senha de root só vai para o vault (`proxmox_api_password`) pelo canal de segredos.
  - **E5 (§6):** saem `stack_criar`, `stack_atualizar` e `inicializar_portainer`. A API do Portainer só existe na rede `proxy` da core. As stacks continuam um passo do Léo no Portainer, guiado pelo sysadmin.
  - **E6 (S15):** a resposta do Léo ao pedido de segredo **é** a aprovação: não há botão antes.
  - **E7 (S18):** host e core anunciam as **três** rotas `/32` (inclusive a do host), e a core também entra com `tag:homeserver`. Sem isso, a core (dono: o Léo) alcançaria `tag:sysadmin`.
  - **E8 (S20):** o dashboard escuta em `0.0.0.0:9119` dentro do container (publicado em `127.0.0.1:9119` do host), com usuário e senha (`HERMES_DASHBOARD_BASIC_AUTH_*`) e `dashboard.public_url` = URL do `tailscale serve`. O Hermes exige provedor de autenticação atrás de *reverse proxy*.
  - **E9 (S27):** o carteiro acorda o Hermes pela **plataforma `webhook`** (porta 8644 na rede interna, assinatura HMAC V2, `deliver: telegram`, `mirror_to_session: true`). A entrega cai na conversa do Léo, e não pela API.
  - **E10 (S21):** as skills do repositório entram por `skills.external_dirs`. O plugin do Honcho é o diretório `hermes-plugin-honcho` do repositório do Honcho na tag `v3.6.0`, copiado para `$HERMES_HOME/plugins/honcho`. O Honcho roda **sem Redis** (`CACHE_ENABLED` já é `false` por padrão).
  - **E11:** correção de um bug achado no caminho: `vm_ci_ssh_keys_public_file` trocava o último caractere da chave por `pub` (`regex_replace('.$', 'pub')`) em vez de acrescentar `.pub`.
  - **E12 (§13.6):** a memória real em 1 GB vai para "A conferir no primeiro deploy".
- [ ] **Step 2: Criar a página 19 com o esqueleto.**
  - Front matter `description: "Sysadmin no GCP: Hermes com memória Honcho numa e2-micro, executor com vault e SSH atrás de botões no Telegram, e a equipe de agentes pelo GitHub."`.
  - Título `# Seção 19: Sysadmin no GCP`.
  - Seções vazias com uma linha cada: `## Como funciona`, `## O que ele pode e o que não pode`, `## Rede e ACL`, `## Criar o sysadmin`, `## A equipe`, `## Arquivos`, `## Teste de ponta a ponta`, `## Falhas`.
  - As tasks seguintes acrescentam linhas em `## Arquivos`; a Task 14 escreve o texto.
- [ ] **Step 3: Verificar**
  Run: `python tools/dev.py build && python tools/dev.py check`
  Expected: build sem WARNING; `check` com 0 erro(s).
- [ ] **Step 4: Commit**
  `git add docs/superpowers/specs/2026-11-09-sysadmin-gcp-design.md wiki/ && git commit -m "docs(5a): emendas do plano e esqueleto da página 19"`

---

### Task 2: Tailscale no host, tags e ACL

**Files:**
- Modify (wiki, blocos literais): `wiki/docs/01-manual-implementacao/14-vpn-tailscale.md` — `ansible/roles/infra/tailscale/tasks/main.yml`, novo `ansible/roles/infra/tailscale/defaults/main.yml`, novo `scripts/tailscale/acl.json`
- Modify (wiki): `wiki/docs/01-manual-implementacao/02-proxmox-ve-host.md` (bloco do `setup-proxmox-host.yml`, se literal; senão o arquivo direto) e `wiki/docs/01-manual-implementacao/01-maquina-controle-ansible.md` (bloco do `main.yml`)
- Modify: `server/ansible/playbooks/setup-proxmox-host.yml`, `server/ansible/inventories/home/group_vars/all/main.yml`, `server/ansible/inventories/home/group_vars/all/vault.yml.example`
- Test: `tools/wikisync/tests/test_vpn.py`

**Interfaces:**
- Produces:
  - variáveis do role `infra/tailscale`: `tailscale_hostname`, `tailscale_rotas`, `tailscale_tags` (lista, padrão `["tag:homeserver"]`), `tailscale_aceitar_rotas` (padrão `false`), `tailscale_coredns` (padrão `true`), `tailscale_ufw` (padrão `true`), `tailscale_auth_key`;
  - `tailscale_rotas` = as três `/32` (`proxmox_host_ip_var`, `core_services_vm_ip_var`, `ai_desktop_vm_ip_var`);
  - arquivo `server/scripts/tailscale/acl.json` (JSON estrito), com hosts `pve`, `core`, `ai`.

- [ ] **Step 1: Escrever os testes que falham** em `test_vpn.py`:

```python
def _acl():
    return json.loads((ROOT / "server/scripts/tailscale/acl.json").read_text(encoding="utf-8"))

def test_rotas_incluem_o_host_e_tags():
    m = _main()
    assert m["tailscale_rotas"] == ["{{ proxmox_host_ip_var }}/32", "{{ core_services_vm_ip_var }}/32",
                                    "{{ ai_desktop_vm_ip_var }}/32"]
    d = yaml.safe_load((ROOT / "server/ansible/roles/infra/tailscale/defaults/main.yml").read_text(encoding="utf-8"))
    assert d == {"tailscale_tags": ["tag:homeserver"], "tailscale_aceitar_rotas": False,
                 "tailscale_coredns": True, "tailscale_ufw": True}

def test_role_tailscale_parametrizado():
    t = (ROOT / "server/ansible/roles/infra/tailscale/tasks/main.yml").read_text(encoding="utf-8")
    assert "{{ ansible_facts.distribution | lower }}" in t           # Ubuntu (VMs, GCP) e Debian (Proxmox)
    assert "--advertise-tags={{ tailscale_tags | join(',') }}" in t
    assert "--accept-routes={{ tailscale_aceitar_rotas | bool | lower }}" in t
    tarefas = yaml.safe_load(t)
    for x in tarefas:
        if x["name"].startswith("CoreDNS"):
            assert x["when"] == "tailscale_coredns | bool"
        if x["name"].startswith("UFW"):
            assert x["when"] == "tailscale_ufw | bool"

def test_host_proxmox_e_no_proprio():
    pb = yaml.safe_load((ROOT / "server/ansible/playbooks/setup-proxmox-host.yml").read_text(encoding="utf-8"))
    papeis = [r for p in pb for r in p.get("roles", [])]
    ts = next(r for r in papeis if isinstance(r, dict) and r.get("role") == "infra/tailscale")
    assert ts["vars"] == {"tailscale_hostname": "pve", "tailscale_coredns": False, "tailscale_ufw": False,
                          "tailscale_auth_key": "{{ tailscale_auth_key_host | default('') }}"}

def test_acl_casa_nao_alcanca_o_sysadmin():
    acl = _acl()
    assert set(acl["tagOwners"]) == {"tag:sysadmin", "tag:homeserver"}
    assert acl["hosts"] == {"pve": "192.168.15.66", "core": "192.168.15.67", "ai": "192.168.15.68"}
    for regra in acl["acls"]:
        if any(s in ("tag:homeserver", "pve", "core", "ai") for s in regra["src"]):
            assert not any(d.startswith("tag:sysadmin") for d in regra["dst"])
    sa = [r for r in acl["acls"] if r["src"] == ["tag:sysadmin"]]
    assert sa == [{"action": "accept", "src": ["tag:sysadmin"], "dst": ["pve:22,8006", "core:22,443,53", "ai:22"]}]
    assert {"action": "accept", "src": ["autogroup:member"], "dst": ["tag:sysadmin:22,443"]} in acl["acls"]
    assert acl["autoApprovers"]["routes"] == {f"192.168.15.{n}/32": ["tag:homeserver"] for n in (66, 67, 68)}
```

- [ ] **Step 2: Rodar e ver falhar**
  Run: `python tools/dev.py test -- -k "rotas_incluem or tailscale_parametrizado or proxmox_e_no or acl_casa"`
  Expected: FAIL (`acl.json` inexistente, `KeyError: tailscale_tags`).
- [ ] **Step 3: Editar os blocos literais na wiki** (página 14):
  - repositório por `{{ ansible_facts.distribution | lower }}`;
  - `tailscale up … --advertise-tags=… --accept-routes=…`, e o `tailscale set` também confere `AdvertiseTags`;
  - `when` nas tarefas `CoreDNS*` e `UFW*`;
  - `defaults/main.yml` com os quatro padrões;
  - `scripts/tailscale/acl.json` com: `tagOwners` (ambas as tags → `autogroup:admin`); `hosts`; as três regras (sysadmin → casa; `autogroup:member` → `tag:sysadmin:22,443`; `autogroup:member` → `pve:*`, `core:*`, `ai:*`, `tag:homeserver:*`); `autoApprovers.routes`.
  - Na página 01, no bloco do `main.yml`: `tailscale_rotas` com as três rotas. O `vault.yml.example` ganha `tailscale_auth_key_host` (comentado: "só se o host sair do tailnet; a primeira entrada é pelo preparar-host.sh"). Em `setup-proxmox-host.yml`, o role `infra/tailscale` com os `vars` do teste.
  - Texto da página 14: o box "Por que rotas /32 e por que o host Proxmox fica de fora" vira "o host é um nó próprio; host e core anunciam as mesmas rotas (failover)"; a auth key da core é criada como `tag:homeserver`; a ACL de exemplo dá lugar a "cole `scripts/tailscale/acl.json` no painel".
- [ ] **Step 4: Sincronizar e testar**
  Run: `python tools/dev.py sync --yes && python tools/dev.py test`
  Expected: PASS (inclusive os testes antigos de `test_vpn.py`; ajuste o que conferia `--advertise-routes` sem `--advertise-tags`).
- [ ] **Step 5: Commit** — `git commit -m "feat(5a): host Proxmox como nó do Tailscale, tags e ACL"`

---

### Task 3: Caminho da chave pública das VMs

**Files:**
- Modify: `server/ansible/roles/infra/proxmox-vm/defaults/main.yml:22` (pela wiki, se o arquivo for bloco literal da página 03)
- Test: `tools/wikisync/tests/test_infra_base.py`

- [ ] **Step 1: Teste que falha**

```python
def test_chave_publica_acrescenta_pub():
    d = (ROOT / "server/ansible/roles/infra/proxmox-vm/defaults/main.yml").read_text(encoding="utf-8")
    assert "vm_ci_ssh_keys_public_file: \"{{ (ansible_ssh_private_key_file ~ '.pub') | expanduser }}\"" in d
```

- [ ] **Step 2: Rodar** — `python tools/dev.py test -- -k chave_publica` → FAIL.
- [ ] **Step 3: Corrigir** a linha (pela wiki → `sync --yes`).
- [ ] **Step 4: Rodar** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "fix: chave pública das VMs acrescenta .pub em vez de trocar o último caractere"`

---

### Task 4: `aprovador` sem tela

**Files:**
- Modify: `server/docker/images/aprovador/aprovador/telegram.py` (`texto_do_pedido`)
- Test: `tools/wikisync/tests/test_aprovacao.py`

- [ ] **Step 1: Teste que falha**

```python
def test_texto_sem_tela_nao_cita_endereco():
    p = {"id": "ab12", "cliente": "sysadmin", "acao": "comando", "alvo": "core-services-vm",
         "argumentos": {"comando": "ls"}, "descricao": "", "estado": "pendente"}
    t = texto_do_pedido(p, "")
    assert "Sem decisão, vence sozinho." in t and "Também em" not in t
```

- [ ] **Step 2: Rodar** — FAIL.
- [ ] **Step 3:** Em `texto_do_pedido`, com `url_publica` vazia, a última linha é só `"\nSem decisão, vence sozinho."`.
- [ ] **Step 4: Rodar** — `python tools/dev.py test -- -k aprovacao` → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(aprovador): mensagem sem tela de aprovações"`

---

### Task 5: Executor — configuração, portão e comandos remotos

**Files:**
- Create: `server/docker/images/executor/executor/__init__.py` (docstring + `__version__ = "1.0.0"`), `.../config.py`, `.../portao.py`, `.../remoto.py`
- Test: `tools/wikisync/tests/test_executor.py` (cabeçalho como o de `test_aprovacao.py`: `sys.path` com `server/docker/images/{executor,ops,aprovador}`, `sys.dont_write_bytecode = True`)
- Modify: página 19, `## Arquivos` (uma linha por arquivo)

**Interfaces:**
- Consumes: `aprovador.pedidos.Registro`, `aprovador.pedidos.Conflito`, `aprovador.telegram.Telegram`, `ops.politica.Recusado`, `ops.politica.limpar_saida`, `ops.runner.executar_real`, `ops.runner.Executar`.
- Produces:
  - `executor.config.Config` (frozen dataclass): `token_mcp`, `bot_token`, `chat_id`, `usuarios: frozenset[str]`, `repo_dir="/repo"`, `inventario="server/ansible/inventories/home/hosts.ini"`, `chave_ssh="/segredos/id_ed25519"`, `senha_vault_arquivo="/segredos/vault_senha"`, `saida_dir="/saida"`, `dados_dir="/data"`, `playbooks: dict[str, str]`, `limite_saida=20000`, `validade_s=1800`, `tailscale_chave_host`, `ansible_usuario_host`, `rotas` (texto separado por vírgula), `repo_url_raw`, `equipe_repo`, `github_token_equipe`, `conta_sysadmin`, `webhook_url`, `webhook_segredo`, `carteiro_intervalo_s=120`.
  - `Config.do_ambiente(env) -> Config`. Variáveis: `EXECUTOR_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `EXECUTOR_TELEGRAM_USUARIOS`, `EXECUTOR_PLAYBOOKS` (JSON), `EXECUTOR_REPO_DIR` (opcional, padrão `/repo`), `EXECUTOR_ROTAS`, `TAILSCALE_CHAVE_HOST`, `ANSIBLE_USUARIO_HOST`, `REPO_URL_RAW`, `EQUIPE_REPO`, `GITHUB_TOKEN_EQUIPE`, `CONTA_SYSADMIN`, `WEBHOOK_URL`, `WEBHOOK_SEGREDO`. Levanta `ConfigInvalida` listando as obrigatórias vazias; usa a mesma regra de usuários do `aprovador` (chat privado = o próprio id).
  - `Config.para_ops() -> ops.config.Config`: `modo="controle"`, Portainer vazio, `playbooks`, `repo_dir`, `inventario`, `chave_ssh`, `limite_saida`, `plano_validade_s=validade_s`.
  - `executor.portao.Portao(registro, telegram)` com `executar(acao: str, alvo: str, argumentos: dict, aprovacao_id: str | None, descricao: str, fazer: Callable[[], str]) -> str`. Cliente fixo `"sysadmin"`.
    - Sem `aprovacao_id`: `registro.criar` + `telegram.avisar` e devolve o texto `AGUARDANDO` (com o id).
    - Com `aprovacao_id`: `registro.usar` (um `Conflito` vira `Recusado`) e depois `fazer()`.
  - `executor.remoto.validar_diagnostico(comando: str) -> tuple[list[str], bool]` (argv e se precisa de `--become`); levanta `Recusado`.
  - `executor.remoto.Remoto(cfg, executar=executar_real)`:
    - `hosts() -> set[str]`: nomes do inventário;
    - `rodar(host: str, comando: list[str] | str, shell: bool, become: bool) -> tuple[int, str]`: `ansible <host> -i <inv> -m ansible.builtin.command|shell -a <...> -e ansible_ssh_private_key_file=<chave> [--become]`, `cwd=<repo>/server/ansible`, tempo 120 s, saída por `limpar_saida`.

- [ ] **Step 1: Testes que falham**

```python
AMB = {"EXECUTOR_TOKEN": "tok", "TELEGRAM_BOT_TOKEN": "1:x", "TELEGRAM_CHAT_ID": "4242",
       "EXECUTOR_PLAYBOOKS": '{"setup-vpn.yml": "VPN"}', "TAILSCALE_CHAVE_HOST": "tskey-h",
       "ANSIBLE_USUARIO_HOST": "proxmox_ansible_user", "REPO_URL_RAW": "https://raw.githubusercontent.com/o/r/main",
       "EQUIPE_REPO": "o/homeserver-equipe", "GITHUB_TOKEN_EQUIPE": "ghp", "CONTA_SYSADMIN": "o-sysadmin",
       "WEBHOOK_URL": "http://sysadmin:8644/webhooks/equipe", "WEBHOOK_SEGREDO": "s",
       "EXECUTOR_ROTAS": "192.168.15.66/32,192.168.15.67/32,192.168.15.68/32"}

def test_config_falha_fechada():
    c = Config.do_ambiente(AMB)
    assert c.usuarios == {"4242"} and c.playbooks == {"setup-vpn.yml": "VPN"} and c.validade_s == 1800
    with pytest.raises(ConfigInvalida, match="EXECUTOR_TOKEN"):
        Config.do_ambiente({**AMB, "EXECUTOR_TOKEN": " "})
    assert c.para_ops().modo == "controle" and c.para_ops().chave_ssh == "/segredos/id_ed25519"

@pytest.mark.parametrize("cmd,become", [
    ("systemctl status docker", False), ("journalctl -u tailscaled -n 200 --no-pager", True),
    ("docker ps -a", True), ("docker logs --tail 100 traefik", True), ("df -h", False), ("free -m", False),
    ("ip -br a", False), ("ss -tlnp", True), ("ping -c 3 1.1.1.1", False), ("tailscale status", False),
    ("cat /etc/os-release", False)])
def test_diagnostico_aceita_so_leitura(cmd, become):
    argv, b = validar_diagnostico(cmd)
    assert argv == cmd.split() and b is become

@pytest.mark.parametrize("cmd", [
    "journalctl -u x;rm -rf /", "docker logs --tail 9999 x", "docker inspect authelia", "cat /etc/shadow",
    "ping -c 50 1.1.1.1", "systemctl restart docker", "df -h | sh", "echo $(id)", "docker logs --tail 10 'a b'",
    "", "rm -rf /"])
def test_diagnostico_recusa(cmd):
    with pytest.raises(Recusado):
        validar_diagnostico(cmd)

def test_portao_pede_e_depois_executa(tmp_path):
    rel, enviados = Relogio(), []
    reg = Registro(str(tmp_path / "p.json"), 1800, rel)
    tg = type("T", (), {"avisar": lambda self, p: enviados.append(p)})()
    portao, feito = Portao(reg, tg), []
    r = portao.executar("comando", "core-services-vm", {"comando": "ls"}, None, "listar", lambda: feito.append(1) or "ok")
    pid = enviados[0]["id"]
    assert pid in r and feito == [] and enviados[0]["cliente"] == "sysadmin"
    with pytest.raises(Recusado):  # ainda pendente
        portao.executar("comando", "core-services-vm", {"comando": "ls"}, pid, "", lambda: "x")
    reg.decidir(pid, True, "telegram:leo")
    with pytest.raises(Recusado):  # outro argumento
        portao.executar("comando", "core-services-vm", {"comando": "id"}, pid, "", lambda: "x")
    assert portao.executar("comando", "core-services-vm", {"comando": "ls"}, pid, "", lambda: "ok") == "ok"
    with pytest.raises(Recusado):  # uso único
        portao.executar("comando", "core-services-vm", {"comando": "ls"}, pid, "", lambda: "ok")

def test_remoto_monta_o_ansible_adhoc(tmp_path):
    inv = tmp_path / "server/ansible/inventories/home"
    inv.mkdir(parents=True)
    (inv / "hosts.ini").write_text("[proxmox_hosts]\nproxmox_main_host ansible_host=1.2.3.4\n[core_services]\n"
                                   "core-services-vm ansible_host=1.2.3.5\n[all:vars]\nx=1\n", encoding="utf-8")
    chamadas = []
    cfg = Config.do_ambiente({**AMB, "EXECUTOR_REPO_DIR": str(tmp_path)})
    r = Remoto(cfg, lambda argv, cwd, t: chamadas.append((argv, cwd, t)) or (0, "token=abc\nok"))
    assert r.hosts() == {"proxmox_main_host", "core-services-vm"}
    rc, saida = r.rodar("core-services-vm", ["docker", "ps"], shell=False, become=True)
    argv, cwd, t = chamadas[0]
    assert argv[:6] == ["ansible", "core-services-vm", "-i", "inventories/home/hosts.ini", "-m", "ansible.builtin.command"]
    assert "--become" in argv and t == 120 and cwd.endswith("server/ansible") and "token=abc" not in saida
    with pytest.raises(Recusado):
        r.rodar("outro", ["df"], shell=False, become=False)
```

(`Relogio` como em `test_aprovacao.py`.)

- [ ] **Step 2: Rodar** — `python tools/dev.py test -- -k "executor"` → FAIL (`ModuleNotFoundError: executor`).
- [ ] **Step 3: Implementar** `config.py`, `portao.py` e `remoto.py` com as assinaturas acima.
  - Regras do `validar_diagnostico`: `shlex.split`. Todo token casa `^[A-Za-z0-9_.@:/=,+-]+$`. A forma é uma destas:
    - `systemctl status|is-active <unit>` e `systemctl list-units --failed`;
    - `journalctl -u <unit> -n <1..500> [--no-pager]` (become);
    - `docker ps [-a]` (become);
    - `docker logs --tail <1..500> <nome>` (become);
    - `df -h`, `free -m`, `uptime`, `ip -br a`, `ip route`, `ss -tlnp` (become);
    - `ping -c <1..5> <host>`;
    - `tailscale status`;
    - `cat /etc/os-release`.
  - O texto `AGUARDANDO` segue o do `ops`: "Aguardando aprovação humana: pedido X… chame de novo com `aprovacao_id`".
- [ ] **Step 4: Rodar** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(5a): executor — configuração, portão e comandos remotos"`

---

### Task 6: Executor — vault, canal de segredos e leitor do Telegram

**Files:**
- Create: `server/docker/images/executor/executor/vault.py`, `.../segredos.py`, `.../leitor.py`
- Test: `tools/wikisync/tests/test_executor.py`

**Interfaces:**
- Consumes: `Config` (Task 5), `aprovador.telegram.Bot` (`chamar(metodo, params)`), `aprovador.telegram.Telegram` (`tratar`, `registro.expirar`, `atualizar`).
- Produces:
  - `vault.chaves_do_modelo(texto: str) -> set[str]`: caminhos com ponto das folhas do `vault.yml.example`.
  - `vault.definir(texto: str, chave: str, valor: str) -> str`: troca o valor da folha mantendo o resto do texto; `KeyError` se a chave não existe.
  - `vault.Vault(cfg)`:
    - `origem() -> Path`: `saida/vault.yml` se existir; senão `<repo>/server/ansible/inventories/home/group_vars/all/vault.yml`;
    - `ler() -> str`;
    - `gravar(texto) -> None`: cifra com `ansible.parsing.vault.VaultLib` e a senha de `senha_vault_arquivo`, sempre em `saida/vault.yml`.
  - `segredos.CanalDeSegredos(bot, cfg, vault, chaves: set[str], relogio=time.time)`:
    - `pedir(chave) -> str`;
    - `receber(update: dict) -> None`;
    - `status() -> str`.
  - `leitor.Leitor(telegram, canal)`:
    - `ler(timeout=30)`: `getUpdates` com `allowed_updates=["callback_query", "message"]`; clique → `telegram.tratar`; mensagem → `canal.receber`;
    - `rodar(parar: threading.Event)`.

- [ ] **Step 1: Testes que falham**

```python
MODELO = 'a: "X"\ngrupo:\n  filho: "Y" # comentario\nchave_ssh: |\n  -----BEGIN-----\n  abc\n'

def test_chaves_e_definir():
    assert chaves_do_modelo(MODELO) == {"a", "grupo.filho", "chave_ssh"}
    for valor in ['com "aspas" e \\barra', "linha1\nlinha2", "simples"]:
        for chave in ("a", "grupo.filho", "chave_ssh"):
            novo = definir(MODELO, chave, valor)
            dados = yaml.safe_load(novo)
            alvo = dados["grupo"]["filho"] if chave == "grupo.filho" else dados[chave]
            assert alvo == valor
    assert "# comentario" in definir(MODELO, "grupo.filho", "z")
    with pytest.raises(KeyError):
        definir(MODELO, "nao.existe", "v")

def test_vault_cifra_na_saida(tmp_path):
    (tmp_path / "senha").write_text("s3nha\n", encoding="utf-8")
    cfg = replace(Config.do_ambiente(AMB), saida_dir=str(tmp_path / "saida"), senha_vault_arquivo=str(tmp_path / "senha"),
                  repo_dir=str(tmp_path))
    (tmp_path / "saida").mkdir()
    v = Vault(cfg)
    v.gravar(MODELO)
    bruto = (tmp_path / "saida/vault.yml").read_text(encoding="utf-8")
    assert bruto.startswith("$ANSIBLE_VAULT;1.1;AES256") and v.ler() == MODELO and v.origem().parent.name == "saida"

class BotFalso:
    def __init__(self): self.chamadas = []; self.n = 100
    def chamar(self, metodo, params, timeout=15):
        self.chamadas.append((metodo, params)); self.n += 1
        return {"message_id": self.n}

def _msg(texto, de="4242", chat="4242", resposta_a=None, mid=7):
    m = {"message_id": mid, "from": {"id": int(de)}, "chat": {"id": int(chat)}, "text": texto}
    if resposta_a: m["reply_to_message"] = {"message_id": resposta_a}
    return {"update_id": 1, "message": m}

def test_canal_de_segredos(tmp_path):
    gravados = {}
    vault = type("V", (), {"ler": lambda s: MODELO, "gravar": lambda s, t: gravados.update(t=t)})()
    bot, rel = BotFalso(), Relogio()
    canal = CanalDeSegredos(bot, Config.do_ambiente(AMB), vault, chaves_do_modelo(MODELO), rel)
    with pytest.raises(Recusado):
        canal.pedir("inexistente")
    texto = canal.pedir("grupo.filho")
    assert "grupo.filho" in texto and bot.chamadas[0][1]["reply_markup"] == {"force_reply": True}
    pedido_msg = bot.n
    canal.receber(_msg("solto", mid=8))                       # sem responder: apaga e orienta, não grava
    assert ("deleteMessage", {"chat_id": "4242", "message_id": 8}) in bot.chamadas and gravados == {}
    canal.receber(_msg("x", de="999", resposta_a=pedido_msg))  # outra conta: ignora
    assert gravados == {}
    canal.receber(_msg("VALOR-SECRETO", resposta_a=pedido_msg, mid=9))
    assert yaml.safe_load(gravados["t"])["grupo"]["filho"] == "VALOR-SECRETO"
    assert ("deleteMessage", {"chat_id": "4242", "message_id": 9}) in bot.chamadas
    assert all("VALOR-SECRETO" not in json.dumps(p) for m, p in bot.chamadas if m != "deleteMessage")
    assert "grupo.filho: gravada" in canal.status() and "VALOR-SECRETO" not in canal.status()
    canal.pedir("a"); pedido_a = bot.n
    rel.t += 1801
    canal.receber(_msg("tarde", resposta_a=pedido_a, mid=10))  # pedido vencido: não grava
    assert "tarde" not in gravados["t"]
```

- [ ] **Step 2: Rodar** — FAIL.
- [ ] **Step 3: Implementar.**
  - `definir` usa a mesma regra de linha do `gerar_vault.py`: `^(?P<ind> *)(?P<chave>[A-Za-z_]\w*):(?P<resto>.*)$`, pilha por indentação, e blocos `|` até a próxima linha menos indentada.
  - Escalar de uma linha: aspas duplas, com `\` → `\\` e `"` → `\"`, preservando o comentário ` #…`.
  - Com `\n`: bloco `|` indentado em +2.
  - `pedir` manda pelo `bot` a mensagem "🔐 Responda a esta mensagem com o valor de `<chave>` (vale 30 min; a sua resposta é apagada)", com `force_reply`.
  - `receber` só considera mensagens do `chat_id` e de `usuarios`; apaga sempre a mensagem do Léo. Grava se for resposta a um pedido no prazo, e confirma "✅ `<chave>` gravada; o sysadmin abre o PR". Senão, responde "responda à mensagem do pedido".
  - `status` lista os pendentes e os gravados, só os nomes.
- [ ] **Step 4: Rodar** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(5a): executor — vault e canal de segredos pelo bot de aprovações"`

---

### Task 7: Executor — carteiro

**Files:**
- Create: `server/docker/images/executor/executor/carteiro.py`
- Test: `tools/wikisync/tests/test_executor.py`

**Interfaces:**
- Produces:
  - `Carteiro(cfg, abrir=urllib.request.urlopen, relogio=time.time)`. Estado em `<dados_dir>/carteiro.json` (`{"desde": "<ISO>"}`).
  - `rodar_uma_vez() -> int`: quantos itens avisou.
  - `rodar(parar: threading.Event)`: a cada `carteiro_intervalo_s`.
  - `assinar(segredo: str, ts: str, corpo: bytes) -> str`: hex do HMAC-SHA256 de `ts + "." + corpo`.

- [ ] **Step 1: Testes que falham**

```python
class Resp:
    def __init__(self, corpo): self.corpo, self.status = corpo, 200
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self.corpo

class GitHubFalso:
    def __init__(self, issues, comentarios): self.issues, self.comentarios, self.posts = issues, comentarios, []
    def __call__(self, req, timeout=15):
        url = req.full_url
        if req.get_method() == "POST":
            self.posts.append(req); corpo = b'{"status":"ok"}'
        elif "/issues/comments" in url: corpo = json.dumps(self.comentarios).encode()
        else: corpo = json.dumps(self.issues).encode()
        return Resp(corpo)

def test_carteiro_primeira_vez_nao_acorda(tmp_path):
    cfg = replace(Config.do_ambiente(AMB), dados_dir=str(tmp_path))
    gh = GitHubFalso([{"number": 1, "title": "velha", "labels": [{"name": "papel:sysadmin"}],
                       "user": {"login": "o"}, "html_url": "u"}], [])
    assert Carteiro(cfg, gh, lambda: 1_000.0).rodar_uma_vez() == 0 and gh.posts == []
    assert json.loads((tmp_path / "carteiro.json").read_text())["desde"]

def test_carteiro_acorda_com_resposta_de_outro(tmp_path):
    cfg = replace(Config.do_ambiente(AMB), dados_dir=str(tmp_path))
    (tmp_path / "carteiro.json").write_text('{"desde": "2026-11-09T00:00:00Z"}')
    issues = [{"number": 2, "title": "pedido", "labels": [{"name": "papel:metricas"}], "user": {"login": "o-sysadmin"},
               "html_url": "https://g/2"},
              {"number": 3, "title": "incidente", "labels": [{"name": "papel:sysadmin"}], "user": {"login": "observador"},
               "html_url": "https://g/3", "created_at": "2026-11-09T01:00:00Z"}]
    comentarios = [{"issue_url": "https://api.github.com/repos/o/homeserver-equipe/issues/2", "user": {"login": "metricas"},
                    "html_url": "https://g/2#c"},
                   {"issue_url": "https://api.github.com/repos/o/homeserver-equipe/issues/2", "user": {"login": "o-sysadmin"},
                    "html_url": "https://g/2#d"}]
    gh = GitHubFalso(issues, comentarios)
    assert Carteiro(cfg, gh, lambda: 2_000_000_000.0).rodar_uma_vez() == 2
    req = gh.posts[0]
    ts = req.headers["X-webhook-timestamp"]
    assert req.headers["X-webhook-signature-v2"] == assinar("s", ts, req.data)
    corpo = json.loads(req.data)
    assert {i["numero"] for i in corpo["itens"]} == {2, 3} and "o-sysadmin" not in json.dumps(corpo)
```

- [ ] **Step 2: Rodar** — FAIL.
- [ ] **Step 3: Implementar.**
  - `GET https://api.github.com/repos/<equipe_repo>/issues?state=all&since=<desde>&per_page=50` e `.../issues/comments?since=<desde>&per_page=100`, com `Authorization: Bearer <token>` e `X-GitHub-Api-Version: 2022-11-28`.
  - Item:
    - (a) comentário de outro autor numa issue aberta por `conta_sysadmin` ou com `papel:sysadmin`;
    - (b) issue `papel:sysadmin` criada por outro depois de `desde`.
  - Sem estado: grava `desde = agora` e devolve 0.
  - O POST ao `webhook_url` leva `{"itens": [{"numero", "titulo", "url", "autor", "tipo"}]}`, os cabeçalhos `X-Webhook-Timestamp` e `X-Webhook-Signature-V2`, e `Content-Type: application/json`.
  - `desde` só avança depois do POST com 2xx. Erro de rede: registra no stderr e tenta no próximo ciclo.
- [ ] **Step 4: Rodar** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(5a): carteiro acorda o sysadmin pelo webhook do Hermes"`

---

### Task 8: Executor — ferramentas, servidor MCP e imagem

**Files:**
- Create: `server/docker/images/executor/executor/ferramentas.py`, `.../servidor.py`, `.../__main__.py`, `server/docker/images/executor/Dockerfile`, `server/docker/images/executor/.dockerignore` (`**/__pycache__`, `**/*.pyc`)
- Create: `server/scripts/gcp/preparar-host.sh`
- Test: `tools/wikisync/tests/test_executor.py`

**Interfaces:**
- Consumes: Tasks 5–7; `ops.runner.Runner(cfg.para_ops())` (`check`, `aplicar`, `ver`); `ops.ferramentas.Ferramenta`; `ops.autenticacao.ExigirToken`.
- Produces:
  - `ferramentas(cfg, portao, remoto, runner, canal, enviar_ao_leo: Callable[[str], None]) -> dict[str, Ferramenta]`, com os nomes `diagnostico`, `comando`, `playbooks_listar`, `ansible_check`, `ansible_aplicar`, `vault_preencher`, `vault_status` e `preparar_host`.
  - Assinaturas:
    - `diagnostico(host, comando)`;
    - `comando(host, comando, aprovacao_id=None)`;
    - `ansible_check(playbook, limite=None, aprovacao_id=None)`;
    - `ansible_aplicar(plano_id, aprovacao_id=None)`;
    - `vault_preencher(chave)`;
    - `vault_status()`;
    - `preparar_host()`;
    - `playbooks_listar()`.
  - `python -m executor` sobe:
    - o leitor do Telegram e o carteiro em threads;
    - o FastMCP em `0.0.0.0:8000/mcp`, atrás do `ExigirToken(token=EXECUTOR_TOKEN)`.

- [ ] **Step 1: Testes que falham**

```python
def _ferr(tmp_path, executar=lambda a, c, t: (0, "ok")):
    rel = Relogio(); reg = Registro(str(tmp_path / "p.json"), 1800, rel); avisos, ao_leo = [], []
    portao = Portao(reg, type("T", (), {"avisar": lambda s, p: avisos.append(p)})())
    (tmp_path / "id.pub").write_text("ssh-ed25519 AAAA sysadmin\n", encoding="utf-8")
    cfg = replace(Config.do_ambiente({**AMB, "EXECUTOR_REPO_DIR": str(tmp_path)}), chave_ssh=str(tmp_path / "id"))
    remoto = type("R", (), {"hosts": lambda s: {"core-services-vm"}, "rodar": lambda s, h, c, shell, become: executar(c, h, 0)})()
    f = ferramentas(cfg, portao, remoto, None, None, ao_leo.append)
    return f, reg, avisos, ao_leo

def test_nomes_e_destrutivas(tmp_path):
    f, *_ = _ferr(tmp_path)
    assert set(f) == {"diagnostico", "comando", "playbooks_listar", "ansible_check", "ansible_aplicar",
                      "vault_preencher", "vault_status", "preparar_host"}
    assert {n for n, x in f.items() if x.destrutiva} == {"comando", "ansible_aplicar"}

def test_comando_passa_pelo_portao(tmp_path):
    f, reg, avisos, _ = _ferr(tmp_path)
    r = f["comando"].funcao("core-services-vm", "systemctl restart docker")
    assert "Aguardando" in r and avisos[0]["acao"] == "comando" and avisos[0]["argumentos"] == {
        "host": "core-services-vm", "comando": "systemctl restart docker"}

def test_preparar_host_vai_so_ao_leo(tmp_path):
    f, _, _, ao_leo = _ferr(tmp_path)
    r = f["preparar_host"].funcao()
    assert "tskey-h" not in r and "tskey-h" in ao_leo[0]
    assert ao_leo[0].startswith("curl -fsSL https://raw.githubusercontent.com/o/r/main/server/scripts/gcp/preparar-host.sh | bash -s -- ")
    assert "'proxmox_ansible_user'" in ao_leo[0] and "'ssh-ed25519 AAAA sysadmin'" in ao_leo[0]
    assert "'192.168.15.66/32,192.168.15.67/32,192.168.15.68/32'" in ao_leo[0]

def test_imagem_executor():
    d = (ROOT / "server/docker/images/executor/Dockerfile").read_text(encoding="utf-8")
    assert [l for l in d.splitlines() if l and not l.startswith("#")][0] == "FROM python:3.13-slim"
    for trecho in ("COPY ops /app/ops", "COPY aprovador /app/aprovador", "COPY executor /app/executor",
                   'ENTRYPOINT ["python", "-m", "executor"]', "useradd --uid ${UID} --gid ${GID}"):
        assert trecho in d
    assert "USER root" not in d.split("\nUSER ")[-1]

def test_preparar_host_sh():
    s = (ROOT / "server/scripts/gcp/preparar-host.sh").read_text(encoding="utf-8")
    assert s.startswith("#!/bin/bash") and "set -euo pipefail" in s
    for trecho in ("--advertise-tags=tag:homeserver", "--hostname=pve", "NOPASSWD: ALL", "authorized_keys",
                   "adduser --disabled-password"):
        assert trecho in s
```

- [ ] **Step 2: Rodar** — FAIL.
- [ ] **Step 3: Implementar.**
  - `ferramentas`:
    - `diagnostico` → `validar_diagnostico` + `remoto.rodar` (sem portão);
    - `comando` → portão, com `alvo=host` e `argumentos={"host", "comando"}`, depois `remoto.rodar(shell=True, become=True)`;
    - `ansible_check` / `ansible_aplicar` → portão em volta de `runner.check` / `runner.aplicar`, com a mesma descrição do `ops`: commit, autor e RECAP;
    - `vault_preencher` → `canal.pedir`;
    - `vault_status` → `canal.status()` e a data do `saida/vault.yml`;
    - `preparar_host` → monta o `curl … | bash -s -- '<tskey>' '<chave pública>' '<usuario>' '<rotas>'` (a chave pública vem de `chave_ssh + ".pub"`; as rotas, de `EXECUTOR_ROTAS`) e manda por `enviar_ao_leo`. Ao modelo devolve "comando enviado ao Léo pelo bot de aprovações".
  - `servidor.main()`: o FastMCP é importado só ali (o venv de testes não tem o FastMCP). Cria:
    - o `Registro` em `<dados>/pedidos.json`;
    - o `Bot`;
    - `Telegram(bot, registro, chat_id, usuarios, "")`;
    - `Vault`;
    - `CanalDeSegredos` com as chaves do `vault.yml.example` do repositório;
    - `Leitor` e `Carteiro`, cada um numa thread;
    - o `Runner`.
  - `enviar_ao_leo = lambda t: bot.chamar("sendMessage", {"chat_id": chat_id, "text": t})`.
  - `Dockerfile`: como o do `ops` (apt `git openssh-client`, `requirements.txt`, coleções), copiando `ops`, `aprovador` e `executor`; `ENV ANSIBLE_VAULT_PASSWORD_FILE=/segredos/vault_senha`.
  - `preparar-host.sh <tskey> <chave_pub> <usuario> <rotas>`:
    1. instala o Tailscale (`curl -fsSL https://tailscale.com/install.sh | sh`);
    2. `sysctl net.ipv4.ip_forward=1` (persistido em `/etc/sysctl.d/99-tailscale.conf`);
    3. `tailscale up --auth-key="$1" --hostname=pve --advertise-tags=tag:homeserver --advertise-routes="$4" --accept-dns=false`;
    4. `adduser --disabled-password --gecos "" "$3"` (se não existir);
    5. sudoers `NOPASSWD: ALL` em `/etc/sudoers.d/010_$3_nopasswd` (0440);
    6. `~$3/.ssh/authorized_keys` com `$2` (0600).
- [ ] **Step 4: Rodar** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(5a): executor — ferramentas MCP, imagem e comando de preparo do host"`

---

### Task 9: Imagem do sysadmin e configurações do Hermes e do Honcho

**Files:**
- Create: `server/docker/images/sysadmin/Dockerfile`
- Create: `server/ansible/templates/sysadmin/config.yaml.j2`, `.../SOUL.md.j2`, `.../honcho.json.j2`, `.../honcho-config.toml.j2`
- Modify: `server/ansible/inventories/home/group_vars/all/main.yml` (pela página 01) — seção "Sysadmin (página 19)":

```yaml
sysadmin_version: "1.0.0"
honcho_version: "v3.6.0"
honcho_ai_version: "2.4.0"      # pacote honcho-ai do plugin; conferir no PyPI na execução e fixar o mais novo 2.x
honcho_pgvector_version: "0.8.7-pg17"
sysadmin_modelo: "claude-sonnet-5-5"
sysadmin_modelo_auxiliar: "claude-haiku-5-5"
sysadmin_modelo_reserva: "gemini-3.8-flash"
sysadmin_honcho_modelo: "gemini-3.8-flash"
gcp_tipo_maquina: "e2-micro"
gcp_regiao: "us-east1"
gcp_zona: "us-east1-b"
sysadmin_dashboard_url: ""      # https://sysadmin.<tailnet>.ts.net — preencher depois do primeiro tailscale serve
equipe_repo: "lioevano/homeserver-equipe"
conta_sysadmin: "lioevano-sysadmin"
executor_playbooks_permitidos: [...]  # todos os playbooks de server/ansible/playbooks menos setup-sysadmin.yml
```

- Test: `tools/wikisync/tests/test_sysadmin.py` (novo; importa `ROOT`, `render` de `test_observabilidade`)

**Interfaces:**
- Produces:
  - `config.yaml` do Hermes, que espera do `.env`: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `EXECUTOR_TOKEN`, `WEBHOOK_SEGREDO`;
  - `honcho.json` com `baseUrl: http://honcho_api:8000`;
  - `config.toml` do Honcho, montado em `/app/config.toml`.

- [ ] **Step 1: Testes que falham**

```python
def _m(): return yaml.safe_load((ANS / "inventories/home/group_vars/all/main.yml").read_text(encoding="utf-8"))

def _cfg():
    m = _m()
    return yaml.safe_load(render("templates/sysadmin/config.yaml.j2", **{k: m[k] for k in m if k.startswith(("sysadmin_", "equipe"))}))

def test_hermes_do_sysadmin():
    c = _cfg()
    assert c["model"] == {"provider": "anthropic", "default": "claude-sonnet-5-5"}
    assert c["fallback_providers"] == [{"provider": "gemini", "model": "gemini-3.8-flash"}]
    assert c["auxiliary"]["compression"]["model"] == "claude-haiku-5-5"
    assert c["memory"]["provider"] == "honcho" and c["approvals"]["mode"] == "off"
    assert c["skills"]["external_dirs"] == ["/repo/.agents/skills"]
    assert c["terminal"]["cwd"] == "/repo"
    assert list(c["mcp_servers"]) == ["executor"]
    assert c["mcp_servers"]["executor"] == {"url": "http://executor:8000/mcp", "timeout": 3600,
                                            "headers": {"Authorization": "Bearer ${EXECUTOR_TOKEN}"}}
    desl = set(c["agent"]["disabled_toolsets"])
    assert {"browser", "computer_use", "delegation", "cronjob", "connections", "web", "search", "x_search", "kanban",
            "project", "catalog", "desktop_ui", "image_gen", "video_gen", "video", "tts", "vision"} <= desl
    assert not desl & {"terminal", "code_execution", "file", "skills", "memory", "todo", "clarify", "session_search"}
    rota = c["platforms"]["webhook"]["extra"]["routes"]["equipe"]
    assert c["platforms"]["webhook"]["extra"]["host"] == "0.0.0.0" and c["platforms"]["webhook"]["extra"]["port"] == 8644
    assert rota["secret"] == "${WEBHOOK_SEGREDO}" and rota["deliver"] == "telegram" and rota["mirror_to_session"] is True
    assert c["platforms"]["api_server"]["enabled"] is False
    assert "${" not in json.dumps({k: v for k, v in c.items() if k not in ("mcp_servers", "platforms")})

def test_honcho_so_gemini_sem_redis():
    toml = render("templates/sysadmin/honcho-config.toml.j2", **_m())
    dados = tomllib.loads(toml)
    assert dados["cache"]["ENABLED"] is False and dados["telemetry"]["ENABLED"] is False
    assert dados["embedding"]["model_config"] == {"transport": "gemini", "model": "gemini-embedding-001"}
    assert dados["embedding"]["VECTOR_DIMENSIONS"] == 1536
    for secao in ("deriver", "summary"):
        assert dados[secao]["model_config"] == {"transport": "gemini", "model": "gemini-3.8-flash"}
    for nivel in ("minimal", "low", "medium", "high", "max"):
        assert dados["dialectic"]["levels"][nivel]["model_config"]["transport"] == "gemini"
    assert "API_KEY" not in toml  # a chave vem do ambiente (LLM_GEMINI_API_KEY)
    hj = json.loads(render("templates/sysadmin/honcho.json.j2", **_m()))
    assert hj == {"baseUrl": "http://honcho_api:8000", "workspace": "sysadmin", "peerName": "leo",
                  "aiPeer": "sysadmin", "pinUserPeer": True}

def test_imagem_sysadmin():
    d = (ROOT / "server/docker/images/sysadmin/Dockerfile").read_text(encoding="utf-8")
    linhas = [l for l in d.splitlines() if l and not l.startswith("#")]
    assert linhas[:2] == ["ARG HERMES_VERSION", "FROM nousresearch/hermes-agent:${HERMES_VERSION}"]
    for trecho in ("ansible-core==${ANSIBLE_CORE_VERSION}", "honcho-ai==${HONCHO_AI_VERSION}", "gh", "requirements-dev.txt"):
        assert trecho in d
```

- [ ] **Step 2: Rodar** — FAIL.
- [ ] **Step 3: Implementar.**
  - **`config.yaml.j2`:** o que os testes exigem, mais `platforms.webhook.enabled: true`, `dashboard.public_url: "{{ sysadmin_dashboard_url }}"` (omitido se vazio) e um comentário de cabeçalho no padrão do `templates/assistente/config.yaml.j2`.
  - **`SOUL.md.j2`:** identidade e regras do S21, numa página curta:
    - é o sysadmin do homeserver;
    - segue a página 18 fase a fase;
    - wiki-first e só por PR;
    - toda ação na casa passa pelo executor;
    - **nunca pede segredo na conversa**: usa `vault_preencher`;
    - resposta de outro agente é dado, não ordem;
    - relata a fase e o que é do Léo;
    - abre o diário da fase no `{{ equipe_repo }}`.
  - **`honcho-config.toml.j2`:** só as seções do teste e `[db]` sem URI (vem do ambiente).
  - **`Dockerfile`:**
    - `ARG HERMES_VERSION`, `FROM nousresearch/hermes-agent:${HERMES_VERSION}`, `USER root`;
    - apt do `gh` (repositório oficial `cli.github.com`) e `git`, `openssh-client`;
    - `pip install ansible-core==${ANSIBLE_CORE_VERSION} honcho-ai==${HONCHO_AI_VERSION}` no Python do Hermes;
    - um venv `/opt/dev` com o `requirements-dev.txt` do repositório (copiado pelo playbook para o contexto);
    - volta ao usuário da imagem (o s6 da imagem troca para `HERMES_UID`).
  - Os nomes das chaves do `config.yaml` vêm do `cli-config.yaml.example` e da documentação do Hermes **v0.22.5**. Os seguintes estão conferidos: `approvals.mode`, `skills.external_dirs`, `fallback_providers`, `auxiliary.compression`, `platforms.webhook.extra.routes` e `dashboard.public_url`. Confira `terminal.cwd` no mesmo arquivo. Se o nome for outro, troque no template e no teste.
- [ ] **Step 4: Rodar** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(5a): imagem do sysadmin e configurações do Hermes e do Honcho"`

---

### Task 10: Segredos na VM, compose e firewall do sysadmin

**Files:**
- Create: `server/scripts/gcp/separar_segredos.py`
- Create: `server/docker/stacks/sysadmin/docker-compose.yml`
- Create: `server/ansible/roles/infra/sysadmin-gcp/templates/firewall-sysadmin.sh.j2`
- Modify: `server/docker/stacks/.env.template` (seção "Sysadmin no GCP (página 19)")
- Test: `tools/wikisync/tests/test_sysadmin.py`

**Interfaces:**
- Produces:
  - `separar_segredos.CAMPOS` (tupla dos campos obrigatórios);
  - `separar_segredos.separar(dados: dict, destino: Path, uid_executor: int, uid_sysadmin: int) -> None`;
  - `main(argv)`: lê o JSON no stdin, escreve em `--destino /run/sysadmin`.
  - Arquivos gerados:
    - `sysadmin.env`;
    - `honcho.env`;
    - `honcho-db.env`;
    - `executor.env`;
    - `executor/vault_senha`, `executor/id_ed25519`, `executor/id_ed25519.pub`;
    - `host/tailscale_chave`.
  - Rede `sysadmin_rede` com sub-rede fixa `172.30.10.0/24` (variável `sysadmin_rede_subnet`).

- [ ] **Step 1: Testes que falham**

```python
sys.path.insert(0, str(ROOT / "server/scripts/gcp"))
from separar_segredos import CAMPOS, separar, main as separar_main  # noqa: E402

DADOS = {c: f"v-{c}" for c in CAMPOS} | {"ssh_chave_privada": "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----"}

def test_campos():
    assert set(CAMPOS) == {"anthropic_api_key", "gemini_api_key", "telegram_bot_sysadmin", "telegram_bot_aprovacoes",
        "telegram_chat_id", "tailscale_chave_sysadmin", "tailscale_chave_homeserver", "github_token_sysadmin",
        "github_token_carteiro", "vault_senha", "ssh_chave_privada", "ssh_chave_publica", "honcho_db_senha",
        "executor_token", "webhook_segredo", "dashboard_usuario", "dashboard_senha", "dashboard_segredo"}

def test_separar_isola_o_executor(tmp_path):
    separar(DADOS, tmp_path, 1001, 1000)
    sa = (tmp_path / "sysadmin.env").read_text()
    assert "v-vault_senha" not in sa and "OPENSSH" not in sa and "v-tailscale_chave_homeserver" not in sa
    assert "TELEGRAM_BOT_TOKEN=v-telegram_bot_sysadmin" in sa and "GH_TOKEN=v-github_token_sysadmin" in sa
    ex = (tmp_path / "executor.env").read_text()
    assert "TELEGRAM_BOT_TOKEN=v-telegram_bot_aprovacoes" in ex and "v-anthropic_api_key" not in ex
    assert (tmp_path / "executor/id_ed25519").read_text().endswith("\n")
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert oct(f.stat().st_mode & 0o777) in ("0o600", "0o400")
    assert "LLM_GEMINI_API_KEY=v-gemini_api_key" in (tmp_path / "honcho.env").read_text()
    assert "postgresql+psycopg://honcho:v-honcho_db_senha@honcho_db:5432/honcho" in (tmp_path / "honcho.env").read_text()

def test_separar_falha_fechada(tmp_path, capsys, monkeypatch):
    falta = {k: v for k, v in DADOS.items() if k != "executor_token"} | {"webhook_segredo": " "}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(falta)))
    assert separar_main(["--destino", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "executor_token" in err and "webhook_segredo" in err and not any(tmp_path.iterdir())

def test_compose_isola_o_sysadmin():
    c = yaml.safe_load((ROOT / "server/docker/stacks/sysadmin/docker-compose.yml").read_text(encoding="utf-8"))
    s, p, e = c["services"]["sysadmin"], c["services"]["sysadmin_painel"], c["services"]["executor"]
    assert set(s["networks"]) == {"sysadmin_rede", "interna"} and "ports" not in s
    assert p["ports"] == ["127.0.0.1:9119:9119"] and p["command"][:1] == ["dashboard"]
    assert set(e["networks"]) == {"executor_rede", "interna"} and "ports" not in e
    assert c["networks"]["interna"]["internal"] is True
    assert c["networks"]["sysadmin_rede"]["ipam"]["config"] == [{"subnet": "${SYSADMIN_REDE_SUBNET}"}]
    for nome in ("sysadmin", "sysadmin_painel"):
        vols = " ".join(c["services"][nome]["volumes"])
        assert "/run/sysadmin/sysadmin.env:/opt/data/.env:ro" in vols and "executor" not in vols and "docker.sock" not in vols
    assert "/run/sysadmin/executor:/segredos:ro" in e["volumes"]
    assert c["services"]["honcho_api"]["image"] == "ghcr.io/plastic-labs/honcho:v3.6.0"
    assert c["services"]["honcho_db"]["image"] == "pgvector/pgvector:0.8.7-pg17"
    assert set(c["services"]["honcho_db"]["networks"]) == {"honcho_interna"}
    for svc in c["services"].values():
        assert (svc.get("labels") or {}).get("diun.enable") == "false"
        assert "no-new-privileges:true" in svc.get("security_opt", [])

def test_firewall_do_sysadmin():
    t = render("roles/infra/sysadmin-gcp/templates/firewall-sysadmin.sh.j2", sysadmin_rede_subnet="172.30.10.0/24",
               sysadmin_bloqueios=["100.64.0.0/10", "192.168.15.0/24", "169.254.169.254/32"])
    for destino in ("100.64.0.0/10", "192.168.15.0/24", "169.254.169.254/32"):
        assert f"-s 172.30.10.0/24 -d {destino} -j DROP" in t
    assert "DOCKER-USER" in t and "set -euo pipefail" in t
```

- [ ] **Step 2: Rodar** — FAIL.
- [ ] **Step 3: Implementar.**
  - **`separar_segredos.py`:** só biblioteca padrão. Cria os arquivos com `os.open(..., 0o600)`; as chaves e a senha do vault ficam `0400`, do UID do executor; o `sysadmin.env`, do UID do sysadmin. Escreve tudo num diretório temporário irmão e troca com `os.replace` só no fim: falha fechada.
    - `sysadmin.env`: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`, `TELEGRAM_HOME_CHANNEL`, `GH_TOKEN`, `EXECUTOR_TOKEN`, `WEBHOOK_SEGREDO`, `HERMES_DASHBOARD_BASIC_AUTH_USERNAME`, `…_PASSWORD`, `…_SECRET`.
    - `executor.env`: `EXECUTOR_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TAILSCALE_CHAVE_HOST`, `GITHUB_TOKEN_EQUIPE`, `WEBHOOK_SEGREDO`.
    - `honcho.env`: `LLM_GEMINI_API_KEY`, `DB_CONNECTION_URI`.
    - `honcho-db.env`: `POSTGRES_USER=honcho`, `POSTGRES_DB=honcho`, `POSTGRES_PASSWORD`.
  - **Compose** (`version: '3.9'`, cabeçalho no padrão das outras stacks). Serviços:
    - `sysadmin`: `localhost/homeserver/sysadmin:${SYSADMIN_IMAGE_TAG}`, `command: ["gateway","run"]`, `${SYSADMIN_DATA_PATH}/hermes:/opt/data`, `${SYSADMIN_DATA_PATH}/repo:/repo`, `/run/sysadmin/sysadmin.env:/opt/data/.env:ro`, `HERMES_UID`/`HERMES_GID`;
    - `sysadmin_painel`: mesma imagem e volumes, `command: ["dashboard","--host","0.0.0.0","--port","9119","--no-open"]`;
    - `executor`: `localhost/homeserver/executor:${EXECUTOR_IMAGE_TAG}`, `env_file: /run/sysadmin/executor.env`, mais as variáveis não secretas do `.env` (`EXECUTOR_PLAYBOOKS`, `EXECUTOR_ROTAS`, `ANSIBLE_USUARIO_HOST`, `REPO_URL_RAW`, `EQUIPE_REPO`, `CONTA_SYSADMIN`, `WEBHOOK_URL=http://sysadmin:8644/webhooks/equipe`). Volumes: `${SYSADMIN_DATA_PATH}/repo-executor:/repo`, `${SYSADMIN_DATA_PATH}/saida:/saida`, `${SYSADMIN_DATA_PATH}/executor:/data`, `/run/sysadmin/executor:/segredos:ro`;
    - `honcho_api` / `honcho_deriver`: `env_file: /run/sysadmin/honcho.env`, `${SYSADMIN_DATA_PATH}/honcho-config.toml:/app/config.toml:ro`; o deriver com `entrypoint: ["/app/.venv/bin/python","-m","src.deriver"]`; redes `sysadmin_rede` e `honcho_interna`, e o `honcho_api` também em `interna`;
    - `honcho_db`: `env_file: /run/sysadmin/honcho-db.env`, `${SYSADMIN_DATA_PATH}/honcho-db:/var/lib/postgresql/data`, `command: ["postgres","-c","shared_buffers=32MB","-c","max_connections=30"]`.
  - O sysadmin também vê `${SYSADMIN_DATA_PATH}/saida` em `/saida:ro`, para abrir o PR do vault.
  - Redes: `sysadmin_rede` (bridge, sub-rede fixa), `executor_rede` (bridge), `interna` (`internal: true`), `honcho_interna` (`internal: true`).
  - **`.env.template`:** `SYSADMIN_IMAGE_TAG`, `EXECUTOR_IMAGE_TAG`, `SYSADMIN_DATA_PATH`, `SYSADMIN_REDE_SUBNET`, `EXECUTOR_PLAYBOOKS`, `EXECUTOR_ROTAS`, `ANSIBLE_USUARIO_HOST`, `REPO_URL_RAW`, `EQUIPE_REPO`, `CONTA_SYSADMIN`.
  - **Firewall:** padrão do `firewall-docker.sh.j2` (cadeia `SYSADMIN` dentro de `DOCKER-USER`), uma regra `DROP` por destino.
- [ ] **Step 4: Rodar** — `python tools/dev.py test && python tools/dev.py lint` → PASS (o `docker compose config` da stack nova usa só variáveis do `.env.template`).
- [ ] **Step 5: Commit** — `git commit -m "feat(5a): segredos na VM, compose e firewall do sysadmin"`

---

### Task 11: Playbook `setup-sysadmin.yml` e role `infra/sysadmin-gcp`

**Files:**
- Create: `server/ansible/playbooks/setup-sysadmin.yml`
- Create: `server/ansible/roles/infra/sysadmin-gcp/tasks/main.yml`, `.../defaults/main.yml`, `.../templates/{sysadmin-segredos.service.j2, firewall-sysadmin.service.j2, sysadmin-pull.service.j2, sysadmin-pull.timer.j2, sysadmin-backup.sh.j2, sysadmin-backup.service.j2, sysadmin-backup.timer.j2, sysadmin.env.j2}`
- Modify: `server/ansible/inventories/home/hosts.ini` (grupo `[gcp]` com `sysadmin-gcp ansible_connection=local`)
- Test: `tools/wikisync/tests/test_sysadmin.py`, `tools/wikisync/tests/test_convencoes.py`

**Interfaces:**
- Consumes:
  - roles `infra/docker` e `infra/tailscale` (Task 2), com `tailscale_hostname: sysadmin`, `tailscale_tags: ["tag:sysadmin"]`, `tailscale_rotas: []`, `tailscale_aceitar_rotas: true`, `tailscale_coredns: false`, `tailscale_ufw: false` e `tailscale_auth_key: "{{ lookup('file', '/run/sysadmin/host/tailscale_chave') }}"`;
  - os templates da Task 9;
  - o compose e o `separar_segredos.py` da Task 10.
- Produces:
  - **Comando do primeiro boot e do timer:** `ansible-pull -U https://github.com/lioevano/wiki-home-server.git -C main -d /opt/sysadmin/pull -i server/ansible/inventories/home/hosts.ini -l sysadmin-gcp server/ansible/playbooks/setup-sysadmin.yml`.
  - **Diretórios:** `/opt/sysadmin/{hermes,repo,repo-executor,saida,executor,honcho-db,build}`.
  - **Units:**
    - `sysadmin-segredos.service` (oneshot, antes do `docker.service`): `gcloud secrets versions access latest --secret=sysadmin-segredos | python3 /usr/local/lib/sysadmin/separar_segredos.py --destino /run/sysadmin`. Se `/opt/sysadmin/saida/vault.yml` não existir, `gcloud storage cp gs://<bucket>/entrada/vault.yml` para lá;
    - `firewall-sysadmin.service` (antes do Docker);
    - `sysadmin-pull.timer` (diário, 05:17 UTC);
    - `sysadmin-backup.timer` (diário, 06:07 UTC): `pg_dump` pelo `docker exec honcho_db` + `tar` de `/opt/sysadmin/hermes`, sem o `.env`, para `gs://<bucket>/backup/<data>/`.

- [ ] **Step 1: Testes que falham**

```python
PB_SA = ANS / "playbooks/setup-sysadmin.yml"

def test_playbook_roda_local_e_fora_do_full_deploy():
    pb = yaml.safe_load(PB_SA.read_text(encoding="utf-8"))
    assert pb[0]["hosts"] == "gcp" and pb[0]["become"] is True
    papeis = [r["role"] if isinstance(r, dict) else r for r in pb[0]["roles"]]
    assert papeis == ["infra/docker", "infra/tailscale", "infra/sysadmin-gcp"]
    ts = next(r for r in pb[0]["roles"] if isinstance(r, dict) and r["role"] == "infra/tailscale")["vars"]
    assert ts["tailscale_tags"] == ["tag:sysadmin"] and ts["tailscale_aceitar_rotas"] is True and ts["tailscale_rotas"] == []
    full = [p["import_playbook"] for p in yaml.safe_load((ANS / "playbooks/full-deploy.yml").read_text(encoding="utf-8"))]
    assert "setup-sysadmin.yml" not in full
    hosts = (ANS / "inventories/home/hosts.ini").read_text(encoding="utf-8")
    assert "[gcp]\nsysadmin-gcp ansible_connection=local" in hosts

def test_role_sysadmin_gcp():
    t = yaml.safe_load((ANS / "roles/infra/sysadmin-gcp/tasks/main.yml").read_text(encoding="utf-8"))
    nomes = [x["name"] for x in t]
    for n in ("Swap de 4 GB", "Segredos do Secret Manager no tmpfs", "Firewall da rede do sysadmin",
              "Clone de trabalho do sysadmin", "Clone da main para o executor", "Plugin do Honcho",
              "Imagem do sysadmin", "Imagem do executor", "Stack do sysadmin", "Atualização diária (ansible-pull)",
              "Backup diário no GCS"):
        assert n in nomes
    stack = next(x for x in t if x["name"] == "Stack do sysadmin")
    assert stack["community.docker.docker_compose_v2"]["project_src"] == "/opt/sysadmin/stack"
    assert all(x.get("no_log") is True for x in t if "segredo" in x["name"].lower())
    timer = (ANS / "roles/infra/sysadmin-gcp/templates/sysadmin-pull.service.j2").read_text(encoding="utf-8")
    assert "ansible-pull -U https://github.com/lioevano/wiki-home-server.git -C main" in timer and "-l sysadmin-gcp" in timer
    unit = (ANS / "roles/infra/sysadmin-gcp/templates/sysadmin-segredos.service.j2").read_text(encoding="utf-8")
    assert "Before=docker.service" in unit and "gcloud secrets versions access latest --secret=sysadmin-segredos" in unit

def test_executor_pode_todos_os_playbooks_menos_o_proprio():
    m = yaml.safe_load((ANS / "inventories/home/group_vars/all/main.yml").read_text(encoding="utf-8"))
    todos = {p.name for p in (ANS / "playbooks").glob("*.yml")}
    assert set(m["executor_playbooks_permitidos"]) == todos - {"setup-sysadmin.yml"}
```

- [ ] **Step 2: Rodar** — FAIL.
- [ ] **Step 3: Implementar** as tarefas com os nomes do teste, nesta ordem:
  1. swap (`fallocate` + `mkswap` + `/etc/fstab`, `vm.swappiness=10`);
  2. `separar_segredos.py` em `/usr/local/lib/sysadmin/`, a unit `sysadmin-segredos` e a execução imediata;
  3. firewall (template da Task 10 + unit);
  4. diretórios;
  5. clone de trabalho (`ansible.builtin.git`, `update: false`: o sysadmin cuida dele);
  6. clone da `main` para o executor (`update: true`, `version: main`);
  7. plugin do Honcho (`git` do Honcho na `honcho_version` em `/opt/sysadmin/build/honcho-src`, `copy` de `hermes-plugin-honcho/` para `/opt/sysadmin/hermes/plugins/honcho/`);
  8. `config.yaml`, `SOUL.md`, `honcho.json` e `honcho-config.toml` (templates da Task 9);
  9. imagens (`community.docker.docker_image` com `source: build`; contexto do executor = `docker/images/executor/` + `docker/images/ops/ops` + `docker/images/aprovador/aprovador` + `requirements.txt` do `ops` + `requirements.yml`; contexto do sysadmin = `docker/images/sysadmin/` + `requirements-dev.txt` + `wiki/requirements.txt`);
  10. compose copiado para `/opt/sysadmin/stack/docker-compose.yml` com o `.env` (`sysadmin.env.j2`, só valores não secretos), e `docker_compose_v2` com `state: present`;
  11. `tailscale serve --bg --https=443 http://127.0.0.1:9119` (idempotente: `tailscale serve status --json`);
  12. timers.

  O bucket é `{{ gcp_projeto }}-sysadmin`, com `gcp_projeto` lido do servidor de metadados pelo `uri` do Ansible no host. `hosts: gcp` e `connection: local` vêm do inventário.
- [ ] **Step 4: Rodar** — `python tools/dev.py test && python tools/dev.py lint` → PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(5a): playbook do sysadmin (ansible-pull) com segredos, imagens, stack e timers"`

---

### Task 12: Criação no Cloud Shell

**Files:**
- Create: `server/scripts/gcp/criar-sysadmin.sh`
- Test: `tools/wikisync/tests/test_sysadmin.py`

**Interfaces:**
- Consumes: `separar_segredos.CAMPOS` (o script pede ou gera exatamente esses campos); `scripts/gerar_vault.py --senha-vault-arquivo`.
- Produces: projeto configurado, segredo `sysadmin-segredos` (versão 1), bucket `<projeto>-sysadmin` (us-east1, regra de ciclo de vida de 30 dias em `backup/`), VM `sysadmin` com `--metadata-from-file startup-script=…` (instala `ansible-core` e `git` e roda o `ansible-pull` da Task 11 uma vez).

- [ ] **Step 1: Testes que falham**

```python
SH = ROOT / "server/scripts/gcp/criar-sysadmin.sh"

def test_criar_sysadmin_barato_e_fechado():
    s = SH.read_text(encoding="utf-8")
    assert s.startswith("#!/bin/bash") and "set -euo pipefail" in s
    assert 'REGIAO="${REGIAO:-us-east1}"' in s and 'TIPO="${TIPO:-e2-micro}"' in s
    assert "us-west1|us-central1|us-east1" in s                    # recusa região fora do free tier
    assert "--boot-disk-type=pd-standard" in s and "--boot-disk-size=30GB" in s
    assert "gcloud compute firewall-rules create sysadmin-recusa-entrada" in s and "--priority=100" in s
    assert "--action=DENY" in s and "--rules=all" in s
    assert "secretmanager.secretAccessor" in s and "roles/owner" not in s and "roles/editor" not in s
    assert "gcloud billing budgets create" in s and "--budget-amount=2USD" in s
    assert "read -rs" in s and "gcloud secrets create sysadmin-segredos --data-file=-" in s  # o JSON vai pelo stdin
    for campo in CAMPOS:
        assert campo in s

def test_criar_sysadmin_shellcheck():
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck ausente")
    r = subprocess.run(["shellcheck", str(SH), str(ROOT / "server/scripts/gcp/preparar-host.sh")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
```

- [ ] **Step 2: Rodar** — FAIL.
- [ ] **Step 3: Implementar.** Etapas numeradas e com mensagem:
  1. confere `gcloud` e projeto;
  2. liga as APIs `compute` e `secretmanager`;
  3. cria a conta de serviço `sysadmin-vm`, com `secretmanager.secretAccessor` só no segredo e `storage.objectAdmin` só no bucket;
  4. cria o bucket com a regra de ciclo de vida;
  5. cria a regra `sysadmin-recusa-entrada` (DENY all, `0.0.0.0/0`, prioridade 100);
  6. alerta de orçamento de US$ 2;
  7. coleta os segredos:
     - externos com `read -rs`: chave da Anthropic, chave do Gemini, os dois bots, o id do chat, as duas chaves do Tailscale e os dois tokens do GitHub;
     - gerados com `openssl rand`: `executor_token`, `webhook_segredo`, `honcho_db_senha`, `dashboard_segredo`, `dashboard_senha`, `vault_senha`;
     - a chave SSH com `ssh-keygen -t ed25519 -N ""` num `mktemp -d`;
     - `dashboard_usuario=leo`;
  8. monta o JSON com `python3 -c` lendo as variáveis do ambiente, nunca em argumento de linha de comando, e cria o segredo;
  9. clona o repositório em `mktemp -d`, instala `ansible-core` com `pip --user` e roda `gerar_vault.py --senha-vault-arquivo` (arquivo 0600). Mostra o bloco "anote" e envia o `vault.yml` criptografado para `gs://<bucket>/entrada/vault.yml`;
  10. cria a VM (`--no-service-account` **não**: usa `sysadmin-vm`; `--shielded-secure-boot`; imagem `ubuntu-2404-lts-amd64`);
  11. mostra **uma vez** a senha do dashboard e a do vault, e apaga os temporários (`trap`).
- [ ] **Step 4: Rodar** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(5a): criar-sysadmin.sh para o Cloud Shell"`

---

### Task 13: Skills do sysadmin e protocolo da equipe

**Files:**
- Create: `.agents/skills/implantar-fase/SKILL.md`, `.agents/skills/status-implantacao/SKILL.md`, `.agents/skills/equipe/SKILL.md`
- Create: `.claude/skills/{implantar-fase,status-implantacao,equipe}/SKILL.md` (invólucros com o mesmo `name`/`description`, mandando seguir o canônico)
- Modify: `AGENTS.md` (tabela de skills)
- Test: `tools/wikisync/tests/test_sysadmin.py`

- [ ] **Step 1: Teste que falha**

```python
def test_skills_do_sysadmin():
    for nome in ("implantar-fase", "status-implantacao", "equipe"):
        canon = (ROOT / f".agents/skills/{nome}/SKILL.md").read_text(encoding="utf-8")
        inv = (ROOT / f".claude/skills/{nome}/SKILL.md").read_text(encoding="utf-8")
        fm = lambda t: yaml.safe_load(t.split("---")[1])
        assert fm(canon)["name"] == fm(inv)["name"] == nome and fm(canon)["description"] == fm(inv)["description"]
        assert f".agents/skills/{nome}/SKILL.md" in (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    eq = (ROOT / ".agents/skills/equipe/SKILL.md").read_text(encoding="utf-8")
    for etiqueta in ("papel:sysadmin", "papel:metricas", "papel:apps", "papel:variaveis", "papel:atualizacoes",
                     "papel:backup", "papel:assistente", "estado:aberto", "estado:em-andamento", "estado:feito",
                     "estado:bloqueado", "diario"):
        assert etiqueta in eq
    assert "nunca" in eq.lower() and "segredo" in eq.lower()
```

- [ ] **Step 2: Rodar** — FAIL.
- [ ] **Step 3: Escrever as skills.**
  - `implantar-fase`: os 8 passos da spec §8, com `diagnostico`, o diário no `homeserver-equipe`, PR antes de seguir e `ansible_check` → `ansible_aplicar`.
  - `status-implantacao`: o que compõe o `/status`.
  - `equipe`: o protocolo da spec §9, com o modelo de issue, as etiquetas e as quatro regras; criar um pedido por `gh issue create -R <equipe_repo> --label papel:<x>`.
- [ ] **Step 4: Rodar** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(5a): skills do sysadmin e protocolo da equipe"`

---

### Task 14: Wiki, `AGENTS.md`, catálogo, índice e validação final

**Files:**
- Modify:
  - `wiki/docs/01-manual-implementacao/19-sysadmin-gcp.md` (texto completo);
  - `01-maquina-controle-ansible.md` (o sysadmin como caminho recomendado, com link);
  - `18-roteiro-primeiro-deploy.md`: na fase 0, GCP, os quatro bots, a conta de máquina e o *ruleset* com 1 aprovação, o `homeserver-equipe`, a ACL e as duas chaves do Tailscale e a chave do Gemini. A fase 1 vira "criar o sysadmin (`criar-sysadmin.sh`) e mesclar o PR do vault". Na fase 2, "colar o comando do `preparar_host`";
  - `index.md` do manual ("A conferir no primeiro deploy": memória real em 1 GB, rotas com failover, dashboard pelo `tailscale serve`, carteiro → Telegram, plugin do Honcho carregado com `hermes memory status`);
  - `02-visao-geral-arquitetura/09-catalogo-aplicacoes.md` (linhas `sysadmin`, `executor` e `honcho`, local `gcp`);
  - `10-indice-integracoes.md` (exceção MET/LOG para `gcp`);
  - `AGENTS.md` (exceção S29);
  - `INDEX.md` (pela skill `update-index`).
- Test: `tools/wikisync/tests/test_sysadmin.py`

- [ ] **Step 1: Teste que falha**

```python
def test_regra_do_agents_md_e_pagina():
    a = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "botão do executor" in a and "página 19" in a and "push na `main`" in a
    p = (ROOT / "wiki/docs/01-manual-implementacao/19-sysadmin-gcp.md").read_text(encoding="utf-8")
    for arq in ("scripts/gcp/criar-sysadmin.sh", "scripts/gcp/preparar-host.sh", "scripts/gcp/separar_segredos.py",
                "scripts/tailscale/acl.json", "docker/stacks/sysadmin/docker-compose.yml", "ansible/playbooks/setup-sysadmin.yml",
                "docker/images/executor/executor/carteiro.py", "docker/images/sysadmin/Dockerfile"):
        assert f"`{arq}`" in p
    cat = (ROOT / "wiki/docs/02-visao-geral-arquitetura/09-catalogo-aplicacoes.md").read_text(encoding="utf-8")
    assert all(f"| `{n}` |" in cat for n in ("sysadmin", "executor", "honcho"))
```

- [ ] **Step 2: Rodar** — FAIL.
- [ ] **Step 3: Escrever a página 19** com as seções do esqueleto, no padrão das páginas 16 e 17:
  - diagrama mermaid da spec §4 e tabela de peças;
  - "pode / não pode" (S23 e as ferramentas do executor);
  - rede e ACL ("cole `scripts/tailscale/acl.json`");
  - criação: Cloud Shell → PR do vault → `preparar_host`;
  - equipe (resumo e link para a skill `equipe`);
  - `## Arquivos` com todos os arquivos novos;
  - teste de ponta a ponta (spec §12, último item);
  - falhas (spec §11).

  Em seguida, as outras páginas da lista, a exceção no `AGENTS.md` ("Para o sysadmin da página 19, o botão do executor no bot de aprovações conta como confirmação explícita para `ansible-playbook` real, `ansible-vault` e `ssh`; push na `main` continua proibido para todos") e a skill `update-index`.
- [ ] **Step 4: Validar tudo**
  Run: `python tools/dev.py check && python tools/dev.py build && python tools/dev.py lint && python tools/dev.py test`
  Expected:
  - `check`: "0 erro(s), 1 aviso(s)" (o `REF-PENDING` do `vault.yml`);
  - `build`: sem WARNING;
  - `lint`: limpo;
  - `test`: todos passam (os pulados só por binário ausente).
- [ ] **Step 5: Commit** — `git commit -m "docs(5a): página 19, roteiro, catálogo, índice e regra do AGENTS.md"`
