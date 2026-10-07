# Seção 4: Configuração Base das VMs Ubuntu (Docker, Portainer, Cliente NFS)

Com as máquinas virtuais (`core-services-vm` e, opcionalmente, `ai-desktop-vm`) devidamente provisionadas ([Seção 3](03-provisionamento-vms.md)), o próximo passo é realizar a configuração base essencial dentro delas. Este processo é automatizado pelo Ansible e inclui:

* Instalação de pacotes comuns e utilitários.
* Configuração do cliente NFS para montar os volumes de dados ZFS compartilhados pelo host Proxmox.
* Criação de um usuário e grupo dedicados (`dockeruser`, `dockergroup`) para possuir os arquivos nos volumes NFS e para os containers Docker utilizarem (via PUID/PGID).
* Configuração do firewall UFW (Uncomplicated Firewall).
* Instalação do Node Exporter para monitoramento.
* Instalação do Docker Engine e Docker Compose na `core-services-vm`.
* Deploy do container Portainer na `core-services-vm` para gerenciamento gráfico do Docker.
* (Opcional) Instalação de um ambiente desktop na `ai-desktop-vm` se `GUI_ENABLED=true`.

Utilizaremos o playbook Ansible `setup-base-ubuntu.yml`. Este playbook orquestra a aplicação de dois roles principais:
1. `common`: Aplicado a todas as VMs no grupo `ubuntu_vms`.
2. `infra/docker`: Aplicado especificamente à `core-services-vm`.
E, condicionalmente, o role `apps/desktop-environment`.

## 4.1. Role Ansible `common` (`ansible/roles/common/`)

Este role é fundamental, pois aplica configurações e instala pacotes que são comuns e necessários para todas as nossas VMs baseadas em Ubuntu.

### `tasks/main.yml`

Este arquivo contém as tarefas principais do role `common`.

```yaml title="ansible/roles/common/tasks/main.yml"
# ansible/roles/common/tasks/main.yml

- name: "Aguardar cloud-init finalizar completamente na VM"
  ansible.builtin.command: cloud-init status --wait
  changed_when: false # Este comando não altera o estado, apenas espera
  tags: always # Garante que esta task sempre rode

- name: "Atualizar cache APT e instalar pacotes essenciais (incluindo nfs-common)"
  ansible.builtin.apt:
    name:
      - git
      - curl
      - wget
      - htop
      - tmux # Multiplexador de terminal, muito útil
      - ufw # Uncomplicated Firewall
      - python3-apt # Necessário para alguns módulos Ansible de gerenciamento de pacotes
      - qemu-guest-agent # Já deve ter sido instalado no template, mas garante
      - nfs-common # Cliente NFS, essencial para montar volumes do Proxmox
      - unattended-upgrades # Para atualizações automáticas de segurança
      - apt-listchanges # Mostra o changelog de pacotes durante upgrades
      # Adicione outros utilitários comuns que você usa
    state: present
    update_cache: yes
  notify: Configure unattended-upgrades # Handler para configurar atualizações automáticas

- name: "Garantir que o serviço qemu-guest-agent está rodando e habilitado"
  ansible.builtin.systemd_service:
    name: qemu-guest-agent
    state: started
    enabled: yes

- name: "Configurar fuso horário da VM"
  community.general.timezone:
    name: "{{ system_timezone }}" # Variável do vault.yml

# --- Configuração do Cliente NFS para montar volumes ZFS do Proxmox Host ---
- name: "Criar ponto de montagem base para volumes NFS do Proxmox Host na VM"
  ansible.builtin.file:
    path: "{{ vm_nfs_mount_base_path }}" # Ex: /mnt/pve_data_zfs (de group_vars/all/main.yml)
    state: directory
    owner: root
    group: root
    mode: '0755'

- name: "Montar datasets ZFS do Proxmox Host via NFS na VM"
  ansible.posix.mount:
    src: "{{ hostvars[groups['proxmox_hosts'][0]]['ansible_host'] }}:{{ zfs_base_pool_path }}/{{ item.dataset_name }}" # Ex: 192.168.1.10:/data/docker-volumes
    path: "{{ vm_nfs_mount_base_path }}/{{ item.dataset_name }}"       # Ex: /mnt/pve_data_zfs/docker-volumes
    fstype: nfs
    # Opções de montagem NFS otimizadas. vers=4.2 é recomendado se suportado pelo host Proxmox.
    # rsize e wsize maiores podem melhorar a performance em redes gigabit.
    opts: "rw,sync,hard,intr,bg,noatime,nodiratime,rsize=1048576,wsize=1048576,vers=4.2"
    state: mounted # Garante que está montado e adiciona a entrada correspondente ao /etc/fstab
  loop: # Itera sobre os datasets ZFS definidos em group_vars/all/main.yml
    - { dataset_name: "{{ zfs_docker_volumes_dataset_name }}" }
    - { dataset_name: "{{ zfs_media_dataset_name }}" }
    - { dataset_name: "{{ zfs_downloads_dataset_name }}" }
    # Monta o dataset de RAG Sources apenas se a VM atual estiver no grupo 'ai_desktop_vm'
    # e se zfs_rag_sources_dataset_name estiver definido.
    - { dataset_name: "{{ zfs_rag_sources_dataset_name }}", when_condition: "'ai-desktop-vm' in group_names and zfs_rag_sources_dataset_name is defined" }
  when: item.when_condition is not defined or item.when_condition # Permite loop condicional
  # NOTA: O dataset de backups (zfs_backups_dataset_name) geralmente não precisa ser montado nas VMs.

# --- Criação de Usuários e Grupos Docker ---
# Este usuário e grupo serão donos dos arquivos nos volumes NFS,
# e os containers Docker rodarão com estes PUID/PGID.
- name: "Criar grupo '{{ docker_group_name_on_vm }}' com GID específico"
  ansible.builtin.group:
    name: "{{ docker_group_name_on_vm }}" # De group_vars/all/main.yml
    gid: "{{ docker_pgid }}" # Do vault.yml
    state: present

- name: "Criar usuário '{{ docker_user_name_on_vm }}' com UID e grupo específicos"
  ansible.builtin.user:
    name: "{{ docker_user_name_on_vm }}" # De group_vars/all/main.yml
    uid: "{{ docker_puid }}" # Do vault.yml
    group: "{{ docker_group_name_on_vm }}" # Grupo criado acima
    groups: sudo # Opcional: Adiciona ao grupo sudo para conveniência. Pode ser removido se não desejado.
    append: yes
    shell: /bin/bash
    comment: "Usuário para containers Docker e proprietário de volumes NFS"
    # Define uma senha (pode ser a mesma do usuário Ansible da VM ou outra do vault)
    # A senha é hasheada com SHA512.
    password: "{{ vm_ansible_user_password_plain | password_hash('sha512') }}"
    state: present

- name: "Adicionar usuário Ansible da VM ('{{ vm_ansible_user_name }}') ao grupo '{{ docker_group_name_on_vm }}'"
  ansible.builtin.user:
    name: "{{ vm_ansible_user_name }}" # Usuário Ansible criado via Cloud-Init
    groups: "{{ docker_group_name_on_vm }}" # Adiciona a este grupo
    append: yes
  # O usuário Ansible já é sudo por padrão via Cloud-Init.

# --- Configuração do Firewall UFW (Uncomplicated Firewall) ---
# Aplicado condicionalmente:
# - Sempre na 'core-services-vm'.
# - Na 'ai-desktop-vm' apenas se a flag GUI_ENABLED for true para ela no inventário.
- name: "Configurar e Habilitar Firewall UFW"
  community.general.ufw:
    state: enabled
    policy: deny # Política padrão: negar todo tráfego de entrada
    rules:
      # Regras básicas
      - { rule: 'allow', name: 'ssh' } # Ou port: '22', proto: 'tcp'
      - { rule: 'allow', port: '80', proto: 'tcp', comment: 'Allow HTTP for Traefik redirect and local services' }
      - { rule: 'allow', port: '443', proto: 'tcp', comment: 'Allow HTTPS for Traefik' }
      # Portas para Node Exporter (Prometheus scrape)
      - { rule: 'allow', port: '9100', proto: 'tcp', comment: 'Allow Node Exporter' }
      # Porta para Glances WebUI (se não acessado via Traefik)
      - { rule: 'allow', port: '61208', proto: 'tcp', comment: 'Allow Glances WebUI' }
      # Para VNC na ai-desktop-vm se GUI_ENABLED=true
      # Esta regra só será efetiva se o UFW for aplicado na ai-desktop-vm.
      - { rule: 'allow', port: '5901', proto: 'tcp', comment: 'Allow VNC :1 (TCP port for display 1)' }
    default_outgoing_policy: allow # Permite todo tráfego de saída por padrão
  when: inventory_hostname == 'core-services-vm' or (inventory_hostname == 'ai-desktop-vm' and hostvars[inventory_hostname]['GUI_ENABLED'] | default(false) | bool)

# --- Instalação do Node Exporter (para monitoramento da VM por Prometheus) ---
- name: "Verificar se Node Exporter já está instalado na VM (binário)"
  ansible.builtin.stat:
    path: /usr/local/bin/node_exporter
  register: node_exporter_vm_binary

- name: "Instalar Node Exporter na VM (se não existir)"
  when: not node_exporter_vm_binary.stat.exists
  block: # Agrupa tarefas para instalação do Node Exporter
    - name: "Checar última release do Node Exporter no GitHub (VM)"
      ansible.builtin.uri:
        url: "https://api.github.com/repos/prometheus/node_exporter/releases/latest"
        return_content: yes
      register: node_exporter_vm_latest_release
      run_once: true # Evita múltiplas chamadas à API se o role for aplicado a várias VMs em paralelo

    - name: "Definir URL de download do Node Exporter (VM)"
      ansible.builtin.set_fact:
        node_exporter_vm_version: "{{ node_exporter_vm_latest_release.json.tag_name | regex_replace('^v(.*)$', '\\1') }}"
        node_exporter_vm_download_url: "https://github.com/prometheus/node_exporter/releases/download/v{{ node_exporter_vm_version }}/node_exporter-{{ node_exporter_vm_version }}.linux-amd64.tar.gz"

    - name: "Baixar Node Exporter (VM)"
      ansible.builtin.get_url:
        url: "{{ node_exporter_vm_download_url }}"
        dest: "/tmp/node_exporter-{{ node_exporter_vm_version }}.linux-amd64.tar.gz"
        mode: '0644'

    - name: "Descompactar Node Exporter (VM)"
      ansible.builtin.unarchive:
        src: "/tmp/node_exporter-{{ node_exporter_vm_version }}.linux-amd64.tar.gz"
        dest: "/tmp/"
        remote_src: yes # Indica que o arquivo de origem está no host remoto (a VM)

    - name: "Mover binário Node Exporter para /usr/local/bin (VM)"
      ansible.builtin.copy:
        src: "/tmp/node_exporter-{{ node_exporter_vm_version }}.linux-amd64/node_exporter"
        dest: "/usr/local/bin/node_exporter"
        mode: '0755'
        remote_src: yes # Indica que o arquivo de origem está no host remoto

    - name: "Criar usuário de sistema 'node_exporter' (VM)"
      ansible.builtin.user:
        name: node_exporter
        shell: /bin/false
        system: yes
        create_home: no

    - name: "Criar arquivo de serviço systemd para Node Exporter (VM)"
      ansible.builtin.template:
        src: node_exporter_vm.service.j2 # Template específico para VM
        dest: /etc/systemd/system/node_exporter.service
        mode: '0644'
      notify: Reload systemd and restart node_exporter_vm # Handler para recarregar systemd e reiniciar o serviço

    - name: "Limpar arquivos temporários de instalação do Node Exporter (VM)"
      ansible.builtin.file:
        path: "{{ item }}"
        state: absent
      loop:
        - "/tmp/node_exporter-{{ node_exporter_vm_version }}.linux-amd64.tar.gz"
        - "/tmp/node_exporter-{{ node_exporter_vm_version }}.linux-amd64"
  # Fim do block de instalação do Node Exporter

- name: "Garantir que Node Exporter (VM) está habilitado e rodando"
  ansible.builtin.systemd_service:
    name: node_exporter
    state: started
    enabled: yes
  # Esta task roda mesmo se o Node Exporter já existia, garantindo que o serviço está OK.
```

### `templates/node_exporter_vm.service.j2`

Este template define o serviço systemd para o Node Exporter que roda dentro das VMs.

```systemd title="ansible/roles/common/templates/node_exporter_vm.service.j2"
# ansible/roles/common/templates/node_exporter_vm.service.j2
[Unit]
Description=Node Exporter for Prometheus (VM)
Wants=network-online.target
After=network-online.target

[Service]
User=node_exporter
Group=node_exporter
Type=simple
ExecStart=/usr/local/bin/node_exporter \
    --collector.systemd \
    --collector.filesystem \
    --collector.network_dev \
    --collector.vmstat \
    --collector.meminfo \
    --collector.diskstats \
    --collector.processes \
    --collector.cpu \
    --collector.loadavg \
    --collector.netstat \
    --collector.stat \
    --collector.time \
    --collector.pressure
    # Coletores relevantes para VMs. Evite coletores que tentem acessar hardware específico do host.

[Install]
WantedBy=multi-user.target
```

### `handlers/main.yml`

Handlers para o role `common`.

```yaml title="ansible/roles/common/handlers/main.yml"
# ansible/roles/common/handlers/main.yml
- name: Reload systemd and restart node_exporter_vm
  ansible.builtin.systemd:
    daemon_reload: yes
  notify: Restart node_exporter_vm_service # Encadeia para o próximo handler

- name: Restart node_exporter_vm_service
  ansible.builtin.systemd_service:
    name: node_exporter
    state: restarted
    enabled: yes

- name: Configure unattended-upgrades
  ansible.builtin.copy:
    content: |
      // Configurações para atualizações automáticas.
      // Arquivo: /etc/apt/apt.conf.d/20auto-upgrades
      APT::Periodic::Update-Package-Lists "1";
      APT::Periodic::Download-Upgradeable-Packages "1";
      APT::Periodic::AutocleanInterval "7";
      APT::Periodic::Unattended-Upgrade "1";
    dest: /etc/apt/apt.conf.d/20auto-upgrades
    owner: root
    group: root
    mode: '0644'
  # Para uma configuração mais detalhada de unattended-upgrades (e.g., Allowed-Origins, Blacklist, Email),
  # você pode usar um template para /etc/apt/apt.conf.d/50unattended-upgrades.
  # Exemplo:
  # - name: Configure unattended-upgrades details (50unattended-upgrades)
  #   ansible.builtin.template:
  #     src: 50unattended-upgrades.j2
  #     dest: /etc/apt/apt.conf.d/50unattended-upgrades
  #     owner: root
  #     group: root
  #     mode: '0644'
```

* **Principais Tarefas do Role `common`:**
  * Aguardar a finalização completa do `cloud-init`.
  * Atualizar o cache APT e instalar pacotes essenciais como `git`, `curl`, `htop`, `ufw`, `nfs-common`, `unattended-upgrades`, `qemu-guest-agent`.
  * Garantir que o serviço `qemu-guest-agent` esteja ativo.
  * Configurar o fuso horário da VM usando a variável `{{ system_timezone }}`.
  * **Configurar Cliente NFS:**
    * Criar o ponto de montagem base na VM (e.g., `/mnt/pve_data_zfs`, definido por `{{ vm_nfs_mount_base_path }}`).
    * Montar os datasets ZFS compartilhados pelo host Proxmox (e.g., `docker-volumes`, `media`, `downloads`, `rag_sources`) nos subdiretórios correspondentes, adicionando entradas ao `/etc/fstab` para persistência.
  * **Criar Usuário e Grupo Docker:**
    * Criar o grupo `{{ docker_group_name_on_vm }}` com o GID `{{ docker_pgid }}`.
    * Criar o usuário `{{ docker_user_name_on_vm }}` com o UID `{{ docker_puid }}`, associado ao grupo acima, e com uma senha definida.
    * Adicionar o usuário Ansible da VM (`{{ vm_ansible_user_name }}`) também ao grupo `{{ docker_group_name_on_vm }}`.
  * **Configurar Firewall UFW:** Habilitar UFW com política padrão `deny` e permitir portas essenciais (SSH, HTTP/S para Traefik, Node Exporter, Glances, VNC se GUI habilitada).
  * **Instalar Node Exporter (VM):** Baixar, instalar e configurar o serviço systemd para o Node Exporter, usando o template `node_exporter_vm.service.j2`.

## 4.2. Role Ansible `docker` (`ansible/roles/infra/docker/`)

Este role é específico para a `core-services-vm` (ou qualquer outra VM que você designar para rodar a maioria dos seus containers Docker e o Portainer). Suas principais responsabilidades são:

* Instalar o Docker Engine e o plugin Docker Compose.
* Adicionar os usuários relevantes (`{{ vm_ansible_user_name }}`, `{{ docker_user_name_on_vm }}`) ao grupo `docker` do sistema para permitir a execução de comandos Docker sem `sudo`.
* Criar o diretório NFS para os dados persistentes do Portainer.
* Criar a rede Docker `proxy` (que será usada pelo Traefik e outros serviços expostos).
* Fazer o deploy do container Portainer CE, configurando-o com:
  * Mapeamento do socket Docker.
  * Volume persistente para seus dados (no diretório NFS preparado).
  * Conexão à rede `proxy`.
  * Labels Traefik para que o Portainer seja automaticamente descoberto e exposto via `https://portainer.{{ base_domain }}` e protegido por Authelia.

### `tasks/main.yml`

```yaml title="ansible/roles/infra/docker/tasks/main.yml"
# ansible/roles/infra/docker/tasks/main.yml
# Instala Docker Engine e Portainer CE na VM designada (core-services-vm).

- name: "Adicionar chave GPG oficial do Docker"
  ansible.builtin.get_url:
    url: https://download.docker.com/linux/ubuntu/gpg
    dest: /etc/apt/keyrings/docker.gpg # Novo caminho recomendado para chaves GPG
    mode: '0644'
    force: true # Sobrescreve se já existir, para garantir a chave mais recente

- name: "Adicionar repositório Docker"
  ansible.builtin.apt_repository:
    repo: "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu {{ ansible_distribution_release }} stable"
    state: present
    filename: docker # Nome do arquivo .list em /etc/apt/sources.list.d/
    update_cache: yes # Atualiza o cache após adicionar o repo

- name: "Instalar Docker Engine, CLI, Containerd e plugins Compose/Buildx"
  ansible.builtin.apt:
    name:
      - docker-ce
      - docker-ce-cli
      - containerd.io
      - docker-buildx-plugin
      - docker-compose-plugin # Para `docker compose` (v2)
    state: present

- name: "Garantir que o serviço Docker está rodando e habilitado"
  ansible.builtin.systemd_service:
    name: docker
    state: started
    enabled: yes

- name: "Adicionar usuários ao grupo 'docker' do sistema para permitir execução de comandos Docker sem sudo"
  ansible.builtin.user:
    name: "{{ item }}"
    groups: docker # Grupo 'docker' é criado automaticamente pela instalação do Docker CE
    append: yes
  loop:
    - "{{ vm_ansible_user_name }}"    # Usuário Ansible da VM
    - "{{ docker_user_name_on_vm }}" # Usuário dedicado para volumes Docker
  notify: Reiniciar VM para aplicar mudanças de grupo Docker # Ou pedir logout/login do usuário

- name: "Criar diretório para dados persistentes do Portainer (via NFS)"
  ansible.builtin.file:
    # Caminho no host (VM core-services-vm) onde o volume do Portainer será montado.
    # Este caminho DEVE existir DENTRO da VM e ser um ponto de montagem NFS do Proxmox Host.
    # {{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }} é o caminho base NFS na VM.
    path: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/portainer/data"
    state: directory
    owner: "{{ docker_puid }}" # PUID do vault.yml (usuário que rodará o container Portainer, ou root)
    group: "{{ docker_pgid }}" # PGID do vault.yml
    mode: '0755' # Permissões para o container Portainer escrever.
  # A criação do diretório base no dataset ZFS do Proxmox host (e.g., /data/docker-volumes/portainer/data)
  # pode ser feita aqui também ou assumir que o dataset pai já existe.
  # Para simplicidade, esta task garante o subdiretório no montado NFS.

- name: "Criar rede Docker 'proxy' se não existir (para Traefik e serviços expostos)"
  community.docker.docker_network:
    name: proxy
    state: present
    # Outras opções como 'driver: bridge' são padrão.

- name: "Deploy Portainer CE container"
  community.docker.docker_container:
    name: portainer
    image: portainer/portainer-ce:2.19.4 # Use uma versão específica e estável. Verifique a mais recente.
    restart_policy: unless-stopped
    security_opt: ["no-new-privileges:true"] # Boa prática de segurança
    ports:
      # Mapeia portas apenas no IP da VM 'core-services-vm' para evitar conflitos e melhor controle.
      # Acesso principal via Traefik na porta 443. Estas são para acesso direto se necessário.
      - "{{ hostvars[inventory_hostname]['ansible_host'] }}:9443:9443" # HTTPS principal do Portainer
      - "{{ hostvars[inventory_hostname]['ansible_host'] }}:9000:9000" # HTTP (redireciona para 9443, pode ser omitido se só usar Traefik)
      - "{{ hostvars[inventory_hostname]['ansible_host'] }}:8000:8000" # Porta para o Edge Agent do Portainer (opcional)
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock" # Permite Portainer gerenciar o Docker local
      # Caminho no host (VM core-services-vm) onde o volume NFS do Portainer está montado
      - "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/portainer/data:/data" # Dados persistentes do Portainer
    networks:
      - proxy # Conecta Portainer à rede 'proxy' para ser descoberto pelo Traefik
    labels: # Labels para Traefik descobrir e rotear para Portainer
      traefik.enable: "true"
      # Roteador para Portainer
      traefik.http.routers.portainer.rule: "Host(`portainer.{{ base_domain }}`)" # base_domain do vault.yml
      traefik.http.routers.portainer.entrypoints: "websecure" # Usa o entrypoint HTTPS do Traefik
      traefik.http.routers.portainer.tls.certresolver: "letsencrypt" # Usa Let's Encrypt para SSL
      traefik.http.routers.portainer.service: "portainer-svc" # Nome do serviço Traefik para Portainer
      # Serviço Traefik para Portainer
      traefik.http.services.portainer-svc.loadbalancer.server.port: "9443" # Porta interna do Portainer (HTTPS)
      traefik.http.services.portainer-svc.loadbalancer.server.scheme: "https" # Esquema para o backend
      # Middleware de Autenticação Authelia
      # Refere-se ao middleware Authelia que será definido no docker-compose do Authelia (Seção 5).
      traefik.http.routers.portainer.middlewares: "authelia@docker"
```

### `handlers/main.yml`

Handler para o role `docker`.

```yaml title="ansible/roles/infra/docker/handlers/main.yml"
# ansible/roles/infra/docker/handlers/main.yml
- name: Reiniciar VM para aplicar mudanças de grupo Docker
  ansible.builtin.reboot:
    msg: "Reiniciando a VM para que as mudanças de associação ao grupo 'docker' tenham efeito para os usuários."
    connect_timeout: 5
    reboot_timeout: 300 # Tempo máximo para a VM reiniciar e SSH estar disponível
    pre_reboot_delay: 0
    post_reboot_delay: 30 # Espera após o reboot para garantir que SSH esteja pronto
    test_command: uptime # Comando para verificar se a VM está de volta
  # Este handler é chamado se a task de adicionar usuário ao grupo 'docker' fizer alguma mudança.
  # É necessário para que o usuário Ansible e dockeruser possam rodar comandos Docker sem sudo
  # em sessões SSH subsequentes sem precisar fazer logout/login manual.
```

## 4.3. Playbook `ansible/playbooks/setup-base-ubuntu.yml`

Este playbook orquestra a aplicação dos roles `common` e `docker` (e `apps/desktop-environment` condicionalmente) às VMs apropriadas.

Certifique-se de que o arquivo `ansible/playbooks/setup-base-ubuntu.yml` exista com o seguinte conteúdo:

```yaml title="ansible/playbooks/setup-base-ubuntu.yml"
# ansible/playbooks/setup-base-ubuntu.yml
# Configura a base para todas as VMs Ubuntu e instala Docker/Portainer na VM de containers.

- hosts: ubuntu_vms # Alvo: todas as VMs definidas no grupo 'ubuntu_vms' do inventário
  become: yes # Tarefas nos roles 'common' e 'docker' exigem privilégios de root
  vars_files:
    - ../inventories/home/group_vars/all/vault.yml
  # Variáveis de group_vars/all/main.yml são carregadas automaticamente

  roles:
    - role: common # Aplica configurações base, UFW, Node Exporter VM a todas as VMs Ubuntu

- hosts: core-services-vm # Alvo específico para instalar Docker e o container Portainer
  become: yes
  vars_files:
    - ../inventories/home/group_vars/all/vault.yml # Necessário para base_domain nas labels do Portainer
  roles:
    - role: infra/docker # Instala Docker Engine e o container Portainer

# Opcional: Instalar ambiente gráfico em VMs específicas
# A variável GUI_ENABLED deve ser definida no inventário para os hosts desejados.
# Exemplo em ansible/inventories/home/hosts.ini:
# ai-desktop-vm ansible_host=192.168.15.12 GUI_ENABLED=true
- hosts: ubuntu_vms # Verifica todas as VMs Ubuntu que podem ter a flag
  become: yes
  tasks:
    - name: "Incluir role para ambiente desktop (se GUI_ENABLED for true para o host)"
      ansible.builtin.include_role:
        name: apps/desktop-environment # Role definido na Seção 3.5
      vars:
        # Passa a flag para o role, convertendo para booleano e tratando ausência da variável
        install_gui_flag: "{{ hostvars[inventory_hostname]['GUI_ENABLED'] | default(false) | bool }}"
      when: hostvars[inventory_hostname]['GUI_ENABLED'] | default(false) | bool # Só executa se a flag for true
```

### Executando o Playbook `setup-base-ubuntu.yml`

1. **Verifique os Roles:** Certifique-se de que os roles `common`, `infra/docker`, e `apps/desktop-environment` (se for usar a funcionalidade de GUI) estão criados e preenchidos com o código correto nos seus respectivos diretórios dentro de `ansible/roles/`.
2. **Execute a Partir da Máquina de Controle:** Na sua máquina de controle Ansible, navegue até a raiz do seu projeto `home-server/`.
3. **Execute o Playbook:**

    ```bash
    ansible-playbook ansible/playbooks/setup-base-ubuntu.yml --ask-vault-pass
    ```

    Você será solicitado a fornecer a senha do Ansible Vault.

!!! note "Possível Reinício das VMs"
    O role `infra/docker` inclui um handler que reiniciará a VM (`core-services-vm`) se o usuário Ansible (`{{ vm_ansible_user_name }}`) ou o `{{ docker_user_name_on_vm }}` forem adicionados ao grupo `docker` do sistema pela primeira vez. Isso é para garantir que as novas associações de grupo tenham efeito imediato para esses usuários em sessões SSH subsequentes, permitindo que eles executem comandos `docker` sem `sudo`.

Após a execução bem-sucedida deste playbook:

* Todas as suas VMs Ubuntu terão as configurações base (NFS client, UFW, Node Exporter, etc.).
* A `core-services-vm` terá o Docker Engine instalado e o container Portainer CE rodando.
* A `ai-desktop-vm`, se `GUI_ENABLED=true` foi definido para ela no inventário, terá o ambiente XFCE e TightVNCServer instalados.

Com esta base sólida, suas VMs estão prontas para o próximo passo crucial: a [Implementação da Rede Segura](05-rede-segura.md), que configurará Traefik, Cloudflare Tunnel e Authelia.
