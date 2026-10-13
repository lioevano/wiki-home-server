# Design: catálogo de aplicações, índice de integrações e camada de agentes independente de LLM

- **Data:** 2026-10-12
- **Autor:** Léo Ivan (com Claude)
- **Status:** aguardando revisão
- **Caminho:** arquitetural — sub-projeto **A** (ferramental declarativo). O sub-projeto **B** (dashboard e notificações via n8n) virá depois, usando este ferramental.
- **Depende de:** `2026-10-07-homeserver-claude-project-design.md` (wiki como fonte da verdade, `wikisync check/apply`, CI).

## 1. Objetivo

Permitir adicionar e remover **aplicações** e **integrações** com segurança, nos dois sentidos, guiado por documentos **declarativos em Markdown** interpretados por **qualquer LLM** — sem motor de código para as integrações.

1. Um **catálogo de aplicações** (fatos de cada aplicação) na wiki.
2. Um **índice de integrações** (regras declarativas: provedor, a quem se aplica, regras de verificação, passos de adicionar/remover) na wiki.
3. **Skills** em formato aberto, reutilizáveis por qualquer agente, que auditam e planejam mudanças a partir desses dois documentos.
4. Um **`INDEX.md`** mantido pela LLM que mapeia tudo (skills, aplicações, integrações, páginas, arquivos).
5. **Menos código** de manutenção: o gerador de índice sai; ficam só as travas determinísticas (`check`, `apply`).

### Critérios de pronto

- `AGENTS.md` (raiz, `wiki/`, `server/`) é a entrada canônica; os `CLAUDE.md` só importam `@AGENTS.md`.
- Skills canônicas em `.agents/skills/`; cada uma com invólucro em `.claude/skills/`; as 5 skills mantidas migradas, `add-docker-service` removida.
- Catálogo (`09-catalogo-aplicacoes.md`) com todas as aplicações das stacks `core`, `apps`, `ai` e o Portainer; nenhum `?` pendente após revisão do usuário.
- Índice de integrações (`10-indice-integracoes.md`) com as 9 integrações iniciais no formato fixo.
- `audit-integrations` executada no estado final sem `❌`/`⚠️` não justificados (desvios reais da infraestrutura são registrados como pendências, não escondidos).
- Os 4 cenários de teste com agente sem contexto (seção 8) passam.
- `dev.py test`, `dev.py check` (exceto o `vault.yml`, pendência do usuário) e `dev.py build` passam; não existe mais `index.json`, `tools/wikisync/index.py` nem tarefa `index`.

## 2. Decisões

| # | Decisão | Escolha |
|---|---|---|
| E1 | Escopo | Sub-projeto A primeiro; B (dashboard, n8n) depois, com `add-integration`. |
| E2 | Automação | Verificar **e planejar**; a execução segue `wiki-first-change` com aprovação do usuário. |
| E3 | Intenção das aplicações | Catálogo na wiki (tabela Markdown), sem arquivo no `server/`. |
| E4 | Verificação de integrações | **Somente LLM** guiada pelo índice declarativo; nenhum código novo, nem validação estrutural. |
| E5 | Portabilidade | `AGENTS.md` + `.agents/skills/` (formato aberto Agent Skills); `.claude/` só com importação/invólucros. |
| E6 | Índice do repositório | `INDEX.md` mantido pela skill `update-index`; gerador de código removido. |
| E7 | Código que permanece | `wikisync check` e `apply` (trava no CI e cópia literal exata), `dev.py`, CI. |
| E8 | Bidirecionalidade | Catálogo guarda **fatos**; integrações declaram **provedor** e **aplica-se a**; quatro operações simétricas (add/remove app, add/remove integração). |

## 3. Camada de agentes

```
homeserver/
├── AGENTS.md                       entrada canônica (conteúdo do CLAUDE.md atual + tabela de skills)
├── CLAUDE.md                       "@AGENTS.md" + particularidades do Claude Code
├── wiki/AGENTS.md  wiki/CLAUDE.md  idem para a wiki
├── server/AGENTS.md server/CLAUDE.md idem para o server
├── .agents/skills/<nome>/SKILL.md  skills canônicas
└── .claude/skills/<nome>/SKILL.md  invólucros
```

- **`AGENTS.md`**: regra de ouro, comandos `dev.py`, segurança, onde procurar, e uma tabela **Skills** (nome · quando usar · caminho) para LLMs que não carregam skills automaticamente.
- **Skill canônica**: front-matter `name` + `description` ("Use when …", terceira pessoa) e corpo em português.
- **Invólucro** `.claude/skills/<nome>/SKILL.md`: o mesmo front-matter e o corpo `Leia e siga integralmente .agents/skills/<nome>/SKILL.md.` (sem symlinks — quebram no git do Windows).
- **Permissões** (`.claude/settings.json`): sem mudança.

## 4. Catálogo de aplicações

**Página:** `wiki/docs/02-visao-geral-arquitetura/09-catalogo-aplicacoes.md` (no `nav`, seção Arquitetura), com front-matter `description`.

**Tabela** — uma linha por aplicação (o que o usuário enxerga; serviços auxiliares entram na coluna Serviços):

| Coluna | Valores |
|---|---|
| Aplicação | id único em kebab-case (`nextcloud`) |
| Categoria | `infra` · `produtividade` · `mídia` · `monitoramento` · `automação` · `ia` |
| Stack / VM | `<stack>` / `<vm>` (ex.: `apps` / `core-services-vm`) |
| Serviços | nomes exatos no `docker-compose.yml`, separados por vírgula |
| Exposição | `publica` · `protegida` · `interna` |
| Subdomínio | subdomínio, ou `—` se `interna` |
| Dados | `nfs` · `local` · `nenhum` |
| Métricas | `sim` · `não` |
| Provê | ids de integrações que a aplicação fornece, ou `—` |
| Ajustes | `-<id>` sai de uma integração que se aplicaria; `+<id>` entra numa integração opcional; ou `—` |
| Página | link relativo para a página da wiki que documenta a aplicação |

**Regras do catálogo** (escritas no topo da página):
- Adicionar/remover aplicação **começa** por esta tabela.
- Valor incerto é marcado `?` e precisa de decisão humana antes de qualquer mudança derivada.
- Aplicações instaladas fora do compose (ex.: Portainer, via Ansible) entram com Stack/VM indicando o role (`ansible:infra/docker`).

## 5. Índice de integrações

**Página:** `wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md` (no `nav`).

**Topo:** legenda — sintaxe de "Aplica-se a" (`<coluna> = <valor>`, `≠`, `todas`, `+<id>` opcional via Ajustes; `-<id>` sempre exclui), significado dos status da auditoria.

**Formato fixo por integração** (seção `## <id>`):

| Campo | Conteúdo |
|---|---|
| Provedor | aplicação do catálogo (ou `infra` quando não é uma aplicação) |
| Aplica-se a | regra sobre os fatos do catálogo |
| Arquivos | caminhos relativos a `server/` (com `<stack>`/`<app>` como variáveis) |
| Páginas | páginas da wiki envolvidas |
| Manual | passos fora do repositório, ou `—` |

Seguido de:
- `### Regras` — itens `**<PREFIXO>-<n>** — afirmação verificável. *Evidência:* onde olhar.` Regras marcadas **(sobra)** verificam o inverso (resíduos).
- `### Ao adicionar (por consumidor)` — passos numerados.
- `### Ao remover (por consumidor)` — passos numerados.
- `### Ao remover o provedor` — o que fazer com os consumidores.

**Integrações iniciais:**

| id | Prefixo | Provedor | Aplica-se a | Essência |
|---|---|---|---|---|
| `roteamento` | ROT | traefik | exposição ≠ interna | router com `Host(<subdomínio>.${BASE_DOMAIN_FROM_VAULT})`, rede `proxy`; (sobra) nada exposto fora do catálogo |
| `autenticacao` | AUT | authelia | exposição ≠ interna | `protegida` → middleware `authelia-forwardauth@docker`; `publica` → regra `bypass` no `configuration.yml.j2` |
| `acesso-externo` | EXT | cloudflared | exposição ≠ interna | manual: hostname público na Cloudflare; registrado na página da aplicação |
| `metricas` | MET | prometheus | métricas = sim | job em `ansible/templates/prometheus.yml.j2`; (sobra) job sem aplicação |
| `logs` | LOG | loki (+promtail) | todas | serviço não sobrescreve `logging:` |
| `dados` | DAD | infra (ZFS/NFS) | dados ≠ nenhum | `nfs` → volume sob `${VM_NFS_MOUNT_BASE_PATH}`; `local` → aviso de backup na página + página de backup |
| `variaveis` | VAR | infra (Ansible/Portainer) | todas | toda `${VAR}` do serviço no `.env.template` e no `setup-<stack>-volumes.yml`; (sobra) variável sem uso |
| `llm` | LLM | litellm | `+llm` | consumidor usa o LiteLLM, não APIs diretas |
| `documentacao` | DOC | wiki | todas | linha no catálogo, seção na página da stack, entrada no `INDEX.md` |

## 6. Skills

| Skill | Situação | Quando usar (description) |
|---|---|---|
| `wiki-first-change` | migra (passa a citar catálogo/índice) | qualquer mudança na infraestrutura |
| `sync-wiki-server` | migra | `dev.py check` com achados |
| `wiki-page-authoring` | migra | criar/editar página |
| `add-ansible-component` | migra | role, playbook, grupo ou variável |
| `validate-infra` | migra | antes de commitar/entregar |
| `add-docker-service` | **removida** | — |
| `add-app` | nova | adicionar aplicação |
| `remove-app` | nova | remover aplicação |
| `add-integration` | nova | criar integração e ligá-la nos consumidores |
| `remove-integration` | nova | desligar integração de todos e remover provedor |
| `audit-integrations` | nova | verificar catálogo × índice × arquivos |
| `update-index` | nova | manter o `INDEX.md` |

**Fluxo das skills de mudança** (`add-app`, `remove-app`, `add-integration`, `remove-integration`):
1. Ler catálogo e índice de integrações.
2. Calcular consumidores/integrações afetados pelas regras "Aplica-se a" e pelos Ajustes.
3. Produzir o **plano**: tabela `# · integração/regra · arquivo ou página · ação`, mais passos manuais.
4. **Parar e pedir aprovação** do plano.
5. Executar via `wiki-first-change` (catálogo/índice/páginas primeiro, depois `check` → `sync`).
6. `audit-integrations` até não restar `❌`/`⚠️` atribuível à mudança.
7. `update-index`, validação (`validate-infra`) e commit único.

**Regras específicas:**
- `remove-app` de uma aplicação que **provê** integração: lista os consumidores e exige `remove-integration` (ou substituição do provedor) antes; nunca deixa consumidores órfãos.
- `add-app` de uma aplicação que provê integração: oferece `add-integration` em seguida.
- `add-integration`: a seção nova no índice segue o formato fixo; o plano cobre **todos** os consumidores atuais.
- Pesquisa: ao adicionar aplicação/integração, consultar a documentação oficial (versão estável para fixar imagem, portas, variáveis, volumes, healthcheck, `/metrics`, suporte a OIDC) e citar as fontes na página.

**`audit-integrations` — saída:** tabela aplicação × integração com `✅` ok · `❌ <REGRA>` falta · `⚠️ <REGRA>` sobra · `✋` manual pendente · `—` não se aplica; abaixo, a lista de `❌`/`⚠️` com evidência `arquivo:linha` e a ação sugerida. Escopo: todas as aplicações (padrão), uma aplicação ou uma integração.

**`update-index` — formato do `INDEX.md`** (seções fixas, nesta ordem):
1. Agentes e skills — skill · quando usar · caminho.
2. Aplicações — aplicação · stack · integrações ativas · página.
3. Integrações — id · provedor · aplica-se a · link para a seção.
4. Páginas da wiki — caminho · título · descrição.
5. Arquivos do server — caminho · tipo · página que documenta.
Regras: ordenar alfabeticamente dentro de cada seção; nunca listar arquivo/página sem confirmar que existe; atualizar apenas as seções afetadas pela mudança; cabeçalho dizendo que é mantido pela skill `update-index`.

## 7. Mudanças no código e documentação existentes

- Remover `tools/wikisync/index.py`, `tools/wikisync/tests/test_index.py`, o subcomando `index` em `cli.py`, a tarefa `index` em `dev.py`, o arquivo `index.json` e a menção ao gerador em `AGENTS.md`/README.
- `INDEX.md` reescrito no novo formato pela `update-index`.
- `wiki/mkdocs.yml`: `nav` com as páginas 09 e 10 na seção Arquitetura.
- Página `03-guias-sustentacao/01-adicionando-novo-servico-docker.md`: aponta para catálogo + índice de integrações como fonte do checklist.
- `wikisync check` passa a ver as novas páginas normalmente (DESC, NAV, LINK).

## 8. Testes das skills

Com agente sem contexto, numa cópia descartável do repositório fora da pasta do usuário (como na entrega anterior):

1. **Auditoria** do estado atual, duas execuções independentes; as tabelas devem coincidir nos `❌`/`⚠️` (divergência → endurecer a redação das regras).
2. **`add-app`** de uma aplicação nova (ex.: Uptime Kuma, protegida, dados locais): plano correto, wiki antes do server, auditoria limpa.
3. **`remove-app`** de aplicação comum (ex.: `jellyfin`): nenhum resíduo (labels, variáveis, volumes, documentação).
4. **`remove-app` de provedor** (ex.: `prometheus`): exige `remove-integration metricas` e limpa os jobs dos consumidores.

Cada cenário roda antes da skill final (linha de base) e depois; ajustes até passar.

## 9. Fora de escopo

- Dashboard (Homepage) e notificações (n8n) — sub-projeto B.
- Corrigir os desvios reais que a primeira auditoria encontrar além de registrá-los (viram pendências para o usuário decidir).
- Refatoração do inventário/variáveis anunciada pelo usuário.

## 10. Riscos

| Risco | Mitigação |
|---|---|
| Auditoria não determinística | regras com ID e evidência obrigatória; cenário 1 mede a divergência |
| `INDEX.md` desatualizado (sem gerador) | `update-index` é o último passo de toda skill de mudança; `audit-integrations` aponta a regra `DOC` |
| Remoção de provedor deixa consumidores órfãos | `remove-app` bloqueia até `remove-integration` |
| LLM sem suporte a skills ignora `.agents/skills/` | `AGENTS.md` lista as skills com caminho e "quando usar" |
