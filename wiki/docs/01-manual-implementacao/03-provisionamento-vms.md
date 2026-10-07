# Seção 3: Provisionamento das Máquinas Virtuais (VMs) com Ansible

Com o host Proxmox VE devidamente configurado ([Seção 2](02-proxmox-ve-host.md)), o próximo passo é provisionar as máquinas virtuais (VMs) que hospedarão seus serviços containerizados. Utilizaremos o Ansible para automatizar a criação e configuração inicial dessas VMs a partir de um template Ubuntu Server Cloud-Init, garantindo consistência e repetibilidade.

Nesta arquitetura, com 48GB de RAM disponíveis no host, temos flexibilidade para alocar recursos de forma mais confortável para nossas VMs principais:

* **`core-services-vm`:** Esta VM será o cavalo de batalha, hospedando a maioria dos seus serviços Docker, incluindo Traefik, Portainer, Authelia, Nextcloud, a stack de mídia, a stack de monitoramento, e outros serviços essenciais.
* **`ai-desktop-vm`:** Esta VM é opcional, mas planejada para tarefas de Inteligência Artificial (LLMs com Ollama, aplicações RAG) que podem se beneficiar de um ambiente isolado e, crucialmente, do passthrough da GPU AMD RX 5600XT para aceleração de hardware.

## 3.1. Criação de Template de VM Base (Ubuntu Server Cloud-Init)

Um template de VM no Proxmox permite que você clone rapidamente novas VMs já com uma configuração base (como o sistema operacional e alguns pacotes essenciais). Usaremos uma imagem Cloud-Init do Ubuntu Server, que é projetada para ser configurada dinamicamente no primeiro boot.

Siga estes passos na **interface web do Proxmox VE** ou, para os comandos de download e importação, no **shell do host Proxmox VE** (como `root`):

1. **Download da Imagem Cloud-Init do Ubuntu Server:**
    No shell do host Proxmox:

    ```bash
    # Versão Ubuntu 24.04 LTS (Noble Numbat)
    IMAGE_URL="https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
    IMAGE_FILENAME="noble-server-cloudimg-amd64.img"

    # O storage 'local' no Proxmox para ISOs/Templates 
    DOWNLOAD_DEST_DIR="/var/lib/vz/template/iso"

    # Cria o diretório se não existir
    mkdir -p "${DOWNLOAD_DEST_DIR}"

    echo "Baixando imagem Cloud-Init (Ubuntu 24.04) para ${DOWNLOAD_DEST_DIR}..."
    wget -O "${DOWNLOAD_DEST_DIR}/${IMAGE_FILENAME}" "${IMAGE_URL}"

    if [ $? -eq 0 ]; then
      echo "Download da imagem ${IMAGE_FILENAME} concluído com sucesso."
    else
      echo "ERRO: Falha ao baixar a imagem. Verifique a URL e a conexão."
      exit 1
    fi
    ```

2. **Crie uma Nova VM Base para o Template (via UI Proxmox):**
    * Na interface web do Proxmox, clique no botão azul "**Create VM**" no canto superior direito.
    * **Aba General:**
        * **Node:** Selecione seu nó Proxmox (e.g., `pve`).
        * **VM ID:** Escolha um ID numérico único que esteja fora da sua faixa usual de VMs de produção. IDs altos como `9000`, `9001`, etc., são comumente usados para templates. Exemplo: `9000`.
        * **Name:** Dê um nome descritivo, e.g., `ubuntu-2204-cloudinit-base`.
    * **Aba OS:**
        * Selecione a opção **"Do not use any media"**.
        * **Guest OS Type:** `Linux`.
        * **Version:** Escolha a mais apropriada (e.g., `5.x - 2.6 Kernel` ou a mais recente listada).
    * **Aba System:**
        * **Graphic card:** `Default`.
        * **Machine:** `q35` (geralmente o padrão e recomendado por ser mais moderno).
        * **BIOS:** `OVMF (UEFI)` (recomendado para sistemas modernos).
        * **EFI Storage:** Selecione o storage onde o disco EFI da VM será armazenado (e.g., `local-lvm`, que é o seu SSD NVMe).
        * **Add TPM:** Opcional, mas pode ser útil para futuras features de segurança. Se adicionar, escolha `v2.0`.
    * **Aba Hard Disk:**
        * **Ignore/Delete:** Não configure um disco aqui ainda. Nós vamos importar o disco da imagem qcow2. Se um disco for adicionado por padrão, você pode selecioná-lo e clicar em "Detach" e depois "Remove".
    * **Aba CPU:**
        * **Cores:** `1` (um core é suficiente para o template base).
    * **Aba Memory:**
        * **Memory (MiB):** `2048` (2GB é suficiente para o template e instalação do guest agent).
    * **Aba Network:**
        * **Bridge:** Selecione sua bridge de rede padrão (e.g., `vmbr0`).
        * **Model:** `VirtIO (paravirtualized)` (para melhor performance).
    * **Aba Confirm:** Revise as configurações e clique em "Finish". **Não marque "Start after created".**

3. **Importe o Disco da Imagem Cloud-Init para a VM Base:**
    No shell do host Proxmox (como `root`):

    ```bash
    # Substitua 9000 pelo VM ID real da sua VM base.
    # Substitua 'local-lvm' pelo nome do seu storage de destino para discos de VM
    # (conforme proxmox_storage_vm_disks em main.yml).
    VMID_TEMPLATE=9000 # O ID da VM que você criou no passo anterior
    STORAGE_VM_DISKS="local-lvm" # Onde os discos das VMs são armazenados
    IMAGE_QCOW2_PATH="${DOWNLOAD_DEST_DIR}/${IMAGE_FILENAME}" # Caminho completo para a imagem baixada

    echo "Importando disco ${IMAGE_QCOW2_PATH} para VM ${VMID_TEMPLATE} no storage ${STORAGE_VM_DISKS}..."
    qm importdisk ${VMID_TEMPLATE} "${IMAGE_QCOW2_PATH}" ${STORAGE_VM_DISKS}
    ```

    Se bem-sucedido, você verá uma mensagem como "Successfully imported disk as 'unused0:local-lvm:vm-9000-disk-0'".

4. **Anexe o Disco Importado à VM Base (via UI Proxmox):**
    * Na UI do Proxmox, selecione a VM base que você criou (e.g., VM 9000).
    * Vá para a aba "**Hardware**".
    * Você verá um item listado como "**Unused Disk 0**" (ou similar). Selecione este disco.
    * Clique no botão "**Edit**".
    * No diálogo "Edit Unused Disk":
        * **Bus/Device:** Escolha `SCSI` (VirtIO SCSI é geralmente uma boa escolha para performance).
        * **SSD emulation:** Marque esta caixa se o seu storage (`local-lvm` neste caso) estiver em um SSD, o que pode melhorar a forma como o SO convidado interage com o disco.
    * Clique em "**Add**". O disco agora deve aparecer como `Hard Disk (scsi0)`.

5. **Configure a Ordem de Boot (via UI Proxmox):**
    * Na aba "**Options**" da VM template, selecione "**Boot Order**".
    * No diálogo "Edit Boot Order":
        * Habilite (marque a caixa) o disco que você acabou de adicionar (e.g., `scsi0`).
        * Arraste-o para o topo da lista para ser o primeiro dispositivo de boot.
        * Você pode desabilitar outras opções de boot como CD-ROM ou Rede se não forem necessárias para o template.
    * Clique em "OK".

6. **Adicione um Drive Cloud-Init (via UI Proxmox):**
    Este drive é essencial para que o Ansible possa passar configurações (usuário, senha, chave SSH, rede) para as VMs clonadas a partir deste template.
    * Na aba "**Hardware**", clique em "**Add**" -> "**CloudInit Drive**".
    * **Storage:** Selecione o mesmo storage onde o disco principal da VM está (e.g., `local-lvm`).
    * Clique em "**Add**".

7. **(Opcional, mas Altamente Recomendado) Instalar `qemu-guest-agent` no Template:**
    O `qemu-guest-agent` melhora significativamente a interação entre o host Proxmox e a VM (e.g., para obter o IP da VM de forma confiável, desligamento/reinício "gracioso", consistência de snapshots).
    * **Inicie a VM template (e.g., VM 9000):** Na UI do Proxmox, selecione a VM e clique em "Start". Abra o ">_ Console".
    * A imagem cloud-init do Ubuntu Server deve bootar. Pode levar um momento para a configuração inicial do Cloud-Init. Eventualmente, você chegará a um login prompt ou um shell.
        * O usuário padrão para imagens cloud Ubuntu é geralmente `ubuntu`. A senha pode estar desabilitada (login direto) ou ser `ubuntu`. Se pedir senha e `ubuntu` não funcionar, pode ser necessário configurar uma senha via Cloud-Init (mas para o template, o acesso ao console deve ser suficiente).
    * **Dentro da VM template, execute os seguintes comandos:**

        ```bash
        sudo apt update
        sudo apt install -y qemu-guest-agent
        sudo systemctl enable qemu-guest-agent # Habilita para iniciar no boot
        sudo systemctl start qemu-guest-agent  # Inicia o serviço imediatamente
        ```

    * **Limpeza (Opcional, para reduzir o tamanho do template e generalizá-lo):**

        ```bash
        sudo apt-get clean              # Limpa o cache do apt
        sudo rm -rf /tmp/* /var/tmp/*   # Remove arquivos temporários
        sudo cloud-init clean --logs --seed # Limpa dados de instância do Cloud-Init
        # Opcional: Remover chaves SSH do host (serão geradas unicamente em cada clone)
        # sudo rm -f /etc/ssh/ssh_host_*
        # Limpar o histórico do bash do usuário atual
        # history -c && history -w
        ```

    * **Desligue a VM template:**

        ```bash
        sudo shutdown now
        ```

8. **Converta a VM Base para um Template (via UI Proxmox):**
    * Aguarde a VM desligar completamente.
    * Na UI do Proxmox, clique com o botão direito do mouse na VM base (e.g., VM 9000).
    * Selecione a opção "**Convert to template**".
    * !!! important "Nome do Template no Proxmox"
        O template agora aparecerá na sua lista de VMs com um ícone diferente. O **nome** deste template no Proxmox deve corresponder **exatamente** ao valor da variável `proxmox_ubuntu_template_name` que você definiu no seu arquivo `ansible/inventories/home/group_vars/all/main.yml` (e.g., `ubuntu-2204-cloudinit-template-v1`). O Ansible usará este nome para clonar as VMs.

## 3.2. Role Ansible `proxmox-vm` (`ansible/roles/infra/proxmox-vm/`)

Este role Ansible é o coração da automação do provisionamento de VMs. Ele é responsável por:
* Clonar novas VMs a partir do template que acabamos de criar.
* Configurar os recursos da VM (vCPUs, RAM).
* Redimensionar o disco principal da VM.
* Passar configurações via Cloud-Init para a VM, incluindo:
    * Nome de usuário e senha.
    * Chave SSH pública para acesso Ansible.
    * Configuração de rede estática (IP, gateway, DNS).
* Configurar o passthrough de dispositivos PCI (como a GPU), se especificado.

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

Este playbook utiliza o role `proxmox-vm` para criar e configurar as VMs `core-services-vm` e `ai-desktop-vm` com suas especificações de recursos.

Certifique-se de que o arquivo `ansible/playbooks/vm-deploy.yml` exista com o seguinte conteúdo, **ajustando os IDs PCI para sua GPU RX 5600XT se for usar o passthrough para `ai-desktop-vm`**:

```yaml
# ansible/playbooks/vm-deploy.yml
- hosts: proxmox_main_host # O playbook é executado *contra* o host Proxmox
                          # pois as tasks do role proxmox-vm são delegadas (delegate_to: localhost)
                          # e interagem com a API Proxmox a partir da máquina de controle.
                          # O alvo aqui é para o Ansible saber com qual host Proxmox falar.
  gather_facts: no # Não precisamos de fatos do Proxmox host para estas tasks
  vars_files:
    - ../inventories/home/group_vars/all/vault.yml # Carrega segredos
  # Variáveis de group_vars/all/main.yml e hosts.ini são carregadas automaticamente

  tasks:
    - name: "Deploy VM: core-services-vm"
      ansible.builtin.include_role:
        name: infra/proxmox-vm
      vars:
        vm_id: 100 # ID único para esta VM
        vm_name: "core-services-vm" # DEVE corresponder ao nome no seu hosts.ini
        vm_cores: 6 # Com 48GB RAM no host, podemos ser mais generosos.
        vm_memory: 16384 # 16GB RAM para a VM de serviços principais
        vm_disk_gb: 100 # Aumentado para 100GB
        # IP estático para a VM, usando o IP definido no inventário (hosts.ini)
        vm_ipconfig: "ip={{ hostvars['core-services-vm']['ansible_host'] }}/24,gw={{ vm_cloud_init_gateway }}"
        vm_tags: "docker,core_services,homelab,ansible_managed"

    - name: "Deploy VM: ai-desktop-vm (Opcional, para LLM/RAG com GPU)"
      ansible.builtin.include_role:
        name: infra/proxmox-vm
      vars:
        vm_id: 101 # ID único
        vm_name: "ai-desktop-vm" # DEVE corresponder ao nome no hosts.ini
        vm_cores: 4 # Pode ser aumentado para 6 ou 8 se necessário e o host permitir
        vm_memory: 16384 # 16GB RAM, pode ser aumentada. Ex: 24576 (24GB)
        vm_disk_gb: 200 # Aumentado para modelos LLM maiores e SO
        vm_ipconfig: "ip={{ hostvars['ai-desktop-vm']['ansible_host'] }}/24,gw={{ vm_cloud_init_gateway }}"
        vm_tags: "llm,rag,ai_gpu,desktop,homelab,ansible_managed"

        # --- Configurações para GPU Passthrough (Exemplo para RX 5600XT) ---
        # !!! IMPORTANTE: Substitua pelos IDs PCI REAIS da sua GPU no host Proxmox !!!
        # Use 'lspci -nn' no shell do Proxmox host para encontrar os IDs [vendor:device] corretos.
        # Remova o prefixo "0000:" dos IDs.
        # Exemplo: Se lspci -nn mostra:
        # 09:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Navi 10 [Radeon RX 5600 OEM/5600 XT / 5700/5700 XT] [1002:731f] (rev c4)
        # 09:00.1 Audio device [0403]: Advanced Micro Devices, Inc. [AMD/ATI] Navi 10/10M/12/14 HDMI Audio Device [1002:ab28]
        # Os IDs PCI para o array abaixo seriam "09:00.0" e "09:00.1".
        vm_vga_type: "none" # Necessário para GPU passthrough ser a placa gráfica principal da VM
        vm_host_pci_devices: # Lista de dispositivos PCI a serem passados
          - "SEU_ID_PCI_GPU_VIDEO,pcie=1,x-vga=1"  # Ex: "09:00.0,pcie=1,x-vga=1"
          - "SEU_ID_PCI_GPU_AUDIO,pcie=1"         # Ex: "09:00.1,pcie=1"
        # Opcional: Se precisar de um arquivo ROM para a GPU (mais comum para NVIDIA, raro para AMD recentes)
        # vm_qemu_args: "-device vfio-pci,host=09:00.0,romfile=amd_rx5600xt.rom"
        # Argumentos para tentar "esconder" que é uma VM, pode ser necessário para drivers NVIDIA (menos para AMD)
        # vm_qemu_args: "-cpu host,kvm=off,hv_vendor_id=NvidiaFuckU" # Exemplo extremo, use com cautela e pesquisa
      when: "'ai-desktop-vm' in groups['virtual_machines']" # Só executa se a VM estiver definida no inventário

    # Aguardar que as VMs estejam prontas e atualizar o inventário Ansible em memória
    - name: "Aguardar todas as VMs Ubuntu recém-criadas/configuradas estarem acessíveis via SSH"
      ansible.builtin.wait_for:
        host: "{{ hostvars[item]['ansible_host'] }}" # IP da VM do inventário
        port: 22 # Porta SSH
        delay: 60  # Segundos de espera inicial antes do primeiro check (Cloud-Init pode demorar)
        timeout: 360 # Tempo máximo de espera em segundos (6 minutos)
        state: started # Espera até que a porta esteja aberta e respondendo
        msg: "Aguardando SSH na VM {{ item }} ({{ hostvars[item]['ansible_host'] }})"
      # loop: "{{ groups['ubuntu_vms'] }}" # Itera sobre todas as VMs no grupo 'ubuntu_vms'
      # Usar query é mais robusto se o grupo puder estar vazio ou hosts não definidos:
      loop: "{{ query('inventory_hostnames', 'ubuntu_vms') }}"
      delegate_to: localhost # A tarefa wait_for roda na máquina de controle Ansible, testando a conexão com as VMs

    - name: "Atualizar inventário Ansible em memória para refletir novas VMs"
      ansible.builtin.meta: refresh_inventory # Garante que Ansible conheça os novos hosts para tasks subsequentes
```

!!! warning "Ajuste de Recursos e IDs PCI"
    *   **Alocação de RAM:** Com 48GB no host, as alocações de 16GB para `core-services-vm` e 16GB (ou mais) para `ai-desktop-vm` são viáveis, deixando uma boa margem para o host Proxmox (16GB). Monitore o uso de RAM e ajuste conforme necessário.
    *   **IDs PCI para GPU Passthrough:** É **crucial** que você use o comando `lspci -nn` no shell do seu host Proxmox para encontrar os IDs corretos da sua placa de vídeo RX 5600XT (tanto a parte de vídeo quanto a de áudio associada) e substitua os placeholders `SEU_ID_PCI_GPU_VIDEO` e `SEU_ID_PCI_GPU_AUDIO` no playbook `vm-deploy.yml`. Um ID incorreto fará com que o passthrough falhe ou a VM não inicie.

### Executando o Playbook de Deploy das VMs

1. Na sua máquina de controle Ansible, navegue até a raiz do projeto `home-server/`.
2. Execute o playbook:

    ```bash
    ansible-playbook ansible/playbooks/vm-deploy.yml --ask-vault-pass
    ```

Após a execução, suas VMs (`core-services-vm` e `ai-desktop-vm`, se habilitada) devem estar criadas no Proxmox, configuradas com os parâmetros básicos de Cloud-Init e, se tudo correu bem com o `wait_for`, prontas para as próximas etapas de configuração.

## 3.4. Configuração de GPU Passthrough (Host Proxmox) - Revisão

Se você planeja usar a `ai-desktop-vm` com a RX 5600XT para aceleração de IA ou outras tarefas gráficas, a configuração de GPU passthrough no **host Proxmox** é um pré-requisito. Este é um processo avançado e os detalhes podem variar ligeiramente dependendo do seu hardware específico e versão do Proxmox.

**Resumo das Etapas Essenciais no Host Proxmox (Como Checklist de Verificação):**

1. **BIOS/UEFI do Servidor (Já Coberto na Seção 2.1):**
    * Virtualização de CPU (AMD-V / SVM Mode) **HABILITADA**.
    * IOMMU (AMD-Vi) **HABILITADO**.

2. **Configuração do Kernel Proxmox (GRUB e Módulos):**
    * **Edite `/etc/default/grub`** no host Proxmox. A linha `GRUB_CMDLINE_LINUX_DEFAULT` deve incluir:

        ```
        GRUB_CMDLINE_LINUX_DEFAULT="quiet amd_iommu=on iommu=pt video=efifb:off"
        ```

        * `amd_iommu=on`: Habilita IOMMU para AMD.
        * `iommu=pt`: (Passthrough mode) Para melhor performance com passthrough.
        * `video=efifb:off`: Tenta desabilitar o framebuffer EFI para a GPU que será passada, o que pode ajudar a desvinculá-la do host. Se você tem uma iGPU para o console do Proxmox, isso é geralmente seguro.
    * Após editar, execute: `sudo update-grub`.
    * **Adicione os seguintes módulos a `/etc/modules`** (um por linha) para garantir que sejam carregados no boot:

        ```
        vfio
        vfio_iommu_type1
        vfio_pci
        vfio_virqfd
        ```

    * Atualize o initramfs: `sudo update-initramfs -u -k all`.

3. **Blacklist dos Drivers da GPU no Host Proxmox:**
    Para que o `vfio-pci` possa assumir o controle da GPU para passthrough, os drivers do host (como `amdgpu` ou `radeon`) não devem carregá-la. Crie (ou edite) o arquivo `/etc/modprobe.d/vfio-pci-blacklist.conf` (o nome pode variar) no host Proxmox com o seguinte conteúdo, **substituindo os VENDOR_ID e DEVICE_ID pelos da sua RX 5600XT** (obtidos com `lspci -nn`):

    ```conf
    # Blacklist drivers AMD para a GPU dedicada ao passthrough
    blacklist amdgpu
    blacklist radeon

    # Carrega vfio-pci para os IDs específicos da sua RX 5600XT
    # Exemplo para RX 5600XT (vídeo: 1002:731f, áudio: 1002:ab28)
    # Use os IDs que você identificou para sua placa!
    options vfio-pci ids=1002:731f,1002:ab28 disable_vga=1
    ```

    * `disable_vga=1` pode ser útil para algumas GPUs para desabilitar completamente a saída VGA legada na GPU passada.

4. **Reinicie o Host Proxmox.** Esta etapa é crucial para que todas as mudanças no kernel e módulos tenham efeito.

5. **Verifique a Configuração IOMMU e Grupos:**
    Após o reboot, no shell do host Proxmox:
    * Verifique se o IOMMU está ativo: `dmesg | grep -e DMAR -e IOMMU` (deve mostrar IOMMU habilitado).
    * **Verifique os Grupos IOMMU:** Este é um passo crítico. Sua GPU RX 5600XT (tanto o dispositivo de vídeo quanto o de áudio associado) deve estar em um ou mais grupos IOMMU que, idealmente, **não contenham outros dispositivos essenciais do sistema** (como a placa de rede do host, controladoras USB principais, etc.).
        Para listar os grupos IOMMU e os dispositivos neles:

        ```bash
        find /sys/kernel/iommu_groups/ -type l
        # Ou um script mais detalhado para ver os dispositivos em cada grupo:
        for d in /sys/kernel/iommu_groups/*/devices/*; do \
          n=${d#*/iommu_groups/*}; n=${n%%/*}; \
          printf 'IOMMU Group %s ' "$n"; \
          lspci -nns "${d##*/}"; \
        done | sort -V
        ```

        Procure pelos dispositivos da sua RX 5600XT. Se eles estiverem em um grupo isolado ou com dispositivos não críticos, ótimo. Se estiverem agrupados com, por exemplo, a sua única placa de rede ou a controladora USB do teclado/mouse do host, o passthrough pode ser problemático ou requerer o patch ACS (Advanced Configuration and Power Interface Override), que é uma técnica avançada e com implicações de segurança.

A configuração de GPU passthrough é uma das partes mais complexas e propensas a variações dependendo do hardware. Consulte guias detalhados online específicos para "Proxmox AMD GPU passthrough" se encontrar dificuldades.

## 3.5. Configuração de Ambiente Desktop (GUI) em VMs Linux (Opcional)

Para a `ai-desktop-vm`, se você deseja uma interface gráfica para interagir com ela (especialmente se estiver usando GPU passthrough e conectar um monitor diretamente à RX 5600XT), você pode instalar um ambiente desktop. Se o acesso for apenas via SSH e para rodar serviços como Ollama, uma GUI não é estritamente necessária.

### Role: `ansible/roles/apps/desktop-environment/`

Este role Ansible instala XFCE (um ambiente desktop leve) e TightVNCServer (para acesso remoto à GUI se não usar GPU passthrough direto com um monitor conectado à VM).

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

O playbook `ansible/playbooks/setup-base-ubuntu.yml` (Seção 4) chamará este role condicionalmente para as VMs que tiverem a variável `GUI_ENABLED=true` definida no seu inventário (`ansible/inventories/home/hosts.ini`).

Com as VMs provisionadas e o GPU passthrough (se aplicável) configurado no host Proxmox, estamos prontos para avançar para a [Configuração Base das VMs Ubuntu](04-configuracao-base-vms-ubuntu.md), onde instalaremos Docker, Portainer e outros utilitários essenciais.