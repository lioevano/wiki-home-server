# Segurança Avançada para Homelab

A arquitetura base implementada já inclui várias camadas de segurança significativas (Cloudflare Tunnel, Traefik com HTTPS, Authelia 2FA, firewalls). No entanto, para aqueles que desejam ir além e fortalecer ainda mais a segurança do seu servidor doméstico, esta seção explora conceitos e ferramentas adicionais.

!!! warning "Complexidade e Recursos"
    Muitas dessas técnicas avançadas adicionam complexidade à sua configuração e podem consumir mais recursos do sistema (CPU, RAM). Avalie cuidadosamente a necessidade e o impacto antes de implementá-las.

## 1. Sistemas de Detecção/Prevenção de Intrusão (IDS/IPS)

IDS/IPS analisam o tráfego de rede em busca de atividades maliciosas conhecidas ou comportamentos suspeitos.

*   **IDS (Intrusion Detection System):** Detecta e alerta sobre possíveis ameaças.
*   **IPS (Intrusion Prevention System):** Detecta e tenta bloquear ativamente as ameaças.

### Ferramentas Populares:

*   **Suricata:** Um motor IDS/IPS de código aberto de alta performance. Pode operar em modo IDS (apenas logando/alertando) ou IPS (bloqueando ativamente, geralmente inline).
    *   **Como Funciona:** Analisa o tráfego de rede com base em um conjunto de regras (signatures) que definem padrões de ataque conhecidos. Também pode fazer análise de protocolo e detecção de anomalias.
    *   **Implementação em Homelab:**
        *   Pode rodar em uma VM dedicada (e.g., uma VM Linux leve) que monitora o tráfego de uma interface de rede espelhada (SPAN port no switch) ou atuando como um gateway transparente.
        *   Se você tem uma VM firewall (pfSense/OPNsense), Suricata pode ser instalado como um pacote nela.
        *   Requer conjuntos de regras atualizados (e.g., ET Open, Emerging Threats Pro).
*   **Snort:** Outro IDS/IPS popular e de código aberto, similar ao Suricata em funcionalidade.
*   **CrowdSec:**
    *   **Diferencial:** Um IDS/IPS colaborativo e moderno. Agentes (instalados nos seus servidores/VMs/containers) detectam comportamentos maliciosos (varreduras de portas, tentativas de brute-force, exploração de LFI/SQLi, etc.) com base em cenários.
    *   Os IPs maliciosos detectados são compartilhados com uma rede comunitária, e seu agente baixa uma "blocklist" de consenso de IPs ruins para bloquear proativamente.
    *   **Componentes:**
        *   **Agent:** Monitora logs de aplicações (Nginx, SSH, WordPress, etc.) ou tráfego de rede.
        *   **Bouncer:** Aplica as decisões de bloqueio (e.g., `iptables`, `nftables`, firewall Cloudflare, Traefik).
    *   **Implementação em Homelab:**
        *   O Agent pode rodar como um container Docker ou serviço nativo na `core-services-vm` ou em outras VMs.
        *   Existem Bouncers para Traefik (bloqueia no nível do proxy reverso), Cloudflare (adiciona IPs à blocklist da Cloudflare), e firewall Linux.
        *   [CrowdSec Docker Hub](https://hub.docker.com/r/crowdsec/crowdsec), [CrowdSec Traefik Bouncer](https://hub.docker.com/r/crowdsec/traefik-bouncer).
    *   **Vantagem:** Leve, fácil de integrar com Docker/Traefik, e se beneficia da inteligência da comunidade.

### Considerações para IDS/IPS:

*   **Recursos:** Podem consumir CPU e RAM significativos, especialmente com muitos pacotes/segundo ou conjuntos de regras grandes.
*   **Falsos Positivos:** Podem ocorrer. É necessário ajustar as regras e monitorar os alertas para evitar bloquear tráfego legítimo.
*   **Posicionamento na Rede:** Onde o IDS/IPS é colocado (e.g., na borda, monitorando tráfego interno) determina o que ele pode ver.

## 2. Hardening de Kernel e Sistema Operacional

Ir além das configurações padrão para fortalecer o kernel Linux e o sistema operacional das suas VMs.

*   **`sysctl` Tuning:**
    *   O arquivo `/etc/sysctl.conf` (ou arquivos em `/etc/sysctl.d/`) permite ajustar parâmetros do kernel em tempo de execução.
    *   **Exemplos de Configurações de Segurança:**
        *   Proteção contra SYN floods: `net.ipv4.tcp_syncookies = 1`
        *   Desabilitar redirecionamentos ICMP: `net.ipv4.conf.all.accept_redirects = 0`, `net.ipv6.conf.all.accept_redirects = 0`
        *   Restringir acesso ao dmesg para usuários não privilegiados: `kernel.dmesg_restrict = 1`
        *   Habilitar proteção contra IP spoofing: `net.ipv4.conf.all.rp_filter = 1`
    *   !!! warning "Cuidado com `sysctl`"
        Alterações incorretas em `sysctl` podem causar instabilidade ou perda de conectividade. Pesquise cada parâmetro antes de alterar.
*   **AppArmor / SELinux:**
    *   **AppArmor (Application Armor):** Um sistema de Mandatory Access Control (MAC) para Linux que restringe as capacidades de programas individuais com base em perfis de segurança. Ubuntu usa AppArmor por padrão para alguns serviços.
        *   Você pode criar ou customizar perfis AppArmor para seus containers Docker ou serviços críticos para limitar o que eles podem acessar no sistema, mesmo se forem comprometidos.
    *   **SELinux (Security-Enhanced Linux):** Outro sistema MAC, mais complexo e granular que AppArmor. Comum em distribuições baseadas em RHEL (Fedora, CentOS).
    *   **Considerações:** Ambos adicionam uma camada significativa de segurança, mas também uma curva de aprendizado e podem ser difíceis de depurar se um perfil estiver muito restritivo.
*   **chkrootkit / rkhunter:** Ferramentas para escanear o sistema em busca de rootkits e backdoors conhecidos. Podem ser rodadas periodicamente via cron.
*   **Minimizar Pacotes Instalados:** Em cada VM, instale apenas os pacotes estritamente necessários para sua função. Menos software significa menos superfície de ataque.

## 3. VPNs para Acesso à Rede Local (Alternativa/Complemento ao Cloudflare Tunnel)

Enquanto o Cloudflare Tunnel é ótimo para expor serviços específicos à internet, uma VPN (Virtual Private Network) permite que você se conecte de forma segura à sua rede local inteira como se estivesse em casa.

*   **Casos de Uso:**
    *   Acessar serviços na sua LAN que não estão (e não deveriam estar) expostos publicamente via Cloudflare Tunnel (e.g., a UI do Proxmox, SSH para seus servidores, compartilhamentos Samba).
    *   Navegar na internet usando o IP da sua casa quando estiver fora.
*   **Soluções Populares para Auto-Hospedagem:**
    *   **WireGuard:**
        *   VPN moderna, rápida, leve e considerada muito segura.
        *   Relativamente simples de configurar.
        *   Pode rodar como um container Docker (e.g., imagem `lscr.io/linuxserver/wireguard`) ou nativamente em uma VM Linux (ou até no host Proxmox, com cuidado).
        *   Requer que você abra **uma única porta UDP** no seu roteador doméstico para o servidor WireGuard.
    *   **OpenVPN:**
        *   Mais antigo e estabelecido, muito robusto e configurável.
        *   Pode ser mais complexo de configurar que WireGuard.
        *   Também pode rodar como container ou nativamente.
        *   Geralmente requer uma porta TCP ou UDP aberta no roteador.
*   **Implementação:**
    *   Instale o servidor VPN escolhido (e.g., WireGuard) em uma VM (pode ser a `core-services-vm` ou uma VM dedicada leve).
    *   Configure o encaminhamento de porta no seu roteador para a porta do servidor VPN.
    *   Gere configurações de cliente para seus dispositivos (laptop, celular).
    *   **DNS e Roteamento:** Considere como o DNS será resolvido quando conectado à VPN (e.g., usar seu Pi-hole local) e como o tráfego será roteado (full tunnel vs. split tunnel).
*   **Comparado ao Cloudflare Tunnel:**
    *   **VPN:** Dá acesso à rede inteira. Requer abertura de porta no roteador. O cliente VPN precisa estar instalado e conectado.
    *   **Cloudflare Tunnel:** Expõe serviços específicos via HTTPS. Nenhuma porta aberta. Mais simples para acesso a aplicações web.

## 4. Monitoramento de Logs de Segurança e SIEM Básico

Coletar e analisar logs de segurança de forma centralizada pode ajudar a detectar atividades suspeitas.

*   **Loki e Promtail (Já na nossa stack):**
    *   Promtail já está configurado para coletar logs do sistema (`/var/log/auth.log`, `syslog`) e logs de containers Docker.
    *   No Grafana, crie dashboards e alertas baseados em queries Loki para eventos de segurança:
        *   Tentativas de login SSH falhas.
        *   Erros de autenticação do Authelia.
        *   Alertas do UFW (se logados).
        *   Atividade suspeita nos logs de aplicações web.
*   **SIEM (Security Information and Event Management) - Avançado:**
    *   Para homelabs, um SIEM completo pode ser overkill, mas existem opções open-source mais leves:
        *   **Wazuh:** Uma plataforma de detecção de intrusão, monitoramento de integridade de arquivos, e análise de logs, com um agente para hosts e um servidor central. Pode ser complexo de configurar.
        *   **Elastic Stack (ELK/EFK - Elasticsearch, Logstash/Fluentd, Kibana):** Poderoso para agregação e visualização de logs, mas consome muitos recursos.
*   **Fail2Ban:**
    *   Um serviço que monitora arquivos de log (e.g., `/var/log/auth.log` para SSH, logs do Nginx/Apache) para tentativas de login falhas e atualiza dinamicamente as regras do firewall (iptables, nftables, firewalld) para bloquear os IPs ofensivos por um tempo.
    *   Pode ser instalado diretamente nas VMs (especialmente naquelas que expõem SSH ou outros serviços de login diretamente, o que não é o caso principal da nossa arquitetura Traefik/Authelia para web).

## 5. Políticas de Acesso Mais Granulares no Cloudflare Zero Trust

Além do Tunnel, a plataforma Cloudflare Zero Trust (gratuita para até 50 usuários) oferece mais funcionalidades:

*   **Access Policies:** Você pode criar políticas de acesso para seus "Applications" (que são os hostnames públicos do seu túnel) baseadas em:
    *   Identidade (requer login com provedores de identidade como Google, GitHub, Okta, ou email one-time-pin).
    *   Geolocalização do usuário.
    *   Endereço IP do usuário.
    *   Status do dispositivo (requer WARP client).
*   Isso adiciona outra camada de autenticação/autorização *antes* que o tráfego chegue ao Authelia/Traefik.
*   Pode ser útil para restringir o acesso a certos serviços apenas para você ou para usuários específicos, mesmo antes de eles verem o portal Authelia.

## 6. Auditoria Regular e Revisão de Configurações

*   Periodicamente (e.g., a cada 3-6 meses), revise:
    *   Suas regras de firewall (PVE, UFW).
    *   Configurações do Traefik e Authelia.
    *   Permissões de usuários e grupos no Proxmox e nas VMs.
    *   Logs de acesso e segurança.
    *   Contas de usuário ativas em seus serviços (Nextcloud, Grafana, etc.) e remova as que não são mais necessárias.
*   Mantenha-se atualizado sobre novas vulnerabilidades que possam afetar o software que você usa.

A segurança avançada é uma jornada, não um destino. Comece com o básico, entenda os riscos específicos do seu ambiente e adicione camadas de proteção gradualmente, conforme sua necessidade e capacidade de gerenciamento.