---
description: "Como reconstruir a infraestrutura após falha grave do disco do sistema, usando Git, Ansible e o pool ZFS."
---

# Reconstruindo a Infraestrutura Após uma Falha Grave

Apesar de todos os nossos esforços de manutenção preventiva e redundância (como o pool ZFS `/data` em RAID 1), falhas de hardware catastróficas podem ocorrer. O cenário mais impactante seria a falha do seu SSD NVMe principal, que hospeda o sistema operacional Proxmox VE e os discos virtuais das suas máquinas virtuais. Outros cenários podem incluir corrupção irreparável do sistema operacional do host Proxmox ou um desastre físico que afete o servidor.

Este guia descreve como reconstruir a infraestrutura do zero com o que a [Estratégia de Backup](02-backup-restore-estrategia.md) garante:

1.  **O pool ZFS `/data`**, intacto nos HDDs ou restaurado do restic (disco externo ou nuvem). Ele traz as configurações das aplicações, os arquivos e os **dumps diários de todos os bancos** em `docker-volumes/<app>/db-dumps/` (Immich: `photos/backups/`).
2.  **O repositório `homeserver`** no GitHub, com o `vault.yml` criptografado.
3.  **As senhas do Ansible Vault e do restic**, guardadas fora do servidor.

As VMs **não** são restauradas de imagem: são recriadas pelo `vm-deploy.yml` e configuradas pelos playbooks. Os bancos, que viviam no disco local das VMs, voltam pelos dumps.

!!! critical "A Importância dos Backups Off-Site"
    Se a falha grave afetar *todos* os discos do servidor (inclusive os HDDs do pool `/data`), o repositório do restic na nuvem será a única forma de recuperar fotos, arquivos, notas e bancos. Confira de vez em quando os testes de restauração da página de backup.

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
    *   **Se os HDDs do pool `/data` foram perdidos e você precisa restaurar do backup:**
        1.  Crie um novo pool ZFS `data` e os datasets seguindo a [Seção 2.2](../01-manual-implementacao/02-proxmox-ve-host.md#22-configuração-do-pool-zfs-data-e-datasets) (mesmos nomes e cotas).
        2.  Instale o restic (`apt install restic`), carregue o repositório (disco externo, se ele sobreviveu, ou a nuvem) e restaure cada dataset de `restic_datasets` como em [Um dataset inteiro](02-backup-restore-estrategia.md#um-dataset-inteiro). A mídia não está no backup: as *arr baixam de novo o que estiver na biblioteca.
        3.  Este é o passo mais demorado (da nuvem, pode levar dias). Comece por `docker-volumes`, que é pequeno e destrava o resto.

4.  **Recriar as VMs:**
    *   Com a máquina de controle pronta (passo 5), rode `playbooks/vm-deploy.yml`: ele recria a `core-services-vm` e a `ai-desktop-vm` com os mesmos IDs, IPs e o passthrough da GPU ([seção 3](../01-manual-implementacao/03-provisionamento-vms.md)). As VMs ganham discos novos; os bancos voltam pelos dumps no passo 7.
    *   O `/etc/pve/qemu-server/` no backup do restic (`/etc` do host) mostra a definição exata das VMs antigas, se precisar comparar.

5.  **Preparar sua Máquina de Controle Ansible e o Repositório:**
    *   Se sua máquina de controle Ansible original foi perdida ou não está configurada, prepare uma nova seguindo a [**Seção 1.1: Instalação do Ambiente de Controle (`scripts/bootstrap.sh`)**](../01-manual-implementacao/01-maquina-controle-ansible.md#11-instalação-do-ambiente-de-controle-scriptsbootstrapsh).
    *   Clone seu repositório `homeserver` do seu serviço Git remoto (GitHub, GitLab, etc.) para sua máquina de controle.
    *   Certifique-se de que você tem acesso à sua **senha do Ansible Vault**.

6.  **Executar os Playbooks Ansible para Reconfigurar a Infraestrutura:**
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
        O playbook `full-deploy.yml` não executa o `vm-deploy.yml` (rode-o antes, no passo 4). Ele irá:
        *   Executar `setup-proxmox-host.yml`: Reconfigurar o host Proxmox (NFS server, firewall, pacotes, Alloy, etc.) para o estado definido.
        *   Executar `setup-base-ubuntu.yml`: Reconfigurar a base das VMs (NFS client, UFW, Alloy, Docker, Portainer na `core-services-vm`).
        *   Executar `setup-core-networking.yml`: Re-deployar as configurações e containers para Traefik, Cloudflared e Authelia.
        *   Executar os playbooks `setup-<stack>-volumes.yml` (produtividade/automação, n8n, monitoramento, mídia, fotos, nuvem, IA, notas, Langfuse e agentes): Garantir que os diretórios NFS para as stacks Docker estejam com as permissões corretas e que os arquivos `.env` sejam recriados nas VMs.

7.  **Implantar (ou Verificar) as Stacks Docker via Portainer:**
    *   Acesse sua instância Portainer (em `https://portainer.seudominio.com`).
    *   **Se os dados do volume `docker-volumes/portainer/data` foram restaurados com o pool ZFS,** suas configurações de stacks, endpoints e usuários do Portainer podem já estar lá.
        *   Navegue para "Stacks". Se suas stacks estiverem listadas, você pode precisar "Update the stack" para algumas delas (sem mudar o compose, apenas para forçar o Portainer a reconciliar com o estado atual do Docker e carregar os `.env` recriados).
    *   **Se você está recriando as stacks do zero no Portainer (ou se a config do Portainer foi perdida):**
        Para cada stack do Portainer (na `core-services-vm`: `apps`, `media`, `photos`, `cloud` e `agents`; na `ai-desktop-vm`: `notes`, `langfuse` e `ai`, nesta ordem; a `core` já foi implantada pelo `setup-core-networking.yml`):
        1.  Vá para "Stacks" -> "+ Add stack".
        2.  Cole o conteúdo do arquivo `docker-compose.yml` da respectiva stack.
        3.  Em **Env** (**Advanced mode**), cole o `.env` que o Ansible recriou na VM (`/opt/portainer_stack_envs/<stack>.env`; [como](../01-manual-implementacao/07-deploy-apps.md#como-as-stacks-recebem-as-variáveis)). Ele já traz os segredos do vault.
        4.  Clique em "**Deploy the stack**".
    *   **Dados das Aplicações:** Como o conteúdo do dataset `/data/docker-volumes` (e outros como `/data/media`) foi restaurado (seja pela importação do pool ZFS original ou de um backup off-site), suas aplicações Docker, ao serem reiniciadas com seus volumes corretamente mapeados, devem encontrar seus dados e configurações anteriores.
        *   **Bancos de dados:** as VMs novas nascem com os bancos vazios em `/opt/local-data`. Para cada um (Authelia, Grafana, Nextcloud, LiteLLM), pare o container da aplicação, restaure o dump mais recente no container do banco e suba a aplicação de novo ([Bancos de dados](02-backup-restore-estrategia.md#bancos-de-dados)). O Immich restaura o dele pela própria tela de [restauração](https://docs.immich.app/administration/backup-and-restore), a partir de `photos/backups/`. Faça o Authelia primeiro: sem ele, ninguém entra nos outros.

8.  **Testar Tudo Exaustivamente:**
    *   Verifique o acesso a cada serviço web via seu subdomínio Cloudflare.
    *   Teste a autenticação com Authelia.
    *   Verifique a funcionalidade de cada aplicação (Nextcloud, Jellyfin, Home Assistant, Grafana, etc.).
    *   Confirme que os dados estão presentes e corretos.
    *   Verifique os logs de todos os componentes (Proxmox, VMs, containers) por quaisquer novos erros.

Este processo de reconstrução, embora possa parecer complexo, é significativamente mais gerenciável e menos propenso a erros do que uma reconstrução totalmente manual, graças à sua Infraestrutura como Código com Ansible e a uma estratégia de backup bem definida. A chave é ter backups confiáveis e um repositório Ansible atualizado.