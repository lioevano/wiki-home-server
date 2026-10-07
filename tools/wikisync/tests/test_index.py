from __future__ import annotations

from wikisync.config import load_config
from wikisync.index import build_index, file_kind, render_markdown, write_index

PAGE = (
    "---\ndescription: Página D\n---\n# Título I\n\n"
    "Usa `ansible/b.yml`.\n\n"
    '```yaml title="ansible/a.yml"\nx: 1\n```\n\n'
    '```yaml title="ansible/c.yml"\nc: 1\n```\n'
)


def repo(make_repo, **extra):
    files = {
        "wiki/docs/index.md": PAGE,
        "server/ansible/a.yml": "x: 1\n",
        "server/ansible/b.yml": "b: 1\n",
        "server/ansible/c.yml": "c: 2\n",
    }
    files.update(extra)
    return load_config(make_repo(files))


def test_pages_and_server_files(make_repo):
    idx = build_index(repo(make_repo))
    assert idx["pages"] == [{
        "path": "index.md", "title": "Título I", "description": "Página D",
        "literal": ["ansible/a.yml", "ansible/c.yml"],
        "refs": ["ansible/a.yml", "ansible/b.yml", "ansible/c.yml"],
    }]
    files = {f["path"]: f for f in idx["server_files"]}
    assert files["ansible/b.yml"] == {"path": "ansible/b.yml", "kind": "outro", "pages": ["index.md"], "literal_state": None}


def test_literal_state_values(make_repo):
    files = {f["path"]: f["literal_state"] for f in build_index(repo(make_repo))["server_files"]}
    assert files["ansible/a.yml"] == "sincronizado"
    assert files["ansible/c.yml"] == "divergente"


def test_file_kind_rules():
    assert file_kind("ansible/inventories/home/hosts.ini") == "inventario"
    assert file_kind("ansible/playbooks/vm-deploy.yml") == "playbook"
    assert file_kind("ansible/roles/infra/docker/tasks/main.yml") == "role-tasks"
    assert file_kind("ansible/roles/infra/docker/handlers/main.yml") == "role-handlers"
    assert file_kind("ansible/roles/infra/docker/defaults/main.yml") == "role-defaults"
    assert file_kind("ansible/roles/common/templates/x.service.j2") == "role-template"
    assert file_kind("ansible/templates/prometheus.yml.j2") == "template"
    assert file_kind("docker/stacks/core/docker-compose.yml") == "stack"
    assert file_kind("docker/stacks/.env.template") == "env-template"
    assert file_kind("scripts/bootstrap.sh") == "script"
    assert file_kind("ansible/ansible.cfg") == "outro"


def test_services_from_compose_list_and_dict_labels(make_repo):
    compose_list = (
        "services:\n  traefik:\n    image: traefik:v3.1\n    networks: [proxy]\n"
        "    labels:\n      - \"traefik.http.routers.t.rule=Host(`traefik.exemplo.com`)\"\n"
    )
    compose_dict = (
        "services:\n  app:\n    image: nginx:1.27\n    networks:\n      proxy: {}\n      interna: {}\n"
        "    labels:\n      traefik.http.routers.a.rule: \"Host(`a.exemplo.com`) || Host(`b.exemplo.com`)\"\n"
        "  db:\n    image: postgres:16\n"
    )
    cfg = repo(make_repo, **{
        "server/docker/stacks/core/docker-compose.yml": compose_list,
        "server/docker/stacks/apps/docker-compose.yml": compose_dict,
    })
    assert build_index(cfg)["services"] == [
        {"stack": "apps", "service": "app", "image": "nginx:1.27", "networks": ["interna", "proxy"],
         "traefik_hosts": ["a.exemplo.com", "b.exemplo.com"]},
        {"stack": "apps", "service": "db", "image": "postgres:16", "networks": [], "traefik_hosts": []},
        {"stack": "core", "service": "traefik", "image": "traefik:v3.1", "networks": ["proxy"],
         "traefik_hosts": ["traefik.exemplo.com"]},
    ]


def test_playbook_roles_str_and_dict(make_repo):
    playbook = (
        "- hosts: proxmox\n  roles:\n    - infra/proxmox-host-config\n"
        "- hosts: vms\n  vars:\n    segredo: !vault |\n      $ANSIBLE_VAULT;1.1;AES256\n      6162\n"
        "  roles:\n    - role: common\n    - { name: infra/docker }\n"
        "- import_playbook: outro.yml\n"
    )
    cfg = repo(make_repo, **{"server/ansible/playbooks/site.yml": playbook})
    assert build_index(cfg)["playbooks"] == [{
        "path": "ansible/playbooks/site.yml",
        "hosts": ["proxmox", "vms"],
        "roles": ["infra/proxmox-host-config", "common", "infra/docker"],
        "imports": ["outro.yml"],
    }]


def test_index_is_deterministic(make_repo):
    cfg = repo(make_repo)
    write_index(cfg, build_index(cfg))
    first = ((cfg.root / "INDEX.md").read_bytes(), (cfg.root / "index.json").read_bytes())
    write_index(cfg, build_index(cfg))
    assert ((cfg.root / "INDEX.md").read_bytes(), (cfg.root / "index.json").read_bytes()) == first
    assert first[1].endswith(b"\n") and b"\r" not in first[0]


def test_markdown_has_generated_header_and_sections(make_repo):
    md = render_markdown(build_index(repo(make_repo)))
    assert md.startswith("<!-- GERADO por tools/wikisync — não editar à mão -->\n")
    for section in ("## Páginas", "## Arquivos do server", "## Serviços", "## Playbooks e roles"):
        assert section in md
    assert "| `ansible/c.yml` |" in md and "⚠️ divergente" in md
