---
description: "Base dos agentes: hub de MCPs (agentgateway) com rota de leitura pública e rota de controle na LAN, MCP de operações com runner Ansible, MCP do Grafana, Home Assistant e n8n, e Langfuse para rastrear LLM e ferramentas."
---

# Seção 13: Agentes — base (hub de MCPs, operações e rastreio)

A IA (Claude Code, app Claude, agentes) alcança o homeserver por um **hub de MCPs** na `core-services-vm`: **leitura de qualquer lugar** (métricas, logs, alertas, containers, a casa e as automações, pelo conector **Servidor**) e **ações só na LAN** (reiniciar containers, redeployar stacks, rodar playbooks Ansible, comandar a casa, executar workflows). Toda chamada de LLM e de ferramenta fica rastreada no **Langfuse**.

## Arquivos

Stack e preparação:

- `docker/stacks/agents/docker-compose.yml` — stack `agents` na `core-services-vm` (Portainer, endpoint `local`, variáveis em `/opt/portainer_stack_envs/agents.env`): `mcp_grafana_leitura`/`mcp_grafana_controle`, `ops_leitura`/`ops_controle` e o hub.
- `ansible/playbooks/setup-agents-volumes.yml` — diretórios em `/opt/local-data/ops`, chave SSH e senha do vault do runner (`0400`), clone do repositório, imagem `localhost/homeserver/ops` e `agents.env`.

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

## Hub de MCPs (agentgateway)

O hub junta os MCPs em dois endereços. A **rota `leitura`** (porta 4000, só na rede interna) recebe o conector **Servidor** pelo `mcp_auth_servidor` e só alcança instâncias que não sabem escrever (`mcp_grafana_leitura`, `ops_leitura`), mais o Home Assistant e o n8n limitados a uma lista de ferramentas de consulta (`agents_leitura`). A **rota `controle`** (porta 4100, publicada só no IP da `core-services-vm` na LAN) alcança tudo e exige a chave de um cliente (`agents_api_keys`); no config vai só o hash. Os tokens do Home Assistant e do n8n ficam em arquivos `0400` montados no container, e a autenticação do rastreio no Langfuse vem da variável `OTEL_EXPORTER_OTLP_TRACES_HEADERS` — o arquivo não tem nenhum segredo. Se um alvo cair, as ferramentas dele somem e o resto continua (`failOpen`).

```jinja title="ansible/templates/agents/agentgateway.yaml.j2"
# Hub de MCPs da base dos agentes (página 13). Gerado pelo setup-agents-volumes.yml em
# {{ '{{' }} vm_local_data_path {{ '}}' }}/agentgateway/config.yaml. Sem segredos: chaves dos clientes só como hash;
# tokens dos alvos em arquivos (/segredos); autenticação do rastreio por variável de ambiente.
# yaml-language-server: $schema=https://agentgateway.dev/schema/config
{% set alvos_fixos = {
  'homeassistant': {'host': 'http://homeassistant:8123/api/mcp', 'token': '/segredos/homeassistant_token'},
  'n8n': {'host': 'http://n8n:5678/mcp-server/http', 'token': '/segredos/n8n_token'},
} %}
{% macro alvos(sufixo) %}
          targets:
          - name: grafana
            mcp:
              host: http://mcp_grafana_{{ sufixo }}:8000/mcp
          - name: ops
            mcp:
              host: http://ops_{{ sufixo }}:8000/mcp
{% for nome, alvo in alvos_fixos.items() %}
          - name: {{ nome }}
            mcp:
              host: {{ alvo.host }}
            policies:
              backendAuth:
                key:
                  file: {{ alvo.token }}
{% endfor %}
{% endmacro %}
config:
  statsAddr: 0.0.0.0:15020
  logging:
    format: json
  tracing:
    otlpEndpoint: http://{{ ai_desktop_vm_ip_var }}:3100/api/public/otel
    otlpProtocol: http
    randomSampling: "true"

binds:
# Rota de leitura: só pela rede interna, atrás do mcp_auth_servidor (OAuth + Authelia, grupo admins).
- port: 4000
  listeners:
  - name: leitura
    routes:
    - name: leitura
      policies:
        mcpAuthorization:
          rules:
{% for alvo, ferramentas in agents_leitura.items() %}
{% if ferramentas == '*' %}
          - allow: 'mcp.tool.target == "{{ alvo }}"'
{% else %}
          - allow: 'mcp.tool.target == "{{ alvo }}" && mcp.tool.name in {{ ferramentas | to_json }}'
{% endif %}
{% endfor %}
      backends:
      - mcp:
          prefixMode: always
          failureMode: failOpen
{{ alvos('leitura') }}
# Rota de controle: só na LAN (porta publicada no IP da core-services-vm), com a chave de cada cliente.
- port: 4100
  listeners:
  - name: controle
    routes:
    - name: controle
      policies:
        apiKey:
          mode: strict
          location:
            header:
              name: Authorization
              prefix: "Bearer "
          keys:
{% for cliente, chave in agents_api_keys.items() %}
          - keyHash: "sha256:{{ chave | hash('sha256') }}"
            metadata:
              cliente: {{ cliente }}
{% endfor %}
      backends:
      - mcp:
          prefixMode: always
          failureMode: failOpen
{{ alvos('controle') }}
```
