from __future__ import annotations

from wikisync.check import run_check
from wikisync.config import load_config

INDEX = (
    "---\ndescription: Página inicial\n---\n# Início\n\n"
    "Arquivo `ansible/a.yml`.\n\n"
    '```yaml title="ansible/a.yml"\nx: 1\n```\n'
)
MKDOCS_AB = "site_name: T\nnav:\n  - 'Início': 'index.md'\n  - 'B': 'b.md'\n"
VAULT = "server/ansible/inventories/home/group_vars/all/vault.yml"


def base(**extra):
    files = {"wiki/docs/index.md": INDEX, "server/ansible/a.yml": "x: 1\n"}
    files.update(extra)
    return files


def found(make_repo, files):
    cfg = load_config(make_repo(files))
    return {(f.code, f.severity, f.path) for f in run_check(cfg)}


def test_clean_repo_has_no_findings(make_repo):
    assert found(make_repo, base()) == set()


def test_lit_diff(make_repo):
    assert found(make_repo, base(**{"server/ansible/a.yml": "x: 2\n"})) == {("LIT-DIFF", "erro", "ansible/a.yml")}


def test_lit_missing_is_not_also_ref_missing(make_repo):
    files = base()
    del files["server/ansible/a.yml"]
    files["server/ansible/outro.yml"] = "y: 1\n"
    files["wiki/docs/index.md"] = INDEX + "\nE `ansible/outro.yml`.\n"
    assert found(make_repo, files) == {("LIT-MISSING", "erro", "ansible/a.yml")}


def test_lit_dup(make_repo):
    files = base(**{
        "wiki/mkdocs.yml": MKDOCS_AB,
        "wiki/docs/b.md": '---\ndescription: B\n---\n# B\n\n```yaml title="ansible/a.yml"\nx: 2\n```\n',
    })
    assert ("LIT-DUP", "erro", "ansible/a.yml") in found(make_repo, files)


def test_bom_and_crlf_only_difference_is_not_lit_diff(make_repo):
    result = found(make_repo, base(**{"server/ansible/a.yml": b"\xef\xbb\xbfx: 1\r\n"}))
    assert result == {("EOL", "erro", "server/ansible/a.yml")}


def test_crlf_allowed_in_ps1(make_repo):
    files = base(**{"server/scripts/x.ps1": b"Write-Host 1\r\n"})
    files["wiki/docs/index.md"] = INDEX + "\nScript `scripts/x.ps1`.\n"
    assert found(make_repo, files) == set()


def test_ref_missing(make_repo):
    files = base()
    files["wiki/docs/index.md"] = INDEX + "\nVeja `docker/stacks/x/` e `ansible/nao-existe.yml`.\n"
    assert found(make_repo, files) == {
        ("REF-MISSING", "erro", "docker/stacks/x/"),
        ("REF-MISSING", "erro", "ansible/nao-existe.yml"),
    }


def test_pending_file_is_warning_until_created(make_repo):
    config = (
        "server_roots: [ansible, docker, scripts]\n"
        "pending_files:\n  ansible/vault.yml: criado só após consolidar o template\n"
        "exclude_dirs: [.git]\n"
    )
    files = base(**{"tools/wikisync/config.yml": config})
    files["wiki/docs/index.md"] = INDEX + "\nCrie `ansible/vault.yml`.\n"
    assert found(make_repo, files) == {("REF-PENDING", "aviso", "ansible/vault.yml")}


def test_orphan_warning(make_repo):
    assert found(make_repo, base(**{"server/ansible/b.yml": "b: 1\n"})) == {("ORPHAN", "aviso", "ansible/b.yml")}


def test_orphan_covered_by_deep_dir_ref(make_repo):
    files = base(**{"server/docker/stacks/core/docker-compose.yml": "services: {}\n"})
    files["wiki/docs/index.md"] = INDEX + "\nStack em `docker/stacks/core/`.\n"
    assert found(make_repo, files) == set()


def test_orphan_not_covered_by_shallow_dir_ref(make_repo):
    files = base(**{"server/ansible/playbooks/p.yml": "- hosts: all\n"})
    files["wiki/docs/index.md"] = INDEX + "\nPlaybooks em `ansible/playbooks/`.\n"
    assert found(make_repo, files) == {("ORPHAN", "aviso", "ansible/playbooks/p.yml")}


def test_ignore_orphans(make_repo):
    config = (
        "server_roots: [ansible, docker, scripts]\n"
        "ignore_orphans:\n  ansible/b.yml: gerado em tempo de execução\n"
        "exclude_dirs: [.git]\n"
    )
    files = base(**{"server/ansible/b.yml": "b: 1\n", "tools/wikisync/config.yml": config})
    assert found(make_repo, files) == set()


def test_unmarked_warning(make_repo):
    files = base()
    files["wiki/docs/index.md"] = INDEX + "\n```yaml\n# ansible/a.yml\nx: 1\n```\n"
    assert found(make_repo, files) == {("UNMARKED", "aviso", "ansible/a.yml")}


def test_desc_warning(make_repo):
    files = base()
    files["wiki/docs/index.md"] = INDEX.replace("---\ndescription: Página inicial\n---\n", "")
    assert found(make_repo, files) == {("DESC", "aviso", "index.md")}


def test_link_broken(make_repo):
    files = base()
    files["wiki/docs/index.md"] = INDEX + (
        "\n[x](outra.md) ![i](img.png) [h](https://a.b/c) [a](#sec) [m](mailto:a@b.c) "
        "[ok](index.md#sec)\n\n```markdown\n[em-bloco](nao-conta.md)\n```\n"
    )
    assert found(make_repo, files) == {("LINK", "erro", "outra.md"), ("LINK", "erro", "img.png")}


def test_nav_page_missing_from_nav(make_repo):
    files = base(**{"wiki/docs/solta.md": "---\ndescription: S\n---\n# Solta\n"})
    assert found(make_repo, files) == {("NAV", "erro", "solta.md")}


def test_nav_entry_without_file(make_repo):
    files = base(**{"wiki/mkdocs.yml": "site_name: T\nnav:\n  - 'I': 'index.md'\n  - 'F': 'falta.md'\n  - 'GH': 'https://x.y'\n"})
    assert found(make_repo, files) == {("NAV", "erro", "falta.md")}


def _with_vault(content: str, name: str = "vault.yml"):
    files = base(**{f"server/ansible/inventories/home/group_vars/all/{name}": content})
    files["wiki/docs/index.md"] = INDEX + f"\nSegredos em `ansible/inventories/home/group_vars/all/{name}`.\n"
    return files


def test_vault_plaintext_is_error(make_repo):
    assert found(make_repo, _with_vault("vault_senha: x\n")) == {("VAULT", "erro", VAULT)}


def test_vault_encrypted_ok(make_repo):
    assert found(make_repo, _with_vault("$ANSIBLE_VAULT;1.1;AES256\n6162\n")) == set()


def test_vault_example_not_checked(make_repo):
    assert found(make_repo, _with_vault("vault_senha: TROCAR\n", "vault.yml.example")) == set()


def test_orphan_respects_ignore_paths(make_repo):
    assert found(make_repo, base(**{"server/docker/stacks/novoservico/docker-compose.yml": "services: {}\n"})) == set()


def test_gitignored_files_are_not_scanned(make_repo):
    import shutil
    import subprocess

    import pytest

    if not shutil.which("git"):
        pytest.skip("git ausente")
    root = make_repo(base(**{
        ".gitignore": ".env\n.vscode/\n",
        "server/docker/stacks/apps/.env": b"SEGREDO=1\r\n",
        ".vscode/settings.json": b"{}\r\n",
    }))
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    assert {(f.code, f.path) for f in run_check(load_config(root))} == set()
