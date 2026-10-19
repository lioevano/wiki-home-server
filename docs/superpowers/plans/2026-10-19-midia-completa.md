# Mídia completa — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stack `media` própria com Jellyfin, Sonarr, Radarr, Lidarr, Prowlarr, Bazarr, Seerr, FlareSolverr, Recyclarr e qBittorrent atrás do gluetun (ProtonVPN), sobre um dataset único `/data` com importação por hardlink.

**Architecture:** Os serviços de mídia saem da stack `apps` para `docker/stacks/media/docker-compose.yml`, carregando `media.env` (gerado pelo `setup-media-stack-volumes.yml`, `0600`). O dataset `downloads` sai; `media` vira `/data` com `torrents/` e `media/`. Chaves das \*arr e da VPN vêm do vault. Painel, disponibilidade e alertas são ajustados; a página 10 documenta deploy e primeira configuração.

**Tech Stack:** Docker Compose (Portainer), Ansible (Jinja2), gluetun, Servarr (\*arr), Seerr, Recyclarr, Homepage, Prometheus/blackbox, Grafana Alerting, pytest, MkDocs.

**Spec:** `docs/superpowers/specs/2026-10-19-midia-completa-design.md`

## Global Constraints

- Wiki-first: literais na wiki → `check` → `sync` (dry-run) → `sync --yes`; estruturais (composes, `setup-media-stack-volumes.yml`, `setup-monitoring-stack-volumes.yml`, templates `prometheus.yml.j2`, `homepage/services.yaml.j2`, `grafana/alerting/rules.yml.j2`, `recyclarr.yml.j2`) mudam direto e são citados com caminho completo. Literais: `group_vars/all/main.yml` e `vault.yml.example` (página 01), role `common` (04), `etc_exports.j2` (02), `.env.template` (00).
- `export HOMESERVER_VENV=$HOME/.venvs/homeserver` na mesma chamada; `check` só com `REF-PENDING`; `build` sem WARNING/INFO de âncora; `lint` OK.
- Testes novos em `tools/wikisync/tests/test_midia.py`, reaproveitando `ROOT` e `render` de `test_observabilidade.py` (`from test_observabilidade import ROOT, render`).
- Serviços, imagens e portas: tabela da spec seção 3 (literal). Subdomínios: `jellyfin`, `pedidos` (seerr), `sonarr`, `radarr`, `lidarr`, `prowlarr`, `bazarr`, `qbittorrent`. `jellyfin` e `seerr` sem middleware; demais com `authelia-forwardauth@docker`.
- Variáveis do `media.env` (nomes exatos): `MEDIA_STACK_DATA_PATH`; `MEDIA_STACK_{JELLYFIN,SEERR,SONARR,RADARR,LIDARR,PROWLARR,BAZARR,GLUETUN,QBITTORRENT,RECYCLARR}_CONFIG_PATH`; `SONARR_API_KEY`, `RADARR_API_KEY`, `LIDARR_API_KEY`, `PROWLARR_API_KEY`; `PROTONVPN_WIREGUARD_PRIVATE_KEY`; mais `DOCKER_PUID`, `DOCKER_PGID`, `SYSTEM_TIMEZONE`, `BASE_DOMAIN_FROM_VAULT`.
- Vault (chaves novas no `vault.yml.example`): `arr_api_keys: {sonarr, radarr, lidarr, prowlarr}` (32 caracteres hexadecimais), `protonvpn_wireguard_private_key`, `homepage_widget_keys.bazarr`, `homepage_widget_keys.seerr`; saem `homepage_widget_keys.sonarr` e `.radarr`.
- No compose: `<APP>__AUTH__APIKEY: ${<APP>_API_KEY}` e `<APP>__AUTH__METHOD: External` para sonarr, radarr, lidarr, prowlarr (prefixos `SONARR__`, `RADARR__`, `LIDARR__`, `PROWLARR__`).
- gluetun: `VPN_SERVICE_PROVIDER=protonvpn`, `VPN_TYPE=wireguard`, `WIREGUARD_PRIVATE_KEY=${PROTONVPN_WIREGUARD_PRIVATE_KEY}`, `VPN_PORT_FORWARDING=on`, `PORT_FORWARD_ONLY=on`, `FIREWALL_INPUT_PORTS=8088`, `VPN_PORT_FORWARDING_UP_COMMAND` e `VPN_PORT_FORWARDING_DOWN_COMMAND` no formato da wiki do gluetun apontando para `http://127.0.0.1:8088/api/v2/app/setPreferences` (up: `listen_port={{PORT}}`, `current_network_interface={{VPN_INTERFACE}}`, `random_port=false`, `upnp=false`; down: `listen_port=0`, `current_network_interface=lo`). Em YAML do compose, `$` literal dos comandos vira `$$`.
- Layout: `/data/torrents/{movies,tv,music}`, `/data/media/{movies,tv,music}`.
- Nada de `docker compose up/down`, `ansible-playbook` sem `--check`/`--syntax-check` ou `git push`. Commits com o trailer da sessão.

## Review Focus

1. **qBittorrent com caminho de rede próprio vazando fora da VPN:** qualquer `ports`, `networks` ou `labels` no serviço `qbittorrent` anula o `network_mode` ou cria rota sem VPN → Task 1 testa que ele só tem `network_mode: service:gluetun`.
2. **Hardlink quebrado por montagens de origens diferentes:** \*arr com `/data` de uma variável e qBittorrent de outra → Task 1 testa que toda montagem de `/data*` usa `${MEDIA_STACK_DATA_PATH}`.
3. **`$` dos comandos do gluetun interpolado pelo Compose/Portainer:** `{{PORT}}` sobrevive, mas `$` solto vira variável vazia → Task 1 testa que o comando contém `{{PORT}}` e `{{VPN_INTERFACE}}` e nenhum `$` sem escape.
4. **`media.env` com segredos legível por todos:** Task 2 testa `mode: '0600'` na tarefa que gera o `media.env`.
5. **Alerta de VPN fora disparando também como serviço genérico (duas mensagens):** Task 4 testa que `servico-fora-do-ar` exclui `qbittorrent` e a regra `qbittorrent-ou-vpn-fora` existe.

---

### Task 1: Stack `media`

**Files:**
- Create: `server/docker/stacks/media/docker-compose.yml` (cabeçalho `# docker/stacks/media/docker-compose.yml`; `networks: proxy` e `internal_services` como `external: true`)
- Modify: `server/docker/stacks/apps/docker-compose.yml` (saem `jellyfin`, `sonarr`, `radarr`, `qbittorrent` e o bloco `# === MÍDIA ===`)
- Test: `tools/wikisync/tests/test_midia.py`

**Interfaces:**
- Produces: nomes de serviço e variáveis da Global Constraints; host interno do qBittorrent = `gluetun:8088` (usado nas Tasks 4 e 5).

- [ ] **Step 1: Write the failing tests**

```python
import re
import yaml
from test_observabilidade import ROOT, render

MEDIA = ROOT / "server/docker/stacks/media/docker-compose.yml"
APPS = ROOT / "server/docker/stacks/apps/docker-compose.yml"
SERVICOS = {"jellyfin", "seerr", "sonarr", "radarr", "lidarr", "prowlarr", "bazarr",
            "gluetun", "qbittorrent", "flaresolverr", "recyclarr"}

def _svc(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))["services"]

def test_stack_media_tem_os_servicos_e_apps_nao():
    assert set(_svc(MEDIA)) == SERVICOS
    assert not (SERVICOS & set(_svc(APPS)))

def test_qbittorrent_so_pela_vpn():
    q = _svc(MEDIA)["qbittorrent"]
    assert q["network_mode"] == "service:gluetun"
    assert not ({"ports", "networks", "labels"} & set(q))
    assert q["depends_on"]["gluetun"]["condition"] == "service_healthy"

def test_data_de_uma_unica_origem():
    for nome, s in _svc(MEDIA).items():
        for v in s.get("volumes", []):
            destino = v.split(":")[1]
            if destino.startswith("/data"):
                assert v.startswith("${MEDIA_STACK_DATA_PATH}"), (nome, v)

def test_gluetun_porta_encaminhada():
    env = _svc(MEDIA)["gluetun"]["environment"]
    texto = str(env)
    for k in ("VPN_PORT_FORWARDING", "PORT_FORWARD_ONLY", "VPN_PORT_FORWARDING_UP_COMMAND", "WIREGUARD_PRIVATE_KEY"):
        assert k in texto
    up = env["VPN_PORT_FORWARDING_UP_COMMAND"] if isinstance(env, dict) else next(e for e in env if e.startswith("VPN_PORT_FORWARDING_UP_COMMAND"))
    assert "{{PORT}}" in up and "{{VPN_INTERFACE}}" in up and "127.0.0.1:8088" in up
    assert not re.search(r"(?<!\$)\$(?![\${])", up)

def test_exposicao_e_autenticacao():
    s = _svc(MEDIA)
    for nome, sub in (("jellyfin", "jellyfin"), ("seerr", "pedidos")):
        lab = s[nome]["labels"]
        assert f"Host(`{sub}.${{BASE_DOMAIN_FROM_VAULT}}`)" in str(lab)
        assert "authelia" not in str(lab)
    for nome in ("sonarr", "radarr", "lidarr", "prowlarr", "bazarr", "gluetun"):
        assert "authelia-forwardauth@docker" in str(s[nome]["labels"]), nome
    assert "qbittorrent.${BASE_DOMAIN_FROM_VAULT}" in str(s["gluetun"]["labels"])
    for app in ("sonarr", "radarr", "lidarr", "prowlarr"):
        env = str(s[app]["environment"])
        assert f"{app.upper()}__AUTH__APIKEY" in env and f"${{{app.upper()}_API_KEY}}" in env
        assert f"{app.upper()}__AUTH__METHOD" in env and "External" in env
```

- [ ] **Step 2: Run** `python3 tools/dev.py test -k "media or qbittorrent or data_de or gluetun or exposicao"` → FAIL (arquivo inexistente).
- [ ] **Step 3:** Escrever o compose conforme a spec seção 3 e a Global Constraints (`restart: unless-stopped`, `PUID/PGID/TZ` nas imagens linuxserver; `jellyfin` com `/dev/dri`; `gluetun` com `cap_add: [NET_ADMIN]`, `devices: [/dev/net/tun:/dev/net/tun]`, volume de config em `/gluetun`; `seerr` com config em `/app/config`; `recyclarr` com config em `/config`; `flaresolverr` só em `internal_services`). Remover a mídia da `apps`.
- [ ] **Step 4: Run** `python3 tools/dev.py test` → PASS; `lint` → OK.
- [ ] **Step 5: Commit** `feat(midia): stack media com VPN (gluetun) e serviços novos`

### Task 2: Playbook de mídia, variáveis, segredos e Recyclarr

**Files:**
- Modify: `server/ansible/playbooks/setup-media-stack-volumes.yml` (diretórios de config das 10 apps com volume; árvore `/data`; `recyclarr.yml`; `stack_configs` com as variáveis da Global Constraints; `.env` com `mode: '0600'`)
- Create: `server/ansible/templates/recyclarr.yml.j2` (Sonarr `web-1080p` e Radarr `hd-bluray-web` pelos templates do TRaSH no formato do Recyclarr v7: `base_url: http://sonarr:8989` / `http://radarr:7878`, `api_key: {{ arr_api_keys.sonarr }}` / `.radarr`)
- Modify (wiki): `01-maquina-controle-ansible.md` (literal `vault.yml.example`: `arr_api_keys`, `protonvpn_wireguard_private_key`, `homepage_widget_keys.bazarr`/`.seerr`; saem `.sonarr`/`.radarr`), `00-preparacao-planejamento.md` (literal `.env.template`: bloco `# --- Stack media ---` com as variáveis; saem as de mídia do bloco apps)
- Test: `tools/wikisync/tests/test_midia.py`

- [ ] **Step 1: Write the failing tests**

```python
PB = ROOT / "server/ansible/playbooks/setup-media-stack-volumes.yml"

def _tasks():
    return yaml.safe_load(PB.read_text(encoding="utf-8"))[0]["tasks"]

def test_media_env_com_segredos_e_0600():
    t = next(t for t in _tasks() if "media.env" in str(t.get("ansible.builtin.template", {}).get("dest", "")))
    assert t["ansible.builtin.template"]["mode"] == "0600"
    nomes = {c["name"] for c in t["vars"]["stack_configs"]}
    assert {"MEDIA_STACK_DATA_PATH", "SONARR_API_KEY", "RADARR_API_KEY", "LIDARR_API_KEY",
            "PROWLARR_API_KEY", "PROTONVPN_WIREGUARD_PRIVATE_KEY"} <= nomes
    assert {f"MEDIA_STACK_{a}_CONFIG_PATH" for a in ("JELLYFIN", "SEERR", "SONARR", "RADARR", "LIDARR",
            "PROWLARR", "BAZARR", "GLUETUN", "QBITTORRENT", "RECYCLARR")} <= nomes

def test_arvore_data():
    texto = PB.read_text(encoding="utf-8")
    for p in ("torrents/movies", "torrents/tv", "torrents/music", "media/movies", "media/tv", "media/music"):
        assert p in texto

def test_recyclarr_renderiza():
    cfg = yaml.safe_load(render("templates/recyclarr.yml.j2",
                                arr_api_keys={"sonarr": "s" * 32, "radarr": "r" * 32}))
    assert cfg["sonarr"] and cfg["radarr"]
    assert "s" * 32 in str(cfg["sonarr"]) and "http://sonarr:8989" in str(cfg["sonarr"])
```

(Ajustar a navegação de `stack_configs` à forma real do playbook — hoje `vars: {stack_name, stack_configs: [...]}` na tarefa do template.)

- [ ] **Step 2: Run** `python3 tools/dev.py test -k "media_env or arvore or recyclarr"` → FAIL.
- [ ] **Step 3:** Editar playbook, criar template, editar os literais na wiki; `check` → `sync` → `sync --yes`.
- [ ] **Step 4: Run** `test` → PASS; `check` → 0 erro(s); `lint` → OK.
- [ ] **Step 5: Commit** `feat(midia): media.env com chaves do vault, árvore /data e Recyclarr`

### Task 3: Dataset único (sai `downloads`)

**Files:**
- Modify (wiki literais): `01-maquina-controle-ansible.md` (`main.yml`: sai `zfs_downloads_dataset_name`), `04-configuracao-base-vms-ubuntu.md` (role `common`: sai a montagem de `downloads`), `02-proxmox-ve-host.md` (`etc_exports.j2`: sai o export; passos manuais de ZFS: sai `zfs create data/downloads`)
- Modify: `02-visao-geral-arquitetura/03-armazenamento-zfs-nfs.md` (layout `/data`, hardlinks)
- Test: `tools/wikisync/tests/test_midia.py`

- [ ] **Step 1: Write the failing test**

```python
def test_sem_dataset_downloads():
    for f in (ROOT / "server").rglob("*"):
        if f.is_file():
            t = f.read_text(encoding="utf-8", errors="ignore")
            assert "zfs_downloads_dataset_name" not in t and "ZFS_DOWNLOADS" not in t, f
```

- [ ] **Step 2: Run** → FAIL. **Step 3:** editar a wiki; `check` → `sync --yes`. **Step 4:** `test` → PASS; `check` → 0; `lint` → OK.
- [ ] **Step 5: Commit** `refactor(dados): dataset único media (/data) para hardlinks`

### Task 4: Painel, disponibilidade e alertas

**Files:**
- Modify: `server/ansible/templates/prometheus.yml.j2` (alvos `blackbox_http` da spec seção 6; `qbittorrent` em `http://gluetun:8088/`)
- Modify: `server/ansible/templates/homepage/services.yaml.j2` (grupo `mídia` com as 8 aplicações com subdomínio, `server: core`, `container: <nome>`; widgets `sonarr`, `radarr`, `lidarr`, `prowlarr`, `bazarr`, `qbittorrent` com `url: http://gluetun:8088`, e Seerr com o tipo de widget da Homepage para Seerr — conferir na documentação da Homepage; se não houver `seerr`, usar `jellyseerr`, API compatível)
- Modify: `server/ansible/playbooks/setup-monitoring-stack-volumes.yml` (`HOMEPAGE_VAR_SONARR_KEY`/`RADARR_KEY` de `arr_api_keys`; novas `HOMEPAGE_VAR_LIDARR_KEY`, `HOMEPAGE_VAR_PROWLARR_KEY` de `arr_api_keys`, `HOMEPAGE_VAR_BAZARR_KEY`, `HOMEPAGE_VAR_SEERR_KEY` de `homepage_widget_keys`)
- Modify: `server/ansible/templates/grafana/alerting/rules.yml.j2` (`servico-fora-do-ar` com `app!~"n8n|qbittorrent"`; regra nova `qbittorrent-ou-vpn-fora`: `1 - probe_success{app="qbittorrent"}`, `gt 0`, `for: fora_do_ar_for`, `critical`, resumo `qBittorrent ou VPN (gluetun) fora: downloads parados`)
- Modify (wiki literal): `.env.template` (variáveis `HOMEPAGE_VAR_*` novas)
- Test: `tools/wikisync/tests/test_midia.py`

- [ ] **Step 1: Write the failing tests**

```python
PROM_VARS = dict(proxmox_host_ip_var="192.168.15.66", core_services_vm_ip_var="192.168.15.67",
                 ai_desktop_vm_ip_var="192.168.15.68")

def test_blackbox_midia():
    cfg = yaml.safe_load(render("templates/prometheus.yml.j2", groups={}, **PROM_VARS))
    alvos = {c["labels"]["app"]: c["targets"][0] for j in cfg["scrape_configs"] if j["job_name"] == "blackbox_http"
             for c in j["static_configs"]}
    assert alvos["qbittorrent"] == "http://gluetun:8088/"
    for app in ("lidarr", "prowlarr", "bazarr", "seerr"):
        assert app in alvos

def test_alerta_vpn_separado():
    regras = {r["uid"]: r for r in yaml.safe_load(render("templates/grafana/alerting/rules.yml.j2"))["groups"][0]["rules"]}
    assert 'app!~"n8n|qbittorrent"' in regras["servico-fora-do-ar"]["data"][0]["model"]["expr"]
    assert regras["qbittorrent-ou-vpn-fora"]["data"][0]["model"]["expr"] == '1 - probe_success{app="qbittorrent"}'
    assert regras["qbittorrent-ou-vpn-fora"]["labels"]["severity"] == "critical"

def test_homepage_midia():
    out = render("templates/homepage/services.yaml.j2", base_domain="seudominio.com",
                 ai_desktop_vm_ip_var="192.168.15.68", groups={"ai_desktop": ["ai-desktop-vm"]})
    midia = next(g for g in yaml.safe_load(out) if "mídia" in g)["mídia"]
    nomes = {list(e)[0] for e in midia}
    assert {"jellyfin", "seerr", "sonarr", "radarr", "lidarr", "prowlarr", "bazarr", "qbittorrent"} <= nomes
    assert "http://gluetun:8088" in out and "{{HOMEPAGE_VAR_SEERR_KEY}}" in out
```

(Se o template da Homepage pedir outras variáveis, passá-las no `render`.)

- [ ] **Step 2: Run** → FAIL. **Step 3:** editar os arquivos. **Step 4:** `test` → PASS; `check` → 0; `lint` → OK.
- [ ] **Step 5: Commit** `feat(notificacoes,painel): mídia na Homepage, no blackbox e alerta de VPN`

### Task 5: Documentação, catálogo, índice e verificação final

**Files:**
- Create: `wiki/docs/01-manual-implementacao/10-midia.md` (front-matter `description`; H1 `Seção 10: Mídia (Jellyfin, *arr, Seerr e VPN)`; conteúdo da spec seções 1, 3, 4, 5, 7 "Primeira configuração", 8 e o teste pós-deploy da seção 9; cita `docker/stacks/media/docker-compose.yml`, `ansible/playbooks/setup-media-stack-volumes.yml`, `ansible/templates/recyclarr.yml.j2`)
- Modify: `wiki/mkdocs.yml` (nav `'Mídia': '01-manual-implementacao/10-midia.md'` após "Painel e Notificações"), `01-manual-implementacao/index.md` (item 11)
- Modify: `07-deploy-apps.md` (sai a mídia: linha da tabela, `media.env` da junção e da tabela de variáveis, comando do playbook de mídia, notas por serviço de Jellyfin/Sonarr/Radarr, "Plex em vez de Jellyfin" vai para a 10), `09-painel-notificacoes.md` (alvos, widgets, regra `qbittorrent-ou-vpn-fora`, NTF-3 com lidarr/prowlarr/seerr), `02-visao-geral-arquitetura/06-principios-seguranca.md` (Jellyfin e Seerr públicos e riscos da spec seção 11), `03-guias-sustentacao/09-integrando-novos-servicos-stacks-existentes.md` (o exemplo passa à stack `media` e a um serviço fora dela, `unpackerr`, já que o Bazarr agora existe)
- Modify: catálogo (7 linhas novas, 4 movidas para `media / core-services-vm`, `jellyfin` `publica`), índice (`dados`: regra DAD-4 da spec seção 4; `notificacoes`: NTF-3 com `lidarr`, `prowlarr`, `seerr`)
- Modify: `INDEX.md` (skill `update-index`)

- [ ] **Step 1:** Escrever as páginas e o catálogo/índice.
- [ ] **Step 2: Run** `git grep -n "stack \`apps\`" -- wiki/docs | grep -i -E "jellyfin|sonarr|radarr|qbittorrent"` → nenhuma linha.
- [ ] **Step 3:** Skill `update-index`.
- [ ] **Step 4:** Skill `audit-integrations` para as 11 aplicações da stack `media` → sem ❌/⚠️ (só `✋`).
- [ ] **Step 5: Run** `test`, `check` (0 erro(s), 1 aviso), `build` (rc 0, sem WARNING/INFO de âncora), `lint` (OK).
- [ ] **Step 6: Commit** `docs(midia): página 10, catálogo e integrações da stack media`
