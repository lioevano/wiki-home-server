# Design: VPN (Tailscale), DNS da VPN e firewall das portas publicadas pelo Docker

- **Data:** 2026-10-21
- **Autor:** Léo Ivan (com Claude)
- **Status:** decidido de forma autônoma, a pedido do Léo ("pode seguir da mesma forma autônoma com os demais pontos").
- **Caminho:** arquitetural: role novo, playbook novo, página nova (14) e regras de firewall nas duas VMs.
- **Origem:** próximos passos do `contexto-homeserver.md` e itens adiados das pendências menores:
  - porta 4100 (rota de controle do hub) em HTTP puro;
  - 9090 aceita séries de qualquer host da LAN;
  - limite de 100 MB do túnel da Cloudflare (vídeos do Immich, arquivos do Nextcloud);
  - Syncthing do celular só pelos relays.

## 1. Objetivo

- Acessar **todos** os serviços de fora de casa pela VPN, com os mesmos endereços `https://<app>.<domínio>`, sem passar pela Cloudflare e sem o limite de 100 MB.
- A rota de controle do hub (4100) **só** pela VPN, cifrada pelo WireGuard, também de dentro de casa.
- As portas publicadas pelo Docker na LAN aceitam só quem precisa. Hoje elas passam por fora do UFW.

### Critérios de pronto

- Role `infra/tailscale` e playbook `setup-vpn.yml` na `core-services-vm`, que vira *subnet router* das duas VMs. O DNS da VPN responde `*.<domínio>` com o IP do Traefik.
- Regras na cadeia `DOCKER-USER` das duas VMs, geradas de `firewall_docker_portas`, que voltam sozinhas depois de um boot ou de um restart do Docker.
- Página nova **14 · VPN (Tailscale)** com os passos no painel do Tailscale, nos aparelhos e o teste.
- As páginas 12 e 13 apontam para a VPN (Syncthing direto; rota de controle).
- `test`, `check`, `build` e `lint` passam.

## 2. Decisões

| # | Tema | Escolha | Por quê |
|---|---|---|---|
| T1 | VPN | **Tailscale** (WireGuard, plano gratuito) | Atravessa NAT sem abrir porta no roteador; clientes para Windows, Android e iOS; ACL e MagicDNS no painel. O Headscale (auto-hospedado) exigiria um servidor público. |
| T2 | Onde roda | Pacote oficial (apt) na **`core-services-vm`**, como *subnet router* | Na VM, porque o host Proxmox fica só com o hypervisor. Na core, porque é ela que recebe todo o tráfego (Traefik) e roda o hub. |
| T3 | Rotas anunciadas | Só `/32` das duas VMs (`tailscale_rotas`) | Rotas `/32` são mais específicas que a `/24` da LAN, então um PC em casa com o Tailscale ligado também fala com as VMs pela VPN (cifrado). O host Proxmox **não** entra: se a core cair, ele continua alcançável pela LAN, sem depender da VPN que roda nela. |
| T4 | DNS | **CoreDNS** 1.15.0 (container do role, no IP da core, porta 53) responde `*.<domínio>` → IP da core; nas outras zonas, recusa. No painel do Tailscale: nameserver = IP da core, **restrito ao domínio** (split DNS) | Os apps (Immich, Nextcloud, Open WebUI, Syncthing pela interface) usam os mesmos endereços dentro e fora de casa. O Traefik tem certificado válido, e os subdomínios da IA já chegam a ele pelo file provider. |
| T5 | Firewall das portas do Docker | Script `firewall-docker.sh` (role `infra/docker`) que monta a cadeia `HOMESERVER` dentro de `DOCKER-USER`. Para cada porta de `firewall_docker_portas[host]`, quem entra pela **interface da LAN** só passa se a origem estiver na lista; lista vazia = ninguém pela LAN. A unit `firewall-docker` roda depois do Docker e junto com cada restart dele (`PartOf`) | O UFW não vê o tráfego que o Docker publica. A `DOCKER-USER` é o lugar documentado pelo Docker para isso. Tráfego da VPN (`tailscale0`) e entre containers não passa por essas regras. |
| T6 | Portas restritas | **core:** 9090 (Prometheus remote write) e 3100 (Loki) só do host Proxmox e da `ai-desktop-vm`; 4100 (hub) ninguém pela LAN. **ai:** 9001 (Portainer Agent) e 3100 (Langfuse) só da core | São as portas sem autenticação própria, ou com um poder que a LAN não precisa ter. O LiteLLM (4000), a Open WebUI (3000) e o Syncthing (22000) continuam na LAN: são usados do PC e do celular em casa. |
| T7 | Autorização no Tailscale | Auth key de uso único no vault (`tailscale_auth_key`), só para o primeiro `tailscale up`. Depois: aprovar as rotas, desligar a expiração da chave do nó e criar a ACL, tudo no painel | O painel do Tailscale não é gerenciado pelo repositório: a ACL e as aprovações ficam documentadas como passos na página 14. |
| T8 | Firewall da VPN | UFW: `41641/udp` (conexão direta) e `route allow in on tailscale0 out on <LAN>` (o roteamento das rotas anunciadas) | Sem a rota, o `DEFAULT_FORWARD_POLICY=DROP` do UFW descarta o tráfego para a `ai-desktop-vm`. |

## 3. Efeitos nas outras páginas

- **13 (agentes):** o endereço da rota de controle não muda (`http://<IP da core>:4100/mcp`), mas só funciona com o Tailscale ligado, inclusive em casa. Sai o "HTTP puro (resolver com a VPN)".
- **12 (segundo cérebro):** com a VPN, o celular conecta direto em `tcp://<IP da ai>:22000`, sem relay.
- **11 (fotos e arquivos):** com a VPN, o app do Immich usa só `https://fotos.<domínio>`, sem o limite de 100 MB; a troca de URL pelo Wi-Fi vira opcional.
- **Catálogo:** aplicações `tailscale` (infra, `ansible:infra/tailscale`, interna) e `coredns` (infra, `ansible:infra/tailscale`, interna).

## 4. Riscos

- **VPN depende da core:** se a `core-services-vm` cair, a VPN cai junto. Em casa, desligue o Tailscale para alcançar o host Proxmox e a ai pela LAN. O host não está nas rotas justamente por isso.
- **4100 fechada na LAN:** um agente que rode **na LAN, fora da VPN**, perde a rota de controle. Os agentes da 4c3 rodam na `ai-desktop-vm`, que alcança a core pela LAN, então a lista do 4100 recebe o IP da ai quando a 4c3 chegar.

## 5. Correções da revisão final (2026-10-28)

- `--check` numa VM nova: a tarefa do `apt` do Tailscale fica fora do check mode (o repositório só foi simulado, e o `apt` não acharia o pacote).
- `sysctl`: `ansible.posix.sysctl` aplica o `ip_forward` na hora, antes do `tailscale up`; sem o forwarding do IPv6 (desligaria o `accept_ra` da LAN). O handler `Aplicar sysctl` saiu.
- `tailscale set` só roda (e mostra *changed*) quando o nome, as rotas ou o `accept-dns` diferem do `tailscale debug prefs`.
- CoreDNS: `template IN ANY` com `NOERROR` para os outros tipos (HTTPS/65, TXT, MX, SOA), que davam SERVFAIL.
- Firewall: a unit `firewall-docker` roda **antes** do Docker (`Before=`), criando a `DOCKER-USER` que o Docker reaproveita: sem janela aberta no boot.
- Textos que ainda diziam que as portas do Docker eram protegidas só pela LAN ou pelo segredo (páginas 04, 06, 07, 10 e 08) passaram a citar a cadeia `HOMESERVER` e a VPN.
