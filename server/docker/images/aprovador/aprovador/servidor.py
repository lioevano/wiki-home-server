"""HTTP do aprovador. API (token do ops): criar, consultar e usar pedidos. Tela (só pelo Traefik, que injeta
X-Aprovador-Chave e o Remote-User do Authelia): lista e decide."""
from __future__ import annotations

import hmac
import html
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import Config
from .pedidos import Conflito, Registro
from .telegram import Telegram

LIMITE_CORPO = 64_000
ROTULO = {"pendente": "⏳ pendente", "aprovado": "✅ aprovado", "recusado": "❌ recusado",
          "expirado": "⌛ expirado", "usado": "✔️ usado"}


def _igual(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def pagina(pedidos: list[dict], usuario: str, aviso: str = "", validade_min: int = 30) -> str:
    def linha(p: dict) -> str:
        quando = time.strftime("%d/%m %H:%M", time.localtime(p["criado"]))
        args = html.escape(json.dumps(p["argumentos"], ensure_ascii=False))
        acoes = ""
        if p["estado"] == "pendente":
            acoes = (f'<form method="post" action="/decidir"><input type="hidden" name="id" value="{p["id"]}">'
                     '<button name="decisao" value="aprovar">Aprovar</button> '
                     '<button name="decisao" value="recusar">Recusar</button></form>')
        elif p.get("decidido_por"):
            acoes = html.escape(p["decidido_por"])
        return (f"<tr><td><code>{p['id']}</code><br>{quando}</td><td>{html.escape(p['cliente'])}</td>"
                f"<td><b>{html.escape(p['acao'])}</b> em <b>{html.escape(p['alvo'])}</b><br><code>{args}</code>"
                f"<br>{html.escape(p.get('descricao', ''))}</td><td>{ROTULO.get(p['estado'], p['estado'])}</td>"
                f"<td>{acoes}</td></tr>")
    pendentes = [p for p in pedidos if p["estado"] == "pendente"]
    outros = [p for p in pedidos if p["estado"] != "pendente"][:30]
    corpo = "".join(linha(p) for p in pendentes + outros) or '<tr><td colspan="5">Nenhum pedido.</td></tr>'
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Aprovações</title>
<style>body{{font-family:system-ui,sans-serif;margin:16px;background:#fafafa;color:#222}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}}
code{{word-break:break-all}}button{{padding:6px 12px;margin:2px}}.aviso{{background:#fff3cd;padding:8px}}
@media (prefers-color-scheme:dark){{body{{background:#1b1b1b;color:#eee}}td,th{{border-color:#444}}.aviso{{background:#4a3d00}}}}</style>
</head><body><h1>Aprovações dos agentes</h1><p>{html.escape(usuario)} · {len(pendentes)} pendente(s) ·
pedidos vencem em {validade_min} min</p>{f'<p class="aviso">{html.escape(aviso)}</p>' if aviso else ''}
<table><tr><th>Pedido</th><th>Quem</th><th>Ação</th><th>Estado</th><th></th></tr>{corpo}</table></body></html>"""


def fazer_handler(cfg: Config, registro: Registro, telegram: Telegram | None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "aprovador"
        timeout = 10

        def _enviar(self, codigo: int, corpo: str, tipo: str = "application/json", extra: dict | None = None) -> None:
            dados = corpo.encode()
            self.send_response(codigo)
            self.send_header("Content-Type", f"{tipo}; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(dados)

        def _json(self, codigo: int, obj: dict) -> None:
            self._enviar(codigo, json.dumps(obj, ensure_ascii=False))

        def _corpo(self) -> bytes | None:
            try:
                tamanho = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                tamanho = -1
            if tamanho < 0 or tamanho > LIMITE_CORPO:
                return None
            return self.rfile.read(tamanho)

        def _api_ok(self) -> bool:
            if _igual(self.headers.get("Authorization", ""), f"Bearer {cfg.token}"):
                return True
            self._json(401, {"erro": "token inválido"})
            return False

        def _usuario_da_tela(self) -> str | None:
            """Só o Traefik conhece a chave do proxy; o Remote-User vem do forward-auth do Authelia."""
            usuario = self.headers.get("Remote-User", "")
            if _igual(self.headers.get("X-Aprovador-Chave", ""), cfg.chave_proxy) and usuario:
                return usuario
            self._enviar(403, "acesso só pela tela (aprovacoes.)", "text/plain")
            return None

        def do_GET(self):  # noqa: N802
            if self.path == "/saude":
                return self._json(200, {"ok": True})
            if self.path.startswith("/api/pedidos/"):
                if not self._api_ok():
                    return
                p = registro.obter(self.path.rsplit("/", 1)[1])
                return self._json(200, p) if p else self._json(404, {"erro": "pedido não encontrado"})
            if self.path == "/" or self.path.startswith("/?"):
                usuario = self._usuario_da_tela()
                if usuario is None:
                    return
                aviso = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("aviso", [""])[0]
                return self._enviar(200, pagina(registro.listar(), usuario, aviso, cfg.validade_s // 60), "text/html")
            self._json(404, {"erro": "não encontrado"})

        def do_POST(self):  # noqa: N802
            corpo = self._corpo()
            if corpo is None:
                return self._json(400, {"erro": "corpo inválido"})
            if self.path == "/decidir":
                return self._decidir(corpo)
            if not self.path.startswith("/api/"):
                return self._json(404, {"erro": "não encontrado"})
            if not self._api_ok():
                return None
            try:
                dados = json.loads(corpo or b"{}")
                if not isinstance(dados, dict):
                    raise ValueError
            except ValueError:
                return self._json(400, {"erro": "JSON inválido"})
            if self.path == "/api/pedidos":
                faltando = [c for c in ("cliente", "acao", "alvo") if not isinstance(dados.get(c), str) or not dados[c]]
                if faltando or not isinstance(dados.get("argumentos", {}), dict):
                    return self._json(400, {"erro": "campos obrigatórios: cliente, acao, alvo, argumentos"})
                try:
                    p = registro.criar(dados["cliente"], dados["acao"], dados["alvo"], dados.get("argumentos", {}),
                                       str(dados.get("descricao", "")))
                except Conflito as erro:
                    return self._json(429, {"erro": str(erro)})
                if telegram:
                    telegram.avisar(p)
                return self._json(201, {"id": p["id"], "estado": p["estado"], "validade_min": cfg.validade_s // 60})
            if self.path.startswith("/api/pedidos/") and self.path.endswith("/usar"):
                pid = self.path.split("/")[3]
                try:
                    p = registro.usar(pid, str(dados.get("cliente", "")), str(dados.get("acao", "")),
                                      str(dados.get("alvo", "")), dados.get("argumentos", {}))
                except Conflito as erro:
                    return self._json(409, {"erro": str(erro)})
                if telegram:
                    telegram.atualizar(p)
                return self._json(200, {"id": pid, "estado": p["estado"]})
            self._json(404, {"erro": "não encontrado"})

        def _decidir(self, corpo: bytes) -> None:
            usuario = self._usuario_da_tela()
            if usuario is None:
                return
            # Outra página aberta no navegador não decide por você: o POST precisa vir da própria tela.
            if self.headers.get("Origin", "") != cfg.url_publica:
                return self._enviar(403, "origem inválida", "text/plain")
            form = urllib.parse.parse_qs(corpo.decode("utf-8", "replace"))
            pid, decisao = form.get("id", [""])[0], form.get("decisao", [""])[0]
            try:
                p = registro.decidir(pid, decisao == "aprovar", f"tela:{usuario}")
                aviso = f"Pedido {pid} {p['estado']}."
                if telegram:
                    telegram.atualizar(p)
            except Conflito as erro:
                aviso = f"Pedido {pid}: {erro}."
            self._enviar(303, "", "text/plain", {"Location": "/?aviso=" + urllib.parse.quote(aviso)})

        def log_message(self, formato, *args):  # o registro útil é o JSON dos eventos
            pass

    return Handler


def servir(cfg: Config, registro: Registro, telegram: Telegram | None, parar: threading.Event) -> ThreadingHTTPServer:
    if telegram:
        threading.Thread(target=telegram.rodar, args=(parar,), daemon=True).start()
    return ThreadingHTTPServer(("0.0.0.0", cfg.porta), fazer_handler(cfg, registro, telegram))
