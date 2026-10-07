# CI/CD Básico para Infraestrutura como Código (Ansible)

Gerenciar sua infraestrutura de servidor doméstico como código (IaC) com Ansible e versioná-la com Git não apenas torna sua configuração repetível e documentada, mas também abre a porta para um fluxo de trabalho similar ao de desenvolvimento de software, incluindo conceitos de Integração Contínua (CI) e Entrega/Deploy Contínuo (CD) – mesmo que de forma simplificada para um ambiente de homelab.

O objetivo principal é ter um processo confiável, testável e, idealmente, automatizável para aplicar mudanças e atualizações na sua infraestrutura.

## Fluxo de Trabalho com Git e Ansible para Gerenciamento de Mudanças

Este é o fluxo de trabalho recomendado ao fazer alterações na sua configuração Ansible:

1.  **Desenvolvimento e Modificação Local (na sua Máquina de Controle Ansible):**
    *   **Branching no Git (Opcional, mas Altamente Recomendado para Mudanças Maiores):**
        Para mudanças significativas, experimentações, ou ao adicionar novas funcionalidades, é uma excelente prática criar uma nova branch no Git antes de começar a editar os arquivos. Isso isola suas mudanças da branch principal (`main` ou `master`) até que você esteja pronto para integrá-las.
        ```bash
        # Na raiz do seu projeto home-server/
        git checkout main  # Certifique-se de estar na branch principal
        git pull origin main # Atualize sua branch principal local
        git checkout -b feature/configurar-novo-servico-X # Crie e mude para uma nova branch
        ```
    *   **Realize as Modificações:**
        Edite seus arquivos Ansible conforme necessário:
        *   Playbooks (`*.yml` em `ansible/playbooks/`)
        *   Roles (tasks, templates `.j2`, handlers, defaults, vars em `ansible/roles/NOME_DO_ROLE/`)
        *   Inventário (`ansible/inventories/home/hosts.ini`)
        *   Variáveis de grupo (`ansible/inventories/home/group_vars/all/main.yml` ou `vault.yml` - use `ansible-vault edit` para este último)

2.  **Teste Local das Mudanças Ansible (CI - Integração Contínua Simplificada):**
    Antes de aplicar as mudanças no seu ambiente de "produção" (seu servidor doméstico), teste o máximo possível localmente na sua máquina de controle. Isso é a nossa forma de "Integração Contínua" simplificada.
    *   **Linting (Verificação de Sintaxe e Estilo):**
        Ferramentas de linting ajudam a pegar erros de sintaxe, inconsistências e más práticas antes mesmo de executar o código.
        *   **`ansible-lint`:** Analisa seus playbooks e roles Ansible.
            ```bash
            # Instale se ainda não tiver: pip install ansible-lint
            # Rode na raiz do seu diretório ansible/ ou em arquivos/diretórios específicos
            ansible-lint ansible/playbooks/meu_playbook_modificado.yml
            ansible-lint ansible/roles/meu_role_modificado/
            ```
        *   **`yamllint`:** Verifica a sintaxe de todos os seus arquivos YAML (playbooks, vars, etc.).
            ```bash
            # Instale se ainda não tiver: pip install yamllint
            # Pode ser rodado na raiz do projeto para verificar todos os YAMLs
            yamllint .
            ```
    *   **Syntax Check do Ansible:**
        O próprio Ansible pode verificar a sintaxe dos seus playbooks.
        ```bash
        ansible-playbook ansible/playbooks/meu_playbook_modificado.yml --syntax-check
        ```
    *   **Dry Run (Modo de Verificação `--check`):**
        Este é um passo crucial. O modo `--check` simula a execução do playbook sem fazer alterações reais nos seus sistemas. Use junto com `--diff` para ver quais mudanças *seriam* feitas.
        ```bash
        ansible-playbook ansible/playbooks/meu_playbook_modificado.yml --check --diff --ask-vault-pass
        ```
        *   `--check`: Ativa o modo Dry Run.
        *   `--diff`: Mostra as diferenças (o que mudaria nos arquivos de configuração ou estado dos serviços).
        Analise a saída cuidadosamente para garantir que as mudanças propostas são as que você espera.

3.  **Commit e Push das Mudanças para o Repositório Git Remoto:**
    Uma vez que você está satisfeito com seus testes locais:
    *   Adicione suas mudanças ao "stage" do Git:
        ```bash
        git add .  # Adiciona todas as mudanças no diretório de trabalho
        # Ou adicione arquivos específicos:
        # git add ansible/playbooks/meu_playbook_modificado.yml ansible/roles/meu_role_modificado/
        ```
    *   Faça o commit das mudanças com uma mensagem clara e descritiva:
        ```bash
        git commit -m "Feature: Adiciona configuração para o serviço X e otimiza role Y"
        # Ou, se for uma correção:
        # git commit -m "Fix: Corrige bug na task de configuração do firewall"
        ```
    *   Envie suas mudanças para o seu repositório Git remoto (e.g., GitHub, GitLab):
        ```bash
        git push origin feature/configurar-novo-servico-X # Envia a sua branch
        ```
    *   **Pull Request / Merge Request (Se estiver usando branches e/ou colaborando):**
        Se você trabalhou em uma feature branch, agora é o momento de criar um Pull Request (GitHub) ou Merge Request (GitLab) no seu repositório remoto. Isso permite uma revisão das suas mudanças (por você mesmo ou por outros, se aplicável) antes de mesclá-las na branch principal (`main`).

4.  **Aplicação das Mudanças na Infraestrutura (CD - Deploy Contínuo ou Controlado):**
    Este é o passo de "Entrega Contínua" ou, mais realisticamente para um homelab, "Deploy Controlado".

    *   **Opção A: Aplicação Manual (Recomendado para a Maioria dos Homelabs para Máximo Controle):**
        1.  **Sincronize sua Máquina de Controle:** Na sua máquina de controle Ansible, certifique-se de que seu repositório local está na branch principal (`main`) e atualizado com as últimas mudanças do repositório remoto (que agora incluem suas alterações mescladas).
            ```bash
            git checkout main
            git pull origin main
            ```
        2.  **Execute o Playbook Ansible Relevante:**
            Execute o playbook Ansible que aplica as mudanças que você fez. Frequentemente, para garantir a consistência de toda a infraestrutura, pode ser o playbook mestre `full-deploy.yml`. Se a mudança for muito isolada e você tiver certeza do seu escopo, pode executar um playbook mais específico.
            ```bash
            ansible-playbook ansible/playbooks/full-deploy.yml --ask-vault-pass
            # Ou, se a mudança foi apenas no setup-core-networking.yml:
            # ansible-playbook ansible/playbooks/setup-core-networking.yml --ask-vault-pass
            ```
    *   **Opção B: Aplicação Automatizada via Cron Job (Avançado - Use com Cautela):**
        Você pode configurar um `cron` job na sua máquina de controle Ansible para, periodicamente (e.g., diariamente em um horário de baixa atividade), puxar as últimas mudanças da branch `main` do seu repositório Git e executar automaticamente o playbook `full-deploy.yml`.
        *   **Exemplo de Script (`/opt/homelab_scripts/run_ansible_autodeploy.sh` na máquina de controle):**
            ```bash
            #!/bin/bash
            # /opt/homelab_scripts/run_ansible_autodeploy.sh

            REPO_PATH="/caminho/completo/para/seu/repo/home-server" # Ajuste este caminho!
            LOG_FILE="/var/log/ansible_autodeploy.log"
            # Caminho para o arquivo contendo a senha do Ansible Vault.
            # !!! CUIDADO MÁXIMO COM A SEGURANÇA DESTE ARQUIVO !!!
            VAULT_PASS_FILE="/home/seu_usuario_ansible_control/.ansible_vault_pass.txt" # Proteja com chmod 400 ou 600

            # Função para logar com timestamp
            log_msg() {
                echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
            }

            log_msg "----------------------------------------------------"
            log_msg "Iniciando auto-deploy da infraestrutura Ansible..."
            cd "$REPO_PATH" || { log_msg "ERRO: Diretório do repositório não encontrado: $REPO_PATH"; exit 1; }

            log_msg "Verificando branch atual e puxando últimas mudanças do Git (branch main)..."
            CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
            if [ "$CURRENT_BRANCH" != "main" ]; then # Ou sua branch principal
                log_msg "AVISO: Não está na branch 'main'. Tentando checkout para 'main'."
                git checkout main >> "$LOG_FILE" 2>&1
                if [ $? -ne 0 ]; then
                    log_msg "ERRO: Falha ao fazer checkout para a branch 'main'."
                    exit 1
                fi
            fi
            git pull origin main >> "$LOG_FILE" 2>&1
            if [ $? -ne 0 ]; then
                log_msg "ERRO: Falha ao executar git pull na branch 'main'."
                exit 1
            fi
            git log -1 --pretty=format:"Último commit para deploy: %h - %an, %ar : %s" >> "$LOG_FILE"

            log_msg "Executando playbook 'full-deploy.yml'..."
            # Use --vault-password-file para automação.
            # Adicione -i para especificar o inventário se não estiver no ansible.cfg
            ansible-playbook "${REPO_PATH}/ansible/playbooks/full-deploy.yml" \
                             -i "${REPO_PATH}/ansible/inventories/home/" \
                             --vault-password-file "$VAULT_PASS_FILE" >> "$LOG_FILE" 2>&1
            ANSIBLE_EXIT_CODE=$?

            if [ ${ANSIBLE_EXIT_CODE} -ne 0 ]; then
                log_msg "ERRO: Playbook Ansible falhou com código de saída ${ANSIBLE_EXIT_CODE}. Verifique o log completo."
                # Adicione aqui um mecanismo de notificação (e.g., enviar email, mensagem no Discord/Telegram)
                exit 1
            fi

            log_msg "Auto-deploy Ansible concluído com sucesso."
            log_msg "----------------------------------------------------"
            exit 0
            ```
        *   **Agendamento com `cron` (e.g., `crontab -e`):**
            `0 5 * * * /opt/homelab_scripts/run_ansible_autodeploy.sh` (Executa todo dia às 5 AM).
        *   !!! danger "Riscos da Automação Total e Segurança do Arquivo de Senha do Vault"
            Automatizar completamente o deploy com `cron` é conveniente, mas introduz riscos:
            *   **Segurança do Arquivo de Senha:** Armazenar a senha do Ansible Vault em texto plano em um arquivo (`VAULT_PASS_FILE`) é um risco de segurança. Esse arquivo deve ter permissões extremamente restritas (e.g., `chmod 400` ou `600`, e ser propriedade apenas do usuário que roda o cron). Se a máquina de controle for comprometida, a senha do vault também será.
            *   **Deploy de Mudanças Quebradiças:** Se uma mudança com erro for mesclada na branch `main`, o cron job a aplicará automaticamente, podendo quebrar sua infraestrutura sem intervenção manual imediata.
            *   Para ambientes mais críticos (mesmo homelabs se você depende muito deles), um "deploy controlado" (manual após revisão) é geralmente mais seguro. Se optar pela automação, invista em testes robustos (Molecule, etc.) e um bom sistema de notificação de falhas.

5.  **Monitoramento Pós-Deploy:**
    *   Independentemente de o deploy ser manual ou automatizado, após a aplicação das mudanças Ansible, **sempre verifique:**
        *   Os logs dos serviços que foram modificados.
        *   A funcionalidade das aplicações afetadas.
        *   O status geral da sua infraestrutura usando o Grafana/Prometheus (veja [Deploy de Apps](../01-manual-implementacao/07-deploy-apps.md)).

## Playbook `ansible/playbooks/full-deploy.yml` (O Orquestrador Principal)

Este playbook é o ponto de entrada principal para garantir que toda a sua infraestrutura base (configuração do host Proxmox, VMs, Docker, rede core, preparação de volumes para stacks) esteja configurada conforme definido no seu código Ansible. Ele importa e executa os outros playbooks de setup em uma sequência lógica.

```yaml
# ansible/playbooks/full-deploy.yml
# Orquestra a configuração completa da infraestrutura.

- import_playbook: setup-proxmox-host.yml
- import_playbook: setup-base-ubuntu.yml
- import_playbook: setup-core-networking.yml
- import_playbook: setup-media-stack-volumes.yml
- import_playbook: setup-n8n-volumes.yml
- import_playbook: setup-ai-volumes.yml
```

## Script `scripts/restore.sh` (Facilitador para Deploy Completo com Ansible)

Este script é um wrapper conveniente para executar o playbook `full-deploy.yml`, especialmente útil para o setup inicial ou para garantir que toda a infraestrutura gerenciada pelo Ansible esteja no estado desejado.

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

**Como usar `scripts/restore.sh` para o setup inicial (após o `bootstrap.sh` na máquina de controle e a configuração SSH inicial no host Proxmox):**
```bash
# Navegue para a raiz do seu projeto home-server/ na máquina de controle
bash scripts/restore.sh # Por padrão, solicitará a senha do vault interativamente
# Ou, se você criou um arquivo de senha do vault (e.g., ~/.ansible_vault_pass.txt):
# bash scripts/restore.sh ~/.ansible_vault_pass.txt
```

Este fluxo de trabalho básico de CI/CD, mesmo que simplificado para um ambiente de homelab (com mais foco no "D" de Deploy do que no "CI" formal), traz uma disciplina valiosa, aumenta a confiabilidade e torna o gerenciamento da sua infraestrutura como código muito mais robusto e rastreável.