from __future__ import annotations

from wikisync.config import load_config
from wikisync.extract import (
    extract_blocks,
    literal_path,
    load_mkdocs,
    nav_pages,
    normalize,
    page_meta,
    page_refs,
)


def test_extracts_titled_block():
    text = '```yaml title="ansible/a.yml"\nx: 1\n```\n'
    blocks = extract_blocks(text, "p.md")
    assert len(blocks) == 1
    b = blocks[0]
    assert b.title == "ansible/a.yml"
    assert b.content == "x: 1"
    assert b.lang == "yaml"
    assert b.line == 1
    assert b.page == "p.md"


def test_dedents_block_inside_admonition():
    text = '!!! note\n    Texto\n\n    ```yaml title="ansible/a.yml"\n    x: 1\n      y: 2\n    ```\n'
    (b,) = extract_blocks(text, "p.md")
    assert b.content == "x: 1\n  y: 2"
    assert b.line == 4


def test_nested_fence_closes_only_on_matching_length():
    text = "````markdown\n```yaml\nx: 1\n```\n````\n\n```bash\nls\n```\n"
    blocks = extract_blocks(text, "p.md")
    assert [b.lang for b in blocks] == ["markdown", "bash"]
    assert blocks[0].content == "```yaml\nx: 1\n```"


def test_tilde_fence_and_untitled_block():
    (b,) = extract_blocks("~~~bash\nls\n~~~\n", "p.md")
    assert b.title is None
    assert b.lang == "bash"


def test_title_variants():
    a, b = extract_blocks(
        "```yaml title='ansible/a.yml'\nx: 1\n```\n\n"
        '``` { .yaml title="ansible/a.yml" linenums="1" }\nx: 1\n```\n',
        "p.md",
    )
    assert a.title == b.title == "ansible/a.yml"
    assert b.lang == "yaml"


def test_literal_path_rules(make_repo):
    cfg = load_config(make_repo({}))
    blocks = extract_blocks(
        '```yaml title="Exemplo: docker/x.yml"\na\n```\n'
        '```text title="/etc/fstab"\na\n```\n'
        '```yaml title="docker/stacks/core/docker-compose.yml"\na\n```\n'
        '```yaml title="docker/stacks/novoservico/docker-compose.yml"\na\n```\n'
        "```yaml\na\n```\n",
        "p.md",
    )
    assert [literal_path(b, cfg) for b in blocks] == [
        None,
        None,
        "docker/stacks/core/docker-compose.yml",
        None,
        None,
    ]


def test_page_refs(make_repo):
    cfg = load_config(make_repo({}))
    text = (
        "Veja `ansible/playbooks/a.yml`, e também docker/stacks/core/. "
        "Ignorar docker/stacks/.../ e docker/stacks/novoservico/docker-compose.yml "
        "e playbooks/relativo.yml."
    )
    assert page_refs(text, cfg) == {"ansible/playbooks/a.yml", "docker/stacks/core/"}


def test_page_meta():
    assert page_meta("---\ndescription: D\n---\n# T\n\ncorpo\n") == ("T", "D")
    assert page_meta("# T\n") == ("T", None)
    assert page_meta("sem titulo\n") == (None, None)


def test_load_mkdocs_tolerates_python_tags(tmp_path):
    p = tmp_path / "mkdocs.yml"
    p.write_text(
        "markdown_extensions:\n"
        "  - pymdownx.superfences:\n"
        "      custom_fences:\n"
        "        - name: mermaid\n"
        "          format: !!python/name:pymdownx.superfences.fence_code_format\n"
        "nav:\n  - 'A': 'a.md'\n",
        encoding="utf-8",
    )
    assert load_mkdocs(p)["nav"] == [{"A": "a.md"}]


def test_nav_pages_nested_and_external():
    nav = [
        {"Início": "index.md"},
        {"Seção": [{"Sub": [{"X": "s/x.md"}]}, {"Y": "s/y.md"}]},
        {"GitHub": "https://github.com/x"},
        "solto.md",
    ]
    assert nav_pages(nav) == ["index.md", "s/x.md", "s/y.md", "solto.md"]


def test_normalize_strips_bom_and_crlf():
    assert normalize("﻿a\r\nb\r\n\n") == "a\nb"


def test_literal_path_rejects_traversal_and_odd_segments(make_repo):
    cfg = load_config(make_repo({}))
    titles = ["ansible/../../escaped.txt", "ansible/./a.yml", "ansible//a.yml", "ansible\\a.yml", "ansible/a/.."]
    blocks = extract_blocks("".join(f'```yaml title="{t}"\na\n```\n' for t in titles), "p.md")
    assert [literal_path(b, cfg) for b in blocks] == [None] * len(titles)
