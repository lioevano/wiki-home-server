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
6.  **[Deploy Core](06-deploy-core.md):** Traefik, Cloudflared e Authelia (infra base).
7.  **[Deploy de Apps](07-deploy-apps.md):** Nextcloud, Jellfin, Sonarr, Radarr, qBittorrent, Prometheus, Grafana, Loki, n8n, Home Assistant.
8.  **[Stack de IA](08-stack-ia.md):** Ollama, LiteLLM, Open WebUI, OpenClaw, OpenClaude.
