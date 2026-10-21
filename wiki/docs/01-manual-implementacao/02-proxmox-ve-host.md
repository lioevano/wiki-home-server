---
description: "Instala e configura o host Proxmox VE: repositórios, pool ZFS, servidor NFS, firewall e o coletor Grafana Alloy."
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
            * **Hostname (FQDN):** Defina um nome de host completo para seu servidor Proxmox. Exemplo: `pve.seudominio.com` (substitua `seudominio.com` pelo seu domínio real).
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
    # zfs_backups_dataset_name: "backups"
    # zfs_photos_dataset_name: "photos"
    # zfs_files_dataset_name: "files"
    # zfs_notes_dataset_name: "notes"

    root@pve:~# zfs create data/docker-volumes
    root@pve:~# zfs create data/media
    root@pve:~# zfs create data/backups
    # Fotos e arquivos com cota (ajuste os tamanhos ao seu acervo; ver a página 11):
    root@pve:~# zfs create -o quota=150G data/photos
    root@pve:~# zfs create -o quota=75G data/files
    # Vaults do Obsidian (segundo cérebro, página 12). refquota (não quota): os snapshots automáticos não
    # contam no limite, então a IA e o Syncthing nunca têm a escrita recusada por causa deles.
    root@pve:~# zfs create -o refquota=20G data/notes
    # A raiz de cada dataset nasce root:root 0755; com all_squash, toda escrita das VMs chega como o dockeruser
    # e seria recusada. Entregue as raízes a ele (use os valores de docker_puid e docker_pgid do vault):
    root@pve:~# chown <docker_puid>:<docker_pgid> /data/docker-volumes /data/media /data/photos /data/files /data/notes
    ```

    A cota limita o quanto fotos e arquivos podem crescer no pool compartilhado com a mídia. Para mudar depois: `zfs set quota=200G data/photos`. Um dataset com cota aparece para o `df` (e para o alerta `disco-cheio`) com o tamanho da cota, então o aviso de espaço chega antes de o pool encher.

    !!! tip "Discos novos para fotos e arquivos"
        Quando chegarem discos novos, crie um pool para eles e mova o dataset sem mudar nenhum caminho do Ansible: pare as stacks `photos`/`cloud`, faça `zfs snapshot data/photos@migra`, `zfs send data/photos@migra | zfs recv novopool/photos`, renomeie o antigo (`zfs rename data/photos data/photos-antigo`) e aponte o novo para o mesmo lugar (`zfs set mountpoint=/data/photos novopool/photos`). Reinicie o NFS (`exportfs -ra`), suba as stacks, confira e só então apague o antigo.

    Por padrão, esses datasets serão automaticamente montados pelo ZFS em `/data/docker-volumes`, `/data/media`, etc., no host Proxmox.

    !!! tip "Vantagens de Usar Datasets ZFS"
        * **Snapshots Individuais:** Você pode tirar snapshots de `data/media` sem afetar `data/docker-volumes`. Veja o [Guia de Snapshots ZFS](../03-guias-sustentacao/11-guia-snapshots-zfs.md) para mais detalhes.
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

!!! info "Firewall do Proxmox"
    As regras de entrada (SSH e Web UI da LAN, NFS v4 na porta 2049 das VMs, Alloy na porta 12345 da `core-services-vm`) são criadas **antes** de ligar o firewall com política `DROP`, para não cortar o acesso ao host no meio da execução. Os módulos são `community.proxmox.proxmox_firewall` (regras no nível do nó, identificadas pela posição `pos`) e `community.proxmox.proxmox_cluster_firewall_options` (liga o firewall e define as políticas). A API é acessada pelo IP do inventário (`ansible_host`) e o nó é `proxmox_node_name` (`group_vars/all/main.yml`), não o nome lógico `proxmox_main_host`. As tarefas específicas do Proxmox (repositórios e firewall) só rodam quando existe `/usr/bin/pveversion`: no Proxmox VE o fato `ansible_distribution` vale `Debian`, então ele não serve para reconhecer o host.

```yaml title="ansible/roles/infra/proxmox-host-config/tasks/main.yml"
# ansible/roles/infra/proxmox-host-config/tasks/main.yml
# No Proxmox VE o fato ansible_distribution é 'Debian'; o host é reconhecido pelo pveversion.
- name: "Detectar se o host é um Proxmox VE"
  ansible.builtin.stat:
    path: /usr/bin/pveversion
  register: pve_binary

# Repositórios enterprise (exigem assinatura): o PVE 8 usa arquivos .list; o PVE 9 (Debian trixie), o formato
# deb822 (.sources). As tarefas tratam os dois, cada uma só quando o arquivo existe.
- name: "Verificar repositórios enterprise no formato .list (PVE 8)"
  ansible.builtin.stat:
    path: "/etc/apt/sources.list.d/{{ item }}"
  loop:
    - pve-enterprise.list
    - ceph.list
  register: pve_enterprise_lists

- name: "Verificar repositórios enterprise no formato .sources (PVE 9)"
  ansible.builtin.stat:
    path: "/etc/apt/sources.list.d/{{ item }}"
  loop:
    - pve-enterprise.sources
    - ceph.sources
  register: pve_enterprise_sources

- name: "Atualizar repositórios Proxmox (remover enterprise, adicionar no-subscription)"
  block:
    - name: "Comentar repositórios enterprise no formato .list"
      ansible.builtin.replace:
        path: "{{ item.stat.path }}"
        regexp: '^deb'
        replace: '#deb'
      loop: "{{ pve_enterprise_lists.results }}"
      loop_control:
        label: "{{ item.item }}"
      when: item.stat.exists
    # O ceph.sources do PVE 9 aponta para o enterprise por padrão; sem Ceph, desativá-lo não tem efeito colateral.
    - name: "Desativar repositórios enterprise no formato .sources"
      ansible.builtin.lineinfile:
        path: "{{ item.stat.path }}"
        regexp: '^Enabled:'
        line: "Enabled: no"
      loop: "{{ pve_enterprise_sources.results }}"
      loop_control:
        label: "{{ item.item }}"
      when: item.stat.exists
    - name: "Adicionar repositório no-subscription (PVE 9, formato deb822)"
      ansible.builtin.deb822_repository:
        name: pve-no-subscription
        types: deb
        uris: http://download.proxmox.com/debian/pve
        suites: "{{ ansible_distribution_release }}"
        components: pve-no-subscription
        signed_by: /usr/share/keyrings/proxmox-archive-keyring.gpg
        state: present
      when: pve_enterprise_sources.results[0].stat.exists
    - name: "Adicionar repositório no-subscription (PVE 8, formato .list)"
      ansible.builtin.apt_repository:
        repo: "deb http://download.proxmox.com/debian/pve {{ ansible_distribution_release }} pve-no-subscription"
        state: present
        filename: pve-no-subscription
      when: not pve_enterprise_sources.results[0].stat.exists
  when: pve_binary.stat.exists
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

# Regras primeiro: ligar o firewall com DROP antes delas cortaria o acesso ao host.
- name: "Permitir SSH, Web UI, NFS e Alloy no Firewall do Host Proxmox"
  community.proxmox.proxmox_firewall:
    level: node
    node: "{{ proxmox_node_name }}" # Nome do nó no Proxmox (group_vars), não o nome lógico do inventário
    state: present
    update: true # Regras identificadas por 'pos': reexecutar atualiza em vez de duplicar
    rules:
      - { pos: 0, type: in, action: ACCEPT, enable: true, iface: "{{ proxmox_default_bridge }}", source: "{{ proxmox_ssh_allowed_cidrs }}", dport: "22", proto: tcp, comment: "Allow SSH from Local LAN" }
      - { pos: 1, type: in, action: ACCEPT, enable: true, iface: "{{ proxmox_default_bridge }}", source: "{{ proxmox_web_ui_allowed_cidrs }}", dport: "8006", proto: tcp, comment: "Allow Proxmox WebUI from Local LAN" }
      - { pos: 2, type: in, action: ACCEPT, enable: true, iface: "{{ proxmox_default_bridge }}", source: "{{ vm_nfs_allowed_clients_cidr }}", dport: "2049", proto: tcp, comment: "NFS v4 das VMs" }
      - { pos: 3, type: in, action: ACCEPT, enable: true, iface: "{{ proxmox_default_bridge }}", source: "{{ core_services_vm_ip_var }}", dport: "12345", proto: tcp, comment: "Alloy: Prometheus da core-services-vm" }
    api_user: "{{ proxmox_api_user }}" # Do vault.yml
    api_password: "{{ proxmox_api_password }}" # Do vault.yml
    api_host: "{{ ansible_host }}" # IP do host Proxmox no inventário
  notify: Reload PVE Firewall
  when: pve_binary.stat.exists

- name: "Configurar Firewall Proxmox (PVE Firewall) - Políticas Globais"
  community.proxmox.proxmox_cluster_firewall_options:
    state: enabled # Habilita o firewall no datacenter
    input_policy: DROP # Política padrão para tráfego de entrada
    output_policy: ACCEPT # Política padrão para tráfego de saída
    api_user: "{{ proxmox_api_user }}"
    api_password: "{{ proxmox_api_password }}"
    api_host: "{{ ansible_host }}"
  notify: Reload PVE Firewall
  when: pve_binary.stat.exists

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

# --- Snapshots automáticos só nos vaults (segundo cérebro, página 12) ---
# O zfs-auto-snapshot tira snapshots de todo dataset cuja propriedade com.sun:auto-snapshot não seja 'false'.
# Desligada em todos os pools (os filhos herdam) e ligada só em notes: a mídia não acumula snapshots de arquivos apagados.
# Retenção padrão do pacote: 15 min ×4, hora ×24, dia ×31, semana ×8, mês ×12.
- name: "Instalar o zfs-auto-snapshot"
  ansible.builtin.apt:
    name: zfs-auto-snapshot
    state: present

# Todos os pools, não só o 'data': com o Proxmox instalado em ZFS (rpool), os discos das VMs também levariam snapshots.
- name: "Listar os pools ZFS do host"
  ansible.builtin.command: zpool list -H -o name
  register: zfs_pools
  changed_when: false

- name: "Desligar snapshots automáticos em cada pool (herdado pelos datasets)"
  community.general.zfs:
    name: "{{ item }}"
    state: present
    extra_zfs_properties:
      "com.sun:auto-snapshot": "false"
  loop: "{{ zfs_pools.stdout_lines }}"

- name: "Ligar snapshots automáticos no dataset dos vaults"
  community.general.zfs:
    name: "data/{{ zfs_notes_dataset_name }}"
    state: present
    extra_zfs_properties:
      "com.sun:auto-snapshot": "true"

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

* `templates/`: Contém arquivos de template Jinja2 (e.g., `etc_exports.j2`).

#### Template `templates/etc_exports.j2`

```jinja title="ansible/roles/infra/proxmox-host-config/templates/etc_exports.j2"
# ansible/roles/infra/proxmox-host-config/templates/etc_exports.j2
# Gerenciado por Ansible - NÃO EDITE MANUALMENTE
# Define os compartilhamentos NFS para os datasets ZFS do host Proxmox.

# Variáveis Ansible usadas (definidas em group_vars/all/main.yml e vault.yml):
# {{ zfs_base_pool_path }}: Caminho base do pool ZFS (e.g., /data)
# {{ vm_nfs_allowed_clients_cidr }}: CIDR da sub-rede das VMs (e.g., 192.168.15.0/24)
# {{ docker_puid }}: User ID numérico do usuário 'dockeruser' nas VMs.
# {{ docker_pgid }}: Group ID numérico do grupo 'dockergroup' nas VMs.

# Compartilhamento para volumes Docker gerais
{{ zfs_base_pool_path }}/{{ zfs_docker_volumes_dataset_name }} {{ vm_nfs_allowed_clients_cidr }}(rw,sync,no_subtree_check,all_squash,anonuid={{ docker_puid }},anongid={{ docker_pgid }})

# Compartilhamento para mídia e torrents (mesmo dataset: a importação das *arr é por hardlink)
{{ zfs_base_pool_path }}/{{ zfs_media_dataset_name }} {{ vm_nfs_allowed_clients_cidr }}(rw,sync,no_subtree_check,all_squash,anonuid={{ docker_puid }},anongid={{ docker_pgid }})

# Compartilhamentos de fotos (Immich) e arquivos (Nextcloud), montados na core-services-vm; 'files' também na VM de IA,
# só leitura na montagem, para o conversor de documentos do segundo cérebro (página 12)
{{ zfs_base_pool_path }}/{{ zfs_photos_dataset_name }} {{ vm_nfs_allowed_clients_cidr }}(rw,sync,no_subtree_check,all_squash,anonuid={{ docker_puid }},anongid={{ docker_pgid }})
{{ zfs_base_pool_path }}/{{ zfs_files_dataset_name }} {{ vm_nfs_allowed_clients_cidr }}(rw,sync,no_subtree_check,all_squash,anonuid={{ docker_puid }},anongid={{ docker_pgid }})

# Vaults do Obsidian (segundo cérebro, página 12): exportado só para a VM de IA, onde rodam o Syncthing e a busca
{{ zfs_base_pool_path }}/{{ zfs_notes_dataset_name }} {{ ai_desktop_vm_ip_var }}(rw,sync,no_subtree_check,all_squash,anonuid={{ docker_puid }},anongid={{ docker_pgid }})

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
  when: pve_binary.stat.exists
  # Usar 'command' pois pode não haver um módulo Ansible específico para 'pve-firewall restart'
  # que seja idempotente da maneira que queremos (apenas recarregar).

- name: Restart sshd
  ansible.builtin.systemd_service:
    name: sshd # Ou ssh.service, dependendo da distro
    state: restarted

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
    - role: infra/alloy # Coletor de logs e métricas (seção 4.4 do manual); sem Docker no host
    - role: infra/restic # Backup diário dos datasets com restic (página 04/02)
```

### Executando o Playbook `setup-proxmox-host.yml`

1. **Verifique se o Role Existe:** Certifique-se de que o diretório do role `ansible/roles/infra/proxmox-host-config/` está criado e contém os arquivos `tasks/main.yml`, `templates/etc_exports.j2` e `handlers/main.yml`, que o role `ansible/roles/infra/alloy/` existe ([seção 4.4](04-configuracao-base-vms-ubuntu.md#44-coleta-com-grafana-alloy-ansiblerolesinfraalloy)) e que o role `ansible/roles/infra/restic/` existe ([backup](../04-manutencao-recuperacao/02-backup-restore-estrategia.md#restic-no-host-proxmox)). O restic precisa de `restic_senha` e `restic_repositorios` no vault; prepare os destinos antes (disco externo e bucket).
2. **Execute a Partir da Máquina de Controle:** Na sua máquina de controle Ansible, entre na pasta `server/ansible` do repositório.
3. **Execute o Playbook:**

    ```bash
    ansible-playbook -i inventories/home/hosts.ini playbooks/setup-proxmox-host.yml --ask-vault-pass
    ```

    Você será solicitado a fornecer a senha do Ansible Vault que você criou na [Seção 1.2](01-maquina-controle-ansible.md#12-criação-e-gerenciamento-de-variáveis-sensíveis-ansible-vault).

Após a execução bem-sucedida deste playbook, seu host Proxmox VE estará com as configurações base aplicadas:

* Repositórios APT ajustados (sem subscrição enterprise, com no-subscription).
* Sistema atualizado.
* Pacotes essenciais instalados.
* Fuso horário e NTP configurados.
* Firewall PVE configurado e habilitado: entrada só para SSH e Web UI (LAN), NFS v4 (VMs) e Alloy (`core-services-vm`).
* Configuração SSHd fortalecida.
* Grafana Alloy instalado e enviando métricas (inclusive ZFS) e o journal do host para o Prometheus e o Loki.
* Servidor NFS configurado e exportando os datasets ZFS.

Com o host Proxmox pronto, o próximo passo é o [Provisionamento das Máquinas Virtuais (VMs) com Ansible](03-provisionamento-vms.md).