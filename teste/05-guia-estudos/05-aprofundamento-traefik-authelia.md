# Aprofundamento em Traefik e Authelia

Traefik e Authelia são os pilares da nossa estratégia de acesso externo seguro e gerenciamento de autenticação. O manual de implementação cobriu suas configurações básicas. Esta seção explora funcionalidades mais avançadas e opções de personalização para ambos.

## 1. Traefik: Middlewares Avançados e Personalização

Traefik utiliza um sistema poderoso de middlewares para processar requisições HTTP antes que elas cheguem aos seus serviços backend (containers).

### Cadeias de Middlewares (Chaining)

Você pode aplicar múltiplos middlewares a um roteador em uma ordem específica. Os middlewares são definidos (seja via labels Docker, File Provider, ou na configuração estática) e depois referenciados.

*   **Definição (Exemplo em `docker-compose.yml` para labels):**
    ```yaml
    services:
      meuservico:
        labels:
          # ... outras labels Traefik ...
          # Define um middleware para adicionar um header customizado
          traefik.http.middlewares.meu-header-custom.headers.customrequestheaders.X-Meu-Header: "ValorCustom"
          # Define um middleware para limitar a taxa de requisições
          traefik.http.middlewares.meu-ratelimit.ratelimit.average: "100" # Requisições por segundo
          traefik.http.middlewares.meu-ratelimit.ratelimit.burst: "50"

          # Aplica uma cadeia de middlewares ao roteador
          # A ordem importa: Authelia -> securityHeaders -> meu-header-custom -> meu-ratelimit
          traefik.http.routers.meuservico.middlewares: "authelia@docker,securityHeaders@file,meu-header-custom@docker,meu-ratelimit@docker"
    ```
    *   `@docker`: Indica que o middleware é definido via labels Docker nesta mesma stack/serviço.
    *   `@file`: Indica que o middleware é definido em um arquivo de configuração dinâmica (e.g., `security_headers.yml`).
    *   `@internal`: Para middlewares internos do Traefik.

### Tipos Comuns de Middlewares Traefik (Além dos já usados)

*   **`RateLimit`:** Limita o número de requisições de um cliente em um determinado período. Útil para prevenir abuso.
    *   Exemplo: `traefik.http.middlewares.meu-ratelimit.ratelimit.average: "10"` (10 reqs/s), `traefik.http.middlewares.meu-ratelimit.ratelimit.period: "1m"` (período de 1 minuto).
*   **`Retry`:** Tenta reenviar uma requisição para o backend se uma tentativa inicial falhar (e.g., erro de rede ou 5xx).
    *   Exemplo: `traefik.http.middlewares.meu-retry.retry.attempts: "3"`
*   **`Buffering`:** Bufferiza a requisição e a resposta. Pode ser útil para backends lentos ou para garantir que a requisição inteira seja recebida antes de ser processada.
*   **`Compress`:** Habilita compressão Gzip ou Brotli para as respostas, se o cliente suportar.
    *   Exemplo: `traefik.http.middlewares.meu-compress.compress: "true"`
*   **`IPWhiteList` / `IPAllowList`:** Permite acesso a um roteador apenas de IPs ou faixas de IP específicas.
    *   Exemplo: `traefik.http.middlewares.meu-ipallow.ipallowlist.sourcerange: "192.168.1.0/24, 203.0.113.5"`
*   **`InFlightReq`:** Limita o número de requisições simultâneas para um backend. Pode ajudar a prevenir sobrecarga.
*   **`ErrorPages`:** Permite definir páginas de erro customizadas para códigos de status HTTP específicos (e.g., 404, 500).
    *   Exemplo: `traefik.http.middlewares.meu-errors.errors.status: "404,500-599"`, `traefik.http.middlewares.meu-errors.errors.service: "meu-servico-de-erro@file"`, `traefik.http.middlewares.meu-errors.errors.query: "/{status}.html"`
*   **`StripPrefix` / `ReplacePathRegex`:** Modifica o caminho da URL antes de encaminhar para o backend.

!!! tip "Documentação de Middlewares Traefik"
    Consulte a [documentação oficial do Traefik sobre middlewares HTTP](https://doc.traefik.io/traefik/middlewares/http/overview/) para a lista completa e opções de configuração.

### Roteamento TCP e UDP com Traefik

Embora nosso foco tenha sido em HTTP/HTTPS, Traefik também pode atuar como proxy para tráfego TCP e UDP.

*   **Caso de Uso:** Expor serviços que não usam HTTP (e.g., um servidor de jogos, um broker MQTT, um servidor OpenVPN que escuta em UDP).
*   **Configuração:**
    1.  **Entrypoints TCP/UDP:** Defina entrypoints TCP/UDP na configuração estática do Traefik (`traefik.yml`).
        ```yaml
        # Exemplo em traefik.yml
        entryPoints:
          # ... (web, websecure já definidos) ...
          meu-servico-tcp:
            address: ":12345/tcp" # Escuta na porta 12345 TCP
          meu-servico-udp:
            address: ":12345/udp" # Escuta na porta 12345 UDP
        ```
    2.  **Mapeamento de Portas no Container Traefik:** O container Traefik precisa ter essas portas mapeadas do host da VM para o container.
        ```yaml
        # Exemplo no docker-compose.yml do Traefik
        ports:
          # ...
          - "${CORE_SERVICES_VM_IP_VAR}:12345:12345/tcp"
          - "${CORE_SERVICES_VM_IP_VAR}:12345:12345/udp"
        ```
    3.  **Roteadores TCP/UDP:** Defina roteadores TCP ou UDP (geralmente via labels Docker ou File Provider) para direcionar o tráfego desses entrypoints para os serviços backend.
        *   A regra de roteamento para TCP/UDP é frequentemente baseada em `HostSNI(`*`)` (para tráfego TLS) ou apenas no entrypoint.
        ```yaml
        # Exemplo de labels Docker para um serviço TCP
        labels:
          traefik.enable: "true"
          traefik.tcp.routers.meu-servico-tcp-router.entrypoints: "meu-servico-tcp"
          traefik.tcp.routers.meu-servico-tcp-router.rule: "HostSNI(`*`)" # Aceita qualquer SNI ou nenhum se não for TLS
          traefik.tcp.routers.meu-servico-tcp-router.service: "meu-servico-tcp-svc"
          traefik.tcp.services.meu-servico-tcp-svc.loadbalancer.server.port: "54321" # Porta interna do container backend
          # Para TLS Passthrough (Traefik não termina TLS, apenas encaminha):
          # traefik.tcp.routers.meu-servico-tcp-router.tls.passthrough: "true"
        ```
*   **Cloudflare Tunnel para TCP/UDP:** Cloudflare Tunnel também suporta proxying de tráfego TCP e UDP arbitrário, não apenas HTTP/S. Você precisaria configurar isso no `cloudflared` ou no dashboard da Cloudflare e, em seguida, o Traefik receberia esse tráfego no entrypoint TCP/UDP correspondente.

### Traefik e Health Checks

Traefik pode usar os health checks definidos nos seus containers Docker para determinar se um backend está saudável antes de enviar tráfego para ele. Isso é implícito quando Traefik usa o Docker provider. Se um container falha no seu healthcheck Docker, Traefik pode parar de rotear tráfego para ele (dependendo da configuração do serviço no Traefik).

## 2. Authelia: Funcionalidades Avançadas

Authelia é mais do que apenas um provedor de 2FA.

### Notificações

Configurar o notificador SMTP no `authelia/config/configuration.yml` é **altamente recomendado**.

*   **Benefícios:**
    *   Reset de senha por email.
    *   Notificações de tentativas de login suspeitas ou bloqueios de conta.
    *   Alertas de segurança importantes do Authelia.
*   **Configuração (Exemplo):**
    ```yaml
    # Em authelia/config/configuration.yml
    notifier:
      smtp:
        address: "smtp.gmail.com:587" # Exemplo para Gmail
        username: "seu_email@gmail.com"
        password: "SUA_SENHA_DE_APLICATIVO_GMAIL" # Use senha de aplicativo!
        sender: "Authelia <seu_email@gmail.com>"
        subject: "[Authelia - {{ base_domain }}] {title}"
        # tls: # Geralmente STARTTLS é usado na porta 587
        #   skip_verify: false
    ```
    !!! warning "Senhas de Aplicativo"
        Para serviços como Gmail, você precisará gerar uma "Senha de Aplicativo" em vez de usar sua senha principal, se tiver 2FA habilitado na sua conta Google.

### WebAuthn (FIDO2 / Passkeys)

Além de TOTP, Authelia suporta WebAuthn como um método de segundo fator, permitindo o uso de chaves de segurança hardware (YubiKey, etc.) ou autenticadores biométricos (Windows Hello, Touch ID).

*   **Configuração:** Geralmente habilitado por padrão se o portal Authelia for acessado via HTTPS (o que é o nosso caso).
*   **Registro:** Os usuários podem registrar dispositivos WebAuthn em seu perfil no portal Authelia.

### Políticas de Acesso Mais Granulares

As `access_control.rules` no `configuration.yml` do Authelia podem ser bastante sofisticadas.

*   **Critérios de Matching:**
    *   `domain`: `meuservico.example.com`, `*.example.com`, `sub.domain.example.com`
    *   `domain_regex`: Usar regex para domínios.
    *   `path` / `path_regex`: Aplicar regras a caminhos específicos.
    *   `method`: `GET`, `POST`, etc.
    *   `networks`: Lista de CIDRs de IP.
    *   `subject`: Aplicar regras a usuários ou grupos específicos (e.g., `user:alice`, `group:admins`).
*   **Políticas:**
    *   `bypass`: Sem autenticação.
    *   `one_factor`: Requer apenas o primeiro fator (usuário/senha).
    *   `two_factor`: Requer primeiro e segundo fator.
    *   `deny`: Nega o acesso.
*   **Exemplo:**
    ```yaml
    access_control:
      default_policy: deny
      rules:
        - domain: "auth.{{ base_domain }}"
          policy: bypass
        - domain: "public-service.{{ base_domain }}" # Um serviço que não precisa de login
          policy: bypass
        - domain: "admin-panel.{{ base_domain }}"
          subject: "group:admins" # Apenas usuários no grupo 'admins'
          policy: two_factor
        - domain: "*.internal.{{ base_domain }}"
          networks: ["192.168.1.0/24"] # Acesso da LAN
          policy: one_factor # Só primeiro fator se da LAN
        - domain: "*.{{ base_domain }}" # Catch-all para outros
          policy: two_factor
    ```

### Integração com Provedores de Identidade Externos (LDAP/OIDC)

Para ambientes maiores ou se você já tem um sistema de gerenciamento de identidades, Authelia pode se integrar com:

*   **LDAP:** Authelia pode usar um servidor LDAP (e.g., OpenLDAP, Active Directory) como backend de autenticação para o primeiro fator.
*   **OpenID Connect (OIDC):** Authelia pode atuar como um Provedor OIDC, permitindo que outras aplicações deleguem a autenticação ao Authelia (SSO).
    *   Isso é mais avançado e requer que as aplicações clientes suportem OIDC.

### Gerenciamento de Usuários

*   **Backend de Arquivo (`users_database.yml`):** Simples para começar, mas menos gerenciável para muitos usuários. Hashes de senha precisam ser gerados com `authelia crypto hash generate argon2`.
*   **Backend de Banco de Dados (PostgreSQL, como configuramos):** Mais robusto.
    *   **Criação de Usuários:** O usuário admin inicial é definido via variáveis (no nosso caso, via `authelia_admin_user_initial` e `authelia_admin_password_hash_initial` no `vault.yml`, que o template `configuration.yml.j2` usa, ou Authelia pode ter um processo de bootstrap).
    *   Outros usuários podem precisar ser criados via API, ou pode haver uma UI de administração em desenvolvimento/disponível dependendo da versão do Authelia, ou diretamente no banco de dados (com cuidado). Para a maioria dos homelabs, criar alguns usuários via `users_database.yml` (se usar backend file) ou gerenciar poucos usuários no DB é suficiente.

### Sessões Persistentes com Redis (Opcional)

Se você rodar Authelia em um setup de múltiplos containers (e.g., para alta disponibilidade, não é nosso caso), usar Redis para armazenar sessões garante que a sessão do usuário persista mesmo que uma instância do Authelia caia.

*   **Configuração:** Adicionar um serviço Redis ao `docker-compose.yml` do Authelia e configurar a seção `session.redis` no `configuration.yml`.

Dominar Traefik e Authelia permite um controle fino sobre como seus serviços são expostos e protegidos. Sempre consulte suas documentações oficiais para as opções mais recentes e detalhadas.
*   [Documentação Traefik](https://doc.traefik.io/traefik/)
*   [Documentação Authelia](https://www.authelia.com/docs/)