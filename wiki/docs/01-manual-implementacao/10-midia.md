---
description: "Stack media: Jellyfin, Seerr, Sonarr, Radarr, Lidarr, Prowlarr, Bazarr, Recyclarr e qBittorrent atrás da ProtonVPN (gluetun), com /data único e importação por hardlink."
---

# Seção 10: Mídia (Jellyfin, *arr, Seerr e VPN)

Um pedido feito no **Seerr** vira download no **qBittorrent**, que só sai para a internet pela **ProtonVPN** (gluetun). O Sonarr, o Radarr ou o Lidarr importam o arquivo **por hardlink** para a biblioteca, o **Bazarr** busca a legenda em pt-BR e o título aparece no **Jellyfin**, dentro e fora de casa.

```
internet ──► Traefik ──► jellyfin.  pedidos. (Seerr)        públicos, login próprio
                    └──► sonarr. radarr. lidarr. prowlarr. bazarr. qbittorrent.   Authelia

Seerr ─► Sonarr/Radarr ─► Prowlarr ─► (FlareSolverr) ─► indexadores
                     └─► gluetun:8088 (qBittorrent) ─► ProtonVPN (WireGuard + porta NAT-PMP)
Sonarr/Radarr/Lidarr ─ hardlink ─► /data/media ◄─ Jellyfin (ro), Bazarr (legendas)
Recyclarr ─(API)─► Sonarr/Radarr   (perfis TRaSH, de arquivo versionado)
```

## Serviços

A stack `media` fica em `docker/stacks/media/docker-compose.yml`, na `core-services-vm`, nas redes externas `proxy` e `internal_services` (as mesmas da stack `apps`, então Traefik, Homepage e blackbox-exporter enxergam tudo).

| Serviço | Para que serve | Endereço interno | Acesso externo |
|---|---|---|---|
| `jellyfin` | Biblioteca e reprodução | `http://jellyfin:8096` | `jellyfin.seudominio.com` (público) |
| `seerr` | Pedidos de filmes e séries (substitui o Jellyseerr) | `http://seerr:5055` | `pedidos.seudominio.com` (público) |
| `sonarr` / `radarr` / `lidarr` | Séries / filmes / música | `http://sonarr:8989`, `http://radarr:7878`, `http://lidarr:8686` | subdomínio próprio, Authelia |
| `prowlarr` | Indexadores para as *arr | `http://prowlarr:9696` | `prowlarr.`, Authelia |
| `bazarr` | Legendas | `http://bazarr:6767` | `bazarr.`, Authelia |
| `flaresolverr` | Resolve o desafio Cloudflare de indexadores | `http://flaresolverr:8191` | — |
| `recyclarr` | Perfis de qualidade do TRaSH Guides | — | — |
| `gluetun` | VPN e kill switch | `http://gluetun:8088` (WebUI do qBittorrent) | `qbittorrent.`, Authelia |
| `qbittorrent` | Cliente de torrent, só pela rede do gluetun | `http://gluetun:8088` | via gluetun |

O qBittorrent usa `network_mode: service:gluetun`: ele não tem rede própria, só a do gluetun. Se o túnel cair, o firewall do gluetun corta toda a saída (sem vazar o IP de casa). Por isso o router do Traefik do qBittorrent fica nas labels do `gluetun`, e todos o acessam por `gluetun:8088`.

## Dados: `/data` único

O dataset `media` (montado na VM em `<vm_nfs_mount_base_path>/<zfs_media_dataset_name>`) vira `/data` nos containers, no layout do TRaSH Guides:

```
/data
├── torrents/{movies,tv,music}   ← downloads do qBittorrent (por categoria)
└── media/{movies,tv,music}      ← biblioteca do Jellyfin
```

| Serviço | Monta |
|---|---|
| qBittorrent | `/data/torrents` |
| Sonarr, Radarr, Lidarr | `/data` (vê as duas pastas: importa por hardlink) |
| Bazarr | `/data/media` |
| Jellyfin | `/data/media` (só leitura) |

Como torrents e biblioteca estão no mesmo sistema de arquivos, a importação é um **hardlink**: o arquivo não é copiado e não ocupa o dobro do espaço enquanto o torrent semeia. Toda montagem de `/data` vem da mesma variável `MEDIA_STACK_DATA_PATH` (regra DAD-4 do [índice de integrações](../02-visao-geral-arquitetura/10-indice-integracoes.md#dados)).

!!! info "Transcodificação por hardware"
    O Jellyfin transcodifica na CPU: a `core-services-vm` não tem GPU (a RX 5600 XT está na `ai-desktop-vm`, com o Ollama). Quando houver uma iGPU ou outra GPU passada para a core, acrescente ao serviço `jellyfin` `devices: ["/dev/dri:/dev/dri"]` e `group_add` com o GID do grupo `render` da VM, e ligue a aceleração em *Dashboard → Playback*. Sem o dispositivo na VM, essa linha impediria a stack de subir, por isso ela não vem pronta.

## Deploy

1. No vault (`ansible-vault edit inventories/home/group_vars/all/vault.yml`, a partir de `server/ansible`): `arr_api_keys` (uma chave de 32 caracteres hexadecimais por aplicação: `openssl rand -hex 16`) e `protonvpn_wireguard_private_key` (passo 1 da primeira configuração).
2. Volumes, árvore `/data`, configuração do Recyclarr e `media.env`:
   ```bash
   ansible-playbook -i inventories/home/hosts.ini playbooks/setup-media-stack-volumes.yml --ask-vault-pass --check
   ansible-playbook -i inventories/home/hosts.ini playbooks/setup-media-stack-volumes.yml --ask-vault-pass
   ```
   O playbook `ansible/playbooks/setup-media-stack-volumes.yml` gera `<NFS>/recyclarr/config/recyclarr.yml` a partir de `ansible/templates/recyclarr.yml.j2` e o `/opt/portainer_stack_envs/media.env` (`0600`, contém as chaves).
3. Portainer → **Stacks** → **Add Stack** → nome `media` → **Web editor** com `docker/stacks/media/docker-compose.yml` → em **Env**, carregue `/opt/portainer_stack_envs/media.env` → **Deploy the stack**.
4. Rode de novo o `setup-monitoring-stack-volumes.yml` ([seção 9](09-painel-notificacoes.md)): ele já traz as sondas e os alertas da mídia (`qbittorrent-ou-vpn-fora`, `servico-fora-do-ar`), mas o Prometheus e o Grafana só os carregam depois de reiniciados com a stack `media` no ar (`sudo docker restart prometheus grafana`). Na primeira instalação, a seção 9 vem antes desta; os alertas da mídia ficam em "sem dados" (`OK`) até aqui.

### Variáveis da stack

| Variável | Origem |
|---|---|
| `MEDIA_STACK_DATA_PATH` | NFS + `zfs_media_dataset_name` |
| `MEDIA_STACK_<APP>_CONFIG_PATH` (jellyfin, seerr, sonarr, radarr, lidarr, prowlarr, bazarr, gluetun, qbittorrent, recyclarr) | NFS + `zfs_docker_volumes_dataset_name` + `<app>/config` |
| `SONARR_API_KEY`, `RADARR_API_KEY`, `LIDARR_API_KEY`, `PROWLARR_API_KEY` | vault `arr_api_keys.*` (viram `<APP>__AUTH__APIKEY`) |
| `PROTONVPN_WIREGUARD_PRIVATE_KEY` | vault `protonvpn_wireguard_private_key` |

As *arr usam `<APP>__AUTH__METHOD=External`: a interface já está atrás do Authelia, então não pedem um segundo login; as chamadas entre containers usam a chave de API. Para mudar uma chave, edite o vault, rode o playbook de novo, recarregue o `media.env` em **Env** e clique em **Update the stack**.

## Primeira configuração

Estes passos ficam no banco de cada aplicação e são feitos na interface, uma vez.

!!! warning "Jellyfin e Seerr primeiro"
    Os dois são públicos desde o primeiro **Deploy the stack**: quem abrir `jellyfin.` ou `pedidos.` antes de você conclui o assistente inicial e vira administrador. Faça os passos 1 e 2 logo depois do deploy, antes de qualquer outro.

1. **Jellyfin** (`jellyfin.seudominio.com`): conclua o assistente criando o admin; bibliotecas em `/data/media/movies`, `/data/media/tv` e `/data/media/music`. Em *Dashboard → Networking*, ponha `traefik` em **Known proxies** (assim o Jellyfin lê o IP real que o Traefik repassa e sabe o que vem da internet) e ajuste **Login attempts before lockout**. Em *Dashboard → Users*, no admin, desmarque **Allow remote connections**; crie os usuários da família. Confira de fora de casa (dados móveis) que o admin não entra.
2. **Seerr** (`pedidos.seudominio.com`): conclua o assistente entrando com o Jellyfin (`http://jellyfin:8096`); Sonarr e Radarr com `http://sonarr:8989` e `http://radarr:7878` e as chaves de `arr_api_keys`.
3. **ProtonVPN:** em account.protonvpn.com → *Downloads* → *WireGuard configuration*, gere uma configuração com **NAT-PMP (Port Forwarding)** ligado, num servidor P2P. Copie o `PrivateKey` para o vault (`protonvpn_wireguard_private_key`) e rode o playbook. O encaminhamento de porta exige plano pago.
4. **qBittorrent** (`qbittorrent.seudominio.com`): troque a senha inicial (veja `docker logs qbittorrent`); em *Opções → Web UI* marque **Bypass authentication for clients on localhost** (o gluetun grava a porta encaminhada por essa API); em *Opções → Downloads*, **Default Torrent Management Mode = Automatic** e caminho padrão `/data/torrents`; categorias `movies`, `tv` e `music` em `/data/torrents/<categoria>`. Depois, aplique a porta: `docker restart gluetun` e em seguida `docker restart qbittorrent` (o qBittorrent perde a rede quando o gluetun reinicia); confira em *Opções → Conexão* a porta que aparece no log do gluetun (`docker logs gluetun | grep -i "port forwarded"`).
5. **Prowlarr:** *Settings → Indexers*: proxy FlareSolverr em `http://flaresolverr:8191` com a tag `flaresolverr` (use a tag nos indexadores atrás de Cloudflare); *Settings → Apps*: Sonarr, Radarr e Lidarr em `http://<app>:<porta>`, com Prowlarr Server `http://prowlarr:9696` e as chaves de `arr_api_keys`; depois, os indexadores.
6. **Sonarr, Radarr e Lidarr:** *Settings → Download Clients*: qBittorrent em host `gluetun`, porta `8088`, categoria `tv` / `movies` / `music`; *Media Management*: pastas raiz `/data/media/tv`, `/data/media/movies`, `/data/media/music` e **Use Hardlinks instead of Copy** ligado.
7. **Bazarr:** *Settings → Sonarr/Radarr* com `http://sonarr:8989` e `http://radarr:7878` e as chaves; idioma **Portuguese (Brazil)**; provedores de legenda.
8. **Homepage:** gere as chaves de API do Bazarr (*Settings → General*) e do Seerr (*Settings → General*) e grave-as em `homepage_widget_keys.bazarr` e `.seerr`; rode o `setup-monitoring-stack-volumes.yml` (ver [Painel e Notificações](09-painel-notificacoes.md)).

### Notificações (NTF-3)

Webhook para `http://n8n:5678/webhook/notificar`, com o cabeçalho `Authorization: Bearer <notificacoes_webhook_token>`:

- **Sonarr, Radarr e Lidarr:** *Settings → Connect → + → Webhook*, método `POST`; eventos como *On Import* e *On Health Issue*. O n8n reconhece o formato nativo (`eventType`).
- **Prowlarr:** o mesmo webhook, mas ele não importa nada: os eventos são *On Health Issue*, *On Application Update* e *On Grab*.
- **Seerr:** *Settings → Notifications → Webhook*, com o *JSON Payload* `{"titulo": "{{event}}", "mensagem": "{{subject}}", "gravidade": "info", "app": "seerr"}` e os eventos de pedido.
- **Jellyfin:** plugin **Webhook** (*Painel → Plugins → Catálogo*), *Generic Destination* para a mesma URL com o modelo `{"titulo": "{{NotificationType}}", "mensagem": "{{Name}}", "gravidade": "info", "app": "jellyfin"}`.

## Falhas

| Situação | Comportamento |
|---|---|
| VPN cai | O firewall do gluetun corta a saída do qBittorrent; o servidor de saúde do gluetun (`gluetun:9999`) passa a responder 500, a probe falha e o alerta `qbittorrent-ou-vpn-fora` avisa no Telegram; o gluetun reconecta sozinho. |
| gluetun reinicia | O qBittorrent fica sem rede até reiniciar também: `docker restart qbittorrent` (o compose já faz isso quando a stack é atualizada); a probe `gluetun:8088` falha enquanto isso. |
| Porta encaminhada muda | O gluetun roda `VPN_PORT_FORWARDING_UP_COMMAND` e grava a porta nova no qBittorrent. |
| Indexador atrás de Cloudflare | O Prowlarr passa pelo FlareSolverr (tag `flaresolverr`). |
| Recyclarr falha | O erro aparece no log (Grafana → Loki, `container_name="recyclarr"`); as *arr seguem com a configuração anterior. |

## Teste de ponta a ponta

1. IP de saída do qBittorrent é da Proton: `docker exec qbittorrent curl -s ifconfig.me` (compare com o IP de casa).
2. Kill switch: `docker stop gluetun` → `docker exec qbittorrent curl -s -m 5 ifconfig.me` falha; `docker start gluetun` e depois `docker restart qbittorrent`.
3. Porta encaminhada: a porta de *Opções → Conexão* do qBittorrent é a do log do gluetun (`port forwarded`).
4. Peça no Seerr um título de domínio público e acompanhe: Sonarr/Radarr → qBittorrent → importação.
5. Hardlink: `stat -c %h <arquivo em /data/media/...>` mostra `2` enquanto o torrent semeia.
6. A legenda pt-BR aparece ao lado do arquivo, e o título aparece no Jellyfin.

!!! tip "Plex em vez de Jellyfin"
    O compose inclui apenas o Jellyfin. Para trocar, use as skills `remove-app` (jellyfin) e `add-app` (plex), que ajustam compose, playbook de volumes, variáveis, catálogo e integrações juntos.
