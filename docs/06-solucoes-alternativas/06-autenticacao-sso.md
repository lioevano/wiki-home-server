# Alternativas para Servidores de Autenticação e Single Sign-On (SSO)

Para proteger o acesso aos nossos serviços web expostos via Traefik, escolhemos e implementamos **Authelia** como nosso portal de autenticação centralizado e provedor de segundo fator (2FA). Authelia se integra muito bem com proxies reversos como Traefik usando o modelo de "forward authentication" e oferece um excelente equilíbrio entre funcionalidades de segurança (2FA, políticas de acesso básicas, proteção contra brute-force) e uma complexidade de configuração gerenciável para um ambiente de homelab.

No entanto, o universo de soluções de Gerenciamento de Identidade e Acesso (IAM - Identity and Access Management) e Single Sign-On (SSO) é vasto, com diversas opções open-source e comerciais, cada uma com diferentes focos, capacidades e níveis de complexidade.

## 1. Authelia (Nossa Escolha no Guia - Revisão)

*   **Tipo:** Servidor de autenticação e autorização open-source, projetado especificamente para adicionar uma camada de autenticação (incluindo 2FA) a aplicações web que são expostas através de um proxy reverso.
*   **Principais Razões da Escolha para este Guia:**
    *   **Leveza e Simplicidade Relativa de Configuração:** Para o conjunto de funcionalidades que oferece (2FA, políticas de acesso baseadas em domínio/rede, proteção contra brute-force), a configuração do Authelia (primariamente via um arquivo YAML, `configuration.yml`) é considerada gerenciável, especialmente para um homelab.
    *   **Excelente Integração com Proxies Reversos (Forward Authentication):** Authelia é projetado para funcionar perfeitamente com Traefik (usando o middleware `ForwardAuth`), Nginx (com o módulo `ngx_http_auth_request_module`), HAProxy, e Caddy. O proxy reverso delega a decisão de autenticação/autorização para o Authelia antes de permitir o acesso ao serviço backend.
    *   **Suporte a Múltiplos Fatores de Autenticação (MFA):**
        *   **TOTP (Time-based One-Time Password):** Suporte nativo para aplicativos autenticadores como Google Authenticator, Authy, Microsoft Authenticator, etc.
        *   **WebAuthn (FIDO2 / Passkeys):** Suporte robusto para chaves de segurança hardware (YubiKey, etc.) e autenticadores biométricos (Windows Hello, Touch ID/Face ID), oferecendo uma forma de 2FA (ou mesmo login sem senha, com passkeys) muito segura e resistente a phishing.
        *   **Duo Push (via API Duo):** Pode se integrar com o serviço Duo Security para notificações push como segundo fator (requer uma conta Duo).
    *   **Políticas de Acesso Granulares:** Permite definir regras no `configuration.yml` (seção `access_control`) baseadas em domínio, subdomínio, path da URL, método HTTP, rede de origem (IP/CIDR), e identidade do usuário ou grupo para aplicar diferentes políticas (`bypass`, `one_factor`, `two_factor`, `deny`).
    *   **Proteção contra Brute-Force:** Limita o número de tentativas de login falhas e pode banir temporariamente IPs.
    *   **SSO Básico entre Aplicações Protegidas pelo Mesmo Authelia:** Uma vez que um usuário está logado no portal Authelia e tem uma sessão válida (cookie), o acesso a outros serviços web que também são protegidos pela mesma instância do Authelia (e para os quais o usuário tem permissão) é transparente, sem a necessidade de logar novamente em cada um.
    *   **Armazenamento Flexível de Usuários e Configurações:**
        *   Pode usar um **arquivo YAML (`users_database.yml`)** para armazenar definições de usuários e hashes de senha (Argon2id). Simples para poucos usuários.
        *   Pode usar um **banco de dados SQL (SQLite, PostgreSQL, MySQL)** para armazenar dados de usuários, dispositivos 2FA, sessões, etc. Nossa arquitetura usa PostgreSQL para isso, o que é mais robusto.
    *   **Totalmente Open Source e Auto-Hospedado:** Você tem controle completo sobre seus dados de autenticação e o processo.
*   **Possíveis Limitações ou Áreas de Menor Foco:**
    *   **Foco Principal em "Forward Authentication" para Aplicações Web:** Authelia é primariamente projetado para proteger aplicações web que podem ser colocadas atrás de um proxy reverso. Sua capacidade de atuar como um Provedor de Identidade (IdP) completo para protocolos de SSO mais complexos como SAML 2.0 ou um Provedor OpenID Connect (OIDC) completo para múltiplas aplicações clientes (Relying Parties) é historicamente mais limitada ou inexistente nativamente (embora funcionalidades OIDC básicas como IdP possam estar evoluindo ou tenham sido adicionadas em versões mais recentes – verifique a documentação).
    *   **Gerenciamento de Usuários (sem backend externo):** Se você não integrar o Authelia com um backend de usuários externo como LDAP, o gerenciamento de um grande número de usuários pode se tornar manual (seja editando o `users_database.yml` ou interagindo diretamente com o banco de dados SQL).
    *   **Interface de Administração Web:** Historicamente, Authelia não possuía uma interface web de administração completa para gerenciamento de usuários, políticas, etc. (o foco era na configuração via arquivos YAML). Isso pode estar mudando ou pode haver projetos comunitários para UIs.

## 2. Keycloak (Solução IAM Open Source Completa)

*   **Tipo:** Uma solução de **Gerenciamento de Identidade e Acesso (IAM - Identity and Access Management)** open-source, de nível empresarial, extremamente poderosa e rica em funcionalidades, desenvolvida pela Red Hat (e um projeto da CNCF).
*   **Prós:**
    *   **Provedor de Identidade (IdP) Completo e Padrão da Indústria:** Keycloak é projetado para ser um IdP central.
    *   **Suporte Extensivo a Protocolos de SSO:**
        *   **OpenID Connect (OIDC) 1.0 Provider:** Implementação completa.
        *   **SAML 2.0 Identity Provider:** Para integração com aplicações que usam SAML.
        *   **OAuth 2.0 Authorization Server.**
    *   **Gerenciamento de Usuários Abrangente:** Interface web de administração para gerenciar usuários, grupos, roles, atributos de usuário, e políticas de senha.
    *   **Federação de Identidades:** Pode se conectar e federar com outros Provedores de Identidade externos, como:
        *   Servidores LDAP ou Microsoft Active Directory.
        *   Provedores OIDC/OAuth2 sociais (Google, Facebook, GitHub, etc.).
        *   Outros IdPs SAML.
    *   **Autenticação de Múltiplos Fatores (MFA):** Suporte nativo para TOTP, WebAuthn (FIDO2/Passkeys), e pode ser estendido.
    *   **Interface de Administração Web Completa (Admin Console):** Para gerenciar todos os aspectos do Keycloak (realms, clientes, usuários, roles, fluxos de autenticação, etc.).
    *   **Customização de Interface do Usuário:** Permite customizar as páginas de login, registro, gerenciamento de conta, etc., usando temas.
    *   **Políticas de Senha Avançadas e Fluxos de Autenticação Customizáveis:** Controle fino sobre os requisitos de senha e as etapas do processo de login/registro.
    *   **APIs REST para Gerenciamento e Integração.**
    *   **Escalabilidade e Alta Disponibilidade:** Projetado para rodar em modo clusterizado para HA.
    *   **Boa Documentação e Comunidade Ativa.**
*   **Contras:**
    *   **Complexidade Significativa:** Keycloak é uma solução IAM completa e, como tal, é **significativamente mais complexo de configurar, gerenciar e entender** do que uma ferramenta mais focada como Authelia. Há muitos conceitos para aprender (Realms, Clients, Roles, Mappers, Flows, etc.).
    *   **Consumo de Recursos Mais Elevado:** Sendo uma aplicação Java robusta (geralmente rodando em WildFly/JBoss), Keycloak tipicamente requer **mais RAM e CPU** do que Authelia. Para um homelab com recursos limitados, isso pode ser uma consideração importante.
    *   **Pode ser Overkill para Necessidades Simples de Homelab:** Se seu único requisito é adicionar 2FA a algumas aplicações web atrás de um proxy reverso, Keycloak pode ser um exagero em termos de complexidade e recursos.
    *   **Integração com Proxy Reverso para "Forward Auth Simples":** Embora Keycloak possa proteger aplicações que suportam OIDC/SAML nativamente, ou você possa usar um "adapter" Keycloak específico da aplicação, a integração no estilo "forward auth" simples (como Authelia faz com Traefik) não é seu principal modo de operação. Para isso, você geralmente usaria uma ferramenta complementar como [`oauth2-proxy`](#5-oauth2-proxy) configurada para usar Keycloak como o backend IdP OIDC.
*   **Quando Considerar Keycloak para Homelab?**
    *   Se você precisa de um **Provedor de Identidade (IdP) completo** com suporte robusto para **OpenID Connect (OIDC) e/ou SAML 2.0** para suas aplicações auto-hospedadas.
    *   Se você quer **federar identidades** com outros sistemas (e.g., usar sua conta Google para logar nos seus serviços, ou integrar com um LDAP local).
    *   Se você precisa de funcionalidades de **gerenciamento de usuários e roles** muito avançadas e centralizadas.
    *   Se você está **aprendendo Keycloak para fins profissionais**, pois é uma ferramenta IAM muito usada em ambientes empresariais.
    *   Se você tem os **recursos de hardware (RAM/CPU) para rodá-lo confortavelmente** e está disposto a investir o tempo para aprender sua complexidade.

## 3. Authentik

*   **Tipo:** Uma solução de Gerenciamento de Identidade e Acesso (IAM) open-source, moderna e rica em funcionalidades, similar ao Keycloak em escopo e capacidades, mas com um foco em uma experiência de usuário mais moderna e um sistema de "outposts" para integração flexível.
*   **Prós:**
    *   **Conjunto de Funcionalidades Abrangente:** Suporte para OpenID Connect (OIDC) Provider, SAML IdP, LDAP (pode atuar como um proxy LDAP ou ter seu próprio backend), RADIUS.
    *   **Interface de Usuário Moderna e Intuitiva:** Tanto a interface de administração quanto a interface do usuário final (login, gerenciamento de conta) são geralmente consideradas bem projetadas e fáceis de usar.
    *   **"Outposts" para Integração Flexível:** Authentik usa um conceito de "outposts" que são agentes/proxies que podem ser implantados para integrar Authentik com diferentes tipos de aplicações:
        *   **Proxy Outpost:** Atua como um proxy reverso que pode adicionar autenticação OIDC a aplicações que não a suportam nativamente (similar ao `oauth2-proxy`).
        *   **LDAP Outpost:** Expõe os usuários e grupos do Authentik como um servidor LDAP, permitindo que aplicações legadas que só suportam LDAP se autentiquem contra o Authentik.
        *   **RADIUS Outpost:** Para autenticação de rede (e.g., Wi-Fi).
    *   **Fluxos de Políticas e Autenticação Poderosos e Customizáveis (baseados em Python e YAML):** Permite criar lógicas de autenticação e autorização muito complexas e condicionais.
    *   **Suporte a MFA Amplo:** TOTP, WebAuthn (FIDO2/Passkeys), Duo, SMS, Email OTPs.
    *   **Comunidade Ativa e Desenvolvimento Rápido.**
    *   **Pode rodar bem como containers Docker.**
*   **Contras:**
    *   **Complexidade:** Assim como Keycloak, por ser uma solução IAM completa, Authentik tem uma curva de aprendizado considerável devido ao número de conceitos e opções de configuração.
    *   **Consumo de Recursos:** Pode ser mais pesado em recursos (CPU/RAM) do que uma solução mais simples como Authelia, embora possa ser mais leve que Keycloak em alguns cenários.
    *   **Maturidade Relativa:** Embora esteja evoluindo muito rapidamente e ganhando popularidade, é um projeto um pouco mais novo do que Keycloak.
*   **Quando Considerar Authentik para Homelab?**
    *   Se você está procurando uma **alternativa moderna e rica em funcionalidades ao Keycloak**, com uma UI potencialmente mais amigável e o conceito interessante de "outposts".
    *   Se você precisa de **suporte a múltiplos protocolos de SSO (OIDC, SAML, LDAP, RADIUS)** em uma única plataforma.
    *   Se você gosta da ideia de **fluxos de autenticação altamente customizáveis**.
    *   Se você tem os recursos para rodá-lo e está disposto a aprender seus conceitos.

## 4. Pomerium

*   **Tipo:** Um **proxy reverso sensível à identidade (identity-aware proxy - IAP)**, open-source. Ele *é* o proxy e o ponto de aplicação de políticas de acesso, com foco em segurança de perímetro e acesso Zero Trust.
*   **Como Funciona:**
    Você coloca o Pomerium na frente das suas aplicações internas. O Pomerium se integra com seu **Provedor de Identidade (IdP) existente** (e.g., Google, Okta, Auth0, Azure AD, Keycloak, ou até mesmo um arquivo de usuários gerenciado pelo Pomerium) para autenticar os usuários. Uma vez autenticado, o Pomerium aplica **políticas de acesso** baseadas na identidade do usuário (e outros contextos) para determinar se o acesso à aplicação backend deve ser permitido.
*   **Prós:**
    *   **Forte Foco em Segurança de Perímetro e Acesso Zero Trust (ZTNA):** Projetado para fornecer acesso seguro a aplicações internas sem a necessidade de uma VPN tradicional.
    *   **Acesso Baseado em Contexto (Context-Aware Access):** As políticas de acesso no Pomerium podem ser muito granulares e baseadas em múltiplos fatores, como a identidade do usuário (e seus grupos/atributos do IdP), o dispositivo do usuário, sua geolocalização, etc.
    *   **Pode Funcionar com uma Vasta Gama de Provedores de Identidade (IdPs) OIDC/SAML.**
    *   **Auditoria Detalhada de Acesso.**
    *   **Pode lidar com TCP e proxy reverso HTTP/S.**
*   **Contras:**
    *   **Ele é o Proxy (ou uma Camada Adicional de Proxy):** Diferente do Authelia que se integra *com* seu proxy reverso existente (como Traefik), o Pomerium geralmente atua *como* o proxy reverso principal para as aplicações que ele protege, ou como uma camada de proxy adicional na frente delas. Isso pode simplificar algumas coisas (a lógica de auth está no proxy), mas pode também complicar seu setup se você já tem um proxy reverso como Traefik com o qual está satisfeito (embora seja possível integrar Pomerium com Traefik).
    *   **Configuração e Dependência de um IdP:** Requer um Provedor de Identidade (IdP) para se integrar (embora tenha um modo "bootstrap" com usuários definidos em arquivo para começar). A configuração das políticas de acesso e da integração com o IdP pode ser complexa.
    *   **Menos Focado em Ser um "Portal de Login Único" Visível como Authelia:** Embora forneça SSO, sua interface de login é geralmente a do IdP externo.
*   **Quando Considerar Pomerium para Homelab?**
    *   Se você está construindo uma arquitetura com um forte foco em **Zero Trust Network Access (ZTNA)**.
    *   Se você já utiliza um Provedor de Identidade (IdP) externo (como Google Workspace, Microsoft Entra ID/Azure AD, Okta) e quer uma forma de estender essa autenticação para suas aplicações auto-hospedadas com políticas de acesso muito granulares e baseadas em contexto.
    *   Se a ideia de um proxy que é intrinsecamente "identity-aware" lhe agrada.

## 5. `oauth2-proxy` (ou `oidc-proxy`)

*   **Tipo:** Um **proxy reverso simples** que fornece uma camada de autenticação na frente de aplicações web, integrando-se com Provedores **OAuth2** ou **OpenID Connect (OIDC)** existentes.
*   **Como Funciona:**
    Você coloca o `oauth2-proxy` na frente da sua aplicação interna. Quando um usuário tenta acessar a aplicação:
    1.  `oauth2-proxy` intercepta a requisição e, se o usuário não estiver autenticado, o redireciona para o Provedor de Identidade (IdP) OIDC/OAuth2 configurado (e.g., Google, GitHub, Keycloak, Authelia se Authelia estivesse atuando como IdP OIDC).
    2.  O usuário se autentica no IdP.
    3.  Se a autenticação for bem-sucedida, o IdP redireciona o usuário de volta para um endpoint no `oauth2-proxy` com um código de autorização ou token.
    4.  `oauth2-proxy` valida o token/código com o IdP, estabelece uma sessão local (geralmente um cookie) para o usuário, e então permite o acesso à aplicação backend.
    5.  `oauth2-proxy` pode passar informações sobre o usuário autenticado (e.g., email, nome de usuário, grupos, o token de acesso) para a aplicação backend através de headers HTTP.
*   **Prós:**
    *   **Relativamente Simples para Adicionar SSO a Aplicações Existentes:** Se você já tem um Provedor de Identidade (IdP) OIDC/OAuth2 que você confia (seja um serviço público como Google, ou um auto-hospedado como Keycloak), o `oauth2-proxy` é uma maneira relativamente fácil e leve de proteger uma aplicação interna que não suporta esses protocolos de SSO nativamente.
    *   **Leve e Escrito em Go.**
    *   **Muitas Opções de Provedores Suportados.**
*   **Contras:**
    *   **NÃO é um Provedor de Identidade (IdP) Completo:** Ele **depende inteiramente de um IdP externo** para realizar a autenticação do usuário. Ele não gerencia usuários, senhas ou métodos 2FA por si só.
    *   **Funcionalidades de Autorização Limitadas:** Seu foco principal é na autenticação. Embora possa passar informações de grupo em headers (que a aplicação backend teria que interpretar), ele não tem um sistema de políticas de autorização tão rico quanto Authelia, Keycloak ou Pomerium.
    *   **Menos "Portal de Usuário" que Authelia:** Não oferece um portal para o usuário gerenciar seus logins ou 2FA (isso é feito no IdP externo).
*   **Quando Considerar `oauth2-proxy` para Homelab?**
    *   Se você já utiliza um Provedor de Identidade (IdP) OIDC/OAuth2 (como Google, GitHub, ou um Keycloak/Authentik auto-hospedado) e quer **proteger rapidamente uma aplicação interna simples** que não tem seu próprio sistema de login ou não suporta OIDC/SAML nativamente.
    *   Pode ser usado em conjunto com Traefik, onde Traefik roteia para `oauth2-proxy`, e `oauth2-proxy` então (após autenticação) roteia para a aplicação backend.

## Conclusão da Escolha da Ferramenta de Autenticação: Por que Authelia para Este Guia?

Para a arquitetura de servidor doméstico detalhada neste guia, **Authelia** foi escolhido como a solução de autenticação e 2FA porque ele atinge um excelente "ponto ideal" ("sweet spot") para as necessidades típicas de um homelab:

*   **Simplicidade Relativa para o Caso de Uso Principal:** Para o objetivo primário de adicionar uma camada de autenticação forte (com 2FA) e controle de acesso básico a um conjunto de serviços web que já estão atrás de um proxy reverso como Traefik, a configuração e o gerenciamento do Authelia são considerados mais diretos do que configurar um IdP completo como Keycloak ou Authentik.
*   **Integração Direta e Eficaz com Traefik:** O modelo de "forward authentication" do Authelia é muito conveniente e funciona perfeitamente com o middleware `ForwardAuth` do Traefik.
*   **Leveza e Eficiência de Recursos:** Authelia é relativamente leve e não consome tantos recursos do sistema (CPU/RAM) quanto um IdP Java completo como Keycloak, o que é uma consideração importante para um homelab com recursos limitados (mesmo com nossos 48GB, queremos usar os recursos de forma eficiente).
*   **Totalmente Auto-Hospedado e Open Source:** Mantém o controle total sobre o processo de autenticação e os dados dos usuários, alinhado com a filosofia de auto-hospedagem.
*   **Suporte Robusto a Métodos 2FA Modernos:** O suporte nativo para TOTP e, crucialmente, para **WebAuthn (FIDO2/Passkeys)** oferece opções de 2FA muito seguras e convenientes para os usuários.
*   **SSO Básico Eficaz:** Fornece uma experiência de Single Sign-On (SSO) coesa para todas as aplicações protegidas pela mesma instância do Authelia.

Se suas necessidades futuras evoluírem para:
*   Suporte robusto para protocolos de SSO mais complexos como **SAML 2.0**.
*   Atuar como um **Provedor OpenID Connect (IdP) completo** para muitas aplicações clientes OIDC.
*   **Federação de identidades** com múltiplos provedores externos (LDAP, Active Directory, IdPs sociais).
*   Um **gerenciamento de usuários, grupos e roles muito mais avançado** através de uma interface de administração web.
Então, migrar ou adicionar uma solução como **Keycloak** ou **Authentik** ao seu homelab seria o próximo passo lógico a ser explorado. Eles são significativamente mais poderosos como plataformas IAM completas, mas vêm com uma curva de aprendizado e requisitos de gerenciamento mais íngremes.