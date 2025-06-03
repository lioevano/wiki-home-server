# Seção 6: Gerenciamento e Deploy de Stacks Docker com Portainer (Usando Volumes NFS)

Com a infraestrutura base (Proxmox, VMs, NFS, Docker) e a rede segura (Traefik, Cloudflare Tunnel, Authelia) configuradas, agora utilizaremos o Portainer para gerenciar e implantar as stacks de aplicações Docker. Os dados persistentes dessas aplicações residirão nos datasets ZFS do host Proxmox e serão acessados pelas VMs via NFS.

O Portainer foi instalado na `core-services-vm` como parte do playbook [`setup-base-ubuntu.yml`](04-configuracao-base-vms-ubuntu.md#43-playbook-ansibleplaybookssetup-base-ubuntumdl) e já deve estar acessível através do seu subdomínio protegido por Authelia.

## 6.1. Acesso Inicial ao Portainer e Configuração

Siga estes passos para o primeiro acesso e configuração do Portainer:

1.  **Acesse o Portainer:**
    *   Abra seu navegador e navegue para `https://portainer.{{ base_domain }}` (substitua `{{ base_domain }}` pelo seu domínio real, conforme configurado no Ansible Vault e DNS da Cloudflare).
    *   Você deverá ser redirecionado para o portal de login do Authelia (`https://auth.{{ base_domain }}`).

2.  **Autenticação com Authelia:**
    *   Faça login com o usuário administrador do Authelia que você configurou (variável `authelia_admin_user_initial` no `vault.yml`) e a senha correspondente ao hash `authelia_admin_password_hash_initial`.
    *   **Configuração de 2FA:** Na primeira vez que você logar com sucesso no Authelia, ele provavelmente solicitará que você configure um método de Dois Fatores (2FA). Siga as instruções na tela para registrar um dispositivo TOTP (e.g., usando Google Authenticator, Authy, ou um gerenciador de senhas com suporte a TOTP).

3.  **Configuração Inicial do Portainer:**
    *   Após a autenticação bem-sucedida com Authelia, você será redirecionado de volta para a página de setup inicial do Portainer.
    *   **Crie uma conta de administrador para o Portainer:**
        *   **Username:** Escolha um nome de usuário (e.g., `admin`).
        *   **Password:** Crie uma senha forte e única **específica para o Portainer**. Armazene-a com segurança.
            !!! warning "Senha do Portainer vs Senha Authelia"
                A senha que você define aqui é para o Portainer em si, e é diferente da senha do seu usuário Authelia.
    *   Clique em "Create user".

4.  **Conecte o Portainer ao Ambiente Docker Local:**
    *   Na tela "Connect Portainer to the Docker environment you want to manage", a opção "Docker - Manage the local Docker environment" já deve estar selecionada.
    *   Clique em "Connect".

5.  **Dashboard do Portainer:**
    *   Você será levado ao dashboard principal do Portainer. Você deve ver o ambiente "local" listado, que corresponde ao Docker Engine rodando na sua `core-services-vm`.

## 6.2. Implantação de Stacks Docker (Processo Geral)

"Stacks" no Portainer são equivalentes a projetos Docker Compose. Para cada grupo de aplicações (Mídia, RAG, Produtividade, etc.), seguiremos um processo similar.

### Ação Preparatória Ansible (para cada grupo de stacks)

Antes de implantar uma stack no Portainer, o Ansible deve ser usado para preparar o ambiente na VM de destino (`core-services-vm` ou `ai-desktop-vm`). Isso envolve:

1.  **Criação de Diretórios nos Volumes NFS:**
    *   Os playbooks específicos de cada stack (e.g., `setup-media-stack-volumes.yml`, `setup-rag-llm-volumes.yml`) são responsáveis por criar os subdiretórios necessários nos datasets ZFS montados via NFS.
    *   Exemplo: Para Plex, o playbook criaria `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/plex/config` na `core-services-vm`.
    *   Esses diretórios devem ter as permissões corretas (geralmente `owner: {{ docker_puid }}`, `group: {{ docker_pgid }}`) para que os containers Docker possam ler e escrever neles.

2.  **Preparação de Arquivos `.env` para Portainer:**
    *   Os mesmos playbooks Ansible gerarão arquivos `.env` para cada stack. Estes arquivos contêm variáveis não sensíveis como PUID, PGID, fuso horário, domínio base, e **caminhos para os volumes NFS**.
    *   Esses arquivos `.env` são colocados em um local específico na VM (e.g., `/opt/portainer_stack_envs/nome_da_stack.env`), conforme definido pela variável `portainer_env_files_dest_path_on_vm`.
    *   O template base para esses arquivos `.env` é `ansible/templates/portainer_stack_env.j2`:

        ```jinja
        # ansible/templates/portainer_stack_env.j2
        # Gerado por Ansible para a stack {{ stack_name }}
        # Use este arquivo no Portainer: Add Stack -> Environment Variables -> Advanced mode -> Load variables from .env file
        # Caminho na VM: {{ portainer_env_files_dest_path_on_vm }}/{{ stack_name }}.env

        # --- Variáveis Comuns (resolvidas do Ansible vault/main.yml) ---
        DOCKER_PUID={{ docker_puid }}
        DOCKER_PGID={{ docker_pgid }}
        SYSTEM_TIMEZONE={{ system_timezone }}
        BASE_DOMAIN={{ base_domain }}

        # --- IPs das VMs (condicionalmente definidos) ---
        {% if inventory_hostname == 'core-services-vm' %}
        CORE_SERVICES_VM_IP_VAR={{ core_services_vm_ip_var }}
        {% elif inventory_hostname == 'ai-desktop-vm' %}
        AI_DESKTOP_VM_IP_VAR={{ ai_desktop_vm_ip_var }}
        {% endif %}

        # --- Caminhos de Volume Base (montados via NFS do Proxmox Host) ---
        # Estes são os pontos de montagem NFS DENTRO da VM.
        VM_NFS_MOUNT_BASE_PATH={{ vm_nfs_mount_base_path }}
        # Nomes dos datasets ZFS (usados para construir os caminhos completos)
        ZFS_DOCKER_VOLUMES_DATASET_NAME={{ zfs_docker_volumes_dataset_name }}
        ZFS_MEDIA_DATASET_NAME={{ zfs_media_dataset_name }}
        ZFS_DOWNLOADS_DATASET_NAME={{ zfs_downloads_dataset_name }}
        ZFS_RAG_SOURCES_DATASET_NAME={{ zfs_rag_sources_dataset_name }}

        # --- Caminhos Específicos para a Stack (Exemplos) ---
        # Estes são gerados condicionalmente pelo playbook Ansible que chama este template,
        # passando o 'stack_name' correto.
        # Os docker-compose.yml usarão estas variáveis (e.g., ${MEDIA_STACK_PLEX_CONFIG_PATH})

        {% if stack_name == "media" %}
        # Caminhos para a Stack de Mídia
        MEDIA_STACK_PLEX_CONFIG_PATH={{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/plex/config
        MEDIA_STACK_PLEX_TRANSCODE_PATH={{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/plex/transcode
        MEDIA_STACK_MOVIES_PATH={{ vm_nfs_mount_base_path }}/{{ zfs_media_dataset_name }}/movies
        MEDIA_STACK_TVSHOWS_PATH={{ vm_nfs_mount_base_path }}/{{ zfs_media_dataset_name }}/tvshows
        # ... (outros caminhos para a stack de mídia) ...
        {% elif stack_name == "rag" %}
        # Caminhos para a Stack de IA/RAG
        RAG_STACK_OPENWEBUI_DATA_PATH={{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/openwebui/data
        # ... (outros caminhos para a stack RAG) ...
        {% elif stack_name == "productivity" %}
        # Caminhos para a Stack de Produtividade
        PROD_STACK_NEXTCLOUD_HTML_PATH={{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/nextcloud/html
        # ... (outros caminhos para a stack de produtividade) ...
        {% elif stack_name == "automation" %}
        # Caminhos para a Stack de Automação
        AUTO_STACK_HOMEASSISTANT_CONFIG_PATH={{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/homeassistant/config
        {% elif stack_name == "monitoring" %}
        # Caminhos para a Stack de Monitoramento
        MONITORING_PROMETHEUS_DATA_PATH={{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/prometheus/data
        # ... (outros caminhos para a stack de monitoramento) ...
        {% endif %}

        !!! warning "Segredos NÃO Incluídos"
            Senhas de bancos de dados, tokens de API e outros segredos **NÃO SÃO** colocados nestes arquivos `.env`. Eles devem ser definidos manualmente como "secrets" do Portainer ou como variáveis de ambiente diretamente na UI do Portainer ao criar/editar a stack.
        ```

    !!! important "Executar Playbooks de Volume ANTES"
        Lembre-se de executar o playbook Ansible `setup-<nome_da_stack>-volumes.yml` correspondente **ANTES** de tentar implantar a stack no Portainer. Isso garante que os diretórios NFS e os arquivos `.env` estejam prontos.

### Ação no Portainer (para cada stack Docker)

1.  **Navegue para o Endpoint Correto:**
    *   No Portainer, vá em "Environments".
    *   Selecione o endpoint `local` (que corresponde à `core-services-vm`).
    *   Se você estiver implantando uma stack na `ai-desktop-vm` (como a stack RAG), você precisará ter o Portainer Agent instalado nessa VM e adicionado como um novo endpoint no Portainer. Selecione esse endpoint.

2.  **Adicionar uma Nova Stack:**
    *   No menu lateral, clique em "Stacks".
    *   Clique em "+ Add stack".

3.  **Configurar a Stack:**
    *   **Name:** Dê um nome descritivo para a stack (e.g., `media-services`, `rag-stack`, `nextcloud-services`).
    *   **Build method:** Selecione "Web editor".
    *   **Web editor:** Cole o conteúdo do arquivo `docker-compose.yml` correspondente à stack que você está implantando (e.g., de `infra-servidor-domestico/docker/stacks/media/docker-compose.yml`).
        !!! note "Caminhos nos Docker Compose Files"
            Os arquivos `docker-compose.yml` para cada stack (detalhados nas Seções 7-10) devem usar variáveis de ambiente para os caminhos dos volumes (e.g., `volumes: - ${MEDIA_STACK_PLEX_CONFIG_PATH}:/config`). Essas variáveis serão fornecidas pelo arquivo `.env` carregado.

4.  **Variáveis de Ambiente (Environment Variables):**
    *   Role a página para baixo até a seção "Environment variables".
    *   Mude para "Advanced mode".
    *   **Carregar Variáveis do Arquivo `.env`:**
        *   Clique no botão "Load variables from .env file".
        *   No campo "Path on disk", forneça o caminho **DENTRO DA VM** para o arquivo `.env` que foi preparado pelo Ansible para esta stack.
            *   Exemplo para a stack de mídia na `core-services-vm`: `/opt/portainer_stack_envs/media.env`
            *   Exemplo para a stack RAG na `ai-desktop-vm`: `/opt/portainer_stack_envs/rag.env`
        *   Isso preencherá automaticamente muitas das variáveis necessárias (PUID, PGID, TZ, caminhos de volume, etc.).
    *   **Adicionar Secrets Manualmente:**
        *   Para senhas de bancos de dados, tokens de API e quaisquer outros segredos que **não** estão no arquivo `.env` (porque são sensíveis demais para serem armazenados em um arquivo de texto simples, mesmo que apenas na VM), adicione-os manualmente aqui.
        *   Clique em "+ Add environment variable" para cada segredo.
            *   **Name:** O nome da variável de ambiente conforme esperado pelo container (e.g., `NEXTCLOUD_DB_PASSWORD`, `PLEX_CLAIM_TOKEN`).
            *   **Value:** O valor do segredo (copie do seu Ansible Vault ou gerenciador de senhas).
        *   Alternativamente, para maior segurança, o Portainer suporta "Secrets". Você pode criar um Secret no Portainer e depois referenciá-lo no seu `docker-compose.yml`. Este guia foca em variáveis de ambiente para simplicidade inicial.

5.  **Verificar Configurações Adicionais:**
    *   **Redes:** Verifique se as redes Docker (`proxy`, `internal_services`) estão corretamente referenciadas como `external: true` no seu `docker-compose.yml` se elas foram criadas globalmente pelo Ansible.
    *   **Volumes:** Confirme se os mapeamentos de volume usam as variáveis de ambiente que serão preenchidas pelo `.env`.

6.  **Deploy da Stack:**
    *   No final da página, clique em "Deploy the stack" (ou "Update the stack" se estiver modificando uma existente).
    *   O Portainer executará o equivalente a `docker compose up -d` com as configurações fornecidas.

7.  **Monitorar Logs e Status:**
    *   Após o deploy, vá para "Containers" no Portainer.
    *   Verifique os logs de cada container na nova stack para garantir que eles iniciaram corretamente e não há erros.
    *   Verifique se os containers estão no estado "running".

**Repita este processo (passos preparatórios Ansible e deploy no Portainer) para cada stack de aplicações que você deseja implantar (Mídia, RAG, Produtividade, Automação, Monitoramento), conforme detalhado nas seções seguintes.**

Este processo estruturado garante que seus dados sejam persistidos corretamente nos volumes NFS e que as configurações sejam gerenciadas de forma consistente.

Próximo passo: [Stack de Inteligência Artificial (LLM/RAG com Ollama)](07-stack-ia-rag.md).