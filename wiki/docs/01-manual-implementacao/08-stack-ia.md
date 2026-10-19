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
- **Open WebUI**: Interface web para chat com LLMs. Usa o LiteLLM como API compatível com OpenAI (`OPENAI_API_BASE_URL=http://litellm:4000/v1`, chave `LITELLM_MASTER_KEY`) e o Ollama direto para gerenciar modelos locais. Acessível em `https://openwebui.seudominio.com` (Traefik da `core-services-vm` + Authelia, router `openwebui-dynamic` em `ansible/roles/infra/traefik-config/templates/dynamic_rag_services.yml.j2`) ou na LAN em `http://ai-desktop-ip:3000`.
- **OpenClaw**: CLI agent para terminal. Conecta ao LiteLLM.
- **OpenClaude**: Assistente AI com memória persistente e integração com ferramentas locais.
- **Diun (`diun_ai`)**: Avisa (via n8n → Telegram) quando sai imagem nova de algum container desta VM; chama `https://n8n.seudominio.com/webhook/notificar` com `NOTIFICACOES_WEBHOOK_TOKEN`. Veja [Painel e Notificações](09-painel-notificacoes.md).
- **Promtail (`promtail_ai`)**: Envia os logs dos containers e do sistema desta VM ao Loki da `core-services-vm` (`http://<core_services_vm_ip_var>:3100`). A configuração é gerada de `ansible/templates/promtail-config.yml.j2` pelo `setup-ai-volumes.yml`.

## Deploy

1. Execute o playbook de volumes:
   ```bash
   ansible-playbook -i inventories/home/hosts.ini playbooks/setup-ai-volumes.yml
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
| `AI_STACK_*_PATH` (inclui `AI_STACK_PROMTAIL_*`) | `vm_nfs_mount_base_path` + `zfs_docker_volumes_dataset_name` |
| `AI_DESKTOP_VM_IP` | `ai_desktop_vm_ip_var` do `hosts.ini` |
| `LITELLM_MASTER_KEY` | vault `litellm_master_key` |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` | vault `llm_api_keys.openai`, `.anthropic`, `.google_gemini` |
| `OPENWEBUI_SECRET_KEY` | vault `openwebui_secret_key` |
| `NOTIFICACOES_WEBHOOK_TOKEN` | vault `notificacoes_webhook_token` (Diun) |

### Passos manuais ao mudar variáveis ou segredos

1. Confira no vault real (`ansible-vault edit inventories/home/group_vars/all/vault.yml`) que `litellm_master_key`, `llm_api_keys.*` e `openwebui_secret_key` estão preenchidos; gere chaves novas com `openssl rand -hex 32` (evite `$`, `#`, aspas e espaços: o `.env` não usa aspas).
2. Simule e depois aplique o playbook (sem `--diff`, que imprimiria os segredos do `.env` no terminal):
   ```bash
   ansible-playbook -i inventories/home/hosts.ini playbooks/setup-ai-volumes.yml --ask-vault-pass --check
   ansible-playbook -i inventories/home/hosts.ini playbooks/setup-ai-volumes.yml --ask-vault-pass
   ```
3. No Portainer, abra a stack `ai`, recarregue `/opt/portainer_stack_envs/ai.env` em **Env** e clique em **Update the stack**.

O `setup-ai-volumes.yml` também aplica o role `ansible/roles/apps/ml-tools/` na `ai-desktop-vm`: ele instala o driver AMD/ROCm da GPU (RX 5600 XT) e desativa uma eventual instalação nativa antiga do Ollama. O Ollama roda **só em container** (`ollama/ollama:rocm`, com `/dev/kfd` e `/dev/dri`).

!!! warning "Suporte da RX 5600 XT"
    A RX 5600 XT (RDNA1, `gfx1010`) não está na lista oficial de GPUs AMD do Ollama; se ela não for reconhecida, o Ollama roda em CPU (veja `docker logs ollama`). O resto da stack funciona igual.

## Configuração do LiteLLM

O arquivo `config.yaml` é gerado pelo Ansible a partir do template abaixo (segredos vêm do vault). Para trocar ou acrescentar modelos, edite este bloco e siga o fluxo wiki-first; modelos locais precisam ser baixados no Ollama (próxima seção).

```yaml title="ansible/templates/litellm_config.yaml.j2"
# ansible/templates/litellm_config.yaml.j2
# Gerado pelo setup-ai-volumes.yml em <NFS>/litellm/config/config.yaml.
general_settings:
  master_key: "{{ litellm_master_key }}"

model_list:
  - model_name: gpt-4o
    litellm_params:
      model: gpt-4o
      api_key: "{{ llm_api_keys.openai }}"

  - model_name: claude-3-opus
    litellm_params:
      model: claude-3-opus-20240229
      api_key: "{{ llm_api_keys.anthropic }}"

  - model_name: gemini-1.5-pro
    litellm_params:
      model: gemini/gemini-1.5-pro-latest
      api_key: "{{ llm_api_keys.google_gemini }}"

  - model_name: ollama/llama3.2
    litellm_params:
      model: ollama/llama3.2
      api_base: "http://ollama:11434" # Ollama na mesma rede Docker (ai_network); ele não escuta no IP da VM
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
| Open WebUI | `https://openwebui.seudominio.com` (Authelia) ou `http://ai-desktop-ip:3000` | 3000 |
| LiteLLM API | `http://ai-desktop-ip:4000` (chave: `LITELLM_MASTER_KEY`) | 4000 |
| Ollama API | só dentro da VM: `http://127.0.0.1:11434` (ou `docker exec -it ollama ...`); os demais serviços usam `http://ollama:11434` | 11434 |
| OpenClaw | Terminal (via `docker exec -it openclaw sh`) | N/A |
| OpenClaude | Terminal (via `docker exec -it openclaude sh`) | N/A |