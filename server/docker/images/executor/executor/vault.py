"""Vault do Ansible editado pelo executor: lê o modelo, troca o valor de uma folha e grava cifrado em `saida/`."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

import yaml

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


_NADA = object()
_TRAVA = threading.RLock()   # o leitor do Telegram e o MCP rodam em threads: uma leitura ou edição do saida/ por vez
DESCONHECIDO = "?"           # commit do vault da main que não deu para ler (git ausente, .base antigo)


class SemVault(FileNotFoundError):
    """Nem a `main` nem o `saida/` têm vault."""


class VaultIndisponivel(RuntimeError):
    """O vault da `main` sumiu depois de servir de base às edições (git pull no meio, clone estragado): nada vale."""


def _sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def _folhas(dado, prefixo: str = "") -> dict:
    """Caminho com ponto -> valor de cada folha de um mapa YAML (listas e mapas vazios contam como valor)."""
    saida = {}
    if isinstance(dado, dict):
        for chave, valor in dado.items():
            nome = f"{prefixo}{chave}"
            if isinstance(valor, dict) and valor:
                saida.update(_folhas(valor, nome + "."))
            else:
                saida[nome] = valor
    return saida


@dataclass(frozen=True)
class Leitura:
    texto: str
    base: str                   # sha256 do vault da `main` em que o texto se baseia, ou BASE_AUSENTE
    ancestral: bytes | None     # o vault cifrado de onde as edições partiram (para reaplicá-las sobre outra `main`)
    commit: str = DESCONHECIDO  # último commit que mudou o vault da `main` na base ("" se ela não tinha vault)


class Vault:
    """O `saida/vault.yml` guarda as edições ainda não mescladas. Ao lado dele:

    - `saida/.base`: três linhas: o sha256 do vault da `main` em que elas se basearam (ou `ausente`), o sha256 do
      `saida/.base.yml` e o último commit que tinha mudado o vault da `main` nessa base;
    - `saida/.base.yml`: o vault (cifrado) de onde as edições partiram, o ancestral comum;
    - `saida/.conflitos`: os nomes (nunca os valores) das edições que a `main` também mudou e que não foram reaplicadas,
      com `*` nas que o Léo já foi avisado pelo Telegram; somem quando a chave é preenchida de novo ou numa reaplicação
      seguinte (a `main` mudou outra vez).

    Com a mesma `main` (mesmo conteúdo e mesmo histórico do vault), vale o `saida/`, se ele difere dela. Se a `main`
    mudou, as edições que ela nunca teve são **reaplicadas** sobre ela, chave a chave, comparando com o ancestral e
    com cada versão do vault da `main` desde a base (`git log`): as que ela já teve em algum momento caem (foram
    mescladas; se depois mudaram, vale a `main`), as que ela mudou para outro valor viram conflito. Sem nada a
    reaplicar, ou sem ancestral (o `entrada/` semeado com a `main` já tendo vault), o `saida/` é **encerrado**
    (apagado): um `saida/` superado nunca volta a valer, mesmo que a `main` volte ao conteúdo antigo."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def _lib(self) -> VaultLib:
        senha = Path(self.cfg.senha_vault_arquivo).read_text(encoding="utf-8").strip()
        return VaultLib([("default", VaultSecret(senha.encode("utf-8")))])

    def _decifrar(self, dados: bytes) -> str:
        return self._lib().decrypt(dados).decode("utf-8")

    def _saida(self) -> Path:
        return Path(self.cfg.saida_dir) / "vault.yml"

    def _arquivo(self, nome: str) -> Path:
        return Path(self.cfg.saida_dir) / nome

    def _main(self) -> Path:
        return Path(self.cfg.repo_dir) / VAULT_NO_REPO

    def _bytes_da_main(self) -> bytes | None:
        try:
            return self._main().read_bytes()
        except FileNotFoundError:
            return None

    # --- histórico do vault na main (git do clone do executor) ---

    def _git(self, *args: str) -> bytes | None:
        try:
            r = subprocess.run(["git", "-C", self.cfg.repo_dir, *args], capture_output=True, timeout=30, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout if r.returncode == 0 else None

    def _commit_do_vault(self) -> str:
        saida = self._git("log", "-1", "--format=%H", "--", VAULT_NO_REPO)
        return DESCONHECIDO if saida is None else saida.decode().strip()

    def _historico(self, desde: str) -> list[dict] | None:
        """As folhas do vault da `main` em cada commit que o mudou depois de `desde` ("" = desde sempre); `None` se o
        git não responder. Versões que esta senha não abre ficam de fora."""
        saida = self._git("log", "--format=%H", *([f"{desde}..HEAD"] if desde else ["HEAD"]), "--", VAULT_NO_REPO)
        if saida is None:
            return None
        versoes = []
        for commit in saida.decode().split():
            dados = self._git("show", f"{commit}:{VAULT_NO_REPO}")
            if dados is None:                                   # o commit que apagou o arquivo
                continue
            try:
                versoes.append(_folhas(yaml.safe_load(self._decifrar(dados))))
            except Exception as erro:  # noqa: BLE001 — só o tipo do erro
                print(f"vault: versão {commit[:8]} da main ilegível ({type(erro).__name__})", file=sys.stderr)
        return versoes

    # --- estado do saida/ ---

    def _base(self) -> tuple[str | None, bytes | None, str]:
        """(base, ancestral, commit) gravados com o saida/; o ancestral só vale se o sha dele bate com o do `.base`."""
        try:
            linhas = self._arquivo(".base").read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return None, None, DESCONHECIDO
        base = linhas[0].strip() if linhas else None
        commit = linhas[2].strip() if len(linhas) > 2 else DESCONHECIDO
        sha_ancestral = linhas[1].strip() if len(linhas) > 1 else ""
        if not sha_ancestral:
            return base, None, commit
        try:
            ancestral = self._arquivo(".base.yml").read_bytes()
        except FileNotFoundError:
            return base, None, commit
        return base, (ancestral if _sha(ancestral) == sha_ancestral else None), commit

    def _conflitos(self) -> dict[str, bool]:
        """nome -> já avisado ao Léo."""
        try:
            linhas = self._arquivo(".conflitos").read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return {}
        return {l.split()[0]: len(l.split()) > 1 for l in linhas if l.split()}

    def _conflitos_gravados(self) -> list[str]:
        return list(self._conflitos())

    def _encerrar(self) -> None:
        """O saida/ foi superado pela main: sai de cena (o `.conflitos` fica, para o Léo saber o que pedir de novo)."""
        for nome in ("vault.yml", ".base", ".base.yml"):
            self._arquivo(nome).unlink(missing_ok=True)

    def _escolher(self, decifrar: bool) -> tuple[Path, Leitura | None, list[str]]:
        """(arquivo que vale, leitura dele se `decifrar`, conflitos registrados). Chamar com a trava; pode encerrar ou
        regravar o saida/."""
        main = self._bytes_da_main()
        saida = self._saida()
        if not saida.exists():
            if main is None:
                raise SemVault(self._main())
            return self._da_main(main, decifrar)
        base, ancestral, commit_base = self._base()
        if main is None:
            # Sem vault na main, vale o saida/, mas só se ele nunca se baseou num vault da main e o clone está são:
            # uma main que some no meio de um git pull (ou um clone estragado) não pode promover um saida/ velho.
            if base not in (None, BASE_AUSENTE) or not (Path(self.cfg.repo_dir) / ".git").exists():
                raise VaultIndisponivel("o vault da main sumiu depois de servir de base; tente de novo")
            dados = saida.read_bytes()
            if base is None:                                   # a entrada do bucket sem edição: ela é o ancestral
                ancestral = dados
            leitura = Leitura(self._decifrar(dados), BASE_AUSENTE, ancestral, "") if decifrar else None
            return saida, leitura, self._conflitos_gravados()
        sha_main = _sha(main)
        commit_agora = self._commit_do_vault()
        mesma_historia = DESCONHECIDO in (commit_base, commit_agora) or commit_base == commit_agora
        if base == sha_main and mesma_historia:
            texto = self._decifrar(saida.read_bytes())
            if _folhas(yaml.safe_load(texto)) == _folhas(yaml.safe_load(self._decifrar(main))):
                self._encerrar()                               # nada difere da main: não há o que levar ao PR
                return self._da_main(main, decifrar)
            commit = commit_base if commit_agora == DESCONHECIDO else commit_agora
            return saida, Leitura(texto, sha_main, main, commit), self._conflitos_gravados()
        if ancestral is None:                                  # entrada velha ou .base antigo: vale a main
            self._encerrar()
            return self._da_main(main, decifrar)
        historico = None if DESCONHECIDO in (commit_base, commit_agora) else self._historico(commit_base)
        return self._reaplicar(saida.read_bytes(), ancestral, main, commit_agora, historico or [])

    def _da_main(self, main: bytes, decifrar: bool) -> tuple[Path, Leitura | None, list[str]]:
        leitura = Leitura(self._decifrar(main), _sha(main), main, self._commit_do_vault()) if decifrar else None
        return self._main(), leitura, self._conflitos_gravados()

    def _reaplicar(self, nosso: bytes, ancestral: bytes, main: bytes, commit: str,
                   historico: list[dict]) -> tuple[Path, Leitura, list[str]]:
        """Reaplica sobre a `main` nova as edições do saida/ que ela nunca teve; grava o resultado se sobrar alguma,
        senão encerra o saida/."""
        texto_main = self._decifrar(main)
        antes = _folhas(yaml.safe_load(self._decifrar(ancestral)))
        depois = _folhas(yaml.safe_load(self._decifrar(nosso)))
        agora = _folhas(yaml.safe_load(texto_main))
        texto, pendentes, novos = texto_main, [], []
        for chave, valor in depois.items():
            if antes.get(chave, _NADA) == valor or agora.get(chave, _NADA) == valor:
                continue                                       # não é edição nossa, ou a main já a tem
            if any(versao.get(chave, _NADA) == valor for versao in historico):
                continue                                       # a main já a teve (PR mesclado) e depois mudou: vale a main
            if agora.get(chave, _NADA) != antes.get(chave, _NADA) or not isinstance(valor, str):
                novos.append(chave)                            # a main mudou a chave para outro valor: vale a main
                continue
            try:
                texto = definir(texto, chave, valor)
            except KeyError:
                novos.append(chave)
                continue
            pendentes.append(chave)
        leitura = Leitura(texto, _sha(main), main, commit)
        if pendentes:
            self._gravar(texto, leitura)
        else:
            self._encerrar()
        self._gravar_conflitos({c: False for c in novos})   # os de antes eram de outra main: já superados
        return (self._saida() if pendentes else self._main()), leitura, novos

    # --- interface ---

    def origem(self) -> Path:
        """`saida/vault.yml` se ele tem edições sobre a `main` atual (ou a `main` não tem vault); senão, o da `main`."""
        return self.situacao()[0]

    def situacao(self) -> tuple[Path, list[str]]:
        """(arquivo que vale, chaves editadas pelo Léo que a main também mudou e não foram reaplicadas)."""
        with _TRAVA:
            try:
                arquivo, _, conflitos = self._escolher(decifrar=False)
            except SemVault:
                return self._main(), []
            return arquivo, conflitos

    def ler(self) -> str:
        return self.ler_com_base().texto

    def ler_com_base(self) -> Leitura:
        with _TRAVA:
            return self._escolher(decifrar=True)[1]

    def editar(self, chave: str, valor: str) -> list[str]:
        """Lê, troca uma folha e grava sob a mesma trava (a base gravada é sempre a do texto editado). Devolve os
        conflitos de que o Léo ainda não foi avisado (cada um é avisado uma vez; a chave regravada deixa de ser
        conflito); `KeyError` se a chave não é uma folha do vault atual."""
        with _TRAVA:
            _, leitura, _ = self._escolher(decifrar=True)
            self._gravar(definir(leitura.texto, chave, valor), leitura)
            conflitos = {c: avisado for c, avisado in self._conflitos().items() if c != chave}
            self._gravar_conflitos({c: True for c in conflitos})
            return [c for c, avisado in conflitos.items() if not avisado]

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

    def _gravar_conflitos(self, conflitos: dict[str, bool]) -> None:
        arquivo = self._arquivo(".conflitos")
        if conflitos:
            texto = "".join(f"{c} *\n" if avisado else f"{c}\n" for c, avisado in conflitos.items())
            self._gravar_atomico(arquivo, texto.encode("utf-8"))
        else:
            arquivo.unlink(missing_ok=True)

    def _gravar(self, texto: str, leitura: Leitura) -> None:
        cifrado = self._lib().encrypt(texto)
        self._saida().parent.mkdir(parents=True, exist_ok=True)
        if leitura.ancestral is not None:
            sha_ancestral = _sha(leitura.ancestral)
            self._gravar_atomico(self._arquivo(".base.yml"), leitura.ancestral)
        else:
            sha_ancestral = ""
            self._arquivo(".base.yml").unlink(missing_ok=True)
        base = f"{leitura.base}\n{sha_ancestral}\n{leitura.commit}\n".encode("utf-8")
        if leitura.base == BASE_AUSENTE:
            # Sem vault na main o saida/ vale de qualquer jeito: o .base vai antes, para o vault.yml editado nunca
            # virar o ancestral (sem .base, o saida/ seria tomado pela entrada do bucket, sem edições).
            self._gravar_atomico(self._arquivo(".base"), base)
            self._gravar_atomico(self._saida(), cifrado)
        else:
            # Com vault na main, o .base vai depois. Se cair entre os dois: na mesma base, vale a edição nova (certo);
            # numa base nova (reaplicação), o .base antigo não confere com o ancestral novo, o saida/ é encerrado e vale
            # a main: a edição pode se perder, mas a main nunca é sobrescrita por um saida/ velho.
            self._gravar_atomico(self._saida(), cifrado)
            self._gravar_atomico(self._arquivo(".base"), base)

    def gravar(self, texto: str, leitura: Leitura | None = None) -> None:
        """Cifra e grava em `saida/vault.yml` de forma atômica (texto puro nunca vai ao disco), com a base da `leitura`
        de onde o texto saiu; sem ela, a base é o vault atual da `main`."""
        with _TRAVA:
            if leitura is None:
                main = self._bytes_da_main()
                leitura = (Leitura(texto, _sha(main), main, self._commit_do_vault()) if main is not None
                           else Leitura(texto, BASE_AUSENTE, None, ""))
            self._gravar(texto, leitura)
