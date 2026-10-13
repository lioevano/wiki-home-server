---
description: "Ajuste de CPU, RAM e disco das VMs no Proxmox mantendo o Ansible como fonte da verdade."
---

# Gerenciando Recursos de Máquinas Virtuais (VMs)

À medida que seu servidor doméstico evolui, seus serviços crescem, ou suas necessidades mudam, você provavelmente precisará ajustar os recursos alocados para suas máquinas virtuais (VMs). Esta página aborda como gerenciar CPU, RAM e discos de VMs existentes no Proxmox VE, com a importante consideração de manter a consistência com sua configuração Ansible (Infraestrutura como Código - IaC).

As modificações de recursos são geralmente realizadas através da **Interface Web do Proxmox VE**. No entanto, para que essas mudanças sejam persistentes e refletidas na sua IaC, elas também devem ser atualizadas nos seus arquivos Ansible, principalmente no playbook `vm-deploy.yml`.

## 1. Redimensionando vCPUs e RAM de uma VM Existente

Aumentar ou diminuir o número de processadores virtuais (vCPUs) ou a quantidade de memória RAM alocada para uma VM são tarefas comuns para otimizar a performance ou liberar recursos no host.

### Procedimento Recomendado (Interface Web Proxmox + Sincronização com Ansible)

1.  **Desligue a VM (Recomendado para a Maioria das Mudanças de CPU/RAM):**
    *   Na interface web do Proxmox VE, selecione a VM que você deseja modificar.
    *   Clique em "**Shutdown**" (para um desligamento gracioso do sistema operacional da VM) ou, se o shutdown não funcionar ou demorar muito, em "**Stop**" (que força o desligamento da VM).
    *   !!! note "Hotplug de CPU e RAM (Adicionar Recursos com a VM Ligada)"
        Proxmox VE, em conjunto com o QEMU Guest Agent (que deve estar instalado e rodando nas suas VMs), suporta o "hotplug" (adição "a quente") de vCPUs e RAM para VMs Linux enquanto elas estão em execução. Você pode tentar aumentar esses recursos com a VM ligada.
        *   **Hot-Unplug (Remover Recursos):** Remover CPU ou RAM "a quente" é geralmente **não suportado** ou muito mais arriscado e pode levar à instabilidade da VM.
        *   **Para consistência e segurança, especialmente ao reduzir recursos ou fazer grandes alterações, desligar a VM é a prática mais segura e recomendada.**

2.  **Modifique os Recursos na Interface Web do Proxmox:**
    *   Com a VM selecionada (e preferencialmente desligada), vá para a aba "**Hardware**".
    *   **Para CPU:**
        *   Encontre a entrada "**Processors**" na lista de hardware.
        *   Selecione-a e clique no botão "**Edit**".
        *   No diálogo "Edit: Processors", ajuste o número de "**Cores**". Você também pode ajustar "Sockets" se preferir (para a maioria dos casos em homelab, manter 1 socket e ajustar o número de cores é mais simples).
        *   Clique em "OK".
    *   **Para RAM:**
        *   Encontre a entrada "**Memory**" na lista de hardware.
        *   Selecione-a e clique no botão "**Edit**".
        *   No diálogo "Edit: Memory", ajuste a "**Memory (MiB)**" para o novo valor desejado.
            *   **Ballooning:** Se a opção "Ballooning Device" estiver habilitada (geralmente está por padrão), ela permite que o Proxmox host tente recuperar memória não utilizada da VM, dentro de um mínimo e máximo configuráveis. Para este guia, focamos em alocação de memória fixa (o valor que você define é o máximo que a VM pode usar), mas o ballooning pode ser explorado para otimizações dinâmicas.
        *   Clique em "OK".

3.  **Atualize a Configuração Ansible (Passo Crucial para Manter a IaC):**
    Esta é uma etapa **fundamental** para garantir que sua Infraestrutura como Código (Ansible) reflita o estado real da sua infraestrutura.
    *   Na sua máquina de controle Ansible, abra o arquivo `home-server/ansible/playbooks/vm-deploy.yml`.
    *   Localize a seção de deploy da VM que você acabou de modificar na UI do Proxmox (e.g., a task para `core-services-vm` ou `ai-desktop-vm`).
    *   Atualize as variáveis `vm_cores` e `vm_memory` (em MiB) para corresponder exatamente aos novos valores que você configurou na UI do Proxmox.
        ```yaml
        # Exemplo de trecho no vm-deploy.yml para core-services-vm
        - name: "Deploy VM: core-services-vm"
          ansible.builtin.include_role:
            name: infra/proxmox-vm
          vars:
            vm_id: 100
            vm_name: "core-services-vm"
            vm_cores: 8      # Exemplo: Atualizado para 8 vCPUs
            vm_memory: 24576 # Exemplo: Atualizado para 24GB RAM (24 * 1024)
            vm_disk_gb: 100
            vm_ipconfig: "ip={{ hostvars['core-services-vm']['ansible_host'] }}/24,gw={{ vm_cloud_init_gateway }}"
            vm_tags: "docker,core_services,homelab,ansible_managed"
        ```
    *   Salve o arquivo `vm-deploy.yml`.

4.  **Execute o Playbook Ansible para Registrar o Novo Estado Desejado:**
    Rode o playbook `vm-deploy.yml` a partir da sua máquina de controle Ansible. Como a VM já existe, o Ansible (através do módulo `community.proxmox.proxmox_kvm` com `update: true` e `state: present`) deve apenas verificar se os recursos da VM no Proxmox correspondem ao definido no playbook. Se você acabou de fazer a mudança na UI, ele deve reportar "ok" para as tasks de configuração de recursos. Se houvesse uma divergência (e.g., você mudou na UI mas esqueceu de mudar no Ansible e rodou o playbook), o Ansible tentaria aplicar os valores do playbook.
    ```bash
    ansible-playbook ansible/playbooks/vm-deploy.yml --ask-vault-pass
    ```
    !!! warning "Idempotência e Sincronização de Estado"
        Se você não atualizar os arquivos Ansible após uma mudança manual na UI do Proxmox, na próxima vez que o playbook `vm-deploy.yml` for executado, ele poderá tentar **reverter os recursos da VM para os valores antigos** que estavam definidos no playbook. Manter a UI do Proxmox e seus arquivos Ansible sincronizados é a chave para uma IaC eficaz. **A configuração Ansible deve ser a fonte da verdade.**

5.  **Inicie a VM (se estava desligada):**
    *   Na interface web do Proxmox, inicie a VM.
    *   Após o boot, conecte-se à VM via SSH e verifique se os novos recursos estão sendo reconhecidos pelo sistema operacional:
        *   Para CPU: `lscpu` ou `htop` (verá o número de cores).
        *   Para RAM: `free -h` ou `htop` (verá a memória total).

## 2. Redimensionando Discos Virtuais de VMs

Aumentar o tamanho de um disco virtual existente é uma operação relativamente comum e segura. **Diminuir** um disco virtual é um processo muito mais complexo, arriscado (risco de perda de dados) e geralmente não recomendado; normalmente envolve ferramentas de particionamento dentro da VM e não é diretamente suportado por uma simples ação no Proxmox.

### Aumentar o Tamanho de um Disco Virtual Existente

1.  **Desligue a VM (Opcional, mas Mais Seguro):**
    Embora o Proxmox permita redimensionar discos "a quente" para a maioria dos formatos de disco virtual (como qcow2 em storage LVM ou ZFS) se o QEMU Guest Agent estiver ativo e o SO da VM suportar, desligar a VM pode prevenir problemas potenciais durante a operação no sistema de arquivos da VM.

2.  **Aumente o Tamanho do Disco Virtual na Interface Web do Proxmox:**
    *   Na UI do Proxmox, selecione a VM e vá para a aba "**Hardware**".
    *   Localize o disco virtual que você deseja redimensionar na lista (e.g., `Hard Disk (scsi0)`).
    *   Selecione o disco.
    *   Clique no botão "**Disk Action**" (ou similar, dependendo da versão do Proxmox) e escolha "**Resize disk**".
    *   No diálogo "Resize disk":
        *   Você precisará inserir o **incremento** de tamanho que deseja adicionar ao disco (e.g., se o disco atual tem 50GB e você quer que ele tenha 70GB, você inseriria `+20G`). Algumas versões mais recentes do Proxmox podem permitir que você insira o tamanho total final desejado.
    *   Clique em "**Resize**". Proxmox alocará o espaço adicional para o dispositivo de bloco da VM.

3.  **Atualize a Configuração Ansible (para IaC):**
    *   No seu arquivo `ansible/playbooks/vm-deploy.yml`, localize a definição da VM e atualize a variável `vm_disk_gb` para o **novo tamanho total** do disco em Gigabytes.
        ```yaml
        # Exemplo no vm-deploy.yml
        # ...
            vm_disk_gb: 70 # Novo tamanho total do disco em GB
        # ...
        ```
    *   Execute o playbook Ansible para registrar a mudança:
        ```bash
        ansible-playbook ansible/playbooks/vm-deploy.yml --ask-vault-pass
        ```

4.  **Expanda o Sistema de Arquivos DENTRO da VM:**
    Aumentar o tamanho do disco virtual no Proxmox apenas aloca mais espaço para o dispositivo de bloco da VM. O sistema de arquivos *dentro* da VM (e.g., ext4, xfs) ainda não sabe sobre esse espaço extra e não o utilizará automaticamente.
    *   Inicie a VM (se estava desligada).
    *   Conecte-se à VM via SSH.
    *   Use `lsblk` para identificar o dispositivo de bloco e suas partições (e.g., `/dev/sda`, `/dev/sda1`).
    *   Use `df -h` para ver o tamanho atual do sistema de arquivos montado.
    *   O processo exato para expandir o sistema de arquivos depende de como o disco foi particionado e qual sistema de arquivos está em uso. Para as imagens Cloud-Init do Ubuntu, geralmente há uma única partição principal que ocupa o disco.
        *   **Para um sistema de arquivos `ext4` em uma partição simples (comum em imagens Cloud-Init):**
            1.  **Identifique o disco e a partição:** Se o disco no Proxmox é `scsi0`, ele pode aparecer na VM como `/dev/sda` (ou `/dev/vda` se usar VirtIO Block diretamente). A partição principal será algo como `/dev/sda1`. Use `lsblk`.
            2.  **Use `growpart` para expandir a partição:** O utilitário `growpart` (do pacote `cloud-guest-utils`) pode expandir a partição para preencher o espaço não alocado no disco.
                ```bash
                # Instale se não estiver presente: sudo apt update && sudo apt install -y cloud-guest-utils
                # Supondo que o disco é /dev/sda e a partição a ser expandida é a 1:
                sudo growpart /dev/sda 1
                ```
            3.  **Redimensione o sistema de arquivos `ext4`:**
                ```bash
                # Use o nome da partição que você expandiu (e.g., /dev/sda1)
                sudo resize2fs /dev/sda1
                ```
            4.  Verifique o novo tamanho com `df -h`. O sistema de arquivos deve agora mostrar o tamanho aumentado.
        *   **Se LVM (Logical Volume Management) estiver em uso dentro da VM:** O processo é mais complexo e envolve:
            1.  `pvresize /dev/sdXN` (para expandir o Physical Volume).
            2.  `lvextend -l +100%FREE /dev/mapper/VGNAME-LVNAME` (para expandir o Logical Volume).
            3.  `resize2fs /dev/mapper/VGNAME-LVNAME` (para ext4) ou `xfs_growfs /mount/point` (para XFS).

### Adicionando um Segundo (ou mais) Disco Virtual a uma VM

Se você precisar de um espaço de armazenamento separado dentro de uma VM (e não quiser usar NFS para esse propósito específico), você pode adicionar um novo disco virtual.

1.  **Crie o Novo Disco Virtual na Interface Web do Proxmox:**
    *   Selecione a VM -> aba "**Hardware**".
    *   Clique em "**Add**" -> "**Hard Disk**".
    *   **Storage:** Selecione o storage de destino (e.g., `local-lvm` para o SSD, ou até mesmo seu pool `data` se quiser um disco maior em HDDs, mas com performance de HDD).
    *   **Disk size (GiB):** Defina o tamanho do novo disco.
    *   **Format:** `QEMU image format (qcow2)` é geralmente uma boa escolha (permite snapshots, thin provisioning). `Raw disk image (raw)` pode oferecer uma pequena vantagem de performance em alguns casos.
    *   **Bus/Device:** `SCSI` (com controlador `VirtIO SCSI` na VM) é recomendado para performance.
    *   **SSD emulation:** Marque se o storage for SSD.
    *   Clique em "Add". Um novo disco (e.g., `scsi1`) aparecerá.

2.  **Atualize a Configuração Ansible (Opcional, mas Recomendado para Documentação e Consistência IaC):**
    *   Você pode adicionar a definição do novo disco ao playbook `ansible/playbooks/vm-deploy.yml` para que o Ansible esteja ciente dele e possa, no futuro, gerenciá-lo (embora o Ansible não vá particionar ou formatar dentro da VM sem tasks adicionais).
        ```yaml
        # Exemplo no vm-deploy.yml, na seção 'vars:' da VM
        # ...
        disk:
          scsi0: # Disco principal existente
            size: "{{ vm_disk_gb }}G"
            storage: "{{ proxmox_storage_vm_disks }}"
          scsi1: # Novo disco adicionado
            size: "100G" # Exemplo: novo disco de 100GB
            storage: "{{ proxmox_storage_vm_disks }}" # Ou outro storage se desejado
            format: "qcow2" # O formato que você escolheu
        # ...
        ```
    *   Execute `ansible-playbook ansible/playbooks/vm-deploy.yml --ask-vault-pass`. O Ansible deve reconhecer o disco existente.

3.  **Particione, Formate e Monte o Novo Disco DENTRO da VM:**
    *   Inicie a VM (ou reinicie se já estava rodando para que ela detecte o novo hardware).
    *   Conecte-se à VM via SSH.
    *   O novo disco virtual aparecerá como um novo dispositivo de bloco não formatado (e.g., `/dev/sdb` ou `/dev/vdb` se o primeiro disco for `/dev/sda` ou `/dev/vda`). Use `lsblk` para identificar.
    *   **Particione o novo disco (exemplo usando `fdisk` para criar uma única partição GPT):**
        ```bash
        sudo fdisk /dev/sdb # Substitua /dev/sdb pelo seu novo disco
        # Dentro do fdisk:
        # g (criar nova tabela de partição GPT)
        # n (nova partição)
        # p (primária, aceite os defaults para número, primeiro e último setor para usar o disco inteiro)
        # w (escrever as alterações e sair)
        ```
    *   **Formate a nova partição (e.g., `/dev/sdb1` com `ext4`):**
        ```bash
        sudo mkfs.ext4 /dev/sdb1
        ```
    *   **Crie um Ponto de Montagem:**
        ```bash
        sudo mkdir /mnt/meu_novo_disco_montado
        ```
    *   **Monte o Disco e Adicione ao `/etc/fstab` para Montagem Automática no Boot:**
        1.  Obtenha o UUID da nova partição: `sudo blkid /dev/sdb1` (copie o valor do UUID).
        2.  Edite `/etc/fstab`: `sudo nano /etc/fstab`
        3.  Adicione uma linha como:
            ```
            UUID=SEU_UUID_COPIADO_AQUI  /mnt/meu_novo_disco_montado  ext4  defaults,errors=remount-ro  0  2
            ```
        4.  Salve o `/etc/fstab`.
        5.  Monte todos os sistemas de arquivos listados no fstab (ou reinicie a VM):
            ```bash
            sudo mount -a
            ```
        6.  Verifique com `df -h`. O novo disco deve estar montado.

## 3. Monitorando o Uso de Recursos por VM

É crucial monitorar como suas VMs estão utilizando os recursos alocados para identificar gargalos ou oportunidades de otimização.

*   **Interface Web do Proxmox VE:**
    *   A aba "**Summary**" de cada VM mostra o uso atual de CPU, RAM, disco e tráfego de rede.
    *   A aba "**Monitor**" oferece gráficos históricos mais detalhados para esses mesmos recursos.
*   **Stack de Monitoramento (Prometheus e Grafana):**
    *   O **Node Exporter** (instalado em cada VM e no host Proxmox) coleta métricas detalhadas do sistema.
    *   **Grafana Dashboards:** Você pode (e deve) importar ou criar dashboards no Grafana para visualizar essas métricas por VM. Dashboards populares como "Node Exporter Full" (ID 1860 no grafana.com/dashboards) ou "Proxmox VE Host and VM stats" (ID 10347) são excelentes pontos de partida.
*   **Dentro da VM (Linha de Comando):**
    *   `htop` ou `top`: Uso de CPU e RAM por processo.
    *   `free -h`: Uso de memória RAM e swap.
    *   `df -h`: Uso de espaço em disco para sistemas de arquivos montados.
    *   `iostat`: Estatísticas de I/O de disco.
    *   `vmstat`: Estatísticas de memória virtual, processos, I/O de bloco, CPU.

## 4. Considerações Sobre Overcommitment de CPU e RAM

"Overcommitment" (ou sobrealocação) ocorre quando a soma dos recursos alocados para todas as VMs excede os recursos físicos disponíveis no host.

*   **CPU Overcommitment:**
    *   É **comum e geralmente bem tolerado** em ambientes de virtualização como Proxmox/KVM. Você pode, por exemplo, alocar um total de 16 vCPUs para suas VMs mesmo que seu host Proxmox tenha apenas 6 núcleos físicos (12 threads).
    *   O hypervisor (KVM) agenda os vCPUs das VMs para rodar nos núcleos físicos do host. Para cargas de trabalho típicas de homelab, onde muitas VMs ou serviços ficam ociosos na maior parte do tempo, isso funciona bem.
    *   **Evite sobrealocação excessiva** se você tiver múltiplas VMs com carga de CPU constantemente alta e próxima de 100% dos seus vCPUs alocados, pois isso levará a contenção e degradação de performance para todas as VMs.
*   **RAM Overcommitment (Geralmente a Evitar ou Usar com Cuidado Extremo):**
    *   Alocar mais RAM total para suas VMs do que a RAM física realmente disponível no host Proxmox (após descontar a RAM usada pelo próprio Proxmox OS e ZFS ARC) é **muito arriscado** e pode levar a:
        *   Uso intenso de **swap** no host Proxmox e/ou dentro das VMs, o que degrada severamente a performance (discos são ordens de magnitude mais lentos que RAM).
        *   O **OOM (Out-of-Memory) Killer** do Linux no host ou nas VMs pode começar a matar processos para liberar memória, causando instabilidade e perda de serviços.
    *   **Com 48GB de RAM no Host:** Você tem uma margem considerável. Se o Proxmox host usa ~2-4GB para si e para o ZFS ARC (o ARC pode usar até 50% da RAM do host por padrão, mas é dinâmico), você ainda tem mais de 40GB para alocar às VMs. A alocação de 16GB para `core-services-vm` e 16-24GB para `ai-desktop-vm` é viável, mas sempre monitore o uso real.
    *   **Memory Ballooning:**
        *   Habilitado por padrão no Proxmox para VMs KVM. Permite que a VM devolva memória não utilizada ao host, e que o host peça memória de volta (dentro dos limites mínimo e máximo configurados para a VM).
        *   Pode ajudar a otimizar o uso de RAM em cenários de baixa contenção, mas pode ter um pequeno overhead de performance. Para cargas de trabalho que precisam de RAM garantida, a alocação fixa (sem depender muito do ballooning para *reduzir* abaixo do alocado) é mais previsível.
    *   **KSM (Kernel Samepage Merging):**
        *   Pode ser habilitado no Proxmox (Serviços -> KSM). Ele escaneia a memória das VMs e deduplica páginas de memória idênticas, potencialmente economizando RAM.
        *   Tem um custo de CPU para o escaneamento. O benefício varia dependendo de quão similares são as cargas de trabalho das suas VMs. Pode ser útil se você tiver muitas VMs rodando o mesmo SO e aplicações.

## 5. Quando Criar uma Nova VM vs. Adicionar Recursos a uma Existente?

A decisão de escalar verticalmente (adicionar mais recursos a uma VM existente) ou horizontalmente (criar uma nova VM) depende de vários fatores:

*   **Isolamento de Serviços/Riscos:**
    *   Se um novo serviço é crítico, experimental, potencialmente instável, ou tem requisitos de segurança muito diferentes dos seus serviços existentes, colocá-lo em uma **nova VM dedicada** oferece o melhor isolamento. Uma falha ou comprometimento nessa VM não afetará diretamente suas outras VMs.
*   **Requisitos de Recursos Específicos:**
    *   Se um serviço precisa de um sistema operacional diferente do Ubuntu Server que usamos.
    *   Se um serviço precisa de acesso exclusivo a um dispositivo de hardware via passthrough PCI (e você não quer complexidade de múltiplos passthroughs para uma única VM).
*   **Organização e Gerenciamento:**
    *   Agrupar serviços com propósitos logicamente semelhantes em uma mesma VM (como fizemos com a `core-services-vm`) pode simplificar o gerenciamento e a comunicação interna entre eles.
    *   No entanto, não sobrecarregue uma única VM com muitos serviços diversos, pois isso pode dificultar o troubleshooting e aumentar o "raio de explosão" se algo der errado com aquela VM.
*   **Impacto de Performance:**
    *   Se adicionar um novo serviço (ou aumentar a carga de um existente) em uma VM já existente está começando a degradar significativamente a performance dos outros serviços naquela VM (mesmo após tentar adicionar mais CPU/RAM a ela), pode ser hora de mover esse serviço para uma **nova VM** (assumindo que os recursos do host Proxmox o permitam).
*   **Limites de Recursos Totais do Host Proxmox:**
    *   Lembre-se sempre da capacidade total do seu host Proxmox (CPU, RAM, I/O de disco). Não adianta criar muitas VMs se o host físico não consegue suportar a carga combinada de todas elas de forma estável.
    *   Monitore o uso de recursos do **host Proxmox** (via UI Proxmox ou Node Exporter no Grafana) além do uso das VMs individuais.

Gerenciar recursos de VM é um ato de equilíbrio contínuo. Monitore regularmente o uso, entenda os requisitos das suas aplicações, e não hesite em ajustar as alocações (ou criar novas VMs) conforme suas necessidades evoluem, sempre mantendo sua configuração Ansible como a fonte da verdade para a Infraestrutura como Código.