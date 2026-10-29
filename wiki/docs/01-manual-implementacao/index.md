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
14. **[Agentes: Base](13-agentes-base.md):** hub de MCPs com leitura pública e controle pela VPN, operações (containers, stacks, Ansible) e rastreio no Langfuse.
15. **[VPN (Tailscale)](14-vpn-tailscale.md):** acesso de fora sem o limite do túnel, rota de controle do hub só pela VPN, DNS da VPN e firewall das portas do Docker.
16. **[IA que observa o servidor](15-ia-observa.md):** análise de cada alerta e boletim da manhã no Telegram, por uma IA que só lê (rota de leitura do hub).
17. **[Posto de agentes](16-posto-agentes.md):** Claude Code em paralelo pelo Vibe Kanban, e cada ação dos agentes no servidor esperando a sua aprovação no Telegram ou na tela.
18. **[Assistente (Hermes)](17-assistente.md):** assistente no Telegram que lê o servidor, busca e escreve nas notas e agenda lembretes, sem terminal.

A lista completa de aplicações, com stack, exposição e dados de cada uma, está no [Catálogo de Aplicações](../02-visao-geral-arquitetura/09-catalogo-aplicacoes.md); as integrações entre elas, no [Índice de Integrações](../02-visao-geral-arquitetura/10-indice-integracoes.md).

## A conferir no primeiro deploy

Estes pontos foram desenhados e testados no repositório, mas só dá para confirmar com o servidor rodando. Na primeira subida de cada seção, confira o item correspondente:

| Seção | O que conferir | Como |
|---|---|---|
| [5](05-rede-segura.md) | Authelia 4.39 sem erro nem aviso de chave obsoleta (`session.cookies`, `identity_validation`, `claims_policies`) e o Traefik v3.7 sem aviso de opção faltando; o forward-auth novo (`/api/authz/forward-auth`) manda ao portal quem não entrou e volta à página pedida | `docker logs authelia`, `docker logs traefik`; abrir `grafana.` numa janela anônima |
| [5](05-rede-segura.md) | Um `X-Forwarded-Host` forjado não pula o Authelia (`trustForwardHeader: "false"`) | De fora de casa: `curl -sI -H 'X-Forwarded-Host: jellyfin.seudominio.com' https://prometheus.seudominio.com/` responde `302` para `auth.` |
| [5](05-rede-segura.md) | Os clientes OIDC recebem e-mail, nome e grupos (política `legado` de claims no ID token) | Entrar no Immich, Nextcloud, Open WebUI, Langfuse e num conector MCP |
| [5](05-rede-segura.md) | Um usuário fora do grupo `admins` é recusado nos painéis de administração (`authelia_dominios_admins`) e não ganha conta no Open WebUI nem no Langfuse | Crie um usuário de teste só com o grupo `users` e tente abrir `grafana.` e `llm.` |
| [9](09-painel-notificacoes.md) | O Diun lê as imagens pelo `docker-socket-proxy` (se faltar uma permissão do proxy, o log do Diun mostra `403`) | `docker logs diun`, `docker logs diun_ai` |
| [9](09-painel-notificacoes.md) | O alerta `timer-falhou` dispara uma vez por falha | `sudo systemctl start backup-litellm-db.service` com o banco parado |
| [10](10-midia.md) | Widget `jellyseerr` da Homepage com o Seerr (mesma API); se a Homepage fixada ganhar o widget `seerr`, troque | Homepage, grupo Mídia |
| [11](11-fotos-arquivos.md) | O editor do Collabora abre dentro do Nextcloud apesar do `X-Frame-Options: SAMEORIGIN` global (o `frame-ancestors` do Collabora deve prevalecer) | Abrir um `.docx` no Nextcloud; console do navegador |
| [11](11-fotos-arquivos.md), [8](08-stack-ia.md), [12](12-segundo-cerebro.md), [13](13-agentes-base.md) | Login OIDC pela LAN (`extra_hosts` de `auth.` para o Traefik da `core-services-vm`) | Entrar no Immich, no Open WebUI e no Langfuse; `docker logs` sem erro de TLS ou de descoberta |
| [12](12-segundo-cerebro.md) | Módulos nativos do qmd no `node:22-bookworm-slim`, `HOME` gravável do markitdown com `--user`, a "Default Folder" criada pelo `generate` do Syncthing e o `notes_escrita` com sistema de arquivos só leitura (`read_only`) | `docker logs qmd`, primeira rodada do `notes-documentos`, painel do Syncthing, uma nota criada pela escrita |
| [13](13-agentes-base.md) | agentgateway em execução: lista de leitura, chaves, tokens em arquivo, `statefulMode: stateless`, traces no Langfuse e o campo `cliente` nos logs e no registro do `ops` | Teste de ponta a ponta da seção 13; `docker logs agentgateway`, `docker logs ops_controle` |
| [15](15-ia-observa.md) | O observador chama as ferramentas da rota de leitura (nomes com prefixo, respostas em SSE do hub em modo `stateless`) e o teste do ponto de contato do Grafana chega analisado; o gasto por análise (campo `tokens`) cabe no orçamento | `docker exec observador python -m observador boletim`; *Test* da integração `observador-webhook`; `docker logs observador`; tela de uso do LiteLLM |
| [16](16-posto-agentes.md) | Vibe Kanban compilado roda o Claude Code pelo LiteLLM; os perfis `DEFAULT` (pede aprovação) e `AUTONOMO` aparecem na tela; o Claude Code lê o `/etc/claude-code/managed-mcp.json`; os botões do Telegram chegam e o clique decide | Teste de ponta a ponta da seção 16; `docker logs posto`, `docker logs aprovador` |
| [17](17-assistente.md) | Hermes 0.22.5 lê o `config.yaml` gerado (modelo `custom`, os três MCPs, `disabled_toolsets`) e só responde aos usuários permitidos | Teste de ponta a ponta da seção 17; `docker logs assistente` |
| [13](13-agentes-base.md) | `PUT /api/stacks` do Portainer 2.45 (redeploy pelo `ops`, pela porta HTTP 9000 do `--http-enabled`) e o alerta `ops-acao-falhou` com o formato do Loki | `ops_stack_redeploy` de uma stack de teste; uma ação recusada |
