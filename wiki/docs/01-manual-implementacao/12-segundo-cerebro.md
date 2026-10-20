---
description: "Stack notes na VM de IA: vaults do Obsidian sincronizados pelo Syncthing, busca local com qmd sobre as notas e os documentos do Nextcloud, e MCP para o Claude com escopo por vault."
---

# Seção 12: Segundo cérebro (Obsidian, Syncthing, busca local e MCP)

Os vaults do Obsidian **Pessoal**, **Trabalho** e **Estudos**, editados no PC e no celular, ficam sincronizados com o servidor pelo **Syncthing**. No servidor, o **qmd** indexa as notas e os documentos do Nextcloud (convertidos para Markdown) com busca local, sem custo de API. O Claude (app, claude.ai e Claude Code), o Open WebUI e os agentes acessam tudo por **MCP**, com escopo por vault:

| Vault | O Claude pode |
|---|---|
| Pessoal | buscar e ler |
| Trabalho | buscar, ler, criar, editar e mover |
| Estudos | buscar, ler, criar, editar e mover |
| Documentos (Nextcloud) | buscar e ler (cópia convertida) |

## Dados

O dataset `data/notes` (cota de 20G, [seção 2](02-proxmox-ve-host.md)) é exportado só para a `ai-desktop-vm` e tem snapshots automáticos a cada 15 minutos ([guia de snapshots](../03-guias-sustentacao/12-guia-snapshots-zfs.md)): é por eles que se desfaz uma edição da IA. O dataset `files` do Nextcloud é montado **só leitura** na mesma VM.
