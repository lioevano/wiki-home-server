---
description: "Como adaptar a infraestrutura a um novo hardware ou a mudanças de rede (novo IP, sub-rede ou roteador)."
---

# Adaptando a Infraestrutura para Novo Hardware ou Mudanças de Rede

Com o tempo, você pode se deparar com a necessidade de migrar seu servidor doméstico para um **novo hardware físico** ou de adaptar sua configuração existente a **mudanças significativas na sua rede local**, como um novo roteador que impõe um esquema de endereçamento IP diferente.

Este guia aborda as principais considerações e os passos envolvidos nesses dois cenários, sempre com o objetivo de minimizar o downtime e manter a consistência da sua Infraestrutura como Código (IaC) gerenciada pelo Ansible.

## A. Migração para Novo Servidor Físico (Novo Host Proxmox)

Mover toda a sua configuração Proxmox VE, juntamente com suas máquinas virtuais (VMs) e dados, para uma nova máquina física é uma tarefa complexa, mas totalmente viável com planejamento cuidadoso e o poder da sua configuração Ansible.

**Considerações Prévias Essenciais Antes da Migração:**

1.  **Compatibilidade de Hardware do Novo Servidor:**
    *   **CPU:** Deve suportar virtualização (AMD-V para processadores AMD, Intel VT-x para Intel) e, crucialmente, IOMMU (AMD-Vi ou Intel VT-d) se você utiliza ou planeja utilizar passthrough de dispositivos PCI (como a sua GPU RX 5600XT).
    *   **RAM:** Idealmente, o novo servidor deve ter uma quantidade de RAM igual ou superior à do servidor antigo. Se for menor, você precisará reavaliar e possivelmente reduzir a alocação de RAM para suas VMs.
    *   **Armazenamento:**
        *   Um SSD (preferencialmente NVMe) com capacidade suficiente para o sistema operacional Proxmox VE e os discos virtuais das suas VMs.
        *   Conectores SATA/SAS e espaço físico para os HDDs do seu pool ZFS `/data` (se você planeja movê-los fisicamente) ou para novos HDDs se for recriar o pool e restaurar os dados a partir de um backup.
    *   **Rede:** Pelo menos uma porta Ethernet Gigabit. Se você usa VLANs ou bonding no Proxmox, garanta que o novo hardware de rede suporte isso.
2.  **IDs de Dispositivos PCI (para Passthrough):**
    Se você usa passthrough de GPU (para a `ai-desktop-vm`) ou quaisquer outros dispositivos PCI (placas de rede dedicadas, controladoras HBA), os **IDs PCI desses dispositivos no novo hardware serão diferentes**. Você precisará:
    1.  Identificar os novos IDs PCI no novo host Proxmox usando o comando `lspci -nn` após a instalação básica do Proxmox.
    2.  Atualizar as configurações de passthrough nas definições das suas VMs. Isso é feito no seu playbook Ansible `vm-deploy.yml` (na variável `vm_host_pci_devices`).
3.  **Nomes de Interfaces de Rede Físicas:**
    O nome da interface de rede principal no novo host Proxmox pode ser diferente do antigo (e.g., `enp3s0` em vez de `eno1`). Isso afetará a configuração da bridge `vmbr0` no arquivo `/etc/network/interfaces` do novo host Proxmox. Esteja preparado para ajustar isso durante a instalação do Proxmox ou via Ansible.

**Processo de Migração Sugerido para Novo Hardware:**

1.  **BACKUP COMPLETO E VERIFICADO DO SERVIDOR ANTIGO:**
    *   !!! critical "Este é o Passo Mais Importante e Não Pode Ser Ignorado!"
        Antes de iniciar qualquer migração:
        *   Garanta que você tem **backups completos e recentes de todas as suas VMs Proxmox**, salvos em um local acessível (idealmente no seu pool `/data/backups/vms` e também uma cópia off-site). Verifique se os backups foram concluídos com sucesso.
        *   Faça um **backup completo dos seus dados do pool ZFS `/data`** (que contém `docker-volumes`, `media`, `photos`, `files`, `notes`, etc.). A melhor forma é usar [BorgBackup](../04-manutencao-recuperacao/02-backup-restore-estrategia.md#b-volumes-de-arquivos-configs-docker-mídia-modelos-rag) para um destino externo. Se não usa Borg, pelo menos `rsync` para um HD externo. Dumps de banco de dados também devem estar incluídos ou feitos separadamente.
        *   Faça um backup da [configuração do seu host Proxmox antigo](../04-manutencao-recuperacao/02-backup-restore-estrategia.md#1-configuração-do-host-proxmox-ve) (arquivos de `/etc/`).
        *   Certifique-se de que seu **repositório `homeserver` está totalmente atualizado e enviado (`pushed`) para seu Git remote** (GitHub, GitLab, etc.).
        *   Tenha sua **senha do Ansible Vault** em local seguro.
        *   **Teste a restauração de uma VM e de alguns dados importantes de seus backups em um ambiente de teste, se possível, ANTES da migração.**

2.  **Setup Inicial do Novo Servidor Físico com Proxmox VE:**
    *   No novo hardware, instale o Proxmox VE no SSD NVMe, seguindo os passos da [**Seção 2.1 do Manual de Implementação**](../01-manual-implementacao/02-proxmox-ve-host.md#21-instalação-do-proxmox-ve-no-servidor-físico).
    *   **Configuração de Rede do Novo Host Proxmox:**
        *   Durante a instalação, configure a rede do novo host Proxmox. **Idealmente, e para simplificar MUITO a migração, tente usar o mesmo endereço IP estático, hostname e configurações de gateway/DNS que o servidor Proxmox antigo usava.**
        *   Se não for possível usar o mesmo IP, anote cuidadosamente o novo IP estático. Você precisará atualizar o inventário Ansible (`ansible_host` para `proxmox_main_host`) e potencialmente outras configurações que referenciem o IP do host Proxmox.

3.  **Migração do Pool ZFS `/data` (Contendo Dados de Aplicações e Backups de VMs):**
    Este pool é crucial. Você tem duas opções principais:

    *   **Opção A: Mover Fisicamente os HDDs do Pool ZFS Antigo para o Novo Servidor (Mais Rápido e Simples se os HDDs são compatíveis e saudáveis):**
        1.  Desligue ambos os servidores completamente e desconecte-os da energia.
        2.  Com cuidado, remova os HDDs que compõem o pool ZFS `/data` do servidor antigo.
        3.  Instale esses mesmos HDDs no novo servidor, conectando-os corretamente aos cabos SATA e de energia.
        4.  Inicie o novo servidor Proxmox.
        5.  No shell do novo host Proxmox (como `root`), importe o pool ZFS:
            ```bash
            sudo zpool import
            # Este comando deve listar pools ZFS que podem ser importados. Se seu pool 'data' aparecer:
            sudo zpool import -f data
            # A flag -f (force) pode ser necessária se o pool não foi exportado "limpamente"
            # do sistema antigo, o que é provável se você apenas desligou o servidor antigo.
            ```
        6.  Verifique o status do pool importado: `sudo zpool status data`. Se o estado for `ONLINE`, seus datasets (como `/data/docker-volumes`, `/data/media`, `/data/backups/vms`) devem estar acessíveis nos seus pontos de montagem usuais.
    *   **Opção B: Recriar o Pool ZFS no Novo Servidor e Restaurar os Dados de um Backup Externo (Se não puder mover os HDDs, ou se os HDDs do novo servidor forem diferentes/novos):**
        1.  No novo host Proxmox, crie um novo pool ZFS `data` com os HDDs disponíveis no novo servidor, seguindo os passos da [**Seção 2.2 do Manual de Implementação**](../01-manual-implementacao/02-proxmox-ve-host.md#22-configuração-do-pool-zfs-data-e-datasets). Use o mesmo nome de pool (`data`) e os mesmos nomes de datasets (`data/docker-volumes`, `data/media`, `data/backups`, etc.).
        2.  Agora, **restaure o conteúdo de cada dataset** a partir do seu backup externo (Borg, rsync de um HD externo, etc.) para os respectivos pontos de montagem no novo pool ZFS (e.g., restaure o conteúdo de `docker-volumes` do seu backup para `/data/docker-volumes` no novo servidor). Este processo pode ser bastante demorado, dependendo do volume de dados e da velocidade do seu backup/rede.

4.  **Configurar o Storage de Backup de VMs no Novo Proxmox:**
    *   Na interface web do novo Proxmox VE, vá para **Datacenter -> Storage**.
    *   Certifique-se de que existe um storage do tipo "**Directory**" configurado para apontar para o local onde seus arquivos de backup de VMs estão armazenados (e.g., `/data/backups/vms`, que agora deve estar acessível no novo host). Se necessário, "Add" ou "Edit" o storage. O campo "Content" deve ter **"VZDump backup file" selecionado**.

5.  **Restaurar Suas Máquinas Virtuais (VMs) no Novo Host Proxmox:**
    *   Usando a interface web do Proxmox, selecione o storage de backup que você acabou de configurar.
    *   A aba "**Backups**" listará os arquivos de backup de VM disponíveis.
    *   Para cada VM que você precisa restaurar (e.g., `core-services-vm`, `ai-desktop-vm`):
        1.  Selecione o arquivo de backup mais recente e apropriado.
        2.  Clique no botão "**Restore**".
        3.  !!! critical "Manter os Mesmos VM IDs ao Restaurar!"
            Ao restaurar, é **extremamente importante** que você use os **mesmos VM IDs** que as VMs tinham no servidor antigo (e.g., `100` para `core-services-vm`, `101` para `ai-desktop-vm`). Seu inventário Ansible (`hosts.ini`) e várias configurações gerenciadas pelo Ansible (como regras de firewall PVE, configurações Cloud-Init passadas pelo `proxmox-vm` role, etc.) dependem desses IDs. Se você for forçado a usar um novo VM ID, precisará atualizar cuidadosamente todas as referências a esse ID no seu código Ansible.
        4.  **Storage de Destino:** Escolha o storage onde o disco da VM restaurada será armazenado (e.g., `local-lvm` no seu novo SSD NVMe).
        5.  Outras opções de restauração: `MAC address` (geralmente "generate new" é seguro, a menos que você tenha reservas DHCP baseadas no MAC antigo); `Start after restore` (pode deixar desmarcado por enquanto, o Ansible cuidará de iniciar se necessário).
    *   Clique em "Restore". Monitore a tarefa na parte inferior da UI do Proxmox.
    *   **Não inicie as VMs ainda** após a restauração, a menos que o Ansible precise delas ligadas para alguma configuração inicial (o que não é o caso aqui para as tasks de `vm-deploy.yml` que ajustam hardware).

6.  **Atualizar Configurações Ansible (na sua Máquina de Controle Ansible):**
    *   **Inventário (`server/ansible/inventories/home/hosts.ini`):**
        *   Se o endereço IP do seu novo host Proxmox mudou, atualize o valor de `ansible_host` para `proxmox_main_host`.
        *   Confirme se os endereços IP das VMs (definidos em `ansible_host` para `core-services-vm` e `ai-desktop-vm`) ainda são os que você planeja que elas usem (e que seu roteador/DHCP está configurado para atribuí-los ou que a config Cloud-Init os definirá).
    *   **Passthrough de PCI (Playbook `vm-deploy.yml`):**
        1.  No novo host Proxmox, use o comando `lspci -nn` no shell para encontrar os **novos IDs PCI** da sua GPU AMD RX 5600XT (e quaisquer outros dispositivos de passthrough, como placas de rede). Lembre-se de pegar tanto o ID do dispositivo de vídeo quanto o do dispositivo de áudio da GPU.
        2.  Edite o arquivo `server/ansible/playbooks/vm-deploy.yml`. Na seção de deploy da `ai-desktop-vm` (ou qualquer outra VM que use passthrough), atualize a lista `vm_host_pci_devices` com os **novos IDs PCI corretos** do novo hardware.
    *   **Outras Variáveis Específicas do Host:** Revise `server/ansible/inventories/home/group_vars/all/main.yml` para quaisquer outras variáveis que possam ser dependentes do hardware específico do host (e.g., nomes de interface de rede se você os referenciou em algum lugar, embora o uso de `vmbr0` como padrão deva minimizar isso).

7.  **Executar os Playbooks Ansible para Configurar o Novo Ambiente:**
    1.  **Prepare o Novo Host Proxmox para ser Gerenciado pelo Ansible:**
        *   No shell do novo host Proxmox (como `root`), crie o usuário Ansible dedicado (`{{ proxmox_ansible_user_on_host }}` e.g., `proxmox_ansible_user`).
        *   Adicione-o ao grupo `sudo` e configure `NOPASSWD` para `sudo`.
        *   Na sua máquina de controle Ansible, copie sua chave SSH pública (`~/.ssh/id_ed25519_homelab.pub`) para este novo usuário no host Proxmox usando `ssh-copy-id`.
        *   Teste a conexão SSH e a capacidade de `sudo` sem senha.
        (Estes são os mesmos passos da [Seção 2.3: Ações Manuais Prévias](../01-manual-implementacao/02-proxmox-ve-host.md#ações-manuais-prévias-no-host-proxmox-essencial-para-ansible)).
    2.  **Execute o Playbook Mestre `full-deploy.yml` (ou o script `restore.sh`):**
        Na raiz do repositório, na máquina de controle Ansible (o `restore.sh` entra sozinho em `server/ansible`):
        ```bash
        bash server/scripts/restore.sh # Este script executa o full-deploy.yml e lida com a senha do vault
        # OU, se preferir executar diretamente:
        # cd server/ansible && ansible-playbook -i inventories/home/hosts.ini playbooks/full-deploy.yml --ask-vault-pass
        ```
        Isto irá:
        *   Configurar o novo host Proxmox (NFS, firewall, pacotes, Alloy, etc.).
        *   Aplicar/verificar as configurações das VMs restauradas (incluindo as novas configurações de passthrough de PCI).
        *   Configurar a base das VMs Ubuntu (cliente NFS, Docker, Portainer, etc.).
        *   Configurar a stack de rede core (Traefik, Cloudflared, Authelia).
        *   Preparar os diretórios e arquivos `.env` para as stacks Docker.

8.  **Verificar e (Re)Implantar/Atualizar Stacks Docker no Portainer:**
    *   Acesse sua instância Portainer (e.g., `https://portainer.seudominio.com`).
    *   Como os dados do volume `/data/docker-volumes/portainer/data` foram migrados com o pool ZFS, suas configurações de stacks, endpoints e usuários do Portainer **devem estar lá**.
    *   Navegue para "**Stacks**". Suas stacks devem estar listadas.
    *   Para cada stack, pode ser uma boa ideia:
        1.  Clicar na stack.
        2.  Ir para o "**Editor**".
        3.  Sem fazer alterações no compose (a menos que necessário), clique em "**Update the stack**". Marque "**Re-pull image and redeploy**" se quiser garantir que as imagens estão corretas ou se houve alguma mudança na configuração da VM que possa afetar os containers (como IPs, se referenciados incorretamente).
        *   Isso força o Portainer a reconciliar o estado da stack com sua definição e com os arquivos `.env` que o Ansible pode ter recriado/atualizado.
    *   **Dados das Aplicações:** Como o conteúdo dos seus datasets ZFS (e.g., `/data/docker-volumes/nextcloud`, `/data/media`) foi migrado, suas aplicações Docker, ao serem reiniciadas com seus volumes corretamente mapeados, devem encontrar seus dados e configurações anteriores.
    *   **Restauração de Dumps de DB:** Se você optou por restaurar os dados do pool ZFS de um backup que não era o mais recente, e você tem dumps de banco de dados mais recentes, restaure esses dumps manualmente agora (conforme descrito na [Estratégia de Backup](02-backup-restore-estrategia.md#a-bancos-de-dados-das-aplicações-postgresql-para-authelia-nextcloud-grafana)).

9.  **Testar Tudo Exaustivamente:**
    *   Verifique o acesso a todos os seus serviços web através dos seus subdomínios.
    *   Teste a autenticação com Authelia.
    *   Verifique a funcionalidade de cada aplicação principal (Nextcloud, Jellyfin, Home Assistant, Grafana, etc.).
    *   Confirme que os dados estão presentes e corretos.
    *   Verifique os logs de todos os componentes (Proxmox, VMs, containers) por quaisquer novos erros ou avisos.
    *   Se você configurou GPU passthrough, teste-o na `ai-desktop-vm` (e.g., rodando Ollama com um modelo que use a GPU).

## B. Mudança de Esquema de Endereçamento IP da Rede Local

Se você precisar alterar o esquema de IP da sua rede doméstica (e.g., seu roteador mudou e agora usa uma sub-rede diferente, como `10.0.10.0/24` em vez de `192.168.15.0/24`).

**Locais Chave Onde os Endereços IP Precisam ser Atualizados:**

1.  **Roteador Doméstico:**
    *   Configure o novo range de IP, o servidor DHCP (se usado para outros dispositivos da sua LAN) e, o mais importante, o novo **endereço IP do gateway** (que é o próprio roteador).
2.  **Host Proxmox VE:**
    *   **Arquivo de Configuração de Rede:** Edite `/etc/network/interfaces` no host Proxmox.
        *   Atualize o `address`, `netmask` (ou CIDR), e `gateway` para a bridge `vmbr0` (sua interface de gerenciamento e LAN).
    *   **Serviço de Rede:** Reinicie o serviço de rede (`sudo systemctl restart networking`) ou, de forma mais segura, reinicie o host Proxmox.
        !!! warning "Acesso ao Host Proxmox Após Mudança de IP"
            Após mudar o IP do host Proxmox, você precisará usar o novo IP para acessá-lo via SSH ou interface web.
3.  **Inventário Ansible (`server/ansible/inventories/home/hosts.ini`):**
    *   Atualize o valor de `ansible_host` para `proxmox_main_host` com o novo IP do Proxmox.
    *   Atualize os valores de `ansible_host` para `core-services-vm` e `ai-desktop-vm` com os novos IPs estáticos que você planeja para elas na nova sub-rede.
    *   Atualize as variáveis de referência de IP no final do arquivo (e.g., `proxmox_host_ip_var`, `core_services_vm_ip_var`, `ai_desktop_vm_ip_var`).
4.  **Variáveis Globais Ansible (`server/ansible/inventories/home/group_vars/all/main.yml`):**
    *   `vm_cloud_init_gateway`: Atualize para o novo endereço IP do seu roteador/gateway.
    *   `proxmox_ssh_allowed_cidrs` e `proxmox_web_ui_allowed_cidrs`: Atualize para o novo CIDR da sua LAN (e.g., `10.0.10.0/24`).
    *   `vm_nfs_allowed_clients_cidr`: Atualize para o novo CIDR da sua sub-rede de VMs (geralmente o mesmo da LAN, e.g., `10.0.10.0/24`).
5.  **Configuração de Rede das Máquinas Virtuais (VMs):**
    As suas VMs (`core-services-vm`, `ai-desktop-vm`) foram configuradas com IPs estáticos através do Cloud-Init, usando a variável `vm_ipconfig` no playbook `vm-deploy.yml`. Esta variável, por sua vez, usa `hostvars[NOME_DA_VM]['ansible_host']` do inventário para definir o IP da VM.
    *   **Após atualizar os IPs no inventário Ansible (`hosts.ini`) e o `vm_cloud_init_gateway` em `main.yml`:**
        1.  **Execute o playbook `vm-deploy.yml`:**
            ```bash
            ansible-playbook -i inventories/home/hosts.ini playbooks/vm-deploy.yml --ask-vault-pass
            ```
            O módulo `community.proxmox.proxmox_kvm` tentará atualizar a configuração de Cloud-Init da VM. Para que a nova configuração de rede tenha efeito, a VM **precisará ser reiniciada**. O Ansible pode não forçar o reboot aqui, então você pode precisar fazer isso manualmente via UI do Proxmox ou `sudo reboot` dentro da VM.
        2.  **Verificação:** Após o reboot da VM, verifique se ela obteve o novo IP estático, gateway e DNS.
    *   **Se a atualização via `vm-deploy.yml` não for suficiente ou se você preferir fazer manualmente (menos recomendado para IaC):**
        1.  Conecte-se a cada VM via console Proxmox (já que o SSH com o IP antigo provavelmente não funcionará).
        2.  Edite o arquivo de configuração de rede. Para Ubuntu com Netplan, este é geralmente um arquivo YAML em `/etc/netplan/` (e.g., `50-cloud-init.yaml` ou similar). Atualize os campos `addresses`, `gateway4` (ou `gateway6`), e `nameservers`.
        3.  Aplique a nova configuração de rede: `sudo netplan apply`.
        4.  Reinicie a VM se necessário.
6.  **Configurações de Firewall (PVE Firewall no Host e UFW nas VMs):**
    *   Os playbooks Ansible (`setup-proxmox-host.yml` para PVE Firewall e `setup-base-ubuntu.yml` para UFW nas VMs) usam as variáveis `proxmox_*_allowed_cidrs` e `vm_nfs_allowed_clients_cidr`.
    *   Após você ter atualizado essas variáveis no seu `group_vars/all/main.yml`, **re-execute esses playbooks** para que o Ansible atualize as regras de firewall para permitir os novos CIDRs da sua rede.
        ```bash
        ansible-playbook -i inventories/home/hosts.ini playbooks/setup-proxmox-host.yml --ask-vault-pass
        ansible-playbook -i inventories/home/hosts.ini playbooks/setup-base-ubuntu.yml --ask-vault-pass
        ```
7.  **Configurações de Aplicações Específicas que Referenciam IPs (Raro, mas Verifique):**
    *   Idealmente, nenhuma das suas aplicações Docker deve ter sido configurada para usar IPs fixos da sua LAN diretamente em suas configurações. Elas devem usar nomes de serviço Docker para comunicação interna ou serem acessadas via Traefik/DNS para acesso externo.
    *   Os IPs das VMs aparecem em vários lugares, mas **todos vêm do inventário**: o `ansible_host` no `hosts.ini` e as variáveis `core_services_vm_ip_var`/`ai_desktop_vm_ip_var` do `main.yml`, que devem bater com ele. São eles:
        *   o roteamento do Traefik para a VM de IA (`dynamic_ai_services.yml.j2`);
        *   as portas publicadas só no IP da LAN (`CORE_SERVICES_VM_IP_VAR` e `AI_DESKTOP_VM_IP` nos `.env`);
        *   os `extra_hosts` de `auth.` e `nextcloud.`;
        *   o export NFS do `notes`;
        *   o UFW e o Alloy.
    *   Depois de mudar o inventário, rode o `full-deploy.yml` ([CI/CD](03-cicd-basico-ansible.md)) e cole os `.env` novos nas stacks do Portainer (**Update the stack**). Se o Claude Code usa a rota de controle do hub, refaça o `claude mcp add` com o IP novo.
8.  **Cloudflare DNS e Tunnel:**
    *   Geralmente, **não precisam de mudanças diretas** devido a uma alteração no esquema de IP da sua LAN. O Cloudflare Tunnel estabelece uma conexão de *saída* e não depende dos IPs internos da sua LAN para o acesso externo aos seus serviços (desde que o `cloudflared` agent e o Traefik consigam se comunicar dentro da VM).

**Ordem Geral Recomendada para Mudança de Esquema de IP:**

1.  **Planeje Cuidadosamente** os novos IPs para todos os dispositivos estáticos (host Proxmox, VMs).
2.  **Faça Backup COMPLETO de Tudo** antes de iniciar qualquer alteração.
3.  **Atualize as Configurações no seu Roteador Doméstico** (novo range de IP, DHCP, novo IP do gateway).
4.  **Atualize as Configurações Ansible:** Modifique `hosts.ini` e `group_vars/all/main.yml` com os novos IPs e CIDRs. Faça commit e push dessas mudanças no Git.
5.  **Atualize a Configuração de Rede do Host Proxmox VE:**
    *   Edite `/etc/network/interfaces` no host Proxmox.
    *   Reinicie os serviços de rede do host (`sudo systemctl restart networking`) ou, de forma mais segura, reinicie o host Proxmox.
    *   Verifique se o host Proxmox está acessível na rede com seu novo endereço IP.
6.  **Atualize as Configurações de Rede das Máquinas Virtuais:**
    *   Tente primeiro executar o playbook `ansible-playbook -i inventories/home/hosts.ini playbooks/vm-deploy.yml --ask-vault-pass`.
    *   Requisite um reboot das VMs após a execução do playbook para que as novas configurações de rede Cloud-Init tenham efeito.
    *   Verifique se as VMs estão acessíveis em seus novos IPs. Se não, ajuste manualmente via console Proxmox e `netplan apply`.
7.  **Execute os Playbooks Ansible para Sincronizar o Resto da Configuração:**
    Rode `bash server/scripts/restore.sh` (ou o `full-deploy.yml`) para que o Ansible atualize todas as outras configurações que dependem dos novos IPs/CIDRs (regras de firewall PVE, regras UFW nas VMs, configurações NFS, arquivos dinâmicos do Traefik, etc.).
8.  **Teste Toda a Conectividade e o Acesso a Todos os Serviços:** Verifique o acesso local e externo (via Cloudflare Tunnel) a todos os seus serviços. Verifique os logs por erros.

Migrações de hardware e mudanças de esquema de rede são operações significativas. Prossiga com cautela, divida o processo em etapas gerenciáveis, verifique cada etapa e, o mais importante, tenha backups confiáveis e testados para poder reverter se algo der muito errado. Sua Infraestrutura como Código com Ansible será uma aliada poderosa nesses processos.