# Design: mídia completa (stack `media`, VPN, hardlinks e pedidos)

- **Data:** 2026-10-19
- **Autor:** Léo Ivan (com Claude)
- **Status:** aguardando revisão
- **Caminho:** arquitetural — sub-projeto **2** da refatoração do server (1 Alloy ✓, 2 mídia, 3 fotos e arquivos, 4 IA).
- **Depende de:** catálogo e índice (`2026-10-12`), painel e notificações (`2026-10-14`), coleta com Alloy (`2026-10-18`).

## 1. Objetivo

Um fluxo de mídia completo e automático para o Léo e a família: um pedido no **Seerr** vira download pelo **qBittorrent atrás da VPN**, é importado **por hardlink** para a biblioteca, ganha **legenda pt-BR** e aparece no **Jellyfin**, dentro e fora de casa.

### Critérios de pronto

- Stack nova `media` (`docker/stacks/media/docker-compose.yml`) com os 11 serviços da seção 3; nenhum serviço de mídia na stack `apps`.
- Um único dataset `media` montado como `/data`; dataset `downloads` removido de wiki e server.
- qBittorrent só com rede via gluetun (`network_mode: service:gluetun`), ProtonVPN WireGuard com porta encaminhada repassada automaticamente.
- Catálogo com as 7 aplicações novas e as 4 movidas; índice atualizado (`dados` DAD-4, `notificacoes` NTF-3); `audit-integrations` sem ❌/⚠️ (só `✋` de passos manuais documentados).
- Página nova `01-manual-implementacao/10-midia.md` com stack, variáveis, primeira configuração e teste de ponta a ponta.
- `dev.py test`, `check` (só `REF-PENDING` do vault), `build` (sem WARNING nem INFO de âncora) e `lint` passam.

## 2. Decisões

| # | Decisão | Escolha |
|---|---|---|
| M1 | Aplicações novas | Prowlarr, Bazarr, Seerr, Lidarr, FlareSolverr, Recyclarr, gluetun. |
| M2 | Pedidos | **Seerr** (`ghcr.io/seerr-team/seerr`): Jellyseerr e Overseerr foram descontinuados e fundidos nele. |
| M3 | Layout | Dataset único `media` → `/data` com `torrents/{movies,tv,music}` e `media/{movies,tv,music}` (TRaSH Guides); importação por hardlink. Sai o dataset `downloads`. |
| M4 | VPN | ProtonVPN, WireGuard, `VPN_PORT_FORWARDING=on`, `PORT_FORWARD_ONLY=on`; `VPN_PORT_FORWARDING_UP_COMMAND` grava a porta no qBittorrent pela API local. Kill switch = firewall do gluetun. |
| M5 | Stack | `media` própria na `core-services-vm`, redes externas `proxy` e `internal_services`, carregando `media.env` direto (sem passar pelo `apps.env`). |
| M6 | Exposição | `jellyfin` e `seerr` `publica` (login próprio, pelo túnel); demais `protegida` (Authelia); `flaresolverr`, `recyclarr`, `gluetun` `interna`. |
| M7 | Chaves das \*arr | `arr_api_keys.{sonarr,radarr,lidarr,prowlarr}` no vault → `<APP>__AUTH__APIKEY`; `<APP>__AUTH__METHOD=External` (o Authelia já protege a interface). |
| M8 | Perfis de qualidade | Recyclarr com config gerada pelo Ansible: Sonarr WEB-1080p, Radarr HD Bluray + WEB (TRaSH). |
| M9 | Ligações entre apps | Passos manuais documentados (ficam no banco de cada app), com os endereços internos exatos. |

## 3. Serviços da stack `media`

| Serviço | Imagem | Porta interna | Redes | `/data` | Exposição / subdomínio |
|---|---|---|---|---|---|
| `jellyfin` | `jellyfin/jellyfin` | 8096 | proxy | `/data/media` (ro) + `/dev/dri` | publica / `jellyfin` |
| `seerr` | `ghcr.io/seerr-team/seerr` | 5055 | proxy, internal_services | — | publica / `pedidos` |
| `sonarr` | `lscr.io/linuxserver/sonarr` | 8989 | proxy, internal_services | `/data` | protegida / `sonarr` |
| `radarr` | `lscr.io/linuxserver/radarr` | 7878 | proxy, internal_services | `/data` | protegida / `radarr` |
| `lidarr` | `lscr.io/linuxserver/lidarr` | 8686 | proxy, internal_services | `/data` | protegida / `lidarr` |
| `prowlarr` | `lscr.io/linuxserver/prowlarr` | 9696 | proxy, internal_services | — | protegida / `prowlarr` |
| `bazarr` | `lscr.io/linuxserver/bazarr` | 6767 | proxy, internal_services | `/data/media` | protegida / `bazarr` |
| `gluetun` | `qmcgaw/gluetun` | 8088 (do qBittorrent) | proxy, internal_services | — | interna (as labels do router `qbittorrent` ficam nele) |
| `qbittorrent` | `lscr.io/linuxserver/qbittorrent` | 8088 | `network_mode: service:gluetun` | `/data/torrents` | protegida / `qbittorrent` (via gluetun) |
| `flaresolverr` | `ghcr.io/flaresolverr/flaresolverr` | 8191 | internal_services | — | interna |
| `recyclarr` | `ghcr.io/recyclarr/recyclarr` | — | internal_services | — | interna |

- Configurações em `${VM_NFS_MOUNT_BASE_PATH}/${ZFS_DOCKER_VOLUMES_DATASET_NAME}/<app>/config` (variáveis `MEDIA_STACK_<APP>_CONFIG_PATH`); `/data` sempre de `MEDIA_STACK_DATA_PATH` (= NFS + `zfs_media_dataset_name`).
- gluetun: `cap_add: [NET_ADMIN]`, `devices: [/dev/net/tun]`, `VPN_SERVICE_PROVIDER=protonvpn`, `VPN_TYPE=wireguard`, `WIREGUARD_PRIVATE_KEY=${PROTONVPN_WIREGUARD_PRIVATE_KEY}`; o qBittorrent depende dele (`depends_on` com `condition: service_healthy`).
- O comando de porta usa `http://127.0.0.1:8088/api/v2/app/setPreferences` (WebUI do qBittorrent em 8088) com `listen_port`, `current_network_interface` = interface da VPN, `random_port=false`, `upnp=false`, e o comando de queda correspondente.
- Recyclarr: `/config/recyclarr.yml` gerado pelo playbook; agenda do próprio container (diária).

## 4. Dados

- Host: um dataset `data/media` (já existe); o `data/downloads` sai dos passos manuais da página 02, do `etc_exports.j2`, das montagens do role `common` e de `zfs_downloads_dataset_name`.
- `setup-media-stack-volumes.yml` cria `torrents/{movies,tv,music}` e `media/{movies,tv,music}` no dataset, com dono `docker_puid:docker_pgid`, e os diretórios de config das 10 apps com volume.
- Índice `dados`, regra nova **DAD-4**: aplicação de Categoria `mídia` com acesso a arquivos de mídia monta `/data` (ou subpasta) a partir de `MEDIA_STACK_DATA_PATH`, nunca de duas variáveis diferentes (hardlink exige o mesmo sistema de arquivos).

## 5. Variáveis e segredos

| No `media.env` | Origem |
|---|---|
| `MEDIA_STACK_DATA_PATH`, `MEDIA_STACK_<APP>_CONFIG_PATH` | `vm_nfs_mount_base_path` + datasets (`group_vars`) |
| `SONARR_API_KEY`, `RADARR_API_KEY`, `LIDARR_API_KEY`, `PROWLARR_API_KEY` | vault `arr_api_keys.*` |
| `PROTONVPN_WIREGUARD_PRIVATE_KEY` | vault `protonvpn_wireguard_private_key` |
| `DOCKER_PUID`, `DOCKER_PGID`, `SYSTEM_TIMEZONE`, `BASE_DOMAIN_FROM_VAULT` | como nas demais stacks |

- `media.env` passa a `mode: '0600'` (tem segredos) e é carregado direto pela stack `media` no Portainer; sai da junção do `apps.env` (página 07).
- Saem `MEDIA_STACK_MOVIES_PATH`, `MEDIA_STACK_TVSHOWS_PATH`, `MEDIA_STACK_MUSIC_PATH`, `ZFS_DOWNLOADS_DATASET_NAME_NFS_PATH`.
- Homepage (no `monitoring.env`): `HOMEPAGE_VAR_SONARR_KEY`/`RADARR_KEY` passam a vir de `arr_api_keys`; entram `HOMEPAGE_VAR_LIDARR_KEY`, `HOMEPAGE_VAR_PROWLARR_KEY` (de `arr_api_keys`), `HOMEPAGE_VAR_BAZARR_KEY` e `HOMEPAGE_VAR_SEERR_KEY` (de `homepage_widget_keys.bazarr`/`.seerr`, geradas na interface: passo manual). Saem `homepage_widget_keys.sonarr`/`.radarr`.
- Chaves novas entram no bloco literal do `vault.yml.example` (página 01).

## 6. Integrações

| Integração | Efeito |
|---|---|
| roteamento / autenticacao / acesso-externo | Labels Traefik nos 8 serviços com subdomínio (o do qBittorrent no `gluetun`); `jellyfin` e `seerr` sem middleware (`publica`), os demais com `authelia-forwardauth@docker`. |
| metricas | Métricas = `não` para todas (nenhuma expõe `/metrics` próprio); métricas por container vêm do cAdvisor do Alloy. |
| logs / dados / variaveis / documentacao | Como nas demais aplicações (Alloy; NFS; `media.env`; página 10). |
| notificacoes | NTF-1: alvos no `blackbox_http` pela URL interna (`http://sonarr:8989/ping`, `http://radarr:7878/ping`, `http://lidarr:8686/ping`, `http://prowlarr:9696/ping`, `http://bazarr:6767/`, `http://seerr:5055/api/v1/status`, `http://jellyfin:8096/health`, `http://gluetun:8088/` com `app: qbittorrent`). NTF-3: a lista de apps com webhook nativo ganha `lidarr`, `prowlarr` e `seerr`. O resumo do `servico-fora-do-ar` para `app="qbittorrent"` diz "qBittorrent ou VPN fora". |
| painel | Entradas para as 8 aplicações com subdomínio; widgets para sonarr, radarr, lidarr, prowlarr, bazarr, seerr e qbittorrent (tipo de widget do Seerr conferido na documentação da Homepage ao escrever o plano). |

Catálogo: novas `bazarr`, `flaresolverr`, `gluetun`, `lidarr`, `prowlarr`, `recyclarr`, `seerr`; `jellyfin`, `qbittorrent`, `radarr`, `sonarr` passam a `media / core-services-vm` e `jellyfin` a `publica`.

## 7. Páginas

| Página | Mudança |
|---|---|
| `01-manual-implementacao/10-midia.md` (nova) | Fluxo, layout `/data`, stack e variáveis, deploy no Portainer, primeira configuração (lista abaixo), ProtonVPN, teste de ponta a ponta. |
| `07-deploy-apps.md` | Sai a mídia (serviços, `media.env` na junção, notas por serviço); aponta para a 10. |
| `02-proxmox-ve-host.md` | Sai o dataset `downloads` (criação manual e `etc_exports.j2`). |
| `04-configuracao-base-vms-ubuntu.md` | Montagens NFS sem `downloads`. |
| `09-painel-notificacoes.md` | Alvos, widgets e webhooks novos. |
| `02-visao-geral-arquitetura/06-principios-seguranca.md` | Jellyfin e Seerr públicos: bloqueio após tentativas de login, admin sem acesso remoto, risco dos termos da Cloudflare para vídeo pelo túnel. |
| `02-visao-geral-arquitetura/03-armazenamento-zfs-nfs.md` | Layout `/data` e hardlinks. |
| `mkdocs.yml`, índices das seções, catálogo, índice, `INDEX.md` | Página nova e aplicações. |

**Primeira configuração (passos manuais, na página 10):**
1. ProtonVPN: gerar configuração WireGuard com **NAT-PMP** ligado; `PrivateKey` → vault `protonvpn_wireguard_private_key`.
2. qBittorrent: trocar a senha inicial; marcar "Bypass authentication for clients on localhost"; caminho padrão `/data/torrents`; categorias `movies`, `tv`, `music` em `/data/torrents/<categoria>`.
3. Prowlarr: FlareSolverr em `http://flaresolverr:8191` (tag `flaresolverr`); apps Sonarr, Radarr e Lidarr com `http://<app>:<porta>` e `arr_api_keys`; indexadores.
4. Sonarr, Radarr, Lidarr: cliente de download `http://gluetun:8088` com a categoria; pastas raiz `/data/media/{tv,movies,music}`.
5. Bazarr: Sonarr e Radarr; idioma pt-BR; provedores de legenda.
6. Jellyfin: bibliotecas em `/data/media/{movies,tv,music}`; *Login attempts before lockout*; desmarcar acesso remoto do admin; usuários da família.
7. Seerr: entrar com o Jellyfin; Sonarr e Radarr com `arr_api_keys`; webhook para o n8n.
8. Homepage: chaves do Bazarr e do Seerr → vault `homepage_widget_keys.bazarr`/`.seerr`.

## 8. Falhas

| Situação | Comportamento |
|---|---|
| VPN cai | Firewall do gluetun corta a saída do qBittorrent (sem vazamento de IP); a probe `gluetun:8088` falha → `servico-fora-do-ar` ("qBittorrent ou VPN fora"); o gluetun reconecta sozinho. |
| Porta encaminhada muda | O gluetun roda o comando de porta e grava a nova no qBittorrent. |
| Indexador atrás de Cloudflare | Prowlarr passa pelo FlareSolverr (tag no indexador). |
| Recyclarr falha | Erro no log (Loki) e no `container-reiniciando`; as \*arr seguem com a configuração anterior. |
| Importação | Hardlink no mesmo dataset; DAD-4 impede montar `/data` de fontes diferentes. |

## 9. Verificação

- **Testes** (`tools/wikisync/tests/`): todo serviço de mídia que monta `/data` usa `MEDIA_STACK_DATA_PATH`; `qbittorrent` com `network_mode: service:gluetun`, sem `ports`, `networks` nem labels; nenhum serviço de mídia na `apps`; `recyclarr.yml.j2` renderiza YAML válido; `stack_configs` do playbook de mídia tem `SONARR_API_KEY`, `RADARR_API_KEY`, `LIDARR_API_KEY`, `PROWLARR_API_KEY` e `PROTONVPN_WIREGUARD_PRIVATE_KEY`, e o `media.env` é `0600`; nenhuma menção a `downloads`/`ZFS_DOWNLOADS` no server.
- **Antes do commit:** `check`, `build`, `lint`, `audit-integrations`, `update-index`.
- **Pós-deploy (página 10):** IP de saída do qBittorrent é da Proton (`docker exec qbittorrent curl -s ifconfig.me`); com o gluetun parado, o qBittorrent fica sem rede; pedido de um título de domínio público no Seerr chega ao Jellyfin; `stat -c %h` do arquivo importado = 2; legenda pt-BR presente.

## 10. Fora de escopo

- Streaming fora de casa por VPN pessoal (Tailscale etc.).
- Unpackerr, Readarr, exportarr, dashboards.
- Automatizar as ligações entre apps por API.

## 11. Riscos

- **Termos da Cloudflare:** vídeo pelo túnel pode violar as regras de uso; mitigação futura = streaming por VPN pessoal (fora de escopo).
- **Jellyfin e Seerr na internet:** login exposto a força bruta; mitigação = bloqueio por tentativas, senhas fortes, admin sem acesso remoto.
- **ProtonVPN:** encaminhamento de porta só em servidores P2P e planos pagos; sem porta, o qBittorrent funciona com menos conexões.
