# wiki/ — convenções

A wiki é a **fonte da verdade** do projeto. Siga estas regras ao criar ou editar páginas
(skill: `wiki-page-authoring`).

## Estrutura

- Seções numeradas em `docs/`: `01-manual-implementacao/`, `02-visao-geral-arquitetura/`,
  `03-guias-sustentacao/`, `04-manutencao-recuperacao/`, mais `05-referencia-rapida.md` e `index.md`.
- Arquivos `NN-nome-em-kebab.md`, numerados na ordem de leitura dentro da seção; cada seção tem `index.md`.
- **Toda página nova entra no `nav` do `mkdocs.yml`** (o `check` acusa `NAV` se faltar).

## Front-matter obrigatório

```markdown
---
description: "Uma frase factual (até 160 caracteres) sobre o que a página ensina."
---

# Título da Página
```

A `description` vira meta description do site e alimenta o `INDEX.md`.

## Blocos de código

- **Literal** (verdade exata de um arquivo do server): `title="ansible/..."`, `title="docker/..."` ou
  `title="scripts/..."`, caminho relativo a `server/`. O conteúdo do bloco é o arquivo inteiro.
- **Ilustrativo**: sem `title`, ou `title="Exemplo: ..."` / `title="Trecho: ..."` para mostrar parte de um arquivo.
- Um mesmo arquivo só pode ter **um** bloco literal (ou vários idênticos) — senão `LIT-DUP`.
- Ao citar arquivos no texto, use o caminho completo relativo a `server/` em código inline
  (`` `ansible/playbooks/vm-deploy.yml` ``) — é assim que o `check` sabe que o arquivo está documentado.

## Links e estilo

- Links relativos entre páginas (`../03-guias-sustentacao/01-adicionando-novo-servico-docker.md`); âncoras permitidas.
- Admonitions do Material (`!!! tip`, `!!! warning`, `!!! info`), diagramas em ```` ```mermaid ````.
- Tom em português, direto, explicando o porquê das escolhas.

## Validar

`python tools/dev.py build` (estrito) e `python tools/dev.py check` — ambos sem erros antes do commit.
