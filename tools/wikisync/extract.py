"""Extração de blocos de código, referências e metadados das páginas da wiki."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import Config, is_ignored

FENCE_OPEN = re.compile(r"^([ \t]*)(`{3,}|~{3,})(.*)$")
TITLE_RE = re.compile(r"""title=(["'])(.*?)\1""")
REF_RE = re.compile(r"(?<![\w.\-/])(?:server/)?((?:ansible|docker|scripts)/[\w.\-/]*)")
REF_TRAILING = ".,:;)"
PLACEHOLDER_NEXT = "*{<$"


@dataclass
class Block:
    page: str
    line: int
    lang: str
    title: str | None
    content: str


def normalize(text: str) -> str:
    """Remove BOM, converte CRLF em LF e remove quebras de linha finais."""
    return text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")


def _parse_info(info: str) -> tuple[str, str | None]:
    info = info.strip()
    m = TITLE_RE.search(info)
    title = m.group(2) if m else None
    lang = ""
    if info.startswith("{"):
        for token in info.strip("{} ").split():
            if token.startswith("."):
                lang = token[1:]
                break
    elif info:
        first = info.split()[0]
        if "=" not in first:
            lang = first
    return lang, title


def _dedent(line: str, indent: str) -> str:
    n = 0
    while n < len(indent) and n < len(line) and line[n] in " \t":
        n += 1
    return line[n:]


def iter_fences(lines: list[str]):
    """Gera (linha_inicial_1based, indent, info, linhas_do_corpo) para cada bloco cercado."""
    i = 0
    while i < len(lines):
        m = FENCE_OPEN.match(lines[i])
        if not m:
            i += 1
            continue
        indent, fence, info = m.groups()
        char, size = fence[0], len(fence)
        if char == "`" and "`" in info:
            i += 1
            continue
        close = re.compile(r"^[ \t]*" + re.escape(char) + "{" + str(size) + r",}[ \t]*$")
        body: list[str] = []
        j = i + 1
        while j < len(lines):
            line = lines[j]
            lead = len(line) - len(line.lstrip(" \t"))
            if close.match(line) and lead <= len(indent):
                break
            body.append(line)
            j += 1
        yield i + 1, indent, info, body
        i = j + 1


def extract_blocks(text: str, page: str) -> list[Block]:
    lines = text.lstrip("﻿").replace("\r\n", "\n").split("\n")
    blocks = []
    for line_no, indent, info, body in iter_fences(lines):
        lang, title = _parse_info(info)
        content = "\n".join(_dedent(l, indent) for l in body)
        blocks.append(Block(page=page, line=line_no, lang=lang, title=title, content=content.rstrip("\n")))
    return blocks


def literal_path(block: Block, cfg: Config) -> str | None:
    """Caminho (relativo a server/) se o bloco é verdade literal, senão None."""
    if not block.title:
        return None
    title = block.title.strip()
    if " " in title or "\\" in title or title.split("/", 1)[0] not in cfg.server_roots or "/" not in title:
        return None
    if any(seg in ("", ".", "..") for seg in title.split("/")):
        return None  # nunca aceitar caminhos que saiam de server/ ou ambíguos
    if is_ignored(title, cfg):
        return None
    return title


def page_refs(text: str, cfg: Config) -> set[str]:
    """Caminhos sob server_roots citados no texto (inline, prosa ou blocos)."""
    refs: set[str] = set()
    for m in REF_RE.finditer(text):
        nxt = text[m.end(): m.end() + 1]
        if nxt and nxt in PLACEHOLDER_NEXT:
            continue
        ref = m.group(1)
        while ref and ref[-1] in REF_TRAILING:
            ref = ref[:-1]
        if ref.split("/", 1)[0] not in cfg.server_roots or ref.count("/") == 0:
            continue
        if ref.endswith("/."):
            ref = ref[:-1]
        if is_ignored(ref, cfg):
            continue
        refs.add(ref)
    return refs


def page_meta(text: str) -> tuple[str | None, str | None]:
    """(título H1, description do front-matter)."""
    text = text.lstrip("﻿").replace("\r\n", "\n")
    description = None
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            try:
                meta = yaml.safe_load(text[4:end]) or {}
            except yaml.YAMLError:
                meta = {}
            if isinstance(meta, dict) and meta.get("description"):
                description = str(meta["description"]).strip()
            body = text[end + 4:]
    lines = body.split("\n")
    fence_lines = set()
    for start, _, _, fence_body in iter_fences(lines):
        fence_lines.update(range(start - 1, start + len(fence_body) + 1))
    for idx, line in enumerate(lines):
        if idx in fence_lines:
            continue
        if line.startswith("# "):
            return line[2:].strip(), description
    return None, description


class _TolerantLoader(yaml.SafeLoader):
    pass


_TolerantLoader.add_multi_constructor("tag:yaml.org,2002:python/", lambda loader, suffix, node: None)


def load_mkdocs(path: Path) -> dict:
    return yaml.load(Path(path).read_text(encoding="utf-8"), Loader=_TolerantLoader) or {}


def nav_pages(nav) -> list[str]:
    """Arquivos .md do nav, em ordem, ignorando URLs externas."""
    out: list[str] = []

    def walk(item):
        if isinstance(item, str):
            if item.endswith(".md") and "://" not in item:
                out.append(item)
        elif isinstance(item, dict):
            for value in item.values():
                walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)

    walk(nav or [])
    return out
