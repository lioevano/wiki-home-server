# Automação da Infraestrutura com Ansible

Ansible é a ferramenta de automação escolhida para esta arquitetura, permitindo que configuremos e gerencemos nosso servidor doméstico de forma programática, consistente e repetível. Isso é um pilar da filosofia de Infraestrutura como Código (IaC).

## Por que Ansible?

*   **Infraestrutura como Código (IaC):** As configurações da sua infraestrutura (servidores, VMs, software, redes) são definidas em arquivos de texto (playbooks YAML), que podem ser versionados em Git, revisados e reutilizados.
*   **Idempotência:** Um conceito fundamental no Ansible. Um playbook pode ser executado múltiplas vezes, e o resultado será sempre o mesmo estado desejado. Se o sistema já está no estado correto, o Ansible não faz alterações (ou faz apenas as mínimas necessárias).
*   **Agentless:** Ansible não requer a instalação de agentes nos nós gerenciados (como o host Proxmox e as VMs). Ele se conecta via SSH (para Linux/Unix) e executa os módulos necessários.
*   **Simplicidade (YAML):** Playbooks são escritos em YAML, que é relativamente fácil de ler e escrever.
*   **Módulos Extensivos:** Ansible possui uma vasta biblioteca de módulos para interagir com diversos sistemas, incluindo Proxmox, Docker, gerenciamento de pacotes, arquivos, serviços, etc. Utilizamos coleções como `community.proxmox` e `community.docker`.
*   **Roles:** Permitem organizar tarefas e variáveis em unidades reutilizáveis, promovendo um código mais limpo e modular.
*   **Ansible Vault:** Para gerenciamento seguro de dados sensíveis (senhas, tokens API).

## Estrutura do Projeto Ansible (`infra-servidor-domestico/ansible/`)

A organização dos arquivos Ansible no nosso projeto é crucial para a manutenibilidade:

*   **`inventories/home/`:** Define os hosts que o Ansible gerenciará.
    *   `hosts.ini`: Lista os hosts (Proxmox, VMs) e os agrupa. Define variáveis de conexão (IP, usuário, chave SSH).
    *   `group_vars/all/main.yml`: Variáveis comuns não sensíveis aplicadas a todos os hosts.
    *   `group_vars/all/vault.yml`: Variáveis comuns sensíveis (criptografadas) aplicadas a todos os hosts.
*   **`playbooks/`:** Contém os playbooks YAML que orquestram as tarefas. Cada playbook define um conjunto de hosts alvo e os roles ou tarefas a serem aplicados.
    *   Ex: `setup-proxmox-host.yml`, `vm-deploy.yml`, `full-deploy.yml` (playbook mestre).
*   **`roles/`:** Diretórios contendo roles reutilizáveis. Cada role tem uma estrutura definida (tasks, handlers, templates, files, defaults, vars).
    *   Ex: `infra/proxmox-host-config`, `common`, `infra/docker`.
*   **`ansible.cfg` (Opcional, na raiz do projeto Ansible):** Pode ser usado para definir configurações padrão do Ansible para o projeto (e.g., caminho do inventário, roles_path, desabilitar host key checking para ambientes de teste - não recomendado para produção). Este guia não foca nele, mas é bom saber que existe.

## Fluxo de Trabalho Típico com Ansible

1.  **Definir o Estado Desejado:** Você descreve o estado final que deseja para seus sistemas nos playbooks e roles Ansible (e.g., "o pacote nginx deve estar instalado", "o serviço Docker deve estar rodando", "esta linha deve existir no arquivo de configuração X").
2.  **Executar o Playbook:** A partir da sua [máquina de controle Ansible](../01-manual-implementacao/01-maquina-controle-ansible.md), você executa um comando como:
    ```bash
    ansible-playbook playbooks/meu-playbook.yml --ask-vault-pass
    ```
3.  **Conexão e Coleta de Fatos (Opcional):** Ansible se conecta aos hosts definidos no inventário via SSH. Opcionalmente, ele pode coletar "fatos" sobre os sistemas remotos (distribuição do SO, IPs, etc.) que podem ser usados em condicionais e templates.
4.  **Execução de Tarefas:** Ansible executa as tarefas definidas no playbook (ou nos roles incluídos) em cada host alvo, em ordem.
    *   Módulos Ansible são executados no host remoto para realizar as ações.
    *   Devido à idempotência, se uma tarefa já foi aplicada e o sistema está no estado desejado, o Ansible reportará "ok" sem fazer mudanças. Se uma mudança for necessária, reportará "changed".
5.  **Handlers:** Se uma tarefa reportar "changed" e tiver um `notify` para um handler, esse handler será executado no final do play em cada host. Handlers são úteis para reiniciar serviços apenas se suas configurações mudaram.
6.  **Relatório:** Ansible exibe um resumo das tarefas (ok, changed, unreachable, failed).

## Principais Playbooks e Seus Papéis na Arquitetura

*   **`setup-proxmox-host.yml`:**
    *   **Alvo:** `proxmox_main_host`.
    *   **Função:** Configurações iniciais do Proxmox VE (repositórios, pacotes, firewall, SSH hardening, Node Exporter, servidor NFS).
*   **`vm-deploy.yml`:**
    *   **Alvo:** `proxmox_main_host` (para interagir com a API Proxmox).
    *   **Função:** Provisiona as VMs (`core-services-vm`, `ai-desktop-vm`) a partir do template Cloud-Init, configurando recursos e Cloud-Init.
*   **`setup-base-ubuntu.yml`:**
    *   **Alvo:** `ubuntu_vms` (grupo contendo todas as VMs Ubuntu).
    *   **Função:** Aplica configurações base (pacotes, fuso horário, cliente NFS, UFW, Node Exporter VM). Instala Docker Engine e Portainer na `core-services-vm`. Instala GUI opcional.
*   **`setup-core-networking.yml`:**
    *   **Alvo:** `core-services-vm`.
    *   **Função:** Prepara arquivos de configuração para Traefik e Authelia, e faz o deploy das stacks Docker `core` (Traefik, Cloudflared) e `authelia`.
*   **Playbooks `setup-<stack>-volumes.yml` (e.g., `setup-media-stack-volumes.yml`):**
    *   **Alvo:** VM específica onde a stack Docker rodará (geralmente `core-services-vm` ou `ai-desktop-vm`).
    *   **Função:** Criar os diretórios necessários nos volumes NFS e gerar o arquivo `.env` com caminhos e variáveis para a respectiva stack Docker a ser implantada via Portainer.
*   **`full-deploy.yml`:**
    *   **Função:** Playbook mestre que importa e executa os playbooks acima em uma sequência lógica para um deploy completo da infraestrutura base. Usado para o setup inicial ou para garantir que toda a infraestrutura esteja no estado desejado.

A automação com Ansible não apenas economiza tempo e reduz erros manuais, mas também serve como documentação viva da configuração da sua infraestrutura. Qualquer pessoa com acesso ao repositório Ansible pode entender como o sistema foi construído e como é gerenciado.