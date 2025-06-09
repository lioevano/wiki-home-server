# Alternativas para Servidores de Autenticação e Single Sign-On (SSO)

Para proteger o acesso aos nossos serviços web expostos, escolhemos **Authelia** como nosso portal de autenticação e provedor de segundo fator (2FA). Ele se integra bem com Traefik via forward authentication e oferece um bom equilíbrio entre funcionalidades e simplicidade para um homelab.

O mercado de soluções de autenticação e SSO é vasto, com opções que variam em complexidade e foco.

## 1. Authelia (Nossa Escolha)

*   **Tipo:** Servidor de autenticação e autorização open-source, focado em 2FA e políticas de acesso para aplicações web via proxy reverso.
*   **Prós:**
    *   **Leve e Simples de Configurar (Relativamente):** Para o conjunto de features que oferece, a configuração via YAML é gerenciável.
    *   **Excelente Integração com Proxies Reversos:** Projetado para funcionar com Traefik, Nginx (com `ngx_http_auth_request_module`), HAProxy, etc., usando o modelo de "forward authentication".
    *   **Suporte a Múltiplos Fatores:** TOTP (apps autenticadores), WebAuthn (FIDO2/Passkeys), Duo Push (requer conta Duo).
    *   **Políticas de Acesso Granulares:** Permite definir regras baseadas em domínio, path, rede, método, usuário, grupo.
    *   **Proteção contra Brute-Force:** Limita tentativas de login.
    *   **SSO Básico:** Uma vez logado no Authelia, o acesso a outros serviços protegidos pelo mesmo Authelia é transparente (dentro da validade da sessão).
    *   **Armazenamento Flexível:** Suporta backend de usuários em arquivo YAML ou banco de dados (SQLite, PostgreSQL, MySQL).
    *   **Open Source e Auto-Hospedado:** Controle total sobre seus dados de autenticação.
*   **Contras:**
    *   **Foco em Forward Auth:** Primariamente projetado para proteger aplicações web que podem ser colocadas atrás de um proxy reverso. A integração com aplicações que esperam protocolos de SSO mais complexos (SAML, OIDC Provider completo) é limitada ou inexistente nativamente (embora possa estar evoluindo).
    *   **Gerenciamento de Usuários:** Se não usar um backend externo como LDAP, o gerenciamento de muitos usuários pode ser manual (via DB ou `users_database.yml`).
    *   **Interface de Administração:** Historicamente, não possuía uma UI de administração completa (foco em config via YAML), mas isso pode estar mudando em versões mais recentes.

## 2. Keycloak

*   **Tipo:** Solução de Gerenciamento de Identidade e Acesso (IAM) open-source completa, desenvolvida pela Red Hat.
*   **Prós:**
    *   **Extremamente Poderoso e Rico em Funcionalidades:**
        *   Provedor de Identidade (IdP) completo.
        *   Suporte para múltiplos protocolos de SSO: OpenID Connect (OIDC), SAML 2.0, OAuth 2.0.
        *   Gerenciamento de usuários, grupos, roles, permissões.
        *   Federação de identidades (conectar com outros IdPs como Google, Facebook, LDAP, Active Directory).
        *   Autenticação de Múltiplos Fatores (TOTP, WebAuthn).
        *   Interface de administração web completa.
        *   Customização de temas para páginas de login.
        *   Políticas de senha, fluxos de autenticação customizáveis.
    *   **Padrão da Indústria:** Amplamente usado em ambientes corporativos e por aplicações que precisam de SSO robusto.
    *   **Boa Documentação e Comunidade.**
*   **Contras:**
    *   **Complexidade:** Significativamente mais complexo de configurar e gerenciar do que Authelia. Muitos conceitos para aprender.
    *   **Consumo de Recursos:** Geralmente requer mais RAM e CPU (roda em Java).
    *   **Overkill para Homelabs Simples:** Se você só precisa de 2FA para algumas aplicações web via proxy, Keycloak pode ser um exagero.
    *   **Integração com Proxy Reverso:** Embora possa proteger aplicações via OIDC/SAML, a integração no estilo "forward auth" simples do Authelia com Traefik não é seu principal modo de operação (embora existam adaptadores ou você possa usar algo como `oauth2-proxy` com Keycloak como backend OIDC).
*   **Quando Considerar:** Se você precisa de um IdP completo, suporte a SAML/OIDC para suas aplicações, federação de identidades, ou se está aprendendo para cenários empresariais.

## 3. Authentik

*   **Tipo:** Solução de Gerenciamento de Identidade e Acesso (IAM) open-source, similar ao Keycloak em escopo, mas com foco em uma experiência de usuário moderna e integração com "outposts" para diferentes tipos de aplicações.
*   **Prós:**
    *   **Funcionalidades Abrangentes:** Suporte a OIDC, SAML, LDAP, RADIUS.
    *   **Interface Moderna:** UI de administração e usuário bem projetada.
    *   **"Outposts":** Agentes que podem ser implantados para integrar Authentik com aplicações que não suportam OIDC/SAML nativamente (e.g., um outpost de proxy reverso, outpost LDAP).
    *   **Fluxos de Políticas/Autenticação Poderosos:** Altamente customizável.
    *   **MFA:** TOTP, WebAuthn, Duo, etc.
    *   **Comunidade Crescente.**
*   **Contras:**
    *   **Complexidade:** Assim como Keycloak, é uma solução IAM completa e tem uma curva de aprendizado.
    *   **Consumo de Recursos:** Pode ser mais pesado que Authelia.
    *   **Maturidade Relativa:** Mais novo que Keycloak, embora esteja evoluindo rapidamente.
*   **Quando Considerar:** Se você quer uma alternativa moderna ao Keycloak com um sistema de "outposts" interessante para integração.

## 4. Pomerium

*   **Tipo:** Um proxy reverso sensível à identidade, open-source. Ele *é* o proxy e o ponto de aplicação de políticas de acesso.
*   **Como Funciona:** Você coloca o Pomerium na frente das suas aplicações. Pomerium se integra com seu Provedor de Identidade (IdP) existente (e.g., Google, Okta, Auth0, Keycloak, ou até mesmo um arquivo de usuários) para autenticar usuários e aplicar políticas de acesso baseadas na identidade.
*   **Prós:**
    *   **Segurança de Perímetro Forte (Zero Trust):** Projetado para acesso "além da VPN corporativa".
    *   **Context-Aware Access:** Políticas podem ser baseadas em identidade do usuário, dispositivo, geolocalização, etc.
    *   **Pode Funcionar com Diversos IdPs.**
    *   **Auditoria Detalhada.**
*   **Contras:**
    *   **Ele é o Proxy:** Diferente de Authelia que se integra *com* seu proxy existente (Traefik), Pomerium *substitui* ou atua como uma camada adicional de proxy. Isso pode simplificar ou complicar dependendo do seu setup.
    *   **Configuração:** Requer um IdP para se integrar (embora tenha um modo "bootstrap" com usuários em arquivo). A configuração das políticas pode ser complexa.
*   **Quando Considerar:** Se você está construindo uma arquitetura com foco em "Zero Trust Network Access" (ZTNA) e precisa de um proxy que aplique políticas de acesso baseadas em identidade de forma muito granular.

## 5. `oauth2-proxy`

*   **Tipo:** Um proxy reverso que fornece autenticação com Provedores OAuth2/OpenID Connect (e.g., Google, GitHub, Keycloak, Authelia se ele atuasse como IdP OIDC).
*   **Como Funciona:** Você coloca `oauth2-proxy` na frente da sua aplicação. Ele redireciona o usuário para o IdP para login. Se bem-sucedido, o IdP redireciona de volta para `oauth2-proxy`, que então permite o acesso à aplicação backend, passando informações do usuário (e.g., email, token) em headers.
*   **Prós:**
    *   **Simples para Adicionar SSO a Aplicações Existentes:** Se você já tem um IdP OIDC/OAuth2, é relativamente fácil proteger uma aplicação com `oauth2-proxy`.
    *   **Leve.**
*   **Contras:**
    *   **Não é um IdP Completo:** Ele depende de um IdP externo.
    *   **Funcionalidades Limitadas:** Focado na autenticação OAuth2/OIDC. Menos features de gerenciamento de usuários ou políticas complexas que Authelia ou Keycloak.
*   **Quando Considerar:** Se você já usa um IdP como Google, Okta, ou Keycloak e quer proteger rapidamente uma aplicação interna que não suporta esses protocolos nativamente, usando um proxy simples.

## Conclusão da Escolha: Authelia

**Authelia** foi escolhido para este guia porque:

*   **Simplicidade para o Caso de Uso:** Para um homelab onde o principal requisito é adicionar uma camada de 2FA e controle de acesso básico a serviços web atrás de Traefik, Authelia oferece um excelente equilíbrio entre funcionalidades e complexidade de configuração.
*   **Integração Direta com Traefik:** O modelo de "forward authentication" é muito conveniente com Traefik.
*   **Leveza:** Não consome tantos recursos quanto um IdP completo como Keycloak.
*   **Auto-Hospedado e Open Source:** Mantém o controle sobre a autenticação.
*   **Suporte a WebAuthn:** Oferece uma opção de 2FA moderna e segura.

Se suas necessidades evoluírem para SSO mais complexo entre muitas aplicações que suportam SAML/OIDC, ou se precisar de federação de identidades, então **Keycloak** ou **Authentik** seriam os próximos passos lógicos a serem explorados. Se o foco for um ZTNA com políticas de acesso muito granulares e você já tem um IdP, **Pomerium** é interessante.