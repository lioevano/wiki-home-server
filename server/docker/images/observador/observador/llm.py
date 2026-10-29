"""Cliente do LiteLLM (API compatível com a da OpenAI): /v1/chat/completions com ferramentas."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable

Abrir = Callable[..., object]


class ErroLLM(RuntimeError):
    pass


class ClienteLLM:
    def __init__(self, url: str, chave: str, modelo: str, timeout: float = 90,
                 abrir: Abrir = urllib.request.urlopen):
        self.url = url.rstrip("/") + "/v1/chat/completions"
        self.chave, self.modelo, self.timeout, self._abrir = chave, modelo, timeout, abrir

    def completar(self, mensagens: list[dict], ferramentas: list[dict] | None = None,
                  metadata: dict | None = None, escolha: str = "auto") -> tuple[dict, dict]:
        """Devolve (mensagem do assistente, uso de tokens). escolha="none" proíbe novas chamadas de ferramenta
        mas mantém as definições (a Anthropic recusa histórico com ferramentas sem as definições)."""
        corpo = {"model": self.modelo, "messages": mensagens, "temperature": 0.2, "max_tokens": 1500,
                 "user": "observador"}
        if ferramentas:
            corpo["tools"] = ferramentas
            corpo["tool_choice"] = escolha
        if metadata:
            corpo["metadata"] = metadata  # o LiteLLM repassa ao Langfuse (trace_name, tags, session_id)
        req = urllib.request.Request(self.url, data=json.dumps(corpo).encode(), method="POST", headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {self.chave}"})
        try:
            with self._abrir(req, timeout=self.timeout) as resp:
                dados = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as erro:
            detalhe = erro.read().decode("utf-8", "replace")[:300] if hasattr(erro, "read") else ""
            raise ErroLLM(f"LiteLLM respondeu {erro.code}: {detalhe}") from erro
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as erro:
            raise ErroLLM(f"LiteLLM inalcançável: {erro}") from erro
        try:
            return dados["choices"][0]["message"], dados.get("usage", {})
        except (KeyError, IndexError, TypeError) as erro:
            raise ErroLLM(f"resposta inesperada do LiteLLM: {str(dados)[:300]}") from erro
