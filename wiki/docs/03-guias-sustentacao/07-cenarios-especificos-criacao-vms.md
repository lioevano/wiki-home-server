# Cenários Específicos de Criação de Máquinas Virtuais (VMs)

Embora nossa arquitetura principal se concentre na `core-services-vm` (para a maioria dos serviços Docker) e na `ai-desktop-vm` (para tarefas de IA com GPU passthrough), podem surgir cenários onde você precise ou deseje criar máquinas virtuais com propósitos mais específicos e isolados. Este guia explora alguns desses cenários comuns e as considerações para implementá-los no seu ambiente Proxmox VE.

Lembre-se sempre da capacidade total do seu host Proxmox, especialmente a RAM (atualmente 48GB em nosso exemplo, o que oferece boa flexibilidade), ao planejar novas VMs. Cada VM consumirá recursos que poderiam ser usados por outras.

## 1. VM para Firewall/Roteador de Borda (e.g., pfSense, OPNsense)

Rodar seu próprio firewall/roteador em uma VM no Proxmox é um projeto popular em homelabs. Ele pode oferecer funcionalidades muito mais avançadas e controle granular sobre sua rede do que a maioria dos roteadores de consumidor.

*   **Propósito:**
    *   Substituir ou complementar seu roteador físico fornecido pelo ISP.
    *   Implementar um firewall stateful robusto.
    *   Configurar um servidor VPN (e.g., OpenVPN, WireGuard) para acesso seguro à sua rede local de fora.
    *   Implementar um cliente VPN para rotear todo o tráfego da sua LAN (ou de VMs específicas) através de um provedor VPN.
    *   Utilizar Sistemas de Detecção/Prevenção de Intrusão (IDS/IPS) como Suricata ou Snort.
    *   Realizar modelagem de tráfego (QoS), port forwarding avançado, DNS seguro, etc.
*   **Softwares Populares:**
    *   **pfSense:** Baseado em FreeBSD, muito maduro, robusto e com uma grande comunidade.
    *   **OPNsense:** Um fork do pfSense, também baseado em FreeBSD, com foco em segurança e uma interface de usuário moderna.
*   **Requisitos e Considerações Chave:**
    *   **Múltiplas Interfaces de Rede Físicas no Host Proxmox:** Essencial. Você precisará de pelo menos **duas** placas de rede físicas no seu servidor Proxmox:
        1.  Uma para a interface **WAN** da sua VM firewall (que se conectará ao seu modem/ONT da internet).
        2.  Uma para a interface **LAN** da sua VM firewall (que se conectará ao seu switch de rede local, servindo seus dispositivos e outras VMs).
    *   **Bridges Proxmox Dedicadas:**
        *   No Proxmox (em Datacenter -> Seu Nó -> System -> Network), crie duas bridges Linux separadas. Por exemplo:
            *   `vmbr0` (já existente): Mantenha-a para sua rede LAN principal e para o gerenciamento do Proxmox.
            *   `vmbr1` (nova): Crie esta bridge e **não** atribua um endereço IP ou gateway a ela no host Proxmox. Associe a segunda placa de rede física (a que será sua WAN) a esta bridge `vmbr1`.
        *   A VM do firewall terá duas interfaces de rede virtuais: uma conectada a `vmbr0` (para sua LAN) e outra a `vmbr1` (para sua WAN).
    *   **Passthrough de Placa de Rede PCI (Opcional, Avançado):**
        Para performance máxima ou se precisar de funcionalidades específicas da placa de rede que não são bem suportadas pelo modelo VirtIO, você pode passar uma (ou ambas) as placas de rede físicas diretamente para a VM do firewall usando o passthrough PCI. Isso requer configuração cuidadosa de IOMMU e blacklisting de drivers no host.
    *   **Recursos da VM Firewall:** Geralmente não são extremamente exigentes para um homelab, a menos que você rode IDS/IPS com muitas regras ou tenha um tráfego de internet muito alto com muitas conexões.
        *   **CPU:** 1-2 vCPUs são frequentemente suficientes.
        *   **RAM:** 1-4GB RAM. pfSense/OPNsense são baseados em FreeBSD e são eficientes.
        *   **Disco:** 20-40GB são geralmente mais que suficientes.
    *   **Ordem de Boot e Dependências Críticas:**
        *   Se esta VM firewall se tornar seu gateway principal para a internet, o host Proxmox e todas as outras VMs dependerão dela para acesso à rede externa após o boot.
        *   Configure a **ordem de início das VMs** no Proxmox (Opções da VM -> Startup/Shutdown Order) para garantir que a VM firewall inicie primeiro.
        *   Considere como você acessará a UI do Proxmox ou outras VMs se a VM firewall falhar ao iniciar. Ter um plano de acesso de contingência (e.g., um laptop conectado diretamente ao mesmo switch da LAN, com um IP estático) é uma boa ideia.
    *   **Alta Disponibilidade (HA - Muito Avançado para Homelab Típico):**
        Para evitar um ponto único de falha, setups de firewall em ambientes críticos usam protocolos como CARP (Common Address Redundancy Protocol) ou VRRP com duas VMs de firewall idênticas, geralmente em um cluster Proxmox com hosts separados. Isso está fora do escopo da maioria dos homelabs.
    *   **Segurança da VM Firewall:** Como esta VM estará diretamente exposta à internet (na interface WAN), é crucial mantê-la **sempre atualizada** com os últimos patches de segurança e configurar suas regras de firewall de forma muito restritiva (permitir apenas o necessário).
*   **Criação da VM Firewall:**
    1.  **Download da ISO:** Baixe a imagem ISO de instalação do pfSense ou OPNsense do site oficial deles. Faça upload para o storage `local (pve)` no seu Proxmox.
    2.  **Criação da VM no Proxmox (via UI ou Ansible):**
        *   Se via UI: Crie uma nova VM. Na aba "Network", adicione **duas** interfaces de rede VirtIO, uma conectada à sua bridge LAN (e.g., `vmbr0`) e outra à sua bridge WAN (e.g., `vmbr1`).
        *   Se via Ansible (modificando `vm-deploy.yml`):
            ```yaml
            # Exemplo de adição ao vm-deploy.yml para uma VM pfSense
            - name: "Deploy VM: pfsense-firewall-vm"
              ansible.builtin.include_role:
                name: infra/proxmox-vm
              vars:
                vm_id: 10 # Exemplo de ID
                vm_name: "pfsense-firewall-vm"
                vm_cores: 2
                vm_memory: 2048 # 2GB RAM
                vm_disk_gb: 30
                vm_os_type: "other" # Ou o tipo FreeBSD se disponível
                vm_iso_file: "local:iso/pfSense-CE-X.Y.Z-RELEASE-amd64.iso" # Nome do arquivo ISO no storage 'local'
                # Definir múltiplas interfaces de rede
                vm_network_interfaces: # Lista de interfaces
                  - { model: "virtio", bridge: "vmbr0", tag: "10" } # Exemplo: LAN na VLAN 10
                  - { model: "virtio", bridge: "vmbr1" }          # Exemplo: WAN (sem tag VLAN)
                # Cloud-Init não se aplica a pfSense/OPNsense da mesma forma que Ubuntu
                # vm_ipconfig: "manual" # A configuração de IP será feita dentro do pfSense
                vm_tags: "firewall,router,pfsense,homelab"
            ```
            (Note: O role `proxmox-vm` precisaria ser adaptado para lidar com `vm_iso_file` e `vm_network_interfaces` se não já o fizer. A configuração de rede via `vm_ipconfig` para Cloud-Init não se aplicaria a pfSense/OPNsense; a configuração de interfaces WAN/LAN é feita dentro do instalador/UI deles.)
    3.  **Instalação e Configuração Interna:**
        *   Inicie a VM a partir da ISO.
        *   Siga o assistente de instalação do pfSense/OPNsense. Durante o processo, ele pedirá para você atribuir as interfaces de rede virtuais (e.g., `vtnet0`, `vtnet1`) às funções WAN e LAN.
        *   Após a instalação, acesse a interface web do pfSense/OPNsense a partir de um computador na sua rede LAN e configure suas regras de firewall, DHCP server para a LAN, DNS, etc.

## 2. VM para Desenvolvimento ou Testes Isolados e Descartáveis

Precisa testar um novo software, uma configuração arriscada, compilar algo de fonte desconhecida, ou criar um ambiente de desenvolvimento específico sem poluir suas VMs principais ou sua máquina de trabalho? Uma VM de teste, possivelmente descartável, é a solução ideal.

*   **Propósito:** Ambientes isolados, temporários, ou para experimentação segura.
*   **Criação Rápida e Fácil:**
    1.  **Clonar do Template Ubuntu Cloud-Init:** Esta é a maneira mais rápida.
        *   **Via UI do Proxmox:** Clique com o botão direito no seu template `ubuntu-2204-cloudinit-base` -> "Clone". Dê um novo VM ID e nome (e.g., `test-vm-01`), escolha "Full Clone".
        *   **Via Ansible (`vm-deploy.yml`):** Adicione uma nova entrada ao seu playbook `vm-deploy.yml` para a VM de teste. Isso é bom se você precisa recriá-la consistentemente.
            ```yaml
            # Exemplo de adição ao vm-deploy.yml
            - name: "Deploy VM: test-environment-vm"
              ansible.builtin.include_role:
                name: infra/proxmox-vm
              vars:
                vm_id: 200 # Escolha um ID não utilizado
                vm_name: "test-environment-vm"
                vm_cores: 2
                vm_memory: 4096 # 4GB RAM para testes
                vm_disk_gb: 30  # Disco de 30GB
                # Para simplicidade, pode usar DHCP da sua LAN principal
                vm_ipconfig: "dhcp"
                # Ou um IP estático se preferir e adicionar ao hosts.ini
                # vm_ipconfig: "ip=192.168.15.200/24,gw={{ vm_cloud_init_gateway }}"
                vm_tags: "test,dev,disposable,ansible_managed"
                vm_start_at_boot: false # Geralmente não precisa iniciar com o host
            ```
            Lembre-se de adicionar `test-environment-vm ansible_host=IP_PARA_TEST_VM` ao seu arquivo `ansible/inventories/home/hosts.ini` se você der um IP estático. Se usar DHCP, você encontrará o IP na UI do Proxmox após o boot (se o QEMU Guest Agent estiver funcionando).
*   **Isolamento de Rede (Opcional, mas Recomendado para Testes Arriscados):**
    *   Se a VM de teste for usada para software não confiável ou se você quiser evitar que ela acesse sua LAN principal:
        1.  No Proxmox (Datacenter -> Nó -> System -> Network), crie uma nova **Linux Bridge** (e.g., `vmbr2`).
        2.  **NÃO** associe esta nova bridge a nenhuma placa de rede física do host.
        3.  **NÃO** configure um endereço IP ou gateway para esta bridge no host Proxmox.
        4.  Ao criar/configurar a VM de teste (via UI ou Ansible), conecte sua interface de rede virtual a esta bridge isolada (`vmbr2`).
        *   Os containers/VMs nesta bridge só poderão se comunicar entre si (se houver mais de um nela), mas não com sua LAN ou a internet, a menos que você adicione uma VM firewall/roteador também conectada a `vmbr2` e à sua LAN/WAN.
*   **Snapshots Proxmox:** Antes de instalar algo arriscado ou fazer uma mudança significativa na VM de teste, **tire um snapshot dela no Proxmox.** Se algo der errado, você pode reverter para o snapshot em segundos.
*   **Descarte Fácil:** Quando não precisar mais da VM de teste, você pode simplesmente desligá-la e deletá-la do Proxmox (clique com o botão direito -> Remove). Se ela foi criada via Ansible e você não pretende recriá-la com a mesma config, remova também a entrada correspondente do `vm-deploy.yml` e do `hosts.ini`.

## 3. VM Windows (Para Aplicações Específicas ou Testes)

Embora este guia foque primariamente em Linux para os serviços do servidor, você pode precisar de uma ou mais máquinas virtuais Windows para:
*   Rodar aplicações que só existem para Windows.
*   Testes de compatibilidade de software ou websites.
*   Acesso a ferramentas de desenvolvimento ou administração específicas do Windows.
*   (Com GPU passthrough) Jogos ou aplicações gráficas intensivas.

*   **Requisitos e Considerações:**
    *   **ISO de Instalação do Windows:** Você precisará de uma imagem ISO oficial do Windows (e.g., Windows 10, Windows 11, Windows Server).
    *   **Drivers VirtIO para Windows:** Para performance otimizada de disco, rede e outros dispositivos virtuais, é **altamente recomendado** usar os drivers VirtIO para Windows.
        *   Baixe a ISO dos drivers VirtIO mais recente da [Fedora Project](https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/). Procure pela `virtio-win-XX.iso`.
        *   Faça upload desta ISO para o seu storage `local (pve)` no Proxmox.
    *   **Licenciamento do Windows:** Lembre-se que sistemas operacionais Windows convidados requerem uma licença válida.
    *   **Recursos da VM:** Windows geralmente requer mais recursos do que uma VM Linux server.
        *   **RAM:** Mínimo de 4GB, recomendado 8GB+ para boa performance, especialmente com GUI.
        *   **Disco:** Pelo menos 60-80GB para o SO e aplicações básicas.
        *   **CPU:** Pelo menos 2 vCPUs, idealmente 4+ para uso com GUI.
    *   **GPU Passthrough (para Jogos/Gráficos):** Se o objetivo for jogos ou aplicações gráficas intensivas, o passthrough da sua GPU AMD RX 5600XT (ou outra GPU dedicada) para a VM Windows será necessário. Siga os mesmos princípios de passthrough da [Seção 3.4](../01-manual-implementacao/03-provisionamento-vms.md#34-configuração-de-gpu-passthrough-host-proxmox).
        *   !!! warning "Drivers de GPU em VM Windows com Passthrough"
            Alguns drivers de GPU (especialmente NVIDIA, mas às vezes AMD também) podem detectar que estão rodando em um ambiente virtualizado e se recusar a instalar ou funcionar corretamente (e.g., "Code 43" no Gerenciador de Dispositivos). Podem ser necessários [workarounds para esconder o status de VM do KVM](../01-manual-implementacao/03-provisionamento-vms.md#playbook-para-deploy-de-vm-ansibleplaybooksvm-deployyml) adicionando argumentos QEMU específicos na configuração da VM (e.g., via `vm_qemu_args` no Ansible ou diretamente no `.conf` da VM).
    *   **QEMU Guest Agent para Windows:** Instale os "Guest Tools" (que incluem o QEMU Guest Agent) dentro da VM Windows após a instalação do SO para melhor integração com o Proxmox (mouse, clipboard, desligamento gracioso). Eles geralmente estão incluídos na ISO `virtio-win.iso`.
*   **Criação da VM Windows (via UI Proxmox):**
    1.  **Create VM:**
        *   **OS:** Selecione "Microsoft Windows" e a versão apropriada. Marque "Install guest agent" (isso pode tentar montar uma ISO de guest tools se o Proxmox tiver uma).
        *   **System:** Machine `q35`, BIOS `OVMF (UEFI)`, EFI Storage no `local-lvm`, TPM `v2.0`.
        *   **CD/DVD Drive 1:** Monte sua ISO de instalação do Windows.
        *   **CD/DVD Drive 2 (Adicional):** Adicione um segundo drive de CD/DVD e monte a ISO `virtio-win-XX.iso`.
        *   **Hard Disk:**
            *   Bus/Device: `VirtIO SCSI` ou `VirtIO Block` (SCSI é geralmente preferido se você usar o controlador VirtIO SCSI).
            *   Storage: `local-lvm`.
            *   Disk size: Adequado (e.g., 100GB).
            *   SSD emulation: Marcado.
        *   **CPU:** Mínimo 2-4 cores.
        *   **Memory:** Mínimo 4096 MiB.
        *   **Network:** Model `VirtIO (paravirtualized)`.
    2.  **Instalação do Windows:**
        *   Inicie a VM. Durante a instalação do Windows, na tela de seleção de disco, o disco VirtIO pode não aparecer.
        *   Clique em "Load driver". Navegue até o drive de CD/DVD que contém a ISO `virtio-win.iso`.
        *   Procure pelo driver `viostor` (para VirtIO SCSI) ou `vioblk` (para VirtIO Block) para sua arquitetura Windows (e.g., `amd64/w10` ou `amd64/w11`).
        *   Carregue o driver. O disco virtual deve aparecer. Prossiga com a instalação.
    3.  **Pós-Instalação:**
        *   Dentro do Windows, abra o Gerenciador de Dispositivos. Dispositivos com exclamação amarela (como o controlador Ethernet) precisam de drivers.
        *   Navegue pelo CD/DVD `virtio-win.iso` e instale os drivers restantes (especialmente `NetKVM` para rede).
        *   Instale também os "Guest Tools" da ISO VirtIO, se disponíveis, para o QEMU Guest Agent.
*   **Gerenciamento Ansible para VMs Windows:**
    É possível, mas mais complexo que para Linux. Requer WinRM configurado na VM Windows e o uso de módulos Ansible específicos para Windows (e.g., `ansible.windows.win_feature`, `ansible.windows.win_package`). Para um homelab, o gerenciamento manual ou via RDP pode ser suficiente para poucas VMs Windows.

## Dicas Gerais para Criar Novas VMs

*   **Documente Suas VMs:** Mesmo que uma VM não seja totalmente gerenciada pelo Ansible, adicione uma entrada para ela no seu inventário Ansible (`hosts.ini`) com seu IP e um breve comentário sobre seu propósito. Isso ajuda a manter um registro centralizado da sua infraestrutura.
*   **Nomeação Consistente:** Use um esquema de nomeação claro e consistente para suas VMs e seus hostnames.
*   **Recursos com Moderação:** Comece com uma alocação de recursos modesta (CPU, RAM) e aumente apenas se o monitoramento indicar necessidade.
*   **Monitoramento:** Assim que a VM estiver operacional, instale o Node Exporter nela (se for Linux e você quiser métricas detalhadas) e adicione-a como um alvo no seu Prometheus para monitorar seu uso de recursos.
*   **Backups:** Não se esqueça de configurar backups para suas novas VMs no sistema de backup do Proxmox VE.
*   **Segurança:** Aplique princípios de segurança básicos (firewall, atualizações, senhas fortes) a todas as VMs, mesmo as de teste.

Ao criar VMs para cenários específicos, sempre avalie o impacto nos recursos globais do seu host Proxmox e planeje de acordo para manter a estabilidade e o desempenho de todo o seu ambiente de servidor doméstico.