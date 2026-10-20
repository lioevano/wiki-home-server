"""Runner Ansible do ops: simulação obrigatória (ansible_check) antes de aplicar (ansible_aplicar)."""
from __future__ import annotations

import secrets
import subprocess
import threading
import time
from typing import Callable

from .config import Config
from .politica import Recusado, limpar_saida

Executar = Callable[[list[str], str, int], "tuple[int, str]"]
TEMPO_CHECK_S = 900
TEMPO_APLICAR_S = 3600


def executar_real(argv: list[str], cwd: str, timeout: int) -> tuple[int, str]:
    try:
        r = subprocess.run(argv, cwd=cwd, timeout=timeout, capture_output=True, text=True)
    except subprocess.TimeoutExpired as erro:
        return 124, f"{erro.output or ''}\n[tempo esgotado depois de {timeout} s]"
    return r.returncode, r.stdout + r.stderr


class Runner:
    def __init__(self, cfg: Config, executar: Executar = executar_real, agora: Callable[[], float] = time.time):
        self.cfg = cfg
        self.executar = executar
        self.agora = agora
        self._planos: dict[str, dict] = {}
        self._trava = threading.Lock()

    @property
    def _cwd(self) -> str:
        return f"{self.cfg.repo_dir}/server/ansible"  # onde fica o ansible.cfg (roles_path, inventário)

    def _atualizar_repo(self) -> str:
        rc, saida = self.executar(["git", "-C", self.cfg.repo_dir, "pull", "--ff-only"], self.cfg.repo_dir, 120)
        if rc != 0:
            raise Recusado(f"git pull falhou: {limpar_saida(saida, 2000)}")
        rc, saida = self.executar(["git", "-C", self.cfg.repo_dir, "rev-parse", "HEAD"], self.cfg.repo_dir, 30)
        if rc != 0:
            raise Recusado("não foi possível ler o commit do repositório")
        return saida.strip()

    def _argv(self, playbook: str, limite: str | None, simular: bool) -> list[str]:
        argv = ["ansible-playbook", "-i", self.cfg.inventario, f"playbooks/{playbook}",
                "-e", f"ansible_ssh_private_key_file={self.cfg.chave_ssh}"]
        if simular:
            argv += ["--check", "--diff"]
        if limite:
            argv += ["-l", limite]
        return argv

    def _exclusivo(self):
        if not self._trava.acquire(blocking=False):
            raise Recusado("outra execução em andamento; tente de novo quando ela terminar")
        return self._trava

    def check(self, playbook: str, limite: str | None = None) -> dict:
        if playbook not in self.cfg.playbooks:
            raise Recusado(f"{playbook} não está em ops_playbooks_permitidos")
        trava = self._exclusivo()
        try:
            commit = self._atualizar_repo()
            rc, saida = self.executar(self._argv(playbook, limite, True), self._cwd, TEMPO_CHECK_S)
        finally:
            trava.release()
        plano_id = ""
        if rc == 0:
            plano_id = secrets.token_hex(8)
            self._planos[plano_id] = {"playbook": playbook, "limite": limite, "commit": commit, "criado": self.agora()}
        return {"plano_id": plano_id, "commit": commit, "rc": rc, "saida": limpar_saida(saida, self.cfg.limite_saida)}

    def aplicar(self, plano_id: str) -> dict:
        plano = self._planos.pop(plano_id, None)  # um plano só vale uma vez
        if plano is None:
            raise Recusado("plano_id desconhecido ou já usado; rode ansible_check de novo")
        if self.agora() - plano["criado"] > self.cfg.plano_validade_s:
            raise Recusado("plano vencido; rode ansible_check de novo")
        trava = self._exclusivo()
        try:
            commit = self._atualizar_repo()
            if commit != plano["commit"]:
                raise Recusado(f"o repositório mudou desde a simulação ({plano['commit'][:8]} → {commit[:8]}); "
                               "rode ansible_check de novo")
            rc, saida = self.executar(self._argv(plano["playbook"], plano["limite"], False), self._cwd,
                                      TEMPO_APLICAR_S)
        finally:
            trava.release()
        return {"playbook": plano["playbook"], "commit": commit, "rc": rc,
                "saida": limpar_saida(saida, self.cfg.limite_saida)}
