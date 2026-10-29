"""Servidor HTTP (POST /alerta, GET /saude), fila de análises (uma por vez) e agendador do boletim da manhã."""
from __future__ import annotations

import hashlib
import hmac
import json
import queue
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from . import agente, prompts, saida
from .config import Config
from .llm import ClienteLLM
from .mcp import ClienteMCP

LIMITE_CORPO = 1_000_000


def impressao(alerta: dict) -> str:
    if alerta.get("fingerprint"):
        return str(alerta["fingerprint"])
    rotulos = json.dumps(alerta.get("labels") or {}, sort_keys=True)
    return hashlib.sha256(rotulos.encode()).hexdigest()[:16]


def proximo_boletim(agora: datetime, hora: str) -> datetime:
    h, m = (int(x) for x in hora.split(":"))
    alvo = agora.replace(hour=h, minute=m, second=0, microsecond=0)
    return alvo if alvo > agora else alvo + timedelta(days=1)


class Observador:
    def __init__(self, cfg: Config, fazer_mcp: Callable[[], object] | None = None,
                 fazer_llm: Callable[[], object] | None = None, enviar: saida.Enviar | None = None,
                 relogio: Callable[[], float] = time.time):
        self.cfg = cfg
        self.fazer_mcp = fazer_mcp or (lambda: ClienteMCP(cfg.hub_url, cfg.hub_token))
        self.fazer_llm = fazer_llm or (lambda: ClienteLLM(cfg.llm_url, cfg.llm_chave, cfg.modelo))
        self.enviar = enviar or saida.enviar_webhook(cfg.webhook_url, cfg.webhook_token)
        self.relogio = relogio
        self.fila: queue.Queue = queue.Queue(maxsize=cfg.fila_max)
        self.vistos: dict[str, float] = {}
        self.inicios: deque = deque()
        self._trava = threading.Lock()

    # --- Entrada dos alertas ---

    def _motivo_para_ignorar(self, alerta: dict, agora: float) -> str | None:
        nome = (alerta.get("labels") or {}).get("alertname", "")
        if alerta.get("status") != "firing":
            return "não está disparando"
        if nome in self.cfg.ignorar:
            return "alerta ignorado (OBSERVADOR_IGNORAR)"
        visto = self.vistos.get(impressao(alerta))
        if visto is not None and agora - visto < self.cfg.reanalise_h * 3600:
            return "já analisado nas últimas horas"
        while self.inicios and agora - self.inicios[0] > 3600:
            self.inicios.popleft()
        if len(self.inicios) >= self.cfg.max_por_hora:
            return "limite de análises por hora"
        return None

    def receber_alerta(self, payload: dict) -> dict:
        aceitos, ignorados = [], []
        with self._trava:
            agora = self.relogio()
            janela = self.cfg.reanalise_h * 3600
            self.vistos = {fp: t for fp, t in self.vistos.items() if agora - t < janela}  # não cresce sem fim
            for alerta in payload.get("alerts") or []:
                nome = (alerta.get("labels") or {}).get("alertname", "alerta")
                motivo = self._motivo_para_ignorar(alerta, agora)
                if motivo is None:
                    try:
                        self.fila.put_nowait(("alerta", alerta))
                    except queue.Full:
                        motivo = "fila cheia"
                if motivo:
                    ignorados.append(nome)
                    saida.registrar({"gatilho": "alerta", "alerta": nome, "resultado": "ignorado", "motivo": motivo})
                    continue
                self.vistos[impressao(alerta)] = agora
                self.inicios.append(agora)
                aceitos.append(nome)
        return {"aceitos": aceitos, "ignorados": ignorados}

    # --- Análises ---

    def processar(self, gatilho: str, alerta: dict | None = None) -> dict:
        inicio = time.monotonic()
        nome = ((alerta or {}).get("labels") or {}).get("alertname", "") if alerta else ""
        sessao = uuid.uuid4().hex[:12]
        if gatilho == "alerta":
            tarefa = prompts.tarefa_alerta(alerta or {})
        else:
            tarefa = prompts.tarefa_boletim(datetime.now().astimezone().strftime("%d/%m/%Y %H:%M"))
        metadata = {"trace_name": f"observador-{gatilho}", "session_id": f"observador-{sessao}",
                    "tags": ["observador", gatilho] + ([nome] if nome else [])}
        reg = {"gatilho": gatilho, "alerta": nome, "sessao": sessao}
        try:
            res = agente.investigar(prompts.SISTEMA, tarefa, self.fazer_mcp(), self.fazer_llm(),
                                    self.cfg.max_passos, self.cfg.limite_saida, self.cfg.tempo_max_s, metadata)
            aviso = saida.aviso_alerta(alerta or {}, res.texto) if gatilho == "alerta" else saida.aviso_boletim(res.texto)
            reg.update(resultado="ok", passos=res.passos, ferramentas=res.ferramentas, tokens=res.uso)
            try:
                self.enviar(aviso)
                reg["aviso"] = "enviado"
            except Exception as erro:
                reg["aviso"] = "falhou"
                saida.aviso_erro(str(erro), "aviso")
        except Exception as erro:  # LiteLLM fora, orçamento estourado, hub fora: registra (alerta observador-falhou)
            reg.update(resultado="erro", detalhe=str(erro)[:500])
        reg["duracao_s"] = round(time.monotonic() - inicio, 2)
        return saida.registrar(reg)

    def trabalhar(self, parar: threading.Event) -> None:
        while not parar.is_set():
            try:
                gatilho, alerta = self.fila.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self.processar(gatilho, alerta)
            finally:
                self.fila.task_done()

    def agendar_boletim(self, parar: threading.Event) -> None:
        if not self.cfg.boletim_hora:
            return
        while not parar.is_set():
            agora = datetime.now().astimezone()
            espera = (proximo_boletim(agora, self.cfg.boletim_hora) - agora).total_seconds()
            if parar.wait(espera):
                return
            try:
                self.fila.put_nowait(("boletim", None))
            except queue.Full:
                saida.registrar({"gatilho": "boletim", "resultado": "ignorado", "motivo": "fila cheia"})


def fazer_handler(obs: Observador):
    class Handler(BaseHTTPRequestHandler):
        server_version = "observador"

        def _responder(self, codigo: int, corpo: dict) -> None:
            dados = json.dumps(corpo).encode()
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def do_GET(self):  # noqa: N802
            if self.path == "/saude":
                self._responder(200, {"ok": True, "fila": obs.fila.qsize()})
            else:
                self._responder(404, {"erro": "não encontrado"})

        def do_POST(self):  # noqa: N802
            if self.path != "/alerta":
                self._responder(404, {"erro": "não encontrado"})
                return
            recebido = self.headers.get("Authorization", "")
            if not hmac.compare_digest(recebido.encode(), f"Bearer {obs.cfg.token}".encode()):
                self._responder(401, {"erro": "token inválido"})
                return
            tamanho = int(self.headers.get("Content-Length") or 0)
            if tamanho <= 0 or tamanho > LIMITE_CORPO:
                self._responder(400, {"erro": "corpo vazio ou grande demais"})
                return
            try:
                payload = json.loads(self.rfile.read(tamanho))
            except json.JSONDecodeError:
                self._responder(400, {"erro": "JSON inválido"})
                return
            self._responder(202, obs.receber_alerta(payload if isinstance(payload, dict) else {}))

        def log_message(self, formato, *args):  # o registro útil é o JSON das análises
            pass

    return Handler


def servir(obs: Observador, parar: threading.Event) -> ThreadingHTTPServer:
    for alvo in (obs.trabalhar, obs.agendar_boletim):
        threading.Thread(target=alvo, args=(parar,), daemon=True).start()
    return ThreadingHTTPServer(("0.0.0.0", obs.cfg.porta), fazer_handler(obs))
