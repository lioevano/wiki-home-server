"""Vault do Ansible editado pelo executor: lê o modelo, troca o valor de uma folha e grava cifrado em `saida/`."""
from __future__ import annotations

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


def _varrer(linhas: list[str]):
    """Gera (inicio, fim, indentacao, chave, caminho, resto) de cada chave do YAML.

    `fim` é exclusivo e só passa de `inicio + 1` nos blocos `|`/`>`, que vão até a próxima linha
    não vazia menos indentada (o conteúdo do bloco nunca é lido como chave).
    """
    pilha: list[tuple[int, str]] = []
    i = 0
    while i < len(linhas):
        linha, inicio = linhas[i], i
        i += 1
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
        yield inicio, i, ind, chave, ".".join(c for _, c in pilha), resto


def _folha(resto: str) -> bool:
    return bool(resto) and not resto.startswith("#")


def chaves_do_modelo(texto: str) -> set[str]:
    """Caminhos com ponto das folhas (chaves de mapa, que têm filhos, não contam)."""
    return {nome for _, _, _, _, nome, resto in _varrer(texto.split("\n")) if _folha(resto)}


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
    for inicio, fim, ind, nome_chave, nome, resto in _varrer(linhas):
        if nome != chave or not _folha(resto):
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
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def _lib(self) -> VaultLib:
        senha = Path(self.cfg.senha_vault_arquivo).read_text(encoding="utf-8").strip()
        return VaultLib([("default", VaultSecret(senha.encode("utf-8")))])

    def _saida(self) -> Path:
        return Path(self.cfg.saida_dir) / "vault.yml"

    def origem(self) -> Path:
        """`saida/vault.yml` (o que o sysadmin já editou) ou, na primeira vez, o vault do repositório."""
        saida = self._saida()
        return saida if saida.exists() else Path(self.cfg.repo_dir) / VAULT_NO_REPO

    def ler(self) -> str:
        return self._lib().decrypt(self.origem().read_bytes()).decode("utf-8")

    def gravar(self, texto: str) -> None:
        """Cifra e grava em `saida/vault.yml` de forma atômica; texto puro nunca vai ao disco."""
        cifrado = self._lib().encrypt(texto)
        saida = self._saida()
        saida.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=saida.parent, prefix=".vault-", suffix=".tmp")   # 0600
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(cifrado)
            os.replace(tmp, saida)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
