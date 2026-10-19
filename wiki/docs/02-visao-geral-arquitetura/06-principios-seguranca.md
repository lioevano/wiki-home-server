---
description: "Princípios de segurança aplicados: defesa em camadas, menor privilégio, 2FA, firewall e gestão de segredos."
---

# Princípios de Segurança Aplicados

A segurança é uma preocupação primordial em qualquer servidor, especialmente um que pode expor serviços à internet. Esta arquitetura foi projetada com vários princípios e camadas de segurança em mente.

## Defesa em Camadas (Defense in Depth)

A estratégia de segurança aqui não depende de uma única solução, mas de múltiplas camadas de proteção. Se uma camada falhar ou for contornada, outras ainda estarão em vigor.

```mermaid
graph TD
    subgraph Externa
        Internet[Internet]
    end

    subgraph Camada_Cloudflare [1. Perímetro Cloudflare]
        CF_Firewall[WAF/DDoS Protection]
        CF_Tunnel_Endpoint[Cloudflare Tunnel Endpoint]
    end

    subgraph Camada_Rede_Local_Segura [2. Rede Local Segura (Sem Portas Abertas)]
        Roteador[Roteador Doméstico (Firewall Ativo)]
        CFT_Agent[cloudflared Agent (Conexão de Saída)]
    end

    subgraph Camada_Proxy_Autenticacao [3. Proxy Reverso e Autenticação (core-services-vm)]
        Traefik[Traefik (HTTPS, Roteamento)]
        Authelia[Authelia (2FA)]
    end

    subgraph Camada_Host_Proxmox [4. Segurança do Hypervisor]
        PVE_Firewall[Proxmox VE Firewall]
        SSH_Hardening_Host[SSH Hardening (Host)]
        ZFS_Integrity[ZFS (Integridade de Dados)]
    end

    subgraph Camada_VM [5. Segurança das Máquinas Virtuais]
        UFW_VM[UFW Firewall (VMs)]
        Atualizacoes_VM[Atualizações SO VM]
        User_Isolation_VM[Isolamento de Usuários (VMs)]
    end

    subgraph Camada_Container_Aplicacao [6. Segurança de Containers e Aplicações]
        Docker_Isolation[Isolamento de Containers]
        MinPriv_Container[Princípio Menor Privilégio (PUID/PGID)]
        App_Passwords[Senhas Fortes de Aplicação]
        App_Updates[Atualizações de Imagens/Apps Docker]
    end

    Internet --> CF_Firewall
    CF_Firewall --> CF_Tunnel_Endpoint
    CF_Tunnel_Endpoint -.-> CFT_Agent
    CFT_Agent --> Traefik
    Traefik <--> Authelia
    Traefik --> Camada_Container_Aplicacao

    Proxmox --> PVE_Firewall
    Proxmox --> SSH_Hardening_Host
    Proxmox --> ZFS_Integrity
    Proxmox -- Hospeda --> Camada_VM

    Camada_VM -- Contém --> Camada_Proxy_Autenticacao
    Camada_VM -- Contém --> Camada_Container_Aplicacao
    Camada_VM --> UFW_VM
    Camada_VM --> Atualizacoes_VM
    Camada_VM --> User_Isolation_VM
```

1.  **Camada de Perímetro (Cloudflare):**
    *   **Ocultação de IP:** Seu IP doméstico não é exposto publicamente.
    *   **Proteção DDoS:** Cloudflare absorve ataques DDoS em sua borda.
    *   **Web Application Firewall (WAF):** Regras básicas do WAF da Cloudflare podem bloquear tráfego malicioso comum.
    *   **Cloudflare Tunnel:** Garante que apenas tráfego autenticado e roteado pela Cloudflare chegue à sua rede interna via uma conexão de saída segura. Nenhuma porta de entrada precisa ser aberta no seu roteador.

2.  **Camada de Proxy Reverso e Autenticação (na `core-services-vm`):**
    *   **Traefik:**
        *   Força **HTTPS** para todo o tráfego externo.
        *   Gerencia certificados SSL/TLS automaticamente via Let's Encrypt.
        *   Atua como um único ponto de entrada, dificultando o acesso direto aos containers de aplicação.
    *   **Authelia:**
        *   Fornece autenticação forte (usuário/senha + **2FA**) para todos os serviços configurados.
        *   Protege contra ataques de força bruta nas credenciais.
        *   Oferece um portal de login centralizado.

3.  **Camada de Segurança do Host Proxmox VE:**
    *   **Proxmox VE Firewall (PVE Firewall):** Configurado para `DROP` por padrão no tráfego de entrada, permitindo apenas SSH e a UI web do Proxmox a partir de CIDRs específicos da sua rede local.
    *   **SSH Hardening no Host Proxmox:**
        *   Login como `root` via SSH desabilitado (apenas `prohibit-password`).
        *   Autenticação por senha desabilitada (`PasswordAuthentication no`), forçando o uso de chaves SSH.
    *   **Atualizações Regulares do Host:** Manter o Proxmox VE e o Debian subjacente atualizados.

4.  **Camada de Segurança das Máquinas Virtuais (VMs):**
    *   **UFW (Uncomplicated Firewall):** Habilitado nas VMs (`core-services-vm` e `ai-desktop-vm` se tiver GUI) para controlar o tráfego de entrada para as próprias VMs, permitindo apenas as portas necessárias (e.g., 80/443 para Traefik, 22 para SSH, 12345 para o Alloy, só a partir da `core-services-vm`).
    *   **Portas na LAN sem autenticação:** Prometheus (9090, *remote write*), Loki (3100) e Alloy (12345, interface e `/metrics`) não têm login; ficam só na LAN, sem rota no Traefik nem no túnel. Portas publicadas pelo Docker não passam pelo UFW, então a proteção do 9090 e do 3100 é a própria LAN; o 12345 é limitado pelo UFW e pelo PVE Firewall à `core-services-vm`.
    *   **Portainer Agent (9001) na ai-desktop-vm:** publicado só no IP da LAN; como o UFW não filtra portas do Docker, o agente só aceita quem conhece o `AGENT_SECRET` (`portainer_agent_secret` do vault), e quem tem esse segredo controla o Docker da VM.
    *   **Jellyfin e Seerr públicos:** ficam na internet pelo túnel, sem Authelia, porque os apps de TV e celular do Jellyfin não sabem passar por ele. Proteções: bloqueio após tentativas de login erradas no Jellyfin, senhas fortes, admin sem acesso remoto e usuários sem permissão de administração. Atenção: as regras de uso da Cloudflare restringem servir vídeo em volume pelo túnel; se a conta for advertida, a alternativa é assistir fora de casa por uma VPN pessoal (ex.: Tailscale) e tirar o Jellyfin do túnel.
    *   **Immich, Nextcloud e Collabora públicos:** ficam na internet pelo túnel, sem o forward-auth do Authelia (os apps de celular e desktop não passam por ele), mas o login de cada um é o OIDC do próprio Authelia, com `two_factor`; o Immich não cria contas pelo OIDC (`autoRegister` desligado) e o login por senha é desligado depois do primeiro acesso. O Collabora só edita documentos deste Nextcloud (`aliasgroup1`) e cada documento exige um token WOPI. Ver [Fotos e Arquivos](../01-manual-implementacao/11-fotos-arquivos.md).
    *   **qBittorrent só pela VPN:** ele usa a rede do gluetun (ProtonVPN); se o túnel cair, o firewall do gluetun corta a saída e o IP de casa não aparece no enxame.
    *   **Alloy como root nas VMs:** necessário para o cAdvisor ler `/var/lib/docker` e para os logs dos containers; no host Proxmox ele roda como o usuário `alloy`.
    *   **Atualizações Automáticas (`unattended-upgrades`):** Configuradas nas VMs Ubuntu para aplicar patches de segurança automaticamente.
    *   **Isolamento:** As VMs são naturalmente isoladas umas das outras e do host pelo hypervisor.

5.  **Camada de Segurança de Containers e Aplicações:**
    *   **Isolamento de Containers Docker:** Docker fornece isolamento entre containers.
    *   **Princípio do Menor Privilégio para Containers:**
        *   Muitos containers (especialmente os da linuxserver.io) são configurados para rodar com um usuário não-root dentro do container, usando as variáveis de ambiente `PUID` (User ID) e `PGID` (Group ID).
        *   Esses `PUID`/`PGID` correspondem ao usuário `dockeruser` e grupo `dockergroup` criados nas VMs, que por sua vez são os "donos" dos arquivos nos volumes NFS devido às opções de `anonuid`/`anongid` no export NFS.
    *   **Senhas Fortes para Aplicações:** Usar senhas únicas e fortes para as contas de administrador de cada aplicação (Nextcloud, Grafana, etc.).
    *   **Atualizações de Imagens Docker:** O Diun avisa quando uma imagem tem versão nova, e a atualização é feita manualmente, depois de ler as notas de release, para manter as imagens nas versões mais recentes e seguras.
    *   **`security_opt: [no-new-privileges:true]`:** Usado em alguns `docker-compose.yml` para impedir que um container ganhe mais privilégios.

## Gerenciamento de Segredos

*   **Ansible Vault:** Todas as senhas, tokens de API e outros dados sensíveis usados pela automação Ansible são armazenados de forma criptografada no arquivo `ansible/inventories/home/group_vars/all/vault.yml`.
*   **Secrets das stacks:** Todo segredo de aplicação fica no `vault.yml` e é gravado pelo Ansible no `.env` da stack (`/opt/portainer_stack_envs/*.env`, `mode: '0600'`), que o Portainer carrega no deploy. Nada é digitado à mão na UI do Portainer (ver "Origem dos valores" no índice de integrações).

## Resiliência de Dados e Backups

Embora não seja estritamente um princípio de segurança *contra intrusão*, a capacidade de recuperar dados após uma falha (de hardware, software, ou mesmo um ataque de ransomware) é uma parte crucial da postura geral de segurança e disponibilidade.

*   **ZFS:** Oferece integridade de dados, snapshots e RAID para o pool `/data`.
*   **Estratégia de Backup 3-2-1:** Implementada para configurações do Proxmox, VMs e dados de aplicações (detalhada na [Seção de Manutenção e Recuperação](../04-manutencao-recuperacao/02-backup-restore-estrategia.md)).

A segurança é um processo contínuo, não um estado final. É importante manter-se informado sobre novas vulnerabilidades, revisar suas configurações periodicamente e adaptar suas defesas conforme necessário.