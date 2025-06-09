# CI/CD Básico para Infraestrutura como Código (Ansible)

Gerenciar sua infraestrutura como código (IaC) com Ansible e Git permite um fluxo de trabalho similar ao de desenvolvimento de software, incluindo conceitos de Integração Contínua (CI) e Entrega Contínua (CD), mesmo que de forma simplificada para um homelab.

O objetivo é ter um processo confiável e automatizável para aplicar mudanças na sua infraestrutura.

## Fluxo de Trabalho com Git e Ansible

1.  **Desenvolvimento Local (na Máquina de Controle Ansible):**
    *   **Branching (Opcional, mas Boa Prática):** Para mudanças significativas, crie uma nova branch no Git: `git checkout -b feature/nova-config-x`.
    *   **Modificações:** Edite seus arquivos Ansible (`.yml`, `.ini`, templates `.j2`).
    *   **Adicionar Novos Roles/Playbooks:** Crie a estrutura necessária.

2.  **Teste Local:**
    Antes de aplicar as mudanças no ambiente "real", teste o máximo possível localmente:
    *   **Linting (Verificação de Sintaxe e Estilo):**
        *   `ansible-lint`: Analisa seus playbooks e roles em busca de erros, más práticas e problemas de estilo.
            ```bash
            # Instale se não tiver: pip install ansible-lint
            ansible-lint playbooks/meu_playbook.yml
            ansible-lint roles/meu_role/
            ```
        *   `yamllint`: Verifica a sintaxe de arquivos YAML.
            ```bash
            # Instale se não tiver: pip install yamllint
            yamllint .
            ```
    *   **Syntax Check do Ansible:**
        ```bash
        ansible-playbook playbooks/meu_playbook.yml --syntax-check
        ```
    *   **Dry Run (Modo de Verificação):**
        Simula a execução do playbook sem fazer alterações reais. Útil para ver o que *seria* alterado.
        ```bash
        ansible-playbook playbooks/meu_playbook.yml --check --diff --ask-vault-pass
        ```
        *   `--check`: Modo Dry Run.
        *   `--diff`: Mostra as diferenças (o que mudaria nos arquivos de configuração).

3.  **Commit e Push para o Repositório Git Remoto:**
    *   Adicione suas mudanças ao stage: `git add .` (ou arquivos específicos).
    *   Faça o commit com uma mensagem descritiva: `git commit -m "Adiciona configuração para o serviço X e corrige bug Y"`.
    *   Envie para o seu repositório remoto (e.g., GitHub, GitLab): `git push origin main` (ou o nome da sua branch).
    *   Se estiver usando branches, crie um Pull Request/Merge Request para revisar as mudanças antes de mesclar na branch principal.

4.  **Aplicação das Mudanças na Infraestrutura (Deploy):**

    Este é o passo "CD" (Entrega Contínua ou Deploy Contínuo, no nosso caso, mais para Deploy).

    *   **Opção A: Aplicação Manual (Recomendado para Controle Inicial)**
        1.  Na sua máquina de controle Ansible, certifique-se de que seu repositório local está atualizado com a branch principal do remoto:
            ```bash
            git checkout main # Ou sua branch principal
            git pull origin main
            ```
        2.  Execute o playbook Ansible relevante para aplicar as mudanças. Frequentemente, será o playbook mestre `full-deploy.yml` para garantir a consistência de toda a infraestrutura, ou um playbook mais específico se a mudança for isolada.
            ```bash
            ansible-playbook ansible/playbooks/full-deploy.yml --ask-vault-pass
            ```
    *   **Opção B: Aplicação Automatizada (Cron Job - Avançado, com ressalvas)**
        Você pode configurar um cron job na sua máquina de controle Ansible para periodicamente puxar as últimas mudanças do Git e executar o `full-deploy.yml`.
        *   **Script Exemplo (`/opt/homelab_scripts/run_ansible_update.sh` na máquina de controle):**
            ```bash
            #!/bin/bash
            # /opt/homelab_scripts/run_ansible_update.sh

            REPO_PATH="/caminho/completo/para/seu/repo/infra-servidor-domestico"
            LOG_FILE="/var/log/ansible_autodeploy.log"
            # Caminho para o arquivo contendo a senha do Ansible Vault
            # !!! CUIDADO COM A SEGURANÇA DESTE ARQUIVO !!!
            VAULT_PASS_FILE="/home/seu_usuario_ansible/.ansible_vault_pass.txt" # Proteja com chmod 400

            echo "----------------------------------------------------" >> "$LOG_FILE"
            echo "Iniciando atualização da infraestrutura Ansible - $(date)" >> "$LOG_FILE"
            cd "$REPO_PATH" || { echo "ERRO: Diretório do repositório não encontrado: $REPO_PATH" >> "$LOG_FILE"; exit 1; }

            echo "Puxando últimas mudanças do Git..." >> "$LOG_FILE"
            git pull origin main >> "$LOG_FILE" 2>&1
            if [ $? -ne 0 ]; then
                echo "ERRO: Falha ao executar git pull." >> "$LOG_FILE"
                # Adicione notificação aqui se desejar
                exit 1
            fi
            # Opcional: Logar o último commit para rastreabilidade
            git log -1 --pretty=format:"Último commit: %h - %an, %ar : %s" >> "$LOG_FILE"

            echo "Executando playbook full-deploy.yml..." >> "$LOG_FILE"
            # Use --vault-password-file para automação
            ansible-playbook ansible/playbooks/full-deploy.yml --vault-password-file "$VAULT_PASS_FILE" >> "$LOG_FILE" 2>&1
            if [ $? -ne 0 ]; then
                echo "ERRO: Playbook Ansible falhou. Verifique o log completo." >> "$LOG_FILE"
                # Adicione notificação aqui
                exit 1
            fi

            echo "Atualização Ansible concluída com sucesso - $(date)" >> "$LOG_FILE"
            echo "----------------------------------------------------" >> "$LOG_FILE"
            exit 0
            ```
        *   **Agendamento com `cron`:**
            `0 5 * * * /opt/homelab_scripts/run_ansible_update.sh` (Todo dia às 5 AM).
        *   !!! danger "Segurança do Arquivo de Senha do Vault"
            Usar `--vault-password-file` em um script automatizado requer que a senha do vault esteja armazenada em texto plano em um arquivo. **Este arquivo deve ser protegido com permissões muito restritas** (e.g., `chmod 400 arquivo_de_senha` e pertencente ao usuário que roda o cron). Mesmo assim, representa um risco de segurança se a máquina de controle for comprometida. Para ambientes mais críticos, soluções como HashiCorp Vault ou chaves SSH com `ssh-agent` e forwarding (para playbooks que não precisam de vault para *conexão*, mas para *conteúdo*) seriam mais seguras, mas adicionam complexidade.

5.  **Monitoramento Pós-Deploy:**
    *   Após aplicar as mudanças (manual ou automaticamente), verifique os logs dos serviços afetados e o status geral da infraestrutura usando sua [Stack de Monitoramento](../01-manual-implementacao/10-stack-monitoramento.md) para garantir que tudo está funcionando como esperado.

## Playbook `ansible/playbooks/full-deploy.yml` (Orquestrador)

Este playbook é o ponto de entrada principal para garantir que toda a infraestrutura base esteja configurada conforme definido no seu código Ansible.

```yaml
# ansible/playbooks/full-deploy.yml
# Orquestra a configuração completa da infraestrutura base.
# As stacks Docker específicas são implantadas via Portainer após a execução bem-sucedida
# dos playbooks que preparam seus volumes e arquivos .env.

- name: "Etapa 1: Configurar Host Proxmox VE (NFS, Firewall, etc.)"
  ansible.builtin.import_playbook: setup-proxmox-host.yml

- name: "Etapa 2: Provisionar Máquinas Virtuais (core-services-vm, ai-desktop-vm)"
  ansible.builtin.import_playbook: vm-deploy.yml

- name: "Etapa 3: Configurar Base das VMs Ubuntu (Docker, Portainer, NFS Client, GUI opcional)"
  ansible.builtin.import_playbook: setup-base-ubuntu.yml

- name: "Etapa 4: Configurar Stack de Rede Core (Traefik, Cloudflare Tunnel, Authelia)"
  ansible.builtin.import_playbook: setup-core-networking.yml

# Os playbooks abaixo preparam os diretórios NFS e os arquivos .env para o Portainer.
# A implantação real das stacks Docker é feita via Portainer (Seções 6 a 10 do Manual).

- name: "Etapa 5.1: Preparar Volumes e .env para Stack de Mídia"
  ansible.builtin.import_playbook: setup-media-stack-volumes.yml
  when: "'core-services-vm' in groups['virtual_machines']" # Só executa se a VM existir no inventário

- name: "Etapa 5.2: Preparar Volumes e .env para Stacks de Produtividade e Automação"
  ansible.builtin.import_playbook: setup-productivity-automation-volumes.yml
  when: "'core-services-vm' in groups['virtual_machines']"

- name: "Etapa 5.3: Preparar Volumes, .env e Configs para Stack RAG/LLM"
  ansible.builtin.import_playbook: setup-rag-llm-volumes.yml
  when: "'ai-desktop-vm' in groups['virtual_machines']" # Só executa se a VM existir

- name: "Etapa 5.4: Preparar Volumes e .env para Stack de Monitoramento"
  ansible.builtin.import_playbook: setup-monitoring-stack-volumes.yml
  when: "'core-services-vm' in groups['virtual_machines']"

- name: "Conclusão do Deploy da Infraestrutura Base Ansible"
  hosts: localhost # Roda na máquina de controle
  gather_facts: no
  tasks:
    - name: "Mensagem de Conclusão"
      ansible.builtin.debug:
        msg: |
          Deploy da infraestrutura base via Ansible CONCLUÍDO.
          PRÓXIMO PASSO (se for setup inicial ou se as stacks Docker não estiverem rodando):
          Implante as stacks de serviços Docker via Portainer, conforme Seções 6 a 10 do Manual de Implementação.
          Lembre-se de configurar os registros CNAME ou Ingress Rules no DNS da Cloudflare para cada serviço exposto.
          Verifique os logs dos containers no Portainer após o deploy de cada stack.
```

## Script `scripts/restore.sh` (Facilitador para Deploy Completo)

Este script é um wrapper conveniente para executar o `full-deploy.yml`.

```bash
#!/bin/bash
# scripts/restore.sh
# Executa o playbook Ansible 'full-deploy.yml' para configurar a infraestrutura base.
# Assume que o Proxmox VE já está instalado e a máquina de controle Ansible está pronta
# (com 'bootstrap.sh' executado e chaves SSH configuradas).

set -e # Encerra o script imediatamente se um comando falhar.

# Determina o caminho raiz do repositório onde o script está localizado
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)" # Vai um nível acima do diretório do script
ANSIBLE_DIR="${REPO_ROOT}/ansible"

# Localização padrão do arquivo com a senha do Ansible Vault (se não usar --ask-vault-pass)
VAULT_PASS_FILE_DEFAULT="${HOME}/.ansible_vault_pass.txt" # Exemplo

echo "🚀 Iniciando restauração/deploy da infraestrutura base Ansible..."
echo " Repositório Raiz: ${REPO_ROOT}"
echo " Playbooks Ansible em: ${ANSIBLE_DIR}/playbooks"
echo " Inventário Ansible em: ${ANSIBLE_DIR}/inventories/home"

# Permite passar um argumento para o script, como --ask-vault-pass
# ou o caminho para um arquivo de senha do vault diferente.
VAULT_PASS_ARG="$1"
ANSIBLE_CMD_OPTIONS="" # Opções adicionais para o comando ansible-playbook

if [ -z "$VAULT_PASS_ARG" ]; then
    if [ -f "$VAULT_PASS_FILE_DEFAULT" ]; then
        ANSIBLE_CMD_OPTIONS="--vault-password-file ${VAULT_PASS_FILE_DEFAULT}"
        echo "🔐 Usando arquivo de senha do Ansible Vault padrão: ${VAULT_PASS_FILE_DEFAULT}"
    else
        echo "⚠️ Arquivo de senha padrão do Vault ('${VAULT_PASS_FILE_DEFAULT}') não encontrado."
        echo "➡️  O Ansible solicitará a senha do Vault interativamente."
        ANSIBLE_CMD_OPTIONS="--ask-vault-pass"
    fi
elif [ "$VAULT_PASS_ARG" == "--ask-vault-pass" ]; then
    ANSIBLE_CMD_OPTIONS="--ask-vault-pass"
    echo "➡️  O Ansible solicitará a senha do Vault interativamente."
elif [ -f "$VAULT_PASS_ARG" ]; then
    ANSIBLE_CMD_OPTIONS="--vault-password-file $VAULT_PASS_ARG"
    echo "🔐 Usando arquivo de senha do Ansible Vault especificado: $VAULT_PASS_ARG"
else
    echo "❌ ERRO: Argumento para senha do Vault ('$VAULT_PASS_ARG') não é '--ask-vault-pass' nem um arquivo válido."
    echo "   Use '--ask-vault-pass' para digitar a senha, ou forneça um caminho válido para o arquivo de senha."
    exit 1
fi

# Comando para executar o playbook Ansible 'full-deploy.yml'
echo "🛠️  Executando playbook 'full-deploy.yml'..."
# -i especifica o caminho para o diretório de inventário.
# Ansible procurará por ansible.cfg na raiz do projeto ou no diretório atual.
# Se seu ansible.cfg estiver em ansible/, você pode precisar de `cd ansible` antes
# ou especificar o caminho do inventário de forma mais absoluta.
# Assumindo que o playbook é executado da raiz do REPO_ROOT:
ansible-playbook -i "${ANSIBLE_DIR}/inventories/home/" \
                 "${ANSIBLE_DIR}/playbooks/full-deploy.yml" \
                 ${ANSIBLE_CMD_OPTIONS}

echo -e "\n✅ Restauração/deploy da infraestrutura base via Ansible CONCLUÍDA."
echo "➡️  PRÓXIMO PASSO (se setup inicial): Implante as stacks de serviços Docker via Portainer (Seções 6-10 do Manual)."
echo "🔗 LEMBRE-SE de configurar os registros DNS na Cloudflare para cada serviço exposto."
echo "🔎 Verifique os logs dos containers no Portainer após o deploy de cada stack."
```

**Como usar `scripts/restore.sh` para o setup inicial (após `bootstrap.sh` e configuração SSH):**
```bash
# Na raiz do projeto infra-servidor-domestico/
bash scripts/restore.sh # Solicitará a senha do vault interativamente
# Ou, se você criou um arquivo de senha:
# bash scripts/restore.sh /caminho/para/seu/arquivo_de_senha.txt
```

Este fluxo de trabalho básico de CI/CD, mesmo que simplificado, traz disciplina e confiabilidade ao gerenciamento da sua infraestrutura como código.