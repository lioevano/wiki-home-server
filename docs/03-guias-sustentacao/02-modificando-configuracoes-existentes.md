# Modificando Configurações Existentes

Sua infraestrutura de servidor doméstico é dinâmica. Com o tempo, você precisará ajustar configurações, atualizar serviços ou alterar parâmetros. Este guia descreve onde as principais configurações residem e como modificá-las com segurança.

## Onde as Configurações Residem? Uma Visão Geral

Entender onde cada peça de configuração está armazenada é o primeiro passo para uma modificação bem-sucedida.

*   **Ansible (Máquina de Controle):**
    *   **Inventário (`ansible/inventories/home/hosts.ini`):** IPs dos hosts, grupos, variáveis de conexão.
    *   **Variáveis Globais (`ansible/inventories/home/group_vars/all/main.yml`):** Parâmetros não sensíveis comuns a todos os hosts (e.g., caminhos NFS, nomes de usuário padrão).
    *   **Vault (`ansible/inventories/home/group_vars/all/vault.yml`):** **TODOS os segredos** gerenciados pelo Ansible (senhas, tokens de API). Edite com `ansible-vault edit ...`.
    *   **Roles (`ansible/roles/...`):** Contêm tasks, templates (`.j2` arquivos), handlers e defaults que definem a configuração dos componentes (e.g., config do servidor NFS, Docker, Traefik).
    *   **Playbooks (`ansible/playbooks/...`):** Orquestram a aplicação dos roles e tasks.
*   **Proxmox VE Host:**
    *   **UI Web do Proxmox:** Para configurações de VMs (RAM, CPU, passthrough), storage, rede do host, firewall PVE.
    *   **Arquivos de Configuração no Host (geralmente gerenciados por Ansible):**
        *   `/etc/pve/`: Configuração do cluster e VMs.
        *   `/etc/network/interfaces`: Configuração de rede do host.
        *   `/etc/default/grub`: Opções de boot do kernel (para IOMMU, etc.).
        *   `/etc/modules`: Módulos do kernel a serem carregados.
        *   `/etc/modprobe.d/`: Blacklisting de módulos.
        *   `/etc/exports`: Configuração do servidor NFS.
        *   `/etc/systemd/system/`: Arquivos de unidade Systemd para serviços (e.g., Node Exporter, Ollama).
*   **Máquinas Virtuais (VMs):**
    *   **Arquivos de Configuração Padrão do Linux (geralmente gerenciados por Ansible):**
        *   `/etc/fstab`: Para montagens NFS.
        *   `/etc/ufw/`: Regras do firewall UFW.
        *   `/etc/apt/sources.list.d/`: Repositórios de pacotes.
        *   Configurações de serviços específicos (e.g., `/etc/systemd/system/node_exporter.service`).
*   **Docker e Portainer (na `core-services-vm` ou `ai-desktop-vm`):**
    *   **`docker-compose.yml` de cada Stack:** Estes arquivos (localizados em `infra-servidor-domestico/docker/stacks/.../`) definem os serviços, imagens, volumes, redes, portas, variáveis de ambiente e labels Traefik para cada stack. As modificações são feitas nesses arquivos e depois aplicadas via Portainer ("Update the stack").
    *   **Variáveis de Ambiente no Portainer:**
        *   Carregadas dos arquivos `.env` (e.g., `/opt/portainer_stack_envs/media.env` na VM).
        *   Secrets (senhas, tokens) definidos manualmente na UI do Portainer ao criar/editar a stack.
    *   **Volumes Docker Persistentes (nos montados NFS):** Contêm os dados e configurações internas das aplicações Docker (e.g., o `config.php` do Nextcloud, o banco de dados do Sonarr).
*   **Traefik (Configuração via `core-services-vm`):**
    *   **Configuração Estática (`traefik.yml`):** Gerada pelo Ansible a partir de `traefik.yml.j2` e localizada em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/traefik/config/traefik.yml`. Define entrypoints, provedores, resolvedores de ACME. **Requer reinício do container Traefik para aplicar mudanças.**
    *   **Configuração Dinâmica (Diretório de Arquivos):** Arquivos YAML em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/traefik/config/dynamic/`. Contém middlewares (e.g., `security_headers.yml`, `nextcloud_middleware.yml`) e roteamento para serviços externos (e.g., `rag_services.yml`). Traefik monitora este diretório e recarrega automaticamente as mudanças.
    *   **`acme.json`:** Localizado em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/traefik/data/acme.json`. Contém os certificados SSL/TLS gerados pela Let's Encrypt. **NÃO EDITE MANUALMENTE.** Traefik gerencia este arquivo.
    *   **Labels Docker nos Containers:** Definidas nos `docker-compose.yml`, são a principal forma de Traefik descobrir e configurar o roteamento para serviços Docker. Modificar labels e atualizar a stack no Portainer faz com que Traefik reconfigure dinamicamente.
*   **Authelia (Configuração via `core-services-vm`):**
    *   **`configuration.yml`:** Gerado pelo Ansible a partir de `configuration.yml.j2` e localizado em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/authelia/config/configuration.yml`. Define a configuração principal do Authelia. **Requer reinício do container Authelia para aplicar a maioria das mudanças.**
    *   **Banco de Dados PostgreSQL do Authelia:** Armazena usuários, dispositivos 2FA, etc.
*   **Aplicações Específicas:**
    *   Muitas aplicações (Nextcloud, Sonarr, Grafana, etc.) têm suas próprias interfaces de administração web onde configurações específicas da aplicação são gerenciadas. Essas configurações são geralmente salvas nos volumes Docker persistentes.

## Processo Seguro para Modificar Configurações

1.  **Identifique a Configuração e Onde Ela Reside:** Consulte a lista acima. Determine se a mudança afeta Ansible, Proxmox, uma VM específica, uma stack Docker, Traefik, Authelia, ou a própria aplicação.

2.  **Planeje a Mudança:** Entenda o impacto da alteração.

3.  **Faça Backup (se a mudança for crítica ou arriscada):**
    *   **Ansible:** Seus arquivos já estão no Git. Faça um commit antes de mudanças significativas.
    *   **Proxmox/VMs:** Crie um snapshot da VM no Proxmox antes de alterações importantes no SO da VM ou configurações críticas do Proxmox.
    *   **Volumes Docker/NFS:** ZFS snapshots no host Proxmox podem ser úteis (`sudo zfs snapshot data/docker-volumes@antes_da_mudanca_X`).
    *   **Arquivos de Configuração Específicos:** Faça uma cópia do arquivo antes de editá-lo (e.g., `cp traefik.yml traefik.yml.bak`).

4.  **Aplique a Mudança:**

    *   **Mudanças Gerenciadas por Ansible:**
        1.  Edite o arquivo Ansible apropriado (inventário, `main.yml`, `vault.yml`, template `.j2`, tasks de um role).
        2.  Execute o playbook Ansible relevante (e.g., `ansible-playbook playbooks/setup-core-networking.yml --ask-vault-pass`). O Ansible aplicará a mudança de forma idempotente.
    *   **Mudanças em Stacks Docker (via Portainer):**
        1.  Edite o arquivo `docker-compose.yml` correspondente no seu projeto `infra-servidor-domestico/docker/stacks/.../`.
        2.  No Portainer, vá para a stack, clique em "Editor".
        3.  Cole o `docker-compose.yml` atualizado.
        4.  Se necessário, modifique as variáveis de ambiente na UI do Portainer.
        5.  Clique em "**Update the stack**". Selecione "Re-pull image and redeploy" se você alterou a tag da imagem.
    *   **Mudanças na Configuração Estática do Traefik ou Authelia (arquivos .yml principais):**
        1.  Edite o template `.j2` no seu role Ansible (`traefik-config` ou `authelia-config`).
        2.  Execute o playbook Ansible que copia esses templates (e.g., `setup-core-networking.yml`).
        3.  **Reinicie os containers Traefik e/ou Authelia** no Portainer para que eles carreguem a nova configuração estática.
    *   **Mudanças na Configuração Dinâmica do Traefik (arquivos no diretório `dynamic`):**
        1.  Edite o template `.j2` ou o arquivo YAML diretamente no volume NFS (se não gerenciado por Ansible).
        2.  Se gerenciado por Ansible, execute o playbook que copia o arquivo.
        3.  Traefik deve recarregar a configuração dinâmica automaticamente (verifique os logs do Traefik).
    *   **Mudanças na UI de uma Aplicação:** Faça a alteração diretamente na interface web da aplicação (e.g., adicionar um usuário no Nextcloud, configurar um indexador no Sonarr). Essas configurações são salvas no volume persistente da aplicação.
    *   **Mudanças na UI do Proxmox:** Faça a alteração na interface web do Proxmox (e.g., aumentar RAM de uma VM).
        !!! warning "Consistência com Ansible"
            Se você fizer uma mudança na UI do Proxmox que também é gerenciada pelo Ansible (e.g., RAM da VM definida no `vm-deploy.yml`), a próxima vez que você rodar o playbook Ansible, ele poderá reverter sua mudança manual para o estado definido no Ansible. Para mudanças permanentes, altere no Ansible e reaplique.

5.  **Verifique e Teste:**
    *   Monitore os logs dos containers/serviços afetados.
    *   Teste a funcionalidade que foi alterada.
    *   Verifique se outros serviços não foram impactados negativamente.

6.  **Documente a Mudança (Opcional, mas bom):** Se for uma alteração significativa, adicione uma nota nesta wiki ou no commit do Git.

## Exemplos Comuns de Modificação

*   **Alterar uma Senha no Ansible Vault:**
    1.  `ansible-vault edit ansible/inventories/home/group_vars/all/vault.yml`
    2.  Modifique a variável da senha. Salve.
    3.  Execute o playbook que usa essa senha (e.g., se for `nextcloud_db_password`, execute o playbook que deploya a stack Nextcloud para que a nova senha seja passada ao container, ou atualize a variável de ambiente no Portainer e recrie a stack).
*   **Atualizar a Imagem de um Container Docker:**
    1.  Edite o `docker-compose.yml` da stack, alterando a tag da imagem (e.g., de `plex:1.30` para `plex:1.31`).
    2.  No Portainer, vá para a stack, clique em "Editor", cole o compose atualizado.
    3.  Clique em "Update the stack" e certifique-se que a opção "Re-pull image and redeploy" (ou similar) está marcada.
*   **Adicionar um Novo Roteamento no Traefik para um Serviço Existente (sem Authelia):**
    1.  Edite o `docker-compose.yml` do serviço, adicionando as labels Traefik apropriadas.
    2.  Atualize a stack no Portainer. Traefik deve detectar as novas labels e criar a rota.
*   **Mudar a Quantidade de RAM de uma VM:**
    1.  **Método Ansible (Recomendado para consistência):**
        *   Edite `ansible/playbooks/vm-deploy.yml`, alterando o valor de `vm_memory` para a VM desejada.
        *   Execute `ansible-playbook ansible/playbooks/vm-deploy.yml --ask-vault-pass`.
        *   A VM provavelmente precisará ser reiniciada para a mudança de RAM ter efeito. O módulo `proxmox_kvm` pode lidar com isso se a VM estiver rodando.
    2.  **Método UI Proxmox (Rápido, mas pode divergir do Ansible):**
        *   Desligue a VM.
        *   Na UI do Proxmox, vá para Hardware da VM, edite a Memória.
        *   Inicie a VM.

Lembre-se sempre de proceder com cautela, especialmente ao modificar configurações críticas. Backups e snapshots são seus amigos!