"""Comandos remotos nos hosts da casa, por Ansible ad-hoc (a chave SSH só existe neste container)."""
from __future__ import annotations

import re
import shlex
from pathlib import Path

from ops.politica import Recusado, limpar_saida
from ops.runner import Executar, executar_real

from .config import Config

TEMPO_S = 120

# Formas exatas, sem argumentos livres (valor: precisa de --become).
FIXOS = {
    ("systemctl", "list-units", "--failed"): False,
    ("docker", "ps"): True, ("docker", "ps", "-a"): True,
    ("df", "-h"): False, ("free", "-m"): False, ("uptime",): False,
    ("ip", "-br", "a"): False, ("ip", "route"): False, ("ss", "-tlnp"): True,
    ("tailscale", "status"): False, ("cat", "/etc/os-release"): False,
}
# Todos começam com letra ou dígito: nunca viram opção (-f, --follow…) do comando.
UNIDADE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@:-]{0,127}")
CONTAINER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,253}")
NUMERO = re.compile(r"[1-9][0-9]{0,2}")  # só dígitos ASCII, sem zero à esquerda


def _numero(texto: str, maximo: int) -> bool:
    return NUMERO.fullmatch(texto) is not None and 1 <= int(texto) <= maximo


def validar_diagnostico(comando: str) -> tuple[list[str], bool]:
    """Aceita só as formas de leitura abaixo, exatamente; devolve (argv, precisa de --become). Nada passa por
    shell: o argv vai ao módulo command. Qualquer outra coisa levanta Recusado."""
    if not isinstance(comando, str) or not comando:
        raise Recusado("comando vazio")
    # Separa só em espaço simples: aspas, tabs, quebras de linha e metacaracteres ficam dentro dos tokens e
    # reprovam nas expressões acima; espaços duplicados/nas pontas geram token vazio e reprovam.
    t = comando.split(" ")
    if any(x == "" for x in t):
        raise Recusado("comando fora das formas de diagnóstico permitidas")
    n = len(t)
    become = FIXOS.get(tuple(t))
    if become is not None:
        return t, become
    if t[0] == "systemctl" and n == 3 and t[1] in ("status", "is-active") and UNIDADE.fullmatch(t[2]):
        return t, False
    if t[0] == "journalctl" and n in (5, 6) and t[1] == "-u" and UNIDADE.fullmatch(t[2]) and t[3] == "-n" \
            and _numero(t[4], 500) and (n == 5 or t[5] == "--no-pager"):
        return t, True
    if t[0] == "docker" and n == 5 and t[1] == "logs" and t[2] == "--tail" and _numero(t[3], 500) \
            and CONTAINER.fullmatch(t[4]):
        return t, True
    if t[0] == "ping" and n == 4 and t[1] == "-c" and _numero(t[2], 5) and HOST.fullmatch(t[3]):
        return t, False
    raise Recusado("comando fora das formas de diagnóstico permitidas")


class Remoto:
    def __init__(self, cfg: Config, executar: Executar = executar_real):
        self.cfg, self.executar = cfg, executar

    @property
    def _cwd(self) -> str:
        return f"{self.cfg.repo_dir}/server/ansible"  # onde ficam o ansible.cfg e o inventário

    def hosts(self) -> set[str]:
        """Nomes dos hosts do inventário: só linhas de host de seções de grupo (sem [x:vars] e [x:children])."""
        try:
            linhas = Path(self._cwd, self.cfg.inventario).read_text(encoding="utf-8").splitlines()
        except OSError as erro:
            raise Recusado(f"inventário ilegível: {type(erro).__name__}") from None
        nomes, valido = set(), False
        for linha in linhas:
            linha = linha.strip()
            if not linha or linha[0] in "#;":
                continue
            if linha.startswith("["):
                valido = linha.endswith("]") and ":" not in linha
                continue
            if valido:
                nomes.add(linha.split()[0])
        return nomes

    def rodar(self, host: str, comando: "list[str] | str", shell: bool, become: bool) -> tuple[int, str]:
        if host.startswith("-") or host not in self.hosts():
            raise Recusado(f"host {host!r} não está no inventário")
        partes = [comando] if isinstance(comando, str) else comando
        if any(m in parte for parte in partes for m in ("{{", "{%", "{#")):
            raise Recusado("comando contém {{, {% ou {#: o Ansible interpretaria isso como Jinja no próprio executor "
                           "(lê arquivos e roda comandos nele, não no host)")
        texto = comando if isinstance(comando, str) else shlex.join(comando)
        argv = ["ansible", host, "-i", self.cfg.inventario, "-m",
                "ansible.builtin.shell" if shell else "ansible.builtin.command", "-a", texto,
                "-e", f"ansible_ssh_private_key_file={self.cfg.chave_ssh}"]
        if become:
            argv.append("--become")
        rc, saida = self.executar(argv, self._cwd, TEMPO_S)
        return rc, limpar_saida(saida, self.cfg.limite_saida)
