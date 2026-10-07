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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wikisync", description="Sincronização wiki (fonte da verdade) -> server.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="raiz do repositório")
    sub = parser.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser("check", help="verifica divergências entre wiki e server")
    p_check.add_argument("--json", action="store_true", help="saída em JSON")
    p_check.set_defaults(func=_cmd_check)
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
