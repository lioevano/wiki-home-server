"""Gera INDEX.md e index.json (comando `index`)."""
from __future__ import annotations

import json
import re

import yaml

from .check import collect, is_covered, run_check, server_files
from .config import Config
from .extract import page_meta

HEADER = "<!-- GERADO por tools/wikisync — não editar à mão -->\n"
HOST_RE = re.compile(r"Host\(`([^`]+)`\)")
LIT_ERRORS = {"LIT-DIFF", "LIT-MISSING", "LIT-DUP"}
STATE_LABEL = {"sincronizado": "✅ sincronizado", "divergente": "⚠️ divergente", None: "—"}


class _AnyTagLoader(yaml.SafeLoader):
    pass


_AnyTagLoader.add_multi_constructor("!", lambda loader, suffix, node: None)
_AnyTagLoader.add_multi_constructor("tag:yaml.org,2002:python/", lambda loader, suffix, node: None)


def _load_yaml(text: str):
    try:
        return yaml.load(text, Loader=_AnyTagLoader)
    except yaml.YAMLError:
        return None


def _unique(items):
    seen, out = set(), []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def file_kind(path: str) -> str:
    parts = path.split("/")
    if path.startswith("ansible/inventories/"):
        return "inventario"
    if path.startswith("ansible/playbooks/"):
        return "playbook"
    if path.startswith("ansible/roles/"):
        for folder, kind in (("tasks", "role-tasks"), ("handlers", "role-handlers"),
                             ("defaults", "role-defaults"), ("templates", "role-template")):
            if folder in parts[:-1]:
                return kind
        return "outro"
    if path.startswith("ansible/templates/"):
        return "template"
    if parts[-1] == "docker-compose.yml":
        return "stack"
    if parts[-1] == ".env.template":
        return "env-template"
    if path.startswith("scripts/"):
        return "script"
    return "outro"


def _services(cfg: Config, files: list[str]) -> list[dict]:
    out = []
    for path in files:
        parts = path.split("/")
        if not (path.startswith("docker/stacks/") and parts[-1] == "docker-compose.yml" and len(parts) == 4):
            continue
        data = _load_yaml((cfg.server_dir / path).read_text(encoding="utf-8"))
        services = (data or {}).get("services") or {}
        for name, svc in services.items():
            svc = svc or {}
            networks = svc.get("networks") or []
            networks = sorted(networks.keys() if isinstance(networks, dict) else networks)
            labels = svc.get("labels") or []
            values = labels.values() if isinstance(labels, dict) else labels
            hosts = sorted({h for v in values for h in HOST_RE.findall(str(v))})
            out.append({"stack": parts[2], "service": name, "image": svc.get("image"),
                        "networks": [str(n) for n in networks], "traefik_hosts": hosts})
    return sorted(out, key=lambda s: (s["stack"], s["service"]))


def _playbooks(cfg: Config, files: list[str]) -> list[dict]:
    out = []
    for path in files:
        if not (path.startswith("ansible/playbooks/") and path.endswith((".yml", ".yaml"))):
            continue
        plays = _load_yaml((cfg.server_dir / path).read_text(encoding="utf-8"))
        hosts, roles, imports = [], [], []
        for play in plays if isinstance(plays, list) else []:
            if not isinstance(play, dict):
                continue
            if play.get("import_playbook"):
                imports.append(str(play["import_playbook"]))
            if play.get("hosts"):
                hosts.append(str(play["hosts"]))
            for role in play.get("roles") or []:
                name = role if isinstance(role, str) else (role or {}).get("role") or (role or {}).get("name")
                if name:
                    roles.append(str(name))
        out.append({"path": path, "hosts": _unique(hosts), "roles": _unique(roles), "imports": _unique(imports)})
    return out


def build_index(cfg: Config) -> dict:
    wiki = collect(cfg)
    findings = run_check(cfg, wiki)
    diverged = {f.path for f in findings if f.code in LIT_ERRORS}
    pages = []
    for path, text in sorted(wiki.pages.items()):
        title, description = page_meta(text)
        literal = sorted({p for p, blocks in wiki.literals.items() if any(b.page == path for b in blocks)})
        pages.append({"path": path, "title": title, "description": description,
                      "literal": literal, "refs": sorted(wiki.refs.get(path, set()))})
    files = server_files(cfg)
    entries = []
    for path in files:
        citing = sorted(
            p for p in wiki.pages
            if is_covered(path, wiki.refs.get(p, set())) or any(b.page == p for b in wiki.literals.get(path, []))
        )
        state = None
        if path in wiki.literals:
            state = "divergente" if path in diverged else "sincronizado"
        entries.append({"path": path, "kind": file_kind(path), "pages": citing, "literal_state": state})
    return {"pages": pages, "server_files": entries,
            "services": _services(cfg, files), "playbooks": _playbooks(cfg, files)}


def _cell(value) -> str:
    if value is None or value == []:
        return "—"
    if isinstance(value, list):
        return ", ".join(f"`{v}`" for v in value)
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(idx: dict) -> str:
    lines = [HEADER.rstrip("\n"), "# Índice do repositório", "",
             "Mapa gerado por `python tools/dev.py index` a partir da wiki (fonte da verdade) e do `server/`.",
             "Caminhos de arquivos são relativos a `server/`; páginas, a `wiki/docs/`.", ""]
    lines += ["## Páginas", "", "| Página | Título | Descrição | Define (literal) | Cita |", "|---|---|---|---|---|"]
    for p in idx["pages"]:
        refs = [r for r in p["refs"] if r not in p["literal"]]
        lines.append(f"| `{p['path']}` | {_cell(p['title'])} | {_cell(p['description'])} | {_cell(p['literal'])} | {_cell(refs)} |")
    lines += ["", "## Arquivos do server", "", "| Arquivo | Tipo | Páginas | Literal |", "|---|---|---|---|"]
    for f in idx["server_files"]:
        lines.append(f"| `{f['path']}` | {f['kind']} | {_cell(f['pages'])} | {STATE_LABEL[f['literal_state']]} |")
    lines += ["", "## Serviços", "", "| Stack | Serviço | Imagem | Redes | Hosts (Traefik) |", "|---|---|---|---|---|"]
    for s in idx["services"]:
        lines.append(f"| {s['stack']} | {s['service']} | {_cell(s['image'])} | {_cell(s['networks'])} | {_cell(s['traefik_hosts'])} |")
    lines += ["", "## Playbooks e roles", "", "| Playbook | Hosts | Roles | Importa |", "|---|---|---|---|"]
    for p in idx["playbooks"]:
        lines.append(f"| `{p['path']}` | {_cell(p['hosts'])} | {_cell(p['roles'])} | {_cell(p['imports'])} |")
    return "\n".join(lines) + "\n"


def write_index(cfg: Config, idx: dict) -> None:
    (cfg.root / "INDEX.md").write_bytes(render_markdown(idx).encode("utf-8"))
    payload = json.dumps(idx, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (cfg.root / "index.json").write_bytes(payload.encode("utf-8"))
