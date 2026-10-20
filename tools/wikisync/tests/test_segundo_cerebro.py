"""Testes do segundo cérebro (4b): dataset notes, conversor, stack notes (Syncthing, qmd, escrita, proxies MCP) e integrações."""
from __future__ import annotations

import yaml

from test_observabilidade import ROOT, render

MAIN = ROOT / "server/ansible/inventories/home/group_vars/all/main.yml"
COMMON = ROOT / "server/ansible/roles/common/tasks/main.yml"
PVE_TASKS = ROOT / "server/ansible/roles/infra/proxmox-host-config/tasks/main.yml"
AI_IP = "192.168.15.68"


def _main() -> dict:
    return yaml.safe_load(MAIN.read_text(encoding="utf-8"))


def _mount_itens() -> dict:
    tarefas = yaml.safe_load(COMMON.read_text(encoding="utf-8"))
    mount = next(t for t in tarefas if "ansible.posix.mount" in t)
    return mount, {i["dataset_name"]: i for i in mount["loop"]}


# --- Task 1: dataset, exports, montagens e snapshots ---

def test_export_notes_so_para_a_vm_de_ia():
    ctx = {**_main(), "docker_puid": 1001, "docker_pgid": 1001, "ai_desktop_vm_ip_var": AI_IP,
           "groups": {"virtual_machines": ["ai-desktop-vm"]}}
    out = render("roles/infra/proxmox-host-config/templates/etc_exports.j2", **ctx)
    linhas = [l for l in out.splitlines() if l.startswith("/data/notes ")]
    assert linhas == [f"/data/notes {AI_IP}(rw,sync,no_subtree_check,all_squash,anonuid=1001,anongid=1001)"]


def test_montagens_da_vm_de_ia():
    assert _main()["zfs_notes_dataset_name"] == "notes"
    mount, itens = _mount_itens()
    notes = itens["{{ zfs_notes_dataset_name }}"]
    assert notes["when_condition"] == "'ai_desktop' in group_names"
    files_ia = [i for i in mount["loop"] if i["dataset_name"] == "{{ zfs_files_dataset_name }}"
                and "'ai_desktop' in group_names" in i.get("when_condition", "")]
    assert len(files_ia) == 1 and files_ia[0]["opts"].startswith("ro,")
    assert "'ai_desktop' in group_names" in itens["{{ zfs_rag_sources_dataset_name }}"]["when_condition"]
    assert "item.opts | default(" in mount["ansible.posix.mount"]["opts"]
    assert "'ai-desktop-vm' in group_names" not in COMMON.read_text(encoding="utf-8")


def test_snapshots_so_em_notes():
    tarefas = yaml.safe_load(PVE_TASKS.read_text(encoding="utf-8"))
    pacotes = [t for t in tarefas if "zfs-auto-snapshot" in str(t.get("ansible.builtin.apt", {}).get("name", ""))]
    assert pacotes
    props = {t["community.general.zfs"]["name"]: t["community.general.zfs"]["extra_zfs_properties"]
             for t in tarefas if "community.general.zfs" in t}
    assert props["data"] == {"com.sun:auto-snapshot": "false"}
    assert props["data/{{ zfs_notes_dataset_name }}"] == {"com.sun:auto-snapshot": "true"}


# --- Task 2: conversor de documentos do Nextcloud ---

import importlib.util  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402

import pytest  # noqa: E402

CONVERSOR = ROOT / "server/ansible/templates/notes/conversor.py"


def _conv():
    spec = importlib.util.spec_from_file_location("conversor", CONVERSOR)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["conversor"] = mod  # dataclasses precisa do módulo registrado
    spec.loader.exec_module(mod)
    return mod


def _falso(p):
    if "quebrado" in p.name:
        raise ValueError("arquivo corrompido")
    return f"texto de {p.name}"


EXT = {"pdf", "docx", "md", "txt"}


def _arq(base, rel, conteudo="x"):
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(conteudo, encoding="utf-8")
    return p


def test_converte_e_mantem(tmp_path):
    c = _conv()
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    _arq(origem, "a.pdf"), _arq(origem, "sub/b.docx"), _arq(origem, "foto.jpg")
    r = c.sincronizar(origem, destino, EXT, 10_000, _falso)
    assert (r.convertidos, r.mantidos, r.removidos, r.falhas) == (2, 0, 0, [])
    b = (destino / "sub/b.docx.md").read_text(encoding="utf-8")
    assert b.startswith('---\norigem: "Nextcloud/sub/b.docx"\n---\n\n') and "texto de b.docx" in b
    assert (destino / "a.pdf.md").exists() and not (destino / "foto.jpg.md").exists()
    r = c.sincronizar(origem, destino, EXT, 10_000, _falso)
    assert (r.convertidos, r.mantidos) == (0, 2)
    a = origem / "a.pdf"
    a.write_text("conteúdo novo", encoding="utf-8")
    os.utime(a, ns=(a.stat().st_atime_ns, a.stat().st_mtime_ns + 5_000_000_000))
    r = c.sincronizar(origem, destino, EXT, 10_000, _falso)
    assert (r.convertidos, r.mantidos) == (1, 1)


def test_remove_o_que_sumiu(tmp_path):
    c = _conv()
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    _arq(origem, "a.pdf"), _arq(origem, "sub/b.docx")
    c.sincronizar(origem, destino, EXT, 10_000, _falso)
    (origem / "sub/b.docx").unlink()
    r = c.sincronizar(origem, destino, EXT, 10_000, _falso)
    assert r.removidos == 1
    assert not (destino / "sub/b.docx.md").exists() and not (destino / "sub").exists()
    manifesto = (destino / ".manifesto.json").read_text(encoding="utf-8")
    assert "sub/b.docx" not in manifesto and "a.pdf" in manifesto


def test_falha_nao_para_o_resto(tmp_path):
    c = _conv()
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    _arq(origem, "quebrado.pdf"), _arq(origem, "ok.pdf")
    r = c.sincronizar(origem, destino, EXT, 10_000, _falso)
    assert (destino / "ok.pdf.md").exists()
    assert r.falhas == ["quebrado.pdf"] and r.convertidos == 1
    assert "quebrado.pdf" not in (destino / ".manifesto.json").read_text(encoding="utf-8")


def test_ignora_symlink_oculto_e_grande(tmp_path):
    c = _conv()
    origem, destino, fora = tmp_path / "origem", tmp_path / "destino", tmp_path / "fora"
    alvo = _arq(fora, "segredo.pdf")
    origem.mkdir()
    os.symlink(alvo, origem / "link.pdf")
    os.symlink(fora, origem / "pasta-link")
    _arq(origem, ".oculto/x.pdf"), _arq(origem, ".y.pdf"), _arq(origem, "grande.pdf", "z" * 200)
    _arq(origem, "ok.md")
    antes = {p for p in tmp_path.rglob("*")}
    r = c.sincronizar(origem, destino, EXT, 100, _falso)
    assert r.convertidos == 1
    novos = {p for p in tmp_path.rglob("*")} - antes
    assert all(destino in p.parents or p == destino for p in novos)
    assert {p.name for p in novos if p.is_file()} == {"ok.md.md", ".manifesto.json"}


def test_origem_vazia_nao_apaga(tmp_path):
    c = _conv()
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    _arq(origem, "a.pdf")
    c.sincronizar(origem, destino, EXT, 10_000, _falso)
    (origem / "a.pdf").unlink()
    with pytest.raises(c.OrigemVazia):
        c.sincronizar(origem, destino, EXT, 10_000, _falso)
    with pytest.raises(c.OrigemVazia):
        c.sincronizar(tmp_path / "nao-existe", destino, EXT, 10_000, _falso)
    assert (destino / "a.pdf.md").exists()
    args = ["--origem", str(tmp_path / "nao-existe"), "--destino", str(destino), "--extensoes", "pdf", "--max-mb", "1"]
    assert c.main(args) == 2
    assert (destino / "a.pdf.md").exists()


# --- Task 3: busca (qmd) e esqueleto da stack notes ---

from test_midia import _env, _svc  # noqa: E402
from test_fotos_arquivos import COMUNS, _configs, _env_task, _pb_tasks, _vars_compose  # noqa: E402

NOTES = ROOT / "server/docker/stacks/notes/docker-compose.yml"
PB_NOTES = ROOT / "server/ansible/playbooks/setup-notes-volumes.yml"


def _vols(servico) -> list[str]:
    return list(servico.get("volumes", []))


def test_qmd_so_leitura_e_sem_porta():
    q = _svc(NOTES)["qmd"]
    assert "ports" not in q
    v = _vols(q)
    for nome in ("pessoal", "trabalho", "estudos"):
        assert f"${{NOTES_STACK_DATA_PATH}}/{nome}:/notes/{nome}:ro" in v
    assert "${NOTES_STACK_DOCUMENTOS_PATH}:/notes/documentos:ro" in v
    assert sorted(x for x in v if not x.endswith(":ro")) == sorted(
        ["${NOTES_STACK_QMD_CONFIG_PATH}:/config", "${NOTES_STACK_QMD_CACHE_PATH}:/cache"])
    assert q["devices"] == ["/dev/dri"] and q["group_add"] == ["${AI_RENDER_GID}"]
    assert q["image"] == "${QMD_IMAGE}" and q["pull_policy"] == "never"
    assert q["labels"]["diun.enable"] == "false"
    assert q["command"] == ["qmd", "mcp", "--http", "--host", "0.0.0.0", "--port", "8181"]
    e = _env(q)
    assert e["QMD_CONFIG_DIR"] == "/config" and e["XDG_CACHE_HOME"] == "/cache"
    assert e["QMD_ALLOWED_HOSTS"] == "qmd,qmd:8181,notas.${BASE_DOMAIN_FROM_VAULT}"
    assert "notes_mcp" in q["networks"]
    redes = yaml.safe_load(NOTES.read_text(encoding="utf-8"))["networks"]
    assert redes["notes_mcp"]["name"] == "notes_mcp"


def test_index_qmd():
    cfg = yaml.safe_load(render("templates/notes/index.yml.j2", qmd_modelos={}))
    col = cfg["collections"]
    assert set(col) == {"pessoal", "trabalho", "estudos", "documentos"}
    for nome, c in col.items():
        assert c["path"] == f"/notes/{nome}" and c["pattern"] == "**/*.md"
        assert c["ignore"] == [".obsidian/**", ".trash/**", "**/*.sync-conflict-*"]
        assert c["context"]["/"]
    assert "models" not in cfg
    cfg = yaml.safe_load(render("templates/notes/index.yml.j2", qmd_modelos={"embed": "hf:x/y/z.gguf"}))
    assert cfg["models"] == {"embed": "hf:x/y/z.gguf"}


def _tarefa(pb, modulo, **filtro):
    for t in _pb_tasks(pb):
        args = t.get(modulo)
        if isinstance(args, dict) and all(str(args.get(k, "")).endswith(v) for k, v in filtro.items()):
            return t
    raise AssertionError(f"tarefa {modulo} {filtro} ausente")


def test_imagens_locais_reconstroem():
    for nome, tag, dockerfile in (("qmd", "{{ qmd_version }}", "Dockerfile.qmd.j2"),
                                  ("notes-conversor", "{{ markitdown_version }}", "Dockerfile.conversor.j2")):
        img = _tarefa(PB_NOTES, "community.docker.docker_image", name=f"localhost/homeserver/{nome}")
        a = img["community.docker.docker_image"]
        assert a["source"] == "build" and a["tag"] == tag
        tpl = _tarefa(PB_NOTES, "ansible.builtin.template", src=dockerfile)
        assert a["force_source"].startswith("{{ " + tpl["register"] + ".changed")
    conv = _tarefa(PB_NOTES, "community.docker.docker_image", name="localhost/homeserver/notes-conversor")
    assert "script_conversor.changed" in conv["community.docker.docker_image"]["force_source"]
    q = render("templates/notes/Dockerfile.qmd.j2", qmd_version="2.8.3")
    assert "@tobilu/qmd@2.8.3" in q and "mesa-vulkan-drivers" in q and "node:22-bookworm-slim" in q
    c = render("templates/notes/Dockerfile.conversor.j2", markitdown_version="0.1.8")
    assert "markitdown[pdf,docx,pptx,xlsx]==0.1.8" in c


def test_variaveis_notes_no_env():
    cfg = _configs(PB_NOTES, "notes.env")
    assert _vars_compose(NOTES) <= set(cfg) | COMUNS
    assert _env_task(PB_NOTES, "notes.env")["ansible.builtin.template"]["mode"] == "0600"
    for k in ("NOTES_STACK_SYNCTHING_DB_PATH", "NOTES_STACK_QMD_CACHE_PATH", "NOTES_STACK_DOCUMENTOS_PATH",
              "NOTES_STACK_MCP_AUTH_BUSCA_PATH", "NOTES_STACK_MCP_AUTH_ESCRITA_PATH"):
        assert cfg[k].startswith("{{ vm_local_data_path }}/"), k
    assert cfg["NOTES_STACK_DATA_PATH"] == "{{ vm_nfs_mount_base_path }}/{{ zfs_notes_dataset_name }}"
    for img in ("qmd", "notes-escrita"):
        assert any(v.startswith(f"localhost/homeserver/{img}:") for v in cfg.values()), img
    for s in _svc(NOTES).values():
        assert not str(s.get("image", "")).endswith(":latest")


# --- Task 4: escrita com escopo ---

def test_escrita_so_trabalho_e_estudos():
    e = _svc(NOTES)["notes_escrita"]
    assert _vols(e) == ["${NOTES_STACK_DATA_PATH}/trabalho:/notes/trabalho",
                        "${NOTES_STACK_DATA_PATH}/estudos:/notes/estudos"]
    assert "ports" not in e
    assert e["user"] == "${DOCKER_PUID}:${DOCKER_PGID}"
    assert e["networks"] == ["notes_mcp"]
    assert e["image"] == "${NOTES_ESCRITA_IMAGE}" and e["pull_policy"] == "never"
    assert e["command"] == ["supergateway", "--stdio", "mcp-server-filesystem /notes/trabalho /notes/estudos",
                            "--outputTransport", "streamableHttp", "--stateful", "--sessionTimeout", "600000",
                            "--port", "8000", "--healthEndpoint", "/healthz"]
    img = _tarefa(PB_NOTES, "community.docker.docker_image", name="localhost/homeserver/notes-escrita")
    a = img["community.docker.docker_image"]
    assert a["tag"] == "{{ mcp_filesystem_version }}"
    tpl = _tarefa(PB_NOTES, "ansible.builtin.template", src="Dockerfile.escrita.j2")
    assert a["force_source"] == "{{ " + tpl["register"] + ".changed }}"
    d = render("templates/notes/Dockerfile.escrita.j2", supergateway_version="4.2.0", mcp_filesystem_version="2.0.0")
    assert "node:24-bookworm-slim" in d and "supergateway@4.2.0" in d
    assert "@modelcontextprotocol/server-filesystem@2.0.0" in d and "USER node" in d


def test_ninguem_mais_escreve_em_pessoal():
    for nome, s in _svc(NOTES).items():
        for v in _vols(s):
            if "/pessoal" in v:
                assert v.endswith(":ro"), (nome, v)
            if v.startswith("${NOTES_STACK_DATA_PATH}:"):
                assert nome == "syncthing", (nome, v)
            assert "files" not in v.split(":")[0].lower(), (nome, v)


# --- Task 5: Syncthing ---

def test_syncthing():
    s = _svc(NOTES)["syncthing"]
    assert s["image"] == "docker.io/syncthing/syncthing:2.1.6"
    e = _env(s)
    assert e["PUID"] == "${DOCKER_PUID}" and e["PGID"] == "${DOCKER_PGID}"
    assert e["STHOMEDIR"] == ""
    assert e["STCONFDIR"] == "/var/syncthing/config" and e["STDATADIR"] == "/var/syncthing/data"
    assert e["STGUIAPIKEY"] == "${SYNCTHING_API_KEY}" and e["STNOUPGRADE"] == "1"
    assert sorted(_vols(s)) == sorted(["${NOTES_STACK_DATA_PATH}:/var/syncthing/notes",
                                       "${NOTES_STACK_SYNCTHING_CONFIG_PATH}:/var/syncthing/config",
                                       "${NOTES_STACK_SYNCTHING_DB_PATH}:/var/syncthing/data"])
    assert s["ports"] == ["${AI_DESKTOP_VM_IP}:8384:8384", "${AI_DESKTOP_VM_IP}:22000:22000/tcp",
                          "${AI_DESKTOP_VM_IP}:22000:22000/udp"]
    assert "/rest/noauth/health" in " ".join(s["healthcheck"]["test"])


def test_syncthing_generate():
    t = next(t for t in _pb_tasks(PB_NOTES)
             if "generate" in str(t.get("ansible.builtin.command", {}).get("cmd", "")))
    c = t["ansible.builtin.command"]
    assert "docker run --rm" in c["cmd"] and "docker.io/syncthing/syncthing:{{ syncthing_version }}" in c["cmd"]
    assert "generate --gui-user {{ syncthing_gui_user }} --gui-password -" in c["cmd"]
    assert c["stdin"] == "{{ syncthing_gui_password }}"
    assert c["creates"].endswith("syncthing/config/config.xml")
    assert t["no_log"] is True
    assert _main()["syncthing_version"] == "2.1.6"


# --- Task 6: acesso remoto (mcp-auth-proxy, Authelia, Traefik) ---

from test_fotos_arquivos import DOM, OIDC, _authelia  # noqa: E402

VAULT_EX = ROOT / "server/ansible/inventories/home/group_vars/all/vault.yml.example"
PROXIES = (("mcp_auth_busca", "notas", "http://qmd:8181/mcp", "8481", "BUSCA"),
           ("mcp_auth_escrita", "escrita", "http://notes_escrita:8000/mcp", "8482", "ESCRITA"))


def test_proxies_mcp():
    svc = _svc(NOTES)
    for nome, sub, backend, porta, dados in PROXIES:
        p = svc[nome]
        assert p["image"] == "ghcr.io/sigbit/mcp-auth-proxy:v2.10.2", nome
        assert p["command"] == [backend]
        assert p["ports"] == [f"${{AI_DESKTOP_VM_IP}}:{porta}:80"]
        assert p["networks"] == ["notes_mcp"]
        assert _vols(p) == [f"${{NOTES_STACK_MCP_AUTH_{dados}_PATH}}:/data"]
        e = _env(p)
        assert e["EXTERNAL_URL"] == f"https://{sub}.${{BASE_DOMAIN_FROM_VAULT}}"
        assert e["NO_AUTO_TLS"] == "true" and e["LISTEN"] == ":80" and e["DATA_PATH"] == "/data"
        assert e["OIDC_CONFIGURATION_URL"] == "https://auth.${BASE_DOMAIN_FROM_VAULT}/.well-known/openid-configuration"
        assert e["OIDC_CLIENT_ID"] == "mcp" and e["OIDC_CLIENT_SECRET"] == "${MCP_OIDC_CLIENT_SECRET}"
        assert e["OIDC_SCOPES"] == "openid,profile,email,groups"
        assert e["OIDC_ALLOWED_ATTRIBUTES"] == "/groups=admins"
        assert e["AUTH_HMAC_SECRET"] == "${MCP_AUTH_HMAC_SECRET}"
        assert e["TRUSTED_PROXIES"] == "${CORE_SERVICES_VM_IP}"
        assert "PASSWORD" not in e
    assert _main()["mcp_auth_proxy_version"] == "v2.10.2"


def test_cliente_oidc_mcp():
    cli = {c["client_id"]: c for c in yaml.safe_load(_authelia())["identity_providers"]["oidc"]["clients"]}
    c = cli["mcp"]
    assert c["client_secret"] == OIDC["mcp"]["secret_digest"] and c["public"] is False
    assert c["authorization_policy"] == "two_factor"
    assert c["require_pkce"] is False and "pkce_challenge_method" not in c
    assert c["token_endpoint_auth_method"] == "client_secret_basic"
    assert c["scopes"] == ["openid", "profile", "email", "groups"]
    assert c["redirect_uris"] == [f"https://notas.{DOM}/.auth/oidc/callback", f"https://escrita.{DOM}/.auth/oidc/callback"]
    vault = yaml.safe_load(VAULT_EX.read_text(encoding="utf-8"))
    assert "mcp" in vault["oidc_clients"]
    for k in ("mcp_auth_hmac_secret", "syncthing_gui_password", "syncthing_api_key"):
        assert k in vault, k


def test_bypass_notas_e_escrita():
    regras = yaml.safe_load(_authelia())["access_control"]["rules"]
    curinga = next(i for i, r in enumerate(regras) if r["domain"] == f"*.{DOM}")
    for sub in ("notas", "escrita"):
        idx = [i for i, r in enumerate(regras) if r["domain"] == f"{sub}.{DOM}"]
        assert len(idx) == 1, sub
        assert regras[idx[0]]["policy"] == "bypass" and "resources" not in regras[idx[0]]
        assert idx[0] < curinga


def test_rotas_notes():
    cfg = yaml.safe_load(render("roles/infra/traefik-config/templates/dynamic_rag_services.yml.j2",
                                base_domain=DOM, ai_desktop_vm_ip_var=AI_IP))
    rot, srv = cfg["http"]["routers"], cfg["http"]["services"]
    por_host = {r["rule"]: r for r in rot.values()}
    for sub, porta, auth in (("notas", 8481, False), ("escrita", 8482, False), ("sync", 8384, True)):
        r = por_host[f"Host(`{sub}.{DOM}`)"]
        assert ("authelia-forwardauth@docker" in r.get("middlewares", [])) is auth, sub
        assert srv[r["service"]]["loadBalancer"]["servers"] == [{"url": f"http://{AI_IP}:{porta}"}]
