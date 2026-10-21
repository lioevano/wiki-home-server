# Design: pendências menores dos sub-projetos 1, 2, 3, 4a, 4b, 4c1 e B

- **Data:** 2026-10-20
- **Autor:** Léo Ivan (com Claude)
- **Status:** decidido de forma autônoma, a pedido do Léo ("faça o máximo das tarefas autonomamente, decisões e sugestões de melhorias"). Cada decisão está registrada abaixo para revisão posterior.
- **Caminho:** arquitetural, porque mexe em várias stacks, roles e no `ops`. Execução no modo "direta" (no `main`, com teste antes da correção, revisor final em contexto novo).
- **Origem:** lista "Pendências menores" do `contexto-homeserver.md` (projeto homeserver) e as pendências do sub-projeto B.

## 1. Objetivo

Fechar, antes do primeiro deploy, as pendências adiadas nas revisões finais dos sub-projetos. Fora do escopo: os "itens adiados" maiores (backup automatizado, fusão de guias, nome legado "rag", fluxo do `apps.env`, VPN). Eles seguem como sub-projetos próprios.

Cada pendência recebe uma de quatro decisões:

- **corrigir:** muda agora (wiki → server, com teste quando há código ou template);
- **aceitar:** o comportamento fica como está, e o motivo é documentado na página;
- **adiar:** vai para o sub-projeto em que faz sentido;
- **conferir:** só dá para validar com o servidor rodando. Entra na lista "A conferir no primeiro deploy" da página.

### Critérios de pronto

- `dev.py test`, `check` (só o `REF-PENDING` do `vault.yml`), `build` estrito e **`lint` verde**.
- O CI `server-lint` volta a passar (ele falha desde a stack `photos`).
- Cada correção é refletida na wiki (literal ou citação) e no `INDEX.md` quando surgir arquivo novo.
- Revisão final sem achados críticos.

## 2. Achado novo (fora da lista): CI vermelho

O `dev.py lint` roda `docker compose config -q` em cada stack **sem variáveis**. Os volumes `${X}:/caminho` viram `:/caminho`, e o compose recusa. Por isso o workflow `server-lint` falha em todo push desde 2026-10-19.

**Decisão: corrigir.** O `lint` passa a gerar um arquivo de variáveis temporário a partir do `docker/stacks/.env.template`. Cada valor vazio vira um marcador não vazio (`/lint/<NOME>` para caminhos, `lint` para os demais), e o arquivo vai em `--env-file`. Isso também **impõe a regra do `server/AGENTS.md`**: uma variável usada no compose e ausente do template gera aviso do compose, e o `lint` falha. O `dev.py test` passa a mostrar o motivo dos testes pulados (`-rs`).

## 3. Decisões por sub-projeto

### 4c1 — agentes (base)

| # | Pendência | Decisão | Como |
|---|---|---|---|
| 1 | `runner.aplicar` consome o plano antes da trava | corrigir | Pegar a trava primeiro. Só então validar e consumir o plano. Recusa por "outra execução em andamento" não queima o plano. |
| 2 | Tempo esgotado do Ansible devolve bytes e pode deixar `ssh` filho | corrigir | `Popen` com `start_new_session=True`. No tempo esgotado, `killpg` do grupo inteiro, e a saída parcial é decodificada (bytes → texto). |
| 3 | `cliente` ausente do registro do `ops` e dos logs do hub | corrigir | Hub: `config.logging.fields.add.cliente = apiKey.cliente` e cabeçalho `x-homeserver-cliente` (de `apiKey.cliente`) enviado aos alvos `ops`. `ops`: lê o cabeçalho (só o hub chega até ele, pelo token interno) e grava `cliente` no JSON da auditoria e no aviso. |
| 4 | `grafana: "*"` na leitura deixa ler logs brutos pelo Loki | aceitar | A rota de leitura exige 2FA do Authelia e o grupo `admins`, ou seja, a mesma pessoa que tem acesso total. Ler logs é o motivo da 4c2. Documentado na página 13 que os logs do Loki chegam **sem máscara**, ao contrário dos do `ops`. |
| 5 | TZ do Langfuse deveria ser UTC | corrigir | `TZ=UTC` nos containers do Langfuse. O ClickHouse e o worker comparam timestamps em UTC; a tela converte para o fuso do navegador. |
| 6 | `ops_containers_protegidos` sem `authelia_db`, Portainer Agent e n8n | corrigir | Entram `authelia_db`, `portainer_agent` e `n8n_app`: o n8n é o caminho dos avisos da própria IA. |
| 7 | Container com o mesmo nome nas duas VMs | corrigir | `_localizar` acha todos os containers com o nome. Se houver mais de um, exige o parâmetro `vm` (`container_logs`/`container_reiniciar` ganham `vm` opcional) e recusa com mensagem clara. |
| 8 | `__pycache__` dos testes no build da imagem | corrigir | `docker/images/ops/.dockerignore` com `**/__pycache__` e `**/*.pyc`. |
| 9 | Porta 4100 em HTTP puro | adiar | Sub-projeto VPN (Tailscale): a rota de controle passa a ser alcançada só pela VPN. |
| 10 | Página 13: recarregar `agents.env` ao liberar playbook; chave do runner no host Proxmox dispensável | corrigir | Texto: depois do `setup-agents-volumes.yml`, **Update the stack** `agents` no Portainer (o `.env` só vale na recriação). A chave pública do runner vai **só nas VMs**: nenhum playbook liberado roda no host Proxmox. |
| 11 | `statefulMode: stateless` da spec não configurado | corrigir | `statefulMode: stateless` nos dois backends do hub, validado com o binário 1.6.0. |
| 12 | `ops_leitura` com a chave admin do Portainer | aceitar | O Portainer CE não tem token só leitura. A instância `leitura` nem registra ferramentas de escrita, e a chave fica num container sem porta publicada. Documentado. |
| 13 | `ansible.cfg` com `stdout_callback = yaml` (saiu do community.general 12) | corrigir | `stdout_callback = default` + `callback_result_format = yaml` (ansible-core ≥ 2.13). As variáveis de contorno do `ops_controle` ficam redundantes e saem. |

### 4b — segundo cérebro

| # | Pendência | Decisão | Como |
|---|---|---|---|
| 14 | Cabeçalho `origem` do conversor sem escape de `"`/`\` | corrigir | Escapar `\` e `"` (YAML entre aspas duplas), com teste. |
| 15 | `quota` do `notes` conta snapshots | corrigir | `refquota=20G` no dataset `notes`, no lugar da `quota`. Os snapshots não roubam espaço de escrita. |
| 16 | Alerta `notes-timer-falhou` com `for: 0s` pode repetir | corrigir | A expressão passa a `max_over_time(...[30m])`: a falha que se repete a cada rodada (a unit volta a `activating` e cai de novo) mantém o alerta disparado em vez de resolver e disparar de novo a cada 10 min. Junto com o #34. |
| 17 | `notes-documentos` sem `RequiresMountsFor=` | corrigir | `RequiresMountsFor=` com a montagem do dataset `files` e a do `notes`. |
| 18 | Catálogo marca Dados de `notas` como `nfs` | aceitar | Conferido na execução: o `index.yml` do qmd (a configuração) fica no NFS (`docker-volumes/qmd/config`), e o índice e os documentos convertidos são cache regerável no disco local, como o cache de modelos do Immich. `nfs` está certo pela DAD-1. |
| 19 | `21027/udp` não publicado e `STGUIADDRESS` pelo padrão da imagem | corrigir / aceitar | `STGUIADDRESS=0.0.0.0:8384` explícito. A `21027/udp` (descoberta local por broadcast) não atravessa a ponte do Docker. Aceito e documentado: o PC e o celular usam o endereço fixo `tcp://<IP da ai-desktop-vm>:22000`. |
| 20 | Roots do cliente MCP podem trocar as pastas do server-filesystem | corrigir | `read_only: true` no container `notes_escrita` (com `tmpfs` em `/tmp`): mesmo que o cliente troque as roots, só `trabalho/` e `estudos/` aceitam escrita. Os outros caminhos do container são do sistema, sem dados. |
| 21 | Ordem de boot Docker × NFS | corrigir | Drop-in do `docker.service` com `After=remote-fs.target` e `Wants=remote-fs.target` (role `infra/docker`). Ordena sem exigir: o NFS fora não impede a core de subir. |

### 4a — fundação de IA

| # | Pendência | Decisão | Como |
|---|---|---|---|
| 22 | `decisao` aparece na lista do Open WebUI | corrigir | `litellm_key_models_ocultos: {openwebui: [decisao]}`. O `setup-ai-keys.yml` grava em cada chave o campo `models` com todos os modelos menos os ocultos (lista vazia = todos), na criação e na atualização. |
| 23 | Primeiro usuário OIDC vira admin; `ENABLE_PASSWORD_AUTH` segue ligado | corrigir | `ENABLE_PASSWORD_AUTH=${OPENWEBUI_LOGIN_FORM}`: quando o formulário sai, a API de senha também sai. O papel de admin vem do grupo (`OAUTH_ADMIN_ROLES`), com `DEFAULT_USER_ROLE=pending`. |
| 24 | `llm.`/`openwebui.` aceitam qualquer usuário do Authelia | corrigir | `authelia_dominios_admins` (main.yml) lista os subdomínios de administração. O Authelia ganha uma regra `two_factor` com `subject: group:admins` e logo depois uma `deny` para os mesmos domínios, ambas antes do curinga. |
| 25 | Imagem do Ollama não reconstrói se só o Dockerfile mudar | corrigir | O build usa `force_source` quando a cópia do Dockerfile mudou (`register`). |
| 26 | Timer do dump ativo antes do deploy | corrigir | O `backup-postgres.sh` sai com 0 e uma mensagem quando o container do banco não existe. O timer pode ficar ativo, e a falha real (container existe e o dump falha) continua falhando. |
| 27 | `diun_ai` em `:latest` | corrigir | `crazymax/diun:4.33.0` nas duas instâncias (`diun`, `diun_ai`). |

### 3 — fotos e arquivos

| # | Pendência | Decisão | Como |
|---|---|---|---|
| 28 | `--clientsecret-env` no hook | corrigir | `user_oidc:provider ... --clientsecret-env=NEXTCLOUD_OIDC_CLIENT_SECRET`: o segredo sai da linha de comando (`ps`). |
| 29 | `immich.json` no disco local | corrigir | O arquivo tem o segredo OIDC e hoje fica no NFS (`all_squash`). Passa para `{{ vm_local_data_path }}/immich-config/immich.json` (`0600`). |
| 30 | `pre_configured_consent_duration` nos clientes OIDC | corrigir | `pre_configured_consent_duration: 1y` em todos os clientes. O consentimento é pedido uma vez por ano, não a cada login. |
| 31 | `extra_hosts auth.` para login sem internet | corrigir | `auth.${BASE_DOMAIN_FROM_VAULT}:${CORE_SERVICES_VM_IP_VAR}` em quem fala com o Authelia por trás (Immich, Nextcloud, Open WebUI, Langfuse e os três mcp-auth-proxy). Descoberta e troca de código passam pela LAN. |
| 32 | `/auth/login?autoLaunch=0` na recuperação do Immich | corrigir | Página 11, seção de falhas: entrar com senha local quando o Authelia estiver fora. |
| 33 | Nextcloud cria conta para qualquer usuário do Authelia | corrigir | Política OIDC por cliente (`authorization_policies`, Authelia 4.38): `so_admins` (grupo `admins`) para Open WebUI, MCP e Langfuse; `familia` (grupo `users`) para Immich e Nextcloud. |
| 34 | Dump sem notificação de falha | corrigir | O coletor `systemd` do Alloy passa a incluir as units de dump (`backup-*`), e o alerta `notes-timer-falhou` vira `timer-falhou`, genérico, para qualquer unit monitorada que falhe. |
| 35 | `collabora/code:latest` sem versão | corrigir | `collabora/code:26.04.5.1.1`. |
| 36 | X-Frame-Options global no `office.` | conferir | O Collabora manda `Content-Security-Policy: frame-ancestors`, que nos navegadores atuais prevalece sobre o `X-Frame-Options`. Se o editor não abrir dentro do Nextcloud, a página 11 indica a saída: um middleware próprio para `office.`. |

### 2 — mídia

| # | Pendência | Decisão | Como |
|---|---|---|---|
| 37 | Widget `seerr` nativo na Homepage | conferir | A Homepage 2.x mantém o widget `jellyseerr` com a mesma API. Mantido; troca quando a imagem fixada tiver o `seerr`. |
| 38 | `init: true` no Seerr | corrigir | `init: true` (o Node como PID 1 não repassa sinais). |
| 39 | Recyclarr com `api_key` entre aspas e imagem `:8` | corrigir | Imagem `ghcr.io/recyclarr/recyclarr:8.8.0` e `api_key` **entre aspas** no template: uma chave hexadecimal como `123e45` viraria número no YAML. |
| 40 | `/dev/dri` do Jellyfin como `devices:` | adiar | A `core-services-vm` não tem GPU (a RX 5600 XT está na `ai-desktop-vm`). Fica para quando houver iGPU ou outra GPU em passthrough. Documentado como opcional na página 10. |
| 41 | `FIREWALL_INPUT_PORTS` redundante | aceitar | Sem efeito colateral e deixa explícita a porta da WebUI. Mantido. |
| 42 | Alertas entre as páginas 09 e 10 na instalação | corrigir | A página 10 manda rodar o `setup-monitoring-stack-volumes.yml` depois da stack `media` (sondas e alerta da VPN). |
| 43 | Guia 03/09 pode citar variáveis removidas | corrigir | Conferido contra o `.env.template`: o exemplo do Bazarr usava `MEDIA_STACK_MOVIES_PATH`/`TVSHOWS_PATH` (saíram com o `/data` único) e o compose da stack `apps`. Passa a montar `${MEDIA_STACK_DATA_PATH}/media` (DAD-4) no compose da `media`. |
| 44 | Prowlarr sem evento On Import | corrigir | Página 10: o Prowlarr só tem *On Health Issue*/*On Application Update*. |

### 1 — coleta (Alloy)

| # | Pendência | Decisão | Como |
|---|---|---|---|
| 45 | UFW da `ai-desktop-vm` só liga com `GUI_ENABLED` | corrigir | O UFW liga sempre: SSH, as portas de LAN de cada serviço e 12345 só a partir da core. |
| 46 | 9090 na LAN expõe `/-/quit`/`/-/reload` e aceita séries injetadas | corrigir | UFW da core: 9090 só para o host Proxmox e a `ai-desktop-vm` (os únicos que fazem `remote_write`). Sem `--web.enable-lifecycle`. |
| 47 | `test_alloy_validate` pula em silêncio | corrigir | `pytest -rs` no `dev.py test`: o motivo do pulo aparece. |
| 48 | Spec do Alloy cita `alloy fmt` e grupo `docker` | corrigir | Nota de atualização na spec. |
| 49 | Página 09 chama `textfile` de argumento | corrigir | Texto. |
| 50 | UFW `172.16.0.0/12` da core depende dos pools padrão do Docker | corrigir | `default-address-pools: [{base: 172.16.0.0/12, size: 24}]` no `daemon.json`. As regras de UFW passam a valer por construção e o Docker nunca cai em `192.168.0.0/16` (a LAN é `192.168.15.0/24`). |

### B — painel e notificações

| # | Pendência | Decisão | Como |
|---|---|---|---|
| 51 | Alerta de disco duplicado nos mounts NFS | corrigir | O alerta de disco ignora `fstype=~"nfs.*"`: o espaço do pool já é medido no host. |
| 52 | Autenticação do webhook quando a variável do token está ausente | corrigir | O workflow `notificar` recusa (401) quando `NOTIFICACOES_WEBHOOK_TOKEN` está vazio. |
| 53 | `n8n update:workflow --active` talvez obsoleto no n8n 2.x | corrigir | Usar `n8n publish:workflow --id=…` (n8n 2.x). |
| 54 | Variáveis do Telegram duplicadas no `apps.env` | corrigir | Na hora de executar se viu que cada `.env` precisa das duas variáveis e que a duplicação vem da junção manual. O nome repetido sai, e o fluxo do `apps.env` continua como item adiado. |
| 55 | Diun pelo socket proxy | corrigir | O `diun` da core usa o `docker-socket-proxy` (`DIUN_PROVIDERS_DOCKER_ENDPOINT=tcp://docker-socket-proxy:2375`, que ganha `IMAGES=1`), e o socket sai do container. O `diun_ai` ganha um proxy próprio na stack `ai`. |

## 4. A conferir no primeiro deploy (consolidado)

As listas "a conferir" de cada sub-projeto ficam numa seção única da página de reconstrução (`04-manutencao-recuperacao/04-reconstruindo-infraestrutura.md`), para o Léo ter um roteiro do primeiro deploy:

- **4c1:** agentgateway (lista de leitura, chaves, tokens em arquivo, traces no Langfuse, campo `cliente` nos logs), `PUT /api/stacks` do Portainer 2.19, alerta `ops-acao-falhou` com o formato do Loki.
- **4b:** módulos nativos do qmd no `node:22-bookworm-slim`, `HOME` gravável do markitdown com `--user`, "Default Folder" criada pelo `generate` do Syncthing.
- **3:** Collabora dentro do Nextcloud (item 36).
- **2:** widget da Homepage para o Seerr (item 37).

## 5. Execução

Commits temáticos, um por grupo: CI/lint, 4c1, 4b, 4a, 3, 2, 1, B, roteiro de deploy. Cada um passa por wiki → `check` → `sync` → teste → `build`/`lint`. No fim: `update-index`, revisor final em contexto novo e as correções que ele apontar.

## 6. Sugestões de melhoria (não implementadas aqui)

- **Política de versões:** dezenas de imagens ainda em `:latest`, contra a regra do `server/AGENTS.md`. Fixar tudo exige configurar o Diun com `watch_repo` + `include_tags` (senão ele deixa de avisar). Merece um sub-projeto curto.
- **GitHub App do Claude** no repositório: permite que as sessões façam o push sozinhas e acompanhem o CI.
- **Pre-commit local** com `dev.py check` e `lint`: o CI ficou vermelho dois dias sem ninguém notar.
