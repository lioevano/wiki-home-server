"""Portão de aprovação: nenhuma ação que muda a casa roda sem um pedido aprovado pelo Léo no Telegram.

1ª chamada (sem aprovacao_id): cria o pedido, avisa o Léo e devolve o id. 2ª chamada, com o id: só executa se o
pedido estiver aprovado, no prazo, e for desta mesma ação, alvo e argumentos; vale uma vez."""
from __future__ import annotations

from typing import Callable

from aprovador.pedidos import Conflito, Registro
from aprovador.telegram import Telegram
from ops.politica import Recusado

CLIENTE = "sysadmin"


class Portao:
    def __init__(self, registro: Registro, telegram: Telegram):
        self.registro, self.telegram = registro, telegram

    def executar(self, acao: str, alvo: str, argumentos: dict, aprovacao_id: str | None, descricao: str,
                 fazer: Callable[[], str]) -> str:
        try:
            if not aprovacao_id:
                p = self.registro.criar(CLIENTE, acao, alvo, argumentos, descricao)
            else:
                self.registro.usar(aprovacao_id, CLIENTE, acao, alvo, argumentos)
        except Conflito as erro:
            raise Recusado(str(erro)) from None
        if aprovacao_id:
            return fazer()
        self.telegram.avisar(p)
        return (f"Aguardando aprovação humana: pedido {p['id']}. O Léo decide pelos botões do Telegram "
                f"(vale {self.registro.validade_s // 60} min; não há tela web). Não fique repetindo a chamada: "
                f"espere o Léo dizer que aprovou e então chame esta mesma ferramenta com os mesmos argumentos e "
                f"aprovacao_id=\"{p['id']}\". Se for recusado, não tente de novo.")
