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
8.  **[Deploy de Apps](07-deploy-apps.md):** Nextcloud, Jellyfin, Sonarr, Radarr, qBittorrent, Prometheus, Grafana, Loki, n8n, Home Assistant.
9.  **[Stack de IA](08-stack-ia.md):** Ollama, LiteLLM, Open WebUI, OpenClaw, OpenClaude.
10. **[Painel e Notificações](09-painel-notificacoes.md):** Homepage, alertas do Grafana, Diun e notificações no Telegram via n8n.

A lista completa de aplicações, com stack, exposição e dados de cada uma, está no [Catálogo de Aplicações](../02-visao-geral-arquitetura/09-catalogo-aplicacoes.md); as integrações entre elas, no [Índice de Integrações](../02-visao-geral-arquitetura/10-indice-integracoes.md).
