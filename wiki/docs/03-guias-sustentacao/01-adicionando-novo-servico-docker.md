---
description: "Checklist e exemplo prático para adicionar um novo serviço Docker com volumes, Traefik, Authelia e Ansible."
---

# Adicionando um Novo Serviço Docker à Infraestrutura

!!! info "Fonte do checklist: catálogo + índice de integrações"
    A lista do que uma aplicação nova precisa (roteamento, autenticação, acesso externo, métricas, logs, dados, variáveis, LLM, documentação) é definida no [Catálogo de Aplicações](../02-visao-geral-arquitetura/09-catalogo-aplicacoes.md) e no [Índice de Integrações](../02-visao-geral-arquitetura/10-indice-integracoes.md). Agentes de IA executam esse fluxo pela skill `add-app` (veja `AGENTS.md`). Este guia mostra o passo a passo manual com um exemplo.

Uma das grandes vantagens da nossa arquitetura baseada em Docker, Portainer e Traefik é a facilidade com que podemos adicionar novos serviços e aplicações ao nosso servidor doméstico. Este guia fornece um checklist detalhado e um exemplo prático para integrar uma nova aplicação containerizada de forma segura e consistente com o restante da infraestrutura.

O processo geral envolve planejar o serviço, preparar os volumes e configurações (idealmente com Ansible), definir o serviço em um arquivo `docker-compose.yml`, e então implantá-lo via Portainer.

## Checklist Detalhado para Adicionar um Novo Serviço Docker

Siga estes passos para garantir uma integração suave e bem-sucedida:

1.  **Fase de Planejamento e Pesquisa do Novo Serviço:**
    *   **Identifique a Imagem Docker:**
        *   Qual imagem Docker você usará? É uma imagem oficial, uma da [LinuxServer.io](https://fleet.linuxserver.io/) (lscr.io), do [GitHub Container Registry](https://ghcr.io), ou de outra fonte confiável?
        *   Verifique a popularidade da imagem, a frequência de atualizações, e se há problemas conhecidos (issues no GitHub do projeto).
        *   **Escolha uma tag de versão específica** (e.g., `imagem:v1.2.3` ou `imagem:stable`) em vez de `imagem:latest` para garantir implantações mais previsíveis e evitar quebras inesperadas quando `latest` for atualizado.
    *   **Requisitos de Recursos:**
        *   Avalie o consumo estimado de CPU, RAM e espaço em disco do novo serviço.
        *   Ele se encaixa confortavelmente nos recursos da sua `core-services-vm`? Ou, se for uma aplicação muito pesada ou com requisitos especiais (como a stack de IA), ela deveria ir para a `ai-desktop-vm` ou até mesmo uma nova VM dedicada? (Veja [Gerenciando Recursos de VMs](06-gerenciando-recursos-vms.md)).
    *   **Persistência de Dados (Volumes):**
        *   O serviço precisa armazenar dados permanentemente (configurações, bancos de dados internos, arquivos de usuário)?
        *   Se sim, identifique quais diretórios dentro do container precisam ser mapeados para volumes persistentes. A documentação da imagem Docker geralmente especifica isso.
        *   Planeje onde esses volumes residirão no seu sistema de arquivos NFS. Uma boa prática é criar um subdiretório específico para o novo serviço dentro do seu dataset de volumes Docker:
            `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/<nome_do_novo_servico>/config`
            `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/<nome_do_novo_servico>/data` (etc.)
    *   **Configuração de Rede:**
        *   **Acesso Externo:** O serviço precisa ser acessível da internet?
            *   Se sim, qual subdomínio você usará (e.g., `novoservico.{{ base_domain }}`)?
        *   **Proteção com Authelia:** Se for acessível externamente, ele deve ser protegido pelo [Authelia](../02-visao-geral-arquitetura/01-fluxo-rede-acesso-externo.md#4-authelia-servidor-de-autenticação-e-autorização)? (Quase sempre sim, a menos que seja um serviço intencionalmente público como um blog).
        *   **Comunicação Interna:** O novo serviço precisa se comunicar com outros containers existentes (e.g., um banco de dados, um serviço de API)? Se sim, a quais redes Docker ele precisará ser conectado (`proxy`, `internal_services`)?
    *   **Variáveis de Ambiente:**
        *   Quais variáveis de ambiente são **obrigatórias** ou **recomendadas** para configurar o serviço? Consulte a documentação da imagem Docker.
        *   Comuns incluem: `PUID`, `PGID` (para permissões de arquivo), `TZ` (fuso horário), senhas, caminhos específicos dentro do container, opções de features.
    *   **Portas Internas:** Em qual porta o serviço escuta *dentro* do container? Isso é necessário para a configuração do Traefik.

2.  **Preparação de Volumes e Arquivo `.env` (Via Ansible - Recomendado):**
    Para manter a consistência e automação (IaC):
    *   No seu projeto `home-server/ansible/`:
        *   Crie um novo playbook Ansible, por exemplo, `ansible/playbooks/setup-novoservico-volumes.yml`.
        *   Este playbook deve ser direcionado à VM onde o novo serviço Docker rodará (e.g., `core-services-vm`).
        *   **Tarefas do Playbook:**
            1.  Usar o módulo `ansible.builtin.file` para criar os diretórios de volume necessários no caminho NFS (e.g., `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/novoservico/config`) com as permissões corretas (`owner: {{ docker_puid }}`, `group: {{ docker_pgid }}`, `mode: '0775'` ou `0750`).
            2.  Usar o módulo `ansible.builtin.template` para gerar um arquivo `.env` para o novo serviço. Este arquivo será colocado em `{{ portainer_env_files_dest_path_on_vm }}/novoservico.env` na VM.
                *   Use o template `ansible/templates/portainer_stack_env.j2` como base.
                *   Adicione variáveis específicas para os caminhos de volume do novo serviço ao template ou ao playbook que chama o template, por exemplo:
                    ```yaml
                    # No playbook setup-novoservico-volumes.yml, ao chamar o template:
                    # ...
                    #   template:
                    #     src: ../templates/portainer_stack_env.j2
                    #     dest: "{{ portainer_env_files_dest_path_on_vm }}/novoservico.env"
                    #   vars:
                    #     stack_name: "novoservico" # Para lógica condicional no template
                    #     NOVOSERVICO_CONFIG_PATH: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/novoservico/config"
                    #     NOVOSERVICO_DATA_PATH: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/novoservico/data"
                    ```
    *   **Execute o novo playbook Ansible:**
        ```bash
        ansible-playbook ansible/playbooks/setup-novoservico-volumes.yml --ask-vault-pass
        ```
        Isso garante que os diretórios NFS e o arquivo `.env` com os caminhos corretos estejam prontos na VM antes de você tentar implantar a stack no Portainer.

3.  **Escrever o Arquivo `docker-compose.yml` para a Nova Stack:**
    *   No seu projeto `home-server/`, crie um novo diretório para a stack, por exemplo, `docker/stacks/novoservico/`.
    *   Dentro dele, crie o arquivo `docker-compose.yml`.
    *   **Estrutura Típica (Exemplo):**
        ```yaml title="Exemplo: docker/stacks/novoservico/docker-compose.yml"
        # docker/stacks/novoservico/docker-compose.yml
        version: '3.9' # Ou a versão mais recente suportada pelo seu Docker Compose

        networks:
          proxy: # Necessário se o serviço for exposto via Traefik
            external: true # Assumindo que a rede 'proxy' já foi criada pelo Ansible
          internal_services: # Se o serviço precisar se comunicar com outros backends (e.g., DBs)
            external: true # Assumindo que 'internal_services' também já existe

        services:
          novoservico: # Nome lógico do serviço dentro deste compose
            image: registry/nome_da_imagem:tag_especifica
            container_name: nome_do_container_novoservico # Nome do container no Docker
            restart: unless-stopped
            networks: # Conecte às redes necessárias
              - proxy # Se exposto via Traefik
              # - internal_services # Se comunica com outros serviços internos
            volumes:
              # Use as variáveis de ambiente que serão definidas no arquivo .env carregado pelo Portainer
              - "${NOVOSERVICO_CONFIG_PATH}:/config"  # Mapeia o volume de configuração do serviço
              - "${NOVOSERVICO_DATA_PATH}:/data"    # Exemplo de volume de dados
              # Adicione outros volumes conforme a documentação da imagem
            environment:
              - PUID=${DOCKER_PUID} # Do arquivo .env (valor do Ansible Vault)
              - PGID=${DOCKER_PGID} # Do arquivo .env (valor do Ansible Vault)
              - TZ=${SYSTEM_TIMEZONE} # Do arquivo .env (valor do Ansible Vault)
              # - OUTRA_VARIAVEL_CONFIG=${VALOR_DA_VARIAVEL} # Pode vir do .env ou definida no Portainer
              # - SENHA_ESPECIFICA_APP=${SENHA_DO_NOVOSERVICO_APP} # Esta será definida como secret no Portainer
            labels: # Labels para Traefik (apenas se o serviço for exposto externamente)
              # --- Labels Traefik ---
              traefik.enable: "true" # Habilita o Traefik para este serviço

              # Roteador HTTP
              traefik.http.routers.novoservico.rule: "Host(`novoservico.{{ base_domain }}`)" # Substitua {{ base_domain }} pelo seu domínio real
              traefik.http.routers.novoservico.entrypoints: "websecure" # Usa o entrypoint HTTPS (porta 443)
              traefik.http.routers.novoservico.tls.certresolver: "letsencrypt" # Usa Let's Encrypt para SSL

              # Middlewares (e.g., Authelia para proteção, headers de segurança)
              # Se precisar de múltiplos middlewares, separe por vírgula: "authelia-forwardauth@docker,securityHeaders@file"
              traefik.http.routers.novoservico.middlewares: "authelia-forwardauth@docker" # Se for proteger com Authelia

              # Serviço (como Traefik deve se conectar ao container internamente)
              traefik.http.services.novoservico.loadbalancer.server.port: "8000" # Porta INTERNA que o container 'novoservico' escuta
              # traefik.http.services.novoservico.loadbalancer.server.scheme: "http" # Se o container escuta em HTTP (padrão)
        ```
    !!! tip "Nomenclatura Consistente para Labels Traefik"
        Use nomes consistentes e descritivos para seus roteadores e serviços Traefik (e.g., `traefik.http.routers.nomedoservico...`). O placeholder `{{ base_domain }}` nas labels será substituído pelo valor real se o container Traefik tiver acesso a essa variável (o que ele tem, via `BASE_DOMAIN_FROM_VAULT` passada para ele).

4.  **Deploy da Nova Stack via Portainer:**
    Siga o processo descrito em [Deploy Core](../01-manual-implementacao/06-deploy-core.md) (para stacks de infraestrutura) ou [Deploy de Apps](../01-manual-implementacao/07-deploy-apps.md) (para stacks de aplicações):
    *   Acesse o Portainer, selecione o **endpoint Docker correto** (e.g., `local` para `core-services-vm`).
    *   Vá para "Stacks" -> "+ Add stack".
    *   **Nome:** Dê um nome para a stack (e.g., `novoservico-stack`).
    *   **Build method:** "Web editor". Cole o conteúdo do seu `docker-stacks/novoservico/docker-compose.yml`.
    *   **Environment variables (Advanced mode):**
        *   **Load variables from .env file:** Forneça o caminho **DENTRO DA VM** para o arquivo `.env` que foi preparado pelo Ansible (e.g., `/opt/portainer_stack_envs/novoservico.env`).
        *   **Adicionar Secrets Manualmente:** Para quaisquer senhas ou tokens de API (e.g., `SENHA_DO_NOVOSERVICO_APP` se referenciada no compose), adicione-os aqui como variáveis de ambiente. **NÃO** coloque segredos diretamente no `docker-compose.yml` ou no arquivo `.env` versionado.
    *   Clique em "**Deploy the stack**".

5.  **Configuração de DNS na Cloudflare (se o serviço for exposto externamente):**
    *   Se você usa uma Ingress Rule wildcard (`*.{{ base_domain }}`) no seu Cloudflare Tunnel que aponta para o Traefik (conforme recomendado na [Seção 5.5](../01-manual-implementacao/05-rede-segura.md#opção-2-gerenciamento-manual-de-ingress-rules-no-cloudflare-zero-trust-dashboard-recomendado-para-flexibilidade)), este passo pode não ser estritamente necessário, pois o novo subdomínio (`novoservico.{{ base_domain }}`) já será coberto e roteado para o Traefik.
    *   Caso contrário, ou se você quiser uma entrada explícita, adicione manualmente um registro **CNAME** no painel DNS da Cloudflare:
        *   **Type:** `CNAME`
        *   **Name:** `novoservico` (o subdomínio do seu novo serviço, sem o domínio base).
        *   **Target:** O hostname do seu Cloudflare Tunnel (e.g., `SEU_TUNNEL_UUID.cfargotunnel.com`).
        *   **Proxy Status:** Certifique-se de que está **Laranja (Proxied)**.
    *   Aguarde alguns minutos para a propagação do DNS.

6.  **Teste e Pós-Configuração:**
    *   Acesse `https://novoservico.{{ base_domain }}` no seu navegador.
    *   Se o serviço estiver protegido por Authelia, você será redirecionado para o portal de login do Authelia.
    *   Verifique os logs do novo container no Portainer para quaisquer erros de inicialização ou operacionais.
    *   Realize qualquer configuração inicial necessária dentro da interface do próprio novo serviço (e.g., criar um usuário administrador, configurar preferências).

## Exemplo Prático: Adicionando `FileBrowser` (Revisitado)

FileBrowser é um gerenciador de arquivos web simples e eficaz. Vamos revisitar o exemplo, focando no fluxo completo.

1.  **Planejamento:**
    *   Imagem: `filebrowser/filebrowser:v2.29.0` (ou mais recente estável).
    *   Recursos: Leve, roda bem na `core-services-vm`.
    *   Persistência:
        *   Configuração: `/config` dentro do container. Mapear para `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/filebrowser/config`.
        *   Dados (arquivos a serem gerenciados): `/srv` dentro do container. Mapearemos para um diretório no NFS, e.g., `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/filebrowser/shared_files` ou até mesmo para `{{ vm_nfs_mount_base_path }}/{{ zfs_media_dataset_name }}/` se quisermos que ele navegue na nossa biblioteca de mídia.
    *   Rede: Expor em `files.{{ base_domain }}`, proteger com Authelia. Conectar à rede `proxy`.
    *   Variáveis: PUID, PGID, TZ. FileBrowser usa a porta 80 internamente por padrão.

2.  **Preparação Ansible (`setup-filebrowser-volumes.yml`):**
    *   Crie o playbook.
    *   Tasks para criar os diretórios NFS:
        *   `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/filebrowser/config`
        *   `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/filebrowser/shared_files` (exemplo para dados)
    *   Task para gerar `/opt/portainer_stack_envs/filebrowser.env` na `core-services-vm` com:
        ```env
        # /opt/portainer_stack_envs/filebrowser.env (Gerado por Ansible)
        DOCKER_PUID={{ docker_puid }}
        DOCKER_PGID={{ docker_pgid }}
        SYSTEM_TIMEZONE={{ system_timezone }}
        # Note: BASE_DOMAIN não é estritamente necessário aqui se as labels Traefik usam {{ base_domain }}
        # que o Traefik resolve, mas pode ser útil para consistência.
        BASE_DOMAIN={{ base_domain }}
        CORE_SERVICES_VM_IP_VAR={{ core_services_vm_ip_var }} # Se precisar para algo específico
        FILEBROWSER_CONFIG_PATH={{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/filebrowser/config
        FILEBROWSER_SHARED_DATA_PATH={{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/filebrowser/shared_files
        ```
    *   Execute o playbook: `ansible-playbook ansible/playbooks/setup-filebrowser-volumes.yml --ask-vault-pass`.

3.  **`docker-compose.yml` para FileBrowser (`docker/stacks/filebrowser/docker-compose.yml`):**
    ```yaml
    version: '3.9'
    networks: { proxy: { external: true } }
    services:
      filebrowser:
        image: filebrowser/filebrowser:v2.29.0 # Verifique a tag mais recente e estável
        container_name: filebrowser_app
        restart: unless-stopped
        # user: "${DOCKER_PUID}:${DOCKER_PGID}" # Filebrowser geralmente roda como root e gerencia permissões internas.
                                             # Se usar PUID/PGID, garanta que ele tenha acesso aos volumes.
                                             # Para simplicidade inicial, pode-se omitir, mas teste as permissões.
        networks: [proxy]
        volumes:
          - "${FILEBROWSER_CONFIG_PATH}:/config" # Configuração do FileBrowser (inclui filebrowser.db)
          - "${FILEBROWSER_SHARED_DATA_PATH}:/srv" # Diretório raiz que o FileBrowser servirá
        environment:
          - PUID=${DOCKER_PUID} # Para o processo interno se a imagem suportar
          - PGID=${DOCKER_PGID}
          - TZ=${SYSTEM_TIMEZONE}
          - FB_BASEURL=/ # Se FileBrowser estiver na raiz do subdomínio
          # FB_ADDRESS=0.0.0.0 # Padrão, escuta em todas as interfaces dentro do container
          # FB_PORT=80 # Porta interna padrão do container FileBrowser
        labels:
          traefik.enable: "true"
          traefik.http.routers.filebrowser.rule: "Host(`files.{{ base_domain }}`)"
          traefik.http.routers.filebrowser.entrypoints: "websecure"
          traefik.http.routers.filebrowser.tls.certresolver: "letsencrypt"
          traefik.http.routers.filebrowser.middlewares: "authelia-forwardauth@docker" # Protegido por Authelia
          traefik.http.services.filebrowser.loadbalancer.server.port: "80" # FileBrowser escuta na porta 80 internamente
    ```

4.  **Deploy via Portainer:**
    *   Endpoint: `local`.
    *   Stack Name: `filebrowser-stack`.
    *   Cole o compose.
    *   Carregue `/opt/portainer_stack_envs/filebrowser.env`.
    *   Não há secrets adicionais para FileBrowser por padrão.
    *   "Deploy the stack".

5.  **DNS Cloudflare:**
    *   Se o wildcard `*.{{ base_domain }}` já estiver configurado no seu Cloudflare Tunnel apontando para Traefik, nenhuma ação de DNS é necessária.
    *   Caso contrário, adicione CNAME `files` para `{{ base_domain }}` apontando para seu túnel.

6.  **Teste e Pós-Configuração:**
    *   Acesse `https://files.{{ base_domain }}`.
    *   Autentique com Authelia.
    *   Você verá a tela de login do FileBrowser. O login padrão é `admin` / `admin`.
    *   !!! critical "MUDE A SENHA PADRÃO DO FILEBROWSER!"
        Após o primeiro login no FileBrowser, vá para "Settings" -> "User Management" e **altere a senha do usuário `admin` imediatamente!**
    *   Configure usuários adicionais, permissões e outras preferências dentro do FileBrowser conforme necessário.

Seguindo este processo estruturado, você pode expandir seu servidor doméstico com uma vasta gama de aplicações e serviços auto-hospedados, mantendo a organização e a segurança.