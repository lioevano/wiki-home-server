# Adaptando a Infraestrutura para Novo Hardware ou Mudanças de Rede

Com o tempo, você pode precisar migrar seu servidor doméstico para um novo hardware físico ou adaptar sua configuração a mudanças na sua rede local (como um novo roteador ou um novo esquema de endereçamento IP). Este guia aborda essas duas situações.

## A. Migração para Novo Servidor Físico (Novo Host Proxmox)

Mover toda a sua configuração Proxmox e VMs para uma nova máquina física é uma tarefa significativa, mas totalmente viável com planejamento e o uso da sua infraestrutura como código (Ansible).

**Considerações Prévias Antes da Migração:**

*   **Compatibilidade de Hardware do Novo Servidor:**
    *   **CPU:** Deve suportar virtualização (AMD-V para AMD, Intel VT-x para Intel) e IOMMU (AMD-Vi ou Intel VT-d) se você utiliza passthrough de dispositivos PCI (como a GPU).
    *   **RAM:** Idealmente, o novo servidor deve ter uma quantidade de RAM igual ou superior à do servidor antigo. Se for menor, você precisará reavaliar a alocação de RAM para suas VMs.
    *   **Armazenamento:**
        *   Espaço suficiente para o sistema operacional Proxmox VE no disco de sistema (SSD NVMe).
        *   Conectores e espaço físico para os HDDs do seu pool ZFS `/data` (se for movê-los) ou para novos HDDs se for recriar o pool e restaurar os dados.
    *   **Rede:** Pelo menos uma porta Ethernet Gigabit.
*   **IDs de Dispositivos PCI:** Se você usa passthrough de GPU ou outros dispositivos PCI, os IDs PCI desses dispositivos no novo hardware **serão diferentes**. Você precisará:
    1.  Identificar os novos IDs PCI no novo host Proxmox usando `lspci -nn`.
    2.  Atualizar as configurações de passthrough nas definições das VMs no Proxmox (geralmente feito via Ansible no playbook `vm-deploy.yml`).
*   **Nomes de Interfaces de Rede:** O nome da interface de rede principal no novo host Proxmox pode ser diferente do antigo (e.g., `enp3s0` em vez de `eno1`). Isso afetará a configuração da bridge `vmbr0` no arquivo `/etc/network/interfaces` do novo host.

**Processo de Migração Sugerido:**

1.  **BACKUP COMPLETO DO SERVIDOR ANTIGO:**
    *   !!! critical "Passo Mais Importante!"
        Antes de qualquer coisa, garanta que você tem backups completos e testados de:
        *   **VMs Proxmox:** Usando o sistema de backup integrado do Proxmox.
        *   **Dados do Pool ZFS `/data`:** Backups dos seus datasets (`docker-volumes`, `media`, `downloads`, `rag_sources`, `backups`) usando Borg, rsync, ou outra ferramenta para um destino externo.
        *   **Configurações do Host Proxmox Antigo:** O script `backup_proxmox_host_config.sh` (ou similar) para `/etc/`.
        *   **Repositório Ansible `infra-servidor-domestico`:** Certifique-se de que todas as suas configurações Ansible estão commitadas e enviadas para um repositório Git remoto.
        *   **Senha do Ansible Vault:** Tenha-a em local seguro.

2.  **Setup Inicial do Novo Servidor Físico:**
    *   Instale o Proxmox VE no SSD NVMe do novo servidor, seguindo a [Seção 2.1 do Manual de Implementação](../01-manual-implementacao/02-proxmox-ve-host.md#21-instalação-do-proxmox-ve-no-servidor-físico).
    *   **Configuração de Rede do Novo Host:** Durante a instalação, configure a rede do novo host Proxmox.
        *   **Idealmente:** Use o **mesmo endereço IP estático** que o servidor Proxmox antigo usava. Isso minimiza a quantidade de alterações necessárias no Ansible e em outras configurações.
        *   **Se não for possível usar o mesmo IP:** Anote o novo IP estático. Você precisará atualizar o inventário Ansible (`ansible_host` para `proxmox_main_host`).

3.  **Migração do Pool ZFS `/data`:**
    Este pool contém os dados das suas aplicações Docker e os backups das VMs.

    *   **Opção 1: Mover Fisicamente os HDDs do Pool ZFS (Recomendado se os HDDs são compatíveis e saudáveis):**
        1.  Desligue ambos os servidores completamente.
        2.  Com cuidado, remova os HDDs que compõem o pool `data` do servidor antigo.
        3.  Instale esses mesmos HDDs no novo servidor, conectando-os corretamente.
        4.  Inicie o novo servidor Proxmox.
        5.  No shell do novo host Proxmox, importe o pool ZFS:
            ```bash
            sudo zpool import
            # Este comando deve listar pools importáveis. Se 'data' aparecer:
            sudo zpool import -f data
            # O -f pode ser necessário se o pool não foi exportado "limpamente".
            ```
        6.  Verifique o status: `sudo zpool status data`. Se `ONLINE`, seus datasets (`/data/docker-volumes`, etc.) devem estar acessíveis.
    *   **Opção 2: Recriar o Pool e Restaurar Dados de um Backup (Se não puder mover os HDDs ou se os HDDs forem novos):**
        1.  No novo host Proxmox, crie um novo pool ZFS `data` com os HDDs disponíveis, como detalhado na [Seção 2.2](../01-manual-implementacao/02-proxmox-ve-host.md#22-configuração-do-pool-zfs-data-e-datasets).
        2.  Crie os datasets ZFS principais (`data/docker-volumes`, `data/media`, `data/backups`, etc.) dentro do novo pool.
        3.  Restaure o conteúdo de cada dataset a partir do seu backup externo (Borg, rsync, HD externo) para os respectivos pontos de montagem no novo pool (e.g., restaurar o conteúdo de `docker-volumes` para `/data/docker-volumes`). Este processo pode ser demorado dependendo do volume de dados.

4.  **Configurar Storage de Backup no Novo Proxmox:**
    *   Na UI web do novo Proxmox, vá em Datacenter -> Storage.
    *   Certifique-se de que existe um storage do tipo "Directory" configurado para apontar para o local onde seus arquivos de backup de VMs estão armazenados (e.g., `/data/backups/vms`, que agora deve estar acessível no novo host). Se necessário, "Add" ou "Edit" o storage. O conteúdo deve ser "VZDump backup file".

5.  **Restaurar as VMs no Novo Host Proxmox:**
    *   Usando a UI do Proxmox (selecionando o storage de backup), restaure suas VMs (`core-services-vm`, `ai-desktop-vm`) a partir dos arquivos de backup.
    *   !!! critical "Manter os Mesmos VM IDs"
        Ao restaurar, é **altamente recomendável** usar os **mesmos VM IDs** que as VMs tinham no servidor antigo (e.g., 100 para `core-services-vm`, 101 para `ai-desktop-vm`). Isso garante que o inventário Ansible e as configurações que podem depender de IDs (raro, mas possível) continuem válidas.
    *   Se você usava passthrough de PCI (GPU) no servidor antigo, **não** configure o passthrough de PCI na UI ao restaurar a VM. O Ansible cuidará disso com os novos IDs PCI.

6.  **Atualizar Configurações Ansible (na Máquina de Controle):**
    *   **Inventário (`ansible/inventories/home/hosts.ini`):**
        *   Se o IP do novo host Proxmox mudou, atualize o valor de `ansible_host` para `proxmox_main_host`.
        *   Confirme se os IPs das VMs (definidos em `ansible_host` para `core-services-vm` e `ai-desktop-vm`) ainda são os que você deseja que elas usem. Como as VMs foram restauradas, elas podem tentar obter o IP antigo via config Cloud-Init. O Ansible pode ajudar a reforçar o IP correto.
    *   **Passthrough de PCI (`ansible/playbooks/vm-deploy.yml`):**
        1.  No novo host Proxmox, use `lspci -nn` para encontrar os **novos IDs PCI** da sua GPU RX 5600XT (e quaisquer outros dispositivos de passthrough).
        2.  Edite o playbook `ansible/playbooks/vm-deploy.yml`. Na seção de deploy da `ai-desktop-vm`, atualize a lista `vm_host_pci_devices` com os **novos IDs PCI** corretos.
    *   **Outras Variáveis:** Revise `ansible/inventories/home/group_vars/all/main.yml` para quaisquer outras configurações que possam ser dependentes do hardware específico do host (e.g., nomes de interface de rede se referenciados, mas geralmente `vmbr0` é consistente).

7.  **Executar Playbooks Ansible para Configurar o Novo Ambiente:**
    1.  **Preparar o Novo Host Proxmox para Ansible:**
        *   Crie o usuário Ansible (`{{ proxmox_ansible_user_on_host }}`) no novo host Proxmox.
        *   Copie sua chave SSH pública (`~/.ssh/id_ed25519_homelab.pub`) para este usuário no novo host.
        *   Teste a conexão SSH e as permissões sudo (como na [Seção 2.3 do Manual](../01-manual-implementacao/02-proxmox-ve-host.md#ações-manuais-prévias-no-host-proxmox-importante)).
    2.  **Executar o Playbook `full-deploy.yml` (ou playbooks individuais em sequência):**
        Na sua máquina de controle Ansible, execute:
        ```bash
        bash scripts/restore.sh # Ou use --vault-password-file
        # OU
        # ansible-playbook ansible/playbooks/full-deploy.yml --ask-vault-pass
        ```
        Isto irá:
        *   Configurar o novo host Proxmox (NFS, firewall, Node Exporter, etc.).
        *   Aplicar configurações às VMs restauradas (incluindo as novas configurações de passthrough de PCI, se aplicável).
        *   Garantir que Docker, Portainer, cliente NFS, etc., estejam corretamente configurados nas VMs.
        *   Preparar os arquivos `.env` e diretórios para as stacks Docker.

8.  **Verificar e (Re)Implantar Stacks Docker no Portainer:**
    *   Acesse o Portainer na `core-services-vm` (e.g., `https://portainer.{{ base_domain }}`).
    *   Os dados de configuração do Portainer em si (localizados em `/data/docker-volumes/portainer/data`) devem ter sido migrados com o pool ZFS.
    *   Verifique se suas stacks estão listadas.
    *   Pode ser necessário:
        *   "Update the stack" para alguns ou todos os serviços para garantir que estão usando as configurações corretas, especialmente se IPs de VMs ou outras referências ambientais mudaram e são refletidas nos arquivos `.env` atualizados pelo Ansible.
        *   Se os dados dos volumes das aplicações foram restaurados corretamente, as aplicações devem iniciar com seus dados e configurações.
        *   Se você teve que restaurar dumps de banco de dados separadamente (em vez de apenas o volume ZFS do DB), faça isso agora.

9.  **Testar Tudo Exaustivamente:**
    *   Verifique o acesso a todos os serviços.
    *   Teste funcionalidades críticas (login, upload/download no Nextcloud, playback no Plex/Jellyfin, automações no Home Assistant, queries no Grafana).
    *   Verifique o GPU passthrough na `ai-desktop-vm` se aplicável.

## B. Mudança de Esquema de Endereçamento IP da Rede Local

Se você precisar alterar o esquema de IP da sua rede doméstica (e.g., mudar de `192.168.1.0/24` para `10.0.10.0/24`).

**Locais Chave para Atualizar Endereços IP:**

1.  **Roteador Doméstico:** Configure o novo range de IP, servidor DHCP (se usado para atribuição inicial), e o novo IP do gateway.
2.  **Host Proxmox VE:**
    *   Arquivo `/etc/network/interfaces`: Atualize o endereço IP estático da bridge `vmbr0`, a máscara de rede e o gateway.
    *   Reinicie os serviços de rede (`sudo systemctl restart networking`) ou o host Proxmox.
3.  **Inventário Ansible (`ansible/inventories/home/hosts.ini`):**
    *   Atualize `ansible_host` para `proxmox_main_host` com o novo IP do Proxmox.
    *   Atualize `ansible_host` para `core-services-vm` e `ai-desktop-vm` com seus novos IPs planejados.
    *   Atualize as variáveis de referência `*_ip_var` (e.g., `proxmox_host_ip_var`).
4.  **Variáveis Ansible (`ansible/inventories/home/group_vars/all/main.yml`):**
    *   `vm_cloud_init_gateway`: Novo IP do seu roteador/gateway.
    *   `proxmox_ssh_allowed_cidrs`, `proxmox_web_ui_allowed_cidrs`: Novo CIDR da sua LAN (e.g., `10.0.10.0/24`).
    *   `vm_nfs_allowed_clients_cidr`: Novo CIDR da sua sub-rede de VMs (e.g., `10.0.10.0/24`).
5.  **Configuração de Rede das Máquinas Virtuais:**
    As VMs foram configuradas com IPs estáticos via Cloud-Init, usando a variável `vm_ipconfig` no playbook `vm-deploy.yml`. Esta variável usa `hostvars[VM_NAME]['ansible_host']` do inventário.
    *   Após atualizar os IPs no inventário (`hosts.ini`), executar novamente o playbook `vm-deploy.yml` *deveria* (se o módulo `proxmox_kvm` conseguir atualizar a config de rede de uma VM em execução ou parada) aplicar a nova configuração de IP via Cloud-Init no próximo boot da VM.
    *   **Se a atualização via `vm-deploy.yml` não for suficiente:**
        1.  Conecte-se a cada VM via console Proxmox (pois o SSH com o IP antigo não funcionará).
        2.  Edite a configuração de rede da VM. Para Ubuntu com Netplan, edite o arquivo YAML em `/etc/netplan/` (geralmente `50-cloud-init.yaml` ou similar). Atualize o endereço IP, gateway e DNS.
        3.  Aplique a nova configuração de rede: `sudo netplan apply`.
        4.  Reinicie a VM se necessário.
6.  **Configurações de Firewall (PVE e UFW):**
    *   O Ansible (playbooks `setup-proxmox-host.yml` e `setup-base-ubuntu.yml`) usa as variáveis `proxmox_*_allowed_cidrs` e `vm_nfs_allowed_clients_cidr`. Após atualizar essas variáveis, re-executar esses playbooks atualizará as regras de firewall para permitir os novos CIDRs.
7.  **Configurações de Aplicações Específicas (Menos Comum):**
    *   Verifique se alguma aplicação Docker foi configurada para usar IPs fixos em vez de nomes de serviço Docker ou DNS. Isso deve ser evitado.
    *   O Traefik File Provider para `rag_services.yml` usa `{{ ai_desktop_vm_ip_var }}`. Como esta variável vem do inventário, ela será atualizada automaticamente quando o Ansible gerar o arquivo dinâmico do Traefik.
8.  **Cloudflare DNS/Tunnel:** Geralmente **não** precisa de mudanças, pois o Cloudflare Tunnel estabelece uma conexão de saída e não depende diretamente dos IPs da sua LAN para o acesso externo.

**Ordem Recomendada para Mudança de Esquema de IP:**

1.  **Planeje os Novos IPs** para o host Proxmox e todas as VMs.
2.  **Faça Backup Completo de Tudo** antes de iniciar.
3.  **Atualize as Configurações Ansible:** Modifique `hosts.ini` e `group_vars/all/main.yml` com os novos IPs e CIDRs.
4.  **Atualize a Configuração de Rede do Host Proxmox:**
    *   Edite `/etc/network/interfaces` no host Proxmox.
    *   Reinicie a rede do host (`sudo systemctl restart networking`) ou reinicie o host Proxmox.
    *   Verifique se o host Proxmox está acessível na rede com seu novo IP.
5.  **Atualize as Configurações de Rede das VMs:**
    *   Tente primeiro executar `ansible-playbook ansible/playbooks/vm-deploy.yml --ask-vault-pass`. Verifique se as VMs pegam os novos IPs após um reboot.
    *   Se não, atualize manualmente via console Proxmox e `netplan apply` em cada VM.
6.  **Execute os Playbooks Ansible para Sincronizar o Resto:**
    Rode `bash scripts/restore.sh` (ou o `full-deploy.yml`) para que o Ansible atualize todas as outras configurações que dependem dos novos IPs/CIDRs (firewalls, configs NFS, etc.).
7.  **Teste Toda a Conectividade e Serviços:** Verifique o acesso local e externo a todos os seus serviços.

Migrações e mudanças de rede são operações delicadas. Prossiga com cautela, verifique cada passo e tenha backups prontos para reverter se algo der errado.