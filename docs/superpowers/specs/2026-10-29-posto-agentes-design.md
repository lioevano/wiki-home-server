# Design: posto de agentes, orquestrador visual e aprovação humana (sub-projeto 4c3)

- **Data:** 2026-10-29
- **Autor:** Léo Ivan (com Claude)
- **Status:** decidido. O Léo escolheu as opções da proposta (`2026-10-28-agentes-4c3-4c4-proposta.md`): **Vibe Kanban**, agentes pelo **LiteLLM**, aprovação pelo **Telegram e pela tela**. O resto foi decidido de forma autônoma, a pedido dele.
- **Caminho:** arquitetural: stack nova (`posto`, ai-desktop-vm), serviço novo (`aprovador`, stack `agents`), rota nova no hub e aprovação no `ops`.
- **Depende de:** 4c1 (hub, `ops`), 4a (LiteLLM), 4b (MCPs das notas), VPN/firewall (página 14), painel e notificações (bot do Telegram).

## 1. Objetivo

Agentes Claude Code que trabalham sozinhos no servidor, em paralelo, cada tarefa num *worktree* próprio, acompanhados numa tela web. Toda ação deles **no servidor** (reiniciar, redeployar, aplicar Ansible) espera o "aprovar" do Léo, pelo Telegram ou por uma tela de aprovações.

### Critérios de pronto

- Stack `posto` na `ai-desktop-vm` com o Vibe Kanban (imagem local construída do código-fonte, versão fixada), atrás do Traefik + Authelia (`kanban.`, grupo `admins`).
- Claude Code no posto pelo LiteLLM (chave `agentes`, orçamento próprio), com os MCPs do servidor (rota nova do hub) e das notas.
- Rota **`autonomos`** do hub (porta 4200): leitura de tudo e as ações do `ops`, sem as ferramentas de escrita do Grafana, da casa e do n8n. Chaves `agentes` (4c3) e `assistente` (4c4).
- Serviço **`aprovador`**: cada ação de um cliente autônomo vira um pedido com botões **Aprovar/Recusar** no Telegram e na tela `aprovacoes.` (Authelia, `admins`). O `ops` só executa com um pedido aprovado, que vale uma vez.
- Página **16**, catálogo, índices, `test`/`check`/`build`/`lint` verdes.

## 2. Decisões

| # | Tema | Escolha | Por quê |
|---|---|---|---|
| P1 | Orquestrador | **Vibe Kanban** (Apache-2.0), modo local (um usuário, SQLite), tag `v0.1.45-20260919085201` | Escolha do Léo. O modo local é o servidor `crates/server` com a interface embutida; o "Cloud" (multiusuário, Postgres, Electric) não é necessário. |
| P2 | Imagem | **Construída do código-fonte** na `ai-desktop-vm` (`docker buildx`, `Dockerfile` do próprio repositório, na tag fixada), e por cima uma imagem `localhost/homeserver/posto` com Node, git, `gh` e o Claude Code em cache | O pacote npm baixa um binário de um CDN da Bloop (que encerrou a nuvem em abril de 2026) e traz telemetria embutida. Do código-fonte, os argumentos `POSTHOG_*` e `SENTRY_DSN` ficam vazios: sem telemetria e sem depender do CDN. O custo é uma compilação Rust longa, uma vez por versão. |
| P3 | Onde | `ai-desktop-vm` (memória livre, perto do LiteLLM e dos MCPs das notas) | Os agentes rodam `npm`, testes e builds; a core fica com o caminho de controle. |
| P4 | Acesso | Porta `3005` no IP da `ai-desktop-vm`, aceita só da `core-services-vm` (`firewall_docker_portas`); Traefik `kanban.` pelo file provider, com `authelia-forwardauth` e `kanban` em `authelia_dominios_admins` | O Vibe Kanban local não tem login: quem chega na porta controla os agentes. Só o Traefik chega, e o Traefik exige 2FA e o grupo `admins`. |
| P5 | Conta dos agentes | **LiteLLM**, chave `litellm_client_keys.agentes` (orçamento US$ 50/mês), nomes reais dos modelos Claude (`ANTHROPIC_DEFAULT_*_MODEL`), `ANTHROPIC_BASE_URL=http://litellm:4000` (rede `ai_network`) | Escolha do Léo: teto de gasto e rastreio no Langfuse. |
| P6 | Aprovação na tela | O perfil padrão do Claude Code no Vibe Kanban passa a **pedir aprovação** (`approvals: true`); a variante `AUTONOMO` mantém o `dangerously_skip_permissions` do Vibe Kanban | A "tela" da escolha do Léo: os pedidos de permissão do Claude Code (comandos, arquivos) aparecem na interface do Vibe Kanban. Para tarefas de confiança, escolhe-se `AUTONOMO` na criação. |
| P7 | MCPs dos agentes | `/etc/claude-code/managed-mcp.json` (gerenciado, só leitura): `servidor` (rota `autonomos`, chave `agentes`), `notas` (`http://qmd:8181/mcp`) e `escrita` (`http://notes_escrita:8000/mcp`), pela rede `notes_mcp` | Igual para todo agente e toda tarefa, sem depender de config por repositório. As notas pela rede interna, como previsto na 4c1 (A14). |
| P8 | Rota `autonomos` no hub | Porta 4200 publicada no IP da core, aceita pela LAN só da `ai-desktop-vm`. Alvos: `mcp_grafana_leitura`, `ops_controle` (ações com aprovação), casa e n8n só com as ferramentas de consulta (`agents_leitura`). Chaves em `agents_autonomos_keys` (vault): `agentes`, `assistente` | Um agente sem ninguém olhando não pode silenciar alertas, mexer em painel, comandar a casa ou editar workflows. Ele age só pelo `ops`, onde a aprovação é exigida. A chave `agentes` sai da rota de controle. |
| P9 | Aprovação no `ops` | Para clientes em `OPS_CLIENTES_COM_APROVACAO` (`agentes,assistente`), as ferramentas destrutivas (`container_reiniciar`, `stack_redeploy`, `ansible_aplicar`) primeiro passam pelas checagens (protegidos), depois criam um pedido no `aprovador` e respondem "aguardando aprovação: pedido X". O agente chama de novo com `aprovacao_id=X`, e o `ops` executa só se o pedido estiver **aprovado**, for **da mesma ação, alvo e argumentos**, **não tiver sido usado** e **estiver no prazo**. Sem `aprovador` configurado, recusa | Igual ao `plano_id` do Ansible: o agente não espera parado (o MCP tem tempo limite), e o pedido não serve para outra ação. Falha fechada. |
| P10 | `aprovador` | Serviço próprio, Python só com a biblioteca padrão (como o observador), na stack `agents` (core). API com token (`APROVADOR_TOKEN`, só o `ops_controle` tem); botões no Telegram pelo **bot de avisos** (o mesmo das notificações), lendo as respostas por `getUpdates`; tela em `aprovacoes.` (Traefik + Authelia `admins`, com um segredo que só o Traefik injeta, `X-Aprovador-Chave`, para que outro container da rede `proxy` não decida no lugar do Léo) | Interação com botões precisa receber o clique; o n8n só envia. O bot de avisos não tem outro leitor (Grafana e n8n só mandam), então o `aprovador` pode ler os cliques. O assistente (4c4) usa um bot próprio. |
| P11 | Validade | Pedido pendente expira em 30 min (`APROVADOR_VALIDADE_MIN`); aprovado vale 30 min para ser usado, uma vez | O contexto de uma ação envelhece rápido. |
| P12 | Quem decide | No Telegram, só o `TELEGRAM_CHAT_ID` (e os ids de `aprovador_telegram_usuarios`, se houver); na tela, quem passou pelo Authelia (`Remote-User`), com `Origin` conferido no POST | O clique de outra pessoa num grupo ou de outra página não aprova nada. |
| P13 | Registro | Linha JSON por evento (`evento: aprovacao`: criado, aprovado, recusado, expirado, usado) e o `ops` registra `aguardando` na auditoria | Loki e Grafana mostram quem pediu o quê e quem decidiu. |
| P14 | Repositórios e GitHub | `/repos` no disco local da VM (`{{ vm_local_data_path }}/posto/repos`); `gh` na imagem com `GH_TOKEN` opcional (`posto_github_token`, token de escopo mínimo) | Os agentes trabalham em clones; o PR sai pelo `gh` ou pela integração do próprio Vibe Kanban. |

## 3. Riscos

- **Compilação longa:** o primeiro `setup-posto-volumes.yml` compila o Vibe Kanban (Rust) na `ai-desktop-vm`; dezenas de minutos. Só repete quando a versão muda.
- **Projeto com futuro incerto:** se o Vibe Kanban parar, o posto (Claude Code), o `aprovador` e a rota `autonomos` continuam; só a tela muda.
- **Agente com `AUTONOMO`:** dentro do container ele faz o que quiser (rede, arquivos dos clones). Fora dele, só pelo `ops`, com aprovação.
- **Telegram fora:** o pedido continua na tela `aprovacoes.`.
