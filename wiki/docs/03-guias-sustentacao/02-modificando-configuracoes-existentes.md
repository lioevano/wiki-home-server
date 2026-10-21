---
description: "Onde ficam as configurações (Ansible, compose, Portainer) e como alterá-las com segurança e rastreabilidade."
---

# Modificando Configurações Existentes

Sua infraestrutura de servidor doméstico é uma entidade viva. Com o tempo, você inevitavelmente precisará ajustar configurações, atualizar parâmetros, ou refinar o comportamento de serviços existentes. Este guia descreve onde as principais peças de configuração residem em nossa arquitetura e como abordá-las de forma segura e consistente, mantendo a integridade da sua Infraestrutura como Código (IaC).

## Onde as Configurações Residem? Um Mapa da Sua Infra

Entender onde cada configuração está armazenada é o primeiro e mais crucial passo para uma modificação bem-sucedida e para evitar quebrar coisas acidentalmente.

1.  **Ansible (Sua Máquina de Controle Ansible - Fonte da Verdade para IaC):**
    O Ansible gerencia a configuração fundamental da sua infraestrutura.
    *   **Inventário (`server/ansible/inventories/home/hosts.ini`):**
        *   Define os IPs dos seus hosts (Proxmox, VMs) e como o Ansible se conecta a eles.
        *   Agrupa hosts para aplicação de configurações em massa.
        *   Contém variáveis de host (e.g., `GUI_ENABLED`) e variáveis de grupo.
    *   **Variáveis Globais Não Sensíveis (`server/ansible/inventories/home/group_vars/all/main.yml`):**
        *   Parâmetros comuns e não secretos aplicados a todos os hosts. Exemplos: caminhos base NFS, nomes de usuário padrão, CIDRs de rede permitidos, nomes de datasets ZFS.
    *   **Ansible Vault (`server/ansible/inventories/home/group_vars/all/vault.yml`):**
        *   **Local de TODOS os segredos** gerenciados pelo Ansible: senhas de sistema, tokens de API (Cloudflare), segredos para Authelia, senhas de banco de dados para aplicações, etc.
        *   **Edição Segura:** Sempre edite este arquivo com `ansible-vault edit inventories/home/group_vars/all/vault.yml`.
    *   **Roles (`server/ansible/roles/...`):**
        *   Contêm a lógica de configuração para componentes específicos (e.g., `infra/proxmox-host-config`, `common`, `infra/docker`, `infra/traefik-config`, `infra/authelia-config`).
        *   **`tasks/main.yml`:** Define as ações.
        *   **`templates/`:** Arquivos de template Jinja2 (`.j2`) que geram arquivos de configuração dinamicamente (e.g., `traefik.yml.j2`, `authelia/configuration.yml.j2`, `etc_exports.j2`).
        *   **`handlers/main.yml`:** Ações acionadas por mudanças (e.g., reiniciar um serviço).
        *   **`defaults/main.yml` e `vars/main.yml`:** Variáveis específicas do role.
    *   **Playbooks (`server/ansible/playbooks/...`):**
        *   Orquestram a aplicação de roles e tarefas aos hosts definidos no inventário.

2.  **Host Proxmox VE:**
    Embora muitas configurações do host sejam gerenciadas pelo Ansible, algumas podem ser ajustadas via UI ou arquivos de sistema.
    *   **Interface Web do Proxmox:** Para configurações de VMs (RAM, CPU, dispositivos de passthrough PCI/USB), storage, rede do host (bridges), firewall PVE.
    *   **Arquivos de Configuração no Host (Muitos gerenciados por Ansible, mas para referência):**
        *   `/etc/pve/`: Configuração do cluster Proxmox e das VMs (e.g., `/etc/pve/qemu-server/VMID.conf`).
        *   `/etc/network/interfaces`: Configuração de rede do host (bridges `vmbr0`, etc.).
        *   `/etc/default/grub` e `/etc/kernel/cmdline`: Opções de boot do kernel (para IOMMU, etc.).
        *   `/etc/modules`, `/etc/modprobe.d/`: Módulos do kernel e blacklisting.
        *   `/etc/exports`: Configuração do servidor NFS (gerada pelo Ansible).
        *   `/etc/systemd/system/` (e `override.conf` em subdiretórios): Arquivos de unidade Systemd para serviços gerenciados por Ansible. O Alloy é um pacote apt: a configuração fica em `/etc/alloy/config.alloy` e `/etc/default/alloy`, gerados pelo role `infra/alloy`. O Ollama roda em container na stack `ai`, não como serviço systemd.

3.  **Máquinas Virtuais (VMs - `core-services-vm`, `ai-desktop-vm`):**
    As configurações base são gerenciadas pelo Ansible.
    *   **Arquivos de Configuração Padrão do Linux (Gerenciados por Ansible):**
        *   `/etc/fstab`: Para montagens NFS automáticas.
        *   `/etc/ufw/`: Regras do firewall UFW.
        *   `/etc/apt/sources.list.d/`: Repositórios de pacotes APT (e.g., para Docker).
        *   Configuração do Alloy (`/etc/alloy/config.alloy`, `/etc/default/alloy`), gerada pelo role `infra/alloy`: para mudá-la, edite o `config.alloy.j2` pela wiki e rode o `setup-base-ubuntu.yml`.
    *   **Arquivos `.env` para Stacks Portainer:**
        *   Localizados em `{{ portainer_env_files_dest_path_on_vm }}` (e.g., `/opt/portainer_stack_envs/`) nas VMs.
        *   Gerados pelo Ansible (e.g., por `setup-media-stack-volumes.yml`). Contêm PUID/PGID, TZ, caminhos de volume, etc., para as stacks Docker.

4.  **Docker e Portainer (na `core-services-vm` ou `ai-desktop-vm`):**
    *   **Arquivos `docker-compose.yml` de cada Stack:**
        *   Localizados no seu projeto Git em `server/docker/stacks/NOME_DA_STACK/docker-compose.yml`.
        *   Definem os serviços, imagens, volumes, redes, portas, variáveis de ambiente e labels Traefik para cada stack de aplicação.
        *   **As modificações são feitas nestes arquivos e depois aplicadas via Portainer ("Update the stack").**
    *   **Variáveis de Ambiente e Secrets:**
        *   Ao criar/editar uma stack no Portainer, cole o `.env` gerado pelo Ansible na VM em **Advanced mode** ([como](../01-manual-implementacao/07-deploy-apps.md#como-as-stacks-recebem-as-variáveis)).
        *   **Secrets críticos** (senhas de banco de dados, tokens de API) ficam no vault e chegam ao `.env` pelo playbook da stack; para mudá-los, edite o vault e rode o playbook de novo. Nada é digitado na UI do Portainer.
    *   **Volumes Docker Persistentes (Mapeados para os Diretórios NFS):**
        *   Contêm os dados e arquivos de configuração internos das suas aplicações Docker (e.g., o `config.php` do Nextcloud dentro do seu volume de config, o banco de dados SQLite do Sonarr, a biblioteca do Jellyfin). As modificações de configuração *dentro* da aplicação são salvas aqui.

5.  **Traefik (Configuração via `core-services-vm`):**
    *   **Configuração Estática (`traefik.yml`):**
        *   Gerada pelo Ansible a partir do template `traefik.yml.j2`.
        *   Localizada no volume NFS: `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/traefik/config/traefik.yml`.
        *   Define entrypoints, provedores Docker/File, e o resolvedor ACME para Let's Encrypt.
        *   **Mudanças aqui geralmente requerem um reinício do container Traefik para terem efeito.**
    *   **Configuração Dinâmica (Diretório de Arquivos):**
        *   Arquivos YAML localizados em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/traefik/config/dynamic/`.
        *   Gerados pelo Ansible (e.g., `security_headers.yml`, `nextcloud_middleware.yml`, `ai_services.yml`).
        *   Contém definições de middlewares, e roteamento para serviços que não são descobertos automaticamente pelo Docker provider (como os da `ai-desktop-vm`).
        *   Traefik monitora este diretório e **recarrega automaticamente as mudanças** sem necessidade de reinício.
    *   **Certificados SSL (`acme.json`):**
        *   Localizado em `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/traefik/data/acme.json`.
        *   Contém os certificados SSL/TLS gerados pela Let's Encrypt.
        *   !!! danger "Não Edite Manualmente `acme.json`"
            Traefik gerencia este arquivo. A edição manual pode corrompê-lo e causar problemas na obtenção/renovação de certificados. Faça backup dele regularmente.
    *   **Labels Docker nos Containers:**
        *   Definidas nos arquivos `docker-compose.yml` de cada stack.
        *   São a principal forma pela qual o Traefik descobre e configura o roteamento para os serviços Docker rodando na mesma instância Docker que ele.
        *   Modificar labels e atualizar a stack no Portainer faz com que Traefik reconfigure dinamicamente o roteamento.

6.  **Authelia (Configuração via `core-services-vm`):**
    *   **Arquivo de Configuração Principal (`configuration.yml`):**
        *   Gerado pelo Ansible a partir do template `configuration.yml.j2`.
        *   Localizado no volume NFS: `{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/authelia/config/configuration.yml`.
        *   Define a configuração principal do Authelia (provedores de armazenamento, regras de acesso, segredos de sessão/JWT, notificador, etc.).
        *   **A maioria das mudanças aqui requer um reinício do container Authelia para terem efeito.**
    *   **Banco de Dados PostgreSQL do Authelia:**
        *   Armazena informações de usuários, dispositivos 2FA registrados, sessões, etc.
        *   Fica no disco local da `core-services-vm`, em `/opt/local-data/authelia-db/`; o dump diário vai para `docker-volumes/authelia/db-dumps/` ([backup](../04-manutencao-recuperacao/02-backup-restore-estrategia.md)).

7.  **Configurações Internas das Aplicações Específicas:**
    *   Muitas aplicações (Nextcloud, Sonarr, Radarr, Grafana, Home Assistant, etc.) têm suas próprias interfaces de administração web (UIs) ou arquivos de configuração específicos dentro dos seus volumes persistentes.
    *   **Exemplo:** Adicionar um usuário no Nextcloud, configurar um indexador no Sonarr, criar um dashboard no Grafana. Essas configurações são salvas nos volumes de dados da respectiva aplicação.

## Processo Seguro e Consistente para Modificar Configurações

1.  **Identifique a Configuração e Onde Ela Reside:** Use o mapa acima para determinar qual sistema ou arquivo controla a configuração que você deseja alterar.

2.  **Planeje a Mudança:** Entenda o impacto da alteração. Quais serviços serão afetados? É uma mudança crítica?

3.  **Faça Backup (SEMPRE para mudanças críticas ou arriscadas):**
    *   **Repositório Ansible Git:** Seus arquivos de configuração IaC já estão versionados. Faça um `git commit` antes de mudanças significativas nos arquivos Ansible.
    *   **Host Proxmox / VMs:** Antes de alterações no SO da VM, atualizações maiores do Proxmox, ou mudanças de hardware virtual, crie um **snapshot da VM** no Proxmox.
    *   **Volumes Docker / Dados NFS:** Para os datasets ZFS no host Proxmox (e.g., `data/docker-volumes`, `data/media`), crie um **snapshot ZFS** antes de modificações que possam afetar os dados:
        ```bash
        # No host Proxmox
        sudo zfs snapshot data/docker-volumes@antes_da_mudanca_X
        ```
        Consulte o [Guia de Snapshots ZFS](11-guia-snapshots-zfs.md) para mais detalhes.
    *   **Arquivos de Configuração Específicos:** Se for editar manualmente um arquivo de configuração crítico (o que deve ser raro se gerenciado por Ansible), faça uma cópia dele primeiro (e.g., `cp /caminho/arquivo.conf /caminho/arquivo.conf.bak`).

4.  **Aplique a Mudança (Método Preferencial Primeiro):**

    *   **Se a Configuração é Gerenciada pelo Ansible (Ideal):**
        1.  **Comece pela wiki** (ela é a fonte da verdade). Ache no `INDEX.md` a página que documenta o arquivo. Se o arquivo tem bloco literal na página, edite o bloco; se não, descreva a mudança na página e edite o arquivo. Depois, `python tools/dev.py check`, `sync` (confira o diff) e `sync --yes`, e então `test`, `build` e `lint`. Os segredos são a exceção: `ansible-vault edit inventories/home/group_vars/all/vault.yml`, mas a chave nova entra antes no `vault.yml.example` da página 01.
        2.  Execute o playbook Ansible relevante para aplicar a mudança (sempre `--check` antes). Exemplo:
            ```bash
            ansible-playbook -i inventories/home/hosts.ini playbooks/setup-core-networking.yml --ask-vault-pass
            ```
        3.  O Ansible aplicará a mudança de forma idempotente. Se a configuração já estiver no estado desejado, nenhuma alteração será feita.
    *   **Se a Mudança é em uma Stack Docker (via Portainer):**
        1.  Edite o arquivo `docker-compose.yml` correspondente no seu projeto Git (`server/docker/stacks/.../`), descrevendo a mudança na página da stack.
        2.  No Portainer, navegue até a stack que você deseja modificar.
        3.  Clique em "**Editor**".
        4.  Cole o conteúdo do `docker-compose.yml` atualizado.
        5.  Se mudou variáveis ou segredos, rode antes o playbook da stack e cole o `.env` atualizado em **Advanced mode** ([como](../01-manual-implementacao/07-deploy-apps.md#como-as-stacks-recebem-as-variáveis)).
        6.  Clique em "**Update the stack**".
            *   Marque a opção "**Re-pull image and redeploy**" se você alterou a tag da imagem de um serviço e quer que o Portainer puxe a nova versão da imagem.
    *   **Se a Mudança é na Configuração Estática do Traefik ou Authelia (arquivos `.yml` principais):**
        1.  Edite o template Jinja2 (`.j2`) correspondente no seu role Ansible (`traefik-config` ou `authelia-config`).
        2.  Execute o playbook Ansible que copia esses templates para os volumes NFS (geralmente `setup-core-networking.yml`).
        3.  Após o Ansible atualizar o arquivo de configuração no volume NFS, você precisará **reiniciar os containers Traefik e/ou Authelia** no Portainer para que eles carreguem a nova configuração estática.
    *   **Se a Mudança é na Configuração Dinâmica do Traefik (arquivos no diretório `dynamic`):**
        1.  Edite o template Jinja2 (`.j2`) ou o arquivo YAML diretamente no volume NFS (se a configuração não for gerenciada pelo Ansible, o que não é o caso aqui para a maioria).
        2.  Se gerenciado pelo Ansible, execute o playbook Ansible que copia o arquivo de configuração dinâmica (e.g., parte do `setup-core-networking.yml`).
        3.  Traefik deve monitorar o diretório de configuração dinâmica e **recarregar automaticamente as mudanças** sem necessidade de reinício. Verifique os logs do Traefik para confirmação.
    *   **Se a Mudança é na UI de uma Aplicação Específica:**
        Faça a alteração diretamente na interface web da aplicação (e.g., adicionar um usuário no Nextcloud, configurar um novo indexador no Sonarr, criar um novo dashboard no Grafana). Essas configurações são salvas no volume persistente da respectiva aplicação.
    *   **Se a Mudança é na UI do Proxmox (e.g., alterar RAM de uma VM):**
        1.  Faça a alteração na interface web do Proxmox.
        2.  !!! warning "Mantenha a Consistência com Ansible!"
            Se a configuração que você alterou na UI do Proxmox também é definida pelo Ansible (e.g., RAM da VM definida no `vm-deploy.yml`), é **crucial** que você atualize também o arquivo Ansible correspondente. Caso contrário, na próxima vez que você rodar o playbook Ansible, ele poderá **reverter sua mudança manual** para o estado definido no Ansible. Para mudanças permanentes, altere no Ansible e reaplique o playbook.

5.  **Verifique e Teste a Mudança:**
    *   Monitore os logs dos containers ou serviços afetados pela mudança.
    *   Teste a funcionalidade que foi alterada para garantir que está funcionando como esperado.
    *   Verifique se outros serviços ou partes do sistema não foram impactados negativamente.

6.  **Feche no Git:** atualize o `INDEX.md` se surgiu ou saiu arquivo (skill `update-index`) e faça **um** commit com a wiki, o `server/` e o índice juntos. O push dispara o CI (`server-lint`) e publica a wiki.

Lembre-se sempre de proceder com cautela, especialmente ao modificar configurações críticas ou que afetam a segurança. A abordagem de Infraestrutura como Código com Ansible, combinada com backups e snapshots, fornece uma base sólida para gerenciar mudanças de forma segura e recuperável.