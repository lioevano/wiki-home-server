---
name: add-integration
description: Use when the user wants a new cross-cutting integration in the homeserver (e.g. dashboard, notifications, backups, SSO, monitoring) that must be wired into many or all existing applications.
---

# Adicionar uma integração

Fontes: índice `wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md` e catálogo `wiki/docs/02-visao-geral-arquitetura/09-catalogo-aplicacoes.md`.

1. **Definir com o usuário:** id (kebab-case), provedor, regra "Aplica-se a" (sobre colunas existentes do catálogo; se precisar de coluna nova, proponha-a) e se é opcional (`+<id>`).
2. **Pesquisar** a documentação oficial do provedor: como cada consumidor se registra (labels, arquivo de configuração, API).
3. **Escrever a seção** no índice, no formato fixo (tabela Provedor/Aplica-se a/Arquivos/Páginas/Manual; Regras com prefixo novo de 3 letras e pelo menos uma regra **(sobra)**; Ao adicionar; Ao remover; Ao remover o provedor).
4. **Provedor:** se ainda não existe no catálogo, o plano inclui `add-app` do provedor (com `Provê = <id>`) primeiro.
5. **Plano:** aplique a regra a todas as linhas do catálogo e liste, por consumidor, os passos de "Ao adicionar" com arquivos reais (formato de plano da `remove-app`, título "Plano: adicionar integração `<id>`").
6. **Pare e peça aprovação.**
7. Execute via `wiki-first-change`; carregue e siga a skill `audit-integrations` (não substitua por script próprio) com `integração=<id>` até não restar `❌`/`⚠️`; `update-index`; `validate-infra`; commit único.
