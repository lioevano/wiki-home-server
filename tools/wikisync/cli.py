"""Interface de linha de comando: python -m wikisync [--root R] <check|apply|index>."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import ConfigError, load_config

DEFAULT_ROOT = Path(__file__).resolve().parents[2]


def _cmd_check(cfg, args) -> int:
    from .check import run_check

    findings = run_check(cfg)
    errors = sum(f.severity == "erro" for f in findings)
    warnings = len(findings) - errors
    if args.json:
        print(json.dumps([f.to_dict() for f in findings], ensure_ascii=False, indent=2))
    else:
        for f in findings:
            page = f" ({f.page})" if f.page and f.page != f.path else ""
            print(f"{f.severity.upper():5}  {f.code:11}  {f.path}{page}  {f.message}")
        print(f"{errors} erro(s), {warnings} aviso(s)")
    return 1 if errors else 0


def _cmd_apply(cfg, args) -> int:
    from .apply import ApplyError, plan_apply, write_changes

    try:
        changes = plan_apply(cfg, only=args.path)
    except ApplyError as exc:
        print(f"wikisync: {exc}", file=sys.stderr)
        return 1
    if args.path and not changes and args.path not in _literal_paths(cfg):
        print(f"wikisync: nenhum bloco literal para {args.path}", file=sys.stderr)
        return 1
    if not changes:
        print("nada a aplicar: server já reflete os blocos literais da wiki")
        return 0
    for change in changes:
        action = "criar" if change.old is None else "atualizar"
        print(f"== {action}: server/{change.path}")
        print(change.diff())
    if args.yes:
        write_changes(cfg, changes)
        print(f"{len(changes)} arquivo(s) gravado(s)")
    else:
        print(f"{len(changes)} arquivo(s) a alterar — dry-run: use --yes para gravar")
    return 0


def _cmd_index(cfg, args) -> int:
    from .index import build_index, write_index

    idx = build_index(cfg)
    write_index(cfg, idx)
    print(f"INDEX.md e index.json gerados: {len(idx['pages'])} páginas, {len(idx['server_files'])} arquivos, "
          f"{len(idx['services'])} serviços, {len(idx['playbooks'])} playbooks")
    return 0


def _literal_paths(cfg) -> set[str]:
    from .check import collect

    return set(collect(cfg).literals)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wikisync", description="Sincronização wiki (fonte da verdade) -> server.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="raiz do repositório")
    sub = parser.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser("check", help="verifica divergências entre wiki e server")
    p_check.add_argument("--json", action="store_true", help="saída em JSON")
    p_check.set_defaults(func=_cmd_check)
    p_apply = sub.add_parser("apply", help="copia blocos literais da wiki para o server (dry-run por padrão)")
    p_apply.add_argument("--yes", action="store_true", help="grava as alterações")
    p_apply.add_argument("--path", help="restringe a um caminho (relativo a server/)")
    p_apply.set_defaults(func=_cmd_apply)
    p_index = sub.add_parser("index", help="gera INDEX.md e index.json na raiz")
    p_index.set_defaults(func=_cmd_index)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        cfg = load_config(args.root)
    except ConfigError as exc:
        print(f"wikisync: {exc}", file=sys.stderr)
        return 2
    return args.func(cfg, args)
