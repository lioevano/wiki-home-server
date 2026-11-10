# wiki/ — convenções

A wiki é a **fonte da verdade** do projeto. Siga estas regras ao criar ou editar páginas
(skill: `wiki-page-authoring`).

## Estrutura

- Seções numeradas em `docs/`: `01-manual-implementacao/`, `02-visao-geral-arquitetura/`,
  `03-guias-sustentacao/`, `04-manutencao-recuperacao/`, mais `05-referencia-rapida.md` e `index.md`.
- Arquivos `NN-nome-em-kebab.md`, numerados na ordem de leitura dentro da seção; cada seção tem `index.md`.
- **Toda página nova entra no `nav` do `mkdocs.yml`** (o `check` acusa `NAV` se faltar).
- **Página renomeada ganha redirecionamento:** acrescente o par `antigo: novo` em `plugins → redirects → redirect_maps` do `mkdocs.yml`, para o endereço publicado não quebrar (`test_convencoes.py` confere). No manual, o `nav` segue a numeração de `00` a `19`.

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
- **Diagramas legíveis:** o site encolhe o diagrama para a coluna do artigo (~690 px), então:
    - `flowchart TB` (de cima para baixo), no máximo 3 ou 4 caixas lado a lado; um diagrama grande vira dois;
    - rótulos curtos e entre aspas (`a["VM (opcional)"]`): parênteses e dois-pontos sem aspas quebram o Mermaid 11;
    - sequência com até 4 participantes, nomes e mensagens curtos, e `%%{init: {"sequence": {"actorMargin": 30, "width": 120}}}%%` na primeira linha;
    - sem `style` nem cores fixas (somem no modo escuro) e sem `{{ variáveis }}` (use os IPs de exemplo);
    - `python tools/dev.py diagramas` renderiza todos e falha com diagrama quebrado ou com escala abaixo de 0,75 (o CI roda o mesmo).
- Tom em português, direto, explicando o porquê das escolhas.

## Validar

`python tools/dev.py build` (estrito) e `python tools/dev.py check` — ambos sem erros antes do commit.
