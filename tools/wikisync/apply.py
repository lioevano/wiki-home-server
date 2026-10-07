"""Aplica blocos literais da wiki no server (comando `apply`)."""
from __future__ import annotations

import difflib
from dataclasses import dataclass

from .check import Wiki, collect
from .config import Config
from .extract import normalize


class ApplyError(Exception):
    """Aplicação recusada (ex.: blocos duplicados divergentes)."""


@dataclass
class Change:
    path: str
    old: str | None
    new: str

    def diff(self) -> str:
        old = [] if self.old is None else normalize(self.old).split("\n")
        new = self.new.split("\n")
        return "\n".join(difflib.unified_diff(
            old, new, fromfile=f"server/{self.path}" if self.old is not None else "/dev/null",
            tofile="wiki", lineterm="",
        ))


def plan_apply(cfg: Config, only: str | None = None, wiki: Wiki | None = None) -> list[Change]:
    wiki = wiki or collect(cfg)
    literals = {p: b for p, b in wiki.literals.items() if only is None or p == only}
    dups = sorted(p for p, blocks in literals.items() if len({normalize(b.content) for b in blocks}) > 1)
    if dups:
        raise ApplyError("blocos literais divergentes para: " + ", ".join(dups) + " (resolva o LIT-DUP na wiki)")
    server_root = cfg.server_dir.resolve()
    invalid = []
    for path in sorted(literals):
        target = cfg.server_dir / path
        if target.is_dir() or not target.resolve().is_relative_to(server_root):
            invalid.append(path)
    if invalid:
        raise ApplyError("destino inválido (diretório ou fora de server/): " + ", ".join(invalid))
    changes = []
    for path, blocks in sorted(literals.items()):
        new = normalize(blocks[0].content)
        target = cfg.server_dir / path
        old = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else None
        if old is None or normalize(old) != new:
            changes.append(Change(path, old, new))
    return changes


def write_changes(cfg: Config, changes: list[Change]) -> None:
    for change in changes:
        target = cfg.server_dir / change.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((change.new + "\n").encode("utf-8"))
