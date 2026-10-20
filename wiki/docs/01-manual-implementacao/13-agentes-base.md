---
description: "Base dos agentes: hub de MCPs (agentgateway) com rota de leitura pública e rota de controle na LAN, MCP de operações com runner Ansible, MCP do Grafana, Home Assistant e n8n, e Langfuse para rastrear LLM e ferramentas."
---

# Seção 13: Agentes — base (hub de MCPs, operações e rastreio)

A IA (Claude Code, app Claude, agentes) alcança o homeserver por um **hub de MCPs** na `core-services-vm`: **leitura de qualquer lugar** (métricas, logs, alertas, containers, a casa e as automações, pelo conector **Servidor**) e **ações só na LAN** (reiniciar containers, redeployar stacks, rodar playbooks Ansible, comandar a casa, executar workflows). Toda chamada de LLM e de ferramenta fica rastreada no **Langfuse**.

## Arquivos

MCP de operações (`ops`), código Python próprio, testado em `tools/wikisync/tests/test_ops.py` (sem rede):

- `docker/images/ops/ops/__init__.py` — descrição do pacote.
- `docker/images/ops/ops/config.py` — configuração lida das variáveis de ambiente (`OPS_MODO`, `PORTAINER_URL`, listas de protegidos e de playbooks).
- `docker/images/ops/ops/politica.py` — o que é recusado (containers e stacks protegidos) e a limpeza das saídas (segredos mascarados, texto longo truncado).
- `docker/images/ops/ops/portainer.py` — cliente da API do Portainer: containers das duas VMs, logs, reinício, stacks e redeploy.
- `docker/images/ops/ops/auditoria.py` — registro de cada ação (JSON no log, coletado para o Loki) e aviso no Telegram pelo webhook do n8n.
- `docker/images/ops/ops/ferramentas.py` — as ferramentas MCP; no modo `leitura`, as que mudam algo nem existem.
- `docker/images/ops/ops/runner.py` — runner Ansible: `git pull`, `ansible-playbook --check --diff` com `plano_id`, aplicação só do plano simulado no mesmo commit, uma execução por vez.
- `docker/images/ops/ops/server.py` — registra as ferramentas do modo no FastMCP (com as anotações `readOnlyHint`/`destructiveHint`) e serve em `:8000/mcp`.
- `docker/images/ops/Dockerfile` — imagem `localhost/homeserver/ops` (Python 3.13, git, cliente SSH, coleções do `ansible/requirements.yml`), sem root.

As versões do FastMCP e do ansible-core vêm do `group_vars` por este template, gravado no diretório de build da imagem:

```jinja title="ansible/templates/agents/ops-requirements.txt.j2"
# Dependências do MCP ops (página 13). Versões em group_vars/all/main.yml.
fastmcp=={{ ops_fastmcp_version }}
ansible-core=={{ ops_ansible_core_version }}
```
