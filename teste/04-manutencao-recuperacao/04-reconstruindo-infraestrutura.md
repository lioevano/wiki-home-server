# Reconstruindo a Infraestrutura Após uma Falha Grave

Apesar de todos os esforços de manutenção e redundância (como ZFS RAID 1), falhas graves podem ocorrer. Isso pode incluir a falha do SSD NVMe principal (que hospeda o Proxmox OS e os discos das VMs), corrupção irreparável do sistema operacional do host, ou outros cenários de desastre.

Este guia descreve os passos para reconstruir sua infraestrutura base, assumindo que você tem:
1.  **Backups das suas VMs Proxmox** (do sistema de backup integrado do Proxmox).
2.  **Backups dos seus dados persistentes de containers Docker** (idealmente, os datasets ZFS `/data/docker-volumes`, `/data/media`, etc., foram backupeados com Borg ou rsync, ou pelo menos os dumps de bancos de dados).
3.  **Seu repositório Ansible `infra-servidor-domestico`** com todas as configurações (em um Git remote).
4.  **Acesso à sua senha do Ansible Vault.**

!!! important "Prevenção é Melhor que Remédio"
    Ter backups testados e uma estratégia de recuperação bem definida (como esta) é sua melhor apólice de seguro. Não espere um desastre para testar seus backups!

## Cenário de Exemplo

Vamos assumir que o SSD NVMe do seu servidor Proxmox falhou completamente, mas seus HDDs do pool ZFS `/data` (que contêm os backups das VMs e os dados dos containers) estão intactos ou você tem um backup off-site desses dados.

## Passos para Reconstrução

1.  **Preparar Novo Hardware/OS Drive (se necessário):**
    *   Substitua o SSD NVMe defeituoso por um novo.
    *   Verifique as conexões de todos os outros componentes (HDDs do pool ZFS, RAM, etc.).

2.  **Instalar Proxmox VE Base:**
    *   Siga os passos da [Seção 2.1 do Manual de Implementação](../01-manual-implementacao/02-proxmox-ve-host.md#21-instalação-do-proxmox-ve-no-servidor-físico) para instalar o Proxmox VE no novo SSD.
    *   Configure a rede do host Proxmox com o **mesmo IP estático** que ele tinha antes (e.g., `192.168.1.10`), se possível. Isso simplificará a restauração das configurações Ansible.
    *   Use a mesma senha `root` se lembrar, ou defina uma nova e atualize no Ansible Vault depois.

3.  **Restaurar Configuração do Host Proxmox (Opcional, mas Pode Ajudar):**
    *   Se você tem um backup dos arquivos de configuração do host Proxmox (conforme [Seção 11.1 do documento original / backup_proxmox_host_config.sh](#1-configuração-do-host-proxmox-ve)), você pode tentar restaurar seletivamente alguns arquivos para o novo host Proxmox.
    *   **Com muito cuidado,** restaure arquivos como:
        *   `/etc/network/interfaces` (se o hardware de rede for idêntico).
        *   `/etc/hosts`, `/etc/hostname`.
        *   `/etc/pve/storage.cfg` (se você souber o que está fazendo e os storages ZFS/LVM terão os mesmos nomes – mais fácil deixar o Ansible recriar/configurar).
        *   `/etc/exports` (para NFS).
    *   **É geralmente mais seguro deixar o Ansible (via `setup-proxmox-host.yml`) reconfigurar a maior parte do host.**

4.  **Recriar/Importar Pool ZFS `/data`:**

    *   **Caso 1: Os HDDs originais do pool `data` estão intactos:**
        1.  No shell do novo host Proxmox, tente importar o pool:
            ```bash
            sudo zpool import -f data
            # O -f pode ser necessário se o pool foi exportado de forma "suja".
            ```
        2.  Verifique o status: `sudo zpool status data`.
        3.  Se importado com sucesso, seus datasets (`docker-volumes`, `media`, `backups`, etc.) devem estar disponíveis em `/data/`.
    *   **Caso 2: Os HDDs do pool `data` foram perdidos, mas você tem um backup off-site dos dados dos datasets (e.g., Borg, rsync):**
        1.  Se os HDDs são novos, crie o pool ZFS espelhado novamente como na [Seção 2.2](../01-manual-implementacao/02-proxmox-ve-host.md#22-configuração-do-pool-zfs-data-e-datasets):
            ```bash
            sudo zpool create -f -o ashift=12 data mirror /dev/disk/by-id/ata-HDD1_ID /dev/disk/by-id/ata-HDD2_ID
            ```
        2.  Crie os datasets ZFS principais novamente:
            ```bash
            sudo zfs create data/docker-volumes
            sudo zfs create data/media
            # ...e os outros datasets
            ```
        3.  Restaure os *dados* de cada dataset a partir do seu backup off-site para os respectivos pontos de montagem (e.g., restaurar o conteúdo de `docker-volumes` para `/data/docker-volumes`).
    *   **Caso 3: Os HDDs do pool `data` foram perdidos, mas o dataset `data/backups` (contendo backups de VMs e DB dumps) estava em um storage separado e sobreviveu, OU você tem um backup off-site apenas do `data/backups`:**
        1.  Siga os passos do Caso 2 para recriar o pool `data` e os datasets.
        2.  Restaure o conteúdo do seu `data/backups` (VMs e DB dumps) para `/data/backups` no novo pool.

5.  **Configurar Storage de Backup no Proxmox (se necessário):**
    *   Na UI web do Proxmox, vá para Datacenter -> Storage.
    *   Se o storage que aponta para `/data/backups/vms` (ou onde seus backups de VMs estão) não existir ou estiver incorreto, adicione-o ou edite-o. Deve ser do tipo "Directory", com o caminho correto e conteúdo "VZDump backup file".

6.  **Restaurar Backups das VMs:**
    *   Com o storage de backup configurado e os arquivos de backup das VMs (`.vma.zst` ou similar) presentes nele:
        1.  Na UI do Proxmox, selecione o storage de backup.
        2.  Encontre os arquivos de backup das suas VMs (`core-services-vm`, `ai-desktop-vm`).
        3.  Para cada uma, clique em "Restore".
        4.  **VM ID:** É crucial que você restaure as VMs com os **mesmos VM IDs** que elas tinham antes (e.g., 100 para `core-services-vm`, 101 para `ai-desktop-vm`), pois o inventário Ansible e outras configurações podem depender desses IDs. Se você não puder usar o mesmo ID, precisará atualizar o inventário Ansible.
        5.  Configure outras opções de restauração conforme necessário (storage de destino para o disco da VM, etc.).
    *   As VMs serão restauradas para o estado em que estavam quando o backup foi feito.

7.  **Preparar Máquina de Controle Ansible e Repositório:**
    *   Se sua máquina de controle Ansible também foi perdida, configure uma nova seguindo a [Seção 1.1](../01-manual-implementacao/01-maquina-controle-ansible.md#11-instalação-do-ambiente-de-controle-scriptsbootstrapsh).
    *   Clone seu repositório `infra-servidor-domestico` do Git remote.
    *   Certifique-se de ter sua senha do Ansible Vault.

8.  **Executar Playbooks Ansible para Reconfigurar Tudo:**
    *   **Primeiro, o host Proxmox:**
        1.  Crie o usuário Ansible no novo host Proxmox e copie sua chave SSH para ele, como na [Seção 2.3](../01-manual-implementacao/02-proxmox-ve-host.md#ações-manuais-prévias-no-host-proxmox-importante).
        2.  Execute o playbook `setup-proxmox-host.yml` para garantir que o host Proxmox esteja configurado corretamente (NFS, firewall, etc.).
            ```bash
            ansible-playbook ansible/playbooks/setup-proxmox-host.yml --ask-vault-pass
            ```
    *   **Depois, as VMs e o restante da infraestrutura:**
        Execute o script `restore.sh` ou o playbook `full-deploy.yml`.
        ```bash
        # Na raiz do projeto infra-servidor-domestico/
        bash scripts/restore.sh # Ou use --vault-password-file se tiver
        # OU
        # ansible-playbook ansible/playbooks/full-deploy.yml --ask-vault-pass
        ```
        Isso irá:
        *   Verificar/reconfigurar as VMs (Cloud-Init pode não rodar da mesma forma em uma VM restaurada, mas o Ansible aplicará o estado).
        *   Configurar o cliente NFS nas VMs.
        *   Instalar Docker, Portainer.
        *   Configurar Traefik, Authelia.
        *   Preparar os diretórios e arquivos `.env` para as stacks Docker.

9.  **Implantar Stacks Docker via Portainer:**
    *   Acesse o Portainer.
    *   Para cada stack (mídia, produtividade, etc.):
        1.  Vá em "Stacks" -> "+ Add stack".
        2.  Cole o `docker-compose.yml` da stack.
        3.  Carregue o arquivo `.env` correspondente (que o Ansible deve ter recriado na VM).
        4.  Adicione os secrets manualmente no Portainer.
        5.  Clique em "Deploy the stack".
    *   Como os dados dos volumes Docker (e.g., `/data/docker-volumes/...`) foram restaurados (do pool ZFS original ou de um backup off-site), suas aplicações devem voltar com suas configurações e dados intactos. Os dumps de banco de dados podem precisar ser restaurados manualmente (ver etapa 3 dos backups de DB) se o backup do volume ZFS não for suficiente ou se você quiser um ponto de restauração mais recente do DB.

10. **Testar Tudo Exaustivamente:**
    *   Verifique cada serviço, acesso externo, autenticação, persistência de dados.

Este processo de reconstrução pode ser demorado, mas ter backups e automação com Ansible torna-o significativamente mais gerenciável e menos propenso a erros do que uma reconstrução manual completa.
```

---

## `homelab-wiki/docs/04-manutencao-recuperacao/05-migrando-hardware-rede.md`

```markdown
# Adaptando a Infraestrutura para Novo Hardware ou Mudanças de Rede

Com o tempo, você pode precisar migrar seu servidor doméstico para um novo hardware físico ou adaptar sua configuração a mudanças na sua rede local (como um novo roteador ou um novo esquema de endereçamento IP).

## A. Migração para Novo Servidor Físico (Novo Host Proxmox)

Mover toda a sua configuração Proxmox e VMs para uma nova máquina física.

**Considerações Prévias:**

*   **Compatibilidade de Hardware do Novo Servidor:**
    *   **CPU:** Deve suportar virtualização (AMD-V ou Intel VT-x) e IOMMU (AMD-Vi ou Intel VT-d) se você usa passthrough de PCI.
    *   **RAM:** Idealmente, igual ou superior à do servidor antigo.
    *   **Armazenamento:** Espaço suficiente para o Proxmox OS, discos das VMs e, crucialmente, para o pool ZFS `/data` (se for migrar os HDDs ou restaurar os dados).
    *   **Rede:** Pelo menos uma porta Ethernet Gigabit.
*   **IDs de Dispositivos PCI:** Se você usa passthrough de GPU ou outros dispositivos PCI, os IDs PCI desses dispositivos no novo hardware serão diferentes. Você precisará atualizar as configurações de passthrough nas VMs e, possivelmente, no Ansible (`vm-deploy.yml`).
*   **Nomes de Interfaces de Rede:** O nome da interface de rede principal no novo host Proxmox pode ser diferente (e.g., `enp3s0` em vez de `eno1`). Isso afetará a configuração da bridge `vmbr0`.

**Processo de Migração Sugerido:**

1.  **Backup Completo do Servidor Antigo:**
    *   Garanta que todos os backups (VMs, dados ZFS, configs Proxmox, repo Ansible) estejam atualizados e, idealmente, uma cópia off-site. Veja a [Estratégia de Backup](02-backup-restore-estrategia.md).

2.  **Setup Inicial do Novo Servidor Físico:**
    *   Instale o Proxmox VE no SSD NVMe do novo servidor, seguindo a [Seção 2.1 do Manual de Implementação](../01-manual-implementacao/02-proxmox-ve-host.md#21-instalação-do-proxmox-ve-no-servidor-físico).
    *   **Importante:** Durante a instalação, configure a rede do novo host Proxmox com o **mesmo endereço IP estático** que o servidor Proxmox antigo usava, se possível. Isso simplificará muito a transição. Se não for possível, anote o novo IP; você precisará atualizar o inventário Ansible.

3.  **Migração do Pool ZFS `/data` (Contendo Dados de Aplicações e Backups de VMs):**

    *   **Opção 1: Mover Fisicamente os HDDs do Pool ZFS (Mais Fácil se Possível):**
        1.  Desligue ambos os servidores.
        2.  Mova os HDDs que compõem o pool `data` do servidor antigo para o novo servidor. Conecte-os corretamente.
        3.  Inicie o novo servidor Proxmox.
        4.  No shell do novo host Proxmox, importe o pool ZFS:
            ```bash
            sudo zpool import -f data
            # Verifique o status:
            sudo zpool status data
            ```
            Seus datasets (`docker-volumes`, `media`, `backups`, etc.) devem estar agora acessíveis em `/data/` no novo host.
    *   **Opção 2: Restaurar Dados ZFS de um Backup (Se não puder mover os HDDs):**
        1.  No novo host Proxmox, crie um novo pool ZFS `data` com os novos HDDs, como na [Seção 2.2](../01-manual-implementacao/02-proxmox-ve-host.md#22-configuração-do-pool-zfs-data-e-datasets).
        2.  Crie os datasets ZFS (`data/docker-volumes`, `data/media`, `data/backups`, etc.) dentro do novo pool.
        3.  Restaure o conteúdo de cada dataset a partir do seu backup externo (Borg, rsync, HD externo) para os respectivos pontos de montagem no novo pool. Isso pode levar tempo.

4.  **Configurar Storage de Backup no Novo Proxmox:**
    *   Na UI web do novo Proxmox, vá em Datacenter -> Storage.
    *   Certifique-se de que existe um storage do tipo "Directory" apontando para o local onde seus backups de VMs estão (e.g., `/data/backups/vms`, que agora deve estar acessível no novo host). Adicione ou edite conforme necessário.

5.  **Restaurar as VMs no Novo Host Proxmox:**
    *   Usando a UI do Proxmox, restaure suas VMs (`core-services-vm`, `ai-desktop-vm`) a partir dos arquivos de backup.
    *   **Crucial:** Restaure-as com os **mesmos VM IDs** que tinham no servidor antigo.
    *   Se você fez passthrough de PCI (GPU) no servidor antigo, **não** adicione essas configurações de PCI ainda. Faremos isso via Ansible após a VM ser restaurada.

6.  **Atualizar Configurações Ansible (se necessário):**
    *   Na sua máquina de controle Ansible:
        *   **Inventário (`ansible/inventories/home/hosts.ini`):**
            *   Se o IP do novo host Proxmox mudou, atualize `ansible_host` para `proxmox_main_host`.
            *   Verifique se os IPs das VMs restauradas ainda correspondem ao que está no inventário (geralmente sim, se a config de rede da VM foi via Cloud-Init com IP estático).
        *   **Passthrough de PCI (`ansible/playbooks/vm-deploy.yml`):**
            *   No novo host Proxmox, use `lspci -nn` para encontrar os **novos IDs PCI** da sua GPU (e outros dispositivos de passthrough).
            *   Atualize a seção `vm_host_pci_devices` no `vm-deploy.yml` para a `ai-desktop-vm` com os novos IDs.
        *   **Outras Variáveis:** Verifique `group_vars/all/main.yml` para quaisquer outras configurações que possam ser dependentes do hardware específico do host (raro, mas possível).

7.  **Executar Playbooks Ansible no Novo Host e VMs:**
    1.  **Preparar o Novo Host Proxmox para Ansible:**
        *   Crie o usuário Ansible (`proxmox_ansible_user`) no novo host Proxmox.
        *   Copie sua chave SSH pública para este usuário.
        *   Teste a conexão e sudo. (Como na [Seção 2.3](../01-manual-implementacao/02-proxmox-ve-host.md#ações-manuais-prévias-no-host-proxmox-importante)).
    2.  **Executar Playbook para o Host Proxmox:**
        ```bash
        ansible-playbook ansible/playbooks/setup-proxmox-host.yml --ask-vault-pass
        ```
        Isso reconfigurará o NFS, firewall, etc., no novo host.
    3.  **Executar Playbook para as VMs (incluindo `vm-deploy.yml` se fez mudanças nos IDs PCI):**
        ```bash
        # Primeiro, para aplicar as configurações de passthrough e outros ajustes nas VMs
        ansible-playbook ansible/playbooks/vm-deploy.yml --ask-vault-pass
        # Depois, para garantir que a base das VMs está correta
        ansible-playbook ansible/playbooks/setup-base-ubuntu.yml --ask-vault-pass
        # E a stack de rede
        ansible-playbook ansible/playbooks/setup-core-networking.yml --ask-vault-pass
        # E os playbooks de preparação de volumes para as stacks Docker
        ansible-playbook ansible/playbooks/setup-media-stack-volumes.yml --ask-vault-pass
        # ... e os outros setup-<stack>-volumes.yml
        ```
        Ou, de forma mais simples, execute o playbook mestre se ele estiver bem configurado para ser idempotente:
        ```bash
        bash scripts/restore.sh
        ```

8.  **Verificar Stacks Docker no Portainer:**
    *   Acesse o Portainer.
    *   As stacks devem estar lá (pois a config do Portainer está em `/data/docker-volumes/portainer/data`).
    *   Pode ser necessário reiniciar algumas stacks ou verificar se os IPs internos e configurações de rede ainda estão corretos. Se os IPs das VMs mudaram e algum serviço Docker referenciava esses IPs diretamente (o que deve ser evitado), isso precisará ser atualizado.

9.  **Testar Tudo Exaustivamente.**

## B. Mudança de Esquema de Endereçamento IP da Rede Local

Se você mudar seu roteador, provedor de internet, ou simplesmente decidir reorganizar sua sub-rede local (e.g., de `192.168.1.0/24` para `192.168.50.0/24`).

**Onde as Atualizações de IP são Necessárias:**

1.  **Host Proxmox VE:**
    *   Arquivo `/etc/network/interfaces` (para o IP estático da bridge `vmbr0` e gateway).
    *   Pode ser necessário reiniciar os serviços de rede ou o host.
2.  **Inventário Ansible (`ansible/inventories/home/hosts.ini`):**
    *   Atualize `ansible_host` para `proxmox_main_host`.
    *   Atualize `ansible_host` para `core-services-vm` e `ai-desktop-vm`.
    *   Atualize as variáveis `*_ip_var` (e.g., `proxmox_host_ip_var`).
3.  **Variáveis Ansible (`ansible/inventories/home/group_vars/all/main.yml`):**
    *   `vm_cloud_init_gateway` (novo IP do roteador/gateway).
    *   `proxmox_ssh_allowed_cidrs`, `proxmox_web_ui_allowed_cidrs` (novo CIDR da sua LAN).
    *   `vm_nfs_allowed_clients_cidr` (novo CIDR da sua sub-rede de VMs).
4.  **Configuração de Rede das VMs:**
    *   As VMs foram configuradas com IPs estáticos via Cloud-Init (usando `vm_ipconfig` no `vm-deploy.yml`). Seus IPs, gateways e DNS precisam ser atualizados.
    *   **Opção 1: Re-provisionar com Ansible (Mais Limpo):** Se as VMs puderem ser recriadas (assumindo que os dados estão nos volumes NFS e os backups de VM estão OK), você pode simplesmente atualizar as variáveis de IP no Ansible e rodar `vm-deploy.yml` novamente após deletar as VMs antigas. **CUIDADO: ISSO APAGA AS VMS EXISTENTES.**
    *   **Opção 2: Atualizar Manualmente ou com Playbook Ansible Específico:**
        *   Conecte-se a cada VM via console Proxmox (se SSH não estiver acessível com o novo IP).
        *   Edite a configuração de rede (e.g., Netplan em `/etc/netplan/50-cloud-init.yaml` ou similar).
        *   Aplique a configuração: `sudo netplan apply`.
        *   Alternativamente, crie um playbook Ansible para modificar os arquivos Netplan e aplicar as mudanças.
5.  **Configurações de Firewall (PVE e UFW):**
    *   Atualize as regras que especificam CIDRs da rede local nos playbooks Ansible (`setup-proxmox-host.yml` para PVE Firewall, `setup-base-ubuntu.yml` para UFW nas VMs) e reaplique.
6.  **Configurações de Aplicações Específicas (Raro):**
    *   Se alguma aplicação Docker foi configurada para usar IPs fixos em vez de nomes de serviço Docker ou DNS, ela precisará ser atualizada.
    *   O Traefik File Provider (`dynamic_rag_services.yml.j2`) usa `{{ ai_desktop_vm_ip_var }}`. Se este IP mudar e for gerenciado pelo inventário, o Ansible atualizará o arquivo dinâmico do Traefik.
7.  **Cloudflare DNS/Tunnel:** Geralmente não precisa de mudanças, pois aponta para o túnel, não para IPs locais específicos, a menos que você tenha IPs fixos em alguma configuração avançada do túnel.

**Ordem Recomendada para Mudança de IP:**

1.  **Planeje os Novos IPs.**
2.  **Faça Backup de Tudo.**
3.  **Atualize as Configurações Ansible:** Inventário, `main.yml`.
4.  **Atualize a Configuração de Rede do Host Proxmox:** Mude o IP e gateway em `/etc/network/interfaces`. Reinicie a rede (`systemctl restart networking`) ou o host. Verifique se o host está acessível com o novo IP.
5.  **Atualize as Configurações de Rede das VMs:** Use o método escolhido (re-provisionar ou atualizar manualmente/via Ansible). Verifique se as VMs estão acessíveis com seus novos IPs.
6.  **Execute os Playbooks Ansible Relevantes:**
    *   `setup-proxmox-host.yml` (para atualizar firewall PVE, NFS exports se CIDR mudou).
    *   `setup-base-ubuntu.yml` (para atualizar UFW nas VMs).
    *   `setup-core-networking.yml` (para garantir que Traefik e outros serviços de rede estão OK, especialmente se o IP da `core-services-vm` mudou e é referenciado em algum lugar).
7.  **Teste Toda a Conectividade e Serviços.**

Migrações e mudanças de rede podem ser complexas. Planeje cuidadosamente, faça backups e teste cada etapa.