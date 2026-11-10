---
description: "Sysadmin no GCP: Hermes com memória Honcho numa e2-micro, executor com vault e SSH atrás de botões no Telegram, e a equipe de agentes pelo GitHub."
---

# Seção 19: Sysadmin no GCP

## Como funciona

O **sysadmin** é um agente que existe **antes** do servidor. Ele roda numa VM `e2-micro` do Google Cloud (nível gratuito, `us-east1`), você o comanda pelo Telegram, e ele conduz o [roteiro do primeiro deploy](18-roteiro-primeiro-deploy.md) fase a fase: lê a wiki, confere o estado real da casa, monta os pedidos e **espera o seu botão** para tudo que muda o servidor. Depois do deploy, continua como o coordenador da equipe de agentes da casa. É também o jeito recomendado de ter a [máquina de controle do Ansible](01-maquina-controle-ansible.md#o-sysadmin-como-caminho-recomendado).

O agente é o [Hermes](17-assistente.md) (v0.22.5) com memória no [Honcho](https://github.com/plastic-labs/honcho) (v3.6.0) próprio. O **modelo** é o Claude da Anthropic (Sonnet por padrão, Haiku para resumos), com o Gemini (AI Studio) de reserva. Ele **não usa o LiteLLM de casa**: o sysadmin existe antes dela e é quem a conserta.

```mermaid
flowchart LR
    leo[Léo] -- "bot sysadmin" --> sa
    leo -- "bot de aprovações<br/>botões e segredos" --> ex
    leo -- "tailscale serve :443" --> dash[dashboard]
    subgraph gcp[VM e2-micro, us-east1]
        sa[sysadmin<br/>Hermes] -- MCP --> ex[executor<br/>vault, SSH, carteiro]
        ex -- "webhook<br/>(carteiro)" --> sa
        sa --> hon[honcho<br/>api, deriver, db]
        dash --- sa
    end
    sa -- "PR (conta de máquina)<br/>issues" --> gh[GitHub<br/>wiki-home-server<br/>homeserver-equipe]
    ex -- "lê a main e a equipe" --> gh
    ex -- "Tailscale<br/>SSH, API do Proxmox" --> casa[host Proxmox<br/>core, ai]
    casa -- "agentes da casa (5b)<br/>issues" --> gh
    sa -- "Claude / Gemini" --> llm[Anthropic<br/>Gemini API]
```

| Peça | Onde | O que faz |
|---|---|---|
| `sysadmin` | container na VM (`localhost/homeserver/sysadmin`: Hermes, Ansible, `gh`, ambiente do `tools/dev.py`) | Conversa pelo bot do sysadmin, tem terminal e o clone do repositório; **não tem** a senha do vault nem a chave SSH da casa |
| `sysadmin_painel` | mesma imagem | Dashboard oficial do Hermes em `127.0.0.1:9119`, publicado só no tailnet pelo `tailscale serve` |
| `executor` | container na VM (`localhost/homeserver/executor`: Python, `ansible-core`, git, ssh) | **Sem modelo.** Único com a senha do vault e a chave SSH; oferece ao Hermes um MCP com ferramentas fechadas, lê os cliques do bot de aprovações e roda o carteiro |
| `honcho_api`, `honcho_deriver`, `honcho_db` | containers na VM (Honcho `v3.6.0`, Postgres com pgvector) | Memória do sysadmin, *workspace* `sysadmin` com os pares Léo e sysadmin. Sem Redis, sem telemetria; o deriver e os *embeddings* usam a chave do Gemini |
| Bot do sysadmin | `telegram_bot_sysadmin` (segredo do GCP) | A conversa. Só responde ao seu `telegram_chat_id` |
| Bot de aprovações | `telegram_bot_aprovacoes` | Só o executor o lê: os botões de aprovar ou recusar e o canal de segredos. Separar conversa e aprovação evita que o modelo veja segredos. Não é o bot de avisos de casa |
| Conta de máquina | `lioevano-sysadmin` no GitHub | Abre PRs e issues; não consegue dar o merge do próprio PR |
| `homeserver-equipe` | repositório privado | Pedidos entre agentes ([A equipe](#a-equipe)) |
| Secret Manager e bucket | `sysadmin-segredos` e `gs://<projeto>-sysadmin` | Um único segredo JSON, lido na partida para o `tmpfs` `/run/sysadmin`; o bucket guarda o vault de entrada e os backups |

Os seis containers dividem 1 GB de RAM com 4 GB de swap (cifrada, com chave nova a cada boot). Se ficar lento, a saída é `gcp_tipo_maquina: e2-small` (cerca de US$ 13 por mês) por PR; a medição real está em [A conferir no primeiro deploy](index.md#a-conferir-no-primeiro-deploy).

### Como uma fase corre

1. Você manda `/implantar-fase 3` (ou "vamos para a fase 3"). Os comandos do Telegram são os **nomes das skills**: `/implantar-fase N`, `/status-implantacao` e `/equipe`; `/status` é o comando nativo do Hermes. Linguagem natural também serve.
2. O sysadmin lê a fase na [página 18](18-roteiro-primeiro-deploy.md) e confere o estado real com o `diagnostico` (só leitura, sem botão).
3. Abre o **diário da fase**: uma issue com a etiqueta `diario` no `homeserver-equipe`, com a lista de passos e o log completo. O Telegram recebe só o resumo e o link.
4. Manda numa mensagem só o que **é seu** (contas, físico, telas que pedem uma pessoa, stacks no Portainer, merges) e espera a confirmação.
5. Segredo que falta: `vault_preencher` (você responde ao bot de aprovações). Wiki errada ou incompleta: PR primeiro; ele só segue depois do seu merge.
6. Cada playbook: `ansible_check` (botão) e `ansible_aplicar` (botão).
7. Teste de ponta a ponta da seção, marca a linha em "A conferir no primeiro deploy", fecha o diário e sugere a próxima fase. "Pare" interrompe o trabalho dele; um playbook já aprovado vai até o fim ou até o tempo limite do runner.

### Dashboard

O dashboard oficial do Hermes (visualização e controle) escuta em `127.0.0.1:9119` do host e o `tailscale serve` o publica em `https://sysadmin.<tailnet>.ts.net`, só para os seus aparelhos. Exige usuário e senha (`leo` e a senha que o `criar-sysadmin.sh` mostra uma vez) e precisa do **HTTPS do tailnet** ligado no painel do Tailscale (*DNS → HTTPS Certificates*). Depois do primeiro `tailscale serve`, grave a URL em `sysadmin_dashboard_url` no `group_vars` (por PR). É uma porta de administração (chaves, ferramentas, terminal): nunca pelo túnel da Cloudflare nem pela internet. O `config.yaml` do Hermes é montado **só leitura**: o que for mudado pelo painel não grava, e a configuração só muda por PR.

### Custo

| Item | Custo |
|---|---|
| VM `e2-micro`, 30 GB de disco padrão, IP externo | US$ 0 (nível gratuito, `us-east1`) |
| Secret Manager (um segredo) e bucket (< 5 GB, região dos EUA) | US$ 0 |
| Saída de rede | 1 GB por mês grátis; acima, cerca de US$ 0,12 por GB |
| Tailscale (plano pessoal) | US$ 0 |
| Modelo | Teto no console da Anthropic (sugerido: US$ 30 por mês na implantação e US$ 10 depois) mais o Gemini do deriver, dos *embeddings* e da reserva (centavos) |

O alerta de orçamento do GCP fica em **US$ 2**.

## O que ele pode e o que não pode

| Pode | Como |
|---|---|
| Ler, planejar e editar a wiki, rodar `check`, `sync`, `test` e `lint` | No terminal do container, no clone do repositório (`/repo`) |
| Abrir PR e issue | Pela conta de máquina `lioevano-sysadmin`; a `main` só muda pelo seu merge |
| Diagnosticar a casa (só leitura) | `diagnostico(host, comando)`: lista fechada (`systemctl status`, `journalctl -u … -n`, `docker ps`, `docker logs`, `df`, `free`, `ip`, `ss -tlnp`, `ping`, `tailscale status`, `cat /etc/os-release`); qualquer outra forma, inclusive `;`, `&&`, `\|` e redirecionamentos, é recusada |
| Listar playbooks e consultar pedidos de segredo | `playbooks_listar()` e `vault_status()` |
| Simular e aplicar um playbook | `ansible_check(playbook, limite)` e `ansible_aplicar(plano_id)`, **cada um com botão** |
| Rodar um comando livre num host | `comando(host, comando)`, **com botão**; uma linha, só caracteres visíveis, até 250 caracteres (o pedido mostra o comando por extenso, e o que passa de cerca de 300 caracteres depois de escapado é cortado). Algo maior vira script versionado por PR |
| Pedir um segredo | `vault_preencher(chave)`: o bot de aprovações pergunta, **a sua resposta é a aprovação**, o valor vai direto ao vault cifrado e a mensagem é apagada. O valor nunca passa pelo modelo, pelo histórico do Hermes nem pelo Honcho |
| Preparar o host Proxmox | `preparar_host()`: o bot de aprovações lhe manda o comando que você cola no console do host |
| Pedir trabalho a outros agentes | Issues no `homeserver-equipe` ([A equipe](#a-equipe)) |

Todo pedido com botão vale só para a **mesma ferramenta, alvo e argumentos**, **uma vez**, em **30 minutos**. Há uma execução por vez, no máximo 5 pedidos pendentes, auditoria em arquivo e saídas cortadas antes de voltar ao modelo. O executor **só aceita botões do seu id** (`telegram_chat_id`), ignora a própria VM do GCP como alvo (rodaria dentro dele, onde estão os segredos) e `setup-sysadmin.yml` não está entre os playbooks permitidos: o sysadmin não se reconfigura.

**Não pode:**

- Alcançar a casa pelo terminal: o container não tem a chave SSH, e o tailnet, a LAN de casa e o servidor de metadados do GCP estão bloqueados para a rede dele ([Rede e ACL](#rede-e-acl)). Tudo passa pelo executor.
- Ler a senha do vault, a chave SSH e a chave do Tailscale da casa: esses arquivos vão só ao executor.
- Dar `git push` na `main` nem fazer o merge do próprio PR (`AGENTS.md`: a exceção da página 19 vale para `ansible-playbook`, `ansible-vault` e `ssh` com o botão, nunca para push na `main`).
- Usar navegador, `computer_use`, subagentes (`delegation`), tarefas agendadas (`cronjob`), conexões novas (`connections`), busca na web, geração de mídia e voz, nem as outras plataformas de mensagem. Esses grupos estão em `agent.disabled_toolsets` no `config.yaml`. Ficam **ligados** `terminal`, `code_execution`, `file` (dentro do container), `skills`, `memory`, `todo`, `clarify` e `session_search`, mais o MCP do executor. A aprovação de comandos do próprio Hermes está desligada (`approvals.mode: off`): o container do sysadmin não guarda nada de valor, e os portões que valem são os do executor; assim você não recebe botão para um `rm` no clone.
- Responder a outra pessoa: o Hermes só aceita o `telegram_chat_id`.

!!! warning "Por que dois containers"
    Um agente com terminal, internet e a chave SSH da casa seria uma injeção de prompt longe de entregar a casa. Por isso o `sysadmin` (que lê issues, PRs, logs e páginas de terceiros) não tem nada de valor, e o `executor` (que tem a senha do vault e a chave SSH) não tem modelo, não aceita conexões e só obedece a botões do seu id. É o padrão `ops` mais `aprovador` da [seção 16](16-posto-agentes.md#aprovação-humana), aqui no mesmo compose.

!!! info "Dados que saem de casa"
    O que você conversa, as saídas de diagnóstico e trechos de log vão à Anthropic, ao Google (reserva, deriver e *embeddings*) e ao GitHub (repositório privado da equipe). Segredos não: o canal de segredos não passa pelo modelo nem pelas issues.

## Rede e ACL

A VM **recusa toda entrada**: uma regra do firewall do GCP (`sysadmin-recusa-entrada`, prioridade 100) anula o `default-allow-ssh` da rede padrão. Telegram, Tailscale, GitHub e as APIs são conexões de saída. O acesso de manutenção é por SSH **pelo Tailscale**.

1. **Tailscale da VM:** entra sozinha no primeiro boot com a chave de uso único da `tag:sysadmin` (`--accept-routes`). Nós com tag não expiram a chave.
2. **Host Proxmox como nó próprio** (`pve`, `tag:homeserver`): anuncia as rotas `/32` do host, da core e da `ai`. Depois do `setup-vpn.yml` a core anuncia as mesmas três rotas (failover do Tailscale): se a core cair, as rotas seguem pelo host e o host continua alcançável. Os passos estão na [seção 14](14-vpn-tailscale.md#primeira-configuração).
3. **ACL:** cole no painel do Tailscale (*Access controls*) o conteúdo de `scripts/tailscale/acl.json`, que a [seção 14](14-vpn-tailscale.md#primeira-configuração) mostra por inteiro e explica linha a linha (JSON estrito não aceita comentários). Em resumo: o `tag:sysadmin` alcança só o host (`:22`, `:8006`) e as VMs (`:22`, `:443`, `:53` na core; `:22` na `ai`); os seus aparelhos alcançam o sysadmin em `:22` e `:443`; **nada da casa alcança o `tag:sysadmin`**, para que um servidor comprometido não chegue ao sysadmin. O `autoApprovers` só aprova as três rotas `/32`.

!!! note "A ACL nova é mais estreita que a padrão"
    Sem uma regra de aparelho para aparelho, o seu celular não alcança o seu PC pelo Tailscale (a ACL antiga, de "tudo para todos", alcançava). Se quiser, acrescente em `acls` uma regra com `autogroup:member` na origem e `autogroup:member:*` no destino.

**O container `sysadmin` não alcança o tailnet, a casa nem os metadados do GCP.** A rede Docker dele (`sysadmin_rede`, ponte `br-sysadmin`, `172.30.10.0/24`) passa por uma cadeia `SYSADMIN` na tabela `raw` (`PREROUTING`) do host, criada pelo role `infra/sysadmin-gcp` (`ansible/roles/infra/sysadmin-gcp/templates/firewall-sysadmin.sh.j2`) e reaplicada antes de cada (re)início do Docker. Ela descarta o que sai dessa rede para `100.64.0.0/10`, para a LAN de casa, para `169.254.169.254` (exceto DNS, que o GCP serve por lá), para o gateway da ponte e para o IP interno da VM. O `executor` fica numa rede à parte e alcança a casa pelo Tailscale do host da VM. O compose publica **uma única porta**, o painel em `127.0.0.1:9119`.

!!! warning "Use um projeto do GCP só para o sysadmin"
    A regra `sysadmin-recusa-entrada` não tem `target-tags`: vale para a rede `default` **inteira** do projeto. Outras VMs no mesmo projeto perderiam o acesso de entrada. Crie um projeto dedicado.

## Criar o sysadmin

O passo a passo tem quatro tempos: contas (fase 0 do [roteiro](18-roteiro-primeiro-deploy.md#fase-0--fora-do-servidor)), o `criar-sysadmin.sh` no Cloud Shell, o PR do vault e o `preparar_host` quando o Proxmox estiver instalado.

### 1. O que você leva para o Cloud Shell

Tudo isso é da fase 0 (você nunca pede a ninguém para criar):

- **Projeto do GCP dedicado**, com faturamento ligado (o nível gratuito exige um cartão cadastrado) e a região `us-east1`, `us-central1` ou `us-west1` (o script recusa outras).
- **Anthropic:** chave da API própria do sysadmin (separada das de casa) e o teto de gasto no console.
- **Gemini:** chave do AI Studio, **plano pago** (o deriver e os *embeddings* do Honcho e a reserva do Hermes).
- **Quatro bots no @BotFather** (`/newbot`), cada um com seu token: o do **sysadmin**, o de **aprovações do sysadmin**, o de **avisos** (n8n e `aprovador` de casa) e o do **assistente**. Um bot só aceita um leitor por vez. Mande `/start` aos dois do sysadmin e anote o id do seu chat (`telegram_chat_id`).
- **GitHub:** a conta de máquina `lioevano-sysadmin`, colaboradora do `wiki-home-server` com escrita; um *ruleset* na `main` com PR obrigatório, **1 aprovação**, aprovação do último push por outra pessoa, sem *force push* e **sem ninguém na lista de exceções**; o repositório privado `lioevano/homeserver-equipe` com as etiquetas do protocolo; e dois tokens *fine-grained* ([A equipe](#a-equipe)).
- **Tailscale:** a ACL colada, o HTTPS do tailnet ligado e **duas chaves de uso único e pré-aprovadas**, uma com `tag:sysadmin` (a VM) e outra com `tag:homeserver` (o host Proxmox).

### 2. Criar a VM (Cloud Shell)

Com o projeto escolhido, rode **uma vez** no Cloud Shell (precisa de Python 3.12 ou mais novo):

```bash title="Exemplo: criar o sysadmin no Cloud Shell"
gcloud config set project <projeto>
curl -fsSL https://raw.githubusercontent.com/lioevano/wiki-home-server/main/server/scripts/gcp/criar-sysadmin.sh | bash
```

O `scripts/gcp/criar-sysadmin.sh`:

1. liga as APIs e cria a conta de serviço `sysadmin-vm` (`secretAccessor` só no segredo, `objectAdmin` só no bucket, nenhum papel no projeto);
2. cria o bucket `<projeto>-sysadmin` (os backups são apagados em 30 dias) e as regras de firewall: a que recusa toda entrada e a `sysadmin-iap-emergencia`, **desligada**;
3. cria o alerta de orçamento de US$ 2;
4. pede, **sem eco**, as chaves e os tokens da seção anterior, gera o resto (tokens internos, senha do Honcho, senha do painel, **senha do vault**, chave SSH do executor) e grava tudo no segredo `sysadmin-segredos`;
5. roda o `gerar_vault.py` no próprio Cloud Shell, mostra o bloco "anote" e envia o `vault.yml` **cifrado** para `gs://<projeto>-sysadmin/entrada/vault.yml`;
6. cria a VM, cujo *startup-script* instala o `ansible-core` fixado e faz o primeiro `ansible-pull` da `main`.

!!! danger "Guarde o que aparece na tela"
    No fim ele mostra **uma vez** a senha do painel e a **senha do vault** (e, antes, o bloco com as senhas do `gerar_vault.py`, incluindo a do restic). Guarde no gerenciador de senhas: sem a senha do vault você perde o acesso aos segredos da casa.

Repetir o script é seguro: ele reaproveita o segredo existente (nada de senha, chave SSH ou vault novos) e recria uma VM perdida. Só `REGERAR=1` (com confirmação) gera tudo de novo.

A VM leva de **20 a 40 minutos** para se configurar (as imagens `sysadmin` e `executor` são compiladas na e2-micro). Acompanhe com `gcloud compute instances get-serial-port-output sysadmin --zone=us-east1-b | tail -n 30`. Quando o nó `sysadmin` aparecer no Tailscale e o bot do sysadmin responder, está de pé. A partir daí, toda a configuração da VM vem de `ansible/playbooks/setup-sysadmin.yml`, que a própria VM puxa da `main` no primeiro boot e num timer diário (05:17 UTC), configurando Docker, Tailscale e o role `infra/sysadmin-gcp`. Ele fica **fora** do `full-deploy.yml`, e só o `main.yml` entra nele, nunca o vault.

### 3. O PR do vault

O vault de entrada está em `/saida/vault.yml` (cifrado, só leitura para o sysadmin, que não o decifra). Peça: "abra o PR do vault". O sysadmin copia o arquivo para `server/ansible/inventories/home/group_vars/all/vault.yml`, roda o `python tools/dev.py check` e abre o PR; você revisa (é um arquivo cifrado: confira que começa com `$ANSIBLE_VAULT;` e mescle). As chaves que vêm de fora (Cloudflare, domínio, provedores de LLM, ProtonVPN, B2 e a senha do root do Proxmox) ficam com o texto do modelo: o sysadmin as pede **uma a uma** pelo `vault_preencher` quando a fase chegar nelas, e cada preenchimento regrava o `saida/vault.yml`; ele abre um PR novo do vault ao fim da fase e você mescla. O executor só lê o vault da `main`.

### 4. Preparar o host Proxmox

Com o Proxmox instalado pelo pendrive, o sysadmin chama `preparar_host()`: o bot de aprovações lhe manda **um comando** para colar no console do host. O `scripts/gcp/preparar-host.sh` (que é repetível) instala o Tailscale e entra no tailnet com a chave de uso único da `tag:homeserver`, anunciando as rotas `/32`; liga o encaminhamento de pacotes; cria o usuário do Ansible, sem senha, com `sudo`; e autoriza a chave pública do executor. É o último passo físico na rede. A senha de root do Proxmox, que o `proxmox_api_password` do vault pede, entra por `vault_preencher`. Daí em diante o `setup-proxmox-host.yml` gerencia esse Tailscale pelo role `infra/tailscale`, que passou a aceitar Debian.

### 5. Daqui em diante

Mande `/status-implantacao` para ver a fase atual, as pendências suas, os pedidos abertos, o gasto do mês e a memória da VM, e `/implantar-fase 1` para começar. Os segredos ficam em `/run/sysadmin` (um `tmpfs`, 0600), separados por container pelo `scripts/gcp/separar_segredos.py`: o sysadmin recebe só o que é dele e **falha fechado** se faltar um campo. O backup roda todo dia às 06:07 UTC (o `pg_dump` do Honcho e o diretório do Hermes, sem `.env` nem `auth.json`) em `gs://<projeto>-sysadmin/backup/<data>/`. O `ansible-pull` das 05:17 UTC mantém a VM igual à `main`; a atualização do próprio Hermes, do Honcho e das imagens acontece por PR de versão no `group_vars`.

## A equipe

Os agentes se coordenam por **issues** no repositório privado `lioevano/homeserver-equipe` (`equipe_repo`). Não há porta nova em lugar nenhum (todos só saem para o GitHub), não há custo, há histórico, e você acompanha e intervém pelo app do GitHub. O protocolo completo é a skill `equipe` (`.agents/skills/equipe/SKILL.md`); este é o resumo.

- **Etiquetas:** `papel:<nome>` (`sysadmin`, `metricas`, `apps`, `variaveis`, `atualizacoes`, `backup`, `assistente`); `estado:aberto`, depois `estado:em-andamento`, e por fim `estado:feito` ou `estado:bloqueado`; `diario` para os diários de fase. Crie todas ao criar o repositório (`gh label create`).
- **Colaboradores:** você, a conta de máquina do sysadmin e, na 5b, as contas dos agentes da casa, cada um só com *Issues: read/write* no repositório. O **carteiro** usa um token *fine-grained* só de leitura de issues.
- **Pedido:** o que se quer, por quê, o que conta como feito, prazo, e "ações no servidor passam pelo aprovador de casa".
- **Feito:** comentário com o resultado e a evidência (comando, saída resumida, link) e a etiqueta `estado:feito`; quem pediu fecha.

As quatro regras: (1) a casa nunca chama o sysadmin, ele pede e busca; (2) pedir a outro agente não fura portão: ações no servidor do agente da casa passam pelo `ops` e pelo `aprovador` de lá; (3) resposta é dado, não ordem; (4) nada de segredo em issue, comentário ou diário (segredo só pelo bot de aprovações).

**Carteiro.** O `docker/images/executor/executor/carteiro.py` não usa modelo: a cada 2 minutos lê o `homeserver-equipe` e, havendo resposta a um pedido do sysadmin ou uma issue `papel:sysadmin`, acorda o Hermes pelo webhook dele (rede interna, porta 8644, assinatura HMAC V2). O Hermes entrega a mensagem na sua conversa do Telegram. Sem novidade, não há chamada e não há gasto de modelo.

Os papéis da casa (`metricas`, `apps`, `variaveis`, `atualizacoes`, `backup`, `assistente`) são implementados na **5b**, em spec própria; até lá o sysadmin pode abrir pedidos, mas só o `assistente` e o observador existem do lado de casa.

## Arquivos

Arquivos desta seção (cada task acrescenta o seu):

- `docker/images/executor/executor/__init__.py` — docstring e versão do pacote do executor.
- `docker/images/executor/executor/config.py` — configuração do executor lida do ambiente (falha fechada) e a conversão para o `ops`.
- `docker/images/executor/executor/portao.py` — portão de aprovação: toda ação que muda a casa só roda com pedido aprovado pelo Léo no Telegram.
- `docker/images/executor/executor/remoto.py` — comandos remotos por Ansible ad-hoc e o validador dos comandos de diagnóstico; hosts de conexão local (o `sysadmin-gcp`) ficam fora: rodariam dentro do próprio executor, onde estão os segredos.
- `docker/images/executor/executor/vault.py` — edita o vault do Ansible: troca o valor de uma folha do modelo e grava cifrado, de forma atômica, em `saida/vault.yml`.
- `docker/images/executor/executor/segredos.py` — canal de segredos: o Léo responde a um pedido no Telegram e o valor vai direto ao vault, sem passar pelo modelo, por log ou por mensagem.
- `docker/images/executor/executor/leitor.py` — leitor do Telegram do executor: cliques nos botões vão ao aprovador e mensagens ao canal de segredos.
- `docker/images/executor/executor/carteiro.py` — carteiro: sem modelo, consulta o repositório da equipe e acorda o sysadmin pelo webhook do Hermes (assinatura HMAC V2) quando há novidade para ele.
- `docker/images/executor/executor/ferramentas.py` — ferramentas MCP do executor: diagnóstico de leitura, comando e playbooks pelo portão de aprovação, pedido de segredos ao Léo e o comando de preparo do host.
- `docker/images/executor/executor/servidor.py` — ponto de entrada: sobe o leitor do Telegram e o carteiro em threads que se recuperam de erros e serve o MCP atrás do token.
- `docker/images/executor/executor/__main__.py` — `python -m executor` chama o `servidor.main`.
- `docker/images/executor/Dockerfile` — imagem do executor (FastMCP, ansible-core, git e ssh), como a do ops mais o aprovador; roda sem root.
- `docker/images/executor/.dockerignore` — deixa o cache do Python fora da imagem.
- `scripts/gcp/preparar-host.sh` — o comando único que o Léo cola no console do host Proxmox: Tailscale com a chave de uso único, usuário do Ansible com sudo e a chave SSH do sysadmin (repetível).
- `docker/images/sysadmin/Dockerfile` — imagem do sysadmin: Hermes Agent mais Ansible, `gh`, git, ssh, o ambiente do `tools/dev.py`, as coleções do Ansible (instaladas na construção) e o cliente do Honcho (`honcho-ai`); o contexto de build traz `requirements-dev.txt`, `wiki/requirements.txt` e `requirements.yml`.
- `ansible/templates/sysadmin/config.yaml.j2` — `config.yaml` do Hermes: modelos, memória no Honcho, executor por MCP, webhook da equipe e ferramentas desligadas.
- `ansible/templates/sysadmin/SOUL.md.j2` — identidade e regras do sysadmin (wiki primeiro, só por PR, tudo pelo executor, segredos só por `vault_preencher`).
- `ansible/templates/sysadmin/honcho.json.j2` — `honcho.json` do plugin: servidor próprio, workspace e pares.
- `ansible/templates/sysadmin/honcho-config.toml.j2` — `config.toml` do Honcho: só Gemini, sem Redis e sem telemetria.
- `scripts/gcp/separar_segredos.py` — separa o JSON do Secret Manager em arquivos por container no tmpfs `/run/sysadmin`: o sysadmin nunca recebe a senha do vault, a chave SSH nem a chave do Tailscale da casa; falha fechada se faltar campo.
- `docker/stacks/sysadmin/docker-compose.yml` — stack do sysadmin na VM da GCP: Hermes (gateway e painel em `127.0.0.1:9119`), executor e Honcho (API, deriver e banco), em redes separadas; `config.yaml`, `SOUL.md`, `honcho.json` e o plugin do Honcho entram só leitura, de `config/` (do root).
- `ansible/roles/infra/sysadmin-gcp/templates/firewall-sysadmin.sh.j2` — firewall da rede do sysadmin (cadeia `SYSADMIN` na tabela `raw` PREROUTING, pela bridge `br-sysadmin`): bloqueia o tailnet, a LAN de casa e o servidor de metadados da GCP.
- `ansible/playbooks/setup-sysadmin.yml` — configura a VM do sysadmin a partir dela mesma (`ansible-pull` da `main`, no primeiro boot e no timer diário): Docker sem Portainer, Tailscale com `tag:sysadmin` e o role `infra/sysadmin-gcp`; só o `main.yml` entra (por `vars_files`), nunca o vault, e fica fora do `full-deploy.yml`.
- `ansible/roles/infra/sysadmin-gcp/defaults/main.yml` — padrões do role: bucket (`<projeto>-sysadmin`), UIDs do Hermes e do executor, endereços do repositório e do Honcho, fuso dos containers.
- `ansible/roles/infra/sysadmin-gcp/tasks/main.yml` — swap de 4 GB cifrada (chave aleatória a cada boot), firewall, diretórios em `/opt/sysadmin` (o root não escreve nem roda git onde um container escreve: as configurações e o plugin ficam em `config/`, só leitura, e os clones são criados uma vez e entregues ao dono), as imagens `sysadmin` e `executor` (reconstruídas quando a versão ou o contexto muda, ou quando o último build falhou), a stack, o painel pelo `tailscale serve` e os timers.
- `ansible/roles/infra/sysadmin-gcp/tasks/segredos.yml` — projeto da GCP pelo servidor de metadados, o `separar_segredos.py` em `/usr/local/lib/sysadmin/` e a unit dos segredos, executada na hora (o playbook a roda antes do Tailscale, que lê a chave do tmpfs).
- `ansible/roles/infra/sysadmin-gcp/templates/sysadmin-segredos.service.j2` — unit que, antes do Docker, lê o `sysadmin-segredos` do Secret Manager e o separa em `/run/sysadmin`, tentando de novo a cada minuto se falhar (e traz o `vault.yml` de entrada do bucket, se ainda não houver um em `saida/`); o `gcloud` não grava log em disco.
- `ansible/roles/infra/sysadmin-gcp/templates/firewall-sysadmin.service.j2` — unit que aplica o `firewall-sysadmin.sh` antes de cada (re)início do Docker.
- `ansible/roles/infra/sysadmin-gcp/templates/sysadmin-pull.service.j2` — o `ansible-pull` da `main` (de `/`, com o `ansible.cfg` do clone e sem `group_vars` automáticos, para o vault cifrado não ser lido).
- `ansible/roles/infra/sysadmin-gcp/templates/sysadmin-pull.timer.j2` — atualização diária às 05:17 UTC.
- `ansible/roles/infra/sysadmin-gcp/templates/sysadmin-backup.sh.j2` — backup da memória: `pg_dump` do banco do Honcho e o diretório do Hermes (sem `.env` nem `auth.json`) em `gs://<bucket>/backup/<data>/`.
- `ansible/roles/infra/sysadmin-gcp/templates/sysadmin-backup.service.j2` — unit do backup.
- `ansible/roles/infra/sysadmin-gcp/templates/sysadmin-backup.timer.j2` — backup diário às 06:07 UTC.
- `ansible/roles/infra/sysadmin-gcp/templates/sysadmin.env.j2` — `.env` da stack, só com valores não secretos: versões, caminhos, a sub-rede do sysadmin, os playbooks e as rotas do executor.
- `scripts/gcp/criar-sysadmin.sh` — roda uma vez no Cloud Shell: liga as APIs, cria a conta de serviço `sysadmin-vm` (`secretAccessor` só no segredo, `objectAdmin` só no bucket), o bucket `<projeto>-sysadmin` (backups apagados em 30 dias), a regra que recusa toda entrada, o alerta de orçamento de US$ 2, o segredo `sysadmin-segredos` (chaves digitadas sem eco, o resto gerado), o `vault.yml` cifrado em `entrada/` e a VM, cujo startup-script instala o `ansible-core` fixado e faz o primeiro `ansible-pull`, igual ao do timer diário. Repetido, reaproveita o segredo existente (só `REGERAR=1` gera tudo de novo, e o startup-script espera o lock do apt); deixa pronta, desligada, a regra `sysadmin-iap-emergencia` (SSH pelo IAP).

## Teste de ponta a ponta

Faça depois que o nó `sysadmin` aparecer no Tailscale e o bot responder:

1. `/status` no bot do sysadmin: o Hermes responde. Depois `/status-implantacao`. Dentro do container, `hermes memory status` mostra o Honcho.
2. Peça algo que dependa da equipe ("peça ao assistente um resumo do servidor"): o sysadmin abre a issue com `papel:` e `estado:aberto` no `homeserver-equipe`, e um comentário no GitHub acorda o sysadmin (o carteiro) com aviso na sua conversa.
3. `ansible_check` e `ansible_aplicar` de um playbook inofensivo, um que você sabe que já está aplicado e não muda nada: chegam os botões no **bot de aprovações** com commit, autor e assunto; aprove os dois.
4. `vault_preencher` de uma chave de teste: o bot pergunta, você responde, a mensagem some do chat e o `saida/vault.yml` atualiza (`vault_status`). Confira que o valor não aparece na conversa com o sysadmin.
5. Peça um `comando` e **recuse** no botão: ele diz que foi recusado e nada roda.
6. De outra conta do Telegram, mande mensagem aos dois bots: nenhuma resposta.
7. Abra o dashboard em `https://sysadmin.<tailnet>.ts.net` com o Tailscale ligado: aparece pedindo usuário e senha. Sem o Tailscale, não abre.
8. Peça "rode `ssh core`" no terminal do Hermes: falha (sem chave e sem rota).
9. `docker exec sysadmin curl -m 5 http://169.254.169.254` falha (idem para um IP `100.x` e para um da LAN de casa), e `docker exec sysadmin getent hosts api.anthropic.com` resolve.

## Falhas

| Falha | Comportamento | O que fazer |
|---|---|---|
| VM parada (manutenção, cobrança) | Bot mudo | `gcloud compute instances start sysadmin --zone=us-east1-b`; na partida, os segredos e os containers sobem sozinhos |
| VM perdida | Perdem-se a memória e as sessões | Rode o `criar-sysadmin.sh` de novo (reaproveita o segredo; `REGERAR=1` só se quiser trocar tudo) e restaure o dump e o diretório do Hermes do GCS |
| Falta de memória | Swap e `restart: unless-stopped` | Se repetir, `gcp_tipo_maquina: e2-small` por PR |
| Anthropic fora ou teto atingido | Reserva no Gemini | Se as duas falharem, o executor avisa pelo bot de aprovações: "sysadmin sem modelo" |
| Casa fora ou tailnet caído | `diagnostico` falha; nada destrutivo é possível | O sysadmin relata e espera; com a core fora, o host segue alcançável pelo Tailscale |
| Playbook falha no meio | Código de saída e o final do log no diário | Correção por PR e `ansible_check` de novo |
| Aprovação vencida | O executor recusa | Peça de novo (vale 30 minutos) |
| GitHub fora | PRs e equipe param; o executor recusa aplicar sem ler a `main` | Esperar |
| Aviso do Telegram que falha ao enviar | O pedido existe, mas você não o vê; vence em 30 minutos (falha fechada) | O sysadmin deve avisar pela conversa que há pedido pendente; reenvie |
| Thread do leitor ou do carteiro cai | O `manter_vivo` a reinicia depois de uma espera; o log só tem o tipo do erro | `docker logs executor`; se repetir, veja o token do bot e o do GitHub |
| Backup falha | Só aparece no journal e em `systemctl --failed` (sem alerta) | `systemctl status sysadmin-backup.service` na VM; confira o bucket de vez em quando |
| Segredos rotacionados | A unit de segredos reinicia o Docker (a stack inteira) | Faça com a casa parada de pedidos; `systemctl list-jobs` mostra o que espera |
| Falha passageira do Secret Manager | A unit tenta de novo a cada minuto e o Docker espera por ela | Espere; veja `journalctl -u sysadmin-segredos` |
| Tailscale caiu e não há SSH | A VM recusa toda entrada | Ligue o IAP de emergência: `gcloud compute firewall-rules update sysadmin-iap-emergencia --no-disabled`, depois `gcloud compute ssh sysadmin --zone=us-east1-b --tunnel-through-iap`; **desligue** de novo com `--disabled` ao terminar |
| Outras VMs do projeto sem acesso | A regra `sysadmin-recusa-entrada` vale para a rede `default` inteira | Use um projeto do GCP só para o sysadmin |
| `container sysadmin` comprometido | Vazam a chave da Anthropic (com teto) e o token da conta de máquina (PR e issues) | Revogue os dois e o bot do sysadmin; a casa e o vault ficam intactos |
| Executor comprometido | Equivale a perder a máquina de controle | Troque a senha do vault e a chave SSH. Mitigação: sem modelo, sem entrada, só botões do seu id e código mínimo e testado |
| Token do bot de aprovações vazado | Quem tem o token lê os pedidos, mas os botões só valem do seu id | `/revoke` no BotFather e troque no segredo |
| `comando` recusado por tamanho ou invisíveis | O executor pede uma linha só, com até 250 caracteres visíveis | Versione um script por PR |
