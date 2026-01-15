# Seção 7: Stack de Inteligência Artificial (LLM/RAG com Ollama)

Esta seção foca na configuração da sua `ai-desktop-vm` para hospedar serviços de Inteligência Artificial (IA). Especificamente, vamos configurar:

*   **Ollama:** Para rodar Modelos de Linguagem Grandes (LLMs) localmente na `ai-desktop-vm`, utilizando a GPU AMD RX 5600XT (via passthrough) para aceleração.
*   **Open WebUI:** Uma interface web amigável (anteriormente conhecida como Ollama WebUI) para interagir com os modelos Ollama. Rodará como um container Docker na `ai-desktop-vm`.
*   (Opcional) Outras aplicações de Retrieval Augmented Generation (RAG) ou ferramentas de IA podem ser adicionadas seguindo um padrão similar.

!!! warning "Limitações de Hardware e Expectativas"
    Dado o hardware do servidor (CPU Ryzen 5 5600G, GPU RX 5600XT, e a alocação de ~16-24GB RAM para a `ai-desktop-vm` no contexto de um host com 48GB), é importante definir expectativas realistas:
    *   **Tamanho dos Modelos LLM:** Você estará limitado a rodar modelos menores ou versões quantizadas de modelos maiores (e.g., modelos de 7 Bilhões de parâmetros com quantização de 4-bits como Q4_K_M, ou talvez modelos de 13B quantizados se a RAM permitir e você não rodar muitos outros simultaneamente). Modelos muito grandes (30B+, 70B+) provavelmente não rodarão ou terão performance insatisfatória.
    *   **Performance de Inferência:** A RX 5600XT fornecerá uma aceleração significativa em comparação com rodar apenas na CPU, mas não espere a performance de GPUs de data center de última geração. A velocidade de geração de tokens será moderada.
    *   **Uso Concorrente de Recursos:** Rodar LLMs é intensivo em GPU e RAM. Isso pode impactar a performance de outros serviços se a `ai-desktop-vm` também estiver hospedando outras cargas de trabalho pesadas (o que não é o plano principal aqui, mas vale a pena notar).

Esta stack é opcional e depende crucialmente da criação bem-sucedida da `ai-desktop-vm` ([Seção 3](03-provisionamento-vms.md)) e da configuração correta do passthrough da GPU RX 5600XT para esta VM ([Seção 3.4](03-provisionamento-vms.md#34-configuração-de-gpu-passthrough-host-proxmox)).

## 7.1. Preparação da VM `ai-desktop-vm` com Ansible

Antes de implantarmos os containers Docker para as aplicações RAG (como Open WebUI), precisamos preparar a `ai-desktop-vm` com os drivers de GPU necessários e instalar o serviço Ollama. O Ollama rodará diretamente como um serviço systemd na VM para ter acesso mais direto e eficiente à GPU passada, em vez de rodar dentro de um container Docker com as complexidades adicionais de passthrough de GPU para containers.

### Playbook `setup-rag-llm-volumes.yml`

Este playbook Ansible, que deve ser executado contra a `ai-desktop-vm`, realizará as seguintes tarefas chave:

1.  **Instalação de Drivers AMD ROCm:** Tenta instalar os drivers AMD ROCm (Radeon Open Compute platform) na `ai-desktop-vm` para permitir que aplicações utilizem a GPU RX 5600XT para computação.
2.  **Instalação do Serviço Ollama:** Baixa e instala o Ollama usando seu script oficial, configurando-o como um serviço systemd.
3.  **Configuração do Ollama:**
    *   Modifica o serviço systemd do Ollama para que ele escute em todas as interfaces de rede da VM (permitindo acesso de outras máquinas na sua LAN, como seu desktop com Obsidian).
    *   Configura o Ollama para armazenar os modelos LLM baixados em um diretório no volume NFS (`{{ vm_nfs_mount_base_path }}/{{ zfs_rag_sources_dataset_name }}/ollama_models`), garantindo que os modelos persistam e sejam armazenados no pool ZFS.
4.  **Preparação de Volumes para Aplicações RAG Docker:**
    *   Cria os subdiretórios necessários no volume NFS (e.g., para os dados do Open WebUI em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/openwebui/data`).
5.  **Preparação do Arquivo `.env`:**
    *   Gera o arquivo `/opt/portainer_stack_envs/rag.env` na `ai-desktop-vm` com as variáveis necessárias para a stack Docker RAG (e.g., caminhos de volume, PUID/PGID, IP da VM).

**Ação:** Execute o playbook a partir da sua máquina de controle Ansible:
```bash
ansible-playbook ansible/playbooks/setup-rag-llm-volumes.yml --ask-vault-pass
```

### Detalhes Importantes do Role `ansible/roles/apps/ml-tools/`

Este role, chamado pelo playbook acima, é responsável pela instalação do ROCm e Ollama.

    **Principais Ações do Role `ml-tools`:**
    *   Verifica a presença de uma GPU AMD na VM (via `lspci`).
    *   Se detectada, tenta adicionar o repositório AMD ROCm e instalar os pacotes `amdgpu-dkms` e `rocm-hip-sdk`.
        !!! warning "Versão do ROCm e Compatibilidade da GPU"
            A compatibilidade entre versões do ROCm e GPUs AMD mais antigas (como a RX 5600XT, baseada na arquitetura Navi 10/RDNA 1) pode ser um desafio. Versões muito recentes do ROCm podem ter descontinuado o suporte oficial. No template do role, `rocm_version_repo: "5.7"` foi usado como exemplo. **Você pode precisar pesquisar a última versão do ROCm que suporta oficialmente sua GPU para Ubuntu 22.04.** Se o ROCm não instalar ou funcionar, Ollama ainda poderá rodar em modo CPU, mas será significativamente mais lento.
    *   Adiciona os usuários relevantes (`{{ vm_ansible_user_name }}`, `{{ docker_user_name_on_vm }}`) aos grupos `render` e `video` na VM para permitir acesso aos dispositivos da GPU.
    *   Instala Ollama usando seu script oficial.
    *   Cria um arquivo de override para o serviço systemd `ollama.service` para definir `OLLAMA_HOST=0.0.0.0:11434` (para escutar em todas as interfaces) e `OLLAMA_MODELS` (para o diretório NFS).
    *   Garante que o diretório de modelos Ollama no NFS exista e tenha permissões adequadas.
        !!! important "Permissões do Diretório `OLLAMA_MODELS`"
            Conforme discutido na Seção 7.1 do documento original, o serviço Ollama (que geralmente roda como um usuário `ollama` dedicado, criado pelo script de instalação) precisa de permissão de escrita no diretório NFS `{{ vm_nfs_mount_base_path }}/{{ zfs_rag_sources_dataset_name }}/ollama_models`. Se o `all_squash` do NFS mapeia para `{{ docker_puid }}:{{ docker_pgid }}` e o usuário `ollama` tem um UID/GID diferente, ele não poderá escrever.
            **Soluções (teste após a execução do Ansible):**
            1.  Verifique como usuário `ollama` está rodando: `ps aux | grep ollama` na `ai-desktop-vm`. Anote seu UID/GID.
            2.  Se diferente de `{{ docker_puid }}:{{ docker_pgid }}`, você pode:
                *   Mudar o proprietário do diretório na VM: `sudo chown ollama:ollama /mnt/pve_data_zfs/rag_sources/ollama_models`
                *   Ou, de forma mais permissiva (menos segura), dar permissão de escrita para todos: `sudo chmod 0777 /mnt/pve_data_zfs/rag_sources/ollama_models` (não ideal).
            A tarefa Ansible tenta `owner: "{{ docker_puid }}"`, `group: "{{ docker_pgid }}"`, `mode: '0775'`. Teste se o serviço Ollama consegue baixar modelos após o deploy. Se não, ajuste as permissões.

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


### Configuração do Portainer Agent na `ai-desktop-vm` (Opcional, mas Recomendado)

Se você deseja gerenciar as stacks Docker que rodarão na `ai-desktop-vm` (como Open WebUI) a partir da sua interface principal do Portainer (que roda na `core-services-vm`), você precisará instalar o **Portainer Agent** na `ai-desktop-vm`.

1.  **Na sua instância principal do Portainer** (acessível em `https://portainer.{{ base_domain }}`):
    *   No menu lateral, vá para "**Environments**".
    *   Clique em "**+ Add environment**".
2.  **Selecione o Tipo de Ambiente:**
    *   Escolha "**Docker Standalone**".
    *   Clique em "**Start Wizard**".
3.  **Escolha o Método de Conexão:**
    *   Selecione "**Agent**".
4.  **Siga as Instruções para Implantar o Agente:**
    *   Portainer fornecerá um comando `docker run ...` para você executar na `ai-desktop-vm`. Conecte-se à `ai-desktop-vm` via SSH.
    *   **Antes de rodar o comando, certifique-se que o Docker Engine está instalado na `ai-desktop-vm`.** Se você seguiu o plano de apenas instalar Docker na `core-services-vm`, você precisará instalar Docker na `ai-desktop-vm` também.
        ```bash
        # Comandos para instalar Docker Engine na ai-desktop-vm (se ainda não feito)
        # (similar ao que o role 'infra/docker' faz)
        sudo apt update
        sudo apt install -y apt-transport-https ca-certificates curl software-properties-common
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        sudo apt update
        sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
        sudo systemctl enable docker --now
        sudo usermod -aG docker {{ vm_ansible_user_name }} # Para seu usuário Ansible na VM
        # Pode ser necessário novo login/reboot para o grupo docker ter efeito
        ```
    *   **Execute o comando do Portainer Agent fornecido pela UI do Portainer na `ai-desktop-vm`**. Ele será algo como:
        ```bash
        # Exemplo (o comando real será fornecido pela sua UI Portainer):
        docker run -d -p 9001:9001 --name portainer_agent --restart=always \
          -v /var/run/docker.sock:/var/run/docker.sock \
          -v /var/lib/docker/volumes:/var/lib/docker/volumes \
          portainer/agent:2.19.4 # Use a mesma versão ou uma compatível com seu Portainer Server
        ```
    *   **Firewall UFW:** Se o UFW estiver ativo na `ai-desktop-vm` (e foi configurado pelo role `common`), certifique-se de que a porta `9001` (ou a porta que o Agent usar) esteja permitida para tráfego de entrada vindo da `core-services-vm`. Adicione uma regra se necessário: `sudo ufw allow from IP_DA_CORE_SERVICES_VM to any port 9001 proto tcp comment 'Portainer Agent'`.
5.  **Complete a Adição do Ambiente no Portainer Principal:**
    *   De volta à UI do Portainer (onde você obteve o comando do Agent), preencha os detalhes do novo ambiente:
        *   **Name:** Dê um nome (e.g., `ai-desktop-docker`).
        *   **Environment URL / IP Address:** O endereço IP da sua `ai-desktop-vm` seguido da porta do Agent (e.g., `{{ ai_desktop_vm_ip_var }}:9001`).
    *   Clique em "Connect" ou "Add environment".

Agora você poderá selecionar o endpoint `ai-desktop-docker` no Portainer para gerenciar containers e stacks rodando naquela VM.

## 7.2. Configuração do Obsidian para Integração RAG (Exemplo)

Se você utiliza o [Obsidian.md](https://obsidian.md/) para gerenciamento de conhecimento e deseja integrá-lo com os LLMs rodando localmente via Ollama, aqui estão algumas dicas:

1.  **Vault do Obsidian e Acesso aos Arquivos:**
    *   Idealmente, seu vault principal do Obsidian está armazenado ou sincronizado com o [Nextcloud](../01-manual-implementacao/09-stack-produtividade-automacao.md#stack-de-produtividade-nextcloud-dockerstacksproductivitydocker-composeyml) (que roda na `core-services-vm`). Isso torna suas notas acessíveis de múltiplos dispositivos.
    *   Para aplicações RAG que precisam processar suas notas, elas precisariam de acesso a esses arquivos. Se rodando na `ai-desktop-vm`, você poderia montar o diretório de dados do Nextcloud (via NFS da `core-services-vm` para a `ai-desktop-vm`, ou sincronizar de outra forma) se a aplicação RAG precisar ler diretamente do sistema de arquivos.

2.  **Plugins Essenciais no Obsidian para Interação com LLMs:**
    *   **Obsidian Copilot:** (Ou um similar como `Text Generator`) Permite enviar prompts de texto selecionado ou notas inteiras para um endpoint LLM e inserir a resposta.
    *   **Smart Second Brain:** Um plugin mais focado em RAG, que pode ajudar a criar embeddings de suas notas e realizar buscas semânticas.
    *   **Obsidian Custom Frames:** Permite embutir páginas web (como a interface do Open WebUI) diretamente como um painel dentro do Obsidian.

3.  **Configuração dos Plugins no Obsidian:**
    *   **Para Obsidian Copilot / Text Generator (ou similar):**
        *   Nas configurações do plugin, você precisará definir o endpoint da API do LLM.
        *   **URL do Servidor LLM / Endpoint API:** `http://{{ ai_desktop_vm_ip_var }}:11434` (substitua `{{ ai_desktop_vm_ip_var }}` pelo IP real da sua `ai-desktop-vm` onde Ollama está escutando).
        *   **Seleção de Modelo:** O plugin geralmente permite que você especifique qual modelo Ollama usar (e.g., `mistral:7b-instruct-q4_K_M`, `llama3:8b-instruct-q4_K_M`). O modelo deve ter sido previamente baixado no Ollama na `ai-desktop-vm`.
    *   **Para Obsidian Custom Frames (se quiser embutir Open WebUI):**
        *   No plugin Custom Frames, crie um novo frame.
        *   **URL:** `https://openwebui.{{ base_domain }}` (se você expôs Open WebUI via Traefik e Cloudflare Tunnel, como planejado).
        *   Ou, para acesso puramente local (se seu desktop com Obsidian estiver na mesma rede que a `ai-desktop-vm` e você não quiser passar pela internet): `http://{{ ai_desktop_vm_ip_var }}:PORTA_DO_OPENWEBUI` (a porta que o container OpenWebUI mapeia na `ai-desktop-vm`, e.g., `8080`).

## 7.3. Deploy da Stack RAG via Portainer (`docker/stacks/rag/docker-compose.yml`)

Agora, vamos implantar as aplicações RAG, como o Open WebUI, como containers Docker na `ai-desktop-vm`.

**Ação:**

1.  **Selecione o Endpoint Correto no Portainer:**
    *   No Portainer, certifique-se de que você está conectado ao endpoint que representa o Docker Engine da sua **`ai-desktop-vm`** (aquele que você configurou com o Portainer Agent).

2.  **Adicionar a Nova Stack:**
    *   Vá para "Stacks" -> "+ Add stack".
    *   **Name:** Dê um nome, e.g., `rag-services`.

3.  **Web Editor (Cole o Docker Compose):**
    *   Copie o conteúdo do arquivo `home-server/docker/stacks/rag/docker-compose.yml` e cole-o no editor web do Portainer:

    ```yaml
    # docker/stacks/rag/docker-compose.yml
    version: '3.9'

    # Esta stack roda na ai-desktop-vm.
    # A exposição para o mundo exterior (via Traefik na core-services-vm)
    # é feita usando o File Provider do Traefik, que aponta para o IP e porta
    # do OpenWebUI expostos pela ai-desktop-vm.
    # Portanto, esta stack não precisa se conectar à rede 'proxy' global do Traefik.

    services:
      open-webui:
        # Verifique a tag mais recente ou uma específica para estabilidade em:
        # https://github.com/open-webui/open-webui/pkgs/container/open-webui
        image: ghcr.io/open-webui/open-webui:main # Ou :ollama para alinhar com Ollama
        container_name: open_webui
        restart: unless-stopped
        ports:
          # Mapeia a porta 8080 do container para a porta 8080 no IP da ai-desktop-vm.
          # Traefik (rodando na core-services-vm) será configurado (via dynamic_rag_services.yml)
          # para rotear o tráfego de https://openwebui.{{ base_domain }}
          # para http://${AI_DESKTOP_VM_IP_VAR}:8080.
          # A variável ${AI_DESKTOP_VM_IP_VAR} virá do arquivo .env carregado no Portainer.
          - "${AI_DESKTOP_VM_IP_VAR}:8080:8080"
        volumes:
          # Caminho NFS montado na ai-desktop-vm para dados persistentes do OpenWebUI.
          # A variável ${RAG_STACK_OPENWEBUI_DATA_PATH} virá do .env.
          - "${RAG_STACK_OPENWEBUI_DATA_PATH}:/app/backend/data"
        environment:
          # Aponta para o serviço Ollama rodando diretamente na ai-desktop-vm (não em outro container).
          # A variável ${AI_DESKTOP_VM_IP_VAR} virá do .env.
          - 'OLLAMA_BASE_URL=http://${AI_DESKTOP_VM_IP_VAR}:11434'
          # Chave secreta para segurança interna do OpenWebUI. Defina no Portainer (via .env ou manualmente).
          - 'WEBUI_SECRET_KEY=${OPENWEBUI_SECRET_KEY_RANDOM}'
          - 'PUID=${DOCKER_PUID}' # Do .env
          - 'PGID=${DOCKER_PGID}' # Do .env
          - 'TZ=${SYSTEM_TIMEZONE}' # Do .env
          # Desabilitar telemetria se desejado
          # - 'OPEN_WEBUI_TELEMETRY_DISABLED=true'
        # Labels Traefik NÃO SÃO USADAS AQUI DIRETAMENTE, pois o roteamento é feito
        # pelo Traefik na core-services-vm usando o File Provider que aponta para
        # o IP e porta desta VM.

      # --- Exemplo (Comentado): Open-NotebookLM (se você for usar) ---
      # open-notebooklm:
      #   # Se você preparou o código fonte via Ansible role 'open-notebooklm-source-prep'
      #   # para, por exemplo, /opt/open-notebooklm-src na ai-desktop-vm, e lá tem um Dockerfile.
      #   # build:
      #   #   context: /opt/open-notebooklm-src # Caminho DENTRO da ai-desktop-vm
      #   #   dockerfile: Dockerfile
      #   # image: open-notebooklm-custom:latest # Nome que você dará à imagem construída
      #   # Ou, se houver uma imagem pré-construída oficial/comunitária:
      #   # image: algum_registro/open-notebooklm:tag
      #   container_name: open_notebooklm
      #   restart: unless-stopped
      #   ports:
      #     # Porta que o Open-NotebookLM escuta internamente, mapeada para a ai-desktop-vm.
      #     # Traefik na core-services-vm apontaria para ${AI_DESKTOP_VM_IP_VAR}:7860.
      #     - "${AI_DESKTOP_VM_IP_VAR}:7860:7860"
      #   volumes: # Caminhos NFS montados na ai-desktop-vm, variáveis do .env
      #     - "${RAG_STACK_OPENNOTEBOOKLM_CONFIG_PATH}:/app/config"
      #     - "${RAG_STACK_OPENNOTEBOOKLM_INPUT_PATH}:/app/input_pdfs" # Para seus PDFs
      #     - "${RAG_STACK_OPENNOTEBOOKLM_OUTPUT_PATH}:/app/output_mp3s" # Para áudios gerados
      #   environment:
      #     # Aponta para a API compatível com OpenAI do Ollama (geralmente /v1)
      #     - 'LLM_API_BASE=http://${AI_DESKTOP_VM_IP_VAR}:11434/v1'
      #     - 'LLM_MODEL=${OPENNOTEBOOKLM_DEFAULT_MODEL}' # e.g., 'mistral:latest'
      #     - 'PUID=${DOCKER_PUID}'
      #     - 'PGID=${DOCKER_PGID}'
      #     - 'TZ=${SYSTEM_TIMEZONE}'
    ```

4.  **Variáveis de Ambiente no Portainer (endpoint `ai-desktop-vm`):**
    *   **Carregue o arquivo `.env`:**
        *   Em "Environment variables" (modo avançado), clique em "Load variables from .env file".
        *   **Path on disk:** `/opt/portainer_stack_envs/rag.env` (Este arquivo foi preparado pelo playbook Ansible `setup-rag-llm-volumes.yml` na `ai-desktop-vm`).
        *   Isso deve preencher variáveis como `AI_DESKTOP_VM_IP_VAR`, `DOCKER_PUID`, `DOCKER_PGID`, `SYSTEM_TIMEZONE`, e os caminhos de volume (e.g., `RAG_STACK_OPENWEBUI_DATA_PATH`).
    *   **Adicione Secrets Manualmente:**
        *   `OPENWEBUI_SECRET_KEY_RANDOM`: Gere uma string aleatória longa e segura (e.g., usando `openssl rand -hex 32` na sua máquina de controle) e cole o valor aqui.
        *   Se estiver usando Open-NotebookLM (descomentado no compose), defina `OPENNOTEBOOKLM_DEFAULT_MODEL` para o nome exato do modelo Ollama que você pretende usar com ele (e.g., `mistral:7b-instruct-q4_K_M`).

5.  **Configuração de Acesso Externo (Traefik na `core-services-vm`):**
    *   Lembre-se que o Traefik, rodando na `core-services-vm`, já foi configurado com o **File Provider** que inclui o arquivo `dynamic_rag_services.yml` (gerado pelo template `dynamic_rag_services.yml.j2` na Seção 5.4).
    *   Este arquivo `dynamic_rag_services.yml` contém as regras para rotear o tráfego de `https://openwebui.{{ base_domain }}` para `http://{{ ai_desktop_vm_ip_var }}:8080` (e similarmente para `notebooklm.{{ base_domain }}` se você o configurou).
    *   Certifique-se de que a variável `ai_desktop_vm_ip_var` no template `dynamic_rag_services.yml.j2` (e, consequentemente, no arquivo gerado na `core-services-vm`) corresponde ao IP real da sua `ai-desktop-vm` conforme definido no seu inventário Ansible.
    *   Se o Traefik ou Authelia na `core-services-vm` forem reiniciados após o deploy da stack RAG na `ai-desktop-vm`, eles devem carregar essas configurações de roteamento. Nenhuma label Traefik é necessária diretamente no compose da stack RAG, pois o roteamento é "empurrado" pelo File Provider do Traefik.

6.  **Deploy da Stack RAG:**
    *   No Portainer (no endpoint da `ai-desktop-vm`), clique em "**Deploy the stack**".
    *   Monitore os logs dos containers (especialmente `open_webui`) para verificar se há erros.

7.  **Baixar Modelos no Ollama (na `ai-desktop-vm`):**
    *   Conecte-se via SSH à sua `ai-desktop-vm`.
    *   Use o comando `ollama` para baixar os modelos de linguagem que você deseja usar com Open WebUI e outras aplicações RAG.
        ```bash
        # Exemplo para baixar Mistral 7B (quantizado, bom para começar com RAM limitada)
        ollama pull mistral:7b-instruct-q4_K_M

        # Exemplo para Llama 3 8B Instruct (quantizado)
        ollama pull llama3:8b-instruct-q4_K_M

        # Para listar modelos já baixados:
        ollama list
        ```
        Os modelos serão armazenados no diretório NFS configurado (`{{ vm_nfs_mount_base_path }}/{{ zfs_rag_sources_dataset_name }}/ollama_models`) devido à variável de ambiente `OLLAMA_MODELS` no serviço systemd do Ollama.

8.  **Teste a Configuração:**
    *   Acesse `https://openwebui.{{ base_domain }}` no seu navegador.
    *   Você deverá ser redirecionado para o portal Authelia para autenticação.
    *   Após o login, você deverá ver a interface do Open WebUI.
    *   No Open WebUI, você deve conseguir selecionar os modelos Ollama que foram baixados na `ai-desktop-vm` e interagir com eles.
    *   Verifique se a GPU está sendo utilizada (e.g., usando `radeontop` ou `rocm-smi` na `ai-desktop-vm` enquanto um modelo está processando).

Esta configuração estabelece uma base poderosa para explorar LLMs e aplicações RAG localmente, tirando proveito da sua GPU dedicada e mantendo os dados e modelos de forma persistente.

Próximo passo: [Stack de Mídia (Plex/Jellyfin, *arrs)](08-stack-midia.md).

---

## 7.4. Ampliando Horizontes: Integrando APIs de LLM Externas com LiteLLM

Rodar LLMs localmente com Ollama é fantástico para privacidade, velocidade em tarefas simples e experimentação sem custo. No entanto, como vimos, o hardware doméstico possui limitações. Para tarefas que exigem modelos mais poderosos (como o GPT-4, Claude 3 Opus ou Gemini 1.5 Pro), ou para garantir alta disponibilidade sem sobrecarregar seu servidor, a integração com APIs de LLM externas é a solução ideal. 

Nesta seção, implementaremos uma arquitetura híbrida e robusta usando o **LiteLLM**, uma ferramenta excepcional que atua como um proxy unificado para mais de 100 serviços de LLM. 

### Por que usar LiteLLM? A Estratégia Híbrida

O LiteLLM nos permite tratar todos os modelos, tanto o seu Ollama local quanto as APIs externas, através de uma única interface compatível com a API da OpenAI. Isso oferece vantagens incríveis:

*   **Flexibilidade Total:** Alterne entre modelos locais e externos (ou até mesmo entre diferentes provedores de nuvem) com uma simples mudança na configuração, sem precisar alterar o código das suas aplicações (como o Open WebUI).
*   **Roteamento Inteligente:** Configure regras para que requisições mais simples e baratas sejam direcionadas para seu Ollama local, enquanto as mais complexas são enviadas para um modelo de ponta na nuvem.
*   **Controle de Custos e Orçamentos:** Estabeleça limites de gastos diários, semanais ou mensais por modelo ou por chave de API para evitar surpresas na fatura.
*   **Fallback e Redundância:** Se uma chamada para a API da OpenAI falhar, o LiteLLM pode automaticamente tentar a mesma requisição na API do Azure, Anthropic ou Google, garantindo que sua aplicação continue funcionando.
*   **Logging e Auditoria Centralizados:** Tenha um registro unificado de todas as chamadas de LLM, custos associados e performance, essencial para otimização.

### Implementação da Stack com LiteLLM

Vamos adicionar o LiteLLM à nossa `ai-desktop-vm` como um container Docker. Ele se tornará o novo ponto de entrada para todas as aplicações que consomem LLMs. O fluxo será: `Aplicação (Open WebUI) -> LiteLLM -> (Ollama ou API Externa)`.

#### 1. Atualização do Ansible Vault com Chaves de API

Primeiro, precisamos armazenar de forma segura as chaves de API dos provedores que você deseja usar. Adicione as seguintes variáveis ao seu arquivo `ansible/vault.yml`:

```yaml
# ansible/vault.yml
# ... (outras variáveis existentes)

# --- API Keys para LLMs Externos ---
llm_api_keys:
  openai: "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  anthropic: "sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  google_gemini: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  # Adicione outras chaves conforme necessário (e.g., cohere, azure)
```

!!! important "Segurança das Chaves"
    Trate essas chaves como senhas. Nunca as armazene em texto plano em seus arquivos de configuração ou código. O Ansible Vault é a maneira correta de gerenciá-las.

#### 2. Criação do Arquivo de Configuração do LiteLLM

O LiteLLM é configurado através de um arquivo `config.yaml`. Vamos criar um template para ele que será preenchido pelo Ansible. Crie o arquivo `ansible/templates/litellm_config.yaml.j2`:

```yaml
# ansible/templates/litellm_config.yaml.j2

general_settings:
  master_key: "{{ litellm_master_key }}" # Chave para acessar a UI e APIs do LiteLLM

litellm_settings:
  # Ativa o cache para reduzir custos com requisições repetidas
  cache: 
    type: "local"
    # Para cache em Redis (recomendado para produção), veja a documentação do LiteLLM
    # type: "redis"
    # host: "<redis_host>"
    # port: <redis_port>
    # password: "<redis_password>"

  # Fallback: Se o primeiro modelo da lista falhar, tenta o próximo
  fallbacks: [{"gpt-4o": ["claude-3-opus", "gemini-1.5-pro"]}, {"ollama/llama3": ["ollama/phi3"]}]

  # Orçamentos para controle de custos
  budget_manager:
    - total_budget: 50.0 # Orçamento total em USD
      user_budgets:
        - user_id: "admin-user"
          budget: 25.0
        - user_id: "dev-user"
          budget: 10.0

# Definição dos modelos que o LiteLLM irá expor
model_list:
  # --- Modelos de API Externa ---
  - model_name: gpt-4o
    litellm_params:
      model: gpt-4o
      api_key: "{{ llm_api_keys.openai }}"

  - model_name: claude-3-opus
    litellm_params:
      model: claude-3-opus-20240229
      api_key: "{{ llm_api_keys.anthropic }}"

  - model_name: gemini-1.5-pro
    litellm_params:
      model: gemini/gemini-1.5-pro-latest
      api_key: "{{ llm_api_keys.google_gemini }}"

  # --- Modelos Locais (Ollama) ---
  # O LiteLLM se conectará ao seu serviço Ollama na mesma VM
  - model_name: ollama/llama3
    litellm_params:
      model: ollama/llama3 # O nome exato do modelo no Ollama
      api_base: "http://{{ ai_desktop_vm_ip_var }}:11434" # IP da própria VM

  - model_name: ollama/phi3
    litellm_params:
      model: ollama/phi3
      api_base: "http://{{ ai_desktop_vm_ip_var }}:11434"

# Roteamento: Estratégias para direcionar as requisições
router_settings:
  # Rota mais simples: envia para o modelo mais barato/rápido primeiro
  - mode: simple
    models: ["ollama/phi3", "ollama/llama3", "gpt-4o", "claude-3-opus"]

  # Rota por custo/latência (requer benchmarks)
  # - mode: weighted-random
  #   models:
  #     - {model: ollama/phi3, weight: 0.8}
  #     - {model: gpt-4o, weight: 0.2}
```

E adicione a variável `litellm_master_key` ao seu `ansible/vault.yml` para proteger a UI do LiteLLM.

#### 3. Atualização do Playbook Ansible

Agora, vamos modificar o playbook `setup-rag-llm-volumes.yml` para incluir a criação do diretório de configuração do LiteLLM e o deploy do seu `config.yaml`.

Adicione estas tarefas ao final do playbook:

```yaml
# Em ansible/playbooks/setup-rag-llm-volumes.yml

# ... (tarefas existentes para Ollama e Open WebUI)

- name: "Preparar diretório de configuração para LiteLLM"
  ansible.builtin.file:
    path: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/litellm/config"
    state: directory
    owner: "{{ docker_puid }}"
    group: "{{ docker_pgid }}"
    mode: '0775'

- name: "Deploy do arquivo de configuração do LiteLLM (config.yaml)"
  ansible.builtin.template:
    src: ../templates/litellm_config.yaml.j2
    dest: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/litellm/config/config.yaml"
    owner: "{{ docker_puid }}"
    group: "{{ docker_pgid }}"
    mode: '0644'
```

#### 4. Novo Docker Compose para LiteLLM

Crie um novo arquivo `docker/stacks/ai/litellm-compose.yml`. Este será uma nova stack no Portainer.

```yaml
# docker/stacks/ai/litellm-compose.yml
version: '3.9'

networks:
  proxy:
    name: proxy
    external: true

services:
  litellm:
    image: ghcr.io/berriai/litellm:main-v1.34.19 # Use uma tag de versão estável
    container_name: litellm_proxy
    restart: unless-stopped
    networks:
      - proxy
    volumes:
      # Mapeia o arquivo de configuração que o Ansible criou
      - "${AI_STACK_LITELLM_CONFIG_PATH}/config.yaml:/app/config.yaml"
    environment:
      - LITELLM_MASTER_KEY=${LITELLM_MASTER_KEY_FROM_PORTAINER_ENV}
      - TZ=${SYSTEM_TIMEZONE}
    ports:
      # Expõe a porta da API do LiteLLM na rede da VM
      - "{{ ai_desktop_vm_ip_var }}:4000:4000"
    command: ["--config", "/app/config.yaml", "--port", "4000", "--host", "0.0.0.0"]
    labels:
      traefik.enable: "true"
      traefik.http.routers.litellm.rule: "Host(`llm.{{ base_domain }}`)" # Subdomínio para a UI do LiteLLM
      traefik.http.routers.litellm.entrypoints: "websecure"
      traefik.http.routers.litellm.tls.certresolver: "letsencrypt"
      traefik.http.routers.litellm.service: "litellm-svc"
      traefik.http.routers.litellm.middlewares: "authelia@docker"
      traefik.http.services.litellm-svc.loadbalancer.server.port: "4000"
```

**Ação de Deploy:**

1.  Execute novamente o playbook Ansible para criar os arquivos e diretórios: `ansible-playbook ansible/playbooks/setup-rag-llm-volumes.yml --ask-vault-pass`
2.  No Portainer, adicione uma nova stack chamada `ai-litellm`.
3.  Cole o conteúdo do `litellm-compose.yml`.
4.  Em "Environment variables", adicione a secret `LITELLM_MASTER_KEY_FROM_PORTAINER_ENV` com o valor do seu vault.
5.  Faça o deploy da stack.

#### 5. Reconfigurando o Open WebUI

O passo final é dizer ao Open WebUI para parar de falar diretamente com o Ollama e, em vez disso, falar com o LiteLLM.

1.  **Acesse a interface do Open WebUI.**
2.  Vá para "Settings" -> "Connections".
3.  Em vez de apontar para o endereço do Ollama (`http://<ip_da_vm>:11434`), aponte para o endereço do LiteLLM: `http://<ip_da_vm>:4000`.
4.  Salve a configuração.

Agora, quando você for na seleção de modelos do Open WebUI, verá a lista completa que definiu no `config.yaml` do LiteLLM, incluindo `gpt-4o`, `claude-3-opus`, `ollama/llama3`, etc. O Open WebUI enviará a requisição para o LiteLLM, e este decidirá para onde roteá-la, seja para o Ollama local ou para uma API na nuvem, de forma totalmente transparente para o usuário.

Com esta implementação, seu home server agora possui uma capacidade de IA verdadeiramente elástica e poderosa, combinando o melhor dos mundos local e em nuvem.
