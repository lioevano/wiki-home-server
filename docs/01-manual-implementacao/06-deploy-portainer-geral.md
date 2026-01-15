# Seção 6: Gerenciamento e Deploy de Stacks Docker com Portainer (Usando Volumes NFS)

Agora que nossa infraestrutura base está de pé – Proxmox VE, máquinas virtuais configuradas (`core-services-vm` e `ai-desktop-vm`), armazenamento NFS funcional, Docker Engine instalado e, mais importante, nossa [rede segura com Traefik, Cloudflare Tunnel e Authelia](05-rede-segura.md) está operacional – é hora de começar a implantar nossas aplicações!

Utilizaremos o **Portainer** como nossa interface gráfica para gerenciar o Docker e implantar "Stacks". Uma Stack no Portainer é, essencialmente, um projeto Docker Compose, permitindo-nos definir e gerenciar aplicações multi-container de forma organizada. Todos os dados persistentes das nossas aplicações Docker residirão nos datasets ZFS do host Proxmox e serão acessados pelas VMs via montagens NFS, garantindo segurança e durabilidade dos dados.

O container do Portainer já foi instalado na `core-services-vm` pelo playbook Ansible [`setup-base-ubuntu.yml`](04-configuracao-base-vms-ubuntu.md) e, após a configuração da rede na Seção 5, deve estar acessível através do subdomínio `https://portainer.{{ base_domain }}` (protegido por Authelia).

## 6.1. Acesso Inicial ao Portainer e Configuração

Se este é seu primeiro acesso ao Portainer após o deploy inicial, siga estes passos:

1.  **Acesse a Interface Web do Portainer:**
    *   Abra seu navegador web e navegue para o endereço que você configurou para o Portainer. Conforme nosso setup, este será:
        `https://portainer.{{ base_domain }}` (substitua `{{ base_domain }}` pelo seu domínio real, e.g., `https://portainer.meuhomelab.com`).
    *   Como o Portainer está protegido por Authelia, você será primeiramente redirecionado para o portal de login do Authelia (e.g., `https://auth.{{ base_domain }}`).

2.  **Autenticação via Authelia:**
    *   Na página de login do Authelia, insira as credenciais do usuário administrador que você definiu no Ansible Vault:
        *   **Username:** `{{ authelia_admin_user_initial }}` (e.g., `admin`)
        *   **Password:** A senha correspondente ao hash `{{ authelia_admin_password_hash_initial }}`.
    *   **Configuração de 2FA (Primeiro Login):** Se for o primeiro login bem-sucedido deste usuário no Authelia, você será guiado para configurar um método de Autenticação de Dois Fatores (2FA). Siga as instruções na tela para registrar um dispositivo TOTP (Time-based One-Time Password) usando um aplicativo autenticador como Google Authenticator, Authy, Microsoft Authenticator, ou um gerenciador de senhas com suporte a TOTP.

3.  **Configuração Inicial do Usuário Administrador do Portainer:**
    *   Após a autenticação bem-sucedida com Authelia, você será redirecionado de volta para a página de configuração inicial do Portainer.
    *   Aqui, você criará a conta de administrador **para o próprio Portainer**:
        *   **Username:** Escolha um nome de usuário (e.g., `portainer_admin` ou simplesmente `admin`).
        *   **Password:** Crie uma senha **forte e única** especificamente para esta conta de administrador do Portainer. Armazene-a com segurança no seu gerenciador de senhas.
            !!! warning "Senha do Portainer vs. Senha Authelia"
                A senha que você define aqui é para logar diretamente no Portainer (se você acessasse sua porta interna ou se Authelia estivesse desabilitado para ele). Ela é distinta da senha do seu usuário Authelia.
    *   Clique em "**Create user**".

4.  **Conectar o Portainer ao Ambiente Docker Local:**
    *   Na próxima tela, "Connect Portainer to the Docker environment you want to manage", a opção "**Docker - Manage the local Docker environment**" já deve estar selecionada por padrão (já que Portainer está rodando como um container Docker na mesma `core-services-vm` que ele gerenciará).
    *   Clique em "**Connect**".

5.  **Bem-vindo ao Dashboard do Portainer:**
    *   Você será levado ao dashboard principal do Portainer. No menu "Environments" (ou na página inicial), você deve ver o ambiente "local" listado, representando o Docker Engine rodando na sua `core-services-vm`.

## 6.2. Implantação de Stacks Docker (Processo Geral e Padronizado)

No Portainer, "Stacks" são a forma de gerenciar aplicações definidas por arquivos `docker-compose.yml`. Para cada grupo de aplicações que vamos implantar (Mídia, RAG, Produtividade, Monitoramento, etc.), seguiremos um processo padronizado.

### Ação Preparatória Chave: Playbooks Ansible para Volumes e `.env`

Antes de tentar implantar qualquer stack no Portainer, é **crucial** que o Ansible tenha preparado o ambiente na VM de destino (seja a `core-services-vm` ou a `ai-desktop-vm`). Cada conjunto de serviços (e.g., "media stack", "monitoring stack") terá um playbook Ansible dedicado (e.g., `setup-media-stack-volumes.yml`, `setup-monitoring-stack-volumes.yml`).

Estes playbooks são responsáveis por:

1.  **Criação de Diretórios nos Volumes NFS:**
    *   Garantir que os subdiretórios necessários para os volumes persistentes da stack existam no local correto do montado NFS.
    *   Exemplo: Para a stack de mídia, o playbook criaria diretórios como `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/plex/config`, `.../sonarr/config`, etc., na `core-services-vm`.
    *   As permissões desses diretórios são definidas para `owner: {{ docker_puid }}` e `group: {{ docker_pgid }}` (com `mode: '0775'` ou similar) para que os containers Docker possam ler e escrever neles.

2.  **Preparação de Arquivos `.env` para cada Stack no Portainer:**
    *   Os mesmos playbooks Ansible também gerarão arquivos `.env` específicos para cada stack. Estes arquivos são cruciais porque contêm variáveis de ambiente que serão usadas pelos arquivos `docker-compose.yml` no Portainer.
    *   **Conteúdo Típico do `.env` Gerado:**
        *   `DOCKER_PUID` e `DOCKER_PGID` (do Ansible Vault).
        *   `SYSTEM_TIMEZONE` (do Ansible Vault).
        *   `BASE_DOMAIN` (do Ansible Vault, para labels Traefik).
        *   `CORE_SERVICES_VM_IP_VAR` ou `AI_DESKTOP_VM_IP_VAR` (do inventário Ansible).
        *   **Caminhos completos para os volumes NFS** que serão usados pela stack (e.g., `MEDIA_STACK_PLEX_CONFIG_PATH={{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/plex/config`).
    *   **Localização na VM:** Esses arquivos `.env` são colocados em um local padronizado na VM de destino (e.g., `/opt/portainer_stack_envs/nome_da_stack.env`), conforme definido pela variável Ansible `portainer_env_files_dest_path_on_vm`.
    *   **Template Base:** O template `ansible/templates/portainer_stack_env.j2` é usado pelo Ansible para gerar esses arquivos `.env`, preenchendo as variáveis específicas da stack.

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

    !!! critical "Execute os Playbooks de Preparação de Volume PRIMEIRO!"
        Antes de tentar implantar qualquer stack de aplicação (Mídia, RAG, etc.) no Portainer, **você DEVE executar o playbook Ansible `setup-<nome_da_stack>-volumes.yml` correspondente.** Isso garante que todos os diretórios de volume NFS estejam criados com as permissões corretas e que o arquivo `.env` com os caminhos e variáveis esteja pronto na VM para o Portainer usar.

### Ação no Portainer (Processo Detalhado para Implantar uma Nova Stack)

Siga estes passos no Portainer para cada stack de aplicação Docker que você deseja implantar:

1.  **Navegue para o Endpoint Docker Correto:**
    *   No menu lateral do Portainer, clique em "**Environments**".
    *   Selecione o endpoint apropriado. Para a maioria das stacks (mídia, produtividade, monitoramento, core networking), será o endpoint `local` (que representa o Docker Engine na `core-services-vm`).
    *   Se você estiver implantando uma stack na `ai-desktop-vm` (como a stack RAG), e você configurou o [Portainer Agent nela](../01-manual-implementacao/07-stack-ia-rag.md#portainer-agent-na-ai-desktop-vm-opcional-mas-recomendado), selecione o endpoint correspondente à `ai-desktop-vm`.

2.  **Adicionar uma Nova Stack:**
    *   No menu lateral, clique em "**Stacks**".
    *   Clique no botão "**+ Add stack**".

3.  **Configurar a Nova Stack:**
    *   **Name:** Dê um nome descritivo e único para a stack (e.g., `media-services`, `rag-stack`, `nextcloud-services`, `monitoring-stack`). É uma boa prática usar nomes consistentes com seus playbooks Ansible e diretórios de compose.
    *   **Build method:** Certifique-se de que "**Web editor**" está selecionado.
    *   **Web editor:** Aqui você colará o conteúdo do arquivo `docker-compose.yml` correspondente à stack que você está implantando.
        *   Os arquivos `docker-compose.yml` para cada stack estão localizados no seu projeto `home-server/docker/stacks/nome_da_stack/docker-compose.yml`.
        *   Copie o conteúdo completo do `docker-compose.yml` relevante e cole-o nesta caixa de texto.
        !!! note "Uso de Variáveis nos Arquivos `docker-compose.yml`"
            Lembre-se que nossos arquivos `docker-compose.yml` (detalhados nas Seções 7 a 10) são projetados para usar variáveis de ambiente para os caminhos dos volumes (e.g., `volumes: - ${MEDIA_STACK_PLEX_CONFIG_PATH}:/config`) e outras configurações. Essas variáveis serão fornecidas pelo arquivo `.env` carregado no próximo passo.

4.  **Configurar Variáveis de Ambiente (Environment Variables):**
    *   Abaixo da caixa do editor web, role a página para baixo até a seção "**Environment variables**".
    *   Clique no botão para mudar para "**Advanced mode**" se ainda não estiver.
    *   **Carregar Variáveis do Arquivo `.env`:**
        *   Clique no botão (ou link) que diz "**Load variables from .env file**".
        *   No campo "**Path on disk**", forneça o caminho **ABSOLUTO DENTRO DA VM** onde o Ansible colocou o arquivo `.env` para esta stack específica.
            *   Exemplo para a stack de mídia na `core-services-vm`: `/opt/portainer_stack_envs/media.env`
            *   Exemplo para a stack RAG na `ai-desktop-vm`: `/opt/portainer_stack_envs/rag.env`
        *   Clicar fora do campo ou pressionar Enter deve fazer o Portainer tentar carregar as variáveis. Se bem-sucedido, você verá as variáveis preenchidas na lista abaixo (em modo "simple" ou visíveis no modo "advanced").
    *   **Adicionar Secrets (Senhas, Tokens API) Manualmente:**
        *   Quaisquer variáveis de ambiente que contenham segredos (como senhas de banco de dados, tokens de API, `PLEX_CLAIM_TOKEN`, etc.) **NÃO** devem estar nos arquivos `.env` versionados. Elas devem ser adicionadas manualmente aqui no Portainer.
        *   Clique em "**+ Add environment variable**" para cada segredo que a stack precisa.
            *   **Name:** O nome exato da variável de ambiente conforme esperado pelo(s) container(es) na sua stack (e.g., `NEXTCLOUD_DB_PASSWORD_FROM_PORTAINER_ENV`, `PLEX_CLAIM_TOKEN_FROM_PORTAINER_ENV`). Os nomes com `_FROM_PORTAINER_ENV` são uma convenção para indicar que o valor virá diretamente do Portainer.
            *   **Value:** Cole o valor do segredo aqui. Obtenha esses valores do seu Ansible Vault (`ansible/inventories/home/group_vars/all/vault.yml`) ou do seu gerenciador de senhas pessoal.
        !!! tip "Usando Secrets do Portainer"
            Para uma segurança ainda maior, em vez de variáveis de ambiente, o Portainer permite criar "Secrets" (em Configs & Secrets -> Secrets). Esses secrets podem então ser referenciados no seu `docker-compose.yml` usando a sintaxe `secrets:`. Esta abordagem evita que os segredos fiquem visíveis como variáveis de ambiente dentro do container, mas adiciona um pouco mais de complexidade ao `docker-compose.yml`. Para este guia, focamos em variáveis de ambiente pela simplicidade.

5.  **Verificar Configurações Adicionais da Stack (Opcional):**
    *   **Redes:** Se sua stack usa redes Docker que foram criadas externamente (como `proxy` e `internal_services`), certifique-se de que elas estão declaradas no topo do seu `docker-compose.yml` com `external: true`. O Portainer não tentará criá-las.
    *   **Volumes:** Revise os mapeamentos de volume no seu `docker-compose.yml` para garantir que eles usam as variáveis de ambiente corretas (que foram preenchidas pelo arquivo `.env`).

6.  **Deploy (ou Update) da Stack:**
    *   No final da página, revise tudo e clique no botão "**Deploy the stack**" (se for uma nova stack) ou "**Update the stack**" (se você estiver modificando uma stack existente).
    *   Ao atualizar, se você mudou a tag de uma imagem Docker no `docker-compose.yml` e quer que o Portainer puxe a nova imagem, certifique-se de que a opção "**Re-pull image**" (ou similar) esteja marcada antes de clicar em "Update".

7.  **Monitorar Logs e Status dos Containers:**
    *   Após o deploy, o Portainer o levará para a página da stack ou você pode navegar até "Stacks" para vê-la.
    *   Clique no nome da stack para ver os containers que a compõem.
    *   Para cada container, especialmente os novos ou os que foram recriados:
        *   Verifique seu **status** (deve ser "running").
        *   Clique no ícone de **Logs** (📄) para ver os logs de inicialização do container. Procure por quaisquer mensagens de erro ou avisos. Isso é crucial para o troubleshooting inicial.

**Este processo padronizado (Preparação Ansible -> Deploy Portainer com `.env` e Secrets) será a base para implantar todas as stacks de aplicações detalhadas nas Seções 7 a 10.**

Este fluxo de trabalho garante que:
*   Seus volumes de dados estejam corretamente localizados nos compartilhamentos NFS resilientes.
*   As configurações de PUID/PGID e caminhos sejam consistentes.
*   Os segredos sejam gerenciados de forma mais segura do que colocá-los diretamente nos arquivos `docker-compose.yml`.

Com o Portainer configurado e este processo em mente, você está pronto para começar a popular seu servidor com serviços!

Próximo passo: Começaremos com a [Stack de Inteligência Artificial (LLM/RAG com Ollama)](07-stack-ia-rag.md).