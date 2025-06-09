# Gerenciando Recursos de Máquinas Virtuais (VMs)

À medida que seu homelab evolui e suas necessidades mudam, você precisará ajustar os recursos alocados para suas máquinas virtuais (VMs). Esta página aborda como gerenciar CPU, RAM e discos de VMs existentes, além de considerações sobre quando adicionar mais recursos ou criar novas VMs.

As modificações de recursos são geralmente feitas através da **Interface Web do Proxmox VE**, mas é crucial entender como essas mudanças interagem com sua configuração **Ansible** para manter a consistência da sua Infraestrutura como Código (IaC).

## 1. Redimensionando CPU e RAM de uma VM

Aumentar ou diminuir o número de vCPUs ou a quantidade de RAM alocada para uma VM é uma tarefa comum.

### Procedimento (Interface Web Proxmox + Ansible)

1.  **Desligue a VM (Recomendado para a maioria das mudanças de CPU/RAM):**
    *   Na UI do Proxmox, selecione a VM.
    *   Clique em "Shutdown" (para um desligamento gracioso) ou "Stop" (se o shutdown não funcionar).
    *   !!! note "Hotplug de CPU/RAM"
        Proxmox suporta hotplug (adicionar "a quente") de CPU e RAM para VMs Linux se o QEMU Guest Agent estiver funcionando e o SO da VM suportar. No entanto, remover CPU/RAM "a quente" é geralmente mais arriscado ou não suportado. Para consistência e segurança, desligar a VM é a prática recomendada, especialmente para remoção ou grandes alterações.

2.  **Modifique os Recursos na UI do Proxmox:**
    *   Com a VM selecionada e desligada, vá para a aba "Hardware".
    *   **CPU:** Encontre a entrada "Processors". Clique em "Edit". Altere o número de "Cores" (ou "Sockets", dependendo de como você prefere configurar).
    *   **RAM:** Encontre a entrada "Memory". Clique em "Edit". Altere a quantidade de memória (em MiB).
        *   Considere o uso de "Ballooning" (se habilitado, permite que o Proxmox dinamicamente ajuste a memória da VM dentro de um mínimo e máximo, mas pode ter implicações de performance). Para este guia, focamos em alocação fixa.
    *   Clique em "OK".

3.  **Atualize a Configuração Ansible (Crucial para IaC):**
    *   Abra o arquivo `ansible/playbooks/vm-deploy.yml` na sua máquina de controle Ansible.
    *   Localize a seção de deploy da VM que você modificou (e.g., `core-services-vm` ou `ai-desktop-vm`).
    *   Atualize as variáveis `vm_cores` e `vm_memory` para refletir os novos valores que você configurou na UI do Proxmox.
        ```yaml
        # Exemplo de trecho no vm-deploy.yml
        - name: "Deploy VM: core-services-vm"
          ansible.builtin.include_role:
            name: infra/proxmox-vm
          vars:
            vm_id: 100
            vm_name: "core-services-vm"
            vm_cores: 6 # Novo valor de vCPUs
            vm_memory: 8192 # Novo valor de RAM (8GB)
            # ... outras vars ...
        ```
    *   Salve o arquivo.

4.  **Execute o Playbook Ansible:**
    Rode o playbook `vm-deploy.yml` para que o Ansible registre o novo estado desejado. Como a VM já existe, o Ansible (via módulo `community.proxmox.proxmox_kvm` com `update: true`) deve apenas confirmar ou aplicar as mudanças de recursos se houver divergência.
    ```bash
    ansible-playbook ansible/playbooks/vm-deploy.yml --ask-vault-pass
    ```
    !!! warning "Idempotência e Estado Desejado"
        Se você não atualizar o Ansible, na próxima vez que o `vm-deploy.yml` rodar, ele poderá tentar reverter os recursos da VM para os valores antigos definidos no playbook. Manter a UI do Proxmox e o Ansible sincronizados é chave.

5.  **Inicie a VM:**
    *   Na UI do Proxmox, inicie a VM.
    *   Verifique dentro da VM (e.g., com `htop` ou `free -h`) se os novos recursos estão sendo reconhecidos.

## 2. Redimensionando Discos Virtuais

Aumentar o tamanho de um disco virtual existente é possível. Diminuir é muito mais complexo e arriscado (geralmente envolve ferramentas de particionamento dentro da VM e pode levar à perda de dados se não feito corretamente - não recomendado).

### Aumentar o Tamanho de um Disco Virtual

1.  **Desligue a VM (Opcional, mas mais seguro para algumas operações de disco):**
    Embora o Proxmox permita redimensionar discos "a quente" para alguns formatos e se o QEMU Guest Agent estiver ativo, desligar pode evitar problemas.

2.  **Aumente o Tamanho do Disco na UI do Proxmox:**
    *   Selecione a VM -> "Hardware".
    *   Localize o disco virtual que você quer redimensionar (e.g., `scsi0`).
    *   Clique em "Disk Action" (ou "Edit" dependendo da versão) -> "Resize disk".
    *   Insira o **incremento** de tamanho que você quer adicionar (e.g., se o disco tem 32GB e você quer 50GB, insira `+18G`). Ou, algumas versões permitem inserir o tamanho total final.
    *   Clique em "Resize".

3.  **Atualize a Configuração Ansible:**
    *   No `ansible/playbooks/vm-deploy.yml`, atualize a variável `vm_disk_gb` para o **novo tamanho total** do disco.
        ```yaml
        # Exemplo
        vm_disk_gb: 50 # Novo tamanho total em GB
        ```
    *   Execute `ansible-playbook ansible/playbooks/vm-deploy.yml --ask-vault-pass`.

4.  **Expanda o Sistema de Arquivos Dentro da VM:**
    Aumentar o disco virtual no Proxmox apenas aloca mais espaço para o dispositivo de bloco. O sistema de arquivos *dentro* da VM ainda não sabe sobre esse espaço extra.
    *   Inicie a VM.
    *   Conecte-se à VM via SSH.
    *   Use ferramentas como `lsblk` para identificar a partição e `df -h` para ver o tamanho atual do sistema de arquivos.
    *   O processo exato depende do sistema de arquivos (ext4, XFS) e se LVM está em uso.
        *   **Para ext4 sem LVM (comum em imagens Cloud-Init):**
            1.  Identifique a partição raiz (e.g., `/dev/sda1` se o disco for `sda`). Se for `scsi0` no Proxmox, pode ser `/dev/sda` ou `/dev/vda`. Supondo que a imagem cloud-init usou todo o disco para uma partição principal e um sistema de arquivos nela.
            2.  **Use `growpart` (do pacote `cloud-guest-utils`) para expandir a partição:**
                ```bash
                # Instale se não tiver: sudo apt install cloud-guest-utils
                # Supondo que o disco é /dev/sda e a partição a ser expandida é a 1
                sudo growpart /dev/sda 1
                ```
            3.  **Redimensione o sistema de arquivos ext4:**
                ```bash
                sudo resize2fs /dev/sda1 # Use o nome da partição
                ```
            4.  Verifique com `df -h`. O tamanho deve ter aumentado.
        *   **Se LVM estiver em uso:** O processo envolve `pvresize` (para o Physical Volume), `lvextend` (para o Logical Volume), e depois `resize2fs` (ou `xfs_growfs` para XFS) no sistema de arquivos.

### Adicionando um Segundo Disco Virtual a uma VM

1.  **Crie o Novo Disco Virtual na UI do Proxmox:**
    *   VM -> Hardware -> Add -> Hard Disk.
    *   Selecione o storage (e.g., `local-lvm`), tamanho, formato (Qcow2), bus (SCSI), etc.

2.  **Atualize a Configuração Ansible (Opcional, mas bom para documentar):**
    *   O módulo `community.proxmox.proxmox_kvm` permite definir múltiplos discos. Você pode adicionar a definição do novo disco (e.g., `scsi1`) no `vm-deploy.yml` se quiser que o Ansible esteja ciente dele.
        ```yaml
        disk:
          scsi0:
            size: "{{ vm_disk_gb }}G"
            storage: "{{ vm_storage_disk }}"
          scsi1: # Novo disco
            size: "100G" # Exemplo de tamanho
            storage: "{{ vm_storage_disk }}" # Ou outro storage
            format: "qcow2"
        ```
    *   Execute o playbook Ansible.

3.  **Particione, Formate e Monte o Novo Disco Dentro da VM:**
    *   Inicie a VM.
    *   O novo disco aparecerá como um novo dispositivo de bloco (e.g., `/dev/sdb` ou `/dev/vdb`).
    *   Use `sudo fdisk /dev/sdb` ou `sudo parted /dev/sdb` para criar uma partição.
    *   Formate a partição: `sudo mkfs.ext4 /dev/sdb1`.
    *   Crie um ponto de montagem: `sudo mkdir /mnt/novo_disco`.
    *   Adicione uma entrada ao `/etc/fstab` para montagem automática e monte:
        ```bash
        # Adicione ao /etc/fstab (use o UUID da partição com 'blkid /dev/sdb1'):
        # UUID=xxxx-xxxx /mnt/novo_disco ext4 defaults 0 2
        sudo mount -a
        ```

## 3. Monitorando o Uso de Recursos por VM

*   **UI do Proxmox:** A aba "Summary" de cada VM mostra o uso atual de CPU, RAM, disco e rede. A aba "Monitor" oferece gráficos históricos.
*   **Stack de Monitoramento (Grafana/Prometheus):**
    *   O Node Exporter (rodando em cada VM e no host) coleta métricas detalhadas.
    *   Dashboards no Grafana (como o "Node Exporter Full" - ID 1860) podem visualizar esses dados por VM.
    *   Glances também fornece uma visão geral.
*   **Dentro da VM:** Comandos como `htop`, `top`, `free -h`, `df -h`, `iostat`, `vmstat`.

## 4. Considerações Sobre Overcommitment de CPU/RAM

*   **CPU Overcommitment:** É comum e geralmente bem tolerado em Proxmox/KVM. Você pode alocar mais vCPUs totais para suas VMs do que o número de núcleos físicos do seu host. O hypervisor agenda os vCPUs nos núcleos físicos. Para cargas de trabalho típicas de homelab (muitas vezes ociosas), isso funciona bem. Evite sobrealocação excessiva se tiver VMs com carga de CPU constantemente alta.
*   **RAM Overcommitment (Evitar sem Ballooning/KSM Cuidadosos):**
    *   Alocar mais RAM total para as VMs do que a RAM física disponível no host (descontando a RAM do host) é **arriscado** e pode levar a uso intenso de swap (no host ou nas VMs), degradando severamente a performance.
    *   **Ballooning:** Permite que as VMs devolvam memória não utilizada ao host, mas pode ter overhead.
    *   **KSM (Kernel Samepage Merging):** Pode economizar RAM deduplicando páginas idênticas. Habilitado no Proxmox, pode ser monitorado.
    *   **Gerenciamento de RAM com 48GB:** Com 48GB de RAM no host, há consideravelmente mais flexibilidade. No entanto, ainda é importante não sobrealocar a RAM de forma excessiva. Mantenha uma reserva adequada para o host Proxmox (recomenda-se 2-4GB ou mais, dependendo do uso do ZFS ARC e outros serviços do host) para garantir estabilidade.

## 5. Quando Criar uma Nova VM vs. Adicionar Recursos?

*   **Isolamento:** Se um novo serviço é crítico, instável, tem requisitos de segurança muito diferentes, ou você quer experimentar com ele sem afetar outros serviços, uma nova VM oferece melhor isolamento.
*   **Requisitos de Recursos Específicos:** Se um serviço precisa de um SO diferente, ou de acesso exclusivo a um dispositivo de hardware via passthrough, uma nova VM é necessária.
*   **Organização:** Agrupar serviços com propósitos semelhantes em uma mesma VM (como a `core-services-vm`) pode simplificar o gerenciamento, mas não exagere para não sobrecarregá-la.
*   **Impacto de Performance:** Se adicionar um novo serviço a uma VM existente for degradar significativamente a performance dos outros serviços nela, considere uma nova VM (se os recursos do host permitirem).
*   **Limites de Recursos do Host:** Lembre-se sempre da capacidade total do seu host Proxmox, especialmente RAM. Não adianta criar muitas VMs se o host não consegue suportá-las.

Gerenciar recursos de VM é um equilíbrio entre fornecer o suficiente para suas aplicações e não sobrecarregar o host físico. Monitoramento regular e planejamento cuidadoso são seus melhores aliados.
