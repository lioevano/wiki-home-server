# Fluxo de Rede e Acesso Externo Seguro

Compreender como o tráfego de usuários externos alcança seus serviços auto-hospedados é fundamental. Esta arquitetura utiliza Cloudflare Tunnel, Traefik e Authelia para fornecer acesso seguro e simplificado.

## Diagrama de Fluxo de Rede

```mermaid
graph TD
    subgraph "Internet (Usuário Externo)"
        U[💻 Usuário Acessa app.seudominio.com]
    end

    subgraph "Cloudflare Network"
        DNS[🌐 Cloudflare DNS]
        EDGE[🛡️ Cloudflare Edge Network (Proxy/WAF/DDoS Protection)]
    end

    subgraph "Sua Rede Doméstica (Sem Portas Abertas no Roteador!)"
        Roteador[🚪 Roteador Doméstico]
        subgraph "Proxmox Host (IP: {{ proxmox_host_ip_var }})"
            VM_CS[🐧 VM: core-services-vm (IP: {{ core_services_vm_ip_var }})]
        end
    end

    subgraph "Dentro da VM core-services-vm (Rede Docker 'proxy')"
        CFT[☁️ Container: cloudflared (Cloudflare Tunnel)]
        TRFK[🚦 Container: Traefik (Reverse Proxy)]
        AUTH[🔐 Container: Authelia (Serviço de Autenticação)]
        APP_X[🐳 Container: Serviço X (e.g., Nextcloud)]
        APP_Y[🐳 Container: Serviço Y (e.g., Grafana)]
    end

    U -->|1. Requisição DNS| DNS
    DNS -->|2. Resolve para IP Cloudflare| EDGE
    EDGE -->|3. Tráfego via Túnel Seguro| CFT
    CFT -->|4. Encaminha para Traefik (http://traefik:80)| TRFK

    TRFK -->|5a. Se rota protegida, verifica com Authelia| AUTH
    AUTH -->|5b. Redireciona para Login ou Confirma Autenticação| TRFK

    TRFK -->|6. Roteia para Serviço Docker Apropriado| APP_X
    TRFK -->|6. Roteia para Serviço Docker Apropriado| APP_Y

    style Roteador fill:#f9f,stroke:#333,stroke-width:2px
    style CFT fill:#f80,stroke:#333,stroke-width:2px
```

## Explicação Detalhada do Fluxo

1.  **Requisição do Usuário e DNS Cloudflare:**
    *   O usuário digita `app.seudominio.com` no navegador.
    *   A requisição DNS é resolvida pelos nameservers da Cloudflare. Em vez de apontar para o seu IP doméstico, o registro CNAME (ou a configuração do Túnel) aponta para a rede da Cloudflare.

2.  **Cloudflare Edge Network:**
    *   A requisição do usuário chega à borda da rede global da Cloudflare.
    *   Aqui, seu tráfego se beneficia da proteção contra DDoS, WAF (Web Application Firewall, se configurado) e do cache da Cloudflare (se aplicável). Seu IP doméstico real permanece oculto.

3.  **Cloudflare Tunnel (`cloudflared`):**
    *   O container `cloudflared`, rodando na sua `core-services-vm`, estabelece uma **conexão de SAÍDA** persistente e segura com a rede da Cloudflare mais próxima.
    *   **Nenhuma porta precisa ser aberta no seu roteador doméstico.** Isso é uma grande vantagem de segurança.
    *   A Cloudflare Edge encaminha o tráfego destinado ao seu domínio (e subdomínios configurados no túnel) através desta conexão segura para o container `cloudflared`.

4.  **`cloudflared` para Traefik:**
    *   O container `cloudflared` recebe o tráfego e o encaminha para o Traefik.
    *   No nosso `docker-compose.yml` para `cloudflared`, o comando `tunnel ... --url http://traefik:80 ...` instrui o túnel a enviar todo o tráfego para o serviço Docker chamado `traefik` na porta `80` (dentro da rede Docker `proxy`).

5.  **Traefik (Reverse Proxy) e Authelia:**
    *   Traefik escuta nas portas `80` (HTTP) e `443` (HTTPS) na `core-services-vm`.
    *   **Redirecionamento HTTP para HTTPS:** Traefik está configurado para redirecionar automaticamente todo o tráfego HTTP para HTTPS.
    *   **Roteamento Baseado em Host:** Traefik inspeciona o cabeçalho `Host` da requisição (e.g., `app.seudominio.com`).
    *   **Middleware de Autenticação:**
        *   Se a rota do Traefik para `app.seudominio.com` estiver configurada com o middleware Authelia (`traefik.http.routers.app.middlewares: "authelia@docker"`), Traefik primeiro encaminha a requisição (ou informações sobre ela) para o container Authelia.
        *   Authelia verifica se o usuário possui uma sessão válida.
        *   Se não, Authelia instrui Traefik a redirecionar o usuário para o portal de login de Authelia (`auth.seudominio.com`).
        *   Após o login bem-sucedido (incluindo 2FA), Authelia cria uma sessão e informa ao Traefik que o usuário está autenticado.
    *   **Gerenciamento de SSL/TLS:** Traefik obtém e renova automaticamente certificados SSL/TLS de Let's Encrypt para todos os seus serviços. Ele usa o desafio `DNS-01` com a API da Cloudflare, o que significa que Traefik pode provar a propriedade do domínio criando temporariamente registros DNS via API. O `acme.json` armazena esses certificados.

6.  **Traefik para o Serviço Docker de Destino:**
    *   Uma vez que o tráfego é HTTPS e o usuário está autenticado (se necessário), Traefik usa as *labels* definidas no `docker-compose.yml` do serviço de destino (e.g., Nextcloud) para saber para qual container e porta interna encaminhar a requisição.
    *   Por exemplo, para o Nextcloud, a label `traefik.http.services.nextcloud-svc.loadbalancer.server.port: "80"` diz ao Traefik para enviar o tráfego para a porta 80 do container `nextcloud_app`.

!!! success "Principais Vantagens Deste Fluxo"
    *   **Segurança Aprimorada:** Nenhum IP doméstico exposto, nenhuma porta aberta no roteador, HTTPS em todos os lugares, 2FA centralizado.
    *   **Simplicidade:** Gerenciamento de certificados automatizado, configuração de proxy reverso centralizada no Traefik.
    *   **Flexibilidade:** Fácil adicionar novos serviços e protegê-los.