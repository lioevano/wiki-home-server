---
name: wiki-page-authoring
description: Use when creating, renaming, splitting or substantially editing a page of the homeserver MkDocs wiki under wiki/docs.
---

# Escrever páginas da wiki

Convenções completas em `wiki/AGENTS.md`. Checklist:

1. **Local e nome** — seção certa (`01-manual-implementacao` passo a passo, `02-visao-geral-arquitetura` conceitos, `03-guias-sustentacao` como fazer, `04-manutencao-recuperacao` operação); arquivo `NN-nome-kebab.md` com o próximo número.
2. **Front-matter** — `description: "..."` (≤160 caracteres, factual) e um único `# Título`.
3. **`nav`** — adicione a entrada em `wiki/mkdocs.yml` na posição da numeração; renomeou → atualize `nav` e todos os links que apontavam para a página (`grep -rn 'nome-antigo' wiki/docs`).
4. **Blocos de código** — arquivo inteiro do server: `title="<caminho relativo a server/>"`; parte: `title="Trecho: ..."`; exemplo hipotético: `title="Exemplo: ..."`.
5. **Citações** — caminhos do server sempre completos em código inline (`` `docker/stacks/apps/docker-compose.yml` ``).
6. **Links** — relativos, com âncora se preciso; nada de URL absoluta para páginas da própria wiki.
7. **Validar** — `python tools/dev.py build` (estrito: qualquer aviso falha) e `python tools/dev.py check` sem `NAV`, `LINK`, `DESC` novos.
