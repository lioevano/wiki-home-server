# Cenários Específicos de Criação de VMs

Embora nossa arquitetura principal se concentre na `core-services-vm` e na `ai-desktop-vm`, podem surgir cenários onde você precise de máquinas virtuais com propósitos mais específicos. Este guia explora alguns desses cenários e as considerações para criá-los.

Lembre-se sempre da [limitação de 16GB de RAM do host Proxmox](../01-manual-implementacao/00-preparacao-planejamento.md#01-hardware-e-software-necessários) ao planejar novas VMs.

## 1. VM para Firewall/Roteador (e.g., pfSense, OPNsense)

Rodar seu próprio firewall/roteador em uma VM no Proxmox pode oferecer funcionalidades avançadas, controle granular e aprendizado sobre redes.

*   **Propósito:** Substituir ou complementar seu roteador físico, oferecendo firewall stateful, VPN server/client, IDS/IPS, modelagem de tráfego, etc.
*   **Softwares Populares:** pfSense, OPNsense (ambos baseados em FreeBSD).
*   **Requisitos e Considerações:**
    *   **Múltiplas Interfaces de Rede:** Essencial. Você precisará de pelo menos duas:
        *   **WAN:** Conectada ao seu modem/ONT (Internet).
        *   **LAN:** Conectada ao seu switch de rede local, para seus dispositivos e outras VMs.
        *   **Como fazer no Proxmox:**
            1.  **Hardware:** O host Proxmox precisa de pelo menos duas portas Ethernet físicas.
            2.  **Bridges Proxmox:** Crie duas bridges Linux no Proxmox (e.g., `vmbr0` para LAN, `vmbr1` para WAN). `vmbr1` não deve ter um endereço IP configurado no host Proxmox, pois a VM do firewall gerenciará essa interface.
            3.  **VM:** Adicione duas interfaces de rede virtual à VM do firewall, cada uma conectada a uma das bridges (`vmbr0` e `vmbr1`).
    *   **Passthrough de Placa de Rede (Opcional, Avançado):** Para performance máxima ou se precisar de funcionalidades específicas da placa de rede, você pode passar uma placa de rede PCI diretamente para a VM do firewall. Isso requer configuração de IOMMU.
    *   **Recursos da VM:** Geralmente não precisa de muita RAM ou CPU para um homelab (e.g., 1-2 vCPUs, 1-2GB RAM), mas depende do número de regras, pacotes (como Suricata/Snort) e tráfego.
    *   **Ordem de Boot e Dependências:** Se esta VM for seu gateway principal, o host Proxmox e outras VMs dependerão dela para acesso à rede/internet após o boot. Configure a ordem de início das VMs no Proxmox.
    *   **Alta Disponibilidade (Avançado):** Para evitar um ponto único de falha, setups de firewall mais avançados usam CARP/VRRP com duas VMs de firewall em um cluster Proxmox. (Fora do escopo deste guia).
    *   **Segurança:** A VM do firewall fica na borda da sua rede. Mantenha-a atualizada e configure regras de firewall restritivas.
*   **Criação da VM:**
    *   Use o [template base Ubuntu](../01-manual-implementacao/03-provisionamento-vms.md#31-criação-de-template-de-vm-base-ubuntu-server-cloud-init) ou baixe a ISO específica do pfSense/OPNsense.
    *   Use o playbook Ansible `vm-deploy.yml` para criar a VM, especificando as interfaces de rede conectadas às bridges corretas e os recursos.
    *   A configuração interna do pfSense/OPNsense (atribuição de interfaces WAN/LAN, DHCP server, regras de firewall) é feita dentro da própria VM após a instalação.

## 2. VM para Desenvolvimento ou Testes Isolados

Precisa testar um novo software, uma configuração arriscada, ou um ambiente de desenvolvimento específico sem impactar seus serviços principais? Uma VM de teste descartável é ideal.

*   **Propósito:** Ambientes isolados e temporários.
*   **Criação Rápida:**
    1.  **Clonar do Template:** A maneira mais rápida é clonar seu [template Ubuntu Cloud-Init](../01-manual-implementacao/03-provisionamento-vms.md#31-criação-de-template-de-vm-base-ubuntu-server-cloud-init) via UI do Proxmox ou Ansible.
    2.  **Ansible (`vm-deploy.yml`):** Adicione uma nova entrada ao `vm-deploy.yml` para a VM de teste, especificando um novo `vm_id`, `vm_name`, e `ansible_host` (IP).
        ```yaml
        # Exemplo no vm-deploy.yml
        - name: "Deploy VM: test-environment-vm"
          ansible.builtin.include_role:
            name: infra/proxmox-vm
          vars:
            vm_id: 200 # Novo ID
            vm_name: "test-environment-vm"
            vm_cores: 2
            vm_memory: 2048
            vm_disk_gb: 20
            vm_ipconfig: "dhcp" # Pode usar DHCP para simplicidade
            vm_tags: "test,disposable,ansible_managed"
        ```
        Lembre-se de adicionar `test-environment-vm ansible_host=IP_PARA_TEST_VM` ao seu `hosts.ini`.
*   **Isolamento de Rede (Opcional):**
    *   Se a VM de teste precisa estar isolada da sua LAN principal, você pode:
        *   Criar uma nova bridge Linux no Proxmox (e.g., `vmbr2`) que não esteja conectada a nenhuma interface física (rede apenas host ou apenas entre VMs nessa bridge).
        *   Conectar a interface de rede da VM de teste a essa bridge isolada.
*   **Snapshots:** Use snapshots do Proxmox para salvar o estado da VM de teste antes de fazer mudanças arriscadas, permitindo reverter facilmente.
*   **Descarte:** Quando não precisar mais, simplesmente delete a VM. Se criada via Ansible, remova a entrada do `vm-deploy.yml` e do `hosts.ini`.

## 3. VM Windows (Se Necessário)

Embora este guia foque em Linux, você pode precisar de uma VM Windows para aplicações específicas, testes de compatibilidade, ou acesso a ferramentas que só rodam em Windows.

*   **Propósito:** Rodar software específico do Windows, jogos (com GPU passthrough), etc.
*   **Requisitos e Considerações:**
    *   **ISO de Instalação do Windows:** Você precisará de uma ISO oficial do Windows.
    *   **Drivers VirtIO para Windows:** Para melhor performance de disco e rede, baixe a ISO dos drivers VirtIO para Windows da [Fedora Project](https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/) ou do Proxmox (geralmente disponível como uma ISO para montar).
        *   Durante a instalação do Windows, você precisará carregar os drivers VirtIO para o disco (viostor) para que o instalador reconheça o disco virtual.
        *   Após a instalação, instale os outros drivers VirtIO (rede, balloon, etc.) de dentro do Windows.
    *   **Licenciamento:** Lembre-se que o Windows requer uma licença válida.
    *   **Recursos da VM:** Windows geralmente requer mais RAM e disco que uma VM Linux server (e.g., mínimo 4GB RAM, 60-80GB disco).
    *   **GPU Passthrough (para Jogos/Gráficos):** Se o objetivo for jogos ou aplicações gráficas intensivas, o passthrough da sua RX 5600XT (ou outra GPU) para a VM Windows será necessário.
        *   !!! warning "Drivers de GPU em VM Windows"
            Alguns drivers de GPU (especialmente NVIDIA) podem ter "code 43" ou outros problemas ao detectar que estão rodando em uma VM. Podem ser necessários [workarounds para esconder o status de VM do KVM](../01-manual-implementacao/03-provisionamento-vms.md#playbook-para-deploy-de-vm-ansibleplaybooksvm-deployyml) (e.g., `vm_qemu_args`).
    *   **QEMU Guest Agent para Windows:** Instale para melhor integração.
*   **Criação da VM:**
    *   **UI Proxmox:**
        1.  Crie uma nova VM.
        2.  Monte a ISO do Windows como CD/DVD.
        3.  Monte a ISO dos drivers VirtIO como um segundo CD/DVD.
        4.  Configure o disco rígido para usar o bus `VirtIO SCSI` ou `VirtIO Block`.
        5.  Configure a placa de rede para usar o modelo `VirtIO (paravirtualized)`.
        6.  Siga o processo de instalação do Windows, carregando os drivers VirtIO para o disco quando solicitado.
    *   **Ansible:** Embora possível, gerenciar uma instalação completa do Windows via Ansible é mais complexo do que Linux. O foco do Ansible aqui seria mais no provisionamento da VM no Proxmox e, talvez, configurações pós-instalação muito básicas se ferramentas como `pywinrm` forem usadas (fora do escopo deste guia).

## Dicas Gerais para Novas VMs

*   **Documente:** Adicione a nova VM ao seu inventário Ansible (`hosts.ini`) e defina suas variáveis (IPs, etc.) mesmo que ela não seja totalmente gerenciada pelo Ansible. Isso ajuda a manter um registro da sua infraestrutura.
*   **Nomeação Consistente:** Use um esquema de nomeação claro para suas VMs.
*   **Monitoramento:** Adicione a nova VM aos alvos do Prometheus (configurando Node Exporter nela e atualizando `prometheus.yml`) para monitorar seus recursos.
*   **Backups:** Configure backups para a nova VM no Proxmox.

Lembre-se sempre das limitações de recursos do seu host Proxmox ao adicionar novas VMs. Cada VM consome CPU, RAM e disco, impactando o desempenho geral do sistema.