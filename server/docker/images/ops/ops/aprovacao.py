"""Cliente do aprovador (página 16): ações de clientes autônomos (agentes, assistente) só rodam com um pedido
aprovado pelo Léo, no Telegram ou na tela aprovacoes. Sem aprovador configurado, recusa (falha fechada)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .politica import Recusado


class Aprovador:
    def __init__(self, url: str, token: str, abrir=urllib.request.urlopen):
        self.url, self.token, self._abrir = url.rstrip("/"), token, abrir

    def _post(self, caminho: str, corpo: dict) -> tuple[int, dict]:
        if not self.url or not self.token:
            raise Recusado("esta ação exige aprovação humana, e o aprovador não está configurado")
        req = urllib.request.Request(self.url + caminho, data=json.dumps(corpo).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {self.token}",
                                              "Content-Type": "application/json"})
        try:
            with self._abrir(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as erro:
            try:
                return erro.code, json.loads(erro.read() or b"{}")
            except ValueError:
                return erro.code, {}
        except (urllib.error.URLError, OSError, ValueError) as erro:
            raise Recusado(f"aprovador inalcançável ({type(erro).__name__}); a ação não foi feita") from None

    def pedir(self, cliente: str, acao: str, alvo: str, argumentos: dict, descricao: str) -> dict:
        codigo, dados = self._post("/api/pedidos", {"cliente": cliente, "acao": acao, "alvo": alvo,
                                                    "argumentos": argumentos, "descricao": descricao})
        if codigo != 201 or "id" not in dados:
            raise Recusado(f"o aprovador recusou o pedido ({codigo}: {dados.get('erro', '')})")
        return dados

    def usar(self, pedido: str, cliente: str, acao: str, alvo: str, argumentos: dict) -> None:
        if not pedido.isalnum() or len(pedido) > 32:
            raise Recusado("aprovacao_id inválido")
        codigo, dados = self._post(f"/api/pedidos/{pedido}/usar", {"cliente": cliente, "acao": acao, "alvo": alvo,
                                                                   "argumentos": argumentos})
        if codigo != 200:
            raise Recusado(f"pedido {pedido} não autoriza esta ação: {dados.get('erro', codigo)}")
