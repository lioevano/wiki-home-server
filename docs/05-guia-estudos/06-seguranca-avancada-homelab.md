# Segurança Avançada para Homelab: Indo Além do Básico

A arquitetura que implementamos neste guia já incorpora várias camadas de segurança significativas:
*   **Cloudflare Tunnel:** Oculta seu IP público e elimina a necessidade de abrir portas no roteador para serviços web.
*   **Traefik Proxy:** Força HTTPS, gerencia certificados SSL/TLS e atua como um ponto de entrada único.
*   **Authelia:** Fornece autenticação forte de dois fatores (2FA) e controle de acesso centralizado.
*   **Firewalls:** Proxmox VE Firewall (PVE Firewall) no host e UFW (Uncomplicated Firewall) nas máquinas virtuais.
*   **Princípios de IaC e Menor Privilégio:** Com Ansible e configuração de usuários/permissões.

No entanto, para aqueles que desejam ir além e fortalecer ainda mais a postura de segurança do seu servidor doméstico, esta seção explora conceitos, ferramentas e técnicas de segurança avançada.

!!! warning "Complexidade, Recursos e Falsos Positivos"
    Muitas dessas técnicas avançadas adicionam uma **camada significativa de complexidade** à sua configuração e podem **consumir mais recursos do sistema** (CPU, RAM, disco). Além disso, algumas ferramentas de detecção podem gerar **falsos positivos** que exigem análise e ajuste fino. Avalie cuidadosamente a real necessidade, o impacto no seu ambiente e sua disposição para gerenciar essa complexidade adicional antes de implementar estas soluções. Para a maioria dos homelabs, a segurança base já é bastante robusta.

## 1. Sistemas de Detecção/Prevenção de Intrusão (IDS/IPS)

Sistemas IDS/IPS analisam o tráfego de rede (ou logs de host) em busca de atividades maliciosas conhecidas, explorações de vulnerabilidades ou comportamentos anômalos.

*   **IDS (Intrusion Detection System):** **Detecta** e **alerta** sobre possíveis ameaças, mas não as bloqueia ativamente.
*   **IPS (Intrusion Prevention System):** **Detecta** e tenta **bloquear ativamente** as ameaças identificadas, geralmente operando inline com o tráfego de rede.

### Ferramentas Populares e Implementação em Homelab:

*   **Suricata:**
    *   **O quê:** Um motor IDS/IPS de código aberto de alta performance, maduro e rico em funcionalidades.
    *   **Como Funciona:** Analisa o tráfego de rede com base em um conjunto de **regras (signatures)** que definem padrões de ataque conhecidos (e.g., explorações, malware C2). Também pode realizar análise de protocolo e detecção de anomalias.
    *   **Implementação em Homelab:**
        *   **VM Dedicada ou Appliance Firewall:** A forma mais comum é rodar Suricata em uma VM Linux dedicada que monitora o tráfego de uma interface de rede espelhada (SPAN port) do seu switch principal, ou em uma VM que atua como um gateway/firewall transparente.
        *   **Integração com pfSense/OPNsense:** Se você usa [pfSense ou OPNsense como seu firewall principal](../03-guias-sustentacao/07-cenarios-especificos-criacao-vms.md#1-vm-para-firewallroteador-eg-pfsense-opnsense), ambos oferecem pacotes para instalar e gerenciar Suricata (ou Snort) diretamente na interface do firewall. Esta é uma forma muito conveniente de implementá-lo.
        *   **Modo de Operação:** Pode operar em modo IDS (apenas logando/alertando para o SIEM ou console) ou IPS (configurado para dropar pacotes maliciosos, requer posicionamento inline).
        *   **Conjuntos de Regras:** Requer conjuntos de regras atualizados, como as gratuitas **ET Open (Emerging Threats Open)** ou as pagas **ET Pro** ou **Snort Talos**.
    *   **Desafios:** Consumo de CPU/RAM pode ser significativo, especialmente com muitos pacotes por segundo ou conjuntos de regras muito grandes. Gerenciamento de regras e falsos positivos requer atenção.

*   **Snort:**
    *   **O quê:** Outro IDS/IPS open-source popular e muito estabelecido, com funcionalidades similares ao Suricata.
    *   **Diferenças:** A escolha entre Suricata e Snort muitas vezes se resume a preferência pessoal, familiaridade, ou pequenas diferenças em performance para tipos específicos de tráfego ou regras. Ambos são capazes.

*   **CrowdSec:**
    *   **O quê:** Um IDS/IPS moderno, colaborativo, leve e baseado em comportamento.
    *   **Diferencial:** Em vez de depender apenas de assinaturas estáticas, CrowdSec usa **cenários (definidos em YAML)** para detectar comportamentos maliciosos (varreduras de portas, tentativas de login brute-force, exploração de LFI/SQLi, acesso a bad user-agents, etc.) analisando logs de diversas fontes (servidores web, SSH, firewalls, aplicações).
    *   **Inteligência de Ameaças Comunitária:** Os IPs maliciosos detectados pelos agentes CrowdSec são (opcionalmente e de forma anonimizada) compartilhados com uma "Blocklist de Consenso" central. Seu agente baixa esta blocklist comunitária para bloquear proativamente IPs já identificados como ruins por outros usuários.
    *   **Componentes:**
        *   **CrowdSec Agent:** Roda nos seus servidores/VMs/containers, monitora logs ou tráfego de rede (com Pcap), e aplica cenários para detectar comportamentos.
        *   **Bouncer:** Componentes que aplicam as decisões de bloqueio (bans) tomadas pelo Agent. Existem bouncers para:
            *   Firewalls Linux (`iptables`, `nftables`).
            *   Firewall da Cloudflare (adiciona IPs à blocklist da Cloudflare).
            *   **Traefik Proxy** (um bouncer que se integra com Traefik para bloquear requisições no nível do proxy reverso).
            *   Nginx, Apache, etc.
    *   **Implementação em Homelab (com Traefik):**
        1.  **CrowdSec Agent:** Pode rodar como um container Docker na `core-services-vm`. Configure-o para ler os logs do Traefik, logs do Authelia, logs de SSH da VM, etc.
            ```yaml
            # Exemplo de parte de um docker-compose.yml para CrowdSec Agent
            # services:
            #   crowdsec:
            #     image: crowdsec/crowdsec:latest
            #     container_name: crowdsec_agent
            #     restart: unless-stopped
            #     volumes:
            #       - ./crowdsec_configs/acquis.yaml:/etc/crowdsec/acquis.yaml:ro # Para configurar fontes de log
            #       - ./crowdsec_configs/crowdsec.yaml:/etc/crowdsec/config.yaml:ro
            #       - ./crowdsec_data:/var/lib/crowdsec/data/
            #       - /var/log/traefik/:/var/log/traefik_mounted/:ro # Log de acesso do Traefik
            #       - /var/log/auth.log:/var/log/auth_mounted.log:ro # Log SSH da VM
            #     environment:
            #       GID: $(shell getent group docker | cut -d: -f3) # Para ler logs do Docker se necessário
            ```
        2.  **CrowdSec Traefik Bouncer:** Roda como outro container Docker, também na `core-services-vm`, conectado à mesma rede Docker que o Traefik. Ele se registra na API LAPI do CrowdSec Agent para receber decisões de ban e as implementa dinamicamente no Traefik (geralmente usando o File Provider do Traefik para adicionar IPs a um IPBlockList middleware).
            [Veja o Hub Docker do CrowdSec Traefik Bouncer](https://hub.docker.com/r/crowdsec/traefik-bouncer) para instruções.
    *   **Vantagens do CrowdSec:** Relativamente leve, fácil de integrar com Docker e Traefik, e se beneficia da inteligência de ameaças da comunidade para bloqueio proativo.

## 2. Hardening Adicional do Kernel e Sistema Operacional (VMs e Host)

Ir além das configurações padrão para fortalecer o kernel Linux e o sistema operacional das suas VMs (e do host Proxmox).

*   **Configurações `sysctl` para Segurança:**
    *   O arquivo `/etc/sysctl.conf` (ou arquivos em `/etc/sysctl.d/`) permite ajustar parâmetros do kernel Linux em tempo de execução para melhorar a segurança e a resiliência da pilha de rede.
    *   **Exemplos de Configurações de Segurança Comuns (aplique com cautela e teste):**
        *   Proteção contra SYN floods: `net.ipv4.tcp_syncookies = 1`
        *   Desabilitar aceitação de redirecionamentos ICMP (pode ser usado em ataques de MitM):
            `net.ipv4.conf.all.accept_redirects = 0`
            `net.ipv4.conf.default.accept_redirects = 0`
            `net.ipv6.conf.all.accept_redirects = 0`
            `net.ipv6.conf.default.accept_redirects = 0`
        *   Desabilitar source routing (geralmente não necessário e um risco):
            `net.ipv4.conf.all.accept_source_route = 0`
            `net.ipv6.conf.all.accept_source_route = 0`
        *   Restringir acesso ao buffer de mensagens do kernel (`dmesg`) para usuários não privilegiados:
            `kernel.dmesg_restrict = 1`
        *   Habilitar proteção contra IP spoofing (Reverse Path Filtering):
            `net.ipv4.conf.all.rp_filter = 1`
            `net.ipv4.conf.default.rp_filter = 1`
        *   Ignorar todos os pings ICMP (pode dificultar troubleshooting, mas aumenta o "stealth"):
            `net.ipv4.icmp_echo_ignore_all = 1`
    *   !!! warning "Cuidado com Modificações em `sysctl`"
        Alterações incorretas em `sysctl.conf` podem causar instabilidade no sistema, perda de conectividade de rede ou quebrar funcionalidades esperadas. **Pesquise cada parâmetro cuidadosamente** antes de alterá-lo e aplique as mudanças de forma incremental, testando após cada uma. Use o Ansible para gerenciar essas configurações de forma consistente.
*   **AppArmor / SELinux (Mandatory Access Control - MAC):**
    *   **AppArmor (Application Armor):** Usado por padrão no Ubuntu. É um sistema MAC que restringe as capacidades de programas individuais com base em **perfis de segurança** definidos em arquivos. Se um programa for comprometido, o AppArmor pode limitar o dano que ele pode causar, mesmo que ele esteja rodando como root (dentro do seu namespace).
        *   Muitos serviços (como o Docker daemon, alguns pacotes do sistema) já vêm com perfis AppArmor.
        *   Você pode criar ou customizar perfis AppArmor para seus containers Docker ou serviços críticos para limitar estritamente o que eles podem acessar no sistema de arquivos, na rede, e quais capabilities do kernel eles podem usar.
        *   **Ferramentas:** `aa-complain`, `aa-enforce`, `aa-genprof`, `aa-logprof`.
    *   **SELinux (Security-Enhanced Linux):** Outro sistema MAC, geralmente considerado mais granular e complexo que AppArmor. É o padrão em distribuições baseadas em RHEL (Fedora, CentOS, AlmaLinux, Rocky Linux).
    *   **Considerações:** Ambos AppArmor e SELinux adicionam uma camada de segurança muito forte, mas também uma **curva de aprendizado significativa** e podem ser difíceis de depurar se um perfil estiver muito restritivo e quebrar uma aplicação. Para a maioria dos homelabs, garantir que os perfis AppArmor padrão estejam ativos e talvez criar perfis para containers muito expostos pode ser um bom começo.
*   **Ferramentas de Detecção de Rootkits (`chkrootkit`, `rkhunter`):**
    *   São ferramentas que escaneiam seu sistema em busca de rootkits, backdoors e outras ameaças de malware conhecidas.
    *   Podem ser instaladas (`sudo apt install chkrootkit rkhunter`) e rodadas periodicamente via `cron`, com os relatórios enviados por email.
    *   Lembre-se de atualizar as bases de dados dessas ferramentas (`sudo rkhunter --update`).
*   **Minimizar a Superfície de Ataque:**
    *   Em cada VM (e no host Proxmox), instale **apenas os pacotes e serviços estritamente necessários** para sua função. Menos software instalado significa menos potenciais vulnerabilidades e uma superfície de ataque menor.
    *   Desabilite ou desinstale quaisquer serviços desnecessários.

## 3. VPNs para Acesso Seguro à Rede Local (Alternativa/Complemento ao Cloudflare Tunnel)

Enquanto o Cloudflare Tunnel é excelente para expor serviços web específicos à internet de forma segura, uma **VPN (Virtual Private Network)** auto-hospedada permite que você se conecte de forma segura à sua **rede local inteira** como se estivesse fisicamente em casa.

Esta é uma alternativa ou um complemento, não um substituto direto para o Tunnel, dependendo do seu caso de uso.

*   **Casos de Uso para uma VPN Auto-Hospedada:**
    *   Acessar serviços na sua LAN que **não estão (e não deveriam estar)** expostos publicamente via Cloudflare Tunnel (e.g., a interface web do Proxmox VE, SSH para seus servidores e VMs, compartilhamentos de arquivos Samba/NFS internos, interfaces de impressoras de rede).
    *   Navegar na internet usando o endereço IP da sua casa quando você estiver viajando ou em uma rede Wi-Fi pública não confiável (roteando todo o seu tráfego pela VPN).
    *   Criar uma conexão segura site-to-site entre sua casa e outro local (e.g., casa de um amigo/familiar).
*   **Soluções Populares para Auto-Hospedar uma VPN:**
    *   **WireGuard:**
        *   **O quê:** Um protocolo VPN moderno, extremamente rápido, leve, com criptografia de ponta (ChaCha20, Poly1305) e uma base de código pequena, o que facilita a auditoria.
        *   **Configuração:** Considerado significativamente mais simples de configurar do que OpenVPN. Usa criptografia baseada em chaves públicas/privadas (similar ao SSH).
        *   **Implementação:** Pode rodar como um container Docker (e.g., imagem `lscr.io/linuxserver/wireguard`) ou nativamente em uma VM Linux (ou até mesmo no host Proxmox, embora rodar em uma VM ou container seja geralmente preferível para isolamento).
        *   **Port Forwarding Necessário:** Requer que você abra **uma única porta UDP** (você escolhe a porta, e.g., 51820) no seu roteador doméstico e a encaminhe para o IP e porta do seu servidor WireGuard.
    *   **OpenVPN:**
        *   **O quê:** Uma solução VPN muito madura, robusta, flexível e estabelecida.
        *   **Configuração:** Pode ser mais complexo de configurar do que WireGuard, especialmente a infraestrutura de PKI (Public Key Infrastructure) para certificados.
        *   **Implementação:** Também pode rodar como container ou nativamente.
        *   **Port Forwarding Necessário:** Geralmente requer uma porta TCP ou UDP (você escolhe, e.g., 1194/udp) aberta no roteador.
*   **Considerações Adicionais para VPN Auto-Hospedada:**
    *   **Segurança do Servidor VPN:** O servidor VPN em si se torna um ponto de entrada para sua rede. Mantenha o software do servidor VPN sempre atualizado e use senhas/chaves fortes.
    *   **DNS Dinâmico (DDNS):** Se o endereço IP público da sua casa for dinâmico (a maioria dos ISPs residenciais o são), você precisará de um serviço de DDNS (e.g., DuckDNS, No-IP, ou o DDNS da Cloudflare se seu roteador ou um script o suportar) para que seus clientes VPN possam sempre encontrar seu servidor VPN usando um hostname fixo.
    *   **DNS e Roteamento na VPN:** Considere como o DNS será resolvido para os clientes conectados à VPN (e.g., eles devem usar seu Pi-hole local?) e como o tráfego será roteado (full tunnel - todo o tráfego do cliente passa pela VPN, ou split tunnel - apenas o tráfego destinado à sua LAN passa pela VPN).

## 4. Monitoramento de Logs de Segurança e Alertas (SIEM Básico)

Coletar, centralizar e analisar logs de segurança de forma eficaz pode ajudar a detectar atividades suspeitas, tentativas de intrusão e a responder a incidentes.

*   **Loki e Promtail (Já em Nossa Stack de Monitoramento):**
    *   **Promtail** já está configurado para coletar logs do systemd journal da `core-services-vm` (que inclui logs de `auth.log` para SSH, `sudo`, etc.) e logs de todos os containers Docker rodando naquela VM.
    *   **Loki** armazena esses logs.
    *   **Grafana:** Use o datasource Loki no Grafana para:
        *   **Criar Dashboards de Segurança:** Visualize tentativas de login SSH falhas, erros de autenticação do Authelia, alertas do UFW (se o UFW estiver configurado para logar), atividades suspeitas nos logs de acesso do Traefik ou de aplicações web específicas.
        *   **Configurar Alertas no Grafana:** Crie regras de alerta no Grafana baseadas em queries Loki para eventos de segurança específicos (e.g., múltiplas falhas de login SSH de um mesmo IP, erros críticos em logs de aplicação).
*   **Fail2Ban:**
    *   **O quê:** Um serviço de prevenção de intrusão que monitora arquivos de log em tempo real (e.g., `/var/log/auth.log` para tentativas de SSH falhas, logs do Nginx/Apache/Traefik para abuso web) para padrões de ataque como tentativas de login brute-force.
    *   **Como Funciona:** Se Fail2Ban detecta um número excessivo de tentativas falhas de um mesmo endereço IP, ele atualiza dinamicamente as regras do firewall do sistema (iptables, nftables, firewalld) para bloquear (banir) aquele IP por um período configurável.
    *   **Implementação:** Pode ser instalado diretamente nas VMs (especialmente na `core-services-vm` para proteger SSH, e potencialmente configurado para ler logs do Traefik/Authelia se eles logarem falhas de forma que Fail2Ban possa parsear).
        ```bash
        # Na VM
        sudo apt install fail2ban
        # A configuração é feita em /etc/fail2ban/jail.local (copie de jail.conf)
        # Defina 'jails' para diferentes serviços.
        sudo systemctl enable fail2ban --now
        ```
*   **SIEM (Security Information and Event Management) - Mais Avançado:**
    *   Para homelabs, um SIEM completo (como Splunk, QRadar) é geralmente um exagero em termos de custo, recursos e complexidade.
    *   No entanto, existem opções open-source mais leves que podem ser exploradas se você tiver um interesse particular em análise de segurança profunda:
        *   **Wazuh:** Uma plataforma de detecção de segurança open-source que combina HIDS (Host-based Intrusion Detection System), monitoramento de integridade de arquivos (FIM), análise de logs, detecção de vulnerabilidades e resposta a incidentes. Consiste em agentes Wazuh (instalados nos hosts/VMs) e um servidor Wazuh central (que pode rodar como containers Docker). É muito poderoso, mas tem uma curva de aprendizado.
        *   **Elastic Stack (ELK/EFK):** Embora pesado em recursos (especialmente Elasticsearch), pode ser usado para agregação e análise profunda de logs de segurança se você já o utiliza para outros fins.

## 5. Políticas de Acesso Mais Granulares na Plataforma Cloudflare Zero Trust

Além do Cloudflare Tunnel em si, a plataforma **Cloudflare Zero Trust** (que tem um nível gratuito generoso, geralmente suficiente para até 50 usuários) oferece funcionalidades para criar políticas de acesso mais granulares *antes* que o tráfego chegue ao seu túnel.

*   **Cloudflare Access Applications:**
    *   Você pode definir seus "Public Hostnames" do túnel como "Applications" na seção Access do dashboard Zero Trust.
    *   Para cada aplicação, você pode criar **políticas de acesso** que determinam quem pode alcançá-la.
*   **Critérios de Política de Acesso:**
    *   **Identidade:** Requer que o usuário se autentique com um Provedor de Identidade (IdP) configurado na Cloudflare.
        *   Pode ser um IdP social (Google, GitHub).
        *   Pode ser um IdP corporativo (Okta, Azure AD).
        *   Pode ser um "Email one-time-pin" (OTP) enviado para o email do usuário.
    *   **Geolocalização:** Permitir/bloquear acesso de certos países.
    *   **Endereço IP de Origem:** Permitir/bloquear IPs específicos ou ASN.
    *   **Status do Dispositivo (requer cliente Cloudflare WARP):** Verificar se o dispositivo do usuário atende a certos critérios de segurança.
*   **Caso de Uso:**
    *   Você pode usar isso para adicionar uma camada de autenticação *antes* do Authelia. Por exemplo, exigir que um usuário se autentique com sua conta Google antes mesmo de ver o portal de login do Authelia para um serviço mais sensível.
    *   Restringir o acesso a certos serviços apenas para você ou para um grupo pequeno de usuários, bloqueando todo o resto no nível da Cloudflare.
    *   Pode ser um pouco redundante se você já tem Authelia, mas oferece uma camada de defesa adicional no perímetro da Cloudflare.

## 6. Auditoria Regular de Configurações e Permissões

A segurança não é um estado "configure e esqueça". É um processo contínuo.

*   **Agende Revisões Periódicas (e.g., a cada 3-6 meses, ou após qualquer mudança significativa):**
    *   **Regras de Firewall:** Revise suas regras no PVE Firewall e no UFW das VMs. Elas ainda são necessárias e estão o mais restritivas possível?
    *   **Configurações Traefik e Authelia:** Revise seus roteadores, middlewares e políticas de acesso. Há algo exposto que não deveria estar? As políticas do Authelia ainda são adequadas?
    *   **Permissões de Usuários e Grupos:**
        *   No host Proxmox e nas VMs: Quem tem acesso `sudo`? As contas de usuário ainda são necessárias?
        *   Nos seus serviços auto-hospedados (Nextcloud, Grafana, Portainer, etc.): Revise as contas de usuário ativas, seus níveis de permissão e remova contas que não são mais necessárias ou que pertenciam a usuários que não deveriam mais ter acesso.
    *   **Logs de Acesso e Segurança:** Dedique um tempo para revisar os logs coletados (via Loki/Grafana ou diretamente) em busca de padrões ou anomalias.
    *   **Exposição de Serviços:** Use ferramentas online de varredura de portas (com cautela, e apenas contra seus próprios domínios/IPs se não estiver usando túnel) ou ferramentas como `nmap` de uma máquina externa (e.g., uma VPS) para verificar o que está realmente exposto da sua rede para a internet. Com o Cloudflare Tunnel, isso deve ser limitado aos seus hostnames configurados.
*   **Mantenha-se Informado sobre Novas Vulnerabilidades:**
    *   Siga blogs de segurança, listas de discussão, ou feeds de notícias sobre vulnerabilidades que possam afetar o software que você usa (Debian, Ubuntu, Proxmox, Docker, e todas as suas aplicações containerizadas).
    *   Aplique patches e atualizações prontamente, conforme discutido na seção de [Rotinas de Manutenção](01-rotinas-manutencao.md).

Implementar todas essas medidas de segurança avançada pode ser um grande esforço. Comece com o básico (que já é bastante robusto em nossa arquitetura), entenda os riscos específicos do seu ambiente e do seu perfil de uso, e adicione camadas de proteção gradualmente, conforme sua necessidade, seu tempo disponível para gerenciamento e seu nível de conforto com a complexidade. Lembre-se que a segurança perfeita é um mito; o objetivo é tornar o "custo" para um invasor maior do que o "benefício" de comprometer seu sistema.