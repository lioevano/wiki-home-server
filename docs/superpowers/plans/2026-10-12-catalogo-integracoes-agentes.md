# Catálogo de aplicações, índice de integrações e camada de agentes — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar a adição/remoção de aplicações e integrações declarativa (catálogo + índice de integrações na wiki), executada por skills portáveis para qualquer LLM, com `INDEX.md` mantido pela LLM e o gerador de índice removido.

**Architecture:** Dois documentos declarativos na wiki (catálogo = fatos; índice de integrações = regras com provedor, "aplica-se a", regras verificáveis e passos). Skills em `.agents/skills/` (formato Agent Skills) leem esses documentos, auditam e planejam; a execução segue `wiki-first-change`. Código fica restrito a `wikisync check/apply`, `dev.py` e CI.

**Tech Stack:** Markdown (MkDocs Material), Agent Skills (`SKILL.md`), git; Python existente só para `check/apply/test/build`.

**Spec:** `docs/superpowers/specs/2026-10-12-catalogo-integracoes-agentes-design.md`

## Global Constraints

- **Nenhum código Python novo.** A única mudança de código é remoção (gerador de índice).
- Português em páginas, skills e mensagens; UTF-8 sem BOM, LF.
- Skill canônica: `.agents/skills/<nome>/SKILL.md` com front-matter `name` e `description` iniciando por "Use when".
- Invólucro: `.claude/skills/<nome>/SKILL.md` com o **mesmo** front-matter e corpo exatamente `Leia e siga integralmente \`.agents/skills/<nome>/SKILL.md\`.`
- Páginas novas: `wiki/docs/02-visao-geral-arquitetura/09-catalogo-aplicacoes.md` e `10-indice-integracoes.md`, com `description:` e no `nav` da seção Arquitetura, após `08-apis-llm-estrategia.md`.
- Valores do catálogo exatamente: Categoria ∈ {`infra`, `produtividade`, `mídia`, `monitoramento`, `automação`, `ia`}; Exposição ∈ {`publica`, `protegida`, `interna`}; Dados ∈ {`nfs`, `local`, `nenhum`}; Métricas ∈ {`sim`, `não`}.
- Status da auditoria exatamente: `✅`, `❌ <REGRA>`, `⚠️ <REGRA>`, `✋`, `—`.
- Skills de mudança **param para aprovação do plano** antes de editar.
- Testes de skills rodam em cópia descartável `$HOME/hs-test` (clone local fora da pasta montada), nunca na pasta do usuário.
- Commits terminam com:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_011krkX9xaitppbasvKKgK5w
  ```

## Ambiente de execução

- Arquivos no computador do usuário via `device_bash` em `$HOME/mnt/homeserver`; venv em `$HOME/.venvs/homeserver` (`export HOMESERVER_VENV=$HOME/.venvs/homeserver`).
- Permissão de deleção na pasta foi concedida nesta sessão (git precisa apagar locks).
- Subagentes de teste usam `mcp__remote-devices__device_bash` e trabalham só em `$HOME/hs-test`.

## Review Focus

1. **Aplicação com vários serviços onde só um é exposto** (nextcloud + banco + redis): regras de roteamento/autenticação valem para o **serviço principal** (o primeiro da coluna Serviços); a auditoria não acusa o banco por não ter router — fixado no catálogo (T3) e nas regras ROT/AUT (T4), e conferido no cenário 1 (T5).
2. **Aplicação fora do compose** (Portainer via Ansible, `ansible:infra/docker`): integrações buscam evidência no role/labels do task Ansible, não em compose — regra escrita em T4, conferida no cenário 1.
3. **Regra curinga do Authelia** (`*.{{ base_domain }}` → `two_factor`): satisfaz o controle de acesso de apps `protegida`; `publica` exige `bypass` explícito antes do curinga — regra AUT em T4, conferida no cenário 1.
4. **Variáveis compartilhadas** (`SYSTEM_TIMEZONE`, `DOCKER_PUID`, `BASE_DOMAIN_FROM_VAULT`): remover uma aplicação não remove variável ainda usada por outra — passo "Ao remover" de VAR em T4; asserção no cenário 3 (T7).
5. **Serviço no compose sem linha no catálogo**: auditoria acusa `⚠️ DOC-<n>` (sobra) — regra em T4; asserção no cenário 1 com um serviço fictício injetado na cópia (T5).

---

### Task 1: Remover o gerador de índice

**Files:**
- Delete: `tools/wikisync/index.py`, `tools/wikisync/tests/test_index.py`, `index.json`
- Modify: `tools/wikisync/cli.py` (remover `_cmd_index` e o subparser `index`), `tools/dev.py` (remover `task_index`, a entrada `"index"` em `TASKS` e a linha `index` da docstring)

**Interfaces:**
- Produces: CLI `python -m wikisync` só com `check` e `apply`; `dev.py` sem `index`.

- [ ] **Step 1:** Remover arquivos e trechos acima.
- [ ] **Step 2:** `python3 tools/dev.py test` → todos passam (contagem esperada: 55 − testes de `test_index.py`).
- [ ] **Step 3:** `PYTHONPATH=tools $HOMESERVER_VENV/bin/python -m wikisync index; echo $?` → `2` (subcomando inválido); `python3 tools/dev.py index; echo $?` → imprime ajuda e `2`.
- [ ] **Step 4:** `grep -rn "dev.py index\|index.json\|wikisync index" --include=*.md --include=*.py --include=*.yml . | grep -v docs/superpowers` → lista de menções a ajustar; ajustar `CLAUDE.md`, `README.md`, skills (`wiki-first-change`, `add-ansible-component`) trocando "rode `dev.py index`" por "use a skill `update-index`". Esperado depois: nenhuma linha.
- [ ] **Step 5:** `python3 tools/dev.py check` → só o erro pré-existente do `vault.yml`.
- [ ] **Step 6: Commit** `refactor: remove gerador de índice (INDEX.md passa a ser mantido pela skill update-index)`.

### Task 2: Camada de agentes (AGENTS.md, skills canônicas, invólucros)

**Files:**
- Create: `AGENTS.md`, `wiki/AGENTS.md`, `server/AGENTS.md`
- Modify: `CLAUDE.md`, `wiki/CLAUDE.md`, `server/CLAUDE.md`
- Move (git mv): `.claude/skills/{wiki-first-change,sync-wiki-server,wiki-page-authoring,add-ansible-component,validate-infra}/` → `.agents/skills/…/`
- Create: invólucros `.claude/skills/<nome>/SKILL.md` para os 5
- Delete: `.claude/skills/add-docker-service/`
- Modify: `tools/wikisync/config.yml` (`ignore_orphans` ganha `AGENTS.md`)

**Interfaces:**
- Produces: `AGENTS.md` com seção `## Skills` em tabela `| Skill | Quando usar | Caminho |` (T5–T7 acrescentam linhas).

- [ ] **Step 1:** `AGENTS.md` ← conteúdo atual de `CLAUDE.md` (substituindo "Claude" por "agente" onde genérico) + seção `## Skills` com as 5 skills migradas + linha `Catálogo e integrações: wiki/docs/02-visao-geral-arquitetura/09-catalogo-aplicacoes.md e 10-indice-integracoes.md`. Idem `wiki/AGENTS.md` e `server/AGENTS.md` a partir dos `CLAUDE.md` correspondentes.
- [ ] **Step 2:** Cada `CLAUDE.md` vira: `@AGENTS.md` na primeira linha + seção curta "Particularidades do Claude Code" (raiz: skills carregadas de `.claude/skills/`, permissões em `.claude/settings.json`; subpastas: só a importação).
- [ ] **Step 3:** `git mv` das 5 skills; criar invólucros conforme Global Constraints; `git rm -r .claude/skills/add-docker-service`.
- [ ] **Step 4: Verificar** com um laço shell: para cada `.claude/skills/*/SKILL.md`, as linhas `name:`/`description:` são idênticas às do canônico e o corpo aponta para um arquivo existente. Esperado: `0 divergências`. E `ls .agents/skills` → 5 pastas.
- [ ] **Step 5:** `python3 tools/dev.py check` → sem novos achados (o `server/AGENTS.md` não pode virar `ORPHAN`).
- [ ] **Step 6: Commit** `agents: AGENTS.md canônico e skills em .agents/skills com invólucros para o Claude Code`.

### Task 3: Catálogo de aplicações

**Files:**
- Create: `wiki/docs/02-visao-geral-arquitetura/09-catalogo-aplicacoes.md`
- Modify: `wiki/mkdocs.yml` (nav)

- [ ] **Step 1:** Página com: front-matter `description`; `# Catálogo de Aplicações`; seção "Como usar" (adicionar/remover começa aqui; `?` exige decisão humana; **o primeiro serviço da coluna Serviços é o principal**, que recebe roteamento/autenticação; apps fora do compose usam `ansible:<role>` em Stack/VM); legenda das colunas (spec §4); a tabela.
- [ ] **Step 2:** Preencher uma linha por aplicação lendo `server/docker/stacks/{core,apps,ai}/docker-compose.yml`, `ansible/templates/prometheus.yml.j2`, o template do Authelia e as páginas 05–08: `traefik`, `cloudflared`, `authelia`, `portainer` (`ansible:infra/docker`), `nextcloud`, `jellyfin`, `sonarr`, `radarr`, `qbittorrent`, `prometheus`, `grafana`, `loki`, `promtail`, `n8n`, `homeassistant` (ou o nome real no compose), `ollama`, `litellm`, `open-webui`, `openclaw`, `openclaude` — e qualquer outro serviço principal encontrado. Coluna **Provê**: `traefik`→`roteamento`, `authelia`→`autenticacao`, `cloudflared`→`acesso-externo`, `prometheus`→`metricas`, `loki`→`logs`, `litellm`→`llm`. Valor não deduzível com certeza → `?`.
- [ ] **Step 3: Verificar** que todo serviço de todos os composes aparece em exatamente uma linha (laço shell: extrair nomes de `services:` e `grep` na página). Esperado: `0 serviços sem aplicação`.
- [ ] **Step 4:** `nav` atualizado; `python3 tools/dev.py check` (sem `NAV`/`DESC`/`LINK` novos) e `python3 tools/dev.py build` (0 WARNING).
- [ ] **Step 5: Commit** `wiki: catálogo de aplicações`.

### Task 4: Índice de integrações

**Files:**
- Create: `wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md`
- Modify: `wiki/mkdocs.yml` (nav)

- [ ] **Step 1:** Página com `description`, `# Índice de Integrações`, legenda (sintaxe de "Aplica-se a": `<Coluna> = <valor>`, `≠`, `todas`; `+<id>` habilita integração opcional via Ajustes; `-<id>` exclui; status da auditoria) e uma seção `## <id>` por integração no formato fixo da spec §5 (tabela Provedor/Aplica-se a/Arquivos/Páginas/Manual; `### Regras`; `### Ao adicionar (por consumidor)`; `### Ao remover (por consumidor)`; `### Ao remover o provedor`).
- [ ] **Step 2:** Escrever as 9 integrações (`roteamento` ROT, `autenticacao` AUT, `acesso-externo` EXT, `metricas` MET, `logs` LOG, `dados` DAD, `variaveis` VAR, `llm` LLM, `documentacao` DOC), cada regra com *Evidência* concreta (arquivo e o que procurar), incluindo obrigatoriamente:
  - ROT/AUT aplicadas ao **serviço principal**; para `ansible:` a evidência é o task/labels no role.
  - AUT: `protegida` → middleware `authelia-forwardauth@docker` no router **e** coberta pela regra `*.{{ base_domain }}` → `two_factor`; `publica` → regra `bypass` para o subdomínio **antes** do curinga no `configuration.yml.j2` (bloco literal na página 05).
  - VAR "Ao remover": só retirar variáveis que nenhum outro serviço usa (`grep` em todos os composes antes).
  - DOC (sobra): serviço presente em compose sem linha no catálogo; linha no catálogo sem serviço.
  - Pelo menos uma regra **(sobra)** em ROT, MET, VAR e DOC.
- [ ] **Step 3: Verificar** a forma: cada `## <id>` tem as 5 subseções; IDs de regra únicos (`grep -o '\*\*[A-Z]\{3\}-[0-9]\+\*\*' | sort | uniq -d` → vazio); todo id de integração citado no catálogo (Provê/Ajustes) existe no índice.
- [ ] **Step 4:** `nav`; `check` e `build` como em T3.
- [ ] **Step 5: Commit** `wiki: índice de integrações`.

### Task 5: Skill `audit-integrations` (cenário 1)

**Files:**
- Create: `.agents/skills/audit-integrations/SKILL.md`, `.claude/skills/audit-integrations/SKILL.md`
- Modify: `AGENTS.md` (linha na tabela Skills)

- [ ] **Step 1: RED (linha de base):** clonar `$HOME/hs-test` a partir da pasta; injetar no `server/docker/stacks/apps/docker-compose.yml` da cópia um serviço fictício `teste-fantasma` (imagem `busybox:1.36`, sem labels). Despachar subagente **sem a skill** com: "Leia AGENTS.md; audite as integrações de todas as aplicações contra o catálogo e o índice de integrações e devolva o resultado." Registrar: formato da saída, se acusou `teste-fantasma`, se acusou indevidamente o banco do Nextcloud.
- [ ] **Step 2:** Escrever a skill: description "Use when asked to verify integrations, before/after adding or removing apps or integrations, or when catalog and server may disagree"; corpo: escopo (todas / uma aplicação / uma integração), procedimento (para cada linha do catálogo × cada integração: avaliar "Aplica-se a" + Ajustes → para cada regra, buscar a evidência indicada; depois rodar as regras **(sobra)** em todo o repositório), formato de saída fixo (tabela aplicação × integração com os status exatos; lista de `❌`/`⚠️` com `arquivo:linha` e ação sugerida), proibições (não editar nada; `?` no catálogo → status `?` e pergunta ao usuário).
- [ ] **Step 3: GREEN:** dois subagentes independentes **com a skill**, mesmo prompt + "siga .agents/skills/audit-integrations". Passa quando: ambos acusam `⚠️ DOC-<n>` para `teste-fantasma`; nenhum acusa `nextcloud_db` por roteamento; Portainer avaliado por evidência Ansible; e os conjuntos de `❌`/`⚠️` das duas execuções coincidem. Divergência → reescrever as regras ambíguas em T4 e repetir.
- [ ] **Step 4:** Descartar a cópia (`rm -rf $HOME/hs-test`). Guardar a tabela de auditoria do estado real (sem o fantasma) para T8.
- [ ] **Step 5: Commit** `skills: audit-integrations`.

### Task 6: Skill `update-index` e novo `INDEX.md`

**Files:**
- Create: `.agents/skills/update-index/SKILL.md`, `.claude/skills/update-index/SKILL.md`
- Modify: `INDEX.md` (reescrito), `AGENTS.md`

- [ ] **Step 1:** Escrever a skill com o formato da spec §6 (5 seções fixas, ordem alfabética, confirmar existência antes de listar, atualizar só as seções afetadas, cabeçalho `<!-- Mantido pela skill update-index — edite por ela -->`), e quando rodar (fim de toda skill de mudança; depois de criar/renomear página ou arquivo).
- [ ] **Step 2:** Executar a skill (eu mesmo) para reescrever o `INDEX.md` inteiro.
- [ ] **Step 3: Verificar** com laço shell: todo caminho entre crases nas seções 4 e 5 existe; toda página `wiki/docs/**/*.md` e todo arquivo versionado de `server/` aparece; toda skill de `.agents/skills/` aparece na seção 1; toda aplicação do catálogo na seção 2; toda integração na seção 3. Esperado: `0 faltando, 0 inexistentes`.
- [ ] **Step 4: Commit** `skills: update-index; INDEX.md no novo formato`.

### Task 7: Skills de mudança (cenários 2, 3, 4)

**Files:**
- Create: `.agents/skills/{add-app,remove-app,add-integration,remove-integration}/SKILL.md` e invólucros
- Modify: `AGENTS.md`

- [ ] **Step 1: RED:** em cópia nova `$HOME/hs-test`, subagente sem as skills novas (só AGENTS.md e as skills migradas) recebe o cenário 3: "Remova a aplicação jellyfin." Registrar resíduos deixados (labels, variáveis `MEDIA_STACK_JELLYFIN_*`, volumes, linha no catálogo, menções nas páginas, `INDEX.md`) e se removeu variáveis compartilhadas.
- [ ] **Step 2:** Escrever as 4 skills seguindo o fluxo comum e as regras específicas da spec §6: plano em tabela `# · integração/regra · arquivo ou página · ação` + passos manuais; **parar para aprovação**; executar via `wiki-first-change`; `audit-integrations` até zerar o que for atribuível à mudança; `update-index`; `validate-infra`; commit. `remove-app` de provedor bloqueia e exige `remove-integration`. `add-app`/`add-integration` exigem pesquisa da documentação oficial com fontes citadas na página.
- [ ] **Step 3: GREEN — cenário 2** (cópia nova): "Adicione o Uptime Kuma (louislam/uptime-kuma:1.23.13), protegido, dados locais, sem métricas." O subagente recebe a aprovação automática do plano no prompt ("plano aprovado; prossiga") **somente depois** de devolver o plano numa primeira rodada (confirma a parada). Passa quando: linha no catálogo; labels/middleware; variável no `.env.template`; aviso de backup; `audit-integrations` sem `❌`/`⚠️` para `uptime-kuma`; `INDEX.md` atualizado; `check` sem erros novos.
- [ ] **Step 4: GREEN — cenário 3** (cópia nova): remover `jellyfin`. Passa quando: nenhum resíduo do Step 1; `SYSTEM_TIMEZONE`, `DOCKER_PUID`, `DOCKER_PGID`, `BASE_DOMAIN_FROM_VAULT` continuam no `.env.template`; auditoria limpa para o resto.
- [ ] **Step 5: GREEN — cenário 4** (cópia nova): remover `prometheus`. Passa quando: a skill para e exige `remove-integration metricas`; após aprovação, nenhum job sobra no `prometheus.yml.j2` (ou o arquivo e o playbook que o usa são tratados), coluna Métricas/Provê coerentes, catálogo sem `prometheus`, auditoria sem `⚠️ MET-*`.
- [ ] **Step 6:** Ajustar skills (ou regras do índice em T4) até os 3 cenários passarem; descartar cópias.
- [ ] **Step 7: Commit** `skills: add-app, remove-app, add-integration, remove-integration`.

### Task 8: Integração final, auditoria real e revisão

**Files:**
- Modify: `.agents/skills/wiki-first-change/SKILL.md` (passo 1 lê catálogo/índice de integrações; aponta `add-app`/`remove-app`), `wiki/docs/03-guias-sustentacao/01-adicionando-novo-servico-docker.md` (admonition no topo apontando catálogo + índice de integrações como fonte do checklist), `AGENTS.md` (tabela Skills final com as 11), `INDEX.md` (via `update-index`)

- [ ] **Step 1:** Aplicar as modificações acima; `update-index`.
- [ ] **Step 2:** Rodar `audit-integrations` no estado real; enviar ao usuário a tabela + os `?` do catálogo + desvios reais encontrados (registrados como pendências, não corrigidos — spec §9).
- [ ] **Step 3:** Incorporar as decisões do usuário sobre os `?` (o critério de pronto exige nenhum `?` após a revisão).
- [ ] **Step 4:** `python3 tools/dev.py test`, `check` (só o `vault.yml` pendente), `build` (0 WARNING); verificação de invólucros de T2 repetida para as 11 skills.
- [ ] **Step 5:** Revisão independente do branch (subagente no modelo mais capaz) contra spec e plano; correções importantes com verificação.
- [ ] **Step 6: Commit** `agents: integra catálogo e índice de integrações ao fluxo; auditoria inicial` e propor `add-app`, `remove-app` e `audit-integrations` para a conta do usuário (limite de 3 por proposta).
