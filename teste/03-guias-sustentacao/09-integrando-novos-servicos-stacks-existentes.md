# Integrando Novos Serviços a Stacks Docker Existentes

Às vezes, em vez de criar uma stack Docker completamente nova para um único serviço, você pode querer adicionar um novo container a uma stack existente. Isso é comum para serviços "companion" ou quando vários pequenos serviços estão intimamente relacionados.

O processo envolve modificar o arquivo `docker-compose.yml` da stack existente e, em seguida, atualizar a stack via Portainer.

## Cenários Comuns

*   Adicionar um serviço de "companion" a uma aplicação principal (e.g., um tema para o Homer dashboard, um plugin que roda como container separado).
*   Adicionar um pequeno utilitário que trabalha em conjunto com outros serviços na mesma stack.
*   Consolidar vários microserviços relacionados em um único `docker-compose.yml` para gerenciamento simplificado.

## Passos para Adicionar um Novo Serviço a uma Stack Existente

1.  **Planejamento do Novo Serviço (Similar a adicionar uma nova stack):**
    *   **Imagem Docker:** Qual imagem e tag?
    *   **Recursos:** O novo serviço é leve o suficiente para não sobrecarregar a VM onde a stack existente roda?
    *   **Persistência de Dados:** Precisa de volumes? Se sim:
        *   Crie o subdiretório necessário no volume NFS apropriado (e.g., `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/nome_da_stack_existente/novo_servico/config`). Isso pode ser feito manualmente na VM ou via um playbook Ansible de "setup de volumes" para a stack existente.
        *   Adicione os novos caminhos de volume ao arquivo `.env` da stack existente (e.g., `/opt/portainer_stack_envs/stack_existente.env`) se você usa variáveis para caminhos no compose.
    *   **Configuração de Rede:**
        *   A quais redes da stack existente o novo serviço precisa se conectar? (`proxy`, `internal_services`, ou uma rede interna da stack).
        *   Precisa ser exposto via Traefik? Se sim, qual subdomínio?
    *   **Variáveis de Ambiente:** Quais são necessárias?

2.  **Modifique o Arquivo `docker-compose.yml` da Stack Existente:**
    *   Localize o arquivo `docker-compose.yml` da stack no seu projeto `infra-servidor-domestico/docker/stacks/nome_da_stack_existente/`.
    *   Abra-o em um editor de texto.
    *   **Adicione a Definição do Novo Serviço:**
        Na seção `services:`, adicione uma nova entrada para o seu novo serviço, seguindo a mesma estrutura dos serviços existentes.
        ```yaml
        # Exemplo: docker/stacks/minha_stack_existente/docker-compose.yml
        version: '3.9'

        networks:
          proxy:
            external: true
          internal_services:
            external: true
          # minha_rede_interna_da_stack: # Se a stack usa uma rede interna não externa

        services:
          servico_existente_1:
            # ... (config do serviço existente 1) ...

          servico_existente_2:
            # ... (config do serviço existente 2) ...

          # --- NOVO SERVIÇO ADICIONADO ---
          meu_novo_servico:
            image: usuario/imagem_novo_servico:tag
            container_name: container_novo_servico
            restart: unless-stopped
            networks: # Conecte às redes apropriadas
              - proxy # Se precisa ser exposto via Traefik
              - internal_services # Se precisa falar com outros serviços internos
              # - minha_rede_interna_da_stack # Se relevante
            volumes:
              - "${NOVOSERVICO_CONFIG_PATH_DA_STACK_EXISTENTE}:/config" # Use vars do .env da stack
            environment:
              - PUID=${DOCKER_PUID} # Herda do .env da stack
              - PGID=${DOCKER_PGID}
              - TZ=${SYSTEM_TIMEZONE}
              # - OUTRA_VAR_NOVO_SERVICO=${VALOR_NOVO_SERVICO} # Defina no .env da stack ou no Portainer
            labels: # Se precisar de Traefik
              traefik.enable: "true"
              traefik.http.routers.meunovoservico.rule: "Host(`novoservico.{{ base_domain }}`)"
              # ... (outras labels Traefik) ...
            depends_on: # Se depender de outros serviços na mesma stack
              - servico_existente_1
        ```
    *   **Verifique as Redes:** Se o novo serviço precisa de uma rede que não está listada na seção `networks:` de nível superior do compose (e não é `external: true`), você precisará defini-la ali.
    *   **Verifique as Variáveis de Ambiente:** Se o novo serviço usa variáveis de ambiente que não estão no arquivo `.env` da stack existente, você precisará:
        *   Adicioná-las ao arquivo `.env` da stack (e garantir que o Ansible o regenere se necessário).
        *   Ou adicioná-las manualmente na UI do Portainer ao atualizar a stack.

3.  **Atualize o Arquivo `.env` da Stack (se necessário):**
    *   Se você adicionou novos caminhos de volume ou variáveis não sensíveis para o novo serviço, edite o arquivo `.env` correspondente à stack na VM (e.g., `/opt/portainer_stack_envs/nome_da_stack_existente.env`).
    *   Se este arquivo `.env` é gerenciado pelo Ansible, atualize o playbook Ansible de "setup de volumes" para a stack existente para incluir as novas variáveis e execute-o.

4.  **Atualize a Stack via Portainer:**
    *   Acesse sua instância Portainer.
    *   Selecione o endpoint Docker correto.
    *   Vá para "Stacks".
    *   Localize a stack existente que você modificou e clique nela.
    *   Clique em "Editor".
    *   **Cole o conteúdo completo do `docker-compose.yml` atualizado.**
    *   **Variáveis de Ambiente:**
        *   Se você modificou o arquivo `.env` na VM, o Portainer *deveria* recarregá-lo automaticamente se você usou a opção "Load variables from .env file" originalmente. Para garantir, você pode re-especificar o caminho para o arquivo `.env`.
        *   Adicione manualmente quaisquer **novos secrets** (senhas, tokens API) para o novo serviço.
    *   Clique em "**Update the stack**".
        *   Certifique-se de que a opção "Re-pull image and redeploy" (ou similar) esteja marcada se você estiver usando uma nova imagem ou quer garantir que a imagem do novo serviço seja puxada. Portainer geralmente faz isso por padrão ao adicionar um novo serviço.
    *   Portainer irá comparar o novo compose com o estado atual e adicionar/modificar apenas o necessário. O novo serviço será criado e iniciado.

5.  **Configuração de DNS e Testes (se o novo serviço for exposto):**
    *   Se o novo serviço foi configurado com labels Traefik para ser exposto externamente, siga os passos de configuração de DNS na Cloudflare (CNAME ou Ingress Rule) como faria para uma nova stack (ver [Seção 03-guias-sustentacao/01-adicionando-novo-servico-docker.md](01-adicionando-novo-servico-docker.md#5-configuração-de-dns-cloudflare-se-exposto-externamente)).
    *   Acesse o novo serviço pelo seu subdomínio.
    *   Verifique os logs do novo container e dos serviços com os quais ele interage.

## Exemplo: Adicionando `phpMyAdmin` à Stack do Nextcloud (para gerenciar o DB do Nextcloud)

Suponha que você queira adicionar o phpMyAdmin para gerenciar o banco de dados PostgreSQL do seu Nextcloud, e ambos estão na stack `productivity-services` (ou `nextcloud-stack`).

1.  **Planejamento:**
    *   Imagem: `phpmyadmin/phpmyadmin:latest`.
    *   Recursos: Leve.
    *   Persistência: Nenhuma crítica para config, mas pode ter um volume para histórico de uploads.
    *   Rede: Precisa se conectar à rede `internal_services` para alcançar `nextcloud_db`. Será exposto via Traefik em `dbadmin.{{ base_domain }}` e protegido por Authelia.
    *   Variáveis: `PMA_HOST=nextcloud_db`, `PMA_PORT=5432` (para PostgreSQL, phpMyAdmin precisa de config adicional ou uma imagem diferente para suportar PostgreSQL nativamente. Este exemplo foca mais no processo de adicionar à stack. Para PostgreSQL, Adminer é uma alternativa mais simples).
        *   **Alternativa mais simples para PostgreSQL: Adminer**
            Imagem: `adminer:latest`
            Variáveis: Nenhuma específica, você insere os detalhes do DB na UI do Adminer.

2.  **Modificar `docker/stacks/productivity/docker-compose.yml`:**
    Adicione o serviço Adminer:
    ```yaml
    # ... (serviços nextcloud_db, nextcloud_redis, nextcloud_app) ...

      adminer: # Novo serviço para gerenciamento de DB
        image: adminer:latest # Imagem oficial do Adminer
        container_name: adminer_nextcloud
        restart: unless-stopped
        networks:
          - proxy # Para ser acessado via Traefik
          - internal_services # Para alcançar nextcloud_db
        environment:
          - ADMINER_DEFAULT_SERVER=nextcloud_db # Preenche o campo do servidor na UI
          # ADMINER_DESIGN: "nette" # Exemplo de tema
          # Não há PUID/PGID ou TZ críticos para Adminer em si
        labels:
          traefik.enable: "true"
          traefik.http.routers.adminer_nextcloud.rule: "Host(`dbadmin.{{ base_domain }}`)"
          traefik.http.routers.adminer_nextcloud.entrypoints: "websecure"
          traefik.http.routers.adminer_nextcloud.tls.certresolver: "letsencrypt"
          traefik.http.routers.adminer_nextcloud.middlewares: "authelia@docker" # Protegido!
          traefik.http.services.adminer_nextcloud.loadbalancer.server.port: "8080" # Porta interna do Adminer
    ```

3.  **Atualizar Arquivo `.env` da Stack:**
    Neste caso, Adminer não introduz novas variáveis de caminho ou PUID/PGID críticas que precisem ir para o `.env` da stack `productivity`.

4.  **Atualizar Stack no Portainer:**
    *   Vá para a stack `productivity-services`.
    *   Editor -> Cole o `docker-compose.yml` atualizado.
    *   Variáveis de Ambiente: Não há novos secrets para Adminer.
    *   Clique em "Update the stack".

5.  **DNS e Testes:**
    *   Configure CNAME `dbadmin` para o túnel Cloudflare (se não coberto por wildcard).
    *   Acesse `https://dbadmin.{{ base_domain }}`. Autentique com Authelia.
    *   Na UI do Adminer:
        *   Sistema: PostgreSQL
        *   Servidor: `nextcloud_db` (nome do serviço Docker)
        *   Usuário: `nextcloud`
        *   Senha: A senha do DB do Nextcloud (`{{ nextcloud_db_password }}` do seu vault)
        *   Banco de dados: `nextcloud`
    *   Você deve conseguir se conectar e gerenciar o banco de dados do Nextcloud.

Este processo permite que você expanda funcionalmente suas stacks existentes de maneira controlada.