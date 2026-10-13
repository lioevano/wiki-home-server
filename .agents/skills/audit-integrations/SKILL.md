---
name: audit-integrations
description: Use when asked to verify or audit the homeserver integrations (Traefik, Authelia, Cloudflare, Prometheus, logs, data, variables, LLM, documentation), before or after adding/removing an app or integration, or when the application catalog and the server files may disagree.
---

# Auditoria de integrações

Compara **intenção** (catálogo) com **realidade** (arquivos) usando as regras do índice. **Não edita nada.**

- Catálogo: `wiki/docs/02-visao-geral-arquitetura/09-catalogo-aplicacoes.md`
- Índice de integrações: `wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md`

## Escopo

Pergunte ou deduza do pedido: **todas** as aplicações (padrão), **uma aplicação** (`app=<id>`) ou **uma integração** (`integração=<id>`). As regras **(sobra)** sempre varrem o repositório inteiro, qualquer que seja o escopo.

## Procedimento

1. Leia o índice inteiro (legenda + todas as seções) e o catálogo inteiro.
2. Para cada par aplicação × integração no escopo, decida a célula:
   - aplicação é a **provedora** da integração → `—`, salvo quando uma regra da seção a avalia explicitamente pelo nome (hoje AUT-3 para `authelia` e MET-1 para `prometheus`) — então avalie normalmente;
   - "Aplica-se a" falso, ou Ajustes tem `-<id>`, ou integração `+<id>` sem `+<id>` em Ajustes → `—`;
   - depende de coluna com `?` → `?`;
   - caso contrário, avalie **cada regra não-(sobra)** buscando a *Evidência* indicada. Todas ok → `✅`; regra falhou → `❌ <REGRA>`; só falta passo manual → `✋`.
3. Rode todas as regras **(sobra)** (`ROT-3`, `AUT-4`, `MET-2`, `VAR-3`, `DOC-4`, `DOC-5`) no repositório inteiro. Cada achado vira `⚠️ <REGRA>` na linha da aplicação afetada, ou na linha `(fora do catálogo)` quando não houver aplicação.
4. Aplique as convenções da legenda do índice: serviço principal = primeiro da coluna Serviços; `ansible:<role>` busca evidência no role; regra curinga do Authelia satisfaz AUT-2.
5. Não "corrija mentalmente": se a evidência não está onde a regra manda, é `❌`.

## Saída (exatamente nesta forma)

```markdown
## Auditoria de integrações — <escopo> — <data>

| Aplicação | roteamento | autenticacao | acesso-externo | metricas | logs | dados | variaveis | llm | documentacao |
|---|---|---|---|---|---|---|---|---|---|
| <id> | ✅ | ❌ AUT-1 | … |
| (fora do catálogo) | ⚠️ ROT-3 | … |

### Achados
| # | Status | Regra | Aplicação | Evidência (arquivo:linha) | Ação sugerida |
|---|---|---|---|---|---|

### Pendências de decisão
- valores `?` do catálogo e o que cada um bloqueia

### Fora das regras
- (opcional) problemas vistos que nenhuma regra cobre — não entram na tabela
```

- Uma coluna por integração **que existe no índice no momento**, na ordem do índice — as colunas do exemplo são ilustrativas; integração removida sai, integração nova entra.
- Status só destes: `✅` · `❌ <REGRA>` · `⚠️ <REGRA>` · `✋` · `—` · `?`. Várias regras na mesma célula: `❌ VAR-1, VAR-2`.
- Todo `❌`/`⚠️` tem linha em **Achados** com caminho relativo à raiz do repositório e número de linha.

## Erros comuns

| Erro | Correção |
|---|---|
| Acusar banco/cache por não ter router | Só o serviço principal recebe roteamento/autenticação. |
| Marcar provedor como consumidor | Célula do provedor é `—`. |
| Ignorar routers por arquivo | ROT-3/AUT-1 também olham `traefik-config/templates/*.yml.j2`. |
| Editar arquivos para "consertar" | Esta skill só relata; mudanças usam `add-app`/`remove-app`/`wiki-first-change`. |
