---
name: wiki-first-change
description: Use when the user asks to change, add, remove or fix anything in the homeserver infrastructure (Ansible, Docker stacks, scripts, network, VMs) or in the wiki that describes it.
---

# Mudança "wiki primeiro"

A wiki (`wiki/docs/`) é a fonte da verdade; o `server/` só muda para refleti-la.

## Sequência

0. **Aplicação ou integração inteira?** Adicionar/remover aplicação → skill `add-app`/`remove-app`; integração transversal → `add-integration`/`remove-integration`. Elas usam esta skill para executar.
1. **Localize** o assunto no `INDEX.md` (aplicações, integrações, páginas, arquivos) e, se envolver uma aplicação, a linha dela no catálogo (`wiki/docs/02-visao-geral-arquitetura/09-catalogo-aplicacoes.md`) e as integrações que se aplicam a ela (`10-indice-integracoes.md`). Só busque no disco se o índice não responder.
2. **Registre a linha de base**: `python tools/dev.py check` e anote os erros que já existiam (não são seus).
3. **Edite a wiki**:
   - arquivo com bloco literal (`title="<caminho>"`) → altere o bloco; ele é o conteúdo exato do arquivo;
   - arquivo estrutural (sem bloco) → descreva a mudança na página e cite o caminho completo em código inline.
   Use a skill `wiki-page-authoring` para página nova.
4. `python tools/dev.py check` → só devem aparecer as divergências que você criou de propósito.
5. `python tools/dev.py sync` (dry-run), leia o diff, depois `python tools/dev.py sync --yes`.
6. Edite à mão **apenas** os arquivos estruturais que a página agora descreve.
7. Valide com a skill `validate-infra`.
8. Skill `update-index` (uma vez, no fim) e commit único: wiki + server + `INDEX.md`.

## Erros comuns

| Erro | Correção |
|---|---|
| Editar o server e "documentar depois" | A página vem antes; o `check` é o juiz. |
| Rodar `index` no início | Só no fim: ele reflete o estado final. |
| Dois blocos literais diferentes para o mesmo arquivo | Um vira `title="Trecho: ..."` (`LIT-DUP`). |
| Corrigir erros pré-existentes no meio da tarefa | Relate-os; corrija só se o usuário pedir. |
| Rodar `ansible-playbook`/`docker compose up`/`git push` | Peça confirmação; esta skill termina no commit local. |
