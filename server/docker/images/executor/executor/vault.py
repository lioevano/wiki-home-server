"""Vault do Ansible editado pelo executor: lê o modelo, troca o valor de uma folha e grava cifrado em `saida/`."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from ansible.parsing.vault import VaultLib, VaultSecret

from .config import Config

# Mesma regra de linha do server/scripts/gerar_vault.py (que não está na imagem do executor).
LINHA = re.compile(r'^(?P<ind> *)(?P<chave>[A-Za-z_]\w*):(?P<resto>.*)$')
VAULT_NO_REPO = "server/ansible/inventories/home/group_vars/all/vault.yml"
BASE_AUSENTE = "ausente"   # o `.base` de um saida/vault.yml feito quando a main ainda não tinha vault


def _varrer(linhas: list[str]):
    """Gera (inicio, fim, indentacao, chave, caminho, resto, em_lista) de cada chave do YAML.

    `em_lista` marca chaves dentro de um item de lista (`- nome: x`): o caminho delas não tem índice e é ambíguo.

    `fim` é exclusivo e só passa de `inicio + 1` nos blocos `|`/`>`, que vão até a próxima linha
    não vazia menos indentada (o conteúdo do bloco nunca é lido como chave).
    """
    pilha: list[tuple[int, str]] = []
    lista_ind: int | None = None            # recuo do `-` do item de lista em que estamos
    i = 0
    while i < len(linhas):
        linha, inicio = linhas[i], i
        i += 1
        if linha.strip() and not linha.lstrip().startswith("#"):
            recuo = len(linha) - len(linha.lstrip())
            if linha.lstrip().startswith("- ") or linha.strip() == "-":
                lista_ind = recuo if lista_ind is None or recuo <= lista_ind else lista_ind
            elif lista_ind is not None and recuo <= lista_ind:
                lista_ind = None
        m = LINHA.match(linha)
        if not m:
            continue
        ind, chave, resto = len(m["ind"]), m["chave"], m["resto"].strip()
        while pilha and pilha[-1][0] >= ind:
            pilha.pop()
        pilha.append((ind, chave))
        if resto[:1] in ("|", ">"):
            while i < len(linhas) and (not linhas[i].strip() or len(linhas[i]) - len(linhas[i].lstrip()) > ind):
                i += 1
        yield inicio, i, ind, chave, ".".join(c for _, c in pilha), resto, lista_ind is not None and ind > lista_ind


def _folha(resto: str) -> bool:
    return bool(resto) and not resto.startswith("#")


def chaves_do_modelo(texto: str) -> set[str]:
    """Caminhos com ponto das folhas (chaves de mapa, que têm filhos, não contam)."""
    return {nome for _, _, _, _, nome, resto, em_lista in _varrer(texto.split("\n")) if _folha(resto) and not em_lista}


def _comentario(resto: str) -> str:
    """O ` # comentário` que segue o valor antigo (uma linha); aspas e `#` dentro do valor não contam."""
    if resto[:1] == '"':
        i = 1
        while i < len(resto) and resto[i] != '"':
            i += 2 if resto[i] == "\\" else 1
        resto = resto[i + 1:]
    elif resto[:1] == "'":
        i = 1
        while i < len(resto):
            if resto[i] == "'":
                if resto[i + 1:i + 2] != "'":
                    break
                i += 1
            i += 1
        resto = resto[i + 1:]
    else:
        m = re.search(r"\s#", resto)
        return resto[m.start():] if m else ""
    m = re.match(r"\s+#.*$", resto)
    return m.group(0) if m else ""


def _linhas_do_valor(ind: int, chave: str, valor: str, comentario: str) -> list[str]:
    cabeca = f"{' ' * ind}{chave}: "
    # Uma linha entre aspas duplas quando não há \n, há caracteres de controle (menos \n e \t), só quebras ou
    # mais de uma quebra no fim (`|+` engoliria a linha em branco que separa a próxima chave).
    if ("\n" not in valor or any(ord(c) < 32 and c not in "\n\t" for c in valor) or not valor.strip("\n")
            or valor.endswith("\n\n")):
        return [cabeca + json.dumps(valor, ensure_ascii=False) + comentario]
    corpo = valor.rstrip("\n")
    fins = len(valor) - len(corpo)                             # 0 ou 1
    indicador = "2" if corpo.startswith((" ", "\n")) else ""   # primeira linha recuada precisa do indicador
    linhas = [cabeca + "|" + indicador + ("" if fins else "-")]
    linhas += [f"{' ' * (ind + 2)}{l}" if l else "" for l in corpo.split("\n")]
    return linhas


def definir(texto: str, chave: str, valor: str) -> str:
    """Troca o valor de uma folha mantendo o resto do texto; `KeyError` se a chave não é uma folha."""
    linhas = texto.split("\n")
    for inicio, fim, ind, nome_chave, nome, resto, em_lista in _varrer(linhas):
        if nome != chave or not _folha(resto) or em_lista:
            continue
        comentario = "" if resto[:1] in ("|", ">") else _comentario(resto)
        sobra = []                                  # linhas em branco que fechavam o bloco antigo
        while fim - 1 > inicio and not linhas[fim - 1].strip():
            fim -= 1
            sobra.append(linhas[fim])
        return "\n".join(linhas[:inicio] + _linhas_do_valor(ind, nome_chave, valor, comentario)
                         + sobra + linhas[fim + len(sobra):])
    raise KeyError(chave)


class Vault:
    """O `saida/vault.yml` guarda as edições ainda não mescladas e o `saida/.base`, o sha256 do vault da `main` em
    que elas se basearam. Mesclado o PR (ou mudada a `main` por outro caminho), o `.base` deixa de bater e volta a
    valer o vault da `main`: um `saida/` velho (o de entrada, semeado do bucket, nem tem `.base`) nunca a sobrescreve."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._base_lida: str | None = None    # a base do texto que o último ler() devolveu

    def _lib(self) -> VaultLib:
        senha = Path(self.cfg.senha_vault_arquivo).read_text(encoding="utf-8").strip()
        return VaultLib([("default", VaultSecret(senha.encode("utf-8")))])

    def _saida(self) -> Path:
        return Path(self.cfg.saida_dir) / "vault.yml"

    def _base_arquivo(self) -> Path:
        return Path(self.cfg.saida_dir) / ".base"

    def _main(self) -> Path:
        return Path(self.cfg.repo_dir) / VAULT_NO_REPO

    def _sha_main(self) -> str:
        try:
            return hashlib.sha256(self._main().read_bytes()).hexdigest()
        except FileNotFoundError:
            return BASE_AUSENTE

    def _escolher(self) -> tuple[Path, str]:
        """(arquivo a ler, base que uma edição dele terá)."""
        sha_main = self._sha_main()
        saida = self._saida()
        if saida.exists():
            if sha_main == BASE_AUSENTE:
                return saida, BASE_AUSENTE
            try:
                base = self._base_arquivo().read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                base = None
            if base == sha_main:
                return saida, sha_main
        return self._main(), sha_main

    def origem(self) -> Path:
        """`saida/vault.yml` se ele tem edições sobre a `main` atual (ou a `main` não tem vault); senão, o da `main`."""
        return self._escolher()[0]

    def ler(self) -> str:
        arquivo, base = self._escolher()
        texto = self._lib().decrypt(arquivo.read_bytes()).decode("utf-8")
        self._base_lida = base
        return texto

    def _gravar_atomico(self, destino: Path, dados: bytes) -> None:
        fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix=".vault-", suffix=".tmp")   # 0600
        try:
            with os.fdopen(fd, "wb") as f:
                os.fchmod(fd, 0o644)   # cifrado e destinado ao git; o sysadmin (outro uid) monta `saida` só para ler
                f.write(dados)
            os.replace(tmp, destino)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def gravar(self, texto: str) -> None:
        """Cifra e grava em `saida/vault.yml` de forma atômica, com o `.base` do texto lido (texto puro nunca vai ao
        disco). A base é a do último ler(): se a `main` mudou entre a leitura e a gravação, a edição não a
        sobrescreve (volta a valer a `main`)."""
        base = self._base_lida if self._base_lida is not None else self._sha_main()
        cifrado = self._lib().encrypt(texto)
        saida = self._saida()
        saida.parent.mkdir(parents=True, exist_ok=True)
        # O .base vai depois: se cair entre os dois, um vault.yml novo com o .base antigo não bate com a main e vale a
        # main (a edição se perde, a main não é sobrescrita); o contrário leria um vault.yml velho como edição nova.
        self._gravar_atomico(saida, cifrado)
        self._gravar_atomico(self._base_arquivo(), (base + "\n").encode("utf-8"))
        self._base_lida = base
