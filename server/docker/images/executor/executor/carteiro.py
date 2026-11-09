"""Carteiro: sem modelo, olha o repositório da equipe e acorda o sysadmin (webhook do Hermes) quando há novidade."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Callable

from executor.config import Config

API = "https://api.github.com"
PAPEL_SYSADMIN = "papel:sysadmin"


def assinar(segredo: str, ts: str, corpo: bytes) -> str:
    """Assinatura V2 do webhook do Hermes: hex do HMAC-SHA256 de `<ts>.<corpo>`."""
    return hmac.new(segredo.encode("utf-8"), ts.encode("utf-8") + b"." + corpo, hashlib.sha256).hexdigest()


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rotulos(issue: dict) -> set[str]:
    return {r.get("name", "") for r in issue.get("labels") or [] if isinstance(r, dict)}


def _login(obj: dict) -> str:
    return str((obj.get("user") or {}).get("login", ""))


class Carteiro:
    def __init__(self, cfg: Config, abrir: Callable = urllib.request.urlopen, relogio: Callable[[], float] = time.time):
        self.cfg, self._abrir, self._relogio = cfg, abrir, relogio
        self.arquivo = os.path.join(cfg.dados_dir, "carteiro.json")

    # estado ---------------------------------------------------------------
    def _ler_desde(self) -> str | None:
        try:
            with open(self.arquivo, encoding="utf-8") as f:
                desde = json.load(f).get("desde")
        except (OSError, ValueError, AttributeError):
            return None
        return desde if isinstance(desde, str) and desde else None

    def _gravar_desde(self, desde: str) -> None:
        os.makedirs(self.cfg.dados_dir, exist_ok=True)
        tmp = self.arquivo + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"desde": desde}, f)
        os.replace(tmp, self.arquivo)

    # rede -----------------------------------------------------------------
    def _get(self, caminho: str):
        req = urllib.request.Request(f"{API}/repos/{self.cfg.equipe_repo}/{caminho}", headers={
            "Authorization": f"Bearer {self.cfg.github_token_equipe}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"})
        return self._chamar(req, "GitHub")

    def _chamar(self, req: urllib.request.Request, nome: str):
        try:
            with self._abrir(req, timeout=15) as resp:
                status = getattr(resp, "status", 200)
                corpo = resp.read()
        except urllib.error.HTTPError as erro:  # a URL pode carregar segredo: só o código vai ao log
            raise OSError(f"{nome}: HTTP {erro.code}") from None
        except (urllib.error.URLError, OSError, ValueError) as erro:
            raise OSError(f"{nome}: {type(erro).__name__}") from None
        if not 200 <= status < 300:
            raise OSError(f"{nome}: HTTP {status}")
        return corpo

    def _json(self, caminho: str):
        try:
            return json.loads(self._get(caminho).decode("utf-8"))
        except ValueError:
            raise OSError("GitHub: resposta que não é JSON") from None

    # núcleo ---------------------------------------------------------------
    def _itens(self, desde: str) -> list[dict]:
        sysadmin = self.cfg.conta_sysadmin.lower()
        issues = self._json(f"issues?state=all&since={desde}&per_page=50")
        comentarios = self._json(f"issues/comments?since={desde}&per_page=100")
        if not isinstance(issues, list) or not isinstance(comentarios, list):
            raise OSError("GitHub: formato inesperado")
        pagina = {i["number"]: i for i in issues if isinstance(i, dict) and "number" in i}
        itens: dict[tuple[int, str], dict] = {}

        def interessa(issue: dict) -> bool:
            return _login(issue).lower() == sysadmin or PAPEL_SYSADMIN in _rotulos(issue)

        for i in pagina.values():  # (b) issue para o sysadmin, aberta por outro, depois de `desde`
            if ("pull_request" not in i and PAPEL_SYSADMIN in _rotulos(i) and _login(i).lower() != sysadmin
                    and str(i.get("created_at", "")) > desde):
                itens.setdefault((i["number"], "issue"), self._item(i, i, "issue"))
        for c in comentarios:  # (a) comentário de outro numa issue do sysadmin
            if not isinstance(c, dict) or _login(c).lower() == sysadmin:
                continue
            try:
                numero = int(str(c["issue_url"]).rstrip("/").rsplit("/", 1)[1])
            except (KeyError, IndexError, ValueError):
                continue
            issue = pagina.get(numero)
            if issue is None:
                issue = self._json(f"issues/{numero}")
            if not isinstance(issue, dict) or "pull_request" in issue or not interessa(issue):
                continue
            itens.setdefault((numero, "comentario"), self._item(issue, c, "comentario"))
        return list(itens.values())

    @staticmethod
    def _item(issue: dict, origem: dict, tipo: str) -> dict:
        return {"numero": issue["number"], "titulo": str(issue.get("title", ""))[:200],
                "url": origem.get("html_url") or issue.get("html_url", ""), "autor": _login(origem), "tipo": tipo}

    def _acordar(self, itens: list[dict]) -> None:
        corpo = json.dumps({"itens": itens}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ts = str(int(self._relogio()))
        req = urllib.request.Request(self.cfg.webhook_url, data=corpo, method="POST", headers={
            "Content-Type": "application/json", "X-Webhook-Timestamp": ts,
            "X-Webhook-Signature-V2": assinar(self.cfg.webhook_segredo, ts, corpo)})
        self._chamar(req, "webhook")

    def rodar_uma_vez(self) -> int:
        inicio = _iso(self._relogio())  # o novo `desde` é o começo da volta: o que chegar durante ela não se perde
        desde = self._ler_desde()
        if desde is None:
            self._gravar_desde(inicio)
            return 0
        try:
            itens = self._itens(desde)
            if itens:
                self._acordar(itens)
        except OSError as erro:
            print(f"carteiro: {erro}", file=sys.stderr)
            return 0
        self._gravar_desde(inicio)
        return len(itens)

    def rodar(self, parar: threading.Event) -> None:
        while not parar.is_set():
            try:
                self.rodar_uma_vez()
            except Exception as erro:  # noqa: BLE001 — o laço não pode morrer
                print(f"carteiro: {type(erro).__name__}", file=sys.stderr)
            parar.wait(self.cfg.carteiro_intervalo_s)
