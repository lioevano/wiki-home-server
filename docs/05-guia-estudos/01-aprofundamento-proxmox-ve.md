# Aprofundamento em Proxmox VE

Proxmox Virtual Environment (PVE) é a fundação da nossa infraestrutura de servidor doméstico, fornecendo uma plataforma de virtualização robusta, open-source e rica em funcionalidades. Enquanto o [Manual de Implementação](../01-manual-implementacao/02-proxmox-ve-host.md) cobriu os passos essenciais para instalar e configurar o Proxmox VE para nossas necessidades básicas, esta seção tem como objetivo explorar alguns dos seus recursos mais avançados e conceitos que podem ajudá-lo a otimizar seu ambiente, expandir suas capacidades de virtualização e entender melhor o que está acontecendo "por baixo dos panos".

## 1. Clusterização Proxmox VE: Gerenciando Múltiplos Hosts

Embora nossa configuração atual neste guia seja de um único host Proxmox VE (um único servidor físico), o PVE foi projetado desde o início para funcionar em **clusters** de múltiplos hosts.

*   **O que é um Cluster Proxmox VE?**
    Um cluster PVE permite que você conecte dois ou mais servidores Proxmox VE para que eles possam ser gerenciados a partir de uma **única interface web centralizada**. Os hosts no cluster compartilham certas configurações (como definições de storage lógico, algumas configurações de rede) e podem oferecer funcionalidades avançadas como migração de VMs e alta disponibilidade (HA).
*   **Requisitos para Criar um Cluster:**
    *   **Mínimo de 2 Hosts Proxmox VE:** Embora um cluster de 2 nós seja funcional, para funcionalidades de Alta Disponibilidade (HA) robustas e para evitar problemas de "split-brain" com o sistema de quorum (Corosync), **3 ou mais hosts são fortemente recomendados.**
    *   **Rede Dedicada para Comunicação do Cluster (Corosync):** Idealmente, uma interface de rede física separada e uma rede (ou VLAN) dedicada para o tráfego de comunicação do Corosync entre os nós do cluster. Esta rede precisa ser de baixa latência e confiável.
    *   **Storage Compartilhado (para Migração Ao Vivo e HA de Storage):** Se você deseja realizar migração ao vivo de VMs (mover uma VM em execução de um host para outro sem downtime perceptível) ou ter alta disponibilidade para os discos das VMs, você precisará de um storage compartilhado acessível por todos os hosts no cluster. Exemplos incluem:
        *   **Ceph:** Uma solução de storage distribuído, open-source e definida por software que pode ser integrada diretamente com o Proxmox VE.
        *   **Servidor NFS:** Um servidor NFS centralizado (que pode ser um NAS dedicado ou outra máquina) onde os discos das VMs são armazenados.
        *   **iSCSI, Fibre Channel:** Soluções de SAN mais tradicionais.
        *   Nosso setup atual usa ZFS local em cada host (se tivéssemos múltiplos hosts, cada um teria seu ZFS local). Migração de VMs entre hosts com ZFS local é possível (migração offline), mas a migração ao vivo com ZFS local requer configurações mais complexas como replicação ZFS entre os hosts.
*   **Principais Vantagens de um Cluster Proxmox VE:**
    *   **Gerenciamento Centralizado:** Configure, monitore e gerencie todos os seus hosts Proxmox e todas as suas VMs/LXC containers a partir de uma única interface web.
    *   **Migração de Máquinas Virtuais:**
        *   **Migração Offline:** Mover uma VM desligada de um host para outro no cluster. Isso pode ser feito mesmo com storage local (o disco da VM é copiado pela rede).
        *   **Migração Ao Vivo (Live Migration):** Mover uma VM *em execução* de um host para outro com mínimo ou nenhum downtime perceptível para a VM. **Requer storage compartilhado** para os discos da VM e CPUs compatíveis entre os hosts.
    *   **Alta Disponibilidade (HA) para VMs:**
        *   Se um host Proxmox no cluster falhar (e.g., problema de hardware, desligamento inesperado), as VMs que foram configuradas para HA e que estavam rodando naquele host podem ser **automaticamente reiniciadas em outro host disponível** no cluster.
        *   **Requer storage compartilhado** para os discos das VMs e um mínimo de 3 hosts para um quorum HA confiável.
*   **Considerações para um Homelab:**
    *   Criar um cluster Proxmox VE pode ser um excelente projeto de aprendizado se você tiver hardware adicional (mesmo máquinas mais modestas, como PCs antigos ou Intel NUCs, podem servir como nós de cluster para experimentação).
    *   Para um homelab, a HA completa pode ser um exagero, mas a migração de VMs (mesmo offline) e o gerenciamento centralizado já são grandes benefícios.
*   **Onde Aprender Mais sobre Clusterização Proxmox VE:**
    *   **Documentação Oficial Proxmox VE - Cluster Manager:** [https://pve.proxmox.com/pve-docs/chapter-pvecm.html](https://pve.proxmox.com/pve-docs/chapter-pvecm.html)
    *   Muitos tutoriais e vídeos da comunidade Proxmox.

## 2. Proxmox Backup Server (PBS): Backups Otimizados e Centralizados

Enquanto o sistema de backup integrado do Proxmox VE (que usa `vzdump` para criar arquivos em um storage de diretório) é funcional e foi o que configuramos para backups locais no nosso dataset ZFS `/data/backups/vms`, o **Proxmox Backup Server (PBS)** é uma solução de backup separada, de nível empresarial, totalmente open-source, e especificamente otimizada para backups de VMs KVM e containers LXC do Proxmox VE.

*   **O que é o Proxmox Backup Server?**
    O PBS é uma distribuição Linux separada (também baseada em Debian) que você instala em um **hardware dedicado** (preferencialmente) ou em uma máquina virtual. Ele atua como um servidor de destino para seus backups Proxmox VE.
*   **Principais Vantagens do PBS sobre o Backup VZDump Padrão para Diretório:**
    *   **Deduplicação Global em Nível de Bloco:** Esta é a maior vantagem. O PBS deduplica os dados de backup *entre todas as VMs e todos os backups armazenados nele*. Se você tem múltiplas VMs com sistemas operacionais similares ou arquivos repetidos, a economia de espaço no servidor de backup pode ser massiva (frequentemente na casa dos 50-90%).
    *   **Backups Incrementais "Para Sempre" e Rápidos:** Após o primeiro backup completo de uma VM para o PBS, os backups subsequentes são incrementais e geralmente muito rápidos, pois apenas os blocos de dados alterados desde o último backup são enviados para o PBS. O PBS reconstrói o "estado" da VM a partir dos blocos deduplicados.
    *   **Criptografia Integrada e Forte:** Suporte para criptografia robusta dos dados de backup, que pode ser feita no lado do cliente (Proxmox VE, antes de enviar os dados) e/ou no lado do servidor PBS (para os dados em repouso no PBS).
    *   **Verificação de Integridade e "Garbage Collection":** O PBS pode verificar a integridade dos backups armazenados e possui um processo de "garbage collection" para remover chunks de dados que não são mais referenciados por nenhum backup, recuperando espaço.
    *   **Interface Web Dedicada:** O PBS tem sua própria interface web para gerenciar datastores de backup, usuários, permissões, tarefas de sincronização, e para navegar/restaurar backups.
    *   **Sincronização Remota (Remote Sync):** O PBS pode sincronizar seus datastores de backup (e os backups contidos neles) com outro servidor PBS localizado em um local diferente, facilitando backups off-site.
    *   **Restauração Granular de Arquivos (Experimental/Em Desenvolvimento):** Algumas funcionalidades para montar backups de VM e restaurar arquivos individuais diretamente da UI do PBS ou via linha de comando.
*   **Como Integrar o PBS com o Proxmox VE:**
    1.  Instale o Proxmox Backup Server em uma máquina separada (ou VM).
    2.  No seu host Proxmox VE (Datacenter -> Storage -> Add), adicione um novo storage do tipo "**Proxmox Backup Server**".
    3.  Configure os detalhes do seu servidor PBS (IP, usuário, senha/token, datastore no PBS).
    4.  Configure seus jobs de backup no Proxmox VE para usar este novo storage PBS como destino.
*   **Considerações para um Homelab:**
    *   O PBS pode ser instalado em hardware relativamente modesto (e.g., um PC antigo, um Raspberry Pi 4 com um HD USB grande – embora a performance no Pi possa ser limitada pela interface USB e CPU para deduplicação/verificação). Para melhor performance, um sistema com CPU decente, RAM suficiente (para deduplicação) e discos rápidos é ideal.
    *   Mesmo para um único host Proxmox VE, usar PBS (mesmo rodando como VM no mesmo host, embora isso anule o benefício de isolamento de falha de hardware) pode trazer grandes economias de espaço de backup devido à deduplicação, especialmente se você tem muitos snapshots de backup ou VMs similares.
*   **Onde Aprender Mais sobre Proxmox Backup Server:**
    *   **Documentação Oficial Proxmox Backup Server:** [https://pbs.proxmox.com/docs/](https://pbs.proxmox.com/docs/)

## 3. LXC (Linux Containers) vs. KVM (Máquinas Virtuais) no Proxmox VE

Proxmox VE suporta dois tipos principais de virtualização: **KVM** para máquinas virtuais completas e **LXC** para containers Linux. Nosso guia focou primariamente em KVMs para hospedar nossos serviços Docker, pois oferece o maior isolamento e flexibilidade de sistema operacional.

*   **KVM (Kernel-based Virtual Machine):**
    *   **Tipo:** Virtualização completa (Type 1 hypervisor, pois o Proxmox é bare-metal).
    *   **Funcionamento:** Cada VM KVM roda seu próprio kernel de sistema operacional completamente independente (e.g., um kernel Linux para nossas VMs Ubuntu, ou um kernel Windows se você criar uma VM Windows).
    *   **Isolamento:** Oferece um nível de isolamento muito forte entre as VMs e entre as VMs e o host Proxmox. Uma falha de kernel dentro de uma VM KVM geralmente não afeta outras VMs ou o host.
    *   **Flexibilidade de SO:** Pode rodar praticamente qualquer sistema operacional x86/amd64 (Linux, Windows, BSDs, etc.).
    *   **Overhead de Recursos:** Consome mais recursos (CPU, RAM, disco) comparado ao LXC, pois cada VM precisa de recursos para seu próprio SO completo, além da aplicação.
    *   **Nosso Uso:** A `core-services-vm` e a `ai-desktop-vm` são implementadas como VMs KVM.

*   **LXC (Linux Containers):**
    *   **Tipo:** Virtualização em nível de sistema operacional (OS-level virtualization).
    *   **Funcionamento:** Containers LXC compartilham o **mesmo kernel do host Proxmox VE**. Eles rodam um ambiente Linux isolado (com seu próprio sistema de arquivos, processos, namespaces de rede), mas não têm seu próprio kernel.
    *   **Isolamento:** Fornece isolamento de processos, sistema de arquivos e rede, mas o isolamento não é tão forte quanto KVM, pois todos os containers LXC no mesmo host compartilham o kernel desse host. Uma vulnerabilidade de kernel no host poderia, teoricamente, afetar todos os LXCs.
    *   **Apenas para Distribuições Linux:** Só pode rodar sistemas operacionais convidados que sejam distribuições Linux.
    *   **Baixo Overhead de Recursos:** Consomem significativamente menos RAM e espaço em disco do que VMs KVM, e iniciam quase instantaneamente (segundos). A performance é muito próxima da nativa do host.
    *   **Casos de Uso Comuns em Homelab para LXC:**
        *   Rodar aplicações Linux únicas que não precisam do isolamento total de uma VM KVM e onde a eficiência de recursos é importante (e.g., um servidor Pi-hole, um servidor web leve, um servidor de banco de dados dedicado se você estiver confortável com o nível de isolamento do LXC).
        *   Se você tem muitos pequenos serviços Linux e quer maximizar a densidade no seu host.
        *   Para criar rapidamente ambientes de teste Linux.
    *   **Tipos de LXC: Privilegiado vs. Não Privilegiado:**
        *   **Containers LXC Não Privilegiados (Recomendado para Segurança):** São mais seguros. O usuário `root` dentro de um container não privilegiado **não** é o usuário `root` do host Proxmox. Isso é alcançado através do mapeamento de UID/GID entre o host e o container. Requer um pouco mais de configuração para o mapeamento.
        *   **Containers LXC Privilegiados:** Mais fáceis de configurar inicialmente, mas menos seguros. O usuário `root` dentro de um container privilegiado **é efetivamente o usuário `root` no host Proxmox**, o que representa um risco de segurança significativo se o container for comprometido. **Evite se possível.**
*   **Quando Escolher KVM vs. LXC no Proxmox VE?**
    *   **Escolha KVM para:**
        *   Isolamento máximo e segurança.
        *   Rodar sistemas operacionais não-Linux (e.g., Windows, pfSense/OPNsense que são FreeBSD).
        *   Quando você precisa de passthrough de hardware PCI completo e robusto (LXC pode ter limitações ou ser mais complexo para alguns tipos de passthrough de dispositivos).
        *   Para serviços críticos ou que lidam com dados muito sensíveis onde o isolamento do kernel é uma prioridade.
        *   Se a aplicação que você quer rodar já vem como uma imagem de VM ou ISO de instalação de SO.
    *   **Escolha LXC para:**
        *   Aplicações Linux confiáveis onde o baixo overhead de recursos e a performance próxima à nativa são prioritários.
        *   "Appliances" de rede ou serviços simples que não exigem um SO completo.
        *   Quando você quer uma densidade muito alta de "instâncias Linux" no seu host.
        *   Se você está confortável com o nível de isolamento de compartilhar o kernel do host.
*   **Gerenciamento no Proxmox:** Containers LXC são gerenciados de forma muito similar a VMs KVM através da interface web do Proxmox. Você pode criar LXCs a partir de "templates" de LXC (disponíveis para download no Proxmox ou que você pode criar) ou de arquivos de backup.

## 4. Opções de Redes Avançadas no Proxmox VE

O sistema de rede padrão do Proxmox VE, usando uma bridge Linux (`vmbr0`) conectada à sua interface de rede física para fornecer acesso à LAN para suas VMs, é simples e eficaz para muitos cenários de homelab. No entanto, Proxmox VE suporta configurações de rede mais complexas e avançadas.

*   **VLANs (Virtual LANs) - IEEE 802.1Q:**
    *   Se seu switch de rede gerenciável suporta VLANs, você pode segmentar sua rede local em múltiplas redes lógicas isoladas, mesmo que elas compartilhem a mesma infraestrutura física de cabeamento.
    *   **No Proxmox VE:**
        1.  **Switch Config:** Configure as portas do seu switch para "tagged" (trunk) para a porta onde o Proxmox está conectado, permitindo as VLAN IDs que você quer usar.
        2.  **Host Proxmox:**
            *   **Opção 1 (Bridge por VLAN):** Crie uma bridge Linux separada no Proxmox para cada VLAN. Exemplo: `vmbr0` (para sua LAN principal, talvez untagged ou VLAN nativa), `vmbr0.10` (para VLAN 10 - nome da interface no host seria `eth0.10` se `eth0` for a física), `vmbr0.20` (para VLAN 20).
            *   **Opção 2 (Bridge VLAN Aware):** Configure sua bridge principal (e.g., `vmbr0`) para ser "VLAN aware" (uma opção na configuração da bridge na UI do Proxmox). Então, ao configurar a interface de rede de uma VM, você pode simplesmente especificar o "VLAN Tag" (e.g., 10) e a VM será colocada naquela VLAN.
    *   **Casos de Uso:**
        *   Isolar tráfego de dispositivos IoT não confiáveis em sua própria VLAN.
        *   Criar uma rede de "convidados" separada.
        *   Segmentar diferentes ambientes (e.g., uma VLAN para seus servidores de "produção", outra para testes).
        *   Necessário se sua VM firewall (pfSense/OPNsense) precisa lidar com múltiplas VLANs na interface LAN.
*   **Bonding (Link Aggregation - LAG):**
    *   Combine múltiplas interfaces de rede físicas do seu host Proxmox em uma única interface lógica "bond".
    *   **Benefícios Potenciais:**
        *   **Aumento da Largura de Banda Agregada:** Se o modo de bonding e o switch suportarem (e.g., LACP 802.3ad), o tráfego pode ser distribuído entre os links.
        *   **Redundância/Failover:** Se um link físico falhar, o tráfego pode continuar fluindo pelos links restantes no bond.
    *   **Requisitos:** Seu switch de rede precisa suportar o modo de bonding que você escolher (e.g., LACP, balance-xor, active-backup).
    *   **Configuração:** Feita no arquivo `/etc/network/interfaces` do host Proxmox, definindo uma interface `bondX` e especificando seus `slaves` (as interfaces físicas) e o `bond_mode`.
*   **SDN (Software Defined Networking):**
    *   Proxmox VE tem suporte (ainda considerado experimental/em desenvolvimento em algumas áreas, mas funcional) para SDN. Isso permite criar e gerenciar redes virtuais complexas e zonas de firewall de forma mais programática e flexível, diretamente da UI do Proxmox.
    *   **Tipos de Redes SDN:** VLANs, QinQ, VXLANs, EVPNs.
    *   **Zonas de Firewall SDN:** Permite definir regras de firewall entre essas redes virtuais.
    *   **Para Usuários Avançados:** Adiciona uma camada de complexidade, mas oferece grande poder para setups de rede mais elaborados ou para simular ambientes de nuvem.

## 5. Otimização de Performance de Máquinas Virtuais (KVM)

Algumas dicas para garantir que suas VMs KVM rodem da melhor forma possível:

*   **Drivers VirtIO (Essencial):**
    *   **Sempre** use os drivers VirtIO para os dispositivos virtuais mais críticos das suas VMs:
        *   **Rede:** Escolha o modelo `VirtIO (paravirtualized)` para a placa de rede da VM.
        *   **Disco:** Use o bus `VirtIO SCSI` (com o controlador `VirtIO SCSI` ou `VirtIO SCSI single` na VM) ou `VirtIO Block` para os discos rígidos virtuais.
    *   Estes drivers são paravirtualizados, o que significa que o SO convidado sabe que está rodando em um ambiente virtual e pode se comunicar de forma muito mais eficiente com o hypervisor, resultando em performance significativamente melhor do que emular hardware legado (e.g., E1000 para rede, IDE para disco).
    *   Para VMs Linux, os drivers VirtIO geralmente já estão incluídos no kernel. Para VMs Windows, você precisa [fornecer a ISO dos drivers VirtIO durante a instalação](../03-guias-sustentacao/07-cenarios-especificos-criacao-vms.md#vm-windows-para-aplicações-específicas-ou-testes).
*   **QEMU Guest Agent:**
    *   Instalado em todas as suas VMs (como fizemos no template).
    *   Permite que o Proxmox obtenha informações precisas da VM (como endereços IP), realize desligamentos/reinícios "graciosos", e execute comandos `fsfreeze` para garantir a consistência dos snapshots de backup de VMs em execução.
*   **Tipo de CPU da VM (Configuração da VM -> Processors -> Type):**
    *   `kvm64` (Padrão): Emula uma CPU x86-64 genérica. Oferece a melhor compatibilidade e portabilidade da VM para outros hosts Proxmox (mesmo com CPUs físicas diferentes).
    *   `host`: Passa (expõe) quase todas as features da CPU física do seu host Proxmox diretamente para a VM. Pode oferecer a **melhor performance** para a VM, pois ela pode usar instruções específicas da CPU do host. No entanto, isso **reduz a portabilidade da VM**; você pode não conseguir migrar (especialmente ao vivo) essa VM para outro host Proxmox com uma CPU física diferente (e.g., de AMD para Intel, ou mesmo entre gerações diferentes da mesma marca).
    *   **Para homelab com um único host, ou se a migração ao vivo não for uma prioridade, usar `type: host` pode trazer um pequeno ganho de performance.** Se a portabilidade ou migração futura for importante, `kvm64` é mais seguro.
*   **Configurações de Cache de Disco da VM (Configuração do Hard Disk da VM -> Advanced -> Cache):**
    *   `Default (No cache)`: O Proxmox não faz cache adicional de I/O para o disco da VM; depende do cache do SO convidado e do ZFS ARC (se o disco da VM estiver em ZFS). Geralmente uma escolha segura e com boa performance.
    *   `Write back`: O Proxmox/QEMU pode fazer cache de escritas em RAM e reportar a escrita como concluída para a VM antes que ela seja realmente escrita no disco físico. **Pode melhorar drasticamente a performance de escrita, MAS introduz um risco de perda de dados em caso de queda de energia do host Proxmox**, a menos que você tenha uma UPS confiável e o Proxmox esteja configurado para fazer flush dos caches de forma segura. Use com extrema cautela.
    *   `Write through`: As escritas são reportadas como concluídas para a VM apenas após serem escritas no disco físico. Mais seguro contra perda de dados por queda de energia, mas mais lento que `Write back`.
    *   `Direct Sync`, `Unsafe`: Outras opções com diferentes trade-offs.
    *   **Recomendação Geral:** Para a maioria dos casos, `Default (No cache)` é uma escolha equilibrada e segura, especialmente se os discos das VMs estão em um storage rápido como `local-lvm` (NVMe) ou um pool ZFS com bom ARC.
*   **Alocação de vCPUs e RAM:**
    *   Monitore o uso real de recursos dentro das suas VMs ([ver Guia de Gerenciamento de Recursos](../03-guias-sustentacao/06-gerenciando-recursos-vms.md)).
    *   Não superaloque vCPUs drasticamente se a VM não os utiliza (e.g., dar 8 vCPUs a uma VM que consistentemente usa apenas 10% de 1 vCPU).
    *   Para RAM, aloque o suficiente para as necessidades da VM e suas aplicações, mas evite sobrealocação excessiva que possa levar o host a usar swap.
*   **NUMA (Non-Uniform Memory Access):**
    *   Relevante apenas se o seu host Proxmox tiver **múltiplas CPUs físicas (sockets)**.
    *   Se for o caso, habilitar a opção "NUMA" na configuração da VM e garantir que os vCPUs e a memória alocada para a VM residam no mesmo nó NUMA físico pode melhorar a performance, reduzindo a latência de acesso à memória.
    *   Para nosso servidor com um único Ryzen 5 5600G (single socket), a configuração NUMA na VM não é uma grande consideração.

Explorar esses recursos avançados e opções de otimização pode ajudá-lo a adaptar seu ambiente Proxmox VE de forma mais precisa às suas necessidades, melhorar a performance e aumentar a resiliência geral do seu servidor doméstico. Lembre-se sempre de consultar a [**documentação oficial do Proxmox VE**](https://pve.proxmox.com/pve-docs/) para obter as informações mais detalhadas, atualizadas e para entender completamente as implicações de cada configuração.