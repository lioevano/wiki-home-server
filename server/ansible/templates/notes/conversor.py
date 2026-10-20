"""Converte os documentos do Nextcloud para Markdown, de forma incremental (segundo cérebro, página 12).

Uso: conversor.py --origem DIR --destino DIR --extensoes pdf,docx,... --max-mb N
Cada <origem>/<rel> vira <destino>/<rel>.md, com o caminho original no cabeçalho. O manifesto
<destino>/.manifesto.json guarda tamanho e data de cada arquivo convertido; o que sumiu da origem sai do destino.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

MANIFESTO = ".manifesto.json"


@dataclass
class Resumo:
    convertidos: int = 0
    mantidos: int = 0
    removidos: int = 0
    falhas: list[str] = field(default_factory=list)


class OrigemVazia(Exception):
    """A origem não existe ou não tem arquivos, mas o manifesto tem: provável montagem ausente."""


def _arquivos(origem: Path) -> list[Path]:
    """Arquivos regulares da origem, sem ocultos e sem seguir links simbólicos."""
    achados = []
    for raiz, pastas, nomes in os.walk(origem, followlinks=False):
        pastas[:] = [p for p in pastas if not p.startswith(".")]
        for nome in nomes:
            p = Path(raiz) / nome
            if not nome.startswith(".") and not p.is_symlink() and p.is_file():
                achados.append(p)
    return achados


def _gravar(caminho: Path, texto: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, caminho)


def _podar(pasta: Path, destino: Path) -> None:
    while pasta != destino and pasta.is_dir() and not any(pasta.iterdir()):
        pasta.rmdir()
        pasta = pasta.parent


def sincronizar(origem: Path, destino: Path, extensoes: set[str], max_bytes: int,
                converter: Callable[[Path], str]) -> Resumo:
    arq_manifesto = destino / MANIFESTO
    manifesto = json.loads(arq_manifesto.read_text(encoding="utf-8")) if arq_manifesto.exists() else {}
    arquivos = _arquivos(origem) if origem.is_dir() else []
    if not arquivos and manifesto:
        raise OrigemVazia(f"{origem} vazia ou ausente; nada foi apagado")

    resumo = Resumo()
    vistos = set()
    for p in sorted(arquivos):
        if p.suffix.lower().lstrip(".") not in extensoes:
            continue
        st = p.stat()
        if st.st_size > max_bytes:
            print(f"grande demais, ignorado: {p}", file=sys.stderr)
            continue
        rel = p.relative_to(origem).as_posix()
        vistos.add(rel)
        assinatura = [st.st_size, st.st_mtime_ns]
        saida = destino / (rel + ".md")
        if manifesto.get(rel) == assinatura and saida.exists():
            resumo.mantidos += 1
            continue
        try:
            texto = converter(p)
        except Exception as erro:  # um documento ruim não para os outros
            print(f"falha ao converter {rel}: {erro}", file=sys.stderr)
            resumo.falhas.append(rel)
            manifesto.pop(rel, None)
            continue
        _gravar(saida, f'---\norigem: "Nextcloud/{rel}"\n---\n\n{texto}')
        manifesto[rel] = assinatura
        resumo.convertidos += 1

    for rel in sorted(set(manifesto) - vistos):
        saida = destino / (rel + ".md")
        if saida.exists():
            saida.unlink()
        _podar(saida.parent, destino)
        del manifesto[rel]
        resumo.removidos += 1

    _gravar(arq_manifesto, json.dumps(manifesto, ensure_ascii=False, indent=1, sort_keys=True))
    return resumo


def _converter_real(p: Path) -> str:
    if p.suffix.lower() in (".md", ".txt"):
        return p.read_text(encoding="utf-8", errors="replace")
    from markitdown import MarkItDown  # importado aqui: os testes não precisam do markitdown
    return MarkItDown().convert(str(p)).text_content


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--origem", required=True, type=Path)
    ap.add_argument("--destino", required=True, type=Path)
    ap.add_argument("--extensoes", required=True)
    ap.add_argument("--max-mb", type=int, default=50)
    a = ap.parse_args(argv)
    extensoes = {e.strip().lower().lstrip(".") for e in a.extensoes.split(",") if e.strip()}
    try:
        r = sincronizar(a.origem, a.destino, extensoes, a.max_mb * 1024 * 1024, _converter_real)
    except OrigemVazia as erro:
        print(f"abortado: {erro}", file=sys.stderr)
        return 2
    print(f"convertidos={r.convertidos} mantidos={r.mantidos} removidos={r.removidos} falhas={len(r.falhas)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
