# Design: assistente sempre ligado (sub-projeto 4c4)

- **Data:** 2026-10-29
- **Autor:** Léo Ivan (com Claude)
- **Status:** decidido. O Léo escolheu o **Hermes Agent** com **leitura e escrita** nas notas (`2026-10-28-agentes-4c3-4c4-proposta.md`). O resto foi decidido de forma autônoma, a pedido dele.
- **Caminho:** arquitetural: stack nova (`assistente`, ai-desktop-vm), bot novo do Telegram, chave nova no hub e no LiteLLM.
- **Depende de:** 4c3 (rota `autonomos`, `aprovador`), 4b (MCPs das notas), 4a (LiteLLM).

## 1. Objetivo

Um assistente que o Léo chama pelo Telegram, de qualquer lugar: perguntar do servidor, anotar e buscar nas notas, pedir lembretes. Ações no servidor passam pela mesma aprovação da 4c3.

### Critérios de pronto

- Stack `assistente` na `ai-desktop-vm` com o Hermes Agent (`nousresearch/hermes-agent:v0.22.5`) em modo gateway, sem porta publicada.
- Responde só ao Léo (`TELEGRAM_ALLOWED_USERS`), por um bot próprio.
- Modelo pelo LiteLLM (chave `assistente`, orçamento próprio); MCPs: servidor (rota `autonomos`, chave `assistente`), busca nas notas e escrita em Trabalho e Estudos.
- Ferramentas embutidas perigosas desligadas (terminal, código, arquivos, navegador, web, conexões, skills…).
- Página **17**, catálogo, índices, `test`/`check`/`build`/`lint` verdes.

## 2. Decisões

| # | Tema | Escolha | Por quê |
|---|---|---|---|
| A1 | Ferramenta | **Hermes Agent** (Nous Research), imagem oficial `nousresearch/hermes-agent:v0.22.5` (estável de 2026-10-23), `gateway run` | Escolha do Léo: Telegram, MCP, lembretes (cron) e memória nativos. |
| A2 | Onde | `ai-desktop-vm`, perto do LiteLLM (`ai_network`) e dos MCPs das notas (`notes_mcp`) | As notas sem autenticação própria só existem nessa rede interna. |
| A3 | Bot | **Bot próprio** (`hermes_telegram_bot_token`), `TELEGRAM_ALLOWED_USERS` = `telegram_chat_id` | O Hermes lê o bot por `getUpdates`; o bot de avisos é lido pelo `aprovador` (4c3) e um bot só aceita um leitor. E é bom separar "avisos" de "conversa". |
| A4 | Modelo | `provider: custom`, `base_url: http://litellm:4000/v1`, chave `litellm_client_keys.assistente` (US$ 15/mês), apelido `assistente_modelo: principal`, `session_affinity_header: x-litellm-session-id` | O apelido troca de LLM sem mexer no assistente; o cabeçalho de sessão agrupa a conversa no LiteLLM/Langfuse. |
| A5 | MCPs | `servidor` (rota `autonomos` do hub na core, chave `agents_autonomos_keys.assistente`), `notas` (`http://qmd:8181/mcp`, busca em tudo) e `escrita` (`http://notes_escrita:8000/mcp`, só Trabalho e Estudos). Todos `trust: full` | Escolha do Léo: leitura e escrita nas notas. O escopo de escrita é o do `notes_escrita` (só duas pastas, snapshots ZFS a cada 15 minutos). Ações no servidor já exigem aprovação no `ops` (4c3), então não precisa de outra confirmação no Hermes. |
| A6 | Ferramentas embutidas | `agent.disabled_toolsets`: `terminal`, `code_execution`, `file`, `browser`, `computer_use`, `web`, `search`, `x_search`, `connections`, `delegation`, `skills`, `image_gen`, `video_gen`, `video`, `tts`, `vision`, `kanban`, `project`, `catalog`, `desktop_ui`, `feishu_doc`, `feishu_drive`, `discord`, `discord_admin`, `yuanbao`. Ficam `memory`, `cronjob`, `todo`, `clarify`, `session_search` e os MCPs | Num assistente aberto a mensagens (e a conteúdo de notas e logs), terminal, código e conexões são o caminho de um ataque. A campanha de junho de 2026 contra Hermes expostos plantou chaves SSH por config de MCP. |
| A7 | Container | Sem porta, sem socket do Docker, sem painel (`HERMES_DASHBOARD` desligado) e sem API (`API_SERVER_ENABLED` desligado); `no-new-privileges`; `HERMES_UID`/`HERMES_GID` do dockeruser; dados em `{{ vm_local_data_path }}/hermes` (disco local: SQLite) | Nada entra; o único canal é o Telegram, filtrado por usuário. |
| A8 | Config | `config.yaml` e `.env` (0600) gerados pelo Ansible a partir da wiki em cada execução do `setup-assistente-volumes.yml` | A wiki é a fonte da verdade: o que for mudado pela interface do Hermes volta ao que a wiki diz. |
| A9 | Memória e lembretes | `memory` (MEMORY.md/USER.md do Hermes) e `cronjob` (lembretes entregues no Telegram) | Pedidos do Léo: lembretes e contexto entre conversas. O que importa de verdade vai para as notas (que têm backup). |
| A10 | Backup | Sem backup próprio: dados no disco local da VM (sessões e memória do Hermes) | Regerável; o que o Léo quer guardar o assistente escreve nas notas. |

## 3. Riscos

- **Injeção de prompt** (uma nota ou um log mandando o assistente fazer algo): sem terminal nem código, ele só alcança as notas de Trabalho e Estudos (versionadas por snapshot) e o `ops` (com aprovação).
- **Dados que saem de casa:** conversas, notas lidas e dados do servidor vão ao provedor do apelido (Anthropic no `principal`).
- **Token do bot vazado:** quem tiver o token lê as mensagens; mas o Hermes só responde a `TELEGRAM_ALLOWED_USERS`. Revogue no BotFather.
