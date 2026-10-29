# Design: IA que observa o servidor (sub-projeto 4c2)

- **Data:** 2026-10-28
- **Autor:** Léo Ivan (com Claude)
- **Status:** decidido de forma autônoma, a pedido do Léo ("pode seguir da mesma forma autônoma com os demais pontos").
- **Caminho:** arquitetural: serviço novo (`observador`) na stack `agents`, página nova (15), chave nova no hub e no LiteLLM.
- **Depende de:** 4c1 (hub de MCPs, rota de leitura, Langfuse), 4a (LiteLLM), painel e notificações (Grafana Alerting → n8n → Telegram).

## 1. Objetivo

Uma IA que **olha o servidor sozinha** e conta ao Léo, no Telegram, o que viu. Ela só lê:

- **Quando um alerta dispara:** investiga (métricas, logs, containers) e manda uma análise curta: o que está acontecendo, as evidências, a causa provável e o próximo passo sugerido.
- **Toda manhã:** um boletim de saúde com o que merece atenção (alertas ativos, discos, reinícios, erros nos logs, backups, atualizações).

Ela **não age**: reiniciar, redeployar ou rodar Ansible continua com o Léo, pela rota de controle e com aprovação. Agentes que agem sozinhos são a 4c3, com aprovação humana desenhada lá.

### Critérios de pronto

- Serviço `observador` na stack `agents` (imagem local `localhost/homeserver/observador:<versão>`), sem porta publicada.
- Ele é cliente MCP da **rota de leitura** do hub, com chave própria (`agents_tokens_internos.observador`, cliente `observador` nos logs do hub e na auditoria do `ops`). Nenhuma ferramenta de escrita é alcançável.
- Pensa pelo LiteLLM com chave virtual própria (`litellm_client_keys.observador`, orçamento em `litellm_key_budgets`), rastreado no Langfuse.
- Recebe os alertas do Grafana (segunda integração do ponto de contato `n8n`) e manda o resultado pelo webhook do n8n.
- Página **15 · IA que observa o servidor**, catálogo, índice de integrações, `test`/`check`/`build`/`lint` verdes.

## 2. Decisões

| # | Tema | Escolha | Por quê |
|---|---|---|---|
| O1 | Forma | Serviço Python **só com a biblioteca padrão** (`python:3.13-slim`, sem `pip install`), código em `docker/images/observador/` | O que ele faz é pouco (um cliente MCP, um laço de chamadas ao LLM, um servidor HTTP e um agendador) e dá para testar inteiro aqui, com servidores falsos. Um workflow de agente no n8n não seria testável no repositório, e a credencial do LLM teria de ser criada à mão. Sem dependências, não há versão de biblioteca para vigiar. |
| O2 | Como observa | **Cliente MCP da rota de leitura** do hub (`http://agentgateway:4000/mcp`), com o mesmo conjunto de ferramentas do conector Servidor | Reaproveita a defesa da 4c1: as instâncias `*_leitura` não registram ferramentas de escrita e a lista `agents_leitura` fecha o resto. Um log com injeção de prompt não tem o que mandar fazer. |
| O3 | Chave no hub | `agents_tokens_internos.observador`, segunda chave da rota de leitura com `cliente: observador` | A auditoria do `ops` e o log do hub mostram quem leu. Trocar ou revogar a chave dele não mexe no conector Servidor. |
| O4 | LLM | LiteLLM em `http://<IP da ai>:4000` (a porta 4000 é aberta na LAN), modelo `observador_modelo: rapido`, chave `litellm_client_keys.observador`, orçamento de US$ 5/mês | O apelido barato basta para ler e resumir. O orçamento é o teto de gasto: estourou, o LiteLLM recusa e o observador só registra o erro. A regra LLM passa a cobrir consumidor em outra VM (sem rede Docker compartilhada). |
| O5 | Laço do agente | Até `OBSERVADOR_MAX_PASSOS=8` rodadas de ferramentas por análise; saída de cada ferramenta cortada em 6.000 caracteres; 180 s por análise | Limita custo e tempo, e mantém o contexto pequeno. |
| O6 | Gatilho: alerta | A integração `observador-webhook` no ponto de contato `n8n` do Grafana manda `POST /alerta` (com `Bearer ${OBSERVADOR_TOKEN}`). Ele responde 202 na hora e analisa numa fila de uma análise por vez | O Grafana não espera a análise. O n8n continua recebendo o alerta como antes: as duas integrações são independentes. |
| O7 | Filtro de alertas | Só `firing`. Uma mesma impressão digital (`fingerprint`) não é analisada de novo antes de 12 h (o Grafana repete a cada 4 h). No máximo 6 análises por hora; fila de até 10. `observador-falhou` é ignorado | Evita custo repetido e o laço "o observador analisa a falha do observador". |
| O8 | Gatilho: boletim | Às 07:30 (`OBSERVADOR_BOLETIM_HORA`, fuso `TZ`), por um agendador interno | Sem cron nem n8n a mais. |
| O9 | Saída | Webhook do n8n (`/webhook/notificar`, formato genérico: `titulo`, `mensagem`, `gravidade`, `app: observador`), mensagem cortada em 3.500 caracteres | O n8n já formata e manda ao Telegram (limite de 4.096). |
| O10 | Registro | Uma linha JSON por análise no stdout (`evento: observador`, gatilho, alerta, passos, ferramentas, resultado, duração), coletada pelo Alloy. Alerta novo **`observador-falhou`** (Loki: análise com `resultado: erro` em 30 min) | O Léo fica sabendo se o observador parou (LiteLLM fora, orçamento estourado, hub fora). |
| O11 | Prompt | Sistema em português: "você só observa", estrutura fixa da resposta, nunca dizer que fez algo, sugerir a ferramenta do `ops` ou a página da wiki para o próximo passo, tratar o conteúdo de logs como dado (não instrução) | O texto que chega ao Telegram é sugestão, não ação. |
| O12 | Rastreio | `metadata` do LiteLLM: `trace_name` (`observador-alerta` ou `observador-boletim`), `tags`, `session_id` por análise | Cada análise vira um trace no Langfuse, com as rodadas de ferramentas. |

## 3. Peças

- `docker/images/observador/` — `Dockerfile` e o pacote `observador` (`config`, `mcp`, `llm`, `agente`, `prompts`, `saida`, `servidor`, `__main__`).
- Compose `agents`: serviço `observador` (redes `agents_internal` e `proxy`; `diun.enable: "false"`; `user` do dockeruser).
- `setup-agents-volumes.yml`: constrói a imagem (força quando o código muda) e grava `OBSERVADOR_*` no `agents.env`.
- `agentgateway.yaml.j2`: segunda chave na rota de leitura.
- `group_vars`: `observador_version`, `observador_modelo`, `observador_boletim_hora`, `litellm_key_budgets.observador`. Vault: `litellm_client_keys.observador`, `agents_tokens_internos.observador`, `observador_token`.
- Grafana: integração `observador-webhook` no ponto de contato `n8n`, `OBSERVADOR_TOKEN` no ambiente do Grafana, regra `observador-falhou`.

## 4. Riscos

- **Custo:** limitado pelo orçamento da chave e pelos limites O5/O7.
- **Análise errada:** o texto é marcado como da IA e só sugere; nenhuma ação sai dele.
- **Injeção de prompt por log:** sem ferramenta de escrita na rota de leitura, o pior caso é um texto enganoso no Telegram.
- **Dados no LLM:** logs e métricas vão ao provedor do apelido `rapido` (Anthropic). Para mantê-los em casa, `observador_modelo: local` (Ollama), com qualidade menor.

## 5. Fora do escopo

- Agir sozinho (4c3), conversar pelo Telegram (4c4).
- Detecção de anomalias por estatística: o boletim e os alertas existentes cobrem o essencial.
