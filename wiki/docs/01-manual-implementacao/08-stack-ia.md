---
description: "Stack de IA na ai-desktop-vm: Ollama, LiteLLM, Open WebUI, OpenClaw e OpenClaude, com volumes e configuração do LiteLLM."
---

# Seção 8: Stack de IA (Ollama + LiteLLM + Open WebUI + OpenClaw + OpenClaude)

A stack de IA roda na `ai-desktop-vm`. Todos os serviços estão em `docker/stacks/ai/docker-compose.yml`.

## Arquitetura

```
Open WebUI ─┐
OpenClaw ───┤──► LiteLLM (proxy:4000) ──► Ollama (local, porta 11434)
OpenClaude ─┤                           └──► APIs externas (Gemini, OpenAI, Anthropic)
```

- **Ollama**: Executa modelos LLM locais. Baixe modelos com `ollama pull llama3.2`, `ollama pull phi3`, etc.
- **LiteLLM**: Proxy OpenAI-compatible. Roteia requisições entre Ollama e APIs externas com fallback automático.
- **Open WebUI**: Interface web para chat com LLMs. Acessível em `http://ai-desktop-ip:3000`.
- **OpenClaw**: CLI agent para terminal. Conecta ao LiteLLM.
- **OpenClaude**: Assistente AI com memória persistente e integração com ferramentas locais.

## Deploy

1. Execute o playbook de volumes:
   ```bash
   ansible-playbook -i ansible/inventories/home/hosts.ini ansible/playbooks/setup-ai-volumes.yml
   ```

2. **Se Portainer está gerenciando a ai-desktop-vm:**
   - Adicione o endpoint da ai-desktop-vm no Portainer (via Portainer Agent ou TCP)
   - **Stacks** > **Add Stack** > Nome: `ai`
   - Cole o conteúdo de `docker/stacks/ai/docker-compose.yml`
   - Carregue `/opt/portainer_stack_envs/ai.env` (já traz todos os segredos; nada a adicionar à mão)
   - **Deploy**

3. **Se deploy manual via CLI (na ai-desktop-vm):**
   ```bash
   cd /path/to/docker/stacks/ai
   sudo docker compose --env-file /opt/portainer_stack_envs/ai.env up -d
   ```

### Variáveis da stack

O `ai.env` é gerado por `ansible/playbooks/setup-ai-volumes.yml` (via `ansible/templates/portainer_stack_env.j2`) com `mode: '0600'`, porque contém segredos.

| Variável | Origem |
|---|---|
| `DOCKER_PUID`, `DOCKER_PGID`, `SYSTEM_TIMEZONE` | comuns (vault) |
| `AI_STACK_*_PATH` | `vm_nfs_mount_base_path` + `zfs_docker_volumes_dataset_name` |
| `AI_DESKTOP_VM_IP` | `ai_desktop_vm_ip_var` do `hosts.ini` |
| `LITELLM_MASTER_KEY` | vault `litellm_master_key` |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` | vault `llm_api_keys.openai`, `.anthropic`, `.google_gemini` |
| `OPENWEBUI_SECRET_KEY` | vault `openwebui_secret_key` |

### Passos manuais ao mudar variáveis ou segredos

1. Confira no vault real (`ansible-vault edit ansible/inventories/home/group_vars/all/vault.yml`) que `litellm_master_key`, `llm_api_keys.*` e `openwebui_secret_key` estão preenchidos; gere chaves novas com `openssl rand -hex 32`.
2. Simule e depois aplique o playbook:
   ```bash
   ansible-playbook -i ansible/inventories/home/hosts.ini ansible/playbooks/setup-ai-volumes.yml --check --diff
   ansible-playbook -i ansible/inventories/home/hosts.ini ansible/playbooks/setup-ai-volumes.yml
   ```
3. No Portainer, abra a stack `ai`, recarregue `/opt/portainer_stack_envs/ai.env` em **Env** e clique em **Update the stack**.

O `setup-ai-volumes.yml` também aplica o role `ansible/roles/apps/ml-tools/` na `ai-desktop-vm` (ferramentas de ML e dependências da stack).

## Configuração do LiteLLM

O arquivo `config.yaml` é gerado pelo Ansible a partir de `ansible/templates/litellm_config.yaml.j2`. Modelo base:

```yaml
general_settings:
  master_key: "sua-chave-master"

model_list:
  - model_name: claude-sonnet
    litellm_params:
      model: claude-sonnet-4-20250514
      api_key: "sk-ant-..."

  - model_name: gemini-flash
    litellm_params:
      model: gemini/gemini-2.5-flash
      api_key: "AIza..."

  - model_name: open-webui
    litellm_params:
      model: openai/gpt-4o
      api_key: "sk-..."

  - model_name: local
    litellm_params:
      model: ollama/llama3.2
      api_base: "http://ollama:11434"
```

## Baixando Modelos no Ollama

```bash
# Na ai-desktop-vm, ou via docker exec
docker exec -it ollama ollama pull llama3.2
docker exec -it ollama ollama pull phi3
docker exec -it ollama ollama list
```

## Acessando os Serviços

| Serviço | URL | Porta |
|---|---|---|
| Open WebUI | `http://ai-desktop-ip:3000` | 3000 |
| LiteLLM API | `http://ai-desktop-ip:4000` | 4000 |
| Ollama API | `http://ai-desktop-ip:11434` | 11434 |
| OpenClaw | Terminal (via `docker exec -it openclaw sh`) | N/A |
| OpenClaude | Terminal (via `docker exec -it openclaude sh`) | N/A |