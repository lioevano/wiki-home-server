---
name: remove-integration
description: Use when the user wants to remove a cross-cutting integration from the homeserver, or when remove-app stops because the application being removed provides an integration to other applications.
---

# Remover uma integração

Fontes: índice `wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md` e catálogo `wiki/docs/02-visao-geral-arquitetura/09-catalogo-aplicacoes.md`.

1. Leia a seção `## <id>` e liste os **consumidores atuais** (aplicações em que "Aplica-se a" é verdadeira).
2. **Plano** (formato da `remove-app`, título "Plano: remover integração `<id>`"):
   - para cada consumidor, os passos de "Ao remover (por consumidor)" com arquivos reais;
   - os passos de "Ao remover o provedor" — se a seção disser **bloquear**, pare e explique o risco (ex.: aplicações protegidas ficariam sem login) e só prossiga com a alternativa que o usuário escolher;
   - catálogo: ajustar colunas que perdem sentido (ex.: Métricas = não em todas, ao remover `metricas`) e tirar o id da coluna Provê;
   - índice: remover a seção `## <id>` e qualquer `+<id>`/`-<id>` em Ajustes;
   - se o pedido veio de `remove-app` do provedor, ao final incluir a remoção do provedor (passos da `remove-app`).
3. **Pare e peça aprovação.**
4. Execute via `wiki-first-change`; carregue e siga a skill `audit-integrations` — não substitua por script próprio — (regras sobra de todas as integrações) sem resíduo do `<id>`; `grep -rIn` pelos arquivos/nomes próprios da integração; `update-index`; `validate-infra`; commit único.
