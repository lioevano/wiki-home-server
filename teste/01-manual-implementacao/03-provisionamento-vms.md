# Seção 3: Provisionamento das Máquinas Virtuais (VMs) com Ansible

Com o host Proxmox VE configurado, o próximo passo é provisionar as máquinas virtuais (VMs) que hospedarão seus serviços. Utilizaremos Ansible para automatizar a criação e configuração inicial dessas VMs a partir de um template Ubuntu Server Cloud-Init.

Nesta arquitetura, devido à limitação de 16GB de RAM, planejamos duas VMs principais:
*   `core-services-vm`: Hospedará a maioria dos serviços Docker (Traefik, Portainer, Nextcloud, mídia, monitoramento, etc.).
*   `ai-desktop-vm`: Opcional, dedicada a tarefas de IA/LLM que podem exigir GPU passthrough e mais recursos.

## 3.1. Criação de Template de VM Base (Ubuntu Server Cloud-Init)

Um template de VM permite clonar rapidamente novas VMs já com configurações base. Usaremos uma imagem Cloud-Init do Ubuntu Server.

Siga estes passos na **interface web do Proxmox VE** ou no **shell do host Proxmox**:

1.  **Download da Imagem Cloud-Init do Ubuntu Server:**
    No shell do host Proxmox (como `root`):
    ```bash
    # Exemplo para Ubuntu 22.04 LTS (Jammy Jellyfish)
    # Verifique o link mais recente em https://cloud-images.ubuntu.com/
    IMAGE_URL="https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.qcow2"
    IMAGE_FILENAME="jammy-server-cloudimg-amd64.qcow2"
    # O storage 'local' é geralmente onde ISOs e templates são armazenados no Proxmox
    # Corresponde a proxmox_storage_iso_templates de main.yml
    DOWNLOAD_PATH="/var/lib/vz/template/iso"

    wget -P ${DOWNLOAD_PATH} ${IMAGE_URL}
    ```

2.  **Crie uma Nova VM Base para o Template:**
    *   Na UI do Proxmox, clique em "Create VM".
    *   **General:**
        *   **VM ID:** Escolha um ID alto, fora da sua faixa usual de VMs (e.g., `9000`).
        *   **Name:** `ubuntu-2204-cloudinit-base` (ou similar).
    *   **OS:**
        *   Selecione **"Do not use any media"**.
        *   Guest OS: Type `Linux`, Version `5.x - 2.6 Kernel`.
    *   **System:**
        *   **Machine:** `q35` (mais moderno).
        *   **BIOS:** `OVMF (UEFI)`.
        *   **EFI Storage:** Selecione o storage onde o disco EFI será armazenado (e.g., `local-lvm`).
        *   **Add TPM:** Opcional, mas bom para futuras features de segurança (escolha `v2.0`).
    *   **Hard Disk:**
        *   Ignore por enquanto (vamos importar o disco qcow2).
    *   **CPU:** 1 core (suficiente para o template).
    *   **Memory:** 1024 MB ou 2048 MB (suficiente para o template).
    *   **Network:** Use a bridge padrão (`vmbr0`), modelo VirtIO.
    *   Confirme e crie a VM, **mas não a inicie ainda.**

3.  **Importe o Disco da Imagem Cloud-Init para a VM Base:**
    No shell do host Proxmox (como `root`):
    ```bash
    # Substitua 9000 pelo VM ID da sua VM base
    # Substitua local-lvm pelo nome do seu storage para discos de VM (proxmox_storage_vm_disks)
    qm importdisk 9000 ${DOWNLOAD_PATH}/${IMAGE_FILENAME} {{ proxmox_storage_vm_disks }}
    ```
    Exemplo: `qm importdisk 9000 /var/lib/vz/template/iso/jammy-server-cloudimg-amd64.qcow2 local-lvm`

4.  **Anexe o Disco Importado à VM Base:**
    *   Na UI do Proxmox, selecione a VM base (ID 9000).
    *   Vá para a aba "Hardware".
    *   Você verá um disco "Unused Disk 0" (ou similar). Selecione-o e clique em "Edit".
    *   **Bus/Device:** Escolha `SCSI`.
    *   **SSD emulation:** Marque se o seu storage (`local-lvm`) está em um SSD.
    *   Clique em "Add".

5.  **Configure a Ordem de Boot:**
    *   Ainda na aba "Hardware", vá em "Boot Order".
    *   Habilite o disco SCSI que você acabou de adicionar (`scsi0`) e mova-o para o topo da ordem. Desabilite outras opções de boot como CD-ROM ou Rede se não forem necessárias.

6.  **Adicione um Drive Cloud-Init:**
    *   Na aba "Hardware", clique em "Add" -> "CloudInit Drive".
    *   **Storage:** Selecione o mesmo storage onde o disco da VM está (e.g., `local-lvm`).
    *   Este drive será usado pelo Ansible para passar configurações iniciais (usuário, senha, chave SSH, rede) para as VMs clonadas.

7.  **(Opcional, mas Recomendado) Instalar `qemu-guest-agent` no Template:**
    O `qemu-guest-agent` melhora a interação entre o host Proxmox e a VM (e.g., para obter o IP da VM, desligamento correto).
    *   Inicie a VM base (ID 9000) a partir do console na UI do Proxmox.
    *   A imagem cloud-init deve bootar e você eventualmente chegará a um login prompt. O usuário padrão e senha podem variar (ubuntu/ubuntu ou sem senha, acesso direto ao root).
    *   Execute os seguintes comandos dentro da VM:
        ```bash
        sudo apt update
        sudo apt install -y qemu-guest-agent
        sudo systemctl enable qemu-guest-agent
        sudo systemctl start qemu-guest-agent
        ```
    *   **Limpeza (Opcional, para reduzir o tamanho do template):**
        ```bash
        sudo apt-get clean
        sudo rm -rf /tmp/* /var/tmp/*
        sudo cloud-init clean --logs --seed # Limpa dados de cloud-init
        # sudo rm /etc/ssh/ssh_host_* # Opcional: remove chaves SSH do host, serão geradas no clone
        # history -c && history -w # Limpa o histórico do bash
        ```
    *   Desligue a VM base: `sudo shutdown now`.

8.  **Converta a VM Base para um Template:**
    *   Na UI do Proxmox, clique com o botão direito na VM base (ID 9000).
    *   Selecione "**Convert to template**".
    *   !!! important "Nome do Template"
        O nome do template resultante no Proxmox deve corresponder exatamente ao valor da variável `proxmox_ubuntu_template_name` definida em `ansible/inventories/home/group_vars/all/main.yml` (e.g., `ubuntu-2204-cloudinit-template-v1`).

## 3.2. Role Ansible `proxmox-vm` (`ansible/roles/infra/proxmox-vm/`)

Este role Ansible será responsável por clonar VMs a partir do template, redimensionar seus discos, e configurar Cloud-Init para nome de usuário, senha, chave SSH e rede.

### `defaults/main.yml`

Valores padrão para o role. Estes podem ser sobrescritos no playbook que chama o role.

```yaml
# ansible/roles/infra/proxmox-vm/defaults/main.yml
# Variáveis padrão para o role proxmox-vm.
# Valores obrigatórios (vm_id, vm_name, vm_ipconfig) devem ser definidos no playbook que chama o role.

# Nome do template Proxmox a ser clonado (deve corresponder ao template criado na Seção 3.1)
vm_template: "{{ proxmox_ubuntu_template_name }}" # Definido em group_vars/all/main.yml

# Recursos padrão da VM (podem ser sobrescritos por VM)
vm_cores: "{{ vm_default_cores | default(2) }}"    # Número de cores CPU
vm_memory: "{{ vm_default_memory_mb | default(2048) }}" # Memória RAM em MB
vm_disk_gb: "{{ vm_default_disk_gb | default(32) }}" # Tamanho final do disco principal (scsi0) em GB

# Configurações Proxmox para a VM
vm_os_type: "l26" # Tipo de OS Proxmox (l26 para Linux genérico 2.6/3.x/4.x/5.x kernel)
vm_bridge: "{{ proxmox_default_bridge | default('vmbr0') }}" # Bridge de rede Proxmox
vm_storage_disk: "{{ proxmox_storage_vm_disks | default('local-lvm') }}" # Storage para o disco da VM

# Configuração Cloud-Init
vm_ci_user: "{{ vm_ansible_user_name | default('vm_ansible_user') }}" # Nome do usuário a ser criado via cloud-init
vm_ci_password: "{{ vm_ansible_user_password_plain }}"      # Senha para vm_ci_user (do vault.yml)
# Caminho para a chave SSH pública na máquina de controle Ansible
vm_ci_ssh_keys_public_file: "{{ ansible_ssh_private_key_file | regex_replace('.$', 'pub') | expanduser }}" # Adiciona .pub ao nome da chave privada e expande ~
vm_ci_nameservers: "{{ vm_cloud_init_nameservers | default('1.1.1.1,8.8.8.8') }}" # DNS para a VM
# A variável vm_ipconfig (e.g., "dhcp" ou "ip=IP/MASK,gw=GATEWAY") DEVE ser passada pelo playbook.

# Comportamento da VM
vm_start_at_boot: true         # Iniciar VM quando o host Proxmox iniciar
vm_qemu_agent_enabled: true    # Habilitar o QEMU Guest Agent (requer instalado na VM/template)
vm_tags: "ansible_managed,homelab"     # Tags para organização no Proxmox

# Configurações avançadas (principalmente para GPU passthrough)
vm_vga_type: "std"             # Tipo de display virtual ('std', 'cirrus', 'vmware', 'qxl', 'serial0', 'none')
vm_machine_type: "q35"         # Tipo de máquina virtual (q35 é mais moderno)
vm_bios_type: "ovmf"           # BIOS ('seabios' ou 'ovmf' para UEFI)
# Lista de dispositivos PCI do host para passthrough (e.g., ["01:00.0", "01:00.1"])
# Para cada device, pode-se adicionar opções: "01:00.0,pcie=1,x-vga=1"
vm_host_pci_devices: []
# Argumentos QEMU adicionais
vm_qemu_args: ""
```
!!! note "Chave SSH Pública para Cloud-Init"
    A linha `vm_ci_ssh_keys_public_file: "{{ ansible_ssh_private_key_file | regex_replace('.$', 'pub') | expanduser }}"` assume que sua chave pública tem o mesmo nome da privada, mas com `.pub` no final, e que `ansible_ssh_private_key_file` (de `hosts.ini`) aponta para a chave privada.

### `tasks/main.yml`

Tarefas para criar/configurar a VM.

```yaml
# ansible/roles/infra/proxmox-vm/tasks/main.yml
# Cria ou atualiza uma VM no Proxmox a partir de um template.

- name: "Garantir que a chave SSH pública para Cloud-Init existe na máquina de controle"
  ansible.builtin.stat:
    path: "{{ vm_ci_ssh_keys_public_file }}"
  register: ssh_key_stat
  delegate_to: localhost # Esta verificação é feita na máquina de controle Ansible

- name: "Falhar se a chave SSH pública não for encontrada"
  ansible.builtin.fail:
    msg: "Chave SSH pública {{ vm_ci_ssh_keys_public_file }} não encontrada. Verifique o caminho ou gere a chave."
  when: not ssh_key_stat.stat.exists
  delegate_to: localhost

- name: "Verificar se a VM {{ vm_name }} (ID: {{ vm_id }}) já existe no Proxmox"
  community.proxmox.proxmox_kvm_info:
    vmid: "{{ vm_id }}"
    api_user: "{{ proxmox_api_user }}"
    api_password: "{{ proxmox_api_password | default(omit) }}"
    api_token_id: "{{ proxmox_api_token_id | default(omit) }}"
    api_token_secret: "{{ proxmox_api_token_secret | default(omit) }}"
    api_host: "{{ groups['proxmox_hosts'][0] }}" # Pega o primeiro host do grupo proxmox_hosts
  register: vm_info_check
  delegate_to: localhost # A API Proxmox é chamada da máquina de controle

- name: "Clonar VM {{ vm_name }} (ID: {{ vm_id }}) a partir do template {{ vm_template }}"
  community.proxmox.proxmox_kvm:
    api_user: "{{ proxmox_api_user }}"
    api_password: "{{ proxmox_api_password | default(omit) }}"
    api_token_id: "{{ proxmox_api_token_id | default(omit) }}"
    api_token_secret: "{{ proxmox_api_token_secret | default(omit) }}"
    api_host: "{{ groups['proxmox_hosts'][0] }}"
    clone: "{{ vm_template }}"
    newid: "{{ vm_id }}"
    name: "{{ vm_name }}"
    full: true # Cria um clone completo (não um linked clone)
    state: present # Garante que a VM clonada exista
    timeout: 600 # Timeout para a operação de clone em segundos (10 minutos)
  when: not vm_info_check.proxmox_kvm_info or vm_info_check.proxmox_kvm_info.status == "unknown" # Só clona se não existir
  delegate_to: localhost
  notify: Configure VM settings # Handler para configurar após o clone (ou se já existir)

- name: "Configurar recursos e Cloud-Init para VM {{ vm_name }} (ID: {{ vm_id }})"
  community.proxmox.proxmox_kvm:
    api_user: "{{ proxmox_api_user }}"
    api_password: "{{ proxmox_api_password | default(omit) }}"
    api_token_id: "{{ proxmox_api_token_id | default(omit) }}"
    api_token_secret: "{{ proxmox_api_token_secret | default(omit) }}"
    api_host: "{{ groups['proxmox_hosts'][0] }}"
    vmid: "{{ vm_id }}"
    node: "{{ (vm_info_check.proxmox_kvm_info.node if vm_info_check.proxmox_kvm_info else omit) | default(omit) }}" # Necessário para algumas operações de update

    # Recursos da VM
    cores: "{{ vm_cores }}"
    memory: "{{ vm_memory }}"
    agent: "{{ vm_qemu_agent_enabled | ternary('enabled=1', 'enabled=0') }}"
    tags: "{{ vm_tags }}"
    onboot: "{{ vm_start_at_boot | bool }}"
    startup: "{{ 'order=1,up=60' if vm_start_at_boot else '' }}" # Ordem de boot e delay se autostart
    scsihw: "virtio-scsi-pci" # Controlador SCSI para melhor performance

    # Redimensionar disco principal (scsi0) se vm_disk_gb for definido
    # O disco já deve existir (criado pelo clone do template). Esta task irá redimensioná-lo.
    disk:
      scsi0:
        size: "{{ vm_disk_gb }}G"
        storage: "{{ vm_storage_disk }}"
        # O 'disk' parameter pode precisar ser mais específico se o template tiver múltiplos discos.
        # Geralmente o disco principal do template é scsi0.

    # Configuração de rede via Cloud-Init (ipconfig0)
    # A interface de rede net0 é geralmente criada pelo template.
    net:
      net0: "model=virtio,bridge={{ vm_bridge }}" # Garante que net0 está configurada
    # Configuração IP para net0 via Cloud-Init
    ipconfig0: "{{ vm_ipconfig }}" # Ex: "ip={{ hostvars[vm_name]['ansible_host'] }}/24,gw={{ vm_cloud_init_gateway }}" ou "dhcp"

    # Configurações Cloud-Init
    nameserver: "{{ vm_ci_nameservers }}"
    searchdomain: "{{ base_domain | default(omit) }}" # Omitir se base_domain não estiver definido
    ciuser: "{{ vm_ci_user }}"
    cipassword: "{{ vm_ci_password }}" # Senha em texto plano para cloud-init
    sshkeys: "{{ lookup('file', vm_ci_ssh_keys_public_file) | urlencode }}" # Lê a chave pública e formata para a API

    # Configurações para GPU Passthrough e outras opções avançadas
    vga: "{{ vm_vga_type }}"
    machine: "{{ vm_machine_type }}"
    bios: "{{ vm_bios_type }}"
    # Mapeamento de dispositivos PCI para passthrough
    # O módulo proxmox_kvm espera uma string como 'hostpci0=01:00.0,pcie=1;hostpci1=01:00.1'
    args: >-
      {% set pci_args_list = [] %}
      {% for idx, device in enumerate(vm_host_pci_devices) %}
      {%   set _ = pci_args_list.append("hostpci" + idx|string + "=" + device) %}
      {% endfor %}
      {% set pci_string = pci_args_list | join(';') %}
      {{ (pci_string + " " + vm_qemu_args) if pci_string else vm_qemu_args | default('') }}

    state: present # Garante que a VM exista com estas configurações
    update: true   # Permite atualizar uma VM existente
    timeout: 300
  delegate_to: localhost
  notify: Start VM after configuration # Handler para iniciar/reiniciar a VM
```

### `handlers/main.yml`

Handlers para o role `proxmox-vm`.

```yaml
# ansible/roles/infra/proxmox-vm/handlers/main.yml
- name: Configure VM settings
  ansible.builtin.debug:
    msg: "VM {{ vm_name }} (ID: {{ vm_id }}) clonada/verificada. Aplicando configurações detalhadas e iniciando."

- name: Start VM after configuration
  community.proxmox.proxmox_kvm:
    api_user: "{{ proxmox_api_user }}"
    api_password: "{{ proxmox_api_password | default(omit) }}"
    api_token_id: "{{ proxmox_api_token_id | default(omit) }}"
    api_token_secret: "{{ proxmox_api_token_secret | default(omit) }}"
    api_host: "{{ groups['proxmox_hosts'][0] }}"
    vmid: "{{ vm_id }}"
    node: "{{ (vm_info_check.proxmox_kvm_info.node if vm_info_check.proxmox_kvm_info else omit) | default(omit) }}" # Necessário para start
    state: started # Garante que a VM esteja rodando
    timeout: 120 # Timeout para iniciar a VM
  delegate_to: localhost
```

## 3.3. Playbook para Deploy de VM (`ansible/playbooks/vm-deploy.yml`)

Este playbook utiliza o role `proxmox-vm` para criar as VMs especificadas.

Crie o arquivo `ansible/playbooks/vm-deploy.yml`:

```yaml
# ansible/playbooks/vm-deploy.yml
- hosts: proxmox_main_host # O playbook é executado *contra* o host Proxmox (para delegar as tasks da API)
  gather_facts: no # Não precisamos de fatos do Proxmox host para estas tasks delegadas
  vars_files:
    - ../inventories/home/group_vars/all/vault.yml
  # Variáveis de group_vars/all/main.yml e hosts.ini são carregadas automaticamente

  tasks:
    - name: "Deploy VM: core-services-vm"
      ansible.builtin.include_role:
        name: infra/proxmox-vm
      vars:
        vm_id: 100 # Escolha um ID único para esta VM
        vm_name: "core-services-vm" # DEVE corresponder ao nome no seu hosts.ini
        vm_cores: 4 # Ryzen 5 5600G tem 6 cores. Ajuste conforme sua necessidade.
        vm_memory: 6144 # 6GB RAM. (16GB Total - 6GB VM1 - 2GB Host = 8GB para VM2 ou folga)
        vm_disk_gb: 80 # Tamanho do disco em GB
        # IP estático para a VM, usando o IP definido no inventário (hosts.ini)
        vm_ipconfig: "ip={{ hostvars['core-services-vm']['ansible_host'] }}/24,gw={{ vm_cloud_init_gateway }}"
        vm_tags: "docker,core_services,homelab,ansible_managed"

    - name: "Deploy VM: ai-desktop-vm (Opcional, para LLM/RAG com GPU)"
      ansible.builtin.include_role:
        name: infra/proxmox-vm
      vars:
        vm_id: 101 # ID único
        vm_name: "ai-desktop-vm" # DEVE corresponder ao nome no hosts.ini
        vm_cores: 4 # Se for usar intensivamente, pode precisar de mais, mas cuidado com a RAM total do host
        vm_memory: 8192 # 8GB RAM. Máximo possível deixando ~2GB para o Proxmox host.
        vm_disk_gb: 150 # Para modelos LLM e SO
        vm_ipconfig: "ip={{ hostvars['ai-desktop-vm']['ansible_host'] }}/24,gw={{ vm_cloud_init_gateway }}"
        vm_tags: "llm,rag,ai_gpu,desktop,homelab,ansible_managed"

        # --- Configurações para GPU Passthrough (Exemplo para RX 5600XT) ---
        # !!! Substitua pelos IDs PCI REAIS da sua GPU no host Proxmox !!!
        # Use 'lspci -nn' no shell do Proxmox host para encontrar os IDs [vendor:device]
        # e remova o prefixo "0000:".
        # Exemplo: Se lspci -nn mostra "09:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Navi 10 [Radeon RX 5600 OEM/5600 XT / 5700/5700 XT] [1002:731f]"
        # e "09:00.1 Audio device [0403]: Advanced Micro Devices, Inc. [AMD/ATI] Navi 10/10M/12/14 HDMI Audio Device [1002:ab28]"
        # Os IDs PCI são "09:00.0" e "09:00.1".
        vm_vga_type: "none" # Necessário para GPU passthrough como placa gráfica principal da VM
        vm_host_pci_devices:
          - "09:00.0,pcie=1,x-vga=1"  # ID_PCI_GPU_VIDEO com opções (pcie=1 para performance, x-vga=1 para ser primária)
          - "09:00.1,pcie=1"         # ID_PCI_GPU_AUDIO (geralmente associado à GPU)
        # Opcional: Se precisar de um arquivo ROM para a GPU AMD (raro, mais comum para NVIDIA)
        # vm_qemu_args: "-device vfio-pci,host=09:00.0,romfile=amd_rx5600xt.rom"
        # Argumentos para tentar esconder que é uma VM (pode ser necessário para drivers NVIDIA)
        # vm_qemu_args: "-cpu host,kvm=off,hv_relaxed,hv_spinlocks=0x1fff,hv_vapic,hv_time,hv_vendor_id=NvidiaFuckYou"
      when: "'ai-desktop-vm' in groups['virtual_machines']" # Só executa se a VM estiver definida no inventário

    # Aguardar que as VMs estejam prontas e atualizar o inventário Ansible em memória
    - name: "Aguardar todas as VMs Ubuntu recém-criadas/configuradas estarem acessíveis via SSH"
      ansible.builtin.wait_for:
        host: "{{ hostvars[item]['ansible_host'] }}" # IP da VM do inventário
        port: 22
        delay: 60  # Espera inicial antes do primeiro check (Cloud-Init pode demorar)
        timeout: 360 # Tempo máximo de espera em segundos (6 minutos)
        state: started
        msg: "Aguardando SSH na VM {{ item }} ({{ hostvars[item]['ansible_host'] }})"
      loop: "{{ query('inventory_hostnames', 'ubuntu_vms') }}" # Itera sobre todas as VMs no grupo 'ubuntu_vms'
      delegate_to: localhost # A tarefa wait_for roda na máquina de controle Ansible

    - name: "Atualizar inventário Ansible em memória para refletir novas VMs"
      ansible.builtin.meta: refresh_inventory
```
!!! warning "Alocação de RAM e IDs PCI"
    *   **RAM Total:** A soma da RAM alocada para `core-services-vm` (6GB) + `ai-desktop-vm` (8GB) é 14GB. Isso deixa apenas 2GB para o Proxmox host, o que é **extremamente apertado**. Considere:
        *   Reduzir a memória de uma das VMs (e.g., `ai-desktop-vm` para 6GB, ou `core-services-vm` para 4GB se seus serviços permitirem).
        *   Não rodar ambas as VMs com carga máxima simultaneamente.
        *   Para uso intensivo de LLMs na `ai-desktop-vm`, pode ser necessário desligar a `core-services-vm` temporariamente ou reduzir drasticamente os serviços nela.
    *   **IDs PCI para GPU:** Use `lspci -nn` no shell do host Proxmox para encontrar os IDs corretos da sua RX 5600XT (a parte de vídeo e a parte de áudio, e.g., `09:00.0` e `09:00.1`). Substitua os valores de exemplo em `vm_host_pci_devices` pelos seus IDs reais.

### Executando o Playbook de Deploy das VMs

1.  Na sua máquina de controle Ansible, navegue até a raiz do projeto `home-server/`.
2.  Execute o playbook:
    ```bash
    ansible-playbook ansible/playbooks/vm-deploy.yml --ask-vault-pass
    ```

Após a execução, suas VMs devem estar criadas e configuradas com os parâmetros básicos de Cloud-Init.

## 3.4. Configuração de GPU Passthrough (Host Proxmox)

Se você planeja usar a `ai-desktop-vm` com a RX 5600XT para aceleração de IA, a configuração de GPU passthrough no host Proxmox é necessária. Este é um processo avançado e pode variar um pouco dependendo do seu hardware.

**Resumo das Etapas Essenciais no Host Proxmox (Reforçando):**

1.  **BIOS/UEFI do Servidor:**
    *   Já deve ter sido feito (Seção 2.1): AMD-V (SVM) e IOMMU (AMD-Vi) **habilitados**.

2.  **Configuração do Kernel Proxmox:**
    *   Edite `/etc/default/grub` no host Proxmox:
        ```bash
        # Exemplo de linha GRUB_CMDLINE_LINUX_DEFAULT
        # Se a iGPU do 5600G for usada para o console Proxmox e a RX 5600XT for apenas para passthrough,
        # video=efifb:off pode ajudar a desvincular a RX 5600XT do console do host. Teste!
        # amd_iommu=on e iommu=pt são cruciais.
        GRUB_CMDLINE_LINUX_DEFAULT="quiet amd_iommu=on iommu=pt video=efifb:off"
        ```
    *   Após editar, execute: `sudo update-grub`.
    *   Adicione os seguintes módulos a `/etc/modules` (um por linha):
        ```
        vfio
        vfio_iommu_type1
        vfio_pci
        vfio_virqfd
        ```
    *   Execute: `sudo update-initramfs -u -k all`.

3.  **Blacklist dos Drivers da GPU no Host Proxmox:**
    Crie (ou edite) o arquivo `/etc/modprobe.d/vfio-blacklist.conf` no host Proxmox com o seguinte conteúdo, **substituindo os VENDOR_ID e DEVICE_ID pelos da sua RX 5600XT** (obtidos com `lspci -nn`):
    ```
    # Blacklist drivers AMD para que vfio-pci possa controlar a GPU
    blacklist amdgpu
    blacklist radeon

    # Carrega vfio-pci para os IDs específicos da sua RX 5600XT
    # Exemplo para RX 5600XT (vídeo: 1002:731f, áudio: 1002:ab28)
    options vfio-pci ids=1002:731f,1002:ab28
    ```
    !!! tip "Encontrando VENDOR_ID:DEVICE_ID"
        O comando `lspci -nn | grep -i amd | grep -i vga` (para vídeo) e `lspci -nn | grep -i amd | grep -i audio` (para áudio associado à GPU) ajudará a encontrar os IDs corretos no formato `[VENDOR_ID:DEVICE_ID]`.

4.  **Reinicie o Host Proxmox.**

5.  **Verifique a Configuração IOMMU e Grupos:**
    Após o reboot, no shell do host Proxmox, execute:
    ```bash
    dmesg | grep -e DMAR -e IOMMU
    # E para verificar os grupos IOMMU:
    find /sys/kernel/iommu_groups/ -type l
    ```
    Você deve ver mensagens indicando que o IOMMU está habilitado e os dispositivos PCI da sua RX 5600XT (vídeo e áudio) devem estar, idealmente, em seus próprios grupos IOMMU isolados.

    Para uma verificação mais detalhada dos grupos:
    ```bash
    for d in /sys/kernel/iommu_groups/*/devices/*; do n=${d#*/iommu_groups/*}; n=${n%%/*}; printf 'IOMMU Group %s ' "$n"; lspci -nns "${d##*/}"; done
    ```
    Procure pelos dispositivos da sua RX 5600XT e verifique se não estão agrupados com outros dispositivos críticos do sistema que você não quer passar para a VM.

A configuração de GPU passthrough é complexa. Consulte guias detalhados online específicos para Proxmox e AMD GPUs se encontrar problemas.

## 3.5. Configuração de Ambiente Desktop (GUI) em VMs Linux (Opcional)

Para a `ai-desktop-vm`, se você deseja uma interface gráfica para interagir com ela (especialmente se estiver usando GPU passthrough e conectar um monitor diretamente), você pode instalar um ambiente desktop.

### Role: `ansible/roles/apps/desktop-environment/`

Este role instala XFCE (um ambiente leve) e TightVNCServer (para acesso remoto à GUI se não usar GPU passthrough direto com monitor).

#### `tasks/main.yml`

```yaml
# ansible/roles/apps/desktop-environment/tasks/main.yml
- name: "Atualizar apt cache e instalar ambiente XFCE e TightVNCServer"
  ansible.builtin.apt:
    name:
      - xfce4
      - xfce4-goodies
      - tightvncserver
      - dbus-x11 # Necessário para algumas sessões XFCE
      - firefox-esr # Um navegador web básico
      # Adicione outros pacotes que desejar para o ambiente desktop
    state: present
    update_cache: yes
  when: install_gui_flag | default(false) | bool # Variável passada pelo playbook (GUI_ENABLED do inventário)

- name: "Informar sobre configuração manual do VNC (se VNC Server foi instalado)"
  ansible.builtin.debug:
    msg: |
      Ambiente XFCE e TightVNCServer instalados na VM {{ inventory_hostname }}.
      Para usar o VNC (se não estiver usando GPU passthrough para display direto na VM):
      1. Conecte-se à VM via SSH: ssh {{ ansible_user }}@{{ inventory_hostname }}
      2. Execute 'vncserver :1' para iniciar o servidor VNC pela primeira vez. Isso solicitará a definição de uma senha VNC.
      3. Crie/Edite o arquivo ~/.vnc/xstartup na VM com o seguinte conteúdo:
         #!/bin/bash
         xrdb $HOME/.Xresources
         startxfce4 &
      4. Torne o arquivo xstartup executável: chmod +x ~/.vnc/xstartup
      5. Pare e reinicie o servidor VNC para aplicar o xstartup:
         vncserver -kill :1
         vncserver :1 -geometry 1280x800 -depth 24 # Ajuste resolução e profundidade de cor
      6. De um cliente VNC na sua máquina de controle, conecte-se a {{ inventory_hostname }}:1 (ou IP_DA_VM:5901).
      Se você estiver usando GPU passthrough com um monitor conectado à RX 5600XT na VM,
      você precisará instalar os drivers AMD apropriados DENTRO da VM ai-desktop-vm
      (ver Seção 7.1) para que a GUI utilize a GPU passada.
  when: install_gui_flag | default(false) | bool
```
Este role será chamado condicionalmente pelo playbook `ansible/playbooks/setup-base-ubuntu.yml` para as VMs que tiverem `GUI_ENABLED=true` no inventário.

Com as VMs provisionadas e o GPU passthrough (se aplicável) configurado no host, podemos prosseguir para a [Configuração Base das VMs Ubuntu](04-configuracao-base-vms-ubuntu.md).