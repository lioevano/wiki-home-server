---
name: sync-wiki-server
description: Use when `python tools/dev.py check` reports errors or warnings (LIT-DIFF, LIT-MISSING, LIT-DUP, REF-MISSING, ORPHAN, UNMARKED, DESC, LINK, NAV, VAULT, EOL) or the wiki and server/ seem out of sync.
---

# Triagem do `wikisync check`

Rode `python tools/dev.py check --json` e trate cada achado pelo código:

| Código | Pergunta | Ação |
|---|---|---|
| `LIT-DIFF` | A wiki está certa? | Sim → `dev.py sync --path <arq>` (dry-run) e `--yes`. Não (o server evoluiu) → copie o conteúdo do server para o bloco da wiki, ajuste o texto ao redor, depois `sync`. |
| `LIT-MISSING` | O arquivo deve existir? | Sim → `sync --path <arq> --yes`. Não → o bloco vira `title="Exemplo: ..."`. |
| `LIT-DUP` | Qual bloco é o arquivo inteiro? | Os parciais viram `title="Trecho: <caminho> (...)"`. |
| `REF-MISSING` | O caminho citado é real? | Criar (via wiki), corrigir o texto, ou — se for placeholder/arquivo de runtime — `ignore_paths` em `tools/wikisync/config.yml` com comentário. |
| `ORPHAN` (aviso) | O arquivo ainda é usado? | Documente na página certa (caminho completo em código inline) ou remova-o junto com a explicação na wiki. Excepcional: `ignore_orphans` com motivo. |
| `UNMARKED` (aviso) | O bloco é o arquivo inteiro? | Sim → `title="<caminho>"`. Parcial → `title="Trecho: ..."`. |
| `DESC` (aviso) | — | `description:` no front-matter (≤160 caracteres). |
| `LINK` / `NAV` | — | Corrija o link relativo / o `nav` do `wiki/mkdocs.yml`. |
| `VAULT` | — | Nunca commite: `ansible-vault encrypt` (peça ao usuário; exige a senha dele). |
| `EOL` | — | Converta para LF (`sed -i 's/\r$//'`); `.gitattributes` evita reincidência. |

## Regras

- Decisões "wiki vence × server evoluiu" que mudam comportamento (IPs, recursos, grupos, versões) são do usuário: mostre o diff e uma recomendação, e espere.
- Nunca use `apply --yes` sem ter lido o dry-run.
- Termine com `check` sem erros (ou só os pré-existentes, relatados).
