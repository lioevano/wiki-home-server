---
description: "Configuração base das VMs Ubuntu com Ansible: pacotes, fuso horário, cliente NFS, Docker, Portainer e o coletor Grafana Alloy."
---

# Seção 4: Configuração Base das VMs Ubuntu (Docker, Portainer, Cliente NFS)

Com as máquinas virtuais (`core-services-vm` e, opcionalmente, `ai-desktop-vm`) devidamente provisionadas ([Seção 3](03-provisionamento-vms.md)), o próximo passo é realizar a configuração base essencial dentro delas. Este processo é automatizado pelo Ansible e inclui:

* Instalação de pacotes comuns e utilitários.
* Configuração do cliente NFS para montar os volumes de dados ZFS compartilhados pelo host Proxmox.
* Criação de um usuário e grupo dedicados (`dockeruser`, `dockergroup`) para possuir os arquivos nos volumes NFS e para os containers Docker utilizarem (via PUID/PGID).
* Configuração do firewall UFW (Uncomplicated Firewall).
* Instalação do Grafana Alloy, coletor de logs e métricas ([seção 4.4](#44-coleta-com-grafana-alloy-ansiblerolesinfraalloy)).
* Instalação do Docker Engine e Docker Compose na `core-services-vm`.
* Deploy do container Portainer na `core-services-vm` para gerenciamento gráfico do Docker.
* (Opcional) Instalação de um ambiente desktop na `ai-desktop-vm` se `GUI_ENABLED=true`.

Utilizaremos o playbook Ansible `setup-base-ubuntu.yml`. Este playbook orquestra a aplicação de três roles principais:
1. `common`: Aplicado a todas as VMs no grupo `ubuntu_vms`.
2. `infra/docker`: Aplicado especificamente à `core-services-vm`.
3. `infra/alloy`: Aplicado a todas as VMs, depois do Docker (o Alloy lê os containers pelo socket e pelo `/var/lib/docker`).
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
    src: "{{ hostvars[groups['proxmox_hosts'][0]]['ansible_host'] }}:{{ zfs_base_pool_path }}/{{ item.dataset_name }}" # Ex: 192.168.15.66:/data/docker-volumes
    path: "{{ vm_nfs_mount_base_path }}/{{ item.dataset_name }}"       # Ex: /mnt/pve_data_zfs/docker-volumes
    fstype: nfs
    # Opções de montagem NFS otimizadas. vers=4.2 é recomendado se suportado pelo host Proxmox.
    # rsize e wsize maiores podem melhorar a performance em redes gigabit.
    # Um item pode trocar as opções (ex.: 'files' só leitura na VM de IA).
    # _netdev + x-systemd.mount-timeout (e não 'bg', que o systemd trata como nofail): a montagem fica ordenada
    # antes do remote-fs.target, então o Docker (After=remote-fs.target) espera o NFS; com o NFS fora, ela
    # desiste em 60 s e o boot segue.
    opts: "{{ item.opts | default('rw,sync,hard,intr,_netdev,x-systemd.mount-timeout=60s,noatime,nodiratime,rsize=1048576,wsize=1048576,vers=4.2') }}"
    state: mounted # Garante que está montado e adiciona a entrada correspondente ao /etc/fstab
  loop: # Itera sobre os datasets ZFS definidos em group_vars/all/main.yml
    - { dataset_name: "{{ zfs_docker_volumes_dataset_name }}" }
    - { dataset_name: "{{ zfs_media_dataset_name }}" }
    # Arquivos do Nextcloud também na VM de IA, só leitura: origem do conversor de documentos (página 12).
    - { dataset_name: "{{ zfs_files_dataset_name }}", when_condition: "'ai_desktop' in group_names", opts: "ro,hard,intr,_netdev,x-systemd.mount-timeout=60s,noatime,nodiratime,rsize=1048576,vers=4.2" }
    # Fotos (Immich) e arquivos (Nextcloud) na core-services-vm, onde rodam as stacks photos e cloud.
    - { dataset_name: "{{ zfs_photos_dataset_name }}", when_condition: "'core_services' in group_names" }
    - { dataset_name: "{{ zfs_files_dataset_name }}", when_condition: "'core_services' in group_names" }
    # Vaults do Obsidian (segundo cérebro, página 12): só na VM de IA (grupo 'ai_desktop' do inventário).
    - { dataset_name: "{{ zfs_notes_dataset_name }}", when_condition: "'ai_desktop' in group_names" }
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

# --- Firewall UFW (Uncomplicated Firewall) ---
# Em todas as VMs: entrada negada por padrão, saída liberada. Vale para os serviços do próprio host (SSH,
# Alloy na 12345, VNC). Portas publicadas pelo Docker não passam pelo UFW: elas são limitadas pela cadeia
# HOMESERVER na DOCKER-USER (firewall_docker_portas, role infra/docker; página 14) e pela autenticação de cada serviço.
- name: "UFW: liberar SSH (antes de ligar, para não perder a conexão)"
  community.general.ufw:
    rule: allow
    port: '22'
    proto: tcp
    comment: "SSH"

- name: "UFW: liberar HTTP e HTTPS do Traefik na core-services-vm"
  community.general.ufw:
    rule: allow
    port: "{{ item }}"
    proto: tcp
    comment: "Traefik"
  loop: ['80', '443']
  when: inventory_hostname in groups['core_services']

- name: "UFW: liberar o VNC na VM com ambiente gráfico (GUI_ENABLED)"
  community.general.ufw:
    rule: allow
    port: '5901'
    proto: tcp
    comment: "VNC :1"
  when: hostvars[inventory_hostname]['GUI_ENABLED'] | default(false) | bool

- name: "UFW: negar entrada por padrão"
  community.general.ufw:
    default: deny
    direction: incoming

- name: "UFW: liberar saída por padrão"
  community.general.ufw:
    default: allow
    direction: outgoing

- name: "UFW: ligar"
  community.general.ufw:
    state: enabled

```

### `handlers/main.yml`

Handlers para o role `common`.

```yaml title="ansible/roles/common/handlers/main.yml"
# ansible/roles/common/handlers/main.yml
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
    * Montar os datasets ZFS compartilhados pelo host Proxmox (`docker-volumes` e `media` em todas; `photos` e `files` na core; `notes` e `files` só leitura na VM de IA) nos subdiretórios correspondentes, adicionando entradas ao `/etc/fstab` para persistência.
  * **Criar Usuário e Grupo Docker:**
    * Criar o grupo `{{ docker_group_name_on_vm }}` com o GID `{{ docker_pgid }}`.
    * Criar o usuário `{{ docker_user_name_on_vm }}` com o UID `{{ docker_puid }}`, associado ao grupo acima, e com uma senha definida.
    * Adicionar o usuário Ansible da VM (`{{ vm_ansible_user_name }}`) também ao grupo `{{ docker_group_name_on_vm }}`.
  * **Configurar Firewall UFW:** em **todas** as VMs, entrada negada por padrão; libera SSH (antes de ligar o firewall), HTTP/S do Traefik só na `core-services-vm` e VNC só onde `GUI_ENABLED` é verdadeiro. A porta 12345 do Alloy é liberada pelo role `infra/alloy`. Portas publicadas pelo Docker não passam pelo UFW: quem as limita é o firewall do role `docker` (abaixo).

## 4.2. Role Ansible `docker` (`ansible/roles/infra/docker/`)

Este role roda em todas as VMs Ubuntu (`ubuntu_vms`). A variável `docker_portainer_mode` (em `ansible/roles/infra/docker/defaults/main.yml`) decide o que cada uma recebe além do Docker: `server` na `core-services-vm` (o Portainer completo, a rede `proxy` e o diretório no NFS) e `agent` nas demais (o **Portainer Agent** na porta 9001, publicada só no IP da LAN, pelo qual o Portainer central gerencia as stacks daquela VM). As portas publicadas pelo Docker não passam pelo UFW. O agente tem duas proteções: o firewall do role (cadeia `HOMESERVER` na `DOCKER-USER`, gerada de `firewall_docker_portas`), que só deixa a `core-services-vm` alcançar a 9001 pela LAN ([seção 14](14-vpn-tailscale.md#firewall-das-portas-publicadas-pelo-docker)), e o segredo `portainer_agent_secret` do vault (`AGENT_SECRET`), que o Portainer central também recebe. Suas principais responsabilidades são:

* Instalar o Docker Engine e o plugin Docker Compose.
* Adicionar os usuários relevantes (`{{ vm_ansible_user_name }}`, `{{ docker_user_name_on_vm }}`) ao grupo `docker` do sistema para permitir a execução de comandos Docker sem `sudo`.
* Na `core-services-vm`: criar o diretório NFS para os dados persistentes do Portainer.
* Na `core-services-vm`: criar a rede Docker `proxy` (que será usada pelo Traefik e outros serviços expostos).
* Nas demais VMs: fazer o deploy do Portainer Agent (`portainer_agent_image`), com o socket do Docker e o `AGENT_SECRET`.
* Na `core-services-vm`: fazer o deploy do container Portainer CE, configurando-o com:
  * Mapeamento do socket Docker.
  * Volume persistente para seus dados (no diretório NFS preparado).
  * Conexão à rede `proxy`.
  * Labels Traefik para que o Portainer seja automaticamente descoberto e exposto via `https://portainer.{{ base_domain }}` e protegido por Authelia.

### `tasks/main.yml`

```yaml title="ansible/roles/infra/docker/tasks/main.yml"
# ansible/roles/infra/docker/tasks/main.yml
# Instala Docker Engine em todas as VMs Ubuntu; Portainer CE na core-services-vm e Portainer Agent nas demais.

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

# Antes da instalação: o daemon já sobe assim, sem imagens a migrar. Com o image store do containerd
# (padrão no Docker 29) o cAdvisor do Alloy não encontra os containers (seção 4.4).
- name: "Garantir o diretório /etc/docker"
  ansible.builtin.file:
    path: /etc/docker
    state: directory
    mode: '0755'

# default-address-pools: as redes Docker saem só de 172.16.0.0/12 (blocos /24). As regras de UFW que confiam
# nessa faixa valem por construção, e o Docker nunca usa 192.168.0.0/16, onde está a LAN.
- name: "Configurar o daemon do Docker sem o image store do containerd"
  ansible.builtin.copy:
    dest: /etc/docker/daemon.json
    content: |
      {
        "features": {
          "containerd-snapshotter": false
        },
        "default-address-pools": [
          {"base": "172.16.0.0/12", "size": 24}
        ]
      }
    owner: root
    group: root
    mode: '0644'
  notify: Reiniciar Docker # numa VM já instalada, a configuração nova só vale com o daemon reiniciado

# Ordem de boot: o Docker sobe depois das montagens NFS (remote-fs.target), para nenhum container nascer com a
# pasta vazia por baixo. Wants (e não Requires): com o NFS fora, a core ainda sobe Traefik e Authelia.
- name: "Garantir o drop-in do serviço Docker"
  ansible.builtin.file:
    path: /etc/systemd/system/docker.service.d
    state: directory
    mode: '0755'

- name: "Docker depois das montagens de rede"
  ansible.builtin.copy:
    dest: /etc/systemd/system/docker.service.d/10-montagens.conf
    content: |
      [Unit]
      After=remote-fs.target
      Wants=remote-fs.target
    owner: root
    group: root
    mode: '0644'
  notify: Reiniciar Docker

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
    daemon_reload: true # lê o drop-in de montagens

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
  when: docker_portainer_mode == 'server'

- name: "Criar rede Docker 'proxy' se não existir (para Traefik e serviços expostos)"
  community.docker.docker_network:
    name: proxy
    state: present
    # Outras opções como 'driver: bridge' são padrão.
  when: docker_portainer_mode == 'server' # O Traefik só roda na core-services-vm

- name: "Deploy Portainer CE container"
  community.docker.docker_container:
    name: portainer
    image: "{{ portainer_ce_image }}" # versão fixada em defaults/main.yml (a mesma do agente)
    # HTTP na 9000 só dentro da rede Docker 'proxy' (não é publicada): é por onde o MCP ops (página 13) fala com a
    # API do Portainer. Publicá-la mandaria senha e chave de API em texto claro pela LAN.
    command: ["--http-enabled"]
    restart_policy: unless-stopped
    security_opt: ["no-new-privileges:true"] # Boa prática de segurança
    ports:
      # Mapeia portas apenas no IP da VM 'core-services-vm' para evitar conflitos e melhor controle.
      # Acesso principal via Traefik na porta 443. Estas são para acesso direto se necessário.
      - "{{ hostvars[inventory_hostname]['ansible_host'] }}:9443:9443" # HTTPS principal do Portainer
      - "{{ hostvars[inventory_hostname]['ansible_host'] }}:8000:8000" # Porta para o Edge Agent do Portainer (opcional)
    env:
      # Segredo compartilhado com o Portainer Agent das outras VMs: o agente só atende quem o conhece.
      AGENT_SECRET: "{{ portainer_agent_secret }}"
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
      traefik.http.routers.portainer.middlewares: "authelia-forwardauth@docker"
  when: docker_portainer_mode == 'server'

# Nas demais VMs (ai-desktop-vm), o Portainer Agent: o Portainer central gerencia as stacks dela por aqui.
# Porta só no IP da LAN, aceita só da core (firewall_docker_portas, abaixo) e protegida pelo AGENT_SECRET
# (o mesmo do Portainer server): sem ele, o agente recusa a conexão.
- name: "Deploy Portainer Agent container"
  community.docker.docker_container:
    name: portainer_agent
    image: "{{ portainer_agent_image }}"
    restart_policy: unless-stopped
    security_opt: ["no-new-privileges:true"]
    ports:
      - "{{ hostvars[inventory_hostname]['ansible_host'] }}:9001:9001"
    env:
      AGENT_SECRET: "{{ portainer_agent_secret }}"
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock"
      - "/var/lib/docker/volumes:/var/lib/docker/volumes"
  when: docker_portainer_mode == 'agent'

# Firewall das portas publicadas pelo Docker (página 14): o UFW não vê esse tráfego. As regras ficam na cadeia
# DOCKER-USER e são refeitas antes de cada início do Docker (Before= e PartOf=docker.service): quando os
# containers sobem, as regras já estão lá.
- name: "Script do firewall das portas publicadas pelo Docker"
  ansible.builtin.template:
    src: firewall-docker.sh.j2
    dest: /usr/local/sbin/firewall-docker.sh
    owner: root
    group: root
    mode: '0750'
  notify: Aplicar firewall do Docker

- name: "Unit do firewall das portas publicadas pelo Docker"
  ansible.builtin.copy:
    dest: /etc/systemd/system/firewall-docker.service
    owner: root
    group: root
    mode: '0644'
    content: |
      [Unit]
      Description=Regras da cadeia DOCKER-USER (portas publicadas pelo Docker; página 14)
      Before=docker.service
      PartOf=docker.service

      [Service]
      Type=oneshot
      RemainAfterExit=true
      ExecStart=/usr/local/sbin/firewall-docker.sh

      [Install]
      WantedBy=docker.service
  notify: Aplicar firewall do Docker

- name: "Habilitar o firewall das portas publicadas pelo Docker"
  ansible.builtin.systemd_service:
    name: firewall-docker.service
    enabled: true
    state: started
    daemon_reload: true
  when: not ansible_check_mode # no --check a unit só foi simulada
```

### `handlers/main.yml`

Handler para o role `docker`.

```yaml title="ansible/roles/infra/docker/handlers/main.yml"
# ansible/roles/infra/docker/handlers/main.yml
# daemon.json ou drop-in mudados numa VM já instalada. Os containers com restart policy voltam sozinhos.
- name: Reiniciar Docker
  ansible.builtin.systemd_service:
    name: docker
    state: restarted
    daemon_reload: true
  when: not ansible_check_mode # numa VM nova, no --check, o Docker ainda não existe

# Regras novas em firewall_docker_portas (página 14).
- name: Aplicar firewall do Docker
  ansible.builtin.systemd_service:
    name: firewall-docker.service
    state: restarted
    daemon_reload: true
  when: not ansible_check_mode

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
    - role: common # Aplica configurações base, cliente NFS e UFW a todas as VMs Ubuntu

# Docker em todas as VMs Ubuntu. O Portainer completo fica na core-services-vm; nas demais (ai-desktop-vm)
# roda o Portainer Agent, que o Portainer central usa para gerenciar as stacks dela (docker_portainer_mode).
- hosts: ubuntu_vms
  become: yes
  vars_files:
    - ../inventories/home/group_vars/all/vault.yml # base_domain nas labels do Portainer e portainer_agent_secret
  roles:
    - role: infra/docker # Instala Docker Engine e o Portainer (server) ou o Portainer Agent (agent)

# Coletor de logs e métricas (seção 4.4). Depois do Docker, cujos containers ele lê.
- hosts: ubuntu_vms
  become: yes
  roles:
    - role: infra/alloy

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

1. **Verifique os Roles:** Certifique-se de que os roles `common`, `infra/docker`, `infra/alloy` (seção 4.4) e `apps/desktop-environment` (se for usar a funcionalidade de GUI) estão criados e preenchidos com o código correto nos seus respectivos diretórios dentro de `ansible/roles/`.
2. **Execute a Partir da Máquina de Controle:** Na sua máquina de controle Ansible, entre na pasta `server/ansible` do repositório.
3. **Execute o Playbook:**

    ```bash
    ansible-playbook -i inventories/home/hosts.ini playbooks/setup-base-ubuntu.yml --ask-vault-pass
    ```

    Você será solicitado a fornecer a senha do Ansible Vault.

!!! note "Possível Reinício das VMs"
    O role `infra/docker` inclui um handler que reiniciará a VM (`core-services-vm`) se o usuário Ansible (`{{ vm_ansible_user_name }}`) ou o `{{ docker_user_name_on_vm }}` forem adicionados ao grupo `docker` do sistema pela primeira vez. Isso é para garantir que as novas associações de grupo tenham efeito imediato para esses usuários em sessões SSH subsequentes, permitindo que eles executem comandos `docker` sem `sudo`.

Após a execução bem-sucedida deste playbook:

* Todas as suas VMs Ubuntu terão as configurações base (NFS client, UFW, Alloy, etc.).
* A `core-services-vm` terá o Docker Engine instalado e o container Portainer CE rodando.
* A `ai-desktop-vm`, se `GUI_ENABLED=true` foi definido para ela no inventário, terá o ambiente XFCE e TightVNCServer instalados.

## 4.4. Coleta com Grafana Alloy (`ansible/roles/infra/alloy/`)

O **Grafana Alloy** é o coletor único da infraestrutura: roda instalado no sistema (pacote `alloy` do repositório apt da Grafana, serviço systemd) no host Proxmox e nas duas VMs. Ele substitui o Promtail (fim da vida em 2026-03-02) e o node_exporter, e acrescenta métricas por container:

| Bloco | O que coleta | Para onde | Etiquetas |
|---|---|---|---|
| Journal | journal do systemd | Loki | `job="system_journal"`, `unit`, `host` |
| `/var/log` | `messages`, `syslog`, `auth.log`, `kern.log` | Loki | `job="var_log"`, `host` |
| Docker (só VMs) | logs de todos os containers, pela API do Docker | Loki | `job="docker_logs"`, `container_name`, `host` |
| Host | métricas do sistema (`node_*`, inclusive `node_zfs_*` no host Proxmox) | Prometheus (`remote_write`) | `job="node"`, `instance` |
| Containers (só VMs) | cAdvisor embutido (`container_*`, etiqueta `name`) | Prometheus (`remote_write`) | `job="cadvisor"`, `instance` |

`host` e `instance` são o nome do host no inventário (`proxmox_main_host`, `core-services-vm`, `ai-desktop-vm`). O Prometheus também raspa o `/metrics` do próprio Alloy em cada host (job `alloy`, porta 12345): é desse `up` que sai o alerta `host-sem-resposta`.

O role é aplicado pelo `setup-base-ubuntu.yml` (VMs) e pelo `setup-proxmox-host.yml` (host). A versão fica fixada em `alloy_version` no `group_vars/all/main.yml`; para atualizar, troque o valor e rode os dois playbooks.

!!! warning "Alloy como root nas VMs"
    Para ler os logs e as métricas dos containers, o Alloy roda como **root** nas VMs (drop-in `/etc/systemd/system/alloy.service.d/override.conf`): o cAdvisor lê `/var/lib/docker`, que só o root acessa, e o grupo `docker` sozinho não basta (e já equivaleria a root). No host Proxmox, sem Docker, ele roda como o usuário `alloy` (grupos `adm` e `systemd-journal`). O Docker é instalado sem o *image store* do containerd (`/etc/docker/daemon.json`, seção 4.2): com ele, padrão no Docker 29, o cAdvisor não encontra os containers. A interface do Alloy (`http://<host>:12345`) não tem autenticação e mostra a configuração (sem segredos); o firewall libera a porta só para a `core-services-vm` (UFW nas VMs; PVE Firewall no host). Na `core-services-vm` a origem liberada é `172.16.0.0/12`, porque o Prometheus em container chega ao IP do próprio host vindo da rede Docker.

### `defaults/main.yml`

```yaml title="ansible/roles/infra/alloy/defaults/main.yml"
# ansible/roles/infra/alloy/defaults/main.yml
# Endereço da interface/API do Alloy (o Prometheus raspa o /metrics daqui).
alloy_listen_addr: "0.0.0.0:12345"
# Destinos na core-services-vm (portas publicadas só na LAN).
alloy_loki_push_url: "http://{{ core_services_vm_ip_var }}:3100/loki/api/v1/push"
alloy_remote_write_url: "http://{{ core_services_vm_ip_var }}:9090/api/v1/write"
# Logs e métricas de containers só onde há Docker (as VMs Ubuntu).
alloy_docker_enabled: "{{ inventory_hostname in groups['ubuntu_vms'] }}"
# Origem liberada no UFW para a porta do Alloy: na core, a rede Docker do Prometheus; nas demais, o IP da core.
alloy_scrape_allowed_from: "{{ '172.16.0.0/12' if inventory_hostname == 'core-services-vm' else core_services_vm_ip_var }}"
```

### `tasks/main.yml`

```yaml title="ansible/roles/infra/alloy/tasks/main.yml"
# ansible/roles/infra/alloy/tasks/main.yml
# Instala o Grafana Alloy (repositório apt da Grafana) e gera /etc/alloy/config.alloy.

- name: "Garantir o diretório de chaves do apt"
  ansible.builtin.file:
    path: /etc/apt/keyrings
    state: directory
    mode: '0755'

- name: "Adicionar a chave do repositório da Grafana"
  ansible.builtin.get_url:
    url: https://apt.grafana.com/gpg.key
    dest: /etc/apt/keyrings/grafana.asc
    mode: '0644'

- name: "Adicionar o repositório apt da Grafana"
  ansible.builtin.apt_repository:
    repo: "deb [signed-by=/etc/apt/keyrings/grafana.asc] https://apt.grafana.com stable main"
    state: present
    filename: grafana
    update_cache: true

# O pin vale também para 'apt upgrade' manual e para o upgrade geral do host Proxmox.
- name: "Fixar a série do Alloy (alloy_version) no apt"
  ansible.builtin.copy:
    dest: /etc/apt/preferences.d/alloy
    content: |
      # Gerenciado pelo Ansible (role infra/alloy): instalação e upgrade ficam na série fixada.
      Package: alloy
      Pin: version {{ alloy_version }}
      Pin-Priority: 1001
    owner: root
    group: root
    mode: '0644'

- name: "Instalar o Alloy (a versão mais nova da série fixada)"
  ansible.builtin.apt:
    name: alloy
    state: latest
    update_cache: true
    cache_valid_time: 3600
  notify: Restart alloy

# journal (systemd-journal) e /var/log (adm). No host Proxmox o Alloy roda como o usuário alloy.
- name: "Dar ao usuário alloy acesso ao journal e ao /var/log"
  ansible.builtin.user:
    name: alloy
    groups: [adm, systemd-journal]
    append: true
  notify: Restart alloy

# Onde há Docker, o cAdvisor lê /var/lib/docker (0710 root:root) e o socket: o grupo docker não basta,
# então o serviço roda como root (o grupo docker já equivaleria a root).
- name: "Criar o diretório de drop-ins do serviço alloy"
  ansible.builtin.file:
    path: /etc/systemd/system/alloy.service.d
    state: directory
    mode: '0755'
  when: alloy_docker_enabled | bool

- name: "Rodar o Alloy como root onde há Docker (cAdvisor)"
  ansible.builtin.copy:
    dest: /etc/systemd/system/alloy.service.d/override.conf
    content: |
      # Gerenciado pelo Ansible (role infra/alloy)
      [Service]
      User=root
    owner: root
    group: root
    mode: '0644'
  when: alloy_docker_enabled | bool
  notify: Restart alloy

- name: "Configurar /etc/default/alloy (arquivo de configuração e endereço de escuta)"
  ansible.builtin.copy:
    dest: /etc/default/alloy
    content: |
      # Gerenciado pelo Ansible (role infra/alloy)
      CONFIG_FILE="/etc/alloy/config.alloy"
      CUSTOM_ARGS="--server.http.listen-addr={{ alloy_listen_addr }}"
      RESTART_ON_UPGRADE=true
    owner: root
    group: root
    mode: '0644'
  notify: Restart alloy

- name: "Gerar /etc/alloy/config.alloy (só grava se a configuração for válida)"
  ansible.builtin.template:
    src: config.alloy.j2
    dest: /etc/alloy/config.alloy
    owner: root
    group: alloy
    mode: '0640'
    validate: alloy validate %s
  notify: Reload alloy

- name: "Garantir que o Alloy está habilitado e rodando"
  ansible.builtin.systemd_service:
    name: alloy
    state: started
    enabled: true

- name: "UFW: liberar a porta do Alloy só para o Prometheus da core-services-vm"
  community.general.ufw:
    rule: allow
    port: '12345'
    proto: tcp
    from_ip: "{{ alloy_scrape_allowed_from }}"
    comment: "Alloy: Prometheus da core-services-vm"
  when: inventory_hostname in groups['ubuntu_vms']
```

### `handlers/main.yml`

```yaml title="ansible/roles/infra/alloy/handlers/main.yml"
# ansible/roles/infra/alloy/handlers/main.yml
- name: Reload alloy
  ansible.builtin.systemd_service:
    name: alloy
    state: reloaded

- name: Restart alloy
  ansible.builtin.systemd_service:
    name: alloy
    state: restarted
    daemon_reload: true # aplica o drop-in de /etc/systemd/system/alloy.service.d
```

### `templates/config.alloy.j2`

```text title="ansible/roles/infra/alloy/templates/config.alloy.j2"
// ansible/roles/infra/alloy/templates/config.alloy.j2
// Gerado pelo Ansible (role infra/alloy) para {{ inventory_hostname }}.

// ---------- Destinos ----------
loki.write "default" {
  endpoint {
    url = "{{ alloy_loki_push_url }}"
  }
}

prometheus.remote_write "default" {
  endpoint {
    url = "{{ alloy_remote_write_url }}"
  }
}

// ---------- Logs: journal do systemd ----------
loki.relabel "journal" {
  forward_to = []

  rule {
    source_labels = ["__journal__systemd_unit"]
    target_label = "unit"
  }
}

loki.source.journal "system" {
  max_age = "12h"
  relabel_rules = loki.relabel.journal.rules
  labels = { job = "system_journal", host = "{{ inventory_hostname }}" }
  forward_to = [loki.write.default.receiver]
}

// ---------- Logs: /var/log ----------
local.file_match "var_log" {
  path_targets = [{ "__path__" = "/var/log/{messages,syslog,auth.log,kern.log}", job = "var_log", host = "{{ inventory_hostname }}" }]
}

loki.source.file "var_log" {
  targets = local.file_match.var_log.targets
  forward_to = [loki.write.default.receiver]
}

// ---------- Métricas do host ----------
// O coletor systemd (além dos padrões) expõe o estado das units notes-* (timers do segundo cérebro, página 12)
// e backup-* (dumps diários dos bancos), usado pelo alerta timer-falhou. Restrito a elas para não gerar uma
// série por unit do sistema.
prometheus.exporter.unix "host" {
  enable_collectors = ["systemd"]

  systemd {
    unit_include = "(notes|backup)-.+\\.service"
  }
}

discovery.relabel "host" {
  targets = prometheus.exporter.unix.host.targets

  rule {
    target_label = "job"
    replacement = "node"
  }

  rule {
    target_label = "instance"
    replacement = "{{ inventory_hostname }}"
  }
}

prometheus.scrape "host" {
  targets = discovery.relabel.host.output
  forward_to = [prometheus.remote_write.default.receiver]
}
{% if alloy_docker_enabled | bool %}

// ---------- Logs dos containers (API do Docker) ----------
discovery.docker "local" {
  host = "unix:///var/run/docker.sock"
}

// O Docker entrega o nome como "/traefik"; a etiqueta fica sem a barra.
discovery.relabel "docker_logs" {
  targets = []

  rule {
    source_labels = ["__meta_docker_container_name"]
    regex = "/(.*)"
    target_label = "container_name"
  }
}

loki.source.docker "containers" {
  host = "unix:///var/run/docker.sock"
  targets = discovery.docker.local.targets
  relabel_rules = discovery.relabel.docker_logs.rules
  labels = { job = "docker_logs", host = "{{ inventory_hostname }}" }
  forward_to = [loki.write.default.receiver]
}

// ---------- Métricas por container (cAdvisor embutido) ----------
prometheus.exporter.cadvisor "containers" {
  docker_host = "unix:///var/run/docker.sock"
  docker_only = true
  store_container_labels = false
}

discovery.relabel "cadvisor" {
  targets = prometheus.exporter.cadvisor.containers.targets

  rule {
    target_label = "job"
    replacement = "cadvisor"
  }

  rule {
    target_label = "instance"
    replacement = "{{ inventory_hostname }}"
  }
}

prometheus.scrape "cadvisor" {
  targets = discovery.relabel.cadvisor.output
  forward_to = [prometheus.remote_write.default.receiver]
}
{% endif %}
```

### Verificação depois do deploy

1. Nos três hosts: `systemctl status alloy`; a interface `http://<host>:12345` mostra os componentes saudáveis.
2. No Prometheus: `up{job="alloy"}` vale 1 nos três hosts; `node_zfs_zpool_state` chega do `proxmox_main_host`; `container_last_seen{name="traefik"}` chega da `core-services-vm`.
3. No Grafana (Explore → Loki): `{job="docker_logs", host="ai-desktop-vm"}` e `{job="system_journal", host="proxmox_main_host"}` trazem linhas; o alerta `authelia-logins-falhos` tem dados.
4. Com o PVE Firewall ligado, as montagens NFS das VMs continuam funcionando (`df -h | grep /mnt`).

!!! tip "Dashboards"
    Nenhum dashboard é provisionado. No Grafana, **Dashboards → New → Import** aceita os dashboards da comunidade para node exporter e cAdvisor (busque por "Node Exporter Full" e "cAdvisor" em grafana.com/grafana/dashboards); escolha o datasource Prometheus ao importar.

Com esta base sólida, suas VMs estão prontas para o próximo passo crucial: a [Implementação da Rede Segura](05-rede-segura.md), que configurará Traefik, Cloudflare Tunnel e Authelia.
