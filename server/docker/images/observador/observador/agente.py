"""O laço do agente: o LLM pede ferramentas da rota de leitura, o observador as chama pelo hub e devolve o
resultado, até o LLM responder em texto ou o limite de passos e de tempo chegar."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable

NOME_VALIDO = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")  # exigência da API de ferramentas
FECHAR = ("Limite de passos ou de tempo atingido. Responda agora, no formato pedido, só com o que já sabe; "
          "diga o que ficou sem verificar.")


@dataclass
class Resultado:
    texto: str
    passos: int = 0
    ferramentas: list[str] = field(default_factory=list)
    uso: dict = field(default_factory=dict)


def ferramentas_para_llm(ferramentas_mcp: list[dict], excluir: tuple = ()) -> list[dict]:
    convertidas = []
    for f in ferramentas_mcp:
        nome = f.get("name", "")
        if not NOME_VALIDO.match(nome) or nome.startswith(excluir):
            continue
        esquema = f.get("inputSchema") or {"type": "object", "properties": {}}
        convertidas.append({"type": "function", "function": {
            "name": nome, "description": (f.get("description") or "")[:1024], "parameters": esquema}})
    return convertidas


def cortar(texto: str, limite: int) -> str:
    if len(texto) <= limite:
        return texto
    return texto[:limite] + f"\n[… cortado: {len(texto) - limite} caracteres a mais]"


def _somar(uso: dict, novo: dict) -> None:
    for chave in ("prompt_tokens", "completion_tokens", "total_tokens"):
        uso[chave] = uso.get(chave, 0) + int(novo.get(chave) or 0)


def investigar(sistema: str, tarefa: str, mcp, llm, max_passos: int, limite_saida: int, tempo_max_s: float,
               metadata: dict | None = None, relogio: Callable[[], float] = time.monotonic,
               excluir: tuple = ()) -> Resultado:
    """tempo_max_s é conferido antes de cada chamada ao LLM: uma chamada em andamento termina (teto aproximado)."""
    inicio = relogio()
    mcp.iniciar()
    ferramentas = ferramentas_para_llm(mcp.ferramentas(), excluir)
    mensagens = [{"role": "system", "content": sistema}, {"role": "user", "content": tarefa}]
    res = Resultado(texto="")
    for _ in range(max_passos):
        if relogio() - inicio > tempo_max_s:
            break
        msg, uso = llm.completar(mensagens, ferramentas, metadata)
        _somar(res.uso, uso)
        chamadas = msg.get("tool_calls") or []
        if not chamadas:
            res.texto = (msg.get("content") or "").strip()
            return res
        res.passos += 1
        mensagens.append({"role": "assistant", "content": msg.get("content"), "tool_calls": chamadas})
        for chamada in chamadas:
            nome = chamada.get("function", {}).get("name", "")
            res.ferramentas.append(nome)
            try:
                argumentos = json.loads(chamada.get("function", {}).get("arguments") or "{}")
                saida = mcp.chamar(nome, argumentos if isinstance(argumentos, dict) else {})
            except json.JSONDecodeError:
                saida = "ERRO: argumentos não são JSON válido."
            except Exception as erro:  # uma ferramenta que falha vira informação para o LLM, não queda
                saida = f"ERRO ao chamar {nome}: {erro}"
            mensagens.append({"role": "tool", "tool_call_id": chamada.get("id", ""),
                              "content": cortar(saida, limite_saida)})
    mensagens.append({"role": "user", "content": FECHAR})
    msg, uso = llm.completar(mensagens, ferramentas, metadata, escolha="none")
    _somar(res.uso, uso)
    res.texto = (msg.get("content") or "").strip()
    return res
