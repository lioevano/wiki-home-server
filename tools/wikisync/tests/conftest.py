from __future__ import annotations

from pathlib import Path

import pytest

DEFAULT_CONFIG = """\
wiki_dir: wiki
server_dir: server
server_roots: [ansible, docker, scripts]
ignore_paths:
  - "docker/stacks/novoservico/**"
ignore_orphans: {}
exclude_dirs: [.git, .venv, venv, wiki/venv, wiki/site, site, __pycache__, .pytest_cache]
"""

DEFAULT_MKDOCS = """\
site_name: Teste
nav:
  - 'Início': 'index.md'
"""


@pytest.fixture
def make_repo(tmp_path: Path):
    """Cria uma árvore de repositório em tmp_path a partir de {caminho: conteúdo}.

    Conteúdo str é gravado em UTF-8 sem conversão de quebras de linha;
    bytes são gravados como estão.
    """

    def _make(files: dict[str, str | bytes]) -> Path:
        files = dict(files)
        files.setdefault("tools/wikisync/config.yml", DEFAULT_CONFIG)
        files.setdefault("wiki/mkdocs.yml", DEFAULT_MKDOCS)
        for rel, content in files.items():
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_bytes(content.encode("utf-8"))
        return tmp_path

    return _make
