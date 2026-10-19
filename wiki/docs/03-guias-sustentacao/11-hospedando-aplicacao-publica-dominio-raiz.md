---
description: "Como publicar uma aplicação (ex.: blog) no domínio raiz com Cloudflare Tunnel e Traefik, sem passar pelo Authelia."
---

# Hospedando uma Aplicação Pública no Domínio Raiz (e.g., Blog)

Em muitos casos, você pode desejar hospedar uma aplicação que seja publicamente acessível diretamente no seu domínio raiz (apex domain), por exemplo, `https://meudominio.com`, em vez de um subdomínio como `https://blog.meudominio.com`. Um caso de uso comum para isso é um blog pessoal, um site de portfólio, ou uma landing page.

Isso é totalmente possível com a nossa arquitetura existente (Cloudflare Tunnel + Traefik), mas requer algumas considerações específicas de segurança e configuração no Traefik para garantir que apenas a aplicação desejada seja exposta no domínio raiz, sem comprometer outros serviços ou a segurança geral.

## 1. Riscos Potenciais e Mitigações ao Expor no Domínio Raiz

Hospedar uma aplicação publicamente, especialmente no domínio raiz que é frequentemente o "rosto" da sua presença online, introduz alguns riscos que precisam ser gerenciados, mesmo com as camadas de proteção que já temos:

*   **Vulnerabilidades na Aplicação Pública (e.g., Software de Blog):**
    *   **Risco:** Se o software da sua aplicação pública (seja um CMS como WordPress, Ghost, ou um servidor web para um site estático) tiver uma vulnerabilidade (XSS, SQL Injection, Remote Code Execution, etc.), um invasor poderia explorá-la. Se o container Docker que hospeda esta aplicação estiver mal configurado, rodar com privilégios excessivos, ou se houver outras falhas de segurança, isso poderia, em teoria, levar a um comprometimento da VM ou, em cenários extremos, do host.
    *   **Mitigações:**
        1.  **Escolha um Software Seguro e Mantenha-o ATUALIZADO:** Use plataformas de blog ou CMS conhecidos e bem mantidos. **Aplique patches de segurança e atualizações de versão rigorosamente e o mais rápido possível.**
        2.  **Priorize Sites Estáticos (Hugo, Jekyll, Pelican, Eleventy):** Esta é a **opção mais segura** para um blog ou site público. Eles geram arquivos HTML, CSS e JavaScript estáticos. A única coisa que você precisa é de um servidor web simples (como Nginx ou Caddy rodando em um container Docker) para servir esses arquivos. A superfície de ataque na camada da aplicação do blog em si é mínima ou inexistente.
        3.  **Containers com Menor Privilégio:** Se usar uma aplicação dinâmica, tente rodar o container com um usuário não-root (configurando `PUID`/`PGID`) sempre que possível.
        4.  **Volumes com Permissões Restritas:** Garanta que o container da aplicação pública só tenha permissão de escrita nos diretórios que ele realmente precisa (e.g., um diretório de uploads, se houver), e permissão de leitura no resto.
        5.  **Atualizações Regulares da Imagem Docker:** O Diun avisa quando sai versão nova da imagem; atualize a imagem Docker do seu blog/servidor web manualmente e com regularidade.
        6.  **Web Application Firewall (WAF):** A Cloudflare já oferece um WAF básico. Para aplicações dinâmicas como WordPress, considere habilitar e configurar o conjunto de regras gerenciadas da Cloudflare ou regras específicas para WordPress para bloquear ataques comuns.

*   **Exposição da Lógica do Proxy Reverso (Traefik):**
    *   **Risco:** Uma configuração incorreta no Traefik para o domínio raiz poderia acidentalmente expor outros serviços internos que não deveriam ser públicos, ou até mesmo o dashboard do Traefik se não estiver protegido corretamente por Authelia.
    *   **Mitigação:**
        1.  **Regra de Roteador Traefik Muito Específica:** Crie uma regra de roteador no Traefik **exclusivamente** para o domínio raiz (e.g., `Host(\`meudominio.com\`)`).
        2.  **Prioridade de Roteadores:** Se você tiver outras regras mais genéricas (como um wildcard `HostS(\`*.meudominio.com\`)` para Authelia), certifique-se de que a regra do domínio raiz tenha uma **prioridade mais alta** (um número maior no Traefik) para ser correspondida primeiro, evitando que a regra wildcard "capture" o tráfego do domínio raiz indevidamente.
        3.  **NÃO Aplicar Authelia ao Blog Público:** A menos que partes específicas do seu blog público exijam login (o que é incomum para a página principal de um blog), **não** aplique o middleware `authelia-forwardauth@docker` ao roteador do Traefik para o seu domínio raiz. Aplique apenas middlewares essenciais, como os de headers de segurança.

*   **Ataques de Negação de Serviço (DDoS) ou Abuso na Aplicação Pública:**
    *   **Risco:** Um ataque direcionado à sua aplicação no domínio raiz poderia consumir recursos do seu servidor (CPU, RAM, largura de banda da sua conexão de internet).
    *   **Mitigação:**
        1.  **Cloudflare:** A camada da Cloudflare é sua primeira linha de defesa e oferece excelente proteção contra a maioria dos ataques DDoS.
        2.  **Rate Limiting no Traefik (Opcional, Avançado):** Configure um middleware `RateLimit` no Traefik para o roteador. Veja a [Referência Rápida](../05-referencia-rapida.md).
        3.  **Cache (Cloudflare e/ou Servidor Web):** Para blogs estáticos ou conteúdo que não muda frequentemente, configure o cache agressivamente na Cloudflare ("Cache Everything" com page rules, se apropriado) e/ou no seu servidor web (Nginx/Caddy). Isso reduz drasticamente a carga no seu backend e melhora a velocidade para os visitantes.

*   **Consumo de Recursos do Servidor:**
    *   **Risco:** Uma aplicação pública popular, especialmente se for dinâmica (como WordPress com muitos plugins), pode consumir uma quantidade significativa de recursos da sua `core-services-vm`.
    *   **Mitigação:**
        1.  **Sites Estáticos:** Novamente, a melhor opção para baixo consumo de recursos.
        2.  **Monitoramento Contínuo:** Use Grafana/Prometheus para acompanhar o uso de CPU, RAM e I/O.
        3.  **Otimização da Aplicação:** Se usar um CMS dinâmico, utilize plugins de cache (e.g., WP Super Cache para WordPress), otimize imagens, minimize CSS/JS, e use um bom tema leve.

!!! success "Vantagens do Cloudflare Tunnel Persistem"
    É crucial lembrar que, mesmo expondo uma aplicação no domínio raiz, o **Cloudflare Tunnel continua protegendo seu endereço IP público e eliminando a necessidade de abrir portas no seu roteador.** Isso mitiga uma classe inteira de ataques diretos à sua rede.

## 2. Melhor Abordagem: Blog Estático (Hugo, Jekyll, etc.) + Servidor Web Leve

Para máxima segurança, performance e mínimo consumo de recursos ao hospedar uma aplicação pública no seu domínio raiz (como um blog pessoal), a **abordagem mais recomendada é usar um Gerador de Sites Estáticos (SSG)**.

*   **Geradores Populares:** Hugo (Go), Jekyll (Ruby), Pelican (Python), Eleventy (JavaScript), Gatsby (React), Next.js (React, pode gerar estático).
*   **Vantagens Detalhadas:**
    *   **Segurança Inerente:** O output são apenas arquivos HTML, CSS e JavaScript. Não há banco de dados do lado do servidor para ser atacado, nem código de servidor complexo (como PHP do WordPress) que possa ter vulnerabilidades na camada da aplicação do blog em si. A única "aplicação" rodando é um servidor web simples.
    *   **Performance Excepcional:** Servir arquivos estáticos é extremamente rápido.
    *   **Baixo Consumo de Recursos:** Um servidor web como Nginx ou Caddy para servir arquivos estáticos é muito leve em CPU e RAM.
    *   **Escalabilidade com Cache:** Ideal para caching na Cloudflare, o que pode fazer seu site resistir a picos de tráfego com carga mínima no seu servidor.
    *   **Versionamento Fácil com Git:** O conteúdo do seu blog (geralmente arquivos Markdown) e o código do seu site estático podem ser facilmente versionados com Git.

### Fluxo de Trabalho Típico para um Blog Estático (Exemplo com Hugo e Nginx Docker):

1.  **Desenvolvimento Local do Blog:**
    *   Instale o gerador de site estático escolhido (e.g., Hugo) na sua máquina de desenvolvimento local.
    *   Crie seu site, escreva seus posts (geralmente em Markdown), personalize o tema.
    *   Use o comando de servidor de desenvolvimento do seu SSG para visualização local (e.g., `hugo server -D` para Hugo, que roda um servidor web local para preview).
    *   Quando estiver satisfeito, gere os arquivos estáticos finais do site. Para Hugo, o comando é `hugo` (ou `hugo -D` para incluir rascunhos). Isso geralmente cria um diretório `public/` (ou `_site/`, `dist/`) contendo todos os arquivos HTML, CSS, JS e assets do seu site.

2.  **Disponibilizar os Arquivos Estáticos para o Servidor Docker:**
    Você precisa transferir o conteúdo do seu diretório de build estático (e.g., `public/`) para um local que o container Nginx no seu servidor possa acessar. Este local será um volume NFS.
    *   **Opção A (Preferencial para Automação): Git + CI/CD Simples (e.g., GitHub Actions, GitLab CI):**
        1.  Mantenha o código fonte do seu blog (arquivos Markdown, tema, configuração do SSG) em um repositório Git (e.g., no GitHub/GitLab).
        2.  Configure um pipeline de CI/CD simples no seu provedor Git que, a cada `push` para a branch principal:
            *   Faz checkout do código.
            *   Instala o SSG (e.g., Hugo).
            *   Roda o comando de build do SSG (e.g., `hugo`).
            *   **Sincroniza/Copia** o conteúdo do diretório de build (e.g., `public/`) para o volume NFS no seu servidor. Isso pode ser feito com `rsync` sobre SSH para a `core-services-vm` (que monta o NFS), ou usando outras ferramentas de deploy.
                *   O diretório de destino no NFS seria algo como: `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/meu_blog_raiz/html/`.
    *   **Opção B (Manual ou Script Local): Sincronização com `rsync`:**
        1.  Após construir o site localmente com seu SSG (e.g., `hugo`), use `rsync` para copiar o conteúdo do diretório de build (e.g., `public/`) para a `core-services-vm` no caminho NFS apropriado.
            ```bash
            # Exemplo, execute na sua máquina local após construir com Hugo
            # Assumindo que você tem acesso SSH à core-services-vm como vm_ansible_user
            # e que o playbook setup-blog-raiz-volumes.yml criou o diretório de destino.
            rsync -avz --delete public/ {{ vm_ansible_user_name }}@{{ core_services_vm_ip_var }}:{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/meu_blog_raiz/html/
            ```

3.  **Servidor Web Nginx (ou Caddy) em Docker para Servir os Arquivos:**
    *   Crie um arquivo `docker-compose.yml` para um container Nginx que sirva os arquivos estáticos do volume NFS.

        ```yaml
        # home-server/docker/stacks/blog_raiz/docker-compose.yml
        version: '3.9'

        networks:
          proxy: # Para ser acessado via Traefik
            external: true

        services:
          meu_blog_nginx:
            image: nginx:1.25-alpine # Imagem oficial e leve do Nginx. Verifique a tag mais recente.
            container_name: meu_blog_raiz_nginx
            restart: unless-stopped
            networks:
              - proxy
            volumes:
              # Mapeia o diretório NFS (na VM) com os arquivos HTML estáticos do blog
              # para o diretório raiz do Nginx dentro do container.
              # Use :ro (read-only) pois o Nginx só precisa ler esses arquivos.
              - "${BLOG_RAIZ_HTML_PATH}:/usr/share/nginx/html:ro"
              # Opcional: Se você precisar de uma configuração Nginx customizada (e.g., para headers, redirects),
              # você pode mapear um arquivo default.conf. Caso contrário, o Nginx usará sua config padrão.
              # - "${BLOG_RAIZ_NGINX_CONF_PATH}/default.conf:/etc/nginx/conf.d/default.conf:ro"
            environment:
              # PUID/PGID geralmente não são críticos para Nginx servindo arquivos estáticos
              # se as permissões no volume NFS estiverem corretas para o usuário 'nginx' dentro do container.
              # Mas incluí-los por consistência se o seu .env os tiver.
              - PUID=${DOCKER_PUID}
              - PGID=${DOCKER_PGID}
              - TZ=${SYSTEM_TIMEZONE}
            labels:
              # --- Labels Traefik para o Domínio Raiz ---
              traefik.enable: "true"
              # Roteador para o domínio raiz (sem www)
              traefik.http.routers.meu_blog_raiz.rule: "Host(`{{ base_domain }}`)"
              traefik.http.routers.meu_blog_raiz.entrypoints: "websecure"
              traefik.http.routers.meu_blog_raiz.tls.certresolver: "letsencrypt"
              # Prioridade ALTA para garantir que esta regra mais específica (domínio raiz)
              # seja correspondida antes de quaisquer regras wildcard (e.g., para Authelia em *.{{ base_domain }}).
              traefik.http.routers.meu_blog_raiz.priority: "100" # Um número alto significa maior prioridade
              # Middlewares: NÃO inclua 'authelia-forwardauth@docker' para um blog público.
              # Você PODE (e deve) incluir seus headers de segurança globais.
              traefik.http.routers.meu_blog_raiz.middlewares: "securityHeaders@file"
              # Serviço Traefik (como Traefik se conecta ao container Nginx)
              traefik.http.services.meu_blog_raiz.loadbalancer.server.port: "80" # Nginx escuta na porta 80 dentro do container por padrão
        ```
    *   **Preparação Ansible:** Crie um playbook (e.g., `setup-blog-raiz-volumes.yml`) para:
        1.  Criar o diretório NFS na `core-services-vm` (e.g., `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/meu_blog_raiz/html/` e opcionalmente `.../meu_blog_raiz/nginx_conf/`).
        2.  Gerar o arquivo `/opt/portainer_stack_envs/blog_raiz.env` com as variáveis de caminho (e.g., `BLOG_RAIZ_HTML_PATH`).
    *   **Deploy via Portainer:** Siga o processo em [Deploy Core](../01-manual-implementacao/06-deploy-core.md) para stacks core, ou [Deploy de Apps](../01-manual-implementacao/07-deploy-apps.md) para stacks de aplicações.

## 3. Configurando o Traefik para o Domínio Raiz

Independentemente de você usar um blog estático ou uma aplicação dinâmica (como WordPress ou Ghost), você precisará de uma regra de roteador no Traefik específica para o seu domínio raiz (e.g., `meudominio.com`).

*   **Roteador Específico para o Domínio Raiz:**
    No `docker-compose.yml` do seu blog (ou do servidor web Nginx/Caddy que o serve), as labels Traefik são cruciais. Veja o exemplo do Nginx acima. Os pontos chave são:
    *   `traefik.http.routers.NOMEDOROUTEADOR.rule: "Host(\`{{ base_domain }}\`)"`
        *   Certifique-se de usar crases (`) em volta do valor da regra Host.
        *   Use seu `{{ base_domain }}` aqui (sem `www` ou outros subdomínios).
    *   `traefik.http.routers.NOMEDOROUTEADOR.priority: "100"` (ou outro número alto)
        *   Isso é importante se você tem outras regras mais genéricas (como uma regra wildcard `HostS(\`*.{{ base_domain }}\`)` que pode ser usada pelo Authelia ou outros serviços). A prioridade mais alta garante que a regra específica para o domínio raiz seja avaliada e correspondida primeiro.
    *   **Middlewares:**
        *   **NÃO inclua `authelia-forwardauth@docker`** para um blog ou site que deve ser publicamente acessível sem login.
        *   Você **DEVE** incluir seus middlewares de segurança globais (e.g., `securityHeaders@file`, que foi definido na [Seção 5.4](../01-manual-implementacao/05-rede-segura.md#templatessecurity_headersymlj2-middleware-de-segurança)) para aplicar headers de segurança importantes.
            Exemplo: `traefik.http.routers.meu_blog_raiz.middlewares: "securityHeaders@file"`

*   **Redirecionamento de `www` para não-`www` (ou vice-versa) - Opcional, mas Recomendado para SEO:**
    É uma boa prática escolher uma forma canônica para o seu domínio (com `www` ou sem `www`) e redirecionar a outra para ela. Suponha que você queira que `https://www.meudominio.com` redirecione para `https://meudominio.com`.
    Você pode configurar isso no Traefik usando um middleware de redirecionamento. Adicione estas labels ao serviço do seu blog (e.g., ao `meu_blog_nginx`):

    ```yaml
    # Adicionar estas labels ao serviço do seu blog no docker-compose.yml
    labels:
      # ... (labels existentes para Host(`seudominio.com`)) ...

      # --- Middleware para redirecionar www para não-www ---
      traefik.http.middlewares.redirect-www-to-nonwww.redirectregex.regex: "^https://www\\.(.*)" # Regex para capturar o domínio após www.
      traefik.http.middlewares.redirect-www-to-nonwww.redirectregex.replacement: "https://$${1}"     # Redireciona para https://dominio (sem www). $$ para escapar o $ para Docker Compose.
      traefik.http.middlewares.redirect-www-to-nonwww.redirectregex.permanent: "true"             # Usa redirecionamento 301 (permanente)

      # --- Roteador para www.seudominio.com que USA o middleware de redirecionamento ---
      traefik.http.routers.blog_www_redirect.rule: "Host(`www.{{ base_domain }}`)"
      traefik.http.routers.blog_www_redirect.entrypoints: "websecure"
      traefik.http.routers.blog_www_redirect.tls.certresolver: "letsencrypt"
      traefik.http.routers.blog_www_redirect.middlewares: "redirect-www-to-nonwww@docker"
      # Este roteador não precisa de um 'service' de backend, pois sua única função é redirecionar.
      # Para versões mais recentes do Traefik (v2.10+), pode ser necessário especificar um serviço "noop" (no operation):
      traefik.http.routers.blog_www_redirect.service: "noop@internal"
    ```
    E no seu DNS da Cloudflare, certifique-se de que tanto `seudominio.com` quanto `www.seudominio.com` apontam para o seu Cloudflare Tunnel (e.g., ambos como CNAMEs ou cobertos pela Ingress Rule do túnel).

## 4. Se Optar por uma Aplicação de Blog Dinâmica (WordPress, Ghost, etc.)

Se, apesar das recomendações de segurança e performance, você optar por uma aplicação de blog dinâmica no seu domínio raiz:

*   **Siga Rigorosamente as Melhores Práticas de Segurança para Aquela Plataforma Específica:**
    *   **WordPress:** Mantenha o core, temas e todos os plugins **SEMPRE atualizados**. Remova plugins e temas não utilizados. Use senhas de administrador extremamente fortes. Considere plugins de segurança robustos (e.g., Wordfence, Sucuri Scanner), configure limites de tentativa de login, 2FA para o admin do WordPress, e proteja o `wp-admin`.
    *   **Ghost:** Mantenha o Ghost atualizado. Siga as recomendações de segurança da documentação do Ghost.
*   **Backup Regular e Completo:** Para aplicações dinâmicas, isso inclui:
    *   O banco de dados da aplicação (MySQL/MariaDB para WordPress, SQLite para algumas configs do Ghost).
    *   Todos os arquivos da aplicação (especialmente o diretório `wp-content` do WordPress, ou o diretório `content` do Ghost).
    *   Use os [mecanismos de backup](../04-manutencao-recuperacao/02-backup-restore-estrategia.md) já discutidos.
*   **Recursos do Servidor:** Aplicações dinâmicas, especialmente WordPress com muitos plugins ou tráfego, consomem significativamente mais CPU, RAM e I/O de banco de dados do que sites estáticos. Monitore de perto.
*   **Docker Compose:** O `docker-compose.yml` para uma aplicação dinâmica geralmente inclui o container da aplicação principal e seu container de banco de dados (se não estiver usando um banco de dados compartilhado/externo). As labels Traefik para o domínio raiz seriam aplicadas ao container da aplicação principal, similar ao exemplo do Nginx.

## Conclusão

Hospedar uma aplicação pública, como um blog, diretamente no seu domínio raiz é uma tarefa comum e perfeitamente viável com a arquitetura que construímos, especialmente aproveitando a segurança do Cloudflare Tunnel e a flexibilidade do Traefik.

**Recomendações Chave para o Domínio Raiz:**

1.  **Priorize Sites Estáticos:** Para máxima segurança, performance e mínimo consumo de recursos, use um gerador de sites estáticos (Hugo, Jekyll, etc.) com um servidor web leve como Nginx ou Caddy.
2.  **Mantenha TUDO Atualizado:** O software da sua aplicação pública, o servidor web, o Docker, o SO da VM.
3.  **Regra Traefik Específica e com Alta Prioridade:** Crie um roteador dedicado no Traefik para o domínio raiz, **sem** o middleware Authelia (a menos que seja um portal que exija login).
4.  **Monitore Continuamente:** Acompanhe os logs da sua aplicação pública, do Traefik, e o consumo de recursos do servidor.
5.  **Aproveite as Proteções da Cloudflare:** Use o WAF e as opções de cache da Cloudflare para adicionar camadas extras de segurança e performance.

Ao seguir estas diretrizes, você pode compartilhar seu conteúdo ou sua aplicação principal com o mundo de forma segura e eficiente, diretamente do seu próprio servidor doméstico.