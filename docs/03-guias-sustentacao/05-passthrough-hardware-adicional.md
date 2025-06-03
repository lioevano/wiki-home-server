# Passthrough de Hardware Adicional para VMs e Containers

Além do passthrough de GPU já abordado para a `ai-desktop-vm`, você pode precisar passar outros dispositivos de hardware (como pendrives USB, placas de rede adicionais, ou controladoras HBA) para suas máquinas virtuais ou, subsequentemente, para containers Docker dentro dessas VMs.

## Revisão: GPU Passthrough para VMs

A configuração de GPU passthrough é um processo complexo que envolve:
1.  Habilitação de IOMMU e virtualização de CPU na BIOS/UEFI do host Proxmox.
2.  Configuração do kernel do Proxmox (GRUB, `/etc/modules`).
3.  Blacklisting dos drivers da GPU no host Proxmox.
4.  Identificação dos IDs PCI da GPU e seus dispositivos de áudio associados.
5.  Adição dos dispositivos PCI à configuração da VM no Proxmox.

Para detalhes, consulte a [Seção 3.4 do Manual de Implementação](../01-manual-implementacao/03-provisionamento-vms.md#34-configuração-de-gpu-passthrough-host-proxmox) e as configurações específicas no playbook `vm-deploy.yml` para a `ai-desktop-vm`.

## Passthrough de Dispositivos USB do Host Proxmox para VMs

Passar dispositivos USB (como pendrives, dongles Zigbee/Zwave, adaptadores Bluetooth USB) para uma VM é geralmente mais simples que o passthrough de PCI.

**Passos:**

1.  **Identifique o Dispositivo USB no Host Proxmox:**
    *   Conecte o dispositivo USB ao servidor Proxmox.
    *   No shell do host Proxmox, use `lsusb` para listar os dispositivos USB conectados.
        ```bash
        root@proxmox:~# lsusb
        Bus 002 Device 003: ID 0781:5583 SanDisk Corp. Ultra Fit
        Bus 001 Device 004: ID 1a86:7523 QinHeng Electronics HL-340 USB-Serial adapter # Exemplo de dongle Zigbee
        ```
    *   Anote o `VENDOR_ID:PRODUCT_ID` do dispositivo que você quer passar (e.g., `1a86:7523`).

2.  **Adicione o Dispositivo USB à Configuração da VM no Proxmox:**
    Você pode fazer isso de duas maneiras:
    *   **Via Interface Web do Proxmox:**
        1.  Selecione a VM de destino (e.g., `core-services-vm` se for para Home Assistant).
        2.  Vá para a aba "Hardware".
        3.  Clique em "Add" -> "USB Device".
        4.  Você pode escolher "Use USB Vendor/Device ID" e inserir os IDs `VENDOR_ID:PRODUCT_ID` que você anotou.
        5.  Ou, se o dispositivo já estiver conectado e reconhecido, pode aparecer na lista "Use USB Port" (menos recomendado, pois a porta física pode mudar se você reconectar em outro lugar).
        6.  Marque "Use USB3" se o dispositivo e a porta forem USB 3.0 (opcional).
        7.  Clique em "Add".
    *   **Via Edição do Arquivo de Configuração da VM (Avançado):**
        1.  No shell do host Proxmox, edite o arquivo de configuração da VM:
            `/etc/pve/qemu-server/VMID.conf` (substitua `VMID` pelo ID da sua VM, e.g., `100.conf`).
        2.  Adicione uma linha como (o número `usbX` deve ser único para a VM):
            ```ini
            # Exemplo para passar o dispositivo com ID 1a86:7523
            usb0: host=1a86:7523
            # Se for um dispositivo USB3 e você quiser usar o controlador xhci:
            # usb1: host=VENDOR_ID:PRODUCT_ID,usb3=1
            ```
        3.  Salve o arquivo.

3.  **Reinicie a VM (se já estiver rodando) ou Inicie-a:**
    Para que a VM reconheça o novo dispositivo USB, ela geralmente precisa ser reiniciada ou iniciada após a adição do dispositivo à sua configuração.

4.  **Verifique o Dispositivo Dentro da VM:**
    *   Conecte-se à VM via SSH.
    *   Use `lsusb` dentro da VM. O dispositivo USB passado deve aparecer na lista.
    *   Para dispositivos seriais como dongles Zigbee/Zwave, verifique se um novo dispositivo TTY foi criado:
        ```bash
        ls /dev/tty*
        # Procure por algo como /dev/ttyUSB0, /dev/ttyACM0, etc.
        dmesg | grep tty # Pode mostrar mensagens do kernel sobre o dispositivo serial
        ```

**Exemplo: Dongle Zigbee para Home Assistant na `core-services-vm`:**
Assumindo que seu dongle Zigbee tem `ID 1a86:7523` e aparece como `/dev/ttyUSB0` dentro da `core-services-vm` após o passthrough.

## Passthrough de Outros Dispositivos PCI para VMs (Além de GPU)

O processo é similar ao de GPU passthrough, mas para outros tipos de dispositivos PCI (e.g., uma placa de rede dedicada para uma VM de firewall como pfSense/OPNsense, ou uma controladora HBA para uma VM de NAS como TrueNAS).

1.  **Verifique o Suporte IOMMU e Grupos:** Confirme que o dispositivo PCI está em um grupo IOMMU isolado no host Proxmox.
2.  **Blacklist Drivers no Host (se necessário):** Se o host Proxmox estiver usando o dispositivo, você pode precisar desvincular os drivers dele para que `vfio-pci` possa controlá-lo.
3.  **Adicione o Dispositivo PCI à Configuração da VM:**
    *   Na UI do Proxmox: VM -> Hardware -> Add -> PCI Device. Selecione o dispositivo da lista.
    *   Marque "All Functions" se o dispositivo tiver múltiplas funções que você quer passar.
    *   Marque "Primary GPU" e "ROM-Bar" apenas se for uma GPU e relevante.
    *   **Cuidado:** Não passe dispositivos essenciais para o funcionamento do host Proxmox (como a placa de rede principal do host, a menos que você saiba exatamente o que está fazendo).
4.  **Instale Drivers na VM:** A VM precisará dos drivers apropriados para o dispositivo PCI passado.

## Disponibilizando Dispositivos da VM para Containers Docker

Uma vez que um dispositivo (USB ou PCI) está acessível *dentro* da máquina virtual, você pode mapeá-lo para um container Docker específico que precise dele.

Isso é feito na seção `devices` do seu `docker-compose.yml` para o serviço relevante.

**Exemplo: Mapeando um Dongle Zigbee (`/dev/ttyUSB0` na VM) para o container Home Assistant:**
```yaml
# Trecho do docker-compose.yml do Home Assistant
services:
  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    # ... outras configurações ...
    devices:
      - "/dev/ttyUSB0:/dev/ttyUSB0" # Mapeia o dispositivo da VM para o mesmo caminho dentro do container
      # Se o dispositivo aparecer como /dev/ttyACM0 na VM:
      # - "/dev/ttyACM0:/dev/ttyACM0"
    # ... outras configurações ...
```

**Considerações de Permissão para Dispositivos em Containers:**

*   O processo rodando dentro do container (Home Assistant, neste caso) precisa de permissão para ler e escrever no dispositivo mapeado (e.g., `/dev/ttyUSB0` dentro do container).
*   **Grupo `dialout` (ou similar):** Na VM, dispositivos seriais como `/dev/ttyUSB0` geralmente pertencem a um grupo como `dialout`.
    *   Você pode precisar adicionar o usuário com o qual o Docker (ou o container específico) opera na VM a este grupo. Se os containers rodam com o PUID/PGID de `dockeruser`, então:
        ```bash
        # Na VM (e.g., core-services-vm)
        sudo usermod -aG dialout dockeruser # Ou o nome do seu usuário PUID
        ```
        Pode ser necessário reiniciar a VM ou o serviço Docker para que a nova associação de grupo tenha efeito.
*   **Rodar como `root` ou `privileged` (Menos Seguro):**
    *   Se o container rodar como `root` internamente (muitos fazem por padrão), ele geralmente terá permissão.
    *   Usar `privileged: true` no `docker-compose.yml` dá ao container acesso quase total ao kernel da VM e aos dispositivos, o que geralmente resolve problemas de permissão de hardware, mas é uma **grande brecha de segurança** e deve ser evitado se possível.

!!! warning "Complexidade e Estabilidade"
    O passthrough de hardware, especialmente PCI, pode ser complexo e, em alguns casos, levar a instabilidade do host ou da VM se não for feito corretamente. Sempre faça backup da configuração da sua VM antes de tentar passthrough de PCI. Dispositivos USB são geralmente mais simples e seguros de passar.

Sempre teste cuidadosamente após configurar o passthrough de qualquer dispositivo para garantir que tanto o dispositivo quanto o restante do sistema funcionem como esperado.
