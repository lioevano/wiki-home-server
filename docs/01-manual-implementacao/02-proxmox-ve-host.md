# Seção 2: Instalação e Configuração Base do Proxmox VE (Incluindo Servidor NFS)

Nesta seção, instalaremos o Proxmox VE no seu servidor físico e realizaremos as configurações base essenciais, incluindo a criação de um pool ZFS para dados e a configuração de um servidor NFS para compartilhar esses dados com as futuras máquinas virtuais.

## 2.1. Instalação do Proxmox VE no Servidor Físico

Siga estes passos para instalar o Proxmox VE:

1.  **Download e Preparação do Mídia de Instalação:**
    *   Baixe a ISO mais recente do Proxmox VE do [site oficial](https://www.proxmox.com/en/downloads).
    *   Use uma ferramenta como [Rufus](https://rufus.ie/) ou [Balena Etcher](https://www.balena.io/etcher/) para gravar a imagem ISO em um pendrive USB, tornando-o bootável.

2.  **Configuração da BIOS/UEFI do Servidor:**
    *   Acesse a BIOS/UEFI do seu servidor físico ao iniciar.
    *   Configure a ordem de boot para iniciar pelo pendrive USB.
    *   !!! critical "Habilite a Virtualização e IOMMU"
        É **essencial** habilitar as seguintes opções na BIOS/UEFI:
        *   **AMD-V** (para processadores AMD, também conhecido como SVM - Secure Virtual Machine) ou **Intel VT-x** (para processadores Intel).
        *   **IOMMU** (Input-Output Memory Management Unit) - AMD-Vi ou Intel VT-d. Isso é crucial para passthrough de dispositivos PCI, como a GPU.

3.  **Processo de Instalação do Proxmox VE:**
    *   Inicie o servidor pelo pendrive bootável.
    *   Siga o assistente de instalação do Proxmox VE:
        *   **Target Harddisk:** Selecione seu **SSD NVMe de 1TB** como o disco de destino para a instalação do Proxmox OS.
        *   **Localização e Fuso Horário:** Configure de acordo com sua localidade.
        *   **Senha `root` e Email:** Defina uma senha forte para o usuário `root` do Proxmox e forneça um email para notificações do sistema.
            !!! important "Anote a Senha Root!"
            Esta senha `root` será usada para o primeiro login na interface web do Proxmox e para acesso SSH inicial.
        *   **Configuração de Rede (Management Network):**
            *   Selecione a interface de rede correta (sua porta Ethernet Gigabit).
            *   **Hostname (FQDN):** e.g., `proxmox.meudominio.com` (use seu domínio).
            *   **IP Address (CIDR):** Defina um **IP estático** para o seu host Proxmox (e.g., `192.168.1.10/24`). **Anote este IP!**
            *   **Gateway:** O IP do seu roteador (e.g., `192.168.1.1`).
            *   **DNS Server:** Um servidor DNS público (e.g., `1.1.1.1` ou `8.8.8.8`) ou o seu DNS local (e.g., Pi-hole).

4.  **Primeiro Boot e Acesso:**
    *   Após a instalação, remova o pendrive USB e reinicie o servidor.
    *   Em outra máquina na mesma rede, abra um navegador e acesse a interface web do Proxmox VE:
        `https://IP_DO_PROXMOX:8006` (e.g., `https://192.168.1.10:8006`)
    *   Você pode receber um aviso de certificado autoassinado; prossiga com segurança.
    *   **Login:**
        *   **Username:** `root`
        *   **Password:** A senha `root` que você definiu durante a instalação.
        *   **Realm:** `Linux PAM standard authentication`

    !!! note "Subscrição Proxmox VE"
        Você verá uma mensagem sobre não ter uma subscrição válida. Para uso doméstico, a subscrição não é necessária. Você pode desabilitar o repositório "enterprise" e adicionar o repositório "no-subscription" para atualizações, o que será feito via Ansible.

## 2.2. Configuração do Pool ZFS `/data` e Datasets

Vamos criar um pool ZFS espelhado (RAID 1) usando seus dois HDDs de 500GB. Este pool, chamado `data`, armazenará os dados persistentes das suas aplicações Docker.

Execute os seguintes comandos no **shell do host Proxmox VE** (acessível via "Shell" na UI web do Datacenter ou via SSH como `root@IP_DO_PROXMOX`):

1.  **Identifique seus HDDs de 500GB:**
    Use `lsblk` para listar os dispositivos de bloco e identificar os nomes corretos dos seus HDDs. Preste atenção aos IDs únicos para evitar usar o disco errado.
    ```bash
    root@proxmox:~# lsblk -o NAME,SIZE,FSTYPE,MODEL,SERIAL,WWN
    ```
    Anote os caminhos `/dev/disk/by-id/ata-DISK_MODEL_AND_SERIAL_ID` para cada um dos seus HDDs de 500GB. Usar `by-id` é mais robusto do que `/dev/sda`, `/dev/sdb`, etc., pois os IDs persistem entre reboots.

2.  **Crie o Pool ZFS (`data`) em Modo Espelhado (RAID 1):**
    Substitua `ata-HDD1_ID` e `ata-HDD2_ID` pelos IDs reais dos seus discos obtidos no passo anterior.
    ```bash
    root@proxmox:~# zpool create -f -o ashift=12 data mirror /dev/disk/by-id/ata-HDD1_ID /dev/disk/by-id/ata-HDD2_ID
    ```
    *   `-f`: Força a criação, útil se os discos tiverem partições antigas.
    *   `-o ashift=12`: Define o tamanho do setor para 4K, recomendado para a maioria dos HDDs modernos e SSDs para melhor performance.
    *   `data`: Nome do pool ZFS.
    *   `mirror`: Especifica um pool espelhado (RAID 1).
    *   `/dev/disk/by-id/...`: Os dois discos que formarão o espelho.

3.  **Verifique o Status do Pool:**
    ```bash
    root@proxmox:~# zpool status data
    ```
    O estado (`state`) do pool deve ser `ONLINE` e ambos os discos devem aparecer como `ONLINE`.

4.  **Crie os Datasets ZFS Principais:**
    Datasets são como "sistemas de arquivos" dentro do pool ZFS. Eles podem ter propriedades individuais e são a unidade que será compartilhada via NFS. Os nomes dos datasets devem corresponder aos definidos em `ansible/inventories/home/group_vars/all/main.yml` (`zfs_*_dataset_name`).

    ```bash
    # Assumindo os valores de zfs_*_dataset_name de main.yml:
    # zfs_docker_volumes_dataset_name: "docker-volumes"
    # zfs_media_dataset_name: "media"
    # zfs_downloads_dataset_name: "downloads"
    # zfs_rag_sources_dataset_name: "rag_sources"
    # zfs_backups_dataset_name: "backups"

    root@proxmox:~# zfs create data/docker-volumes
    root@proxmox:~# zfs create data/media
    root@proxmox:~# zfs create data/downloads
    root@proxmox:~# zfs create data/rag_sources  # Se for usar a VM de IA
    root@proxmox:~# zfs create data/backups
    ```
    Estes datasets serão automaticamente montados em `/data/docker-volumes`, `/data/media`, etc.

    !!! tip "Vantagens dos Datasets ZFS"
        *   **Snapshots Individuais:** Você pode tirar snapshots de `data/media` sem afetar `data/docker-volumes`.
        *   **Propriedades por Dataset:** Pode-se definir compressão, cotas, etc., por dataset.
        *   **Compartilhamento Granular:** Facilita o compartilhamento de diretórios específicos via NFS.

## 2.3. Playbook `setup-proxmox-host.yml` (Configurações Iniciais, Hardening, Servidor NFS)

Agora que o Proxmox VE está instalado e o pool ZFS básico foi criado, usaremos Ansible para automatizar o restante da configuração do host.

### Ações Manuais Prévias no Host Proxmox (Importante!)

Antes de executar o playbook `setup-proxmox-host.yml` pela primeira vez, você precisa:

1.  **Criar um Usuário Ansible Dedicado no Host Proxmox:**
    Ainda no shell do host Proxmox como `root`:
    ```bash
    # O nome do usuário deve corresponder a 'proxmox_ansible_user_on_host'
    # definido em ansible/inventories/home/group_vars/all/main.yml
    # Exemplo: PROXMOX_ANSIBLE_USER="proxmox_ansible_user"
    PROXMOX_ANSIBLE_USER="{{ proxmox_ansible_user_on_host }}" # Esta variável virá do Ansible, use o valor literal por enquanto.

    adduser ${PROXMOX_ANSIBLE_USER} # Siga as instruções para definir senha, etc.
    usermod -aG sudo ${PROXMOX_ANSIBLE_USER} # Adiciona o usuário ao grupo sudo
    # Permite que o usuário execute comandos sudo sem senha (necessário para Ansible)
    echo "${PROXMOX_ANSIBLE_USER} ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/010_${PROXMOX_ANSIBLE_USER}_nopasswd
    chmod 0440 /etc/sudoers.d/010_${PROXMOX_ANSIBLE_USER}_nopasswd
    ```
    Substitua `${PROXMOX_ANSIBLE_USER}` pelo valor real da variável `proxmox_ansible_user_on_host` (e.g., `proxmox_ansible_user`).

2.  **Copiar sua Chave SSH Pública para o Novo Usuário Ansible:**
    Na sua **máquina de controle Ansible**, execute o comando `ssh-copy-id`. Isso permitirá que o Ansible se conecte ao host Proxmox usando sua chave SSH.
    ```bash
    # Substitua 'proxmox_ansible_user' pelo nome do usuário criado e 'IP_DO_PROXMOX' pelo IP do seu host.
    # Use o caminho para a chave pública gerada na Seção 1.1.
    ssh-copy-id -i ~/.ssh/id_ed25519_homelab.pub proxmox_ansible_user@IP_DO_PROXMOX
    ```
    Exemplo: `ssh-copy-id -i ~/.ssh/id_ed25519_homelab.pub proxmox_ansible_user@192.168.1.10`

3.  **Teste a Conexão SSH e as Permissões Sudo:**
    Ainda na sua máquina de controle Ansible:
    ```bash
    ssh proxmox_ansible_user@IP_DO_PROXMOX "sudo whoami"
    ```
    Isso deve se conectar sem pedir senha e retornar `root`. Se funcionar, o Ansible está pronto para gerenciar o host Proxmox.

### Estrutura do Role `ansible/roles/infra/proxmox-host-config/`

Este role Ansible contém todas as tarefas para configurar o host Proxmox.

#### `tasks/main.yml`

Este arquivo define as tarefas a serem executadas no host Proxmox.

```yaml
# ansible/roles/infra/proxmox-host-config/tasks/main.yml
- name: "Atualizar repositórios Proxmox (remover enterprise, adicionar no-subscription)"
  ansible.builtin.block:
    - name: "Comentar repositório enterprise"
      ansible.builtin.replace:
        path: /etc/apt/sources.list.d/pve-enterprise.list
        regexp: '^deb'
        replace: '#deb'
      when: ansible_distribution == 'Proxmox VE' # Garante que só roda em PVE
    - name: "Adicionar repositório no-subscription"
      ansible.builtin.apt_repository:
        repo: "deb http://download.proxmox.com/debian/pve {{ ansible_distribution_release }} pve-no-subscription"
        state: present
        filename: pve-no-subscription
      when: ansible_distribution == 'Proxmox VE'
  notify: Update apt cache

- name: "Atualizar todos os pacotes do sistema"
  ansible.builtin.apt:
    update_cache: yes
    upgrade: dist # Equivalente a apt full-upgrade
    autoremove: yes
  register: apt_upgrade_status
  changed_when: "'0 upgraded, 0 newly installed' not in apt_upgrade_status.stdout"

- name: "Instalar pacotes essenciais no host Proxmox"
  ansible.builtin.apt:
    name:
      - htop
      - ncdu
      - git
      - curl
      - wget
      - qemu-guest-agent # Embora seja host, é bom ter para consistência se virtualizar PVE
      - nfs-kernel-server # Para compartilhar ZFS com VMs
      - zfsutils-linux # Já deve estar, mas para garantir
      - smartmontools # Para monitoramento de discos S.M.A.R.T.
    state: present

- name: "Configurar fuso horário do sistema"
  community.general.timezone:
    name: "{{ system_timezone }}" # Variável do vault.yml

- name: "Configurar NTP (systemd-timesyncd)"
  ansible.builtin.lineinfile:
    path: /etc/systemd/timesyncd.conf
    regexp: "^#?NTP="
    line: "NTP=a.st1.ntp.br b.st1.ntp.br c.st1.ntp.br pool.ntp.org" # Servidores NTP BR + pool global
  notify: Restart timesyncd
- ansible.builtin.systemd_service:
    name: systemd-timesyncd
    state: started
    enabled: yes

- name: "Configurar Firewall Proxmox (PVE Firewall) - Políticas Globais"
  community.proxmox.pve_firewall_global: # Módulo correto para PVE Firewall global
    enable: true # Habilita o firewall globalmente
    input_policy: DROP # Política padrão para tráfego de entrada
    output_policy: ACCEPT # Política padrão para tráfego de saída
    api_user: "{{ proxmox_api_user }}" # Do vault.yml
    api_password: "{{ proxmox_api_password }}" # Do vault.yml
    api_host: "{{ inventory_hostname }}" # Conecta ao host Proxmox que está sendo configurado
  notify: Reload PVE Firewall
  when: ansible_distribution == 'Proxmox VE'

- name: "Permitir SSH e Web UI no Firewall do Host Proxmox"
  community.proxmox.pve_firewall_rules: # Módulo para regras de firewall
    node: "{{ inventory_hostname_short | lower }}" # Nome curto do host Proxmox (e.g., 'proxmox_main_host')
    type: group # Aplica a um grupo de regras (security group, não é o caso aqui, mas pode ser usado)
                 # Para regras individuais, omita 'type: group' e defina 'direction', 'action', etc. diretamente.
                 # Vamos definir regras individuais
    rules:
      - { dir: 'in', action: 'ACCEPT', enable: 1, interface: '{{ proxmox_default_bridge }}', source: '{{ proxmox_ssh_allowed_cidrs }}', dport: '22', proto: 'tcp', comment: 'Allow SSH from Local LAN' }
      - { dir: 'in', action: 'ACCEPT', enable: 1, interface: '{{ proxmox_default_bridge }}', source: '{{ proxmox_web_ui_allowed_cidrs }}', dport: '8006', proto: 'tcp', comment: 'Allow Proxmox WebUI from Local LAN' }
    api_user: "{{ proxmox_api_user }}"
    api_password: "{{ proxmox_api_password }}"
    api_host: "{{ inventory_hostname }}"
  notify: Reload PVE Firewall
  when: ansible_distribution == 'Proxmox VE'

- name: "Hardening Configuração SSHD"
  ansible.builtin.lineinfile:
    path: /etc/ssh/sshd_config
    regexp: "{{ item.regexp }}"
    line: "{{ item.line }}"
    state: present
  loop:
    - { regexp: '^#?PermitRootLogin', line: 'PermitRootLogin prohibit-password' }
    - { regexp: '^#?PasswordAuthentication', line: 'PasswordAuthentication no' } # Desabilita login por senha, força chaves SSH
    - { regexp: '^#?PubkeyAuthentication', line: 'PubkeyAuthentication yes' }
    - { regexp: '^#?ChallengeResponseAuthentication', line: 'ChallengeResponseAuthentication no' }
    - { regexp: '^#?UsePAM', line: 'UsePAM yes' } # Manter PAM para `su` e outras funcionalidades
  notify: Restart sshd

# --- Instalação do Node Exporter (Host Proxmox) para Prometheus ---
- name: "Verificar se Node Exporter já está instalado (binário)"
  ansible.builtin.stat:
    path: /usr/local/bin/node_exporter
  register: node_exporter_host_binary

- name: Instalar Node Exporter (se não existir)
  when: not node_exporter_host_binary.stat.exists
  ansible.builtin.block:
    - name: Checar última release do Node Exporter no GitHub
      ansible.builtin.uri:
        url: "https://api.github.com/repos/prometheus/node_exporter/releases/latest"
        return_content: yes
      register: node_exporter_latest_release
      run_once: true # Para evitar múltiplas chamadas à API se rodar em vários hosts

    - name: Definir URL de download do Node Exporter
      ansible.builtin.set_fact:
        node_exporter_version: "{{ node_exporter_latest_release.json.tag_name | regex_replace('^v(.*)$', '\\1') }}"
        node_exporter_download_url: "https://github.com/prometheus/node_exporter/releases/download/v{{ node_exporter_version }}/node_exporter-{{ node_exporter_version }}.linux-amd64.tar.gz"

    - name: Baixar Node Exporter
      ansible.builtin.get_url:
        url: "{{ node_exporter_download_url }}"
        dest: "/tmp/node_exporter-{{ node_exporter_version }}.linux-amd64.tar.gz"
        mode: '0644'

    - name: Descompactar Node Exporter
      ansible.builtin.unarchive:
        src: "/tmp/node_exporter-{{ node_exporter_version }}.linux-amd64.tar.gz"
        dest: "/tmp/"
        remote_src: yes # O arquivo .tar.gz está no host remoto (Proxmox)

    - name: Mover binário Node Exporter para /usr/local/bin
      ansible.builtin.copy:
        src: "/tmp/node_exporter-{{ node_exporter_version }}.linux-amd64/node_exporter"
        dest: "/usr/local/bin/node_exporter"
        mode: '0755'
        remote_src: yes # O binário extraído está no host remoto

    - name: Criar usuário de sistema 'node_exporter'
      ansible.builtin.user:
        name: node_exporter
        shell: /bin/false
        system: yes
        create_home: no

    - name: Criar arquivo de serviço systemd para Node Exporter (Host)
      ansible.builtin.template:
        src: node_exporter_host.service.j2 # Template específico para o host
        dest: /etc/systemd/system/node_exporter.service
        mode: '0644'
      notify: Reload systemd and restart node_exporter_host

    - name: Limpar arquivos temporários de instalação do Node Exporter
      ansible.builtin.file:
        path: "{{ item }}"
        state: absent
      loop:
        - "/tmp/node_exporter-{{ node_exporter_version }}.linux-amd64.tar.gz"
        - "/tmp/node_exporter-{{ node_exporter_version }}.linux-amd64"

- name: Garantir que Node Exporter (Host) está habilitado e rodando
  ansible.builtin.systemd_service:
    name: node_exporter
    state: started
    enabled: yes
  # Esta task roda mesmo se o Node Exporter já existia, garantindo que o serviço está OK.

# --- Configuração do Servidor NFS ---
- name: "Garantir que nfs-kernel-server está instalado"
  ansible.builtin.apt:
    name: nfs-kernel-server
    state: present

- name: "Criar arquivo /etc/exports a partir do template"
  ansible.builtin.template:
    src: etc_exports.j2 # Template Jinja2 para /etc/exports
    dest: /etc/exports
    owner: root
    group: root
    mode: '0644'
  notify: Export filesystems # Handler para aplicar mudanças no NFS

- name: "Garantir que o serviço NFS está habilitado e rodando"
  ansible.builtin.systemd_service:
    name: nfs-kernel-server
    state: started
    enabled: yes
```

#### Template `templates/node_exporter_host.service.j2`

```systemd
# ansible/roles/infra/proxmox-host-config/templates/node_exporter_host.service.j2
[Unit]
Description=Node Exporter for Prometheus (Proxmox Host)
Wants=network-online.target
After=network-online.target

[Service]
User=node_exporter
Group=node_exporter
Type=simple
ExecStart=/usr/local/bin/node_exporter \
    --collector.zfs \
    --collector.ksm \
    --collector.systemd \
    --collector.thermal_zone \
    --collector.power_supply \
    --collector.mdadm \
    --collector.meminfo_numa \
    --collector.interrupts \
    --collector.entropy \
    --collector.bonding \
    --collector.buddyinfo \
    --collector.conntrack \
    --collector.cpu \
    --collector.diskstats \
    --collector.filesystem \
    --collector.loadavg \
    --collector.meminfo \
    --collector.netdev \
    --collector.netstat \
    --collector.stat \
    --collector.time \
    --collector.vmstat \
    --collector.pressure
    # Adicione ou remova coletores conforme necessário.
    # Para Proxmox, --collector.zfs é particularmente útil.

[Install]
WantedBy=multi-user.target
```

#### Template `templates/etc_exports.j2`

```jinja
# ansible/roles/infra/proxmox-host-config/templates/etc_exports.j2
# Gerenciado por Ansible - NÃO EDITE MANUALMENTE
# Define os compartilhamentos NFS para os datasets ZFS do host Proxmox.

# Variáveis Ansible usadas (definidas em group_vars/all/main.yml e vault.yml):
# {{ zfs_base_pool_path }}: Caminho base do pool ZFS (e.g., /data)
# {{ vm_nfs_allowed_clients_cidr }}: CIDR da sub-rede das VMs (e.g., 192.168.1.0/24)
# {{ docker_puid }}: User ID numérico do usuário 'dockeruser' nas VMs.
# {{ docker_pgid }}: Group ID numérico do grupo 'dockergroup' nas VMs.

# Compartilhamento para volumes Docker gerais
{{ zfs_base_pool_path }}/{{ zfs_docker_volumes_dataset_name }} {{ vm_nfs_allowed_clients_cidr }}(rw,sync,no_subtree_check,all_squash,anonuid={{ docker_puid }},anongid={{ docker_pgid }})

# Compartilhamento para dados de mídia
{{ zfs_base_pool_path }}/{{ zfs_media_dataset_name }} {{ vm_nfs_allowed_clients_cidr }}(rw,sync,no_subtree_check,all_squash,anonuid={{ docker_puid }},anongid={{ docker_pgid }})

# Compartilhamento para downloads
{{ zfs_base_pool_path }}/{{ zfs_downloads_dataset_name }} {{ vm_nfs_allowed_clients_cidr }}(rw,sync,no_subtree_check,all_squash,anonuid={{ docker_puid }},anongid={{ docker_pgid }})

# Compartilhamento para fontes RAG (condicional, se a VM AI existir e usar)
{% if zfs_rag_sources_dataset_name is defined and 'ai-desktop-vm' in groups['virtual_machines'] %}
{{ zfs_base_pool_path }}/{{ zfs_rag_sources_dataset_name }} {{ vm_nfs_allowed_clients_cidr }}(rw,sync,no_subtree_check,all_squash,anonuid={{ docker_puid }},anongid={{ docker_pgid }})
{% endif %}

# Compartilhamento para backups (geralmente não precisa ser montado por VMs,
# a menos que uma VM específica precise ler backups. Pode ser 'ro' para VMs).
# {{ zfs_base_pool_path }}/{{ zfs_backups_dataset_name }} {{ vm_nfs_allowed_clients_cidr }}(ro,sync,no_subtree_check)
```
!!! note "Opções de Exportação NFS Explicadas"
    *   `rw`: Permite leitura e escrita no compartilhamento.
    *   `sync`: Força o servidor NFS a responder à requisição do cliente apenas após as mudanças terem sido escritas fisicamente no disco. É mais seguro para a integridade dos dados, mas pode ser um pouco mais lento que `async`.
    *   `no_subtree_check`: Desabilita a verificação de subárvores, o que pode melhorar a confiabilidade se um subdiretório dentro do compartilhamento for renomeado enquanto estiver exportado.
    *   `all_squash`: Mapeia todos os User IDs (UIDs) e Group IDs (GIDs) dos clientes NFS para o usuário anônimo no servidor.
    *   `anonuid={{ docker_puid }}`: Define o UID do usuário anônimo (após o squash) para o valor da variável `docker_puid` (que é o PUID do seu `dockeruser` nas VMs).
    *   `anongid={{ docker_pgid }}`: Define o GID do usuário anônimo para o valor da variável `docker_pgid` (PGID do `dockergroup` nas VMs).
    Esta combinação garante que os arquivos criados pelas VMs nos montados NFS tenham a propriedade correta para que os containers Docker (rodando como `dockeruser:dockergroup`) possam acessá-los corretamente.

#### Handlers (`handlers/main.yml`)

Handlers são tarefas que são executadas apenas se notificadas por uma mudança em outra tarefa.

```yaml
# ansible/roles/infra/proxmox-host-config/handlers/main.yml
- name: Update apt cache
  ansible.builtin.apt:
    update_cache: yes

- name: Restart timesyncd
  ansible.builtin.systemd_service:
    name: systemd-timesyncd
    state: restarted

- name: Reload PVE Firewall
  ansible.builtin.command: pve-firewall restart
  when: ansible_distribution == 'Proxmox VE'
  # Usar 'command' pois pode não haver um módulo Ansible específico para 'pve-firewall restart'
  # que seja idempotente da maneira que queremos (apenas recarregar).

- name: Restart sshd
  ansible.builtin.systemd_service:
    name: sshd # Ou ssh.service, dependendo da distro
    state: restarted

- name: Reload systemd and restart node_exporter_host
  ansible.builtin.systemd: # Módulo systemd para daemon_reload
    daemon_reload: yes
  notify: Restart node_exporter_host_service # Encadeia para o próximo handler

- name: Restart node_exporter_host_service
  ansible.builtin.systemd_service:
    name: node_exporter
    state: restarted
    enabled: yes # Garante que está habilitado também

- name: Export filesystems
  ansible.builtin.command: exportfs -ra
  listen: "Export filesystems" # Nome do listener para ser chamado por notify

- name: Restart nfs-server
  ansible.builtin.systemd_service:
    name: nfs-kernel-server
    state: restarted
  listen: "Export filesystems" # Também reinicia nfs-server se os exports mudarem
```

### Playbook Principal (`ansible/playbooks/setup-proxmox-host.yml`)

Este é o playbook que você executará para aplicar o role `proxmox-host-config`.

```yaml
# ansible/playbooks/setup-proxmox-host.yml
- hosts: proxmox_main_host # Alvo definido no seu inventário (ansible/inventories/home/hosts.ini)
  become: yes # A maioria das tarefas neste role requer privilégios de root
  vars_files:
    - ../inventories/home/group_vars/all/vault.yml # Carrega variáveis sensíveis
  # Variáveis de ../inventories/home/group_vars/all/main.yml são carregadas automaticamente

  roles:
    - role: infra/proxmox-host-config # Aplica o role que acabamos de detalhar
```

### Executando o Playbook

1.  **Certifique-se de que o role `infra/proxmox-host-config` está criado** com os arquivos `tasks/main.yml`, `templates/node_exporter_host.service.j2`, `templates/etc_exports.j2`, e `handlers/main.yml` conforme detalhado acima.
2.  Na sua máquina de controle Ansible, navegue até a raiz do projeto `infra-servidor-domestico/`.
3.  Execute o playbook:
    ```bash
    ansible-playbook ansible/playbooks/setup-proxmox-host.yml --ask-vault-pass
    ```
    Você será solicitado a fornecer a senha do Ansible Vault que você criou anteriormente.

Após a execução bem-sucedida, seu host Proxmox VE estará com as configurações base aplicadas, incluindo o servidor NFS pronto para compartilhar os datasets ZFS.

Próximo passo: [Provisionamento das Máquinas Virtuais (VMs) com Ansible](03-provisionamento-vms.md).