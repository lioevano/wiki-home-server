---
name: update-index
description: Use when INDEX.md may be out of date — at the end of any change to the homeserver wiki, server files, skills, application catalog or integration index, or when someone reports that INDEX.md is missing or lists something wrong.
---

# Manter o `INDEX.md`

O `INDEX.md` (raiz) é o mapa do repositório para pessoas e LLMs. **Não há gerador:** esta skill é a única forma de atualizá-lo.

## Quando rodar

- Último passo de `add-app`, `remove-app`, `add-integration`, `remove-integration` e `wiki-first-change`.
- Depois de criar, renomear ou remover página da wiki, arquivo do `server/` ou skill.
- Atualize **só as seções afetadas** pela mudança; reescreva tudo apenas se o arquivo estiver muito defasado.

## Formato (exatamente estas seções, nesta ordem)

```markdown
<!-- Mantido pela skill update-index (.agents/skills/update-index/SKILL.md) — edite por ela -->
# Índice do repositório

Mapa do repositório. Caminhos de arquivos do server são relativos a `server/`; páginas, a `wiki/docs/`.

## Agentes e skills
| Skill | Quando usar | Caminho |

## Aplicações
| Aplicação | Stack / VM | Integrações ativas | Página |

## Integrações
| Integração | Provedor | Aplica-se a | Seção |

## Páginas da wiki
| Página | Título | Descrição |

## Arquivos do server
| Arquivo | Tipo | Página que documenta |
```

## Fontes de cada seção

| Seção | Fonte | Regra |
|---|---|---|
| Agentes e skills | `.agents/skills/*/SKILL.md` | "Quando usar" = resumo em português da `description` |
| Aplicações | catálogo (`02-visao-geral-arquitetura/09-catalogo-aplicacoes.md`) | Integrações ativas = ids cuja "Aplica-se a" é verdadeira para a aplicação (respeitando Ajustes; o provedor não conta como consumidor); Página = a da coluna Página |
| Integrações | índice (`02-visao-geral-arquitetura/10-indice-integracoes.md`) | Seção = link `wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md#<id>` |
| Páginas da wiki | `wiki/docs/**/*.md` | Título = primeiro `# `; Descrição = `description` do front-matter |
| Arquivos do server | `git ls-files server/` (exceto `CLAUDE.md`/`AGENTS.md`) | Tipo: `inventario`, `playbook`, `role-tasks`, `role-handlers`, `role-defaults`, `role-template`, `template`, `stack`, `env-template`, `script`, `outro`; Página = página(s) da wiki que citam o caminho ou definem seu bloco literal |

## Regras

- Ordem alfabética dentro de cada tabela (por skill, aplicação, id, caminho).
- **Nunca** liste caminho, página, skill ou aplicação sem confirmar que existe (`ls`/`git ls-files`).
- Arquivo do server sem página que o cite: escreva `—` e avise o usuário (é um `ORPHAN` do `dev.py check`).
- Valor `?` no catálogo: copie `?` e avise.
- Termine conferindo: toda skill, aplicação, integração, página e arquivo versionado do server aparece exatamente uma vez na sua seção.
