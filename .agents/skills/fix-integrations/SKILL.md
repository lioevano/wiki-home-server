---
name: fix-integrations
description: Use when the user asks to fix, correct or generate missing integration wiring or environment variables in the homeserver, or when audit-integrations reports ❌ or ⚠️ findings that should be resolved.
---

# Corrigir integrações e variáveis

Fontes: índice `wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md` (regras, passos e **Origem dos valores**) e catálogo `wiki/docs/02-visao-geral-arquitetura/09-catalogo-aplicacoes.md`.

## 1. Auditar

Carregue e siga a skill `audit-integrations` (não substitua por script próprio) no escopo pedido: tudo, `app=<id>`, `integração=<id>` ou uma stack (= as aplicações dela).

## 2. Classificar cada achado

| Achado | Tipo | Correção |
|---|---|---|
| `❌` de regra não-(sobra) | mecânico | passos de **"Ao adicionar (por consumidor)"** da integração, concretizados |
| `❌ VAR-1` | mecânico | variável no bloco literal do `.env.template` (página 00) |
| `❌ VAR-2` | mecânico | emitir no playbook da stack seguindo **Origem dos valores**; nome divergente → alinhar ao nome usado no compose (ajustando quem emite); emissão condicional → emissão direta |
| `⚠️` (sobra) com dono claro (job/variável/regra sem aplicação) | decisão | perguntar: remover ou catalogar |
| `⚠️ ROT-3` em aplicação `interna` | decisão | perguntar: remover o router ou mudar Exposição no catálogo |
| `❌ LOG-2` | decisão | perguntar: subir Promtail na VM ou `-logs` em Ajustes |
| segredo sem chave no vault | decisão | propor `snake_case` e confirmar |
| `?` no catálogo | decisão | perguntar antes de tudo |

Não corrija nada classificado como **decisão** sem a resposta do usuário.

## 3. Plano

```markdown
### Plano: corrigir integrações — <escopo>
| # | Regra | Aplicação | Arquivo ou página | Ação | Origem do valor (variáveis) |
|---|---|---|---|---|---|
### Decisões necessárias
- ...
### Passos manuais
- preencher segredos novos no vault real (`ansible-vault edit`), rodar o playbook da stack, redeploy no Portainer
```

Regras do plano:
- Blocos literais mudam **na wiki** (ex.: `vault.yml.example` na página 01, `.env.template` na página 00, roles com bloco literal); arquivos estruturais (playbooks sem bloco literal) mudam direto, citados na página da stack.
- Segredo: placeholder no `vault.yml.example`; o playbook carrega o vault e grava o `.env` com `mode: '0600'`.
- Nunca escrever valor real de segredo em nenhum arquivo.
- Passos manuais (preencher o vault real, rodar playbook com `--check` antes, redeploy no Portainer) ficam **na página da stack na wiki**, numa subseção "Passos manuais ao mudar variáveis ou segredos" — não só no relatório.

## 4. Aprovação

**Pare e peça aprovação** do plano e das decisões. Só continue com um "sim" explícito.

## 5. Executar, verificar e fechar

1. `wiki-first-change` (wiki → `dev.py check` → `dev.py sync` → `--yes` → arquivos estruturais).
2. Rode de novo a skill `audit-integrations` (não substitua por script próprio) nas aplicações afetadas, com **todas** as integrações: os achados corrigidos devem sumir e nenhum novo pode surgir. Repita até zerar o que foi aprovado; o que ficou pendente por decisão continua no relatório.
3. Se um item corrigido estava em **Pendências da auditoria inicial** (índice de integrações), atualize ou retire a linha.
4. `update-index`, `validate-infra`, commit único. Relate: o que foi corrigido, decisões tomadas, passos manuais.
