---
description: "Base dos agentes: hub de MCPs (agentgateway) com rota de leitura pública e rota de controle na LAN, MCP de operações com runner Ansible, MCP do Grafana, Home Assistant e n8n, e Langfuse para rastrear LLM e ferramentas."
---

# Seção 13: Agentes — base (hub de MCPs, operações e rastreio)

A IA (Claude Code, app Claude, agentes) alcança o homeserver por um **hub de MCPs** na `core-services-vm`: **leitura de qualquer lugar** (métricas, logs, alertas, containers, a casa e as automações, pelo conector **Servidor**) e **ações só na LAN** (reiniciar containers, redeployar stacks, rodar playbooks Ansible, comandar a casa, executar workflows). Toda chamada de LLM e de ferramenta fica rastreada no **Langfuse**.
