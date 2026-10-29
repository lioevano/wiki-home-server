"""Cliente mínimo da API do Portainer (CE 2.45): containers das duas VMs e stacks."""
from __future__ import annotations

import json
import struct
import urllib.error
import urllib.request
from typing import Callable

from .config import Config

Http = Callable[[str, str, "dict | None"], "tuple[int, bytes]"]


class ErroPortainer(Exception):
    pass


def http_real(cfg: Config) -> Http:
    def chamar(metodo: str, caminho: str, corpo: dict | None) -> tuple[int, bytes]:
        dados = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(cfg.portainer_url + caminho, data=dados, method=metodo,
                                     headers={"X-API-Key": cfg.portainer_api_key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as erro:
            return erro.code, erro.read()

    return chamar


def _desmultiplexar(corpo: bytes) -> str:
    """Logs do Docker sem TTY vêm em frames: 1 byte de stream, 3 zerados, 4 de tamanho (big-endian)."""
    partes, i = [], 0
    while i + 8 <= len(corpo) and corpo[i] in (0, 1, 2) and corpo[i + 1:i + 4] == b"\x00\x00\x00":
        (tamanho,) = struct.unpack(">L", corpo[i + 4:i + 8])
        partes.append(corpo[i + 8:i + 8 + tamanho])
        i += 8 + tamanho
    if i != len(corpo):  # container com TTY: texto puro
        return corpo.decode("utf-8", errors="replace")
    return b"".join(partes).decode("utf-8", errors="replace")


class Portainer:
    def __init__(self, cfg: Config, http: Http):
        self.cfg = cfg
        self.http = http

    def _json(self, metodo: str, caminho: str, corpo: dict | None = None):
        status, resposta = self.http(metodo, caminho, corpo)
        if status >= 300:
            raise ErroPortainer(f"Portainer respondeu {status} em {metodo} {caminho}: {resposta[:200]!r}")
        return json.loads(resposta) if resposta else None

    def _endpoints(self) -> dict[str, int]:
        por_nome = {e["Name"]: e["Id"] for e in self._json("GET", "/api/endpoints")}
        faltando = [n for n in self.cfg.endpoints.values() if n not in por_nome]
        if faltando:
            raise ErroPortainer(f"ambiente(s) {faltando} não existem no Portainer (confira ops_endpoints)")
        return {vm: por_nome[nome] for vm, nome in self.cfg.endpoints.items()}

    def containers(self, vm: str | None = None) -> list[dict]:
        eps = self._endpoints()
        if vm is not None and vm not in eps:
            raise ErroPortainer(f"VM desconhecida: {vm} (use {sorted(eps)})")
        lista = []
        for nome_vm, eid in eps.items():
            if vm is not None and nome_vm != vm:
                continue
            for c in self._json("GET", f"/api/endpoints/{eid}/docker/containers/json?all=1"):
                status = c.get("Status", "")
                saude = "healthy" if "(healthy)" in status else "unhealthy" if "(unhealthy)" in status else "—"
                lista.append({"vm": nome_vm, "nome": c["Names"][0].lstrip("/"), "imagem": c.get("Image", ""),
                              "estado": c.get("State", ""), "saude": saude, "status": status,
                              "_eid": eid, "_id": c["Id"]})
        return lista

    def _localizar(self, nome: str, vm: str | None = None) -> dict:
        achados = [c for c in self.containers(vm) if c["nome"] == nome]
        if not achados:
            raise ErroPortainer(f"container {nome} não encontrado" + (f" na VM {vm}" if vm else " nas VMs"))
        if len(achados) > 1:  # mesmo nome nas duas VMs: não escolhe sozinho
            vms = ", ".join(sorted(c["vm"] for c in achados))
            raise ErroPortainer(f"o container {nome} existe em mais de uma VM ({vms}); informe vm")
        return achados[0]

    def logs(self, nome: str, linhas: int, vm: str | None = None) -> str:
        c = self._localizar(nome, vm)
        status, corpo = self.http("GET", f"/api/endpoints/{c['_eid']}/docker/containers/{c['_id']}/logs"
                                         f"?stdout=1&stderr=1&tail={linhas}", None)
        if status >= 300:
            raise ErroPortainer(f"Portainer respondeu {status} ao ler os logs de {nome}")
        return _desmultiplexar(corpo)

    def reiniciar(self, nome: str, vm: str | None = None) -> None:
        c = self._localizar(nome, vm)
        status, corpo = self.http("POST", f"/api/endpoints/{c['_eid']}/docker/containers/{c['_id']}/restart", None)
        if status >= 300:
            raise ErroPortainer(f"Portainer respondeu {status} ao reiniciar {nome}: {corpo[:200]!r}")

    def _stacks_brutas(self) -> list[dict]:
        return self._json("GET", "/api/stacks")

    def stacks(self) -> list[dict]:
        eps = {eid: vm for vm, eid in self._endpoints().items()}
        return [{"nome": s["Name"], "vm": eps.get(s.get("EndpointId"), str(s.get("EndpointId"))),
                 "estado": "ativa" if s.get("Status") == 1 else "parada"} for s in self._stacks_brutas()]

    def redeploy(self, nome: str, puxar_imagens: bool) -> None:
        stack = next((s for s in self._stacks_brutas() if s["Name"] == nome), None)
        if stack is None:
            raise ErroPortainer(f"stack {nome} não encontrada no Portainer")
        arquivo = self._json("GET", f"/api/stacks/{stack['Id']}/file")["StackFileContent"]
        self._json("PUT", f"/api/stacks/{stack['Id']}?endpointId={stack['EndpointId']}",
                   {"stackFileContent": arquivo, "env": stack.get("Env") or [], "prune": False,
                    "pullImage": puxar_imagens})
