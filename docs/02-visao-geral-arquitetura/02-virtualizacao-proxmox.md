# Virtualização com Proxmox VE

Proxmox Virtual Environment (PVE) é a espinha dorsal da nossa infraestrutura de servidor doméstico, fornecendo a plataforma para hospedar todas as nossas aplicações e serviços em máquinas virtuais (VMs) isoladas.

## Por que Proxmox VE?

Proxmox VE foi escolhido por várias razões:

*   **Open Source:** É uma solução de virtualização de servidor completa, baseada em Debian Linux, e totalmente de código aberto.
*   **Baseado em KVM e LXC:**
    *   **KVM (Kernel-based Virtual Machine):** Permite virtualização completa, rodando sistemas operacionais convidados com seus próprios kernels (como nossas VMs Ubuntu).
    *   **LXC (Linux Containers):** Oferece virtualização em nível de sistema operacional, mais leve que KVM, ideal para rodar múltiplas aplicações Linux isoladas compartilhando o kernel do host (não explorado extensivamente neste guia, mas uma capacidade do PVE).
*   **Interface Web Integrada:** Facilita o gerenciamento de VMs, storage, rede e o próprio host Proxmox.
*   **Suporte a ZFS Integrado:** Permite o uso do sistema de arquivos ZFS para storage resiliente e com recursos avançados (ver [Estratégia de Armazenamento](03-armazenamento-zfs-nfs.md)).
*   **Backup e Restauração:** Ferramentas integradas para backup de VMs (snapshot, stop, suspend).
*   **Clusterização:** Proxmox VE suporta a criação de clusters de múltiplos hosts para alta disponibilidade e balanceamento de carga (não utilizado neste setup de servidor único, mas uma capacidade para expansão).
*   **Comunidade Ativa:** Grande comunidade e boa documentação.

## Gerenciamento de Recursos do Host Proxmox

O Proxmox VE gerencia os recursos de hardware do servidor físico e os distribui entre as VMs.

*   **CPU (AMD Ryzen 5 5600G):**
    *   Possui 6 núcleos / 12 threads.
    *   Os núcleos são alocados para as VMs conforme a necessidade. É importante não sobrealocar cronicamente os núcleos para evitar degradação de performance.
    *   Neste guia, a `core-services-vm` e a `ai-desktop-vm` recebem 4 vCPUs cada, o que representa uma sobrealocação se ambas estiverem em uso intenso simultaneamente. O PVE lida bem com sobrealocação leve para cargas de trabalho típicas de homelab.
*   **RAM (16GB DDR4):**
    *   Esta é a **principal limitação** do nosso hardware.
    *   O Proxmox host em si consome uma pequena quantidade de RAM (geralmente 1-2GB).
    *   O restante é dividido entre as VMs. A alocação de 6GB para `core-services-vm` e 8GB para `ai-desktop-vm` deixa pouca margem.
    *   O KSM (Kernel Samepage Merging) pode ser habilitado no Proxmox para deduplicar páginas de memória idênticas entre VMs, economizando RAM, mas com um pequeno custo de CPU. (O Node Exporter no host está configurado para coletar métricas KSM).
*   **Armazenamento:**
    *   **SSD NVMe 1TB:** Usado para o sistema operacional Proxmox VE e para os discos virtuais das VMs (`local-lvm`). Isso garante boot rápido do host e boa performance de I/O para as VMs.
    *   **HDDs 2x 500GB (ZFS Pool `/data`):** Usados para armazenamento de dados persistentes das aplicações, backups de VMs, etc., como detalhado na [Estratégia de Armazenamento](03-armazenamento-zfs-nfs.md).
*   **Rede (vmbr0):**
    *   Proxmox utiliza uma bridge Linux (`vmbr0` por padrão) para conectar as VMs à rede física. As VMs se comportam como se estivessem conectadas diretamente ao seu switch de rede local.

## Máquinas Virtuais (KVM) na Arquitetura

Nesta arquitetura, utilizamos principalmente VMs KVM para isolamento completo de ambientes.

*   **`core-services-vm`:**
    *   **Propósito:** Hospedar a maioria dos serviços Docker, incluindo a stack de rede (Traefik, Cloudflared, Authelia), Portainer, Nextcloud, Home Assistant, stack de mídia e stack de monitoramento.
    *   **Recursos (Exemplo):** 4 vCPUs, 6GB RAM, 80GB disco.
    *   **Sistema Operacional:** Ubuntu Server (instalado via template Cloud-Init).
*   **`ai-desktop-vm` (Opcional):**
    *   **Propósito:** Dedicada a tarefas de Inteligência Artificial (LLMs com Ollama, RAG) que podem se beneficiar de GPU passthrough (RX 5600XT). Pode também ter um ambiente desktop para interação direta.
    *   **Recursos (Exemplo):** 4 vCPUs, 8GB RAM, 150GB disco.
    *   **Sistema Operacional:** Ubuntu Server (ou Desktop, se GUI for primária).
    *   **GPU Passthrough:** Configurado no Proxmox para dar à VM controle direto da GPU RX 5600XT.

### Cloud-Init para Provisionamento de VMs

*   **Automação:** Utilizamos imagens Cloud-Init do Ubuntu Server como base para nossos templates de VM.
*   **Configuração Inicial:** Cloud-Init permite que o Ansible (através do módulo `community.proxmox.proxmox_kvm`) injete configurações iniciais na VM durante o primeiro boot, como:
    *   Hostname
    *   Criação do usuário Ansible (`vm_ansible_user`)
    *   Definição da senha do usuário
    *   Injeção da chave SSH pública para login sem senha
    *   Configuração de rede estática (IP, gateway, DNS)
*   Isso torna o processo de deploy de novas VMs rápido e consistente.

### QEMU Guest Agent

*   Instalado no template e, consequentemente, em todas as VMs.
*   Permite uma melhor comunicação entre o host Proxmox e a VM.
*   **Funcionalidades:**
    *   Obtenção precisa do endereço IP da VM pela UI do Proxmox.
    *   Desligamento/Reinício "gracioso" da VM a partir do Proxmox.
    *   Sincronização de tempo (embora NTP seja preferível).
    *   Execução de comandos `fsfreeze` para consistência de snapshots de backup.

## GPU Passthrough (Conceito e Aplicação)

*   **O que é:** Permite que uma VM KVM tenha controle exclusivo sobre um dispositivo PCI físico do host, como uma placa gráfica.
*   **Por que usar:**
    *   **Aceleração de IA/ML:** Muitos frameworks de Machine Learning (como os usados por Ollama) podem utilizar GPUs para acelerar o treinamento e a inferência de modelos. A RX 5600XT é passada para a `ai-desktop-vm` para este fim.
    *   **Transcoding de Mídia:** Servidores de mídia como Plex ou Jellyfin podem usar GPUs para acelerar o transcoding de vídeo (embora neste guia, a iGPU do host seja uma opção mais simples para Jellyfin na `core-services-vm`).
    *   **VM Desktop com Performance Gráfica:** Se a `ai-desktop-vm` for usada como uma estação de trabalho virtual com GUI, o passthrough da GPU fornece performance gráfica nativa.
*   **Complexidade:**
    *   Requer suporte de hardware (CPU e Chipset com IOMMU).
    *   Configuração no nível do kernel do Proxmox (GRUB, módulos `vfio`).
    *   Blacklisting dos drivers da GPU no host para que `vfio-pci` possa controlá-la.
    *   Isolamento IOMMU adequado (a GPU e seus dispositivos associados devem estar em grupos IOMMU que não contenham outros dispositivos críticos do host).
*   **Implementação:** Detalhada na [Seção 3.4 do Manual de Implementação](../01-manual-implementacao/03-provisionamento-vms.md#34-configuração-de-gpu-passthrough-host-proxmox).

A virtualização com Proxmox VE oferece uma base flexível e poderosa para construir e expandir seu servidor doméstico, permitindo o isolamento de serviços e o gerenciamento eficiente de recursos.