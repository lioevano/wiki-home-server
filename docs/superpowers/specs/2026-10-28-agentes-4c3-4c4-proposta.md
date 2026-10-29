# Proposta: agentes 4c3 (posto e orquestrador) e 4c4 (assistente sempre ligado)

- **Data:** 2026-10-28
- **Autor:** Léo Ivan (com Claude)
- **Status:** **proposta, aguardando a escolha do Léo.** Diferente dos outros sub-projetos desta rodada, aqui não decidi sozinho. A ferramenta escolhida vira o jeito de trabalhar do dia a dia, e o mercado muda rápido: o Vibe Kanban encerrou a nuvem em abril de 2026, e o Cline Kanban ainda é *research preview*. Depois de implantado, voltar atrás custaria caro.
- **Depende de:** 4c1 (hub, rota de controle, `ops`), 4c2 (observador), VPN (página 14), LiteLLM (chave `agentes` já prevista).

## 4c3 — posto de agentes e orquestrador visual

### O que precisa existir

1. **Posto:** Claude Code (e, se quiser, Codex ou Gemini CLI) rodando no servidor, cada tarefa num *worktree* próprio de um repositório, com os MCPs do hub (rota de controle, chave `agentes_api_keys.agentes`) e das notas (`notes_mcp`).
2. **Orquestrador visual:** uma tela web para criar tarefas, acompanhar vários agentes em paralelo, revisar o diff e aprovar.
3. **Aprovação humana para agentes autônomos:** hoje o `ops` confia que o Claude Code pede aprovação a cada ferramenta destrutiva. Um agente sem ninguém olhando não pede. Proposta: para o cliente `agentes`, o `ops` não executa a ação. Ele cria um pedido (o que vai fazer, em quê e por quê) e manda ao Telegram pelo n8n, com botões **Aprovar** e **Recusar**. A ação só roda depois do "Aprovar", dentro de um prazo, e fica registrada na auditoria.

### Opções de orquestrador

| Opção | O que é | A favor | Contra |
|---|---|---|---|
| **A. Vibe Kanban** (BloopAI, Apache-2.0) | Kanban web; cada tarefa ganha branch, worktree, terminal e servidor de dev; revisão de diff com comentários; servidor MCP próprio; 10 agentes (Claude Code, Codex, Gemini CLI…) | O mais completo; licença aberta; o modo local roda num container | A empresa encerrou a nuvem paga em abril de 2026, então o futuro do projeto é incerto |
| **B. Cline Kanban** (`npx kanban`) | Kanban web da Cline; worktree por cartão; diff com comentários; Claude Code, Codex, OpenCode | Simples; equipe ativa | *Research preview* (a própria documentação avisa que vai mudar); acesso remoto ainda pouco documentado |
| **C. Terminal** (tmux + Claude Squad, com o Happy Coder no celular) | Sessões de terminal por agente; controle pelo celular | Robusto e leve; nada de interface própria para manter | Não é visual: é o oposto do "equivalente ao Maestri" pedido |

**Recomendação:** **A**, num container na `ai-desktop-vm` (ela tem a memória livre e fica perto do LiteLLM), publicado só pela VPN e pelo Traefik com Authelia (grupo `admins`). Os agentes usam o Claude Code pelo LiteLLM (chave `agentes`, com orçamento), não a assinatura: um posto que roda sozinho deve ter teto de gasto e rastreio no Langfuse. Se o Vibe Kanban parar, o posto e a aprovação continuam valendo; só a tela muda (para B).

## 4c4 — assistente sempre ligado

### O que precisa existir

Um assistente que você chama pelo Telegram, de qualquer lugar ("como está o servidor?", "anota isso no vault de estudos", "me lembra amanhã às 9h", "o que está passando na fila de downloads?"). Ele lê pelo hub e escreve só onde a política deixar.

### Opções

| Opção | O que é | A favor | Contra |
|---|---|---|---|
| **A. n8n** (workflow de agente com gatilho do Telegram e a ferramenta MCP Client apontando para o hub) | Tudo no que já existe: n8n, bot do Telegram, LiteLLM, hub | Nenhum serviço novo; a superfície de ataque não cresce | Workflow de agente difícil de testar no repositório; memória e lembretes ficam limitados |
| **B. Hermes Agent** (Nous Research) | Agente pessoal com Telegram, MCP, cron em linguagem natural, memória em camadas, endpoint compatível com OpenAI (LiteLLM) | Feito para isso; MCP e lembretes nativos | Projeto novo, que precisa de container endurecido (sem acesso ao host, saída só para o hub e o LiteLLM) |
| **C. OpenClaw** (MIT, fundação) | Agente pessoal com muitos canais e skills | Comunidade grande | O modo padrão dá acesso total ao host e o sandbox é opcional; o histórico de skills de terceiros pede cuidado |

**Recomendação:** **B**, em container sem acesso ao host, com rede só para o hub (rota de **leitura** mais as notas) e o LiteLLM (chave e orçamento próprios), e respondendo só ao seu `TELEGRAM_CHAT_ID`. As ações passam pela aprovação da 4c3 (botões no Telegram). Se você preferir não ter serviço novo, **A** é o caminho mais conservador.

## Perguntas para o Léo

1. **4c3, tela:** Vibe Kanban (recomendado), Cline Kanban ou terminal?
2. **4c3, conta:** os agentes do posto usam a API pelo LiteLLM (recomendado: teto e rastreio) ou a sua assinatura do Claude?
3. **4c3, aprovação:** aprovar pelo Telegram, com botões (recomendado), ou só pela tela do orquestrador?
4. **4c4:** Hermes Agent (recomendado), n8n ou OpenClaw? O assistente pode **escrever** nas notas, ou só ler?

Com as respostas, a 4c3 e a 4c4 seguem o fluxo de sempre: spec decidida, wiki primeiro, testes, revisão e push.
