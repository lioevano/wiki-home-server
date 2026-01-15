# Seção 11: Stack de Automação Low-Code com n8n

Bem-vindo à automação de próximo nível para o seu home server. Enquanto o Home Assistant é o rei da automação residencial e de dispositivos, o **n8n** (pronuncia-se "nodemation") se destaca como uma plataforma de automação de workflows de propósito geral. Ele permite conectar centenas de aplicações e serviços diferentes, tanto internos quanto externos, através de uma interface visual baseada em nós (nodes).

Com o n8n, você pode criar workflows complexos que reagem a eventos, processam dados e executam ações em múltiplos sistemas, tudo isso com pouca ou nenhuma necessidade de código. É a ferramenta perfeita para orquestrar tarefas que vão além do escopo do Home Assistant ou do Ansible.

**Casos de Uso para n8n no seu Home Server:**

*   **Notificações Inteligentes:** Crie um workflow que, ao receber um webhook de um dos seus serviços (ex: Uptime Kuma detecta um serviço offline), envia uma notificação detalhada para o Telegram, Discord e também cria um card em um quadro Kanban (como o do Nextcloud Deck).
*   **Sincronização de Conteúdo:** Monitore uma pasta no seu Nextcloud e, sempre que um novo arquivo for adicionado, envie-o para um serviço de OCR, salve o texto extraído em uma nota e, em seguida, use uma API de LLM (via LiteLLM) para resumi-lo.
*   **Gerenciamento de Mídia:** Quando um novo filme for adicionado à sua biblioteca Plex/Jellyfin (usando webhooks), busque informações adicionais sobre ele em APIs como a do IMDb/TMDb e atualize os metadados ou envie uma notificação para um grupo de amigos.
*   **Backups e Alertas:** Crie um workflow agendado que verifica o status dos seus backups ZFS e, em caso de falha, abre um chamado em uma ferramenta de gestão de projetos e envia um alerta crítico.

Nesta seção, vamos implantar o n8n como um container Docker na `core-services-vm`, integrá-lo ao nosso ecossistema seguro com Traefik e Authelia, e garantir que seus dados e workflows sejam persistidos de forma segura no nosso armazenamento ZFS.

## 11.1. Preparação com Ansible para a Stack n8n

Como de costume, o primeiro passo é usar o Ansible para preparar o ambiente na `core-services-vm`. O playbook irá criar os diretórios necessários no volume NFS e gerar o arquivo `.env` para a stack do n8n.

### Playbook `setup-n8n-volumes.yml`

Este novo playbook Ansible, a ser executado contra a `core-services-vm`, fará o seguinte:

1.  **Criação do Diretório de Configuração do n8n:**
    *   No dataset ZFS `docker-volumes` (montado em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/`), criará o subdiretório `.../n8n/config`.
    *   Este diretório armazenará todos os seus workflows, credenciais e configurações do n8n.
    *   As permissões serão definidas para `owner: {{ docker_puid }}` e `group: {{ docker_pgid }}` para garantir que o container do n8n tenha acesso de escrita.
2.  **Preparação do Arquivo `.env`:**
    *   Gerará o arquivo `/opt/portainer_stack_envs/n8n.env` na `core-services-vm`.
    *   Este arquivo conterá o caminho completo para o volume de configuração, PUID/PGID, fuso horário e outras variáveis necessárias para o deploy.

**Ação:** Crie e execute o playbook a partir da sua máquina de controle Ansible.

1.  **Crie o arquivo `ansible/playbooks/setup-n8n-volumes.yml`:**

    ```yaml
    # ansible/playbooks/setup-n8n-volumes.yml
    - name: Setup n8n Volumes and Environment
      hosts: core-services-vm
      become: true
      gather_facts: true
      vars_files:
        - ../vars/main.yml
        - ../vault.yml

      tasks:
        - name: "Create n8n config directory on NFS volume"
          ansible.builtin.file:
            path: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/n8n/config"
            state: directory
            owner: "{{ docker_puid }}"
            group: "{{ docker_pgid }}"
            mode: '0775'

        - name: "Generate .env file for n8n stack"
          ansible.builtin.template:
            src: ../templates/portainer_stack_env.j2
            dest: "/opt/portainer_stack_envs/n8n.env"
            owner: root
            group: root
            mode: '0644'
          vars:
            stack_name: "n8n"
            stack_configs:
              - { name: 'N8N_CONFIG_PATH', value: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/n8n/config" }
    ```

2.  **Execute o playbook:**

    ```bash
    ansible-playbook ansible/playbooks/setup-n8n-volumes.yml --ask-vault-pass
    ```

## 11.2. Deploy da Stack n8n via Portainer

Com o diretório e o arquivo `.env` prontos, podemos implantar o n8n.

### Docker Compose para n8n (`docker/stacks/automation/n8n-compose.yml`)

Crie o seguinte arquivo de Docker Compose. Ele define o serviço do n8n e o configura para trabalhar com nosso ambiente.

```yaml
# docker/stacks/automation/n8n-compose.yml
version: '3.9'

networks:
  proxy:
    name: proxy
    external: true

services:
  n8n:
    image: docker.n8n.io/n8nio/n8n:1.45.1 # Use uma tag de versão estável
    container_name: n8n_app
    restart: unless-stopped
    networks:
      - proxy
    volumes:
      - "${N8N_CONFIG_PATH}:/home/node/.n8n"
    environment:
      - N8N_HOST={{ n8n_subdomain }}.{{ base_domain }}
      - N8N_PROTOCOL=https
      - NODE_ENV=production
      - WEBHOOK_URL=https://{{ n8n_subdomain }}.{{ base_domain }}/
      - GENERIC_TIMEZONE=${SYSTEM_TIMEZONE}
      # Credenciais de admin para o n8n (defina no vault e passe como secret)
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=${N8N_ADMIN_USER_FROM_PORTAINER_ENV}
      - N8N_BASIC_AUTH_PASSWORD=${N8N_ADMIN_PASSWORD_FROM_PORTAINER_ENV}
    labels:
      traefik.enable: "true"
      traefik.http.routers.n8n.rule: "Host(`{{ n8n_subdomain }}.{{ base_domain }}`)"
      traefik.http.routers.n8n.entrypoints: "websecure"
      traefik.http.routers.n8n.tls.certresolver: "letsencrypt"
      traefik.http.routers.n8n.service: "n8n-svc"
      # Protegendo com Authelia para SSO e 2FA
      traefik.http.routers.n8n.middlewares: "authelia@docker"
      traefik.http.services.n8n-svc.loadbalancer.server.port: "5678"
```

**Pontos Chave do Compose:**

*   **Imagem:** Usamos a imagem oficial `docker.n8n.io/n8nio/n8n`.
*   **Volume:** O diretório de dados do n8n (`/home/node/.n8n` dentro do container) é mapeado para o caminho NFS que preparamos.
*   **Variáveis de Ambiente:**
    *   `N8N_HOST`, `N8N_PROTOCOL`, e `WEBHOOK_URL` são cruciais para que o n8n saiba seu próprio endereço público, o que é essencial para webhooks funcionarem corretamente.
    *   `N8N_BASIC_AUTH_...`: O n8n possui um sistema de autenticação de usuário embutido. Embora estejamos usando Authelia na frente, é uma boa prática de segurança em profundidade ter também a autenticação do próprio n8n ativa. Vamos armazenar essas credenciais no Ansible Vault.
*   **Labels Traefik:** Configuração padrão para expor o serviço via Traefik e protegê-lo com Authelia.

### Ação de Deploy

1.  **Adicione as novas variáveis ao Ansible Vault (`ansible/vault.yml`):**

    ```yaml
    # ...
    # --- n8n Admin Credentials ---
    n8n_admin_user: "admin"
    n8n_admin_password: "sua-senha-forte-e-segura-para-n8n"
    ```

2.  **Adicione o subdomínio ao `main.yml`:**

    ```yaml
    # ansible/vars/main.yml
    # ...
    n8n_subdomain: "n8n"
    ```

3.  **Acesse o Portainer e Selecione o Endpoint `local`** (`core-services-vm`).
4.  Vá para "Stacks" -> "+ Add stack".
5.  **Nome da Stack:** `automation-n8n`.
6.  **Web editor:** Cole o conteúdo do `n8n-compose.yml`.
7.  **Carregue o Arquivo `.env`:**
    *   Na seção "Environment variables", clique em "Load variables from .env file".
    *   **Path on disk:** `/opt/portainer_stack_envs/n8n.env`.
8.  **Adicione Secrets Manualmente:**
    *   `N8N_ADMIN_USER_FROM_PORTAINER_ENV`: Cole o valor de `n8n_admin_user` do seu vault.
    *   `N8N_ADMIN_PASSWORD_FROM_PORTAINER_ENV`: Cole o valor de `n8n_admin_password` do seu vault.
9.  **Clique em "Deploy the stack".**

Após alguns instantes, você poderá acessar `https://n8n.seudominio.com`. Você será saudado pela tela de login do Authelia e, em seguida, pela tela de login do próprio n8n. Após o login, você estará pronto para começar a construir seus workflows.

## 11.3. Configuração Inicial e Primeiro Workflow

Ao acessar o n8n pela primeira vez, você verá uma tela em branco, pronta para a sua criatividade.

### Armazenando Credenciais no n8n

O n8n precisa se autenticar com outros serviços. Ele possui um gerenciador de credenciais seguro embutido.

1.  No menu à esquerda, vá para "Credentials".
2.  Clique em "Add credential".
3.  Pesquise pelo serviço que deseja usar (ex: "Telegram", "Google Sheets", "HTTP Header Auth").
4.  Preencha as informações solicitadas (API keys, tokens, etc.). Essas credenciais são criptografadas e armazenadas de forma segura no volume do n8n.

### Criando um Workflow de Notificação Simples

Vamos criar um workflow que pode ser acionado por um webhook e envia uma mensagem para o Telegram.

1.  **Crie as Credenciais do Telegram:**
    *   Fale com o `@BotFather` no Telegram para criar um novo bot e obter seu token de API.
    *   Obtenha o Chat ID do seu usuário ou de um grupo.
    *   Adicione as credenciais "Telegram API" no n8n.

2.  **Crie um Novo Workflow:**
    *   Clique em "Add workflow".

3.  **Adicione o Nó de Trigger (Webhook):**
    *   O workflow começa com um nó. Clique nele e escolha o trigger "Webhook".
    *   O n8n gerará uma URL de webhook de teste e uma de produção. Copie a URL de teste.

4.  **Teste o Webhook:**
    *   Em outra janela ou usando uma ferramenta como `curl`, envie uma requisição POST para a URL de teste com um corpo JSON simples:
        ```bash
        curl -X POST -H "Content-Type: application/json" -d '{"service":"Plex","status":"offline","details":"Não foi possível acessar o servidor Plex."}' <URL_DO_WEBHOOK_DE_TESTE>
        ```
    *   Volte para o n8n. Você verá que o nó do webhook capturou os dados.

5.  **Adicione o Nó do Telegram:**
    *   Clique no `+` após o nó do webhook para adicionar um novo nó.
    *   Pesquise por "Telegram" e selecione a ação "Send Message".
    *   **Credential:** Escolha a credencial do Telegram que você criou.
    *   **Chat ID:** Insira o seu Chat ID.
    *   **Text:** Aqui vem a mágica do n8n. Você pode construir a mensagem usando os dados do nó anterior. Clique na caixa "Text" e use o "Expression Editor" para montar uma mensagem dinâmica:
        ```
        🚨 Alerta de Serviço! 🚨
        Serviço: {{$json["body"]["service"]}}
        Status: {{$json["body"]["status"]}}
        Detalhes: {{$json["body"]["details"]}}
        ```

6.  **Teste o Nó do Telegram:**
    *   Clique no botão "Execute Node". Uma mensagem deve aparecer no seu Telegram.

7.  **Ative o Workflow:**
    *   No canto superior direito, ative o workflow. Agora ele está "vivo" e escutando na URL de webhook de produção.

Você acabou de criar uma automação poderosa e flexível. Agora você pode integrar essa URL de webhook em qualquer serviço que suporte notificações, como o Uptime Kuma, para receber alertas personalizados e inteligentes.

Explore os mais de 400 nós disponíveis no n8n para conectar suas aplicações e liberar todo o potencial de automação do seu servidor doméstico. Para guias mais aprofundados, consulte a [nova seção no Guia de Estudos](/?path=docs/05-guia-estudos/09-aprofundamento-n8n.md).
