---
description: "Catálogo de aplicações do servidor: fatos de cada aplicação (stack, serviços, exposição, dados, métricas, integrações providas) que guiam as integrações."
---

# Catálogo de Aplicações

Este catálogo declara **o que cada aplicação é** — os fatos que decidem quais integrações ela recebe. As regras de cada integração estão no [Índice de Integrações](10-indice-integracoes.md); quem aplica e verifica essas regras são as skills `audit-integrations`, `add-app`, `remove-app`, `add-integration` e `remove-integration` (veja `AGENTS.md` na raiz do repositório).

## Como usar

- **Adicionar ou remover uma aplicação começa por esta tabela.** O restante (compose, labels, variáveis, páginas, índice) é derivado dela.
- **Uma linha por aplicação** — o que o usuário enxerga. Serviços auxiliares (banco, cache) entram na coluna Serviços da aplicação principal.
- **O primeiro serviço da coluna Serviços é o principal**: é ele que recebe roteamento e autenticação. Os demais não precisam de router.
- Aplicações instaladas fora de um `docker-compose.yml` (ex.: Portainer, pelo Ansible) usam `ansible:<role>` em Stack.
- Valor marcado `?` é incerto e **precisa de decisão humana** antes de qualquer mudança derivada dele.

## Colunas

| Coluna | Valores |
|---|---|
| Aplicação | id único em kebab-case |
| Categoria | `infra` · `produtividade` · `mídia` · `monitoramento` · `automação` · `ia` |
| Stack / VM | `<stack>` / `<vm>` — stack = pasta em `docker/stacks/` ou `ansible:<role>`; aplicação presente em mais de uma VM lista cada par separado por `;` |
| Serviços | nomes exatos no compose; o primeiro é o principal |
| Exposição | `publica` (internet, sem login) · `protegida` (internet, com Authelia) · `interna` (só rede local/Docker) |
| Subdomínio | subdomínio em `<sub>.seudominio.com`, ou `—` se `interna` |
| Dados | `nfs` (datasets ZFS via NFS, com snapshots) · `local` (disco da VM) · `nenhum` |
| Métricas | `sim` se o Prometheus coleta métricas da aplicação · `não` |
| Provê | ids de integrações que a aplicação fornece, ou `—` |
| Ajustes | `+<id>` entra numa integração opcional · `-<id>` sai de uma integração que se aplicaria · `—` |
| Página | página da wiki que documenta a aplicação |

## Aplicações

| Aplicação | Categoria | Stack / VM | Serviços | Exposição | Subdomínio | Dados | Métricas | Provê | Ajustes | Página |
|---|---|---|---|---|---|---|---|---|---|---|
| `agentgateway` | ia | agents / core-services-vm | `mcp_auth_servidor`, `agentgateway`, `mcp_grafana_leitura`, `mcp_grafana_controle`, `ops_leitura`, `ops_controle` | publica | `servidor` | local | sim | — | `+mcp` | [Agentes: base](../01-manual-implementacao/13-agentes-base.md) |
| `alloy` | monitoramento | ansible:infra/alloy / proxmox_main_host; ansible:infra/alloy / core-services-vm; ansible:infra/alloy / ai-desktop-vm | `alloy` | interna | — | nenhum | sim | `logs`, `metricas` | — | [Configuração base das VMs](../01-manual-implementacao/04-configuracao-base-vms-ubuntu.md#44-coleta-com-grafana-alloy-ansiblerolesinfraalloy) |
| `authelia` | infra | core / core-services-vm | `authelia`, `authelia_db` | publica | `auth` | nfs | não | `autenticacao`, `mcp` | — | [Rede segura](../01-manual-implementacao/05-rede-segura.md) |
| `bazarr` | mídia | media / core-services-vm | `bazarr` | protegida | `bazarr` | nfs | não | — | — | [Mídia](../01-manual-implementacao/10-midia.md) |
| `blackbox-exporter` | monitoramento | apps / core-services-vm | `blackbox-exporter` | interna | — | nfs | sim | — | — | [Painel e notificações](../01-manual-implementacao/09-painel-notificacoes.md) |
| `cloudflared` | infra | core / core-services-vm | `cloudflared` | interna | — | nenhum | sim | `acesso-externo` | — | [Rede segura](../01-manual-implementacao/05-rede-segura.md) |
| `collabora` | produtividade | cloud / core-services-vm | `collabora` | publica | `office` | nenhum | não | — | — | [Fotos e arquivos](../01-manual-implementacao/11-fotos-arquivos.md) |
| `coredns` | infra | ansible:infra/tailscale / core-services-vm | `coredns` | interna | — | nenhum | não | — | — | [VPN (Tailscale)](../01-manual-implementacao/14-vpn-tailscale.md) |
| `diun` | monitoramento | apps / core-services-vm; ai / ai-desktop-vm | `diun`, `diun_ai` | interna | — | nfs | não | — | — | [Painel e notificações](../01-manual-implementacao/09-painel-notificacoes.md) |
| `docker-socket-proxy` | infra | apps / core-services-vm; ai / ai-desktop-vm | `docker-socket-proxy`, `docker-socket-proxy-ai` | interna | — | nenhum | não | — | — | [Painel e notificações](../01-manual-implementacao/09-painel-notificacoes.md) |
| `flaresolverr` | mídia | media / core-services-vm | `flaresolverr` | interna | — | nenhum | não | — | — | [Mídia](../01-manual-implementacao/10-midia.md) |
| `gluetun` | mídia | media / core-services-vm | `gluetun` | interna | — | nfs | não | — | — | [Mídia](../01-manual-implementacao/10-midia.md) |
| `grafana` | monitoramento | apps / core-services-vm | `grafana`, `grafana_db` | protegida | `grafana` | nfs | não | — | — | [Deploy de apps](../01-manual-implementacao/07-deploy-apps.md) |
| `homeassistant` | automação | apps / core-services-vm | `homeassistant` | protegida | `hass` | nfs | não | — | — | [Deploy de apps](../01-manual-implementacao/07-deploy-apps.md) |
| `homepage` | infra | apps / core-services-vm | `homepage` | protegida | `home` | nfs | não | `painel` | — | [Painel e notificações](../01-manual-implementacao/09-painel-notificacoes.md) |
| `immich` | produtividade | photos / core-services-vm | `immich_server`, `immich_ml`, `immich_redis`, `immich_db` | publica | `fotos` | nfs | não | — | — | [Fotos e arquivos](../01-manual-implementacao/11-fotos-arquivos.md) |
| `jellyfin` | mídia | media / core-services-vm | `jellyfin` | publica | `jellyfin` | nfs | não | — | — | [Mídia](../01-manual-implementacao/10-midia.md) |
| `langfuse` | ia | langfuse / ai-desktop-vm | `langfuse_web`, `langfuse_worker`, `langfuse_db`, `langfuse_clickhouse`, `langfuse_redis`, `langfuse_minio` | protegida | `langfuse` | local | não | — | — | [Agentes: base](../01-manual-implementacao/13-agentes-base.md) |
| `lidarr` | mídia | media / core-services-vm | `lidarr` | protegida | `lidarr` | nfs | não | — | — | [Mídia](../01-manual-implementacao/10-midia.md) |
| `litellm` | ia | ai / ai-desktop-vm | `litellm`, `litellm_db` | protegida | `llm` | nfs | sim | `llm` | — | [Stack de IA](../01-manual-implementacao/08-stack-ia.md) |
| `loki` | monitoramento | apps / core-services-vm | `loki` | interna | — | nfs | não | `logs` | — | [Deploy de apps](../01-manual-implementacao/07-deploy-apps.md) |
| `n8n` | automação | apps / core-services-vm | `n8n` | protegida | `n8n` | nfs | não | `notificacoes` | — | [Deploy de apps](../01-manual-implementacao/07-deploy-apps.md) |
| `nextcloud` | produtividade | cloud / core-services-vm | `nextcloud_app`, `nextcloud_cron`, `nextcloud_db`, `nextcloud_redis` | publica | `nextcloud` | nfs | não | — | — | [Fotos e arquivos](../01-manual-implementacao/11-fotos-arquivos.md) |
| `notas` | ia | notes / ai-desktop-vm | `mcp_auth_busca`, `qmd` | publica | `notas` | nfs | não | — | `+mcp` | [Segundo cérebro](../01-manual-implementacao/12-segundo-cerebro.md) |
| `notas-escrita` | ia | notes / ai-desktop-vm | `mcp_auth_escrita`, `notes_escrita` | publica | `escrita` | nfs | não | — | `+mcp` | [Segundo cérebro](../01-manual-implementacao/12-segundo-cerebro.md) |
| `ollama` | ia | ai / ai-desktop-vm | `ollama` | interna | — | nfs | não | — | — | [Stack de IA](../01-manual-implementacao/08-stack-ia.md) |
| `open-webui` | ia | ai / ai-desktop-vm | `open-webui` | protegida | `openwebui` | nfs | não | — | `+llm` | [Stack de IA](../01-manual-implementacao/08-stack-ia.md) |
| `portainer` | infra | ansible:infra/docker / core-services-vm | `portainer` | protegida | `portainer` | nfs | não | — | — | [Configuração base das VMs](../01-manual-implementacao/04-configuracao-base-vms-ubuntu.md) |
| `prometheus` | monitoramento | apps / core-services-vm | `prometheus` | protegida | `prometheus` | nfs | sim | `metricas` | — | [Deploy de apps](../01-manual-implementacao/07-deploy-apps.md) |
| `prowlarr` | mídia | media / core-services-vm | `prowlarr` | protegida | `prowlarr` | nfs | não | — | — | [Mídia](../01-manual-implementacao/10-midia.md) |
| `qbittorrent` | mídia | media / core-services-vm | `qbittorrent` | protegida | `qbittorrent` | nfs | não | — | — | [Mídia](../01-manual-implementacao/10-midia.md) |
| `radarr` | mídia | media / core-services-vm | `radarr` | protegida | `radarr` | nfs | não | — | — | [Mídia](../01-manual-implementacao/10-midia.md) |
| `recyclarr` | mídia | media / core-services-vm | `recyclarr` | interna | — | nfs | não | — | — | [Mídia](../01-manual-implementacao/10-midia.md) |
| `seerr` | mídia | media / core-services-vm | `seerr` | publica | `pedidos` | nfs | não | — | — | [Mídia](../01-manual-implementacao/10-midia.md) |
| `sonarr` | mídia | media / core-services-vm | `sonarr` | protegida | `sonarr` | nfs | não | — | — | [Mídia](../01-manual-implementacao/10-midia.md) |
| `syncthing` | produtividade | notes / ai-desktop-vm | `syncthing` | protegida | `sync` | nfs | não | — | — | [Segundo cérebro](../01-manual-implementacao/12-segundo-cerebro.md) |
| `tailscale` | infra | ansible:infra/tailscale / core-services-vm | `tailscaled` | interna | — | nenhum | não | — | — | [VPN (Tailscale)](../01-manual-implementacao/14-vpn-tailscale.md) |
| `traefik` | infra | core / core-services-vm | `traefik` | protegida | `traefik` | nfs | não | `roteamento` | — | [Rede segura](../01-manual-implementacao/05-rede-segura.md) |
