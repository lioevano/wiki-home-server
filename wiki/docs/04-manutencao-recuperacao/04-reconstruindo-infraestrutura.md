---
description: "Como reconstruir a infraestrutura após falha grave do disco do sistema, usando Git, Ansible e o pool ZFS."
---

# Reconstruindo a Infraestrutura Após uma Falha Grave

Apesar de todos os nossos esforços de manutenção preventiva e redundância (como o pool ZFS `/data` em RAID 1), falhas de hardware catastróficas podem ocorrer. O cenário mais impactante seria a falha do seu SSD NVMe principal, que hospeda o sistema operacional Proxmox VE e os discos virtuais das suas máquinas virtuais. Outros cenários podem incluir corrupção irreparável do sistema operacional do host Proxmox ou um desastre físico que afete o servidor.

Este guia descreve os passos gerais para reconstruir sua infraestrutura base do zero, assumindo que você implementou e manteve a [Estratégia de Backup e Restauração](02-backup-restore-estrategia.md) e, portanto, possui:

1.  **Backups recentes e testados das suas Máquinas Virtuais Proxmox** (e.g., arquivos `.vma.zst` do sistema de backup integrado do Proxmox, armazenados no seu dataset ZFS `/data/backups/vms` ou em um backup off-site).
2.  **Backups dos seus dados persistentes de containers Docker:**
    *   Idealmente, um backup completo dos seus datasets ZFS `/data/docker-volumes`, `/data/media`, etc., feito com uma ferramenta como BorgBackup para um destino externo.
    *   No mínimo, dumps recentes dos seus bancos de dados importantes (Authelia, Nextcloud, Grafana) salvos no dataset `/data/backups/db_dumps` (ou em um backup off-site).
3.  **Seu repositório `homeserver` completo e atualizado**, com todas as configurações da sua infraestrutura, seguramente armazenado em um serviço Git remoto (e.g., GitHub, GitLab).
4.  **Acesso seguro à sua senha do Ansible Vault.**

!!! critical "A Importância dos Backups Off-Site"
    Se a falha grave afetar *todos* os discos do seu servidor Proxmox (incluindo os HDDs do pool `/data`), ter backups off-site (na nuvem, em um HD externo guardado em outro local) será sua única forma de recuperação completa. Este guia assume que você tem acesso a alguma forma de backup dos dados do pool `/data` se ele também for perdido.

## Cenário de Exemplo Considerado

Vamos focar no cenário onde o **SSD NVMe principal do seu servidor Proxmox falhou completamente**, mas seus HDDs do pool ZFS `/data` (que contêm os backups das VMs e, idealmente, os dados dos containers ou backups deles) **estão intactos e podem ser reutilizados**. Se os HDDs do pool `/data` também falharem, o processo será similar, mas a etapa de restauração dos dados dos datasets ZFS dependerá inteiramente dos seus backups off-site.

## Passos Detalhados para Reconstrução da Infraestrutura

Siga estes passos metodicamente:

1.  **Preparar Novo Hardware ou Substituir Componente Defeituoso:**
    *   Se o SSD NVMe falhou, substitua-o por um novo SSD NVMe de capacidade igual ou superior.
    *   Verifique todas as conexões de hardware (cabos SATA para os HDDs do pool ZFS, RAM, CPU, etc.) para garantir que estão firmes.

2.  **Instalar o Proxmox VE Base no Novo SSD:**
    *   Siga rigorosamente os passos da [**Seção 2.1: Instalação do Proxmox VE no Servidor Físico**](../01-manual-implementacao/02-proxmox-ve-host.md#21-instalação-do-proxmox-ve-no-servidor-físico) para instalar uma cópia limpa do Proxmox VE no novo SSD NVMe.
    *   **Configuração de Rede do Host:** Durante a instalação, configure a rede do novo host Proxmox com o **mesmo endereço IP estático** que o servidor Proxmox antigo usava (e.g., `192.168.15.10`). Isso simplificará enormemente a restauração das configurações Ansible e a conectividade.
    *   **Senha Root:** Você pode usar a mesma senha `root` que usava antes (se lembrar e estiver no seu Ansible Vault) ou definir uma nova. Se definir uma nova, lembre-se de atualizar a variável `proxmox_api_password` no seu Ansible Vault posteriormente.

3.  **Importar o Pool ZFS `/data` Existente (se os HDDs sobreviveram):**
    Se os HDDs que compunham seu pool `/data` estão intactos e foram reconectados ao novo sistema:
    1.  No shell do novo host Proxmox (como `root`), tente listar pools ZFS que podem ser importados:
        ```bash
        sudo zpool import
        ```
        Se o seu pool `data` aparecer na lista, ele está pronto para ser importado.
    2.  Importe o pool `data`:
        ```bash
        sudo zpool import -f data
        # A flag -f (force) pode ser necessária se o pool não foi exportado "limpamente"
        # do sistema antigo (o que é o caso se o SSD do SO falhou).
        ```
    3.  Verifique o status do pool importado:
        ```bash
        sudo zpool status data
        ```
        O estado deve ser `ONLINE`, e seus datasets (`docker-volumes`, `media`, `backups`, etc.) devem agora estar acessíveis nos seus pontos de montagem usuais (e.g., `/data/docker-volumes`).
    *   **Se os HDDs do pool `/data` foram perdidos e você precisa restaurar de um backup off-site:**
        1.  Crie um novo pool ZFS `data` com os novos HDDs (ou os antigos formatados) seguindo a [Seção 2.2](../01-manual-implementacao/02-proxmox-ve-host.md#22-configuração-do-pool-zfs-data-e-datasets).
        2.  Crie novamente os datasets ZFS principais (`data/docker-volumes`, `data/media`, `data/backups`, etc.).
        3.  **Restaure o conteúdo de cada dataset** a partir do seu backup off-site (Borg, rsync, etc.) para os respectivos pontos de montagem no novo pool (e.g., restaure o conteúdo de `docker-volumes` para `/data/docker-volumes`). Este será o passo mais demorado.

4.  **Configurar o Storage de Backup de VMs no Novo Proxmox:**
    *   Na interface web do novo Proxmox VE, vá para **Datacenter -> Storage**.
    *   Se o storage que aponta para o diretório onde seus backups de VMs estão (e.g., `/data/backups/vms`) não existir ou estiver com a configuração incorreta, você precisará **Adicionar** ou **Editar** um storage do tipo "**Directory**".
        *   **ID:** Dê um nome (e.g., `local_zfs_vmbackups`).
        *   **Directory:** Especifique o caminho absoluto no host Proxmox (e.g., `/data/backups/vms`).
        *   **Content:** Selecione **APENAS "VZDump backup file"**.
        *   Clique em "Add" ou "OK".

5.  **Restaurar Suas Máquinas Virtuais (VMs) a partir dos Backups:**
    *   Com o storage de backup configurado e os arquivos de backup das suas VMs (e.g., `.vma.zst`) presentes nele:
        1.  Na UI do Proxmox, selecione o **storage de backup** na árvore à esquerda.
        2.  A aba "**Backups**" listará os arquivos de backup de VM disponíveis.
        3.  Para cada VM que você precisa restaurar (`core-services-vm`, `ai-desktop-vm`):
            *   Selecione o arquivo de backup mais recente e apropriado.
            *   Clique no botão "**Restore**".
        4.  No diálogo "Restore":
            *   !!! critical "VM ID"
                É **extremamente importante** que você restaure as VMs com os **mesmos VM IDs** que elas tinham originalmente (e.g., `100` para `core-services-vm`, `101` para `ai-desktop-vm`). Seu inventário Ansible (`hosts.ini`) e potencialmente outras configurações (como as regras de firewall PVE no `setup-proxmox-host.yml`) dependem desses IDs. Se você não puder usar o mesmo ID por algum motivo, precisará atualizar cuidadosamente todas as referências a esse ID no seu código Ansible.
            *   **Storage:** Escolha o storage de destino para o disco da VM restaurada (e.g., `local-lvm` no seu novo SSD NVMe).
            *   Configure outras opções de restauração conforme necessário (e.g., `MAC address` - geralmente "generate new" é seguro, a menos que você tenha reservas DHCP baseadas no MAC antigo; `Start after restore` - pode deixar desmarcado por enquanto).
        5.  Clique em "**Restore**". Monitore a tarefa na parte inferior da UI do Proxmox.
    *   Após a restauração, **não inicie as VMs ainda**. O Ansible fará a configuração final.

6.  **Preparar sua Máquina de Controle Ansible e o Repositório:**
    *   Se sua máquina de controle Ansible original foi perdida ou não está configurada, prepare uma nova seguindo a [**Seção 1.1: Instalação do Ambiente de Controle (`scripts/bootstrap.sh`)**](../01-manual-implementacao/01-maquina-controle-ansible.md#11-instalação-do-ambiente-de-controle-scriptsbootstrapsh).
    *   Clone seu repositório `homeserver` do seu serviço Git remoto (GitHub, GitLab, etc.) para sua máquina de controle.
    *   Certifique-se de que você tem acesso à sua **senha do Ansible Vault**.

7.  **Executar os Playbooks Ansible para Reconfigurar a Infraestrutura:**
    Este é o passo onde a mágica da Infraestrutura como Código acontece!

    1.  **Preparar o Novo Host Proxmox para ser Gerenciado pelo Ansible:**
        *   No shell do novo host Proxmox (como `root`), crie o usuário Ansible dedicado (`{{ proxmox_ansible_user_on_host }}` e.g., `proxmox_ansible_user`).
        *   Adicione-o ao grupo `sudo` e configure `NOPASSWD` para `sudo` (conforme detalhado na [Seção 2.3: Ações Manuais Prévias](../01-manual-implementacao/02-proxmox-ve-host.md#ações-manuais-prévias-no-host-proxmox-essencial-para-ansible)).
        *   Na sua máquina de controle Ansible, copie sua chave SSH pública (`~/.ssh/id_ed25519_homelab.pub`) para este novo usuário no host Proxmox usando `ssh-copy-id`.
        *   Teste a conexão SSH e a capacidade de `sudo` sem senha.
    2.  **Executar o Playbook `full-deploy.yml` (ou o script `restore.sh`):**
        Na raiz do repositório, na máquina de controle Ansible (o `restore.sh` entra sozinho em `server/ansible`):
        ```bash
        bash server/scripts/restore.sh # Este script executa o full-deploy.yml e lida com a senha do vault
        # OU, se preferir executar diretamente:
        # cd server/ansible && ansible-playbook -i inventories/home/hosts.ini playbooks/full-deploy.yml --ask-vault-pass
        ```
        O playbook `full-deploy.yml` não executa o `vm-deploy.yml`: as VMs vêm da restauração (se precisar recriá-las, rode-o antes). Ele irá:
        *   Executar `setup-proxmox-host.yml`: Reconfigurar o host Proxmox (NFS server, firewall, pacotes, Node Exporter, etc.) para o estado definido.
        *   Executar `setup-base-ubuntu.yml`: Reconfigurar a base das VMs (NFS client, UFW, Node Exporter VM, Docker, Portainer na `core-services-vm`).
        *   Executar `setup-core-networking.yml`: Re-deployar as configurações e containers para Traefik, Cloudflared e Authelia.
        *   Executar os playbooks `setup-<stack>-volumes.yml` (produtividade/automação, mídia, monitoramento, n8n e IA): Garantir que os diretórios NFS para as stacks Docker estejam com as permissões corretas e que os arquivos `.env` sejam recriados nas VMs.

8.  **Implantar (ou Verificar) as Stacks Docker via Portainer:**
    *   Acesse sua instância Portainer (em `https://portainer.{{ base_domain }}`).
    *   **Se os dados do volume `docker-volumes/portainer/data` foram restaurados com o pool ZFS,** suas configurações de stacks, endpoints e usuários do Portainer podem já estar lá.
        *   Navegue para "Stacks". Se suas stacks estiverem listadas, você pode precisar "Update the stack" para algumas delas (sem mudar o compose, apenas para forçar o Portainer a reconciliar com o estado atual do Docker e carregar os `.env` recriados).
    *   **Se você está recriando as stacks do zero no Portainer (ou se a config do Portainer foi perdida):**
        Para cada stack do Portainer (`apps` na `core-services-vm`, `ai` na `ai-desktop-vm`; a `core` já foi implantada pelo `setup-core-networking.yml`):
        1.  Vá para "Stacks" -> "+ Add stack".
        2.  Cole o conteúdo do arquivo `docker-compose.yml` da respectiva stack.
        3.  Em **Env**, carregue o `.env` que o Ansible recriou na VM (`/opt/portainer_stack_envs/apps.env`, montado como na [seção 7](../01-manual-implementacao/07-deploy-apps.md), ou `/opt/portainer_stack_envs/ai.env`). Ele já traz os segredos do vault.
        4.  Clique em "**Deploy the stack**".
    *   **Dados das Aplicações:** Como o conteúdo do dataset `/data/docker-volumes` (e outros como `/data/media`) foi restaurado (seja pela importação do pool ZFS original ou de um backup off-site), suas aplicações Docker, ao serem reiniciadas com seus volumes corretamente mapeados, devem encontrar seus dados e configurações anteriores.
        *   **Restauração de Dumps de DB:** Se você tem dumps de banco de dados mais recentes do que o estado dos volumes ZFS restaurados, ou se a restauração do volume do DB não foi perfeita, você pode precisar restaurar os dumps de banco de dados manualmente (conforme descrito na [Estratégia de Backup](02-backup-restore-estrategia.md#a-bancos-de-dados-das-aplicações-postgresql-para-authelia-nextcloud-grafana)).

9.  **Testar Tudo Exaustivamente:**
    *   Verifique o acesso a cada serviço web via seu subdomínio Cloudflare.
    *   Teste a autenticação com Authelia.
    *   Verifique a funcionalidade de cada aplicação (Nextcloud, Jellyfin, Home Assistant, Grafana, etc.).
    *   Confirme que os dados estão presentes e corretos.
    *   Verifique os logs de todos os componentes (Proxmox, VMs, containers) por quaisquer novos erros.

Este processo de reconstrução, embora possa parecer complexo, é significativamente mais gerenciável e menos propenso a erros do que uma reconstrução totalmente manual, graças à sua Infraestrutura como Código com Ansible e a uma estratégia de backup bem definida. A chave é ter backups confiáveis e um repositório Ansible atualizado.