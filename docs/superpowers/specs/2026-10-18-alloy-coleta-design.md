# Design: coleta com Grafana Alloy (logs, métricas do host e de containers)

- **Data:** 2026-10-18
- **Autor:** Léo Ivan (com Claude)
- **Status:** aguardando revisão
- **Caminho:** arquitetural — sub-projeto **1** da refatoração do server (ordem aprovada: 1 Alloy, 2 mídia, 3 fotos e arquivos, 4 IA).
- **Depende de:** `2026-10-12-catalogo-integracoes-agentes-design.md` (catálogo e índice), `2026-10-14-painel-notificacoes-design.md` (alertas no Grafana).

## 1. Objetivo

O Promtail chegou ao fim da vida em 2026-03-02. Substituí-lo pelo **Grafana Alloy** como coletor único em toda a infraestrutura, assumindo três papéis:

1. **Logs** (hoje do Promtail): containers Docker, journal do systemd e `/var/log`.
2. **Métricas do host** (hoje do node_exporter): no host Proxmox e nas duas VMs.
3. **Métricas por container** (novo): cAdvisor embutido, nas VMs com Docker.

De quebra, corrigir o Loki, que com a imagem atual (Loki 3) não inicia com o schema v11/`boltdb-shipper` configurado.

### Critérios de pronto

- Nenhuma menção a `promtail` ou `node_exporter` no `server/` e na wiki, exceto em texto histórico explícito (ex.: "substitui o node_exporter").
- Role `infra/alloy` aplicado aos grupos `proxmox_hosts` e `ubuntu_vms`, com `config.alloy.j2` literal na wiki.
- Catálogo com `alloy` no lugar de `promtail`; índice com `logs` (LOG-1, LOG-2) e `metricas` (MET-2) atualizados.
- `loki-local-config.yaml.j2` em schema v13 + TSDB.
- `rules.yml.j2` com `host-sem-resposta` sobre `job="alloy"` e a regra nova `container-reiniciando`.
- `dev.py test`, `check` (só o aviso `REF-PENDING` do vault), `build` (sem WARNING nem INFO de âncora) e `lint` passam; `--syntax-check` dos playbooks alterados passa.
- Roteiro de verificação pós-deploy na wiki.

## 2. Decisões

| # | Decisão | Escolha |
|---|---|---|
| A1 | Papel do Alloy | Logs + métricas do host + métricas por container. |
| A2 | Onde | Host Proxmox, `core-services-vm` e `ai-desktop-vm` (sem cAdvisor nem logs Docker no host, que não tem Docker). |
| A3 | Forma | **Nativo**: pacote `alloy` do repositório apt da Grafana, serviço systemd, role Ansible `infra/alloy`. Mesma forma do node_exporter que ele substitui. |
| A4 | Entrega de métricas | **Push**: `prometheus.remote_write` para o Prometheus, que liga `--web.enable-remote-write-receiver`. |
| A5 | "Está vivo?" | O Prometheus raspa só o `/metrics` do próprio Alloy (job `alloy`, porta 12345) em cada host; o `up` desse job alimenta o `host-sem-resposta`. |
| A6 | Logs Docker | `loki.source.docker` pelo socket (entrega o nome do container); o usuário `alloy` entra no grupo `docker`. |
| A7 | Compatibilidade | Mesmas etiquetas de hoje: logs `job`/`host`/`container_name`/`unit`; métricas `node_*` com `instance` = nome do host no inventário. |
| A8 | Versão | `alloy_version` fixada em `group_vars/all/main.yml`; o valor é a versão estável atual, confirmada no repositório da Grafana ao escrever o plano. Atualizar = trocar o valor e rodar o playbook. |
| A9 | Loki | Schema v13 + TSDB começando direto (nada em produção, nada a migrar); remove `ruler.alertmanager_url`. |
| A10 | Dashboards | Fora de escopo; a página explica como importar dashboards da comunidade (node e cAdvisor). |
| A11 | Firewall do host Proxmox | Corrigir a condição que hoje pula todas as tarefas de firewall/repositório do role `proxmox-host-config` (`ansible_distribution` no Proxmox é `Debian`, nunca `Proxmox VE`) e incluir as regras que faltam para o firewall poder ser ligado: NFS (2049/tcp) das VMs e Alloy (12345/tcp) da `core-services-vm`. Achado durante a spec; necessário para a regra do Alloy existir. |

## 3. Componentes

### 3.1. Role `infra/alloy` (novo)

Arquivos (literais na wiki, página `04-configuracao-base-vms-ubuntu.md`, seção nova "Coleta com Alloy"):

- `ansible/roles/infra/alloy/defaults/main.yml` — `alloy_listen_addr: "0.0.0.0:12345"`, `alloy_loki_push_url`, `alloy_remote_write_url` (ambos em `http://{{ core_services_vm_ip_var }}:<porta>`), `alloy_docker_enabled` (padrão: `true` se o host está em `ubuntu_vms`).
- `ansible/roles/infra/alloy/tasks/main.yml`:
  1. Chave e repositório apt `https://apt.grafana.com stable main` em `/etc/apt/keyrings/grafana.asc`.
  2. Pacote `alloy={{ alloy_version }}`.
  3. Usuário `alloy` nos grupos `adm` e `systemd-journal` (journal e `/var/log`) e, com `alloy_docker_enabled`, `docker` (logs e cAdvisor).
  4. `/etc/default/alloy` com `CONFIG_FILE=/etc/alloy/config.alloy` e `CUSTOM_ARGS="--server.http.listen-addr={{ alloy_listen_addr }}"`.
  5. `/etc/alloy/config.alloy` a partir de `config.alloy.j2`, com `validate: alloy fmt %s`.
  6. Serviço `alloy` habilitado e iniciado; handlers `reload` (config) e `restart` (grupos, `/etc/default/alloy`, versão).
  7. Nas VMs, regra UFW para 12345/tcp: na `ai-desktop-vm`, origem `core_services_vm_ip_var`; na `core-services-vm`, origem `172.16.0.0/12` (o Prometheus em container chega ao IP do próprio host vindo da rede Docker).
- `ansible/roles/infra/alloy/handlers/main.yml`.
- `ansible/roles/infra/alloy/templates/config.alloy.j2` (seção 3.2).

Chamado por `setup-base-ubuntu.yml` (grupo `ubuntu_vms`) e `setup-proxmox-host.yml` (`proxmox_main_host`).

### 3.2. `config.alloy.j2`

Blocos, com `host`/`instance` = `{{ inventory_hostname }}`:

| Bloco | Componentes | Saída e etiquetas |
|---|---|---|
| Destinos | `loki.write "default"` (`alloy_loki_push_url`); `prometheus.remote_write "default"` (`alloy_remote_write_url`) | — |
| Journal | `loki.relabel` (`__journal__systemd_unit` → `unit`) + `loki.source.journal` (`max_age = "12h"`) | `job="system_journal"`, `host` |
| `/var/log` | `local.file_match` (`/var/log/{messages,syslog,auth.log,kern.log}`) + `loki.source.file` | `job="var_log"`, `host` |
| Docker *(só com `alloy_docker_enabled`)* | `discovery.docker` + `discovery.relabel` (`__meta_docker_container_name` sem a `/` inicial → `container_name`) + `loki.source.docker` | `job="docker_logs"`, `host`, `container_name` |
| Host | `prometheus.exporter.unix` + `prometheus.scrape` | `job="node"`, `instance`; nomes `node_*` inalterados (inclui `node_zfs_*` no host Proxmox) |
| Containers *(só com `alloy_docker_enabled`)* | `prometheus.exporter.cadvisor` (`docker_only = true`, `store_container_labels = false`) + `prometheus.scrape` | `job="cadvisor"`, `instance`; séries `container_*` com `name` |

### 3.3. Prometheus (stack `apps`)

- `command:` ganha `--web.enable-remote-write-receiver`.
- `ports:` ganha `"${CORE_SERVICES_VM_IP_VAR}:9090:9090"` (só na LAN, sem autenticação; portas publicadas pelo Docker não passam pelo UFW — mesma situação aceita para o 3100 do Loki).
- `prometheus.yml.j2`: saem os três jobs `node_exporter_*`; entra o job `alloy` com alvos `<ip>:12345` e `instance` = `proxmox_main_host`, `core-services-vm` e (se existir o grupo `ai_desktop`) `ai-desktop-vm`.

### 3.4. Loki

`loki-local-config.yaml.j2`: `schema_config` com uma entrada `from: 2026-10-01`, `store: tsdb`, `object_store: filesystem`, `schema: v13`, `index.period: 24h`; `storage_config.tsdb_shipper` com diretórios em `/loki`; sai o bloco `ruler.alertmanager_url`. A porta 3100 na LAN continua (agora recebe dos três Alloys).

### 3.5. Alertas (`rules.yml.j2`)

- `host-sem-resposta`: `1 - up{job=~"alloy|blackbox_http"}`.
- Nova `container-reiniciando` (aviso): `changes(container_start_time_seconds{name!=""}[15m]) > {{ reinicios_max }}`, com `reinicios_max = 3` no topo do arquivo junto dos demais limites; resumo com `{{ $$labels.name }}` e `{{ $$labels.instance }}`.
- As demais (`disco-cheio`, `ram-alta`, `cpu-alta`, `zfs-degradado`, `authelia-logins-falhos`) não mudam.

### 3.6. Host Proxmox (`proxmox-host-config`)

- Sai a instalação do node_exporter (tarefas, `node_exporter_host.service.j2`, handlers).
- A condição `ansible_distribution == 'Proxmox VE'` dá lugar a um fato próprio: `stat` de `/usr/bin/pveversion` no início do role, usado em todas as tarefas e handlers que hoje têm essa condição.
- Regras do PVE Firewall (nível node), além de SSH e Web UI: `pos: 2` NFS 2049/tcp de `vm_nfs_allowed_clients_cidr` (as VMs montam com `vers=4.2`, que só usa 2049); `pos: 3` Alloy 12345/tcp de `core_services_vm_ip_var`.

### 3.7. Remoções

- Serviços `promtail` (stack `apps`) e `promtail_ai` (stack `ai`); `ansible/templates/promtail-config.yml.j2`; tarefas e diretórios NFS do Promtail em `setup-monitoring-stack-volumes.yml` e `setup-ai-volumes.yml`; variáveis `MONITORING_PROMTAIL_*` e `AI_STACK_PROMTAIL_*` (`stack_configs` e `.env.template`).
- node_exporter no role `common` (tarefas, `node_exporter_vm.service.j2`, handlers, regra UFW 9100).

## 4. Catálogo e índice

- **Catálogo:** a linha `promtail` dá lugar a `alloy` — Categoria `monitoramento`; Stack/VM `host (systemd): proxmox, core-services-vm, ai-desktop-vm`; Serviços `alloy`; Exposição `interna`; Subdomínio `—`; Dados `nenhum`; Métricas `sim`; Provê `logs, metricas`; Página `04-configuracao-base-vms-ubuntu.md`.
- **`logs`:** Provedor `loki` (coleta pelo `alloy`); Arquivos `config.alloy.j2` e role `infra/alloy`; Páginas 04 e 07.
  - **LOG-1:** nenhum serviço sobrescreve `logging:` (o Alloy lê pela API do Docker, que depende do driver padrão).
  - **LOG-2:** a VM da aplicação está num grupo do inventário que recebe o role `infra/alloy` (`proxmox_hosts`, `ubuntu_vms`).
  - "Ao remover o provedor" passa a citar `config.alloy.j2` em vez de `promtail-config.yml.j2`.
- **`metricas`:** MET-2 troca a exceção `node_exporter_*` por `alloy`; nota: métricas por container de qualquer aplicação vêm do cAdvisor do Alloy, sem regra por consumidor; MET-1 continua para aplicações com `/metrics` próprio.

## 5. Páginas

| Página | Mudança |
|---|---|
| `01-manual-implementacao/04-configuracao-base-vms-ubuntu.md` | Sai o node_exporter do role `common`; seção nova "Coleta com Alloy" (role literal, `config.alloy.j2`, verificação pós-deploy, importação de dashboards). |
| `01-manual-implementacao/02-proxmox-ve-host.md` | Sai o node_exporter; condição `pveversion`; regras NFS e Alloy no firewall; chamada do role `infra/alloy`. |
| `01-manual-implementacao/07-deploy-apps.md` | Sai o Promtail; Prometheus com remote write e 9090 na LAN; Loki v13. |
| `01-manual-implementacao/08-stack-ia.md` | Sai o `promtail_ai`. |
| `01-manual-implementacao/09-painel-notificacoes.md` | `host-sem-resposta` sobre `alloy`; regra `container-reiniciando`. |
| `01-manual-implementacao/00-preparacao-planejamento.md` | Árvore e `.env.template` sem Promtail. |
| `02-visao-geral-arquitetura/06-principios-seguranca.md` | Grupo `docker` do `alloy`; portas 9090, 3100 e 12345 na LAN. |
| `03-guias-sustentacao/02-modificando-configuracoes-existentes.md`, `03-guias-sustentacao/03-troubleshooting-comum.md`, `05-referencia-rapida.md` | `systemctl status alloy`, interface em `:12345` no lugar de node_exporter/Promtail. |
| Catálogo e índice | Seção 4. |

## 6. Falhas

| Situação | Comportamento |
|---|---|
| Prometheus fora | WAL do `remote_write` em `/var/lib/alloy/data` reenvia ao voltar (~2 h sem perda). |
| Loki fora | `loki.write` tenta de novo com espera progressiva; fila em memória — se o Alloy reiniciar durante a queda, essas linhas se perdem. |
| Alloy reinicia | Retoma do ponto lido (posições em `/var/lib/alloy/data`). |
| Alloy parado ou host fora | `up{job="alloy"} = 0` → `host-sem-resposta` (Telegram). |
| Config inválida | `validate: alloy fmt %s` impede gravar; o serviço segue com a config anterior. |
| Ordem de deploy | Indiferente: o Alloy do host Proxmox sobe antes do Prometheus e do Loki e fica tentando. `full-deploy.yml` mantém a ordem. |

## 7. Segurança

- `alloy` no grupo `docker` equivale a root na VM (recomendação da própria documentação do cAdvisor); mesmo nível de um container privilegiado.
- 9090 (Prometheus), 3100 (Loki) e 12345 (Alloy) sem autenticação, limitados à LAN; 12345 restrito por UFW/PVE Firewall à `core-services-vm`. A interface do Alloy mostra a configuração, que não contém segredos.
- O firewall do host Proxmox passa a ser aplicado de fato (A11); as regras de SSH, Web UI e NFS entram antes da política `DROP`, como já está ordenado no role.

## 8. Verificação

- **Antes do commit:** `dev.py test`, `check`, `build`, `lint`; `--syntax-check` de `setup-base-ubuntu.yml`, `setup-proxmox-host.yml`, `setup-monitoring-stack-volumes.yml`, `setup-ai-volumes.yml`. `dev.py lint` ganha `alloy fmt` do template renderizado, só quando o binário existir (sem ele, aviso e segue, como no `docker compose config`).
- **Pós-deploy (roteiro na página 04):**
  1. `systemctl status alloy` nos três hosts; interface em `http://<host>:12345`.
  2. Prometheus: `up{job="alloy"}` = 1 nos três; `node_zfs_zpool_state` do `proxmox_main_host`; `container_last_seen{name="traefik"}` da core.
  3. Grafana Explore: `{job="docker_logs", host="ai-desktop-vm"}`, `{job="system_journal", host="proxmox_main_host"}`; alerta `authelia-logins-falhos` com dados.
  4. Montagens NFS das VMs funcionando com o PVE Firewall ligado.

## 9. Fora de escopo

- Dashboards versionados do Grafana.
- Traces e OTLP.
- Autenticação nos endpoints de LAN (9090, 3100, 12345).
- Alertas sobre métricas de container além de `container-reiniciando`.

## 10. Riscos

- **PVE Firewall passa a valer pela primeira vez:** uma regra faltando corta acesso (ex.: outra porta usada por alguma VM). Mitigação: regras antes do `DROP`, `--check` antes, e o roteiro confere SSH, Web UI e NFS logo após o playbook.
- **Cardinalidade do cAdvisor:** `docker_only` e `store_container_labels = false` limitam as séries; `disabled_metrics` fica no padrão.
- **Versão do Alloy:** componentes e argumentos conferidos na documentação da versão fixada ao escrever o plano.
