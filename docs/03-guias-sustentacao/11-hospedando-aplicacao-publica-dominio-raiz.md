# Hospedando uma Aplicação Pública no Domínio Raiz (e.g., Blog)

Você pode desejar hospedar uma aplicação publicamente acessível diretamente no seu domínio raiz (e.g., `https://seudominio.com` em vez de `https://blog.seudominio.com`), como um blog pessoal, um portfólio ou uma landing page. Isso é totalmente possível com a nossa arquitetura, mas requer algumas considerações de segurança e configuração no Traefik.

## 1. Riscos Potenciais e Mitigações

Hospedar uma aplicação pública, especialmente no domínio raiz, introduz alguns riscos que precisam ser gerenciados, mesmo com o Cloudflare Tunnel e Traefik:

*   **Vulnerabilidades na Aplicação do Blog:**
    *   **Risco:** Se o software do seu blog (e.g., WordPress, Ghost, Hugo com um servidor web) tiver uma vulnerabilidade (XSS, SQLi, RCE), um invasor poderia explorá-la. Se o container do blog estiver mal configurado ou rodar com privilégios excessivos, isso poderia levar a um comprometimento mais amplo da VM ou até mesmo (em cenários extremos e com outras falhas de segurança) do host.
    *   **Mitigação:**
        *   **Escolha um Software de Blog Seguro e Bem Mantido:** Use plataformas conhecidas e mantenha-as **sempre atualizadas** com os últimos patches de segurança.
        *   **Blogs Estáticos (Hugo, Jekyll, Pelican):** São inerentemente mais seguros, pois geram arquivos HTML estáticos. Você só precisa de um servidor web simples (como Nginx ou Caddy) para servi-los. A superfície de ataque é mínima.
        *   **Containers com Menor Privilégio:** Rode o container do blog com um usuário não-root (PUID/PGID) sempre que possível.
        *   **Volumes com Permissões Restritas:** Garanta que o container só tenha permissão de escrita nos diretórios que ele realmente precisa (e.g., uploads), e leitura no resto.
        *   **Atualizações Regulares da Imagem Docker:** Use Watchtower ou atualize manualmente a imagem Docker do seu blog/servidor web.
*   **Exposição da Lógica do Proxy Reverso:**
    *   **Risco:** Se houver falhas na configuração do Traefik para o domínio raiz, isso poderia acidentalmente expor outros serviços ou o dashboard do Traefik se não estiverem protegidos corretamente.
    *   **Mitigação:**
        *   **Regras Traefik Específicas:** Crie uma regra de roteador no Traefik muito específica para o domínio raiz (`Host(`seudominio.com`)`).
        *   **Prioridade de Roteadores (se necessário):** Se você tiver outras regras wildcard (`HostS(`*.seudominio.com`)`), certifique-se de que a regra do domínio raiz tenha uma prioridade mais alta para ser correspondida primeiro.
        *   **NÃO aplicar o middleware Authelia** ao roteador do blog público, a menos que partes dele exijam login (o que é incomum para um blog principal).
*   **Ataques DDoS ou de Negação de Serviço na Aplicação do Blog:**
    *   **Risco:** Um ataque direcionado ao seu blog poderia consumir recursos do seu servidor (CPU, RAM, banda da internet).
    *   **Mitigação:**
        *   **Cloudflare:** A camada da Cloudflare já oferece uma boa proteção contra DDoS.
        *   **Rate Limiting no Traefik (Opcional):** Você pode adicionar um middleware de rate limiting ao roteador do blog no Traefik para limitar o número de requisições de um único IP.
        *   **Cache (Cloudflare ou Servidor Web):** Para blogs estáticos ou com conteúdo que não muda frequentemente, configurar cache na Cloudflare ou no servidor web pode reduzir significativamente a carga no seu backend.
*   **Consumo de Recursos:**
    *   **Risco:** Um blog popular pode consumir uma quantidade significativa de recursos da sua `core-services-vm`.
    *   **Mitigação:**
        *   **Blogs Estáticos:** Novamente, a melhor opção para baixo consumo de recursos.
        *   **Monitoramento:** Monitore o uso de CPU/RAM da VM e do container do blog.
        *   **Otimização da Aplicação do Blog:** Use plugins de cache, otimize imagens, etc.

!!! success "Cloudflare Tunnel Ajuda Muito"
    Lembre-se que o Cloudflare Tunnel já mitiga um grande risco: a exposição do seu IP público e a necessidade de abrir portas. Isso significa que ataques de varredura de portas ou explorações diretas contra seu IP são prevenidos.

## 2. Melhor Forma de Hospedar uma Aplicação Aberta (Blog Estático é Ideal)

Para um blog público no domínio raiz com foco em segurança e baixo consumo de recursos, a **melhor abordagem é usar um gerador de sites estáticos** como Hugo, Jekyll, Pelican, Eleventy, etc.

### Vantagens de um Blog Estático:

*   **Segurança Máxima:** São apenas arquivos HTML, CSS e JavaScript. Não há banco de dados ou código do lado do servidor para ser explorado na camada da aplicação do blog em si.
*   **Performance Excelente:** Arquivos estáticos são servidos muito rapidamente.
*   **Baixo Consumo de Recursos:** Um servidor web simples para arquivos estáticos (como Nginx ou Caddy em um container Docker) consome recursos mínimos.
*   **Escalabilidade Fácil (com Cache):** Cloudflare pode armazenar em cache seu site inteiro, reduzindo ainda mais a carga no seu servidor.
*   **Versionamento com Git:** O conteúdo do seu blog (arquivos Markdown) pode ser facilmente versionado com Git.

### Fluxo de Trabalho para um Blog Estático (Exemplo com Hugo e Nginx):

1.  **Desenvolvimento Local:**
    *   Instale Hugo (ou outro gerador) na sua máquina local.
    *   Crie seu site, escreva posts em Markdown.
    *   Use `hugo server -D` para visualização local.
    *   Quando estiver pronto, gere os arquivos estáticos: `hugo -D` (isso cria um diretório `public/` com o site).
2.  **Disponibilizar os Arquivos Estáticos para o Servidor:**
    *   **Opção A (Git + CI/CD Simples):**
        1.  Commite o código fonte do seu blog (arquivos Markdown, temas) para um repositório Git.
        2.  Configure um pipeline de CI/CD simples (e.g., GitHub Actions, GitLab CI) que:
            *   Roda o comando `hugo` para construir o site.
            *   Copia os arquivos do diretório `public/` para um volume NFS que o container Nginx no seu servidor acessa (e.g., `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/meu_blog_estatico/html/`).
    *   **Opção B (Sincronização Manual/Rsync):**
        1.  Após construir o site localmente, use `rsync` para copiar o conteúdo do diretório `public/` para o volume NFS apropriado na sua `core-services-vm`.
3.  **Servidor Web (Nginx em Docker):**
    *   Crie um `docker-compose.yml` para um container Nginx que sirva os arquivos do volume NFS.

    ```yaml
    # docker/stacks/blog_estatico/docker-compose.yml
    version: '3.9'
    networks: { proxy: { external: true } }
    services:
      meu_blog_nginx:
        image: nginx:alpine # Imagem leve do Nginx
        container_name: meu_blog_estatico_nginx
        restart: unless-stopped
        networks: [proxy]
        volumes:
          # Mapeia o diretório com os arquivos HTML estáticos do blog
          - "${MEU_BLOG_ESTATICO_HTML_PATH}:/usr/share/nginx/html:ro" # :ro pois Nginx só precisa ler
          # Opcional: Mapear um arquivo de configuração Nginx customizado se necessário
          # - "${MEU_BLOG_ESTATICO_NGINX_CONF_PATH}/default.conf:/etc/nginx/conf.d/default.conf:ro"
        environment:
          - PUID=${DOCKER_PUID} # Embora Nginx geralmente rode como root e depois drope para nginx user
          - PGID=${DOCKER_PGID}
          - TZ=${SYSTEM_TIMEZONE}
        labels:
          traefik.enable: "true"
          # Roteador para o domínio raiz
          traefik.http.routers.meu_blog_raiz.rule: "Host(`{{ base_domain }}`)"
          traefik.http.routers.meu_blog_raiz.entrypoints: "websecure"
          traefik.http.routers.meu_blog_raiz.tls.certresolver: "letsencrypt"
          # Opcional: Prioridade para garantir que esta regra seja correspondida antes de um wildcard
          traefik.http.routers.meu_blog_raiz.priority: "100"
          # NÃO adicionar middleware Authelia aqui para um blog público
          # traefik.http.routers.meu_blog_raiz.middlewares: "securityHeaders@file" # Apenas headers de segurança globais
          traefik.http.services.meu_blog_raiz.loadbalancer.server.port: "80" # Nginx escuta na porta 80 dentro do container
    ```
    *   **Preparação Ansible:** Crie um `setup-blog-estatico-volumes.yml` para criar o diretório NFS (e.g., `.../meu_blog_estatico/html/`) e o arquivo `/opt/portainer_stack_envs/blog_estatico.env` com `MEU_BLOG_ESTATICO_HTML_PATH`.
    *   **Deploy via Portainer:** Implante a stack.

## 3. Configurando Traefik para o Domínio Raiz

Seja um blog estático ou uma aplicação dinâmica (como WordPress, Ghost), você precisará de uma regra Traefik para o seu domínio raiz.

*   **Roteador Específico:**
    No `docker-compose.yml` do seu blog ou do servidor web que o serve, adicione labels Traefik para o domínio raiz:
    ```yaml
    labels:
      traefik.enable: "true"
      traefik.http.routers.meu_blog_raiz.rule: "Host(`{{ base_domain }}`)" # Sem www ou subdomínio
      # Opcionalmente, para cobrir www também, se você quer que www redirecione para o raiz ou sirva o mesmo:
      # traefik.http.routers.meu_blog_raiz_www.rule: "Host(`www.{{ base_domain }}`)"
      # E então você pode usar um middleware de redirecionamento ou servir o mesmo serviço.
      # Para um blog simples, focar no domínio raiz é mais fácil.
      traefik.http.routers.meu_blog_raiz.entrypoints: "websecure"
      traefik.http.routers.meu_blog_raiz.tls.certresolver: "letsencrypt"
      # Defina uma prioridade alta se você tiver outras regras wildcard (e.g., para *.{{ base_domain }})
      # para garantir que esta regra mais específica seja correspondida primeiro.
      traefik.http.routers.meu_blog_raiz.priority: "100" # Um número alto significa maior prioridade
      # Middlewares: NÃO inclua 'authelia@docker' para um blog público.
      # Você PODE incluir seus headers de segurança globais, se apropriado.
      traefik.http.routers.meu_blog_raiz.middlewares: "securityHeaders@file"
      traefik.http.services.meu_blog_raiz.loadbalancer.server.port: "80" # Ou a porta interna do seu app de blog
    ```
*   **Redirecionamento de `www` para não-`www` (ou vice-versa) - Opcional:**
    Se você quer que `www.seudominio.com` redirecione para `seudominio.com` (ou o contrário), você pode configurar um middleware de redirecionamento no Traefik.
    ```yaml
    # Exemplo de labels para redirecionar www para não-www (adicione ao serviço do blog)
    labels:
      # ... labels do blog raiz (Host(`seudominio.com`)) ...

      # Middleware para redirecionamento
      traefik.http.middlewares.redirect-www-to-nonwww.redirectregex.regex: "^https://www\\.(.*)"
      traefik.http.middlewares.redirect-www-to-nonwww.redirectregex.replacement: "https://$${1}" # $$ para escapar $
      traefik.http.middlewares.redirect-www-to-nonwww.redirectregex.permanent: "true"

      # Roteador para www que usa o middleware de redirecionamento
      traefik.http.routers.blog_www_redirect.rule: "Host(`www.{{ base_domain }}`)"
      traefik.http.routers.blog_www_redirect.entrypoints: "websecure"
      traefik.http.routers.blog_www_redirect.tls.certresolver: "letsencrypt"
      traefik.http.routers.blog_www_redirect.middlewares: "redirect-www-to-nonwww@docker"
      # Este roteador não precisa de um 'service' pois apenas redireciona.
      # Traefik v2.10+ pode precisar de um service dummy:
      traefik.http.routers.blog_www_redirect.service: "noop@internal"
    ```

## 4. Se Usar uma Aplicação de Blog Dinâmica (WordPress, Ghost)

Se você optar por um blog dinâmico:

*   **Siga as Melhores Práticas de Segurança para Aquela Plataforma:**
    *   Mantenha o core, temas e plugins **sempre atualizados**.
    *   Use senhas fortes para o admin.
    *   Considere plugins de segurança (e.g., Wordfence para WordPress).
    *   Limite as tentativas de login.
*   **Backup Regular do Banco de Dados e Arquivos:** Essencial.
*   **Recursos:** Aplicações dinâmicas consomem mais CPU, RAM e I/O do que sites estáticos. Monitore de perto.
*   **Docker Compose:** Incluirá o container da aplicação do blog e seu banco de dados (se não usar um DB compartilhado). As labels Traefik seriam similares às do exemplo do Nginx.

## Conclusão

Hospedar uma aplicação pública no domínio raiz, como um blog, é perfeitamente viável e seguro com a arquitetura baseada em Cloudflare Tunnel e Traefik, **especialmente se você optar por um gerador de sites estáticos.**

**Principais Recomendações:**

1.  **Prefira Blogs Estáticos:** Para máxima segurança e performance com o mínimo de recursos.
2.  **Mantenha Tudo Atualizado:** O software do blog, o servidor web, o Docker, o SO da VM.
3.  **Regra Traefik Específica:** Crie um roteador dedicado para o domínio raiz, sem Authelia (a menos que partes do blog sejam privadas).
4.  **Monitore:** Acompanhe os logs e o consumo de recursos.
5.  **Cloudflare Protege:** Aproveite as proteções DDoS e WAF da Cloudflare.

Ao seguir estas diretrizes, você pode compartilhar seu conteúdo com o mundo de forma segura e eficiente a partir do seu próprio servidor doméstico.