"""Carrega tools/wikisync/config.yml."""
from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path

import yaml

CONFIG_REL = Path("tools/wikisync/config.yml")


class ConfigError(Exception):
    """Configuração ausente ou inválida."""


@dataclass
class Config:
    root: Path
    wiki_dir: Path
    docs_dir: Path
    mkdocs_file: Path
    server_dir: Path
    server_roots: list[str]
    ignore_paths: list[str] = field(default_factory=list)
    ignore_orphans: dict[str, str] = field(default_factory=dict)
    pending_files: dict[str, str] = field(default_factory=dict)
    exclude_dirs: list[str] = field(default_factory=list)


def load_config(root: Path) -> Config:
    root = Path(root).resolve()
    path = root / CONFIG_REL
    if not path.is_file():
        raise ConfigError(f"arquivo de configuração não encontrado: {path} (esperado em {CONFIG_REL.as_posix()})")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"config.yml inválido: {exc}") from exc
    wiki_dir = root / data.get("wiki_dir", "wiki")
    mkdocs_file = wiki_dir / "mkdocs.yml"
    docs_name = "docs"
    if mkdocs_file.is_file():
        from .extract import load_mkdocs  # import tardio evita ciclo

        docs_name = load_mkdocs(mkdocs_file).get("docs_dir") or "docs"
    return Config(
        root=root,
        wiki_dir=wiki_dir,
        docs_dir=wiki_dir / docs_name,
        mkdocs_file=mkdocs_file,
        server_dir=root / data.get("server_dir", "server"),
        server_roots=list(data.get("server_roots") or ["ansible", "docker", "scripts"]),
        ignore_paths=list(data.get("ignore_paths") or []),
        ignore_orphans=dict(data.get("ignore_orphans") or {}),
        pending_files=dict(data.get("pending_files") or {}),
        exclude_dirs=list(data.get("exclude_dirs") or []),
    )


def is_ignored(path: str, cfg: Config) -> bool:
    """Placeholder didático? (contém '...' ou casa com ignore_paths)."""
    if "..." in path:
        return True
    candidates = {path, path.rstrip("/"), path.rstrip("/") + "/"}
    return any(fnmatchcase(c, pat) for c in candidates for pat in cfg.ignore_paths)
