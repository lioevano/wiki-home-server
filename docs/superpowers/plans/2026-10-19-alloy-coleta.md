# Coleta com Grafana Alloy — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar Promtail e node_exporter pelo Grafana Alloy nativo no host Proxmox e nas duas VMs (logs, métricas do host e por container), corrigir o Loki para schema v13/TSDB e o firewall do host Proxmox.

**Architecture:** Um role Ansible `infra/alloy` instala o pacote `alloy` (repositório apt da Grafana) e gera `/etc/alloy/config.alloy` de um template único com blocos condicionais (Docker/cAdvisor só nas VMs). O Alloy envia logs ao Loki e métricas ao Prometheus por `remote_write`; o Prometheus raspa só o `/metrics` do Alloy (job `alloy`) para saber se cada host está vivo. Tudo pelo fluxo wiki-first.

**Tech Stack:** Ansible (Jinja2), Grafana Alloy 1.20, Loki 3 (TSDB, schema v13), Prometheus (remote write receiver), Grafana Alerting, PVE Firewall, UFW, pytest, MkDocs.

**Spec:** `docs/superpowers/specs/2026-10-18-alloy-coleta-design.md`

## Global Constraints

- Wiki-first: bloco literal (`title="<caminho relativo a server/>"`) muda na wiki → `python3 tools/dev.py check` → `sync` (dry-run) → `sync --yes`. Arquivos estruturais (sem bloco literal: `docker/stacks/*/docker-compose.yml`, `ansible/templates/{prometheus.yml,loki-local-config.yaml,grafana/alerting/rules.yml}.j2`, `ansible/playbooks/setup-{monitoring-stack,ai}-volumes.yml`) mudam direto e são citados com caminho completo na página.
- Literais hoje: role `common` e `setup-base-ubuntu.yml` em `01-manual-implementacao/04-configuracao-base-vms-ubuntu.md`; role `proxmox-host-config` e `setup-proxmox-host.yml` em `02-proxmox-ve-host.md`; `group_vars/all/main.yml` em `01-maquina-controle-ansible.md`; `.env.template` em `00-preparacao-planejamento.md`.
- Arquivo do server que perde o bloco literal é apagado no mesmo commit (justificativa: a página que o removeu).
- Ambiente: `export HOMESERVER_VENV=$HOME/.venvs/homeserver` na mesma chamada antes de `python3 tools/dev.py ...`. `check` aceita só o aviso `REF-PENDING` do `vault.yml`; `build` sem WARNING e sem INFO de âncora.
- `alloy_version: "1.20.*"` em `group_vars/all/main.yml` (última versão na documentação em 2026-10-19 é a v1.20; o curinga aceita correções da série). Repositório: `deb [signed-by=/etc/apt/keyrings/grafana.asc] https://apt.grafana.com stable main`, chave `https://apt.grafana.com/gpg.key`.
- Alloy: escuta `0.0.0.0:12345`; `/etc/default/alloy` com `CONFIG_FILE=/etc/alloy/config.alloy` e `CUSTOM_ARGS="--server.http.listen-addr=0.0.0.0:12345"`; dados em `/var/lib/alloy/data` (padrão do pacote).
- Destinos: Loki `http://{{ core_services_vm_ip_var }}:3100/loki/api/v1/push`; Prometheus `http://{{ core_services_vm_ip_var }}:9090/api/v1/write` (inclusive na própria core).
- Etiquetas (fixas, usadas por alertas): logs `job="docker_logs"` + `container_name`; `job="system_journal"` + `unit`; `job="var_log"`; todos com `host` = `inventory_hostname`. Métricas: `job="node"` (unix) e `job="cadvisor"`, `instance` = `inventory_hostname` (`proxmox_main_host`, `core-services-vm`, `ai-desktop-vm`).
- cAdvisor: `docker_only = true`, `store_container_labels = false`.
- Alerta novo `container-reiniciando`: `changes(container_start_time_seconds{name!=""}[15m])` `gt` `reinicios_max` (= 3, `{% set %}` no topo), severidade `warning`, `for: '0s'`.
- **Desvio da spec (registrado):** o `alloy fmt` do template renderizado roda no `dev.py test` (teste pulado se o binário não existir), não no `dev.py lint` — o template precisa ser renderizado com variáveis de teste, o que já é o papel da suíte; CI e local rodam `test`.
- Comandos Ansible a partir de `server/ansible` com `-i inventories/home/hosts.ini`; nada de `ansible-playbook` contra hosts reais sem `--check`/`--syntax-check`, nem `git push`.
- Commits com o trailer da sessão (`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` e `Claude-Session: https://claude.ai/code/session_011krkX9xaiTppBasvKKgK5w`).

## Review Focus

1. **Prometheus da core não alcança o Alloy da própria core:** o container sai pela rede Docker, então o UFW da core deve liberar 12345 para `172.16.0.0/12`; nas outras VMs, só o IP da core → Task 2 testa a expressão `alloy_scrape_allowed_from`.
2. **Alloy do host Proxmox tentando ler Docker inexistente:** `alloy_docker_enabled` deve ser falso fora de `ubuntu_vms` e o template sem blocos Docker/cAdvisor → Task 2 testa a expressão e o render.
3. **`container_name` com a `/` inicial do Docker:** o alerta e as consultas usam o nome limpo → Task 2 testa a regra de relabel (`regex = "/(.*)"`).
4. **Firewall ligado cortando NFS:** as regras 2049 (VMs) e 12345 (core) precisam vir antes da tarefa que liga a política `DROP` → Task 4 testa a ordem das tarefas.
5. **Condição antiga sobrando:** nenhuma ocorrência de `ansible_distribution == 'Proxmox VE'` no `server/`; Prometheus sem o grupo `ai_desktop` não gera alvo da VM de IA → Tasks 4 e 5 testam.

---

### Task 1: Loki em schema v13/TSDB e harness de templates

**Files:**
- Create: `tools/wikisync/tests/test_observabilidade.py`
- Modify: `server/ansible/templates/loki-local-config.yaml.j2`
- Modify: `wiki/docs/01-manual-implementacao/07-deploy-apps.md` (nota por serviço "Loki/Promtail": Loki 3 com schema v13/TSDB)

**Interfaces:**
- Produces: em `test_observabilidade.py` (imports: `re`, `shutil`, `subprocess`, `pathlib.Path`, `jinja2`, `pytest`, `yaml`), `ROOT: Path` (raiz do repositório, `Path(__file__).resolve().parents[3]`) e `render(rel: str, **vars) -> str` — renderiza `server/ansible/<rel>` com `jinja2.Environment(undefined=StrictUndefined, loader=FileSystemLoader(ROOT/"server/ansible"), keep_trailing_newline=True)` e o filtro `bool` do Ansible registrado (`str(v).lower() in ("true", "1", "yes", "on")`); usado pelas Tasks 2–6.

- [ ] **Step 1: Write the failing test**

```python
def test_loki_schema_v13_tsdb():
    cfg = yaml.safe_load(render("templates/loki-local-config.yaml.j2"))
    periodo = cfg["schema_config"]["configs"][-1]
    assert periodo["schema"] == "v13" and periodo["store"] == "tsdb"
    assert periodo["object_store"] == "filesystem" and periodo["index"]["period"] == "24h"
    assert "tsdb_shipper" in cfg["storage_config"]
    assert "alertmanager_url" not in str(cfg.get("ruler", {}))
```

- [ ] **Step 2: Run** `HOMESERVER_VENV=$HOME/.venvs/homeserver python3 tools/dev.py test -k loki` → FAIL (`schema == "v11"`).
- [ ] **Step 3:** Em `loki-local-config.yaml.j2`, uma única entrada de schema `from: 2026-10-01`, `store: tsdb`, `object_store: filesystem`, `schema: v13`, `index: {prefix: index_, period: 24h}`; `storage_config.tsdb_shipper` com `active_index_directory: /loki/tsdb-index` e `cache_location: /loki/tsdb-cache`; remover o bloco `ruler`. Atualizar a nota do Loki na página 07.
- [ ] **Step 4: Run** `python3 tools/dev.py test` → PASS; `check` → 0 erro(s).
- [ ] **Step 5: Commit** `fix(loki): schema v13 com TSDB (Loki 3 não inicia com v11/boltdb-shipper)`

### Task 2: Role `infra/alloy` e `config.alloy.j2`

**Files:**
- Modify: `wiki/docs/01-manual-implementacao/04-configuracao-base-vms-ubuntu.md` — seção nova `## 4.4. Coleta com Grafana Alloy (`ansible/roles/infra/alloy/`)` com blocos literais de `ansible/roles/infra/alloy/{defaults/main.yml,tasks/main.yml,handlers/main.yml,templates/config.alloy.j2}` (criados pelo `sync`), explicação dos blocos (tabela da spec 3.2), segurança (grupo `docker`), importação de dashboards da comunidade no Grafana e o roteiro pós-deploy da spec seção 8.
- Modify: `wiki/docs/01-manual-implementacao/01-maquina-controle-ansible.md` (literal `group_vars/all/main.yml`: `alloy_version: "1.20.*"` com comentário)
- Test: `tools/wikisync/tests/test_observabilidade.py`

**Interfaces:**
- Consumes: `render` (Task 1).
- Produces: role `infra/alloy`, variáveis `alloy_version`, `alloy_listen_addr`, `alloy_loki_push_url`, `alloy_remote_write_url`, `alloy_docker_enabled` (padrão `"{{ inventory_hostname in groups['ubuntu_vms'] }}"`), `alloy_scrape_allowed_from` (padrão `"{{ '172.16.0.0/12' if inventory_hostname == 'core-services-vm' else core_services_vm_ip_var }}"`); handlers `Reload alloy` e `Restart alloy`. Tasks 3 e 4 incluem o role.

- [ ] **Step 1: Write the failing tests**

```python
ALLOY_VARS = dict(alloy_loki_push_url="http://192.168.15.67:3100/loki/api/v1/push",
                  alloy_remote_write_url="http://192.168.15.67:9090/api/v1/write")

def test_alloy_vm_com_docker():
    out = render("roles/infra/alloy/templates/config.alloy.j2", inventory_hostname="core-services-vm",
                 alloy_docker_enabled=True, **ALLOY_VARS)
    for trecho in ('loki.source.docker', 'prometheus.exporter.cadvisor', 'loki.source.journal',
                   'prometheus.exporter.unix', '"docker_logs"', '"system_journal"', '"var_log"',
                   '"cadvisor"', '"node"', 'regex = "/(.*)"', '"container_name"', '"core-services-vm"',
                   ALLOY_VARS["alloy_loki_push_url"], ALLOY_VARS["alloy_remote_write_url"]):
        assert trecho in out, trecho
    assert "{{" not in out and "{%" not in out

def test_alloy_host_sem_docker():
    out = render("roles/infra/alloy/templates/config.alloy.j2", inventory_hostname="proxmox_main_host",
                 alloy_docker_enabled=False, **ALLOY_VARS)
    assert "loki.source.docker" not in out and "cadvisor" not in out
    assert "prometheus.exporter.unix" in out and '"proxmox_main_host"' in out

@pytest.mark.skipif(shutil.which("alloy") is None, reason="binário alloy ausente")
@pytest.mark.parametrize("docker", [True, False])
def test_alloy_fmt(tmp_path, docker):
    f = tmp_path / "config.alloy"
    f.write_text(render("roles/infra/alloy/templates/config.alloy.j2", inventory_hostname="h",
                        alloy_docker_enabled=docker, **ALLOY_VARS))
    assert subprocess.run(["alloy", "fmt", str(f)], capture_output=True).returncode == 0

def _expr(defaults: dict, chave: str, **ctx) -> str:
    return jinja2.Environment().from_string(defaults[chave]).render(**ctx)

def test_alloy_defaults_por_host():
    d = yaml.safe_load((ROOT / "server/ansible/roles/infra/alloy/defaults/main.yml").read_text())
    grupos = {"ubuntu_vms": ["core-services-vm", "ai-desktop-vm"]}
    assert _expr(d, "alloy_docker_enabled", inventory_hostname="proxmox_main_host", groups=grupos) == "False"
    assert _expr(d, "alloy_docker_enabled", inventory_hostname="ai-desktop-vm", groups=grupos) == "True"
    ip = "192.168.15.67"
    assert _expr(d, "alloy_scrape_allowed_from", inventory_hostname="core-services-vm", core_services_vm_ip_var=ip) == "172.16.0.0/12"
    assert _expr(d, "alloy_scrape_allowed_from", inventory_hostname="ai-desktop-vm", core_services_vm_ip_var=ip) == ip
```

- [ ] **Step 2: Run** `python3 tools/dev.py test -k alloy` → FAIL (template inexistente).
- [ ] **Step 3: Escrever a seção 4.4 na wiki.** `tasks/main.yml` na ordem da spec 3.1: `get_url` da chave em `/etc/apt/keyrings/grafana.asc` (`mode: '0644'`); `apt_repository` (`filename: grafana`); `apt: name: "alloy={{ alloy_version }}", update_cache: true` (notify `Restart alloy`); `user: name: alloy, groups: "{{ ['adm', 'systemd-journal'] + (['docker'] if alloy_docker_enabled | bool else []) }}", append: true` (notify `Restart alloy`); `copy` de `/etc/default/alloy` (notify `Restart alloy`); `template` de `config.alloy.j2` para `/etc/alloy/config.alloy` com `validate: alloy fmt %s`, `owner: root`, `group: alloy`, `mode: '0640'` (notify `Reload alloy`); `systemd_service: alloy, enabled, started`; `community.general.ufw: rule allow, port '12345', proto tcp, from_ip "{{ alloy_scrape_allowed_from }}"` com `when: inventory_hostname in groups['ubuntu_vms']`. Handlers: `Reload alloy` (`systemd_service state: reloaded`) e `Restart alloy` (`state: restarted`). `config.alloy.j2` segue a tabela da spec 3.2, com os blocos Docker e cAdvisor dentro de `{% if alloy_docker_enabled | bool %}` (`| bool` é obrigatório: o padrão do `defaults` chega ao template como a string `"False"`, que sem o filtro seria verdadeira). Nenhum arquivo do role cita `node_exporter`/Promtail (o teste da Task 6 varre o `server/`); a história fica na wiki.
- [ ] **Step 4:** `check` → `sync` (dry-run, só os arquivos novos do role e `main.yml`) → `sync --yes`.
- [ ] **Step 5: Run** `python3 tools/dev.py test` → PASS (o `test_alloy_fmt` pula sem o binário); `lint` → OK.
- [ ] **Step 6: Commit** `feat(alloy): role infra/alloy com logs, métricas do host e cAdvisor`

### Task 3: VMs usam o Alloy; sai o node_exporter do role `common`

**Files:**
- Modify: `wiki/docs/01-manual-implementacao/04-configuracao-base-vms-ubuntu.md` — literais de `ansible/roles/common/tasks/main.yml` (sai o bloco "Instalação do Node Exporter" e a regra UFW 9100), `ansible/roles/common/handlers/main.yml` (saem os dois handlers do node_exporter), seção `### templates/node_exporter_vm.service.j2` removida, `ansible/playbooks/setup-base-ubuntu.yml` (primeiro play: `roles: [common, infra/alloy]`, comentário atualizado); textos da página sem node_exporter.
- Delete: `server/ansible/roles/common/templates/node_exporter_vm.service.j2`
- Test: `tools/wikisync/tests/test_observabilidade.py`

**Interfaces:**
- Consumes: role `infra/alloy` (Task 2).

- [ ] **Step 1: Write the failing test**

```python
def test_vms_recebem_alloy():
    plays = yaml.safe_load((ROOT / "server/ansible/playbooks/setup-base-ubuntu.yml").read_text())
    base = next(p for p in plays if p["hosts"].startswith("ubuntu_vms") and "roles" in p)
    nomes = [r["role"] if isinstance(r, dict) else r for r in base["roles"]]
    assert nomes == ["common", "infra/alloy"]
    assert "node_exporter" not in (ROOT / "server/ansible/roles/common/tasks/main.yml").read_text()
```

- [ ] **Step 2: Run** `python3 tools/dev.py test -k vms_recebem` → FAIL.
- [ ] **Step 3:** Editar a página 04 (literais acima); `check` → `sync` → `sync --yes`; apagar `node_exporter_vm.service.j2` (o `check` acusaria `ORPHAN`).
- [ ] **Step 4: Run** `test` → PASS; `check` → 0 erro(s); `lint` → OK (inclui `--syntax-check` de `setup-base-ubuntu.yml`).
- [ ] **Step 5: Commit** `feat(alloy): VMs com Alloy no lugar do node_exporter`

### Task 4: Host Proxmox — Alloy, condição `pveversion` e firewall

**Files:**
- Modify: `wiki/docs/01-manual-implementacao/02-proxmox-ve-host.md` — literais de `ansible/roles/infra/proxmox-host-config/tasks/main.yml`, `.../handlers/main.yml`, `ansible/playbooks/setup-proxmox-host.yml`; seção do template `node_exporter_host.service.j2` removida; texto do firewall (portas liberadas) e da chamada do Alloy.
- Delete: `server/ansible/roles/infra/proxmox-host-config/templates/node_exporter_host.service.j2`
- Test: `tools/wikisync/tests/test_observabilidade.py`

**Interfaces:**
- Consumes: role `infra/alloy` (Task 2).
- Produces: fato registrado `pve_binary` (`stat` de `/usr/bin/pveversion`); condição `when: pve_binary.stat.exists` em todas as tarefas e no handler `Reload PVE Firewall` que hoje usam `ansible_distribution == 'Proxmox VE'`.

- [ ] **Step 1: Write the failing tests**

```python
def test_sem_condicao_proxmox_ve():
    for f in (ROOT / "server/ansible").rglob("*.yml"):
        assert "ansible_distribution == 'Proxmox VE'" not in f.read_text(encoding="utf-8"), f

def test_firewall_host_libera_nfs_e_alloy_antes_do_drop():
    tasks = yaml.safe_load((ROOT / "server/ansible/roles/infra/proxmox-host-config/tasks/main.yml").read_text())
    nomes = [t.get("name", "") for t in tasks]
    i_regras = next(i for i, t in enumerate(tasks) if "community.proxmox.proxmox_firewall" in t)
    i_drop = next(i for i, t in enumerate(tasks) if "community.proxmox.proxmox_cluster_firewall_options" in t)
    assert i_regras < i_drop
    regras = {r["pos"]: r for r in tasks[i_regras]["community.proxmox.proxmox_firewall"]["rules"]}
    assert regras[2]["dport"] == "2049" and "vm_nfs_allowed_clients_cidr" in regras[2]["source"]
    assert regras[3]["dport"] == "12345" and "core_services_vm_ip_var" in regras[3]["source"]
    assert not any("Node Exporter" in n for n in nomes)
    play = yaml.safe_load((ROOT / "server/ansible/playbooks/setup-proxmox-host.yml").read_text())[0]
    assert [r["role"] if isinstance(r, dict) else r for r in play["roles"]] == ["infra/proxmox-host-config", "infra/alloy"]
```

- [ ] **Step 2: Run** `python3 tools/dev.py test -k "proxmox or firewall"` → FAIL.
- [ ] **Step 3:** Na página 02: primeira tarefa do role `stat: path: /usr/bin/pveversion` → `register: pve_binary`; trocar as condições; regras `pos: 2` (`dport: "2049"`, `proto: tcp`, `source: "{{ vm_nfs_allowed_clients_cidr }}"`, comentário "NFS v4 das VMs") e `pos: 3` (`dport: "12345"`, `source: "{{ core_services_vm_ip_var }}"`, comentário "Alloy: Prometheus da core-services-vm") no mesmo formato das existentes; remover o bloco do node_exporter e seus handlers; playbook com `roles: [infra/proxmox-host-config, infra/alloy]`. `check` → `sync` → `sync --yes`; apagar `node_exporter_host.service.j2`.
- [ ] **Step 4: Run** `test` → PASS; `check` → 0 erro(s); `lint` → OK.
- [ ] **Step 5: Commit** `fix(proxmox): firewall aplicado de fato (pveversion), NFS e Alloy liberados; Alloy no host`

### Task 5: Prometheus recebe remote write; job `alloy`; alertas

**Files:**
- Modify: `server/docker/stacks/apps/docker-compose.yml` (serviço `prometheus`: `command` + `--web.enable-remote-write-receiver`; `ports: ["${CORE_SERVICES_VM_IP_VAR}:9090:9090"]` com comentário "remote write dos Alloys; só na LAN, sem rota no Traefik")
- Modify: `server/ansible/templates/prometheus.yml.j2` (saem os três jobs `node_exporter_*`; entra `job_name: 'alloy'` com alvos `{{ proxmox_host_ip_var }}:12345` → `instance: 'proxmox_main_host'`, `{{ core_services_vm_ip_var }}:12345` → `'core-services-vm'` e, dentro de `{% if 'ai_desktop' in groups %}`, `{{ ai_desktop_vm_ip_var }}:12345` → `'ai-desktop-vm'`)
- Modify: `server/ansible/templates/grafana/alerting/rules.yml.j2` (`host-sem-resposta` com `up{job=~"alloy|blackbox_http"}`; `{% set reinicios_max = 3 %}`; regra `container-reiniciando` conforme Global Constraints, resumo `'{{ $$labels.name }} reiniciou mais de ' ~ reinicios_max ~ ' vezes em 15 min ({{ $$labels.instance }})'`)
- Modify: `wiki/docs/01-manual-implementacao/07-deploy-apps.md` (nota do Prometheus: remote write e 9090 na LAN), `wiki/docs/01-manual-implementacao/09-painel-notificacoes.md` (tabela de alertas)
- Test: `tools/wikisync/tests/test_observabilidade.py`

- [ ] **Step 1: Write the failing tests**

```python
PROM_VARS = dict(proxmox_host_ip_var="192.168.15.66", core_services_vm_ip_var="192.168.15.67",
                 ai_desktop_vm_ip_var="192.168.15.68")

def _jobs(groups):
    cfg = yaml.safe_load(render("templates/prometheus.yml.j2", groups=groups, **PROM_VARS))
    return {j["job_name"]: j for j in cfg["scrape_configs"]}

def test_prometheus_job_alloy():
    jobs = _jobs({"ai_desktop": ["ai-desktop-vm"]})
    assert not any(n.startswith("node_exporter") for n in jobs)
    alvos = {c["targets"][0]: c["labels"]["instance"] for c in jobs["alloy"]["static_configs"]}
    assert alvos == {"192.168.15.66:12345": "proxmox_main_host", "192.168.15.67:12345": "core-services-vm",
                     "192.168.15.68:12345": "ai-desktop-vm"}

def test_prometheus_sem_vm_ia():
    alvos = [c["targets"][0] for c in _jobs({})["alloy"]["static_configs"]]
    assert "192.168.15.68:12345" not in alvos

def test_alertas_alloy_e_reinicios():
    regras = {r["uid"]: r for r in yaml.safe_load(render("templates/grafana/alerting/rules.yml.j2"))["groups"][0]["rules"]}
    assert 'job=~"alloy|blackbox_http"' in regras["host-sem-resposta"]["data"][0]["model"]["expr"]
    r = regras["container-reiniciando"]
    assert r["data"][0]["model"]["expr"] == 'changes(container_start_time_seconds{name!=""}[15m])'
    assert r["data"][1]["model"]["conditions"][0]["evaluator"] == {"type": "gt", "params": [3]}
    assert r["labels"]["severity"] == "warning"

def test_prometheus_remote_write_na_lan():
    svc = yaml.safe_load((ROOT / "server/docker/stacks/apps/docker-compose.yml").read_text())["services"]["prometheus"]
    assert "--web.enable-remote-write-receiver" in svc["command"]
    assert "${CORE_SERVICES_VM_IP_VAR}:9090:9090" in svc["ports"]
```

- [ ] **Step 2: Run** `python3 tools/dev.py test -k "prometheus or alertas"` → FAIL.
- [ ] **Step 3:** Fazer as alterações listadas em **Files**.
- [ ] **Step 4: Run** `test` → PASS; `check` → 0 erro(s); `lint` → OK.
- [ ] **Step 5: Commit** `feat(metricas): Prometheus recebe remote write do Alloy; alertas host e reinícios`

### Task 6: Remover o Promtail

**Files:**
- Modify: `server/docker/stacks/apps/docker-compose.yml` (sai o serviço `promtail`; comentário da porta 3100 do Loki passa a "recebe logs dos Alloys")
- Modify: `server/docker/stacks/ai/docker-compose.yml` (sai `promtail_ai`; cabeçalho sem "+ Promtail")
- Modify: `server/ansible/playbooks/setup-monitoring-stack-volumes.yml` e `server/ansible/playbooks/setup-ai-volumes.yml` (saem diretórios, tarefa do template e as entradas `MONITORING_PROMTAIL_*` / `AI_STACK_PROMTAIL_*` de `stack_configs`)
- Delete: `server/ansible/templates/promtail-config.yml.j2`
- Modify: `wiki/docs/01-manual-implementacao/00-preparacao-planejamento.md` (literal `.env.template` e árvore sem Promtail), `07-deploy-apps.md`, `08-stack-ia.md` (serviços, tabela de variáveis, menções ao template)
- Test: `tools/wikisync/tests/test_observabilidade.py`

- [ ] **Step 1: Write the failing test**

```python
def test_sem_coletores_antigos():
    for f in (ROOT / "server").rglob("*"):
        if f.is_file():
            texto = f.read_text(encoding="utf-8", errors="ignore").lower()
            assert "promtail" not in texto and not re.search(r"node[_ ]exporter", texto), f
```

- [ ] **Step 2: Run** `python3 tools/dev.py test -k coletores` → FAIL.
- [ ] **Step 3:** Fazer as remoções; `.env.template` pela wiki (`check` → `sync` → `sync --yes`).
- [ ] **Step 4: Run** `test` → PASS; `check` → 0 erro(s); `lint` → OK.
- [ ] **Step 5: Commit** `refactor(logs): remove o Promtail (EOL); coleta pelo Alloy`

### Task 7: Catálogo, índice, páginas restantes e verificação final

**Files:**
- Modify: `wiki/docs/02-visao-geral-arquitetura/09-catalogo-aplicacoes.md` (linha `promtail` → `alloy`, valores da spec seção 4)
- Modify: `wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md` (`logs`: Provedor, Arquivos, Páginas, LOG-1, LOG-2, "Ao adicionar" passo 2 e "Ao remover o provedor"; `metricas`: MET-2 e a nota do cAdvisor — textos da spec seção 4)
- Modify: `wiki/docs/02-visao-geral-arquitetura/06-principios-seguranca.md`, `wiki/docs/03-guias-sustentacao/02-modificando-configuracoes-existentes.md`, `wiki/docs/03-guias-sustentacao/03-troubleshooting-comum.md`, `wiki/docs/05-referencia-rapida.md` e qualquer outra página que `git grep -n -i "promtail\|node.exporter" -- wiki/docs` ainda listar (exceto frases históricas explícitas como "substitui o node_exporter")
- Modify: `INDEX.md` (skill `update-index`)

- [ ] **Step 1:** Editar catálogo, índice e páginas.
- [ ] **Step 2: Run** `git grep -n -i "promtail\|node.exporter" -- wiki/docs server` → só frases históricas na seção 4.4 da página 04 e no `07-deploy-apps.md`.
- [ ] **Step 3:** Skill `update-index` (role novo, templates removidos, catálogo, descrições de páginas alteradas).
- [ ] **Step 4:** Skill `audit-integrations` com `integração=logs` e `integração=metricas` → nenhum ❌/⚠️.
- [ ] **Step 5: Run** `test`, `check` (0 erro(s), 1 aviso), `build` (sem WARNING nem INFO de âncora), `lint` (OK).
- [ ] **Step 6: Commit** `docs: catálogo, integrações e páginas com o Alloy`
