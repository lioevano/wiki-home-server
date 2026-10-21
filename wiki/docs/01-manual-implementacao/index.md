---
description: "Roteiro do manual de implementação: a ordem dos passos para construir o servidor doméstico do zero."
---

# Manual de Implementação

Guia passo a passo para implementar o servidor doméstico. Siga na ordem.

## Estrutura

1.  **[Preparação e Planejamento](00-preparacao-planejamento.md):** Requisitos e estrutura do projeto.
2.  **[Máquina de Controle Ansible](01-maquina-controle-ansible.md):** Ambiente de gestão da infraestrutura.
3.  **[Proxmox VE Host](02-proxmox-ve-host.md):** Hypervisor, ZFS e NFS.
4.  **[Provisionamento de VMs](03-provisionamento-vms.md):** VMs `core-services-vm` e `ai-desktop-vm`.
5.  **[Configuração Base das VMs](04-configuracao-base-vms-ubuntu.md):** Docker, redes e Portainer.
6.  **[Rede Segura](05-rede-segura.md):** Configuração de Traefik, Cloudflare Tunnel e Authelia.
7.  **[Deploy Core](06-deploy-core.md):** Subida da stack `core` (Traefik, Cloudflared e Authelia).
8.  **[Deploy de Apps](07-deploy-apps.md):** Prometheus, Grafana, Loki, n8n, Home Assistant.
9.  **[Stack de IA](08-stack-ia.md):** gateway LiteLLM (apelidos de modelo, chaves por cliente, uso e Jev), Open WebUI, Ollama com Vulkan e o Claude Code.
10. **[Painel e Notificações](09-painel-notificacoes.md):** Homepage, alertas do Grafana, Diun e notificações no Telegram via n8n.
11. **[Mídia](10-midia.md):** Jellyfin, Seerr, Sonarr, Radarr, Lidarr, Prowlarr, Bazarr e qBittorrent atrás da ProtonVPN, com importação por hardlink.
12. **[Fotos e Arquivos](11-fotos-arquivos.md):** Immich, Nextcloud e Collabora, com login OIDC do Authelia.
13. **[Segundo Cérebro](12-segundo-cerebro.md):** vaults do Obsidian pelo Syncthing, busca local (qmd) e MCP para o Claude com escopo por vault.
14. **[Agentes: Base](13-agentes-base.md):** hub de MCPs com leitura pública e controle na LAN, operações (containers, stacks, Ansible) e rastreio no Langfuse.
15. **[VPN (Tailscale)](14-vpn-tailscale.md):** acesso de fora sem o limite do túnel, rota de controle do hub só pela VPN, DNS da VPN e firewall das portas do Docker.

A lista completa de aplicações, com stack, exposição e dados de cada uma, está no [Catálogo de Aplicações](../02-visao-geral-arquitetura/09-catalogo-aplicacoes.md); as integrações entre elas, no [Índice de Integrações](../02-visao-geral-arquitetura/10-indice-integracoes.md).

## A conferir no primeiro deploy

Estes pontos foram desenhados e testados no repositório, mas só dá para confirmar com o servidor rodando. Na primeira subida de cada seção, confira o item correspondente:

| Seção | O que conferir | Como |
|---|---|---|
| [5](05-rede-segura.md) | Um usuário fora do grupo `admins` é recusado nos painéis de administração (`authelia_dominios_admins`) e não ganha conta no Open WebUI nem no Langfuse | Crie um usuário de teste só com o grupo `users` e tente abrir `grafana.` e `llm.` |
| [9](09-painel-notificacoes.md) | O Diun lê as imagens pelo `docker-socket-proxy` (se faltar uma permissão do proxy, o log do Diun mostra `403`) | `docker logs diun`, `docker logs diun_ai` |
| [9](09-painel-notificacoes.md) | O alerta `timer-falhou` dispara uma vez por falha | `sudo systemctl start backup-litellm-db.service` com o banco parado |
| [10](10-midia.md) | Widget `jellyseerr` da Homepage com o Seerr (mesma API); se a Homepage fixada ganhar o widget `seerr`, troque | Homepage, grupo Mídia |
| [11](11-fotos-arquivos.md) | O editor do Collabora abre dentro do Nextcloud apesar do `X-Frame-Options: SAMEORIGIN` global (o `frame-ancestors` do Collabora deve prevalecer) | Abrir um `.docx` no Nextcloud; console do navegador |
| [11](11-fotos-arquivos.md), [8](08-stack-ia.md), [12](12-segundo-cerebro.md), [13](13-agentes-base.md) | Login OIDC pela LAN (`extra_hosts` de `auth.` para o Traefik da `core-services-vm`) | Entrar no Immich, no Open WebUI e no Langfuse; `docker logs` sem erro de TLS ou de descoberta |
| [12](12-segundo-cerebro.md) | Módulos nativos do qmd no `node:22-bookworm-slim`, `HOME` gravável do markitdown com `--user`, a "Default Folder" criada pelo `generate` do Syncthing e o `notes_escrita` com sistema de arquivos só leitura (`read_only`) | `docker logs qmd`, primeira rodada do `notes-documentos`, painel do Syncthing, uma nota criada pela escrita |
| [13](13-agentes-base.md) | agentgateway em execução: lista de leitura, chaves, tokens em arquivo, `statefulMode: stateless`, traces no Langfuse e o campo `cliente` nos logs e no registro do `ops` | Teste de ponta a ponta da seção 13; `docker logs agentgateway`, `docker logs ops_controle` |
| [13](13-agentes-base.md) | `PUT /api/stacks` do Portainer 2.19 (redeploy pelo `ops`) e o alerta `ops-acao-falhou` com o formato do Loki | `ops_stack_redeploy` de uma stack de teste; uma ação recusada |
