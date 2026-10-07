# Passthrough de Hardware Adicional para VMs e Containers

Além do passthrough de GPU já abordado para a `ai-desktop-vm` ([Seção 3.4 do Manual de Implementação](../01-manual-implementacao/03-provisionamento-vms.md#34-configuração-de-gpu-passthrough-host-proxmox)), você pode encontrar cenários onde precisa passar outros tipos de dispositivos de hardware do seu host Proxmox VE diretamente para suas máquinas virtuais (VMs) ou, subsequentemente, para containers Docker rodando dentro dessas VMs.

Exemplos comuns incluem:
*   **Pendrives USB:** Para acesso a armazenamento externo, dongles de licença, etc.
*   **Dongles USB para Rádio Frequência:** Como sticks Zigbee (e.g., ConBee II, Sonoff), Z-Wave, ou Bluetooth para uso com Home Assistant.
*   **Placas de Rede PCI Adicionais:** Para VMs que atuam como firewalls (pfSense, OPNsense) ou que precisam de uma interface de rede dedicada.
*   **Controladoras HBA (Host Bus Adapter) ou RAID Cards em modo IT:** Para passar controle direto de discos para uma VM de NAS (e.g., TrueNAS).

!!! warning "Complexidade e Estabilidade"
    O passthrough de hardware, especialmente dispositivos PCI, pode adicionar complexidade à sua configuração e, em alguns casos, levar a instabilidade do host Proxmox ou da VM se não for feito corretamente. Sempre proceda com cautela, faça backups da configuração da sua VM antes de tentar passthrough de PCI, e pesquise especificamente sobre a compatibilidade do seu hardware. Dispositivos USB são geralmente mais simples e seguros de passar.

## Revisão: GPU Passthrough para VMs

A configuração de GPU passthrough é um processo específico e detalhado que envolve:
1.  Habilitação de **IOMMU** (AMD-Vi / Intel VT-d) e virtualização de CPU (AMD-V / Intel VT-x) na BIOS/UEFI do host Proxmox.
2.  Configuração do **kernel do Proxmox** (parâmetros no GRUB, carregamento de módulos `vfio`).
3.  **Blacklisting dos drivers da GPU** no host Proxmox para que `vfio-pci` possa assumir o controle.
4.  Identificação dos **IDs PCI** da GPU e de quaisquer dispositivos de áudio associados a ela.
5.  Adição dos dispositivos PCI à configuração da VM no Proxmox, geralmente com opções como `pcie=1`, `x-vga=1` (para a GPU principal da VM) e `romfile` (se necessário).

Para um passo a passo detalhado, consulte a [**Seção 3.4 do Manual de Implementação: Configuração de GPU Passthrough (Host Proxmox)**](../01-manual-implementacao/03-provisionamento-vms.md#34-configuração-de-gpu-passthrough-host-proxmox) e as configurações específicas no playbook `vm-deploy.yml` para a `ai-desktop-vm`.

## Passthrough de Dispositivos USB do Host Proxmox para VMs

Passar dispositivos USB para uma VM é consideravelmente mais simples do que o passthrough de dispositivos PCI.

**Passos para Passthrough de USB:**

1.  **Identifique o Dispositivo USB no Host Proxmox:**
    *   Conecte o dispositivo USB desejado a uma porta USB do seu servidor Proxmox.
    *   No shell do host Proxmox (como `root`), use o comando `lsusb` para listar todos os dispositivos USB conectados e seus IDs:
        ```bash
        root@pve:~# lsusb
        Bus 002 Device 003: ID 0781:5583 SanDisk Corp. Ultra Fit # Exemplo: Pendrive
        Bus 001 Device 005: ID 1a86:7523 QinHeng Electronics HL-340 USB-Serial adapter # Exemplo: Dongle Zigbee
        Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
        ...
        ```
    *   Anote o `VENDOR_ID:PRODUCT_ID` do dispositivo que você deseja passar (e.g., `1a86:7523` para o dongle Zigbee no exemplo acima).

2.  **Adicione o Dispositivo USB à Configuração da VM no Proxmox:**
    Você pode fazer isso de duas maneiras principais:

    *   **Opção A: Via Interface Web do Proxmox (Recomendado para Simplicidade):**
        1.  Na UI do Proxmox, selecione a máquina virtual de destino (e.g., `core-services-vm` se for um dongle para Home Assistant).
        2.  Vá para a aba "**Hardware**".
        3.  Clique no botão "**Add**" e selecione "**USB Device**".
        4.  No diálogo "Add USB Device", você tem duas opções principais:
            *   **Use USB Vendor/Device ID (Preferível para Consistência):** Selecione esta opção e, nos campos que aparecem, insira o `Vendor ID` e o `Product ID` que você anotou (e.g., Vendor ID: `1a86`, Product ID: `7523`). Isso garante que o mesmo dispositivo seja passado, mesmo que você o conecte a uma porta USB física diferente no host.
            *   **Use USB Port:** Esta opção lista os dispositivos USB atualmente conectados e permite selecioná-los pela porta física à qual estão conectados. É menos robusto, pois se você mover o dispositivo para outra porta USB no host, o passthrough pode quebrar.
        5.  **Use USB3:** Marque esta caixa se o dispositivo USB e a porta do host forem USB 3.0 e você quiser tentar usar o controlador xHCI para o passthrough (pode oferecer melhor performance para dispositivos USB 3.0).
        6.  Clique em "**Add**".

    *   **Opção B: Via Edição do Arquivo de Configuração da VM (Avançado):**
        1.  No shell do host Proxmox (como `root`), edite o arquivo de configuração da VM:
            `/etc/pve/qemu-server/VMID.conf` (substitua `VMID` pelo ID da sua VM, e.g., `100.conf` para a `core-services-vm`).
        2.  Adicione uma linha para o dispositivo USB. O número `usbX` (onde X é 0, 1, 2, etc.) deve ser único para os dispositivos USB passados para aquela VM.
            ```ini
            # Exemplo para passar o dispositivo com ID 1a86:7523
            usb0: host=1a86:7523

            # Exemplo para passar outro dispositivo USB 3.0
            # usb1: host=VENDOR_ID:PRODUCT_ID,usb3=1
            ```
        3.  Salve o arquivo.

3.  **Reinicie a VM (se já estiver rodando) ou Inicie-a:**
    Para que a VM reconheça o novo dispositivo USB que foi adicionado à sua configuração, ela geralmente precisa ser reiniciada ou iniciada após a alteração.

4.  **Verifique o Dispositivo Dentro da VM:**
    *   Conecte-se à VM de destino (e.g., `core-services-vm`) via SSH.
    *   Use `lsusb` dentro da VM. O dispositivo USB que você passou do host deve agora aparecer na lista de dispositivos USB da VM.
    *   **Para Dispositivos Seriais (como dongles Zigbee/Zwave):**
        Verifique se um novo dispositivo TTY (Teletypewriter) foi criado no diretório `/dev/` da VM. É através deste arquivo de dispositivo que as aplicações (como Home Assistant) interagirão com o dongle.
        ```bash
        # Dentro da VM
        ls /dev/tty*
        # Procure por algo como /dev/ttyUSB0, /dev/ttyUSB1, /dev/ttyACM0, etc.

        # Ver mensagens do kernel sobre o novo dispositivo (pode ajudar a identificar o nome)
        dmesg | grep tty
        dmesg | grep -i usb
        ```
        Anote o caminho do dispositivo (e.g., `/dev/ttyUSB0`).

**Exemplo Concreto: Dongle Zigbee para Home Assistant na `core-services-vm`:**
Se você passou um dongle Sonoff Zigbee 3.0 Dongle Plus (que usa o chip `10c4:ea60`) e ele aparece como `/dev/ttyUSB0` dentro da `core-services-vm`, você usará este caminho ao configurar a integração ZHA (Zigbee Home Automation) no Home Assistant.

## Passthrough de Outros Dispositivos PCI para VMs (Placas de Rede, HBAs)

O processo para passar outros tipos de dispositivos PCI (que não sejam GPUs) para uma VM é muito similar ao do GPU passthrough, mas geralmente sem a complexidade adicional de `x-vga=1` ou `romfile`.

1.  **Pré-requisitos do Host Proxmox:**
    *   IOMMU habilitado na BIOS/UEFI e no kernel GRUB (`amd_iommu=on iommu=pt`).
    *   Módulos `vfio` carregados.
2.  **Identifique o Dispositivo PCI e seu Grupo IOMMU:**
    *   No host Proxmox, use `lspci -nn` para encontrar o dispositivo e seus IDs `[VENDOR:DEVICE]`.
    *   Use o script de verificação de grupos IOMMU (da Seção 3.4) para garantir que o dispositivo está em um grupo IOMMU isolado ou em um grupo com outros dispositivos que você também deseja passar (ou que não se importa em perder para o host).
3.  **Blacklist Drivers no Host (se o host estiver usando o dispositivo):**
    Se o Proxmox host estiver usando o dispositivo PCI (e.g., uma placa de rede que você quer dedicar a uma VM firewall), você precisará impedir que o driver do host carregue para ele. Adicione os IDs do dispositivo a `/etc/modprobe.d/vfio-pci-blacklist.conf` (ou similar) com `options vfio-pci ids=VENDOR:DEVICE,...` e, possivelmente, blacklist o driver específico (e.g., `blacklist e1000e`). Atualize initramfs e reinicie o host.
4.  **Adicione o Dispositivo PCI à Configuração da VM:**
    *   **Via UI Proxmox:** Selecione a VM -> Hardware -> Add -> PCI Device.
        *   Selecione o dispositivo desejado da lista.
        *   Marque "**All Functions**" se o dispositivo tiver múltiplas funções e você quiser passar todas elas.
        *   **NÃO** marque "Primary GPU" ou "ROM-Bar" a menos que seja realmente uma GPU.
    *   **Via Ansible (`vm-deploy.yml`):** Adicione o ID PCI (sem o `0000:`) à lista `vm_host_pci_devices` para a VM, e.g., `vm_host_pci_devices: ["03:00.0"]`.
5.  **Instale Drivers na VM Convidada:** A VM precisará dos drivers apropriados para o dispositivo PCI que foi passado. Para placas de rede comuns ou HBAs, o kernel Linux da VM Ubuntu geralmente já os possui.

!!! danger "Cuidado ao Passar Dispositivos PCI Essenciais"
    Seja extremamente cuidadoso para não passar dispositivos PCI que são essenciais para o funcionamento do seu host Proxmox (como a placa de rede principal usada para gerenciamento, ou a controladora de disco onde o Proxmox OS está instalado), a menos que você saiba exatamente o que está fazendo e tenha um plano de contingência.

## Disponibilizando Dispositivos da VM para Containers Docker

Uma vez que um dispositivo (seja USB que apareceu como `/dev/ttyUSB0`, ou um dispositivo PCI que criou uma interface `/dev/algumacoisa` dentro da VM) está acessível *dentro* da máquina virtual, você pode mapeá-lo para um container Docker específico que precise dele.

Isso é feito na seção `devices` do seu arquivo `docker-compose.yml` para o serviço relevante.

**Exemplo: Mapeando um Dongle Zigbee (`/dev/ttyUSB0` na VM) para o container Home Assistant:**

No `docker/stacks/apps/docker-compose.yml` (para Home Assistant):
```yaml
services:
  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable # Ou sua tag específica
    # ... outras configurações como nome, restart, volumes, network, environment, labels ...
    devices:
      # Mapeia o dispositivo /dev/ttyUSB0 da VM para /dev/ttyUSB0 dentro do container.
      # O caminho DEVE corresponder ao que aparece DENTRO da VM.
      - "/dev/ttyUSB0:/dev/ttyUSB0"
      # Se o seu dispositivo apareceu como /dev/ttyACM0 na VM, use:
      # - "/dev/ttyACM0:/dev/ttyACM0"
    # ...
```

**Considerações de Permissão para Dispositivos Mapeados em Containers:**

*   O processo principal rodando dentro do container (e.g., o processo Home Assistant) precisa ter permissão para ler e escrever no arquivo de dispositivo mapeado (e.g., `/dev/ttyUSB0` dentro do container).
*   **Grupos de Sistema na VM:** Na VM Linux, dispositivos seriais como `/dev/ttyUSB0` ou `/dev/ttyACM0` geralmente pertencem a um grupo de sistema como `dialout` ou `tty`.
    *   Você pode precisar adicionar o usuário com o qual os containers Docker rodam (ou o PUID especificado para o container) ao grupo `dialout` **dentro da VM**. Se você usa o `dockeruser` (com PUID `{{ docker_puid }}`) para seus containers:
        ```bash
        # Execute DENTRO da VM (e.g., core-services-vm via SSH)
        sudo usermod -aG dialout {{ docker_user_name_on_vm }} # Usa o nome do usuário
        # Pode ser necessário um logout/login do usuário ou um reboot da VM para que
        # a nova associação de grupo tenha efeito para processos já existentes,
        # ou para o Docker daemon reconhecer a mudança para novos containers.
        ```
*   **Rodar Container como `root` ou `privileged: true` (Menos Seguro):**
    *   Se o container Docker roda como `root` internamente (o que algumas imagens fazem por padrão, embora não seja ideal), ele geralmente já terá as permissões necessárias para acessar o dispositivo mapeado.
    *   Definir `privileged: true` na seção do serviço no `docker-compose.yml` dá ao container acesso quase irrestrito ao kernel da VM e a todos os seus dispositivos. Isso geralmente resolve problemas de permissão de hardware, mas é uma **grande brecha de segurança** e deve ser **evitado sempre que possível**. Use-o apenas como último recurso e entenda os riscos. Para dispositivos TTY, o gerenciamento de grupo é geralmente suficiente.

Sempre teste cuidadosamente após configurar o passthrough de qualquer dispositivo, primeiro para a VM e depois para o container, para garantir que tanto o dispositivo quanto o restante do sistema e as aplicações funcionem como esperado.