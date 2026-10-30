---
description: "Roteiro do primeiro deploy: a ordem de contas, vault, playbooks e stacks do Portainer, do servidor vazio até os agentes, com o link de cada passo."
---

# Roteiro do primeiro deploy

As seções 0 a 17 explicam cada parte e trazem os arquivos. Esta página só põe tudo **na ordem da primeira subida**, com o vault gerado pelo `scripts/gerar_vault.py` ([seção 1](01-maquina-controle-ansible.md#caminho-recomendado-scriptsgerar_vaultpy)): como os segredos aleatórios já estão nele, os passos "gere o segredo X" das seções viram só "rode o playbook". Siga as fases em ordem; dentro de cada uma, os detalhes estão no link.

Todos os comandos rodam na máquina de controle, a partir de `server/ansible`. Antes de cada playbook, rode-o com `--check`; depois, sem.

```bash title="Exemplo: o padrão de cada playbook"
ansible-playbook -i inventories/home/hosts.ini playbooks/<playbook>.yml --ask-vault-pass --check
ansible-playbook -i inventories/home/hosts.ini playbooks/<playbook>.yml --ask-vault-pass
```

"Stack no Portainer" quer dizer: **Stacks → Add stack** (ou **Update the stack**, se ela já existe), no ambiente indicado, com o compose do repositório no *Web editor* e o `/opt/portainer_stack_envs/<stack>.env` colado em **Environment variables → Advanced mode** ([seção 7](07-deploy-apps.md#deploy-via-portainer)).

## Fase 0 — Fora do servidor

| Passo | Onde | Detalhe |
|---|---|---|
| Domínio na Cloudflare, token de API com edição de DNS e o túnel criado (token do conector) | Painel da Cloudflare | [Seção 6](06-deploy-core.md#pré-requisitos) |
| Chaves dos provedores de LLM (Anthropic, OpenAI, Gemini, TypeSafe) | Console de cada um | [Seção 8](08-stack-ia.md#deploy) |
| Bot de avisos no @BotFather e o id do seu chat; **outro** bot para o assistente | Telegram | [Seção 9](09-painel-notificacoes.md#bot-do-telegram-e-importação-do-workflow), [seção 17](17-assistente.md#primeira-configuração) |
| Configuração WireGuard da ProtonVPN com NAT-PMP | account.protonvpn.com | [Seção 10](10-midia.md#primeira-configuração) |
| Conta Tailscale e auth key de uso único, pré-aprovada | login.tailscale.com | [Seção 14](14-vpn-tailscale.md#primeira-configuração) |
| Disco externo para o backup e bucket B2 com chave de aplicação | Host e Backblaze | [Backup](../04-manutencao-recuperacao/02-backup-restore-estrategia.md) |
| Proteção da `main` do `wiki-home-server` (PR obrigatório, sem *force push*) e, para os agentes, um token do GitHub **sem** escrita neste repositório | GitHub → *Settings → Rules* | [Seção 16](16-posto-agentes.md#ansible-duas-aprovações) |

## Fase 1 — Máquina de controle e vault

1. `scripts/bootstrap.sh` e a chave SSH da máquina de controle ([seção 1](01-maquina-controle-ansible.md#11-instalação-do-ambiente-de-controle-scriptsbootstrapsh)).
2. Ajuste o `group_vars/all/main.yml` **pela wiki** ([seção 1](01-maquina-controle-ansible.md#variáveis-globais-não-sensíveis-ansibleinventorieshomegroup_varsallmainyml)): IPs, gateway, CIDRs, discos. O `notes_nextcloud_usuario` fica para a fase 8.
3. `python3 scripts/gerar_vault.py` (na pasta `server/`). Anote o que ele mostra no gerenciador de senhas, principalmente a senha do vault e a do **restic**.
4. `ansible-vault edit inventories/home/group_vars/all/vault.yml` e preencha o que a fase 0 trouxe: Cloudflare, `base_domain`, `letsencrypt_email`, chaves de LLM, `telegram_bot_token`, `telegram_chat_id`, `hermes_telegram_bot_token`, ProtonVPN, `tailscale_auth_key`, B2 e a senha do root do Proxmox. Os tokens criados nas telas (Grafana, Portainer, Home Assistant, n8n, widgets) ficam para depois.
5. Commit do `vault.yml` **criptografado** (o `python tools/dev.py check` acusa se não estiver): o runner do `ops` clona o repositório e precisa dele.

## Fase 2 — Host e VMs

1. Instale o Proxmox VE e crie o pool ZFS e os datasets, incluindo o `data/notes` da [seção 12](12-segundo-cerebro.md#deploy) ([seção 2](02-proxmox-ve-host.md)).
2. Usuário Ansible no host ([ações manuais prévias](02-proxmox-ve-host.md#ações-manuais-prévias-no-host-proxmox-essencial-para-ansible)) e `setup-proxmox-host.yml` (NFS, Alloy, restic).
3. Template Cloud-Init ([seção 3.1](03-provisionamento-vms.md#31-criação-de-template-de-vm-base-ubuntu-server-cloud-init)) e `vm-deploy.yml`.
4. `setup-base-ubuntu.yml` (Docker, UFW, firewall das portas do Docker, Alloy, Portainer na core e o agente na VM de IA) ([seção 4](04-configuracao-base-vms-ubuntu.md)).
5. A chave pública do runner que o `gerar_vault.py` mostrou vai para o `~/.ssh/authorized_keys` do usuário Ansible das **duas VMs** (não no host) ([seção 13](13-agentes-base.md#tokens-e-chaves)).

## Fase 3 — Rede, VPN e Portainer

1. `setup-core-networking.yml`: sobe a stack `core` (Traefik, Cloudflared, Authelia) ([seção 6](06-deploy-core.md)).
2. Public Hostnames do túnel ([seção 5.5](05-rede-segura.md#55-configuração-de-dns-na-cloudflare)); abra `auth.` e registre o 2FA. A senha do admin do Authelia é a que o `gerar_vault.py` mostrou.
3. `setup-vpn.yml` e, no painel do Tailscale, rotas, expiração da chave, DNS e ACL ([seção 14](14-vpn-tailscale.md#primeira-configuração)).
4. **Portainer, nos primeiros 5 minutos:** administrador, ambiente `local` e o agente `ai-desktop-vm`; crie o token de API e grave em `portainer_api_key` ([seção 7](07-deploy-apps.md#primeiro-acesso-ao-portainer)).

## Fase 4 — Apps da core

1. `setup-productivity-automation-volumes.yml`, `setup-n8n-volumes.yml` e `setup-monitoring-stack-volumes.yml`.
2. Stack `apps` no ambiente `local` ([seção 7](07-deploy-apps.md)).
3. Importe e ative o workflow `notificar` do n8n ([seção 9](09-painel-notificacoes.md#bot-do-telegram-e-importação-do-workflow)) e configure o Home Assistant ([seção 7](07-deploy-apps.md#notas-por-serviço)).

## Fase 5 — IA

1. `setup-ai-volumes.yml` (imagem do Ollama, LiteLLM, `ai.env`).
2. Stack `ai` no ambiente `ai-desktop-vm` ([seção 8](08-stack-ia.md#deploy)).
3. `setup-ai-keys.yml`: cria no LiteLLM **todas** as chaves do vault (Open WebUI, Claude Code, n8n, observador, agentes, assistente) com os orçamentos.
4. `docker exec -it ollama ollama pull llama3.2:3b`.

## Fase 6 — Mídia

1. `setup-media-stack-volumes.yml` e stack `media` no ambiente `local` ([seção 10](10-midia.md#deploy)).
2. **Logo em seguida**, Jellyfin e Seerr (quem chegar primeiro vira administrador); depois o resto da [primeira configuração](10-midia.md#primeira-configuração).
3. `sudo docker restart prometheus grafana`, para carregar os alertas da mídia.

## Fase 7 — Fotos e arquivos

1. `setup-photos-stack-volumes.yml`, `setup-cloud-stack-volumes.yml` e as stacks `photos` e `cloud` no ambiente `local` ([seção 11](11-fotos-arquivos.md#deploy)).
2. **Logo em seguida**, o administrador do Immich com o e-mail do Authelia; depois o Nextcloud ([primeiro acesso](11-fotos-arquivos.md#primeiro-acesso)).

## Fase 8 — Segundo cérebro

1. `notes_nextcloud_usuario` no `group_vars` (pela wiki) com o seu id no Nextcloud.
2. `setup-notes-volumes.yml`, stack `notes` no ambiente `ai-desktop-vm` e **Update the stack** da `ai` ([seção 12](12-segundo-cerebro.md#deploy)).
3. Timers `notes-documentos` e `notes-indice`, pareamento do Syncthing e os conectores do Claude.

## Fase 9 — Base dos agentes

1. Tokens nas telas: as duas service accounts do Grafana, o MCP do Home Assistant e o do n8n ([seção 13](13-agentes-base.md#tokens-e-chaves)); grave no vault.
2. `setup-agents-volumes.yml`, `setup-langfuse-volumes.yml`, `setup-ai-volumes.yml` e `setup-monitoring-stack-volumes.yml`.
3. Stack `langfuse` (ambiente `ai-desktop-vm`), **Update the stack** da `ai`, stack `agents` (ambiente `local`) e **Update the stack** da `apps` (o Grafana recebe o token do observador) ([seção 13](13-agentes-base.md#deploy), [seção 15](15-ia-observa.md#primeira-configuração)).
4. Conecte o Claude: o conector **Servidor** no claude.ai e a rota de controle no Claude Code, com o Tailscale ligado ([seção 13](13-agentes-base.md#conectar-o-claude)).

## Fase 10 — Posto e assistente

1. `setup-posto-volumes.yml` (a primeira compilação do Vibe Kanban leva dezenas de minutos) e stack `posto` no ambiente `ai-desktop-vm` ([seção 16](16-posto-agentes.md#primeira-configuração)).
2. `setup-assistente-volumes.yml` e stack `assistente` no ambiente `ai-desktop-vm`; mande `/start` ao bot ([seção 17](17-assistente.md#primeira-configuração)).

## Fase 11 — Painel e backup

1. Chaves dos widgets nas telas de cada aplicação, gravadas em `homepage_widget_keys`; `setup-monitoring-stack-volumes.yml` e **Update the stack** da `apps` ([seção 9](09-painel-notificacoes.md#chaves-de-api-dos-widgets)).
2. Rode um backup e **teste uma restauração** ([backup](../04-manutencao-recuperacao/02-backup-restore-estrategia.md)).

## Depois de cada fase

Faça o teste de ponta a ponta da seção correspondente e confira a linha dela em [A conferir no primeiro deploy](index.md#a-conferir-no-primeiro-deploy). Depois de tudo de pé, o `full-deploy.yml` reaplica a configuração inteira de uma vez (sem criar VMs nem subir stacks).
