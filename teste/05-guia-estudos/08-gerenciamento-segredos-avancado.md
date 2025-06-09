# Gerenciamento Avançado de Segredos

No manual de implementação, utilizamos o [Ansible Vault](../01-manual-implementacao/01-maquina-controle-ansible.md#12-criação-e-gerenciamento-de-variáveis-sensíveis-ansible-vault) para criptografar segredos usados pela automação Ansible, e definimos segredos específicos de aplicações Docker diretamente como variáveis de ambiente no Portainer. Embora isso funcione bem para um homelab, à medida que sua infraestrutura cresce em complexidade ou se você começar a colaborar com outros, podem surgir necessidades de gerenciamento de segredos mais robustas e centralizadas.

Esta seção introduz duas abordagens mais avançadas: HashiCorp Vault e SOPS.

!!! warning "Complexidade Adicional"
    Ambas as soluções adicionam uma nova camada de software e complexidade ao seu setup. Avalie se os benefícios superam o custo de gerenciamento para seu caso de uso específico no homelab. Para a maioria dos homelabs, Ansible Vault + secrets de ambiente no orquestrador (Portainer, Kubernetes Secrets) é suficiente.

## 1. HashiCorp Vault

[HashiCorp Vault](https://www.vaultproject.io/) é uma ferramenta poderosa e popular para gerenciar segredos e proteger dados sensíveis de forma centralizada. Ele pode armazenar senhas, tokens de API, certificados, chaves de criptografia e muito mais.

*   **Principais Funcionalidades:**
    *   **Armazenamento Seguro de Segredos:** Segredos são criptografados em repouso (e em trânsito).
    *   **Controle de Acesso Granular:** Políticas detalhadas definem quem ou o quê (aplicações, usuários Ansible) pode acessar quais segredos.
    *   **Leases Dinâmicos e Renovação:** Vault pode gerar credenciais dinâmicas para bancos de dados, provedores de nuvem, etc., que expiram automaticamente, reduzindo o risco de credenciais de longa duração comprometidas.
    *   **Auditoria:** Logs detalhados de quem acessou quais segredos e quando.
    *   **Múltiplos Backends de Armazenamento:** Pode usar diferentes backends para armazenar os dados criptografados (e.g., sistema de arquivos local, Consul, S3, etc.).
    *   **Múltiplos Métodos de Autenticação:** Aplicações e usuários podem se autenticar no Vault usando tokens, AppRole, certificados, LDAP, Kubernetes Service Accounts, etc.
    *   **Motores de Segredos (Secrets Engines):** Além de armazenar segredos chave/valor, possui motores para PKI (gerar certificados), bancos de dados (credenciais dinâmicas), SSH, etc.

*   **Como Funciona (Visão Geral):**
    1.  **Servidor Vault:** Você roda um servidor Vault (pode ser um container Docker ou um binário).
    2.  **Inicialização e "Unsealing":** Na primeira vez, o Vault é inicializado, gerando chaves de recuperação (shard keys). Para "abrir" (unseal) o Vault após um reinício, um quórum dessas chaves precisa ser fornecido. Isso garante que o Vault não possa ser acessado apenas com o roubo do storage.
    3.  **Autenticação:** Clientes (usuários, scripts Ansible, aplicações) se autenticam no Vault.
    4.  **Políticas:** Políticas definem quais caminhos de segredos o cliente autenticado pode acessar e com quais permissões (read, write, list, delete).
    5.  **Acesso a Segredos:** Clientes leem ou escrevem segredos nos caminhos permitidos.

*   **Integração com Ansible:**
    *   Ansible tem um [lookup plugin `hashi_vault`](https://docs.ansible.com/ansible/latest/collections/community/hashi_vault/hashi_vault_lookup.html) que permite que playbooks busquem segredos diretamente do HashiCorp Vault em tempo de execução.
        ```yaml
        # Exemplo em um playbook Ansible
        vars:
          db_password: "{{ lookup('community.hashi_vault.hashi_vault', 'secret=secret/data/myapp/db:password token={{ vault_token }} url={{ vault_addr }}') }}"
        # vault_token e vault_addr seriam passados como extra_vars ou variáveis de ambiente para o ansible-playbook.
        ```
    *   Isso evita armazenar os segredos diretamente no Ansible Vault, usando o HashiCorp Vault como a fonte da verdade centralizada.

*   **Rodando Vault em um Homelab:**
    *   **Modo de Desenvolvimento (`vault server -dev`):** Ótimo para aprendizado e testes. Inicia rapidamente, armazena dados em memória (perde ao parar) e é auto-unsealed. **NÃO USE PARA PRODUÇÃO DE SEGREDOS REAIS.**
    *   **Servidor Standalone (Backend File):** Você pode rodar um servidor Vault com um backend de sistema de arquivos local (criptografado). Precisa gerenciar o processo de unsealing.
        ```hcl
        // Exemplo de config básica do Vault (vault_config.hcl)
        storage "file" {
          path = "/vault/data" // Diretório onde os dados criptografados são armazenados
        }

        listener "tcp" {
          address     = "0.0.0.0:8200"
          tls_disable = true // Para homelab local, pode desabilitar TLS para o listener do Vault,
                             // mas use um proxy reverso com TLS na frente se expor.
        }

        api_addr = "http://127.0.0.1:8200" // Como o Vault se anuncia
        ui = true // Habilita a UI web
        ```
    *   **Container Docker:** Existem imagens Docker oficiais para Vault. Você precisará gerenciar a persistência dos dados e o unsealing.

*   **Desafios:**
    *   **Unsealing:** O processo de unsealing pode ser manual ou automatizado (e.g., usando um KMS na nuvem ou um serviço de HSM, que é overkill para homelab). Para homelab, o unsealing manual após reinícios é comum.
    *   **Gerenciamento de Tokens e Políticas:** Configurar autenticação e políticas corretamente requer aprendizado.
    *   **Backup do Vault:** O backend de armazenamento do Vault precisa ser backupeado de forma segura.

!!! tip "Quando Considerar HashiCorp Vault?"
    *   Se você tem muitos segredos espalhados e quer um local central e seguro.
    *   Se precisa de auditoria detalhada de acesso a segredos.
    *   Se quer gerar credenciais dinâmicas.
    *   Se está aprendendo para uso profissional.

## 2. SOPS (Secrets OPerationS)

[SOPS](https://github.com/mozilla/sops) é uma ferramenta de linha de comando de código aberto que permite criptografar arquivos YAML, JSON, ENV, INI e binários. A principal vantagem é que os arquivos criptografados **podem ser commitados de forma segura no Git**, e os segredos são descriptografados apenas em tempo de execução ou quando necessário.

*   **Como Funciona:**
    *   SOPS usa um ou mais "Key Management Services" (KMS) ou chaves PGP/GPG ou Age para criptografar e descriptografar os dados.
    *   **PGP/GPG:** Você pode usar sua chave GPG pessoal (ou chaves de membros da equipe) para criptografar o arquivo. Apenas quem tem acesso à chave privada GPG correspondente pode descriptografar.
    *   **Age:** Um sistema de criptografia moderno e simples, similar ao PGP em conceito, usando pares de chaves.
    *   **Cloud KMS (AWS KMS, GCP KMS, Azure Key Vault):** Para ambientes de nuvem.
    *   Um arquivo `.sops.yaml` na raiz do seu projeto define quais chaves são usadas para criptografar quais arquivos (usando padrões de glob).

*   **Fluxo de Trabalho com SOPS e Git:**
    1.  **Instale SOPS** e o backend de chave desejado (e.g., GPG, Age).
    2.  **Crie um arquivo `.sops.yaml`** para configurar as regras de criptografia.
        ```yaml
        # Exemplo .sops.yaml
        creation_rules:
          - path_regex: .*.secret\.yaml$ # Criptografa arquivos terminando com .secret.yaml
            pgp: 'FINGERPRINT_DA_SUA_CHAVE_GPG,FINGERPRINT_CHAVE_COLEGA'
            # ou age: 'AGE_PUBLIC_KEY_1,AGE_PUBLIC_KEY_2'
          - path_regex: ansible/inventories/home/group_vars/all/vault\.sops\.yml
            # Poderia usar SOPS para criptografar o que seria o conteúdo do Ansible Vault
            pgp: 'FINGERPRINT_DA_SUA_CHAVE_GPG'
        ```
    3.  **Crie um arquivo de segredos** (e.g., `meus_segredos.secret.yaml`):
        ```yaml
        # meus_segredos.secret.yaml
        db_user: "admin"
        db_password: "SENHA_SUPER_SECRETA" # Este valor será criptografado
        api_key: "outra_coisa_secreta"
        ```
    4.  **Criptografe o arquivo com SOPS:**
        ```bash
        sops --encrypt --in-place meus_segredos.secret.yaml
        # ou para editar de forma criptografada:
        # sops meus_segredos.secret.yaml
        ```
        O arquivo agora conterá os valores criptografados, mas a estrutura (chaves) permanecerá visível.
    5.  **Commit o arquivo criptografado no Git.**
    6.  **Descriptografar em Tempo de Execução:**
        *   **Ansible:** Existe um [lookup plugin `sops`](https://github.com/crivetimihai/ansible-sops) ou você pode usar `sops --decrypt` em uma task `command` e registrar a saída.
            ```yaml
            # Exemplo com lookup plugin de terceiros (requer instalação)
            # vars:
            #   segredos: "{{ lookup('sops', 'meus_segredos.secret.yaml') }}"
            #   db_password: "{{ segredos.db_password }}"

            # Exemplo com comando:
            - name: Descriptografar segredos com SOPS
              ansible.builtin.command: "sops --decrypt /caminho/para/meus_segredos.secret.yaml"
              register: sops_output
              changed_when: false
              check_mode: no # Para rodar mesmo em --check

            - name: Carregar segredos descriptografados
              ansible.builtin.set_fact:
                segredos: "{{ sops_output.stdout | from_yaml }}"
              when: sops_output.rc == 0

            - name: Usar o segredo
              ansible.builtin.debug:
                msg: "A senha do DB é {{ segredos.db_password }}"
            ```
        *   **Docker Compose / Scripts:** Você pode usar `sops exec-file` para injetar segredos como variáveis de ambiente para um comando:
            ```bash
            sops exec-file meus_segredos.secret.yaml \
              'docker compose -e DB_PASSWORD={= db_password =} up'
            # {= db_password =} é a sintaxe para injetar o valor descriptografado.
            ```

*   **Vantagens do SOPS:**
    *   Segredos podem ser versionados no Git de forma segura.
    *   Descentralizado (não requer um servidor Vault rodando).
    *   Bom para colaboração se as chaves GPG/Age forem compartilhadas corretamente.
    *   Integração com Git hooks para criptografar/descriptografar automaticamente em commits/checkouts.
*   **Desafios:**
    *   Gerenciamento das chaves GPG/Age (distribuição, revogação).
    *   A estrutura do arquivo (chaves YAML/JSON) é visível no arquivo criptografado, apenas os valores são secretos.

!!! tip "SOPS vs. Ansible Vault"
    *   **Ansible Vault:** Criptografa o arquivo inteiro. Mais simples para uso exclusivo com Ansible. A senha do vault é o único segredo a ser gerenciado.
    *   **SOPS:** Criptografa valores dentro de um arquivo, mantendo a estrutura. Mais flexível para usar os mesmos arquivos de segredos com outras ferramentas além do Ansible. Requer gerenciamento de chaves PGP/Age.
    Você pode até usar SOPS para criptografar o arquivo que seria seu `ansible/inventories/home/group_vars/all/vault.yml`, e depois usar `sops --decrypt` para passar o conteúdo para `ansible-playbook --vault-password-file /dev/stdin`.

## Escolhendo a Ferramenta Certa

*   **Para a maioria dos homelabs individuais, Ansible Vault é suficiente e bem integrado.**
*   **Considere HashiCorp Vault se:**
    *   Você quer um sistema centralizado com UI, auditoria, e credenciais dinâmicas.
    *   Você está disposto a gerenciar o servidor Vault e o processo de unsealing.
    *   Você precisa de integrações com muitos sistemas diferentes ou está preparando para ambientes empresariais.
*   **Considere SOPS se:**
    *   Você quer versionar seus segredos no Git de forma criptografada.
    *   Você trabalha em equipe e o gerenciamento de chaves GPG/Age é viável.
    *   Você precisa que os mesmos arquivos de segredos sejam facilmente consumidos por múltiplas ferramentas (Ansible, scripts, Docker Compose com `sops exec-file`).

Ambas as ferramentas representam um passo significativo em relação ao armazenamento de segredos em texto plano ou apenas com Ansible Vault se a senha do vault for compartilhada de forma insegura.