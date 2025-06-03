# Seção 7: Stack de Inteligência Artificial (LLM/RAG com Ollama)

Esta seção detalha a configuração da `ai-desktop-vm` para hospedar serviços de Inteligência Artificial, especificamente para rodar Modelos de Linguagem Grandes (LLMs) localmente com Ollama e aplicações de Retrieval Augmented Generation (RAG) como Open WebUI.

!!! warning "Limitações de Hardware (16GB RAM Total)"
    Com apenas 16GB de RAM no host Proxmox e aproximadamente 8GB alocados para a `ai-desktop-vm` (se a `core-services-vm` estiver usando 6GB e o host 2GB), você estará **severamente limitado** quanto ao tamanho dos LLMs que pode rodar.
    *   **Modelos Viáveis:** Foque em modelos menores, quantizados (e.g., versões de 3 Bilhões ou 7 Bilhões de parâmetros com quantização de 4 bits como Q4_K_M). Modelos maiores provavelmente não carregarão ou causarão instabilidade.
    *   **Performance:** A performance será limitada pela CPU (Ryzen 5 5600G) e pela GPU (RX 5600XT via passthrough).
    *   **Uso Concorrente:** Rodar LLMs pesados pode impactar a performance de outros serviços no seu servidor. Considere agendar o uso intensivo de IA para horários de baixa atividade.

Esta stack é opcional e depende da criação da `ai-desktop-vm` e da configuração bem-sucedida do GPU passthrough (Seção 3).

## 7.1. Preparação da VM `ai-desktop-vm` com Ansible

Antes de implantar os containers Docker para as aplicações RAG, precisamos preparar a `ai-desktop-vm` com drivers de GPU e o serviço Ollama.

### Playbook `setup-rag-llm-volumes.yml`

Este playbook Ansible, executado contra a `ai-desktop-vm`, realizará as seguintes tarefas:
*   Instalar drivers AMD ROCm para a GPU RX 5600XT (se o passthrough estiver funcionando).
*   Instalar o serviço Ollama diretamente na VM (não como container, para melhor acesso à GPU).
*   Configurar Ollama para usar um diretório de modelos no volume NFS.
*   Criar os diretórios NFS necessários para os volumes Docker das aplicações RAG (e.g., Open WebUI).
*   Preparar o arquivo `/opt/portainer_stack_envs/rag.env` na `ai-desktop-vm`.

**Ação:** Execute o playbook a partir da sua máquina de controle Ansible:
```bash
ansible-playbook ansible/playbooks/setup-rag-llm-volumes.yml --ask-vault-pass
```

### Detalhes do Role `ansible/roles/apps/ml-tools/`

Este role é o principal componente do playbook acima para configurar as ferramentas de ML.

#### `tasks/main.yml`

```yaml
# ansible/roles/apps/ml-tools/tasks/main.yml
# Este playbook é para a VM ai-desktop-vm
# Assume que o passthrough da GPU AMD (RX 5600XT) para esta VM foi configurado no Proxmox.

- name: "Verificar se GPU AMD está presente na VM (lspci)"
  ansible.builtin.command: lspci -nn
  register: lspci_output_vm
  changed_when: false
  failed_when: false # Não falha se o comando não encontrar, apenas registra

- name: "Debug: Saída do lspci na VM"
  ansible.builtin.debug:
    var: lspci_output_vm.stdout_lines
  when: lspci_output_vm.rc == 0

- name: "Instalar drivers AMD ROCm para RX 5600XT (Ubuntu 22.04)"
  # Tenta instalar se uma GPU AMD for detectada. Ajuste a string de detecção se necessário.
  when: "'AMD' in lspci_output_vm.stdout and ('Radeon RX 5600' in lspci_output_vm.stdout or 'Navi 10' in lspci_output_vm.stdout or '1002:731f' in lspci_output_vm.stdout)"
  ansible.builtin.block:
    - name: "Adicionar repositório AMD ROCm (ex: para Ubuntu 22.04 - Jammy)"
      ansible.builtin.apt_repository:
        repo: "deb [arch=amd64 signed-by=/etc/apt/keyrings/rocm.gpg] https://repo.radeon.com/rocm/apt/{{ rocm_version_repo | default('latest') }} {{ ansible_distribution_codename }} main"
        state: present
        filename: rocm
      vars:
        # Verifique a versão ROCm compatível com sua GPU (RX 5600XT - Navi 10) e SO (Ubuntu 22.04).
        # Versões mais recentes do ROCm podem ter descontinuado o suporte para GPUs mais antigas.
        # ROCm 5.x (e.g., 5.7) ou 6.x podem ser opções, mas verifique a matriz de compatibilidade da AMD.
        rocm_version_repo: "5.7" # Exemplo, verifique a compatibilidade!
      notify: Update apt cache after adding repo ROCm

    - name: "Adicionar chave GPG do ROCm"
      ansible.builtin.get_url:
        url: https://repo.radeon.com/rocm/rocm.gpg.key
        dest: /etc/apt/keyrings/rocm.gpg # Caminho para chaves GPG
        mode: '0644'
        force: yes # Garante a chave mais recente
      notify: Update apt cache after adding key ROCm # Handler específico para não colidir

    - name: "Instalar pacotes ROCm (drivers e SDK básico)"
      ansible.builtin.apt:
        name:
          - amdgpu-dkms # Driver do kernel
          - rocm-hip-sdk # SDK principal (inclui compilador HIP, bibliotecas) - pode ser grande
          # - rocm-opencl-sdk # Se precisar de OpenCL explicitamente
          - mesa-utils # Para verificar com glxinfo
          # - rocm-utils # Para rocminfo
        state: present
        update_cache: yes # Atualiza antes de instalar
      notify: Reboot VM for GPU drivers # Drivers de kernel geralmente requerem reboot

    - name: "Adicionar usuários aos grupos 'render' e 'video' para acesso à GPU"
      ansible.builtin.user:
        name: "{{ item }}"
        groups: render,video # Grupos que dão acesso a /dev/dri/* e /dev/kfd
        append: yes
      loop:
        - "{{ vm_ansible_user_name }}" # Usuário Ansible
        - "{{ docker_user_name_on_vm }}" # Usuário Docker (para containers que possam precisar de GPU)
  rescue:
    - name: "Falha ao tentar instalar ROCm"
      ansible.builtin.debug:
        msg: "Não foi possível instalar os drivers ROCm. Verifique a compatibilidade da GPU, a versão do ROCm e os logs de erro do apt. GPU Passthrough pode não estar funcionando corretamente."

- name: "Instalar Ollama via script oficial"
  ansible.builtin.shell: |
    curl -fsSL https://ollama.com/install.sh | sh
  args:
    creates: /usr/local/bin/ollama # Só executa se o binário Ollama não estiver instalado
  changed_when: true # Assume que sempre muda se o script for executado
  become: true # O script de instalação do Ollama precisa de sudo

- name: "Configurar Ollama systemd service para escutar em todas as interfaces e usar diretório de modelos NFS"
  ansible.builtin.block:
    - name: "Garantir que o diretório de override do serviço Ollama exista"
      ansible.builtin.file:
        path: /etc/systemd/system/ollama.service.d
        state: directory
        mode: '0755'
    - name: "Criar arquivo de override para o serviço Ollama"
      ansible.builtin.copy:
        dest: /etc/systemd/system/ollama.service.d/override.conf
        content: |
          [Service]
          # Permite que Ollama seja acessado de outras máquinas na rede (e.g., do Obsidian na sua máquina principal)
          Environment="OLLAMA_HOST=0.0.0.0:11434"
          # Define o diretório onde Ollama armazenará os modelos baixados.
          # Este caminho DEVE ser um montado NFS da ai-desktop-vm para o dataset ZFS no Proxmox.
          Environment="OLLAMA_MODELS={{ vm_nfs_mount_base_path }}/{{ zfs_rag_sources_dataset_name }}/ollama_models"
          # Adicione aqui outras variáveis de ambiente para Ollama se necessário:
          # Environment="OLLAMA_NUM_PARALLEL=1" # Limita o número de modelos carregados simultaneamente
          # Environment="OLLAMA_MAX_LOADED_MODELS=1"
          # Environment="OLLAMA_DEBUG=0"
        mode: '0644'
      notify: Reload systemd and restart Ollama # Handler para aplicar a mudança no serviço

- name: "Garantir que o diretório de modelos Ollama no volume NFS exista"
  ansible.builtin.file:
    path: "{{ vm_nfs_mount_base_path }}/{{ zfs_rag_sources_dataset_name }}/ollama_models"
    state: directory
    owner: "{{ docker_puid }}" # Ou o usuário que o serviço Ollama rodará como (geralmente 'ollama' se instalado pelo script)
    group: "{{ docker_pgid }}" # Ou o grupo 'ollama'
    mode: '0775' # Ollama precisa de permissão para escrever neste diretório (baixar modelos)
    # Verifique o usuário/grupo real com que o serviço Ollama roda (`ps aux | grep ollama`) e ajuste owner/group.
    # Se o serviço Ollama rodar como um usuário 'ollama' criado pelo script de instalação,
    # você pode precisar dar permissões mais amplas (e.g., 0777, menos seguro) ou
    # mudar o proprietário para 'ollama:ollama' se souber o UID/GID dele.
    # A melhor abordagem é garantir que o usuário do serviço Ollama corresponda ao PUID/PGID
    # ou que o PUID/PGID tenha acesso de escrita.
    # Como PUID/PGID é 1000/1000 e NFS squasha para ele, 0775 com PUID/PGID deve funcionar se Ollama herdar.
    # Alternativamente, se Ollama cria seu próprio usuário, e esse usuário não é 1000:1000,
    # e o NFS squash está ativo, Ollama não conseguirá escrever.
    # Uma solução: `chown ollama:ollama /mnt/pve_data_zfs/rag_sources/ollama_models` na VM após o NFS ser montado,
    # e ajustar as opções do NFS export no Proxmox para não fazer squash ou squashear para ollama:ollama (complexo).
    # Solução mais simples se PUID/PGID não for o usuário ollama: `mode: '0777'` no diretório de modelos.
```
!!! warning "Permissões do Diretório de Modelos Ollama"
    A configuração de permissões para `OLLAMA_MODELS` pode ser tricky. O serviço Ollama (geralmente rodando como usuário `ollama`) precisa de permissão de escrita no diretório NFS.
    1.  Se o `all_squash` do NFS no Proxmox mapeia para `{{ docker_puid }}:{{ docker_pgid }}` (e.g., 1000:1000), e o serviço Ollama NÃO roda com esse UID/GID, ele não poderá escrever.
    2.  **Soluções possíveis:**
        *   Mudar o `owner` e `group` do diretório de modelos na VM para o usuário e grupo reais com que o serviço Ollama roda (e.g., `chown ollama:ollama /mnt/pve_data_zfs/rag_sources/ollama_models` na VM). Isso requer saber o UID/GID do usuário `ollama`.
        *   Configurar o serviço Ollama para rodar como `{{ docker_puid }}:{{ docker_pgid }}` (pode exigir edição do `ollama.service`).
        *   Dar permissões mais amplas ao diretório (e.g., `mode: '0777'`), o que é menos seguro.
        *   Modificar as opções de exportação NFS no Proxmox para não fazer `all_squash` (menos recomendado para outros volumes Docker).
    A tarefa Ansible tenta `owner: "{{ docker_puid }}"`, `group: "{{ docker_pgid }}"`, `mode: '0775'`. Teste se o serviço Ollama consegue baixar modelos. Se não, ajuste as permissões ou o usuário do serviço.

#### `handlers/main.yml` (para `apps/ml-tools`)

```yaml
# ansible/roles/apps/ml-tools/handlers/main.yml
- name: Update apt cache after adding key ROCm
  ansible.builtin.apt:
    update_cache: yes

- name: Reboot VM for GPU drivers
  ansible.builtin.reboot:
    msg: "Reiniciando a VM para aplicar os drivers de GPU AMD ROCm."
    connect_timeout: 5
    reboot_timeout: 600 # Pode demorar um pouco para instalar DKMS
    pre_reboot_delay: 0
    post_reboot_delay: 60 # Espera adicional para a VM estar completamente pronta
    test_command: uptime

- name: Reload systemd and restart Ollama
  ansible.builtin.systemd:
    daemon_reload: yes
  notify: Restart Ollama service

- name: Restart Ollama service
  ansible.builtin.systemd_service:
    name: ollama
    state: restarted
    enabled: yes
```

### Portainer Agent na `ai-desktop-vm` (Opcional, mas Recomendado)

Se você deseja gerenciar as stacks Docker na `ai-desktop-vm` a partir da mesma interface Portainer que roda na `core-services-vm`:
1.  Na sua instância principal do Portainer (em `core-services-vm`), vá para "Environments" -> "+ Add environment".
2.  Selecione "Docker Standalone" e depois "Agent".
3.  Siga as instruções para implantar o container do Portainer Agent na `ai-desktop-vm`. Isso geralmente envolve rodar um comando `docker run ...` na `ai-desktop-vm`. Você pode fazer isso via SSH ou, se tiver uma GUI, via terminal.
    *   **Exemplo de comando do Portainer Agent (adapte conforme fornecido pela sua UI Portainer):**
        ```bash
        # Execute na ai-desktop-vm
        docker run -d -p 9001:9001 --name portainer_agent --restart=always -v /var/run/docker.sock:/var/run/docker.sock -v /var/lib/docker/volumes:/var/lib/docker/volumes portainer/agent:latest # Use uma tag de versão específica
        ```
    *   Certifique-se de que a porta 9001 (ou a que o Agent usar) esteja permitida no firewall UFW da `ai-desktop-vm` se o UFW estiver ativo nela.
4.  Após o Agent estar rodando na `ai-desktop-vm`, complete a adição do ambiente no Portainer principal, fornecendo o IP da `ai-desktop-vm` e a porta do Agent (e.g., `IP_AI_DESKTOP_VM:9001`).

## 7.2. Configuração do Obsidian para RAG (Exemplo)

Se você usa Obsidian e quer integrá-lo com seus LLMs locais:

1.  **Vault do Obsidian:** Idealmente, seu vault do Obsidian está sincronizado com um serviço como o Nextcloud (que rodará na `core-services-vm`), tornando suas notas acessíveis.
2.  **Plugins Essenciais no Obsidian:**
    *   **Obsidian Copilot:** (Ou similar como `Text Generator`) Para enviar prompts para LLMs.
    *   **Smart Second Brain:** Se você usar suas funcionalidades de RAG específicas.
    *   **Obsidian Custom Frames:** Para embutir a interface do Open WebUI diretamente no Obsidian.
3.  **Configuração dos Plugins:**
    *   **Obsidian Copilot / Text Generator:**
        *   Configure para apontar para a API do Ollama na sua `ai-desktop-vm`.
        *   **URL do Servidor LLM / Endpoint API:** `http://{{ ai_desktop_vm_ip_var }}:11434` (substitua `{{ ai_desktop_vm_ip_var }}` pelo IP real).
        *   Selecione o modelo que você baixou no Ollama (e.g., `mistral:7b-instruct-q4_K_M`).
    *   **Obsidian Custom Frames (para Open WebUI):**
        *   Crie um novo frame no plugin.
        *   **URL:** `https://openwebui.{{ base_domain }}` (se você expôs OpenWebUI via Traefik e Cloudflare Tunnel).
        *   Ou, para acesso puramente local (se Obsidian estiver na mesma rede que `ai-desktop-vm`): `http://{{ ai_desktop_vm_ip_var }}:PORTA_OPENWEBUI` (a porta mapeada no Docker Compose do OpenWebUI, e.g., 8080).

## 7.3. Deploy da Stack RAG via Portainer (`docker/stacks/rag/docker-compose.yml`)

Agora, implantaremos as aplicações RAG (como Open WebUI) como containers Docker na `ai-desktop-vm`.

**Ação:**
1.  No Portainer, certifique-se de que está conectado ao **endpoint da `ai-desktop-vm`** (via Agent).
2.  Vá para "Stacks" -> "+ Add stack".
3.  **Nome:** `rag-services`.
4.  **Web editor:** Cole o conteúdo do arquivo `infra-servidor-domestico/docker/stacks/rag/docker-compose.yml`:

    ```yaml
    # docker/stacks/rag/docker-compose.yml
    version: '3.9'

    # Networks:
    # Se OpenWebUI for exposto via Traefik na core-services-vm (usando File Provider),
    # esta stack na ai-desktop-vm não precisa estar na rede 'proxy' global do Traefik.
    # Ela apenas precisa expor a porta do OpenWebUI no IP da ai-desktop-vm,
    # e o Traefik na core-services-vm será configurado (via File Provider) para rotear para lá.

    services:
      open-webui:
        # Imagem oficial. Verifique tags de versão específicas para estabilidade.
        image: ghcr.io/open-webui/open-webui:main # Ou :ollama se quiser a versão mais alinhada com Ollama
        container_name: open_webui
        restart: unless-stopped
        ports:
          # Mapeia a porta 8080 do container para a porta 8080 no IP da ai-desktop-vm.
          # Traefik (rodando na core-services-vm) será configurado para rotear para este IP e porta.
          # A variável AI_DESKTOP_VM_IP_VAR virá do .env carregado no Portainer.
          - "${AI_DESKTOP_VM_IP_VAR}:8080:8080"
        volumes:
          # Caminho NFS montado na ai-desktop-vm para dados persistentes do OpenWebUI.
          # A variável RAG_STACK_OPENWEBUI_DATA_PATH virá do .env.
          - "${RAG_STACK_OPENWEBUI_DATA_PATH}:/app/backend/data"
        environment:
          # Aponta para o serviço Ollama rodando diretamente na ai-desktop-vm (não em container).
          # A variável AI_DESKTOP_VM_IP_VAR virá do .env.
          - 'OLLAMA_BASE_URL=http://${AI_DESKTOP_VM_IP_VAR}:11434'
          # Chave secreta para OpenWebUI, defina no Portainer .env ou UI.
          - 'WEBUI_SECRET_KEY=${OPENWEBUI_SECRET_KEY_RANDOM}'
          - 'PUID=${DOCKER_PUID}' # Do .env
          - 'PGID=${DOCKER_PGID}' # Do .env
          - 'TZ=${SYSTEM_TIMEZONE}' # Do .env
        # Labels Traefik NÃO SÃO USADAS AQUI se Traefik está em outra VM (core-services-vm)
        # e usa o File Provider para rotear para este serviço. Se Traefik estivesse rodando
        # na mesma ai-desktop-vm e conectado à mesma rede 'proxy', então as labels seriam usadas.

      # --- Exemplo: Open-NotebookLM (se for usar e preparou o código fonte) ---
      # open-notebooklm:
      #   # Assume que você clonou o repositório Open-NotebookLM para /opt/open-notebooklm-src na ai-desktop-vm
      #   # e que há um Dockerfile lá. Ou use uma imagem pré-construída se disponível.
      #   build:
      #     context: /opt/open-notebooklm-src # Caminho na ai-desktop-vm
      #     dockerfile: Dockerfile
      #   image: open-notebooklm-custom:latest # Nome da imagem construída
      #   container_name: open_notebooklm
      #   restart: unless-stopped
      #   ports:
      #     - "${AI_DESKTOP_VM_IP_VAR}:7860:7860" # Porta para acesso (e para Traefik File Provider)
      #   volumes: # Caminhos NFS montados na ai-desktop-vm
      #     - "${RAG_STACK_OPENNOTEBOOKLM_CONFIG_PATH}:/app/config"
      #     - "${RAG_STACK_OPENNOTEBOOKLM_INPUT_PATH}:/app/input_pdfs" # Diretório para PDFs de entrada
      #     - "${RAG_STACK_OPENNOTEBOOKLM_OUTPUT_PATH}:/app/output_mp3s" # Diretório para áudios de saída
      #   environment:
      #     # Aponta para a API compatível com OpenAI do Ollama (adicionar /v1)
      #     - 'LLM_API_BASE=http://${AI_DESKTOP_VM_IP_VAR}:11434/v1'
      #     - 'LLM_MODEL=${OPENNOTEBOOKLM_DEFAULT_MODEL}' # Ex: 'mistral:latest' ou o modelo específico baixado
      #     - 'PUID=${DOCKER_PUID}'
      #     - 'PGID=${DOCKER_PGID}'
      #     - 'TZ=${SYSTEM_TIMEZONE}'
    ```

5.  **Variáveis de Ambiente no Portainer (endpoint `ai-desktop-vm`):**
    *   **Carregue o arquivo `.env`:**
        *   Path on disk: `/opt/portainer_stack_envs/rag.env` (preparado pelo Ansible na `ai-desktop-vm`).
        *   Isso fornecerá `AI_DESKTOP_VM_IP_VAR`, `DOCKER_PUID`, `DOCKER_PGID`, `SYSTEM_TIMEZONE`, e os caminhos de volume como `RAG_STACK_OPENWEBUI_DATA_PATH`.
    *   **Adicione Secrets Manualmente:**
        *   `OPENWEBUI_SECRET_KEY_RANDOM`: Gere uma string aleatória longa (e.g., `openssl rand -hex 32`).
        *   Se estiver usando Open-NotebookLM, defina `OPENNOTEBOOKLM_DEFAULT_MODEL` para o nome do modelo Ollama que você usará (e.g., `mistral:7b-instruct-q4_K_M`).

6.  **Exposição via Traefik/Cloudflare Tunnel:**
    *   Lembre-se que o Traefik (rodando na `core-services-vm`) já foi configurado com o File Provider `dynamic_rag_services.yml` (ver Seção 5.4). Este arquivo contém as regras para rotear o tráfego de `https://openwebui.{{ base_domain }}` para `http://{{ ai_desktop_vm_ip_var }}:8080`.
    *   Certifique-se de que a variável `ai_desktop_vm_ip_var` no `dynamic_rag_services.yml.j2` (e consequentemente no arquivo gerado) corresponde ao IP real da sua `ai-desktop-vm`.
    *   Se Traefik ou Authelia forem reiniciados na `core-services-vm` após o deploy da stack RAG, eles devem carregar essas configurações.

7.  **Deploy da Stack:**
    *   Clique em "Deploy the stack" no Portainer.

8.  **Baixar Modelos no Ollama:**
    *   Conecte-se via SSH à sua `ai-desktop-vm`.
    *   Use o comando `ollama` para baixar os modelos que você deseja usar.
        ```bash
        # Exemplo para baixar Mistral 7B (quantizado, bom para começar com RAM limitada)
        ollama pull mistral:7b-instruct-q4_K_M

        # Para listar modelos baixados:
        ollama list
        ```
        Os modelos serão armazenados em `{{ vm_nfs_mount_base_path }}/{{ zfs_rag_sources_dataset_name }}/ollama_models` devido à configuração `OLLAMA_MODELS` no serviço Ollama.

9.  **Teste:**
    *   Acesse `https://openwebui.{{ base_domain }}`. Após autenticação com Authelia, você deve ver a interface do Open WebUI.
    *   No Open WebUI, você deve conseguir selecionar os modelos Ollama que foram baixados.

Esta configuração fornece uma base para explorar LLMs e RAG localmente, mesmo com as limitações de hardware.

Próximo passo: [Stack de Mídia (Plex/Jellyfin, *arrs)](08-stack-midia.md).