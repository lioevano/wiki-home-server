# Aprofundamento em Traefik e Authelia: Proxy Reverso e Autenticação Avançada

Traefik Proxy e Authelia são os pilares da nossa estratégia de acesso externo seguro e gerenciamento de autenticação para os serviços web do nosso servidor doméstico. O [Manual de Implementação](../01-manual-implementacao/05-rede-segura.md) cobriu suas configurações básicas para colocar tudo em funcionamento.

Esta seção tem como objetivo aprofundar seu conhecimento sobre esses dois componentes poderosos, explorando funcionalidades mais avançadas, opções de personalização e como eles trabalham em conjunto para proteger sua infraestrutura.

## 1. Traefik Proxy: Explorando Middlewares Avançados e Outras Funcionalidades

Traefik utiliza um sistema flexível e poderoso de **middlewares** para processar requisições HTTP antes que elas cheguem aos seus serviços backend (os containers Docker). Além dos middlewares básicos que já usamos (como o de redirecionamento HTTP-para-HTTPS e o de forward auth para Authelia), Traefik oferece muitos outros.

### Cadeias de Middlewares (Chaining) e Ordem de Aplicação

Você pode aplicar múltiplos middlewares a um único roteador Traefik, criando uma "cadeia" de processamento. A ordem em que os middlewares são listados na configuração do roteador geralmente dita a ordem em que são aplicados à requisição.

*   **Definição de Middlewares:**
    *   **Via Labels Docker (no `docker-compose.yml` do serviço):** Conveniente para middlewares específicos de um serviço.
        Ex: `traefik.http.middlewares.meu-middleware-nome.plugin.opcoes...`
    *   **Via File Provider (em arquivos YAML no diretório de configuração dinâmica do Traefik):** Ideal para middlewares globais ou complexos que você quer reutilizar em múltiplos roteadores. Nossos `securityHeaders@file` e `nextcloud-headers@file` são exemplos.
    *   **Via Configuração Estática (`traefik.yml`):** Menos comum para middlewares de roteamento, mais para configurações globais.
*   **Referenciando Middlewares em um Roteador:**
    No `docker-compose.yml` do serviço que o roteador expõe:
    ```yaml
    services:
      meu_servico_web:
        # ... outras configs ...
        labels:
          # ... labels do roteador (rule, entrypoints, service, tls) ...
          # Aplicando uma cadeia de middlewares:
          # A ordem aqui é importante!
          traefik.http.routers.meu_servico_web_router.middlewares: "authelia@docker,meu-custom-header@docker,meu-ratelimit@file,securityHeaders@file"
    ```
    *   `nome_middleware@provider`: Especifica o nome do middleware e onde ele foi definido (`docker` para labels, `file` para o File Provider, `internal` para os do Traefik).

### Tipos Comuns de Middlewares Traefik (Além dos Já Utilizados)

Explore a [documentação oficial de middlewares HTTP do Traefik](https://doc.traefik.io/traefik/middlewares/http/overview/) para a lista completa e todas as opções de configuração. Aqui estão alguns exemplos úteis:

*   **`RateLimit`:**
    *   **Propósito:** Limita o número de requisições que um cliente (baseado em IP de origem, por padrão) pode fazer a um serviço em um determinado período. Útil para prevenir abuso, ataques de força bruta lentos, ou sobrecarga por web scrapers.
    *   **Exemplo (label Docker):**
        ```yaml
        # Limita a 10 requisições por segundo, com uma "explosão" (burst) de até 20
        traefik.http.middlewares.meu-servico-ratelimit.ratelimit.average: "10"
        traefik.http.middlewares.meu-servico-ratelimit.ratelimit.burst: "20"
        # Opcional: traefik.http.middlewares.meu-servico-ratelimit.ratelimit.period: "5m" (para limites mais longos)
        ```
*   **`Retry`:**
    *   **Propósito:** Tenta reenviar uma requisição para o serviço backend se uma tentativa inicial falhar (e.g., devido a um erro de rede temporário ou um erro 5xx do backend).
    *   **Exemplo (label Docker):**
        ```yaml
        # Tenta até 3 vezes
        traefik.http.middlewares.meu-servico-retry.retry.attempts: "3"
        # Opcional: traefik.http.middlewares.meu-servico-retry.retry.initialInterval: "100ms"
        ```
*   **`Buffering`:**
    *   **Propósito:** Bufferiza o corpo da requisição e/ou da resposta. Pode ser útil para backends que são lentos para processar ou que esperam a requisição inteira antes de começar.
    *   **Exemplo (label Docker):**
        ```yaml
        traefik.http.middlewares.meu-servico-buffer.buffering.maxRequestBodyBytes: "10485760" # 10MB
        traefik.http.middlewares.meu-servico-buffer.buffering.memRequestBodyBytes: "2097152"  # 2MB em memória
        traefik.http.middlewares.meu-servico-buffer.buffering.retryExpression: "IsNetworkError() && Attempts() <= 2"
        ```
*   **`Compress`:**
    *   **Propósito:** Habilita compressão Gzip ou Brotli para as respostas enviadas ao cliente, se o cliente indicar suporte (via header `Accept-Encoding`). Pode reduzir o tamanho dos dados transferidos e melhorar os tempos de carregamento.
    *   **Exemplo (label Docker ou File Provider):**
        ```yaml
        # Habilita compressão (Traefik escolhe Gzip ou Brotli baseado no cliente)
        traefik.http.middlewares.meu-servico-compress.compress: "true"
        # Opcional: Especificar compressores excluídos
        # traefik.http.middlewares.meu-servico-compress.compress.excludedcontenttypes: "image/jpeg,video/mp4"
        ```
*   **`IPWhiteList` / `IPAllowList` (o nome mudou em versões mais recentes para `IPAllowList`):**
    *   **Propósito:** Restringe o acesso a um roteador apenas a uma lista de endereços IP ou faixas de CIDR específicas.
    *   **Exemplo (File Provider):**
        ```yaml
        # Em um arquivo .yml no diretório de configuração dinâmica do Traefik
        http:
          middlewares:
            meu-ip-allowlist:
              ipAllowList:
                sourceRange:
                  - "192.168.1.0/24"  # Permite sua LAN
                  - "203.0.113.42/32" # Permite um IP público específico
                # ipStrategy: # Opcional, para profundidade de X-Forwarded-For
                #   depth: 1
        ```
*   **`InFlightReq` (Requisições em Trânsito):**
    *   **Propósito:** Limita o número de requisições simultâneas que são encaminhadas para um serviço backend. Pode ajudar a prevenir a sobrecarga de um backend que tem capacidade limitada de processamento concorrente.
    *   **Exemplo (label Docker):**
        ```yaml
        # Permite no máximo 50 requisições simultâneas para este backend
        traefik.http.middlewares.meu-servico-inflight.inflightreq.amount: "50"
        # Opcional: sourceCriterion.ipStrategy.depth: 2 (para considerar o IP real atrás de proxies)
        ```
*   **`ErrorPages` (Páginas de Erro Customizadas):**
    *   **Propósito:** Permite que você defina páginas de erro HTML customizadas para códigos de status HTTP específicos (e.g., 401, 403, 404, 500) em vez de exibir as páginas de erro padrão do Traefik ou do serviço backend.
    *   **Configuração:** Você define um serviço backend que serve as páginas de erro e um query path que inclui o status.
    *   **Exemplo (File Provider):**
        ```yaml
        # Em um arquivo .yml no diretório de configuração dinâmica
        http:
          services: # Serviço que serve as páginas de erro
            meu-error-page-service:
              loadBalancer:
                servers:
                  - url: "http://meu_servidor_de_paginas_de_erro_estaticas/" # e.g., um Nginx servindo HTMLs
          middlewares:
            minhas-custom-errors:
              errors:
                status:
                  - "401-404" # Intervalo de códigos de status
                  - "500-599"
                service: "meu-error-page-service@file" # Serviço definido acima
                query: "/{status}.html" # Traefik substituirá {status} pelo código de erro
                                        # e buscará /404.html, /500.html, etc.
        ```
*   **`StripPrefix`, `AddPrefix`, `ReplacePath`, `ReplacePathRegex`:**
    *   **Propósito:** Vários middlewares para manipular o caminho (path) da URL da requisição antes que ela seja encaminhada ao serviço backend. Útil se a aplicação backend espera requisições em um sub-path específico, mas você quer expô-la na raiz de um subdomínio (ou vice-versa).

### Roteamento TCP e UDP com Traefik (Além de HTTP/S)

Embora nosso foco principal neste guia seja em serviços web HTTP/S, Traefik também é capaz de atuar como um proxy reverso para tráfego **TCP** genérico e **UDP**.

*   **Casos de Uso Comuns:**
    *   Expor um servidor de banco de dados (e.g., PostgreSQL, MySQL) para acesso restrito (com IPAllowList).
    *   Expor um servidor de jogos que usa TCP ou UDP.
    *   Servidores MQTT, OpenVPN (UDP), ou outros serviços baseados em TCP/UDP.
*   **Configuração Geral:**
    1.  **Definir Entrypoints TCP/UDP na Configuração Estática (`traefik.yml`):**
        ```yaml
        # Exemplo em traefik.yml
        entryPoints:
          # ... (seus entrypoints web e websecure) ...
          meu_servico_tcp_entry: # Nome do entrypoint TCP
            address: ":12345/tcp" # Traefik escutará na porta 12345/tcp
          meu_servico_udp_entry: # Nome do entrypoint UDP
            address: ":54321/udp" # Traefik escutará na porta 54321/udp
        ```
    2.  **Mapear as Portas no Container Traefik:** No `docker-compose.yml` da stack `core`, você precisará adicionar esses mapeamentos de porta para o container Traefik:
        ```yaml
        # No docker-compose.yml do Traefik
        services:
          traefik:
            ports:
              # ... (portas 80 e 443) ...
              - "${CORE_SERVICES_VM_IP_VAR}:12345:12345/tcp"
              - "${CORE_SERVICES_VM_IP_VAR}:54321:54321/udp"
        ```
    3.  **Configurar Roteadores TCP/UDP:** Você define roteadores TCP ou UDP, geralmente via labels Docker ou File Provider, para direcionar o tráfego desses entrypoints para os serviços backend apropriados.
        *   A regra de roteamento para TCP/UDP é frequentemente baseada em `HostSNI(\`*\`)` (para tráfego TCP que usa TLS e tem um Server Name Indication) ou simplesmente no entrypoint (aceitando qualquer tráfego que chegue naquele entrypoint).
        *   **Exemplo de Labels Docker para um Serviço TCP (sem TLS no Traefik):**
            ```yaml
            services:
              meu_servico_backend_tcp:
                image: ...
                # NÃO mapeie a porta aqui se Traefik for o único ponto de entrada
                labels:
                  traefik.enable: "true"
                  traefik.tcp.routers.meu_tcp_router.entrypoints: "meu_servico_tcp_entry" # Entrypoint TCP definido
                  traefik.tcp.routers.meu_tcp_router.rule: "HostSNI(`*`)" # Aceita qualquer tráfego neste entrypoint
                  traefik.tcp.routers.meu_tcp_router.service: "meu_tcp_service"
                  traefik.tcp.services.meu_tcp_service.loadbalancer.server.port: "50000" # Porta INTERNA do container backend
            ```
        *   **TLS Passthrough para TCP:** Se seu serviço TCP backend lida com sua própria terminação TLS, você pode configurar o Traefik para fazer "TLS Passthrough", onde ele apenas encaminha o tráfego TCP criptografado sem tentar descriptografá-lo.
            ```yaml
            # ...
            traefik.tcp.routers.meu_tcp_router.tls.passthrough: "true"
            # ...
            ```
*   **Cloudflare Tunnel para TCP/UDP:** Lembre-se que o Cloudflare Tunnel também pode proxyar tráfego TCP e UDP arbitrário, não apenas HTTP/S. Você precisaria configurar isso no seu `cloudflared` (via arquivo de configuração ou Ingress Rules no dashboard da Cloudflare) para apontar para o entrypoint TCP/UDP correspondente no Traefik.

### Traefik e Health Checks de Backend

Traefik pode usar os **health checks** definidos nos seus containers Docker (na seção `healthcheck:` do `docker-compose.yml`) para determinar se uma instância de um serviço backend está saudável antes de enviar tráfego para ela.
*   Quando o Docker provider está habilitado, Traefik automaticamente leva em consideração o status de saúde reportado pelo Docker para os containers.
*   Se um container falha no seu healthcheck Docker, Traefik pode parar de rotear tráfego para aquela instância específica (especialmente útil se você tiver múltiplas réplicas de um serviço para balanceamento de carga).

## 2. Authelia: Explorando Funcionalidades Avançadas

Authelia é mais do que um simples provedor de 2FA; ele oferece um conjunto robusto de funcionalidades para gerenciamento de identidade e acesso.

### Configuração de Notificações (SMTP)

Configurar o notificador SMTP no arquivo `authelia/config/configuration.yml` é **altamente recomendado** para funcionalidades críticas.

*   **Benefícios:**
    *   Permite que os usuários realizem **reset de senha por email** de forma segura.
    *   Authelia pode enviar **notificações de segurança** (e.g., sobre tentativas de login suspeitas, bloqueios de conta devido a muitas falhas, registro de novos dispositivos 2FA).
    *   Alertas importantes do próprio sistema Authelia.
*   **Configuração (Exemplo no `configuration.yml` do Authelia):**
    ```yaml
    # Em authelia/config/configuration.yml
    notifier:
      smtp:
        address: "smtp.seuprovedor.com:587" # Ex: smtp.gmail.com:587, smtp.mailgun.org:587
        username: "seu_email_de_envio@example.com"
        # Para Gmail/Google Workspace, use uma "Senha de Aplicativo" gerada, não sua senha principal.
        password: "SUA_SENHA_DE_EMAIL_OU_SENHA_DE_APLICATIVO"
        sender: "Authelia <authelia_noreply@{{ base_domain }}>" # Remetente exibido nos emails
        subject: "[Authelia - {{ base_domain }}] {title}" # {title} será substituído pelo título da notificação
        # tls: # Geralmente STARTTLS é usado na porta 587 e é negociado automaticamente.
        #   skip_verify: false # Mantenha false para produção para verificar o certificado do servidor SMTP.
        # Para verificar a configuração do notificador ao iniciar Authelia:
        # startup_check_address: "seu_email_pessoal_para_teste@example.com"
    ```
    !!! warning "Senhas de Aplicativo para Provedores de Email"
        Se você usar um provedor de email como Gmail ou Outlook que tenha 2FA habilitado na sua conta, você geralmente precisará gerar uma **"Senha de Aplicativo"** específica para o Authelia usar, em vez de sua senha de login principal. Consulte a documentação do seu provedor de email.

### Suporte a WebAuthn (FIDO2 / Passkeys)

Além de TOTP (Time-based One-Time Passwords de aplicativos autenticadores), Authelia tem um excelente suporte a **WebAuthn**, que permite o uso de:
*   **Chaves de Segurança Hardware:** Como YubiKey, Google Titan Key, etc.
*   **Autenticadores Biométricos Integrados:** Como Windows Hello (reconhecimento facial/impressão digital), Touch ID/Face ID da Apple.
*   **Passkeys:** A evolução do WebAuthn, permitindo logins sem senha sincronizados entre dispositivos.

*   **Configuração:** Geralmente habilitado por padrão no Authelia se o portal de login (`auth.{{ base_domain }}`) for acessado via **HTTPS** (o que é o nosso caso, graças ao Traefik e Let's Encrypt).
*   **Registro pelo Usuário:** Os usuários podem registrar seus dispositivos WebAuthn (chaves de segurança, biometria) diretamente em seu perfil no portal Authelia, após fazerem login com seu primeiro fator e um método 2FA já registrado (como TOTP).

### Políticas de Acesso Mais Granulares e Sofisticadas

As regras de controle de acesso (`access_control.rules`) no `configuration.yml` do Authelia podem ser muito mais detalhadas do que o exemplo básico que usamos.

*   **Critérios de Correspondência para Regras:**
    *   `domain`: `meuservico.example.com`, `*.example.com` (wildcard simples), `sub.domain.example.com`.
    *   `domain_regex`: Permite usar expressões regulares para corresponder a domínios.
    *   `path` ou `path_regex`: Aplica regras a caminhos de URL específicos (e.g., `/admin`, `/api/v2`).
    *   `method`: Permite aplicar regras baseadas no método HTTP da requisição (e.g., `GET`, `POST`, `PUT`).
    *   `networks`: Lista de endereços IP ou faixas CIDR de origem (e.g., permitir acesso da sua LAN sem 2FA).
    *   `subject`: Aplica regras baseadas na identidade do usuário ou nos grupos aos quais ele pertence (e.g., `user:alice`, `group:admins`, `group:editors`).
*   **Políticas de Acesso Disponíveis:**
    *   `bypass`: Acesso permitido sem qualquer autenticação do Authelia.
    *   `one_factor`: Requer apenas o primeiro fator de autenticação (usuário/senha) bem-sucedido.
    *   `two_factor`: Requer primeiro e segundo fator (e.g., senha + TOTP/WebAuthn) bem-sucedidos.
    *   `deny`: Nega explicitamente o acesso, mesmo que outras regras permitam.
*   **Exemplo de Regras Mais Complexas:**
    ```yaml
    access_control:
      default_policy: deny # Política padrão se nenhuma regra corresponder
      rules:
        # Regra para o próprio portal Authelia (sempre bypass)
        - domain: "auth.{{ base_domain }}"
          policy: bypass

        # Regra para um serviço público que não requer login
        - domain: "meu-blog-publico.{{ base_domain }}"
          policy: bypass

        # Regra para um painel de administração, apenas para usuários do grupo 'admins' com 2FA
        - domain: "admin-panel.{{ base_domain }}"
          subject: "group:admins"
          policy: two_factor

        # Regra para serviços internos, acessíveis da LAN com apenas senha, mas requer 2FA de fora
        - domain: "*.servicos-internos.{{ base_domain }}"
          networks: ["192.168.15.0/24"] # CIDR da sua LAN
          policy: one_factor
        - domain: "*.servicos-internos.{{ base_domain }}" # Para acesso externo (não da LAN)
          policy: two_factor # Requer 2FA

        # Regra geral para todos os outros subdomínios: requer 2FA
        - domain: "*.{{ base_domain }}"
          policy: two_factor
    ```

### Integração com Provedores de Identidade Externos (LDAP / OpenID Connect - OIDC)

Para ambientes de homelab mais avançados ou se você já possui um sistema centralizado de gerenciamento de identidades, Authelia pode se integrar com:

*   **LDAP:** Authelia pode usar um servidor LDAP (como OpenLDAP, FreeIPA, ou até mesmo Active Directory) como um **backend de autenticação para o primeiro fator (usuário/senha)**. Os usuários e grupos são gerenciados no LDAP, e Authelia consulta o LDAP para verificar as credenciais. O segundo fator (2FA) ainda é gerenciado pelo Authelia.
*   **OpenID Connect (OIDC) como Provedor (IdP):** Authelia pode atuar como um Provedor OpenID Connect. Isso significa que outras aplicações que suportam login via OIDC (muitas aplicações modernas o fazem) podem delegar a autenticação dos seus usuários ao Authelia. Isso permite um verdadeiro Single Sign-On (SSO) onde o usuário loga uma vez no Authelia e ganha acesso a múltiplas aplicações clientes OIDC.
    *   Configurar Authelia como um IdP OIDC e registrar clientes OIDC (suas outras aplicações) é um tópico mais avançado.

### Gerenciamento de Usuários

*   **Backend de Arquivo (`users_database.yml`):** Simples para começar com poucos usuários. Lembre-se que as senhas devem ser hashes Argon2id gerados com o comando `authelia crypto hash generate argon2 ...`.
*   **Backend de Banco de Dados (PostgreSQL, como configuramos):** Mais robusto e escalável.
    *   **Criação de Usuários:**
        *   O usuário administrador inicial (`{{ authelia_admin_user_initial }}`) é implicitamente criado com base no hash de senha fornecido no `configuration.yml` (que nosso template Ansible preenche do `vault.yml`).
        *   Para outros usuários, a forma mais fácil em um setup com DB é:
            1.  O usuário tenta logar no portal Authelia com um nome de usuário e senha desejados. O login falhará.
            2.  O administrador (você) pode então precisar aprovar ou criar o usuário no banco de dados ou através de uma interface de administração do Authelia, se disponível e configurada.
            3.  Alternativamente, para setups controlados, você pode adicionar usuários diretamente ao banco de dados PostgreSQL (com senhas hasheadas corretamente) ou usar a API do Authelia (se disponível) para gerenciamento de usuários.
        *   Para a maioria dos homelabs, criar alguns usuários manualmente (seja via arquivo ou DB) é suficiente.

### Sessões Persistentes e Distribuídas com Redis (Opcional)

Se você fosse rodar Authelia em um setup de alta disponibilidade com múltiplas instâncias do container Authelia (não é o nosso caso aqui, pois temos uma única `core-services-vm`), usar **Redis** para armazenar as sessões dos usuários se torna crucial. Isso garante que a sessão de um usuário persista e seja compartilhada entre todas as instâncias do Authelia, de modo que o usuário não perca a sessão se sua requisição for para uma instância diferente do Authelia.

*   **Configuração:**
    1.  Adicionar um serviço Redis ao `docker-compose.yml` da stack Authelia (conectado à rede `internal_services`).
    2.  No `configuration.yml` do Authelia, configurar a seção `session.redis:` com os detalhes do host e porta do serviço Redis.

Dominar as funcionalidades avançadas do Traefik e do Authelia permite um controle incrivelmente fino sobre como seus serviços são expostos, protegidos e acessados. Sempre consulte as documentações oficiais para as opções mais recentes, detalhadas e para exemplos de configuração específicos:

*   ➡️ **[Documentação Oficial do Traefik Proxy](https://doc.traefik.io/traefik/)**
*   ➡️ **[Documentação Oficial do Authelia](https://www.authelia.com/docs/)**