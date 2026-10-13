"""Verificações wiki <-> server (comando `check`)."""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from functools import lru_cache
from typing import Literal

from .config import Config, is_ignored
from .extract import (
    Block,
    extract_blocks,
    iter_fences,
    literal_path,
    load_mkdocs,
    nav_pages,
    normalize,
    page_meta,
    page_refs,
)

Severity = Literal["erro", "aviso"]
UNMARKED_RE = re.compile(r"^\s*(?:#|//|;|\{#)\s*((?:ansible|docker|scripts)/\S+)")
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".bundle", ".pdf", ".zip", ".gz"}
VAULT_HEADER = "$ANSIBLE_VAULT;"


@dataclass
class Finding:
    code: str
    severity: Severity
    path: str
    page: str | None
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Wiki:
    pages: dict[str, str] = field(default_factory=dict)
    blocks: list[Block] = field(default_factory=list)
    literals: dict[str, list[Block]] = field(default_factory=dict)
    refs: dict[str, set[str]] = field(default_factory=dict)


def _excluded(rel: str, cfg: Config) -> bool:
    parts = rel.split("/")
    for ex in cfg.exclude_dirs:
        if "/" in ex:
            if rel == ex or rel.startswith(ex + "/"):
                return True
        elif ex in parts:
            return True
    return False


@lru_cache(maxsize=8)
def _git_files(root: str) -> frozenset[str] | None:
    """Arquivos versionados ou não ignorados (git ls-files -co --exclude-standard); None sem git."""
    if not (Path(root) / ".git").exists():
        return None
    try:
        proc = subprocess.run(["git", "-C", root, "ls-files", "-co", "--exclude-standard", "-z"],
                              capture_output=True, check=False)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return frozenset(p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p)


def _walk(base: Path, cfg: Config, rel_to: Path) -> list[str]:
    out = []
    if not base.is_dir():
        return out
    tracked = _git_files(str(cfg.root))
    for dirpath, dirnames, filenames in os.walk(base):
        d = Path(dirpath)
        dirnames[:] = [n for n in dirnames if not _excluded((d / n).relative_to(cfg.root).as_posix(), cfg)]
        for name in filenames:
            p = d / name
            rel_root = p.relative_to(cfg.root).as_posix()
            if _excluded(rel_root, cfg) or (tracked is not None and rel_root not in tracked):
                continue
            out.append(p.relative_to(rel_to).as_posix())
    return sorted(out)


def server_files(cfg: Config) -> list[str]:
    return _walk(cfg.server_dir, cfg, cfg.server_dir)


def collect(cfg: Config) -> Wiki:
    wiki = Wiki()
    for rel in _walk(cfg.docs_dir, cfg, cfg.docs_dir):
        if not rel.endswith(".md"):
            continue
        text = (cfg.docs_dir / rel).read_text(encoding="utf-8-sig")
        wiki.pages[rel] = text
        blocks = extract_blocks(text, rel)
        wiki.blocks.extend(blocks)
        for b in blocks:
            path = literal_path(b, cfg)
            if path:
                wiki.literals.setdefault(path, []).append(b)
        wiki.refs[rel] = page_refs(text, cfg)
    return wiki


def is_covered(path: str, refs: set[str]) -> bool:
    if path in refs:
        return True
    return any(r.endswith("/") and r.count("/") >= 3 and path.startswith(r) for r in refs)


def _check_literals(cfg: Config, wiki: Wiki) -> list[Finding]:
    out = []
    for path, blocks in sorted(wiki.literals.items()):
        first = blocks[0]
        variants = {normalize(b.content) for b in blocks}
        if len(variants) > 1:
            pages = ", ".join(f"{b.page}:{b.line}" for b in blocks)
            out.append(Finding("LIT-DUP", "erro", path, first.page, f"blocos com conteúdos diferentes para o mesmo arquivo ({pages})"))
            continue
        target = cfg.server_dir / path
        if not target.is_file():
            out.append(Finding("LIT-MISSING", "erro", path, first.page, f"bloco literal (linha {first.line}) sem arquivo no server"))
        elif normalize(target.read_text(encoding="utf-8", errors="replace")) != normalize(first.content):
            out.append(Finding("LIT-DIFF", "erro", path, first.page, f"conteúdo difere do bloco literal (linha {first.line}); veja: dev.py sync --path {path}"))
    return out


def _check_refs(cfg: Config, wiki: Wiki) -> list[Finding]:
    out = []
    seen = set()
    for page, refs in sorted(wiki.refs.items()):
        for ref in sorted(refs):
            if ref in seen or ref.rstrip("/") in wiki.literals:
                continue
            target = cfg.server_dir / ref
            ok = target.is_dir() if ref.endswith("/") else target.exists()
            if not ok:
                seen.add(ref)
                if ref in cfg.pending_files:
                    out.append(Finding("REF-PENDING", "aviso", ref, page, f"ainda não criado: {cfg.pending_files[ref]}"))
                else:
                    out.append(Finding("REF-MISSING", "erro", ref, page, "caminho citado na wiki não existe no server"))
    return out


def _check_orphans(cfg: Config, wiki: Wiki) -> list[Finding]:
    refs = set().union(*wiki.refs.values()) if wiki.refs else set()
    refs |= set(wiki.literals)
    out = []
    for path in server_files(cfg):
        if path in cfg.ignore_orphans or is_ignored(path, cfg) or is_covered(path, refs):
            continue
        out.append(Finding("ORPHAN", "aviso", path, None, "arquivo do server não citado por nenhuma página"))
    return out


def _check_unmarked(cfg: Config, wiki: Wiki) -> list[Finding]:
    out = []
    for b in wiki.blocks:
        if b.title:
            continue
        first = next((l for l in b.content.split("\n") if l.strip()), "")
        m = UNMARKED_RE.match(first)
        if m:
            out.append(Finding("UNMARKED", "aviso", m.group(1), b.page, f"bloco (linha {b.line}) com comentário de caminho mas sem title="))
    return out


def _check_desc(cfg: Config, wiki: Wiki) -> list[Finding]:
    return [
        Finding("DESC", "aviso", page, page, "página sem description: no front-matter")
        for page, text in sorted(wiki.pages.items())
        if page_meta(text)[1] is None
    ]


def _without_fences(text: str) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    drop = set()
    for start, _, _, body in iter_fences(lines):
        drop.update(range(start - 1, start + len(body) + 1))
    return "\n".join(l for i, l in enumerate(lines) if i not in drop)


def _check_links(cfg: Config, wiki: Wiki) -> list[Finding]:
    out = []
    for page, text in sorted(wiki.pages.items()):
        for target in LINK_RE.findall(_without_fences(text)):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            clean = target.split("#", 1)[0]
            if not clean:
                continue
            if not ((cfg.docs_dir / page).parent / clean).exists():
                out.append(Finding("LINK", "erro", clean, page, f"link relativo quebrado: {target}"))
    return out


def _check_nav(cfg: Config, wiki: Wiki) -> list[Finding]:
    if not cfg.mkdocs_file.is_file():
        return [Finding("NAV", "erro", "mkdocs.yml", None, "mkdocs.yml não encontrado")]
    nav = nav_pages(load_mkdocs(cfg.mkdocs_file).get("nav"))
    out = [Finding("NAV", "erro", p, None, "entrada do nav sem arquivo") for p in nav if p not in wiki.pages]
    out += [Finding("NAV", "erro", p, p, "página fora do nav") for p in sorted(wiki.pages) if p not in nav]
    return out


def _check_vault(cfg: Config, wiki: Wiki) -> list[Finding]:
    out = []
    for rel in _walk(cfg.server_dir, cfg, cfg.root):
        if rel.rsplit("/", 1)[-1] != "vault.yml":
            continue
        head = (cfg.root / rel).read_text(encoding="utf-8", errors="replace").lstrip("﻿")
        if not head.startswith(VAULT_HEADER):
            out.append(Finding("VAULT", "erro", rel, None, "vault.yml não está criptografado (rode ansible-vault encrypt)"))
    return out


def _check_eol(cfg: Config, wiki: Wiki) -> list[Finding]:
    out = []
    for rel in _walk(cfg.root, cfg, cfg.root):
        suffix = Path(rel).suffix.lower()
        if suffix in BINARY_SUFFIXES or suffix == ".ps1":
            continue
        data = (cfg.root / rel).read_bytes()
        if b"\0" in data[:8192]:
            continue
        if b"\r\n" in data:
            out.append(Finding("EOL", "erro", rel, None, "arquivo com quebras de linha CRLF (use LF)"))
    return out


CHECKS = [
    _check_literals,
    _check_refs,
    _check_orphans,
    _check_unmarked,
    _check_desc,
    _check_links,
    _check_nav,
    _check_vault,
    _check_eol,
]


def run_check(cfg: Config, wiki: Wiki | None = None) -> list[Finding]:
    wiki = wiki or collect(cfg)
    findings = [f for check in CHECKS for f in check(cfg, wiki)]
    return sorted(findings, key=lambda f: (f.severity != "erro", f.code, f.path))
