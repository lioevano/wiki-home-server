---
description: "Roteiro do manual de implementação: a ordem dos passos para construir o servidor doméstico do zero."
---

# Manual de Implementação

Guia passo a passo para implementar o servidor doméstico. A primeira subida segue o [Roteiro do primeiro deploy](01-roteiro-primeiro-deploy.md): ele começa pelas contas, cria o [sysadmin no GCP](02-sysadmin-gcp.md), que passa a ser a máquina de controle Ansible, e daí em diante o sysadmin conduz as fases pelo Telegram, na ordem das seções seguintes. As seções 4 a 19 explicam cada parte e trazem os arquivos; o vault nasce do `scripts/gerar_vault.py`, rodado pelo próprio script de criação do sysadmin.

## Estrutura

- **[0. Preparação e Planejamento](00-preparacao-planejamento.md):** Requisitos e estrutura do projeto.
- **[1. Roteiro do primeiro deploy](01-roteiro-primeiro-deploy.md):** a ordem da primeira subida, das contas ao último agente, com o link de cada passo. **Comece por aqui.**
- **[2. Sysadmin no GCP](02-sysadmin-gcp.md):** a máquina de controle, criada antes do servidor: Hermes com memória Honcho numa e2-micro, executor com vault e SSH atrás de botões no Telegram, e a equipe de agentes pelo GitHub.
- **[3. Máquina de Controle](03-maquina-controle-ansible.md):** vault, inventário e variáveis globais, que o sysadmin usa; e, como alternativa, a máquina de controle local na LAN.
- **[4. Proxmox VE Host](04-proxmox-ve-host.md):** Hypervisor, ZFS e NFS.
- **[5. Provisionamento de VMs](05-provisionamento-vms.md):** VMs `core-services-vm` e `ai-desktop-vm`.
- **[6. Configuração Base das VMs](06-configuracao-base-vms-ubuntu.md):** Docker, redes e Portainer.
- **[7. Rede Segura](07-rede-segura.md):** Configuração de Traefik, Cloudflare Tunnel e Authelia.
- **[8. Deploy Core](08-deploy-core.md):** Subida da stack `core` (Traefik, Cloudflared e Authelia).
- **[9. Deploy de Apps](09-deploy-apps.md):** Prometheus, Grafana, Loki, n8n, Home Assistant.
- **[10. Stack de IA](10-stack-ia.md):** gateway LiteLLM (apelidos de modelo, chaves por cliente, uso e Jev), Open WebUI, Ollama com Vulkan e o Claude Code.
- **[11. Painel e Notificações](11-painel-notificacoes.md):** Homepage, alertas do Grafana, Diun e notificações no Telegram via n8n.
- **[12. Mídia](12-midia.md):** Jellyfin, Seerr, Sonarr, Radarr, Lidarr, Prowlarr, Bazarr e qBittorrent atrás da ProtonVPN, com importação por hardlink.
- **[13. Fotos e Arquivos](13-fotos-arquivos.md):** Immich, Nextcloud e Collabora, com login OIDC do Authelia.
- **[14. Segundo Cérebro](14-segundo-cerebro.md):** vaults do Obsidian pelo Syncthing, busca local (qmd) e MCP para o Claude com escopo por vault.
- **[15. Agentes: Base](15-agentes-base.md):** hub de MCPs com leitura pública e controle pela VPN, operações (containers, stacks, Ansible) e rastreio no Langfuse.
- **[16. VPN (Tailscale)](16-vpn-tailscale.md):** acesso de fora sem o limite do túnel, rota de controle do hub só pela VPN, DNS da VPN e firewall das portas do Docker.
- **[17. IA que observa o servidor](17-ia-observa.md):** análise de cada alerta e boletim da manhã no Telegram, por uma IA que só lê (rota de leitura do hub).
- **[18. Posto de agentes](18-posto-agentes.md):** Claude Code em paralelo pelo Vibe Kanban, e cada ação dos agentes no servidor esperando a sua aprovação no Telegram ou na tela.
- **[19. Assistente (Hermes)](19-assistente.md):** assistente no Telegram que lê o servidor, busca e escreve nas notas e guarda memória, sem terminal.

A lista completa de aplicações, com stack, exposição e dados de cada uma, está no [Catálogo de Aplicações](../02-visao-geral-arquitetura/09-catalogo-aplicacoes.md); as integrações entre elas, no [Índice de Integrações](../02-visao-geral-arquitetura/10-indice-integracoes.md).

## A conferir no primeiro deploy

Estes pontos foram desenhados e testados no repositório, mas só dá para confirmar com o servidor rodando. Na primeira subida de cada seção, confira o item correspondente:

| Seção | O que conferir | Como |
|---|---|---|
| [2](02-sysadmin-gcp.md) | Memória real da e2-micro com os seis containers e um playbook rodando (decida `gcp_tipo_maquina: e2-small` com números); `hermes memory status` mostra o Honcho e o `honcho-ai` do venv selado do Hermes carrega o plugin | `free -m` e `docker stats --no-stream` na VM durante um `ansible_aplicar`; `docker exec sysadmin hermes memory status` |
| [2](02-sysadmin-gcp.md) | Primeira compilação das imagens `sysadmin` e `executor` na e2-micro (tempo e swap); o ambiente de testes não tem daemon Docker | `gcloud compute instances get-serial-port-output`; `docker images` na VM |
| [2](02-sysadmin-gcp.md) | `gcloud` no PATH das units (`/snap/bin`); `tailscale serve` com o HTTPS do tailnet desligado; swap cifrada em arquivo; o Docker esperando a unit de segredos | `systemctl status sysadmin-segredos`; `swapon --show` (deve mostrar `/dev/mapper/cryptswap`); `systemctl list-jobs` durante uma falha passageira; `tailscale serve status` |
| [2](02-sysadmin-gcp.md), [4](04-proxmox-ve-host.md) | Firewall do PVE com o Tailscale em nftables: logo após o primeiro `setup-proxmox-host.yml` (que liga a política `DROP`), o executor ainda entra no host pelo tailnet (regras de `tailscale0` para 22 e 8006, origem `100.64.0.0/10`) | `diagnostico("proxmox_main_host", "systemctl status pve-firewall")` e um novo `ansible_check` de qualquer playbook do host precisam funcionar; se não, entre pelo console do host e `pve-firewall stop` |
| [2](02-sysadmin-gcp.md), [16](16-vpn-tailscale.md) | Rotas com failover: host e core anunciam as três `/32` | Desligue a core e alcance o host (`ssh` ao `pve` pelo tailnet) |
| [2](02-sysadmin-gcp.md) | Carteiro até a conversa do Telegram: uma issue `papel:sysadmin` de teste acorda o sysadmin | Abra a issue no `homeserver-equipe`; a mensagem chega em até 2 minutos; `docker logs executor` |
| [2](02-sysadmin-gcp.md) | DNS dentro da `sysadmin_rede` e o bloqueio dos metadados, do tailnet e da LAN de casa | `docker exec sysadmin getent hosts api.anthropic.com` resolve; `docker exec sysadmin curl -m 5 http://169.254.169.254` falha (idem `100.x` e `192.168.15.x`) |
| [2](02-sysadmin-gcp.md) | GCP real: flags do `gcloud billing budgets create` e do ciclo de vida do bucket, Python 3.12 ou mais novo no Cloud Shell e a propagação da conta de serviço | Saída do `criar-sysadmin.sh`; `gcloud billing budgets list`; `gcloud storage buckets describe gs://<projeto>-sysadmin` |
| [2](02-sysadmin-gcp.md) | GitHub da conta de máquina: o token clássico (`repo`, sem `workflow`) abre PR no `wiki-home-server` e comenta no `homeserver-equipe`; um push dela em `.github/workflows/` é recusado; o *ruleset* não deixa mesclar sem a sua aprovação nem empurrar direto para a `main` (nem você) | O PR do vault na fase 1; o diário da fase; `git push origin HEAD:main` a partir de um clone seu é recusado |
| [3](03-maquina-controle-ansible.md) | O `vault.yml` do `scripts/gerar_vault.py` é aceito por todos os playbooks e o Authelia aceita o hash `pbkdf2-sha512` do admin | `setup-core-networking.yml --check`; entrar em `auth.` com a senha anotada |
| [7](07-rede-segura.md) | Authelia 4.39 sem erro nem aviso de chave obsoleta (`session.cookies`, `identity_validation`, `claims_policies`) e o Traefik v3.7 sem aviso de opção faltando; o forward-auth novo (`/api/authz/forward-auth`) manda ao portal quem não entrou e volta à página pedida | `docker logs authelia`, `docker logs traefik`; abrir `grafana.` numa janela anônima |
| [7](07-rede-segura.md) | Um `X-Forwarded-Host` forjado não pula o Authelia (`trustForwardHeader: "false"`) | De fora de casa: `curl -sI -H 'X-Forwarded-Host: jellyfin.seudominio.com' https://prometheus.seudominio.com/` responde `302` para `auth.` |
| [7](07-rede-segura.md) | Os clientes OIDC recebem e-mail, nome e grupos (política `legado` de claims no ID token) | Entrar no Immich, Nextcloud, Open WebUI, Langfuse e num conector MCP |
| [7](07-rede-segura.md) | Um usuário fora do grupo `admins` é recusado nos painéis de administração (`authelia_dominios_admins`) e não ganha conta no Open WebUI nem no Langfuse | Crie um usuário de teste só com o grupo `users` e tente abrir `grafana.` e `llm.` |
| [11](11-painel-notificacoes.md) | O Diun lê as imagens pelo `docker-socket-proxy` (se faltar uma permissão do proxy, o log do Diun mostra `403`) | `docker logs diun`, `docker logs diun_ai` |
| [11](11-painel-notificacoes.md) | O alerta `timer-falhou` dispara uma vez por falha | `sudo systemctl start backup-litellm-db.service` com o banco parado |
| [12](12-midia.md) | Widget `jellyseerr` da Homepage com o Seerr (mesma API); se a Homepage fixada ganhar o widget `seerr`, troque | Homepage, grupo Mídia |
| [13](13-fotos-arquivos.md) | O editor do Collabora abre dentro do Nextcloud apesar do `X-Frame-Options: SAMEORIGIN` global (o `frame-ancestors` do Collabora deve prevalecer) | Abrir um `.docx` no Nextcloud; console do navegador |
| [13](13-fotos-arquivos.md), [10](10-stack-ia.md), [14](14-segundo-cerebro.md), [15](15-agentes-base.md) | Login OIDC pela LAN (`extra_hosts` de `auth.` para o Traefik da `core-services-vm`) | Entrar no Immich, no Open WebUI e no Langfuse; `docker logs` sem erro de TLS ou de descoberta |
| [14](14-segundo-cerebro.md) | Módulos nativos do qmd no `node:22-bookworm-slim`, `HOME` gravável do markitdown com `--user`, a "Default Folder" criada pelo `generate` do Syncthing e o `notes_escrita` com sistema de arquivos só leitura (`read_only`) | `docker logs qmd`, primeira rodada do `notes-documentos`, painel do Syncthing, uma nota criada pela escrita |
| [15](15-agentes-base.md) | agentgateway em execução: lista de leitura, chaves, tokens em arquivo, `statefulMode: stateless`, traces no Langfuse e o campo `cliente` nos logs e no registro do `ops` | Teste de ponta a ponta da seção 15; `docker logs agentgateway`, `docker logs ops_controle` |
| [15](15-agentes-base.md) | `PUT /api/stacks` do Portainer 2.45 (redeploy pelo `ops`, pela porta HTTP 9000 do `--http-enabled`) e o alerta `ops-acao-falhou` com o formato do Loki | `ops_stack_redeploy` de uma stack de teste; uma ação recusada |
| [17](17-ia-observa.md) | O observador chama as ferramentas da rota de leitura (nomes com prefixo, respostas em SSE do hub em modo `stateless`) e o teste do ponto de contato do Grafana chega analisado; o gasto por análise (campo `tokens`) cabe no orçamento | `docker exec observador python -m observador boletim`; *Test* da integração `observador-webhook`; `docker logs observador`; tela de uso do LiteLLM |
| [18](18-posto-agentes.md) | Vibe Kanban compilado roda o Claude Code pelo LiteLLM; os perfis `DEFAULT` (pede aprovação) e `AUTONOMO` aparecem na tela; o Claude Code lê o `/etc/claude-code/managed-mcp.json`; os botões do Telegram chegam e o clique decide; o porteiro (Caddy 2.11.7 com `cap_add: NET_BIND_SERVICE`) sobe, repassa com o segredo do Traefik e dá 403 sem ele; o Vibe Kanban responde em `/api/health` atrás dele | Teste de ponta a ponta da seção 18; `docker logs posto`, `docker logs posto_porteiro`, `docker logs aprovador` |
| [19](19-assistente.md) | Hermes 0.22.5 lê o `config.yaml` gerado (modelo `custom`, os três MCPs, `disabled_toolsets` com o `cronjob`, `platforms.api_server.enabled: false`: nenhuma porta escutando) e só responde aos usuários permitidos | Teste de ponta a ponta da seção 19; `docker logs assistente` |
