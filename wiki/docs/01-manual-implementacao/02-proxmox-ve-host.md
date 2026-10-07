---
description: "Instala e configura o host Proxmox VE: repositórios, pool ZFS, servidor NFS, firewall e Node Exporter via role proxmox-host-config."
---

# Seção 2: Instalação e Configuração Base do Proxmox VE (Incluindo Servidor NFS)

Nesta seção crucial, instalaremos o Proxmox VE no seu servidor físico. Em seguida, realizaremos as configurações base essenciais, incluindo a criação de um pool ZFS resiliente para armazenamento de dados e a configuração de um servidor NFS para compartilhar esses dados com as futuras máquinas virtuais que hospedarão nossos containers Docker.

## 2.1. Instalação do Proxmox VE no Servidor Físico

Siga estes passos cuidadosamente para instalar o Proxmox VE:

1. **Download da ISO e Preparação da Mídia de Instalação:**
    * Acesse o [site oficial do Proxmox](https://www.proxmox.com/en/downloads) e baixe a **ISO mais recente e estável** do Proxmox VE.
    * Utilize uma ferramenta para criar um pendrive USB bootável a partir da imagem ISO. Minha recomendação pessoal é o [Ventoy](https://www.ventoy.net/en/download.html) pela sua flexibilidade (permite copiar múltiplas ISOs para o mesmo pendrive), mas [Rufus](https://rufus.ie/) (para Windows) ou [Balena Etcher](https://www.balena.io/etcher/) (multiplataforma) também são excelentes opções.

2. **Configuração da BIOS/UEFI do Servidor Físico:**
    * Conecte o pendrive bootável ao seu servidor.
    * Ao ligar o servidor, acesse a configuração da BIOS/UEFI (geralmente pressionando `DEL`, `F2`, `F10`, `F12` ou `ESC` durante o boot inicial – a tecla varia conforme o fabricante da placa-mãe).
    * **Defina a Ordem de Boot:** Configure o sistema para iniciar (boot) a partir do pendrive USB que contém a ISO do Proxmox.
    * !!! critical "Habilite a Virtualização e IOMMU na BIOS/UEFI"
        Este é um passo **absolutamente essencial** para que a virtualização funcione corretamente e para permitir o passthrough de dispositivos PCI (como sua GPU RX 5600XT) para as VMs. Procure e habilite as seguintes opções (os nomes podem variar um pouco dependendo do fabricante da BIOS):
        * **Para processadores AMD (como o Ryzen 5 5600G):**
            * `AMD-V` ou `SVM Mode` (Secure Virtual Machine) - **Habilitar**.
            * `IOMMU` ou `AMD IOMMU` ou `AMD-Vi` - **Habilitar**.
        * **Para processadores Intel:**
            * `Intel VT-x` ou `Intel Virtualization Technology` - **Habilitar**.
            * `Intel VT-d` ou `Intel Directed I/O Virtualization` - **Habilitar**.
    * Salve as alterações na BIOS/UEFI e reinicie o servidor.

3. **Processo de Instalação do Proxmox VE:**
    * O servidor deve iniciar a partir do pendrive e carregar o instalador do Proxmox VE.
    * Siga o assistente gráfico de instalação:
        * **EULA:** Aceite os termos.
        * **Target Harddisk:** Selecione seu **SSD NVMe de 1TB** como o disco de destino para a instalação do sistema operacional Proxmox VE.
        !!! warning "Apagamento de Disco"
            A instalação formatará o disco selecionado. Certifique-se de que não há dados importantes nele.
        * **Country, Time zone and Keyboard Layout:** Configure de acordo com sua localização e preferências.
        * **Password and Email:**
            * **Password:** Defina uma senha forte para o usuário `root` do Proxmox. Esta senha será usada para o primeiro login na interface web e para acesso SSH inicial ao host.
            !!! important "Anote a Senha Root e Use no Ansible Vault!"
                Esta senha `root` é crítica. Anote-a em local seguro. Você também precisará dela para a variável `proxmox_api_password` no seu arquivo `ansible/inventories/home/group_vars/all/vault.yml` (pelo menos inicialmente).
            * **Email:** Forneça um endereço de email válido. O sistema Proxmox pode enviar notificações importantes para este email.
        * **Management Network Configuration:**
            * **Management Interface:** Selecione a interface de rede correta do seu servidor (sua porta Ethernet Gigabit).
            * **Hostname (FQDN):** Defina um nome de host completo para seu servidor Proxmox. Exemplo: `pve.meudominio.com` (substitua `meudominio.com` pelo seu domínio real).
            * **IP Address (CIDR):** Defina um **endereço IP estático** para o seu host Proxmox. Este IP não deve estar na faixa DHCP do seu roteador para evitar conflitos. Exemplo: `192.168.15.10/24` (substitua pela sua sub-rede e IP desejado). **Anote este IP!**
            * **Gateway:** O endereço IP do seu roteador doméstico. Exemplo: `192.168.15.1`.
            * **DNS Server:** Um servidor DNS. Pode ser um DNS público (e.g., `1.1.1.1` da Cloudflare, ou `8.8.8.8` do Google) ou o IP do seu DNS local (e.g., se você tiver um Pi-hole, que pode ser `192.168.15.1` se o roteador também for o DNS, ou outro IP).
    * Revise o sumário da instalação e clique em "Install". O processo de instalação começará.

4. **Primeiro Boot e Acesso à Interface Web:**
    * Após a conclusão da instalação, o servidor será reiniciado automaticamente. **Remova o pendrive USB** para que ele não tente iniciar pela mídia de instalação novamente.
    * Em outro computador na mesma rede local, abra um navegador web.
    * Acesse a interface web do Proxmox VE usando o endereço IP que você configurou e a porta `8006`:
        `https://IP_DO_SEU_PROXMOX:8006` (e.g., `https://192.168.15.10:8006`)
    * Você provavelmente verá um aviso de segurança do navegador sobre um certificado SSL autoassinado. Isso é normal. Você pode prosseguir com segurança (geralmente clicando em "Avançado" e "Aceitar o risco e continuar"). Mais tarde, poderemos configurar um certificado válido para a UI do Proxmox, se desejado, embora o acesso principal aos seus serviços seja via Traefik e Cloudflare Tunnel.
    * **Tela de Login do Proxmox VE:**
        * **Username:** `root`
        * **Password:** A senha `root` que você definiu durante a instalação.
        * **Realm:** Selecione `Linux PAM standard authentication`.
        * **Language:** Escolha seu idioma preferido.
    * Clique em "Login".

    !!! note "Aviso de Subscrição Proxmox VE"
        Ao logar, você verá uma caixa de diálogo "No valid subscription". Para uso doméstico e aprendizado, uma subscrição paga não é necessária. Você pode simplesmente clicar em "OK". As atualizações do Proxmox VE podem ser obtidas do repositório "no-subscription", que será configurado automaticamente pelo nosso playbook Ansible na próxima etapa.

## 2.2. Configuração do Pool ZFS `/data` e Datasets

Com o Proxmox VE instalado, vamos criar um pool ZFS espelhado (RAID 1) usando seus dois HDDs de 500GB. Este pool, que chamaremos de `data`, será o local principal para armazenar os dados persistentes das suas aplicações Docker, arquivos de mídia, downloads e backups de VMs.

1. Execute os seguintes comandos no **shell do host Proxmox VE**. Você pode acessar o shell de algumas maneiras:
    * Na interface web do Proxmox: Selecione seu nó Proxmox (e.g., `pve`) na árvore à esquerda, depois clique em ">_ Shell".
    * Via SSH: Conecte-se como `root` ao IP do seu host Proxmox (e.g., `ssh root@192.168.15.10`).

2. **Identifique seus HDDs de 500GB:**
    Use o comando `lsblk` para listar os dispositivos de bloco e identificar os nomes corretos dos seus HDDs. É crucial usar identificadores persistentes para os discos.

    ```bash
    root@pve:~# lsblk -o NAME,SIZE,FSTYPE,MODEL,SERIAL,WWN,PATH
    ```

    Procure pelos seus dois HDDs de 500GB. Anote seus caminhos únicos em `/dev/disk/by-id/`, por exemplo:
    * `ata-HGST_HDN728080ALE604_R1234567`
    * `ata-WDC_WD5000AAKX-001CA0_WD-WMEXAMPLE1`
    !!! note "Importância dos IDs Persistentes dos HDDs"
        Usar caminhos como `/dev/disk/by-id/ata-VENDOR_MODEL_SERIAL` é muito mais robusto do que usar `/dev/sda`, `/dev/sdb`, etc. Os nomes `sdX` podem mudar entre reboots, mas os caminhos `by-id` são baseados em identificadores únicos do hardware e permanecem consistentes.

3. **Crie o Pool ZFS (`data`) em Modo Espelhado (RAID 1):**
    Substitua `ata-HDD1_MODEL_SERIAL_ID` e `ata-HDD2_MODEL_SERIAL_ID` pelos IDs reais dos seus discos que você anotou no passo anterior.

    ```bash
    root@pve:~# zpool create -f -o ashift=12 data mirror /dev/disk/by-id/ata-HDD1_MODEL_SERIAL_ID /dev/disk/by-id/ata-HDD2_MODEL_SERIAL_ID
    ```

    Explicação dos parâmetros:
    * `-f`: Força a criação do pool. Útil se os discos tiverem partições ou metadados ZFS antigos.
    * `-o ashift=12`: Define o tamanho do setor físico para o ZFS como 4KB (2^12 bytes). Isso é recomendado para a maioria dos HDDs modernos ("Advanced Format") e SSDs para otimizar a performance e o alinhamento.
    * `data`: O nome que estamos dando ao nosso pool ZFS.
    * `mirror`: Especifica que este VDEV (Virtual Device) será um espelho (RAID 1).
    * `/dev/disk/by-id/...`: Os dois discos físicos que formarão o espelho.

4. **Verifique o Status do Pool ZFS:**
    Após a criação, verifique se o pool está online e saudável:

    ```bash
    root@pve:~# zpool status data
    ```

    A saída deve mostrar:
    * `pool: data`
    * `state: ONLINE`
    * Ambos os discos listados sob `data` também devem estar `ONLINE`.

5. **Crie os Datasets ZFS Principais:**
    Datasets são como sistemas de arquivos ou diretórios "inteligentes" dentro de um pool ZFS. Eles podem ter propriedades individuais (como compressão, cotas, snapshots) e são a unidade que compartilharemos via NFS. Os nomes dos datasets devem corresponder aos definidos na variável `zfs_*_dataset_name` no seu arquivo `ansible/inventories/home/group_vars/all/main.yml`.

    ```bash
    # Assumindo os valores padrão de zfs_*_dataset_name do main.yml:
    # zfs_docker_volumes_dataset_name: "docker-volumes"
    # zfs_media_dataset_name: "media"
    # zfs_downloads_dataset_name: "downloads"
    # zfs_rag_sources_dataset_name: "rag_sources"
    # zfs_backups_dataset_name: "backups"

    root@pve:~# zfs create data/docker-volumes
    root@pve:~# zfs create data/media
    root@pve:~# zfs create data/downloads
    root@pve:~# zfs create data/rag_sources
    root@pve:~# zfs create data/backups
    ```

    Por padrão, esses datasets serão automaticamente montados pelo ZFS em `/data/docker-volumes`, `/data/media`, etc., no host Proxmox.

    !!! tip "Vantagens de Usar Datasets ZFS"
        * **Snapshots Individuais:** Você pode tirar snapshots de `data/media` sem afetar `data/docker-volumes`. Veja o [Guia de Snapshots ZFS](../03-guias-sustentacao/12-guia-snapshots-zfs.md) para mais detalhes.
        * **Propriedades por Dataset:** Permite definir configurações específicas como compressão (`zfs set compression=lz4 data/docker-volumes`), cotas (`zfs set quota=100G data/media`), ou `recordsize` por dataset.
        * **Compartilhamento Granular via NFS:** Facilita a exportação de diretórios específicos.
        * **Organização:** Mantém seus dados logicamente separados dentro do pool.

## 2.3. Playbook `setup-proxmox-host.yml` (Configurações Iniciais, Hardening, Servidor NFS)

Agora que o Proxmox VE está instalado e o pool ZFS básico (`data`) e seus datasets principais foram criados manualmente, usaremos o Ansible para automatizar o restante da configuração do host. Isso inclui atualizar o sistema, instalar pacotes, configurar o firewall do Proxmox, fortalecer o SSH e, crucialmente, configurar o servidor NFS para compartilhar os datasets ZFS com as VMs.

### Ações Manuais Prévias no Host Proxmox (Essencial para Ansible)

Antes de poder executar o playbook `setup-proxmox-host.yml` pela primeira vez, você precisa realizar algumas ações manuais no host Proxmox recém-instalado para permitir que o Ansible se conecte e execute tarefas com privilégios:

1. **Criar um Usuário Ansible Dedicado no Host Proxmox:**
    É uma má prática de segurança usar o usuário `root` para automação Ansible. Vamos criar um usuário dedicado. No shell do host Proxmox (como `root`):

    ```bash
    # O nome do usuário ('proxmox_ansible_user') deve corresponder ao valor da variável
    # 'proxmox_ansible_user_on_host' definida em seu arquivo
    # ansible/inventories/home/group_vars/all/main.yml.

    PROXMOX_ANSIBLE_USER_VAR="proxmox_ansible_user" # Use o valor exato de main.yml

    adduser ${PROXMOX_ANSIBLE_USER_VAR}
    # Siga as instruções para definir uma senha para este novo usuário.
    # Esta senha é para o sistema Linux, não necessariamente para a API Proxmox.

    # Adicione o usuário ao grupo 'sudo' para permitir escalação de privilégios.
    usermod -aG sudo ${PROXMOX_ANSIBLE_USER_VAR}

    # Configure sudo para permitir que este usuário execute comandos como root SEM senha.
    # Isso é necessário para que o Ansible (com 'become: yes') funcione sem problemas.
    echo "${PROXMOX_ANSIBLE_USER_VAR} ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/010_${PROXMOX_ANSIBLE_USER_VAR}_nopasswd
    chmod 0440 /etc/sudoers.d/010_${PROXMOX_ANSIBLE_USER_VAR}_nopasswd
    ```

2. **Copiar sua Chave SSH Pública para o Novo Usuário Ansible no Host Proxmox:**
    Na sua **máquina de controle Ansible** (onde você gerou a chave SSH `id_ed25519_homelab` na [Seção 1.1](01-maquina-controle-ansible.md#ação-chave-ssh-essencial-para-automação)), execute o comando `ssh-copy-id`. Isso copia sua chave pública para o arquivo `~/.ssh/authorized_keys` do usuário `proxmox_ansible_user` no host Proxmox, permitindo login SSH sem senha.

    ```bash
    # Substitua 'proxmox_ansible_user' pelo nome do usuário que você acabou de criar
    # e 'IP_DO_SEU_PROXMOX' pelo endereço IP do seu host Proxmox.
    ssh-copy-id -i ~/.ssh/id_ed25519_homelab.pub proxmox_ansible_user@IP_DO_SEU_PROXMOX
    ```

    Exemplo: `ssh-copy-id -i ~/.ssh/id_ed25519_homelab.pub proxmox_ansible_user@192.168.15.10`

3. **Teste a Conexão SSH e as Permissões Sudo:**
    Ainda na sua máquina de controle Ansible, verifique se você pode se conectar via SSH como o novo usuário e executar um comando `sudo` sem senha:

    ```bash
    ssh proxmox_ansible_user@IP_DO_SEU_PROXMOX "sudo whoami"
    ```

    Isso deve se conectar sem pedir a senha do usuário `proxmox_ansible_user` (usando sua chave SSH) e o comando `sudo whoami` deve retornar `root` sem pedir a senha sudo. Se isso funcionar, o Ansible está pronto para gerenciar seu host Proxmox.

### Estrutura do Role `ansible/roles/infra/proxmox-host-config/`

Este role Ansible contém todas as tarefas para configurar o host Proxmox. Os arquivos principais são:

* `tasks/main.yml`: Define as ações a serem executadas.

#### `tasks/main.yml`

Este arquivo define as tarefas a serem executadas no host Proxmox.

```yaml title="ansible/roles/infra/proxmox-host-config/tasks/main.yml"
# ansible/roles/infra/proxmox-host-config/tasks/main.yml
- name: "Atualizar repositórios Proxmox (remover enterprise, adicionar no-subscription)"
  block:
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
  block:
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

* `templates/`: Contém arquivos de template Jinja2 (e.g., `node_exporter_host.service.j2`, `etc_exports.j2`).

#### Template `templates/node_exporter_host.service.j2`

```systemd title="ansible/roles/infra/proxmox-host-config/templates/node_exporter_host.service.j2"
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

```jinja title="ansible/roles/infra/proxmox-host-config/templates/etc_exports.j2"
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
    * `rw`: Permite leitura e escrita no compartilhamento.
    * `sync`: Força o servidor NFS a responder à requisição do cliente apenas após as mudanças terem sido escritas fisicamente no disco. É mais seguro para a integridade dos dados, mas pode ser um pouco mais lento que `async`.
    * `no_subtree_check`: Desabilita a verificação de subárvores, o que pode melhorar a confiabilidade se um subdiretório dentro do compartilhamento for renomeado enquanto estiver exportado.
    * `all_squash`: Mapeia todos os User IDs (UIDs) e Group IDs (GIDs) dos clientes NFS para o usuário anônimo no servidor.
    * `anonuid={{ docker_puid }}`: Define o UID do usuário anônimo (após o squash) para o valor da variável `docker_puid` (que é o PUID do seu `dockeruser` nas VMs).
    * `anongid={{ docker_pgid }}`: Define o GID do usuário anônimo para o valor da variável `docker_pgid` (PGID do `dockergroup` nas VMs).
    Esta combinação garante que os arquivos criados pelas VMs nos montados NFS tenham a propriedade correta para que os containers Docker (rodando como `dockeruser:dockergroup`) possam acessá-los corretamente.

* `handlers/main.yml`: Define ações que são acionadas por notificações de tarefas (e.g., reiniciar um serviço).

#### Handlers (`handlers/main.yml`)

Handlers são tarefas que são executadas apenas se notificadas por uma mudança em outra tarefa.

```yaml title="ansible/roles/infra/proxmox-host-config/handlers/main.yml"
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

Este é o playbook que você executará para aplicar o role `proxmox-host-config` ao seu host Proxmox. Certifique-se de que o arquivo `ansible/playbooks/setup-proxmox-host.yml` exista com o seguinte conteúdo:

```yaml title="ansible/playbooks/setup-proxmox-host.yml"
# ansible/playbooks/setup-proxmox-host.yml
- hosts: proxmox_main_host # Alvo definido no seu inventário (ansible/inventories/home/hosts.ini)
  become: yes # A maioria das tarefas neste role requer privilégios de root
  vars_files:
    - ../inventories/home/group_vars/all/vault.yml # Carrega variáveis sensíveis
  # Variáveis de ../inventories/home/group_vars/all/main.yml são carregadas automaticamente para 'all' hosts

  roles:
    - role: infra/proxmox-host-config # Aplica o role que configura o host
```

### Executando o Playbook `setup-proxmox-host.yml`

1. **Verifique se o Role Existe:** Certifique-se de que o diretório do role `ansible/roles/infra/proxmox-host-config/` está criado e contém os arquivos `tasks/main.yml`, `templates/node_exporter_host.service.j2`, `templates/etc_exports.j2`, e `handlers/main.yml` com o conteúdo apropriado.
2. **Execute a Partir da Máquina de Controle:** Na sua máquina de controle Ansible, navegue até a raiz do seu projeto `home-server/`.
3. **Execute o Playbook:**

    ```bash
    ansible-playbook ansible/playbooks/setup-proxmox-host.yml --ask-vault-pass
    ```

    Você será solicitado a fornecer a senha do Ansible Vault que você criou na [Seção 1.2](01-maquina-controle-ansible.md#12-criação-e-gerenciamento-de-variáveis-sensíveis-ansible-vault).

Após a execução bem-sucedida deste playbook, seu host Proxmox VE estará com as configurações base aplicadas:

* Repositórios APT ajustados (sem subscrição enterprise, com no-subscription).
* Sistema atualizado.
* Pacotes essenciais instalados.
* Fuso horário e NTP configurados.
* Firewall PVE básico configurado e habilitado.
* Configuração SSHd fortalecida.
* Node Exporter instalado e rodando para monitoramento com Prometheus.
* Servidor NFS configurado e exportando os datasets ZFS.

Com o host Proxmox pronto, o próximo passo é o [Provisionamento das Máquinas Virtuais (VMs) com Ansible](03-provisionamento-vms.md).