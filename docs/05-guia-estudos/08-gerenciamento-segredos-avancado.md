# Gerenciamento Avançado de Segredos: HashiCorp Vault e SOPS

No [Manual de Implementação](../01-manual-implementacao/index.md), utilizamos principalmente duas estratégias para o gerenciamento de segredos:
1.  **Ansible Vault:** Para criptografar o arquivo `vault.yml` que contém segredos usados pela automação Ansible (e.g., senhas de API, senhas de banco de dados para setup inicial).
2.  **Variáveis de Ambiente no Portainer:** Para injetar segredos específicos de aplicações (como senhas de banco de dados que os containers usam em tempo de execução) diretamente na configuração da stack no Portainer.

Embora essa abordagem seja funcional e razoavelmente segura para um homelab individual (especialmente se a senha do Ansible Vault for forte e o acesso ao Portainer for bem protegido), à medida que sua infraestrutura cresce em complexidade, se você começar a colaborar com outros, ou se tiver requisitos de segurança e auditoria mais rigorosos, podem surgir necessidades de um gerenciamento de segredos mais robusto, centralizado e com controle de acesso granular.

Esta seção introduz duas ferramentas populares para gerenciamento avançado de segredos: **HashiCorp Vault** e **Mozilla SOPS**.

!!! warning "Complexidade Adicional vs. Benefício"
    Ambas as soluções aqui apresentadas, HashiCorp Vault e SOPS, adicionam uma **nova camada de software, configuração e complexidade** ao seu setup. Avalie cuidadosamente se os benefícios de segurança e gerenciamento que elas oferecem superam o custo de aprendizado e manutenção para o seu caso de uso específico no homelab. Para a maioria dos homelabs, a combinação de Ansible Vault com a definição de secrets diretamente no orquestrador de containers (Portainer, Kubernetes Secrets) pode ser perfeitamente adequada.

## 1. HashiCorp Vault: Gerenciamento Centralizado de Segredos

[**HashiCorp Vault**](https://www.vaultproject.io/) (frequentemente chamado apenas de "Vault") é uma ferramenta de código aberto extremamente poderosa e popular para gerenciar segredos e proteger dados sensíveis de forma centralizada e segura. Ele pode armazenar senhas, tokens de API, certificados TLS, chaves de criptografia e muito mais.

*   **Principais Funcionalidades e Vantagens:**
    *   **Armazenamento Seguro e Criptografado:** Segredos são criptografados em repouso (no backend de armazenamento do Vault) e em trânsito (comunicação com o Vault via TLS).
    *   **Controle de Acesso Granular (Políticas):** Vault utiliza um sistema de políticas detalhadas para definir quem ou o quê (usuários, aplicações, scripts Ansible) pode acessar quais "caminhos" de segredos e com quais permissões (ler, escrever, listar, deletar, etc.).
    *   **Leases Dinâmicos e Renovação Automática de Segredos:** Uma das features mais poderosas. Vault pode gerar credenciais **dinâmicas e de curta duração** para acesso a bancos de dados, provedores de nuvem (AWS, Azure, GCP), e outros sistemas. Essas credenciais expiram automaticamente, reduzindo drasticamente o risco associado a credenciais de longa duração comprometidas. Vault também pode renovar leases para segredos.
    *   **Auditoria Detalhada:** Vault mantém logs de auditoria detalhados registrando quem acessou quais segredos, quando, e quais operações foram realizadas.
    *   **Múltiplos Backends de Armazenamento:** Vault não armazena os segredos descriptografados diretamente. Ele usa um backend de armazenamento para guardar os dados criptografados. Pode usar diversos backends, como:
        *   Sistema de arquivos local (criptografado pelo Vault).
        *   Consul (outro produto da HashiCorp).
        *   Bancos de dados (PostgreSQL, MySQL).
        *   Armazenamento em nuvem (Amazon S3, Google Cloud Storage, Azure Blob Storage).
    *   **Múltiplos Métodos de Autenticação:** Clientes (usuários, aplicações, máquinas) podem se autenticar no Vault usando uma variedade de métodos:
        *   Tokens (o método base).
        *   AppRole (para autenticação de máquinas/aplicações).
        *   Certificados TLS.
        *   Provedores de identidade como LDAP, Kubernetes Service Accounts, GitHub, AWS IAM, GCP GCE.
    *   **Motores de Segredos (Secrets Engines):** Além de um simples armazenamento chave/valor (`kv`), Vault possui "motores de segredos" especializados para diferentes tipos de segredos:
        *   `pki`: Para gerar e gerenciar certificados TLS (pode atuar como uma CA interna).
        *   `database`: Para gerar credenciais dinâmicas para bancos de dados.
        *   `ssh`: Para gerenciar acesso SSH (e.g., senhas de uso único).
        *   `aws`, `gcp`, `azure`: Para credenciais dinâmicas de provedores de nuvem.
        *   `transit`: Para criptografia como serviço (encrypt/decrypt data without storing it).

*   **Como Funciona o Vault (Visão Geral Simplificada):**
    1.  **Servidor Vault:** Você roda uma ou mais instâncias do servidor Vault (pode ser um container Docker, um binário nativo, ou em um cluster para alta disponibilidade).
    2.  **Inicialização e "Unsealing" (Deslacrar):**
        *   Na primeira vez que o Vault é iniciado com um novo backend de armazenamento, ele precisa ser **inicializado**. Este processo gera uma chave de criptografia mestra (master key) e um conjunto de **chaves de recuperação (shard keys ou unseal keys)** – geralmente 5 chaves, onde um quórum (e.g., 3 de 5) é necessário para "deslacrar" o Vault.
        *   Sempre que o servidor Vault é reiniciado (ou iniciado pela primeira vez após a inicialização), ele começa em um estado **"selado" (sealed)**. Neste estado, ele sabe onde seus dados estão, mas não como descriptografá-los.
        *   Para torná-lo operacional, ele precisa ser **"deslacrado" (unsealed)** fornecendo o número necessário de unseal keys. Isso garante que, mesmo que um invasor obtenha acesso ao backend de armazenamento do Vault, ele não poderá ler os segredos sem as unseal keys.
    3.  **Autenticação no Vault:** Clientes (usuários, scripts Ansible, aplicações Docker) precisam se autenticar no Vault usando um dos métodos configurados para obter um **token do Vault**. Este token tem políticas associadas.
    4.  **Políticas de Acesso:** Administradores do Vault definem políticas (escritas em HCL - HashiCorp Configuration Language) que especificam quais caminhos de segredos um token (ou uma entidade autenticada) pode acessar e com quais capacidades (`read`, `write`, `list`, `delete`, `sudo`).
    5.  **Acesso a Segredos:** Com um token válido e as permissões apropriadas, os clientes podem ler ou escrever segredos nos caminhos permitidos usando a API HTTP do Vault, a CLI do Vault, ou bibliotecas cliente.

*   **Integração do HashiCorp Vault com Ansible:**
    *   Ansible possui um **lookup plugin `community.hashi_vault.hashi_vault`** (parte da coleção `community.hashi_vault`) que permite que seus playbooks busquem segredos diretamente do HashiCorp Vault em tempo de execução.
        ```yaml
        # Exemplo de uso em um playbook Ansible
        vars:
          # Busca o valor da chave 'password' do segredo localizado em 'secret/data/minha_app/db' no Vault.
          # As variáveis vault_token e vault_addr precisariam ser passadas para o ansible-playbook
          # como extra_vars, variáveis de ambiente (VAULT_TOKEN, VAULT_ADDR), ou configuradas no ansible.cfg.
          db_password_from_hashicorp: "{{ lookup('community.hashi_vault.hashi_vault', 'secret=secret/data/minha_app/db:password token={{ meu_vault_token }} url={{ meu_vault_addr }}') }}"
        tasks:
          - name: "Debug: Mostrar senha do DB obtida do HashiCorp Vault"
            ansible.builtin.debug:
              msg: "A senha do DB (do HashiCorp Vault) é: {{ db_password_from_hashicorp }}"
            no_log: true # Importante para não logar o segredo!
        ```
    *   Esta abordagem permite que o HashiCorp Vault seja a fonte central da verdade para seus segredos, e o Ansible Vault pode não ser mais necessário para armazenar esses segredos específicos (embora a senha para o `meu_vault_token` possa, ironicamente, ainda vir do Ansible Vault ou de uma variável de ambiente protegida).

*   **Rodando HashiCorp Vault em um Homelab:**
    *   **Modo de Desenvolvimento (`vault server -dev`):**
        *   Excelente para aprendizado rápido e testes. Inicia um servidor Vault em memória, auto-unsealed, com um token root pré-gerado.
        *   **NÃO USE PARA ARMAZENAR SEGREDOS REAIS DE PRODUÇÃO**, pois todos os dados são perdidos quando o processo para.
    *   **Servidor Vault Standalone (com Backend de Arquivo ou Docker):**
        1.  **Backend de Arquivo:** Você pode rodar um servidor Vault "real" configurando-o para usar o sistema de arquivos local como backend de armazenamento (os dados serão criptografados pelo Vault).
            Exemplo de arquivo de configuração básico (`vault_config.hcl`):
            ```hcl
            # vault_config.hcl
            storage "file" {
              path = "/opt/vault/data" // Diretório onde os dados criptografados do Vault serão armazenados
            }

            listener "tcp" {
              address     = "0.0.0.0:8200" // Vault escutará em todas as interfaces na porta 8200
              tls_disable = true // Para um homelab local, você PODE desabilitar TLS para o listener do Vault,
                                 // mas se for expor a UI ou API do Vault (mesmo que internamente via Traefik),
                                 // é ALTAMENTE RECOMENDADO colocar um proxy reverso com TLS na frente.
            }

            api_addr = "http://IP_DA_VM_DO_VAULT:8200" // Como o Vault se anuncia para clientes e na UI
            ui = true // Habilita a interface web do Vault (acessível em http://IP:8200/ui)
            ```
            Você iniciaria o Vault com `vault server -config=vault_config.hcl`.
        2.  **Container Docker:** Existem imagens Docker oficiais para Vault ([`hashicorp/vault`](https://hub.docker.com/r/hashicorp/vault)). Você precisará:
            *   Mapear um volume persistente para `/vault/data` (para o storage) e `/vault/config` (para o `vault_config.hcl`).
            *   Passar capabilities como `IPC_LOCK` para o container (para evitar que a memória do Vault seja enviada para swap).
            *   Gerenciar o processo de **unsealing** do container após cada reinício.
    *   **Gerenciamento do Unsealing:**
        *   Este é um dos maiores desafios operacionais do Vault em qualquer ambiente. Para um homelab, o unsealing manual (fornecendo as unseal keys via CLI ou API após cada reinício do servidor Vault) é a abordagem mais comum.
        *   Soluções de auto-unseal (e.g., usando um KMS de nuvem, Transit Secrets Engine do próprio Vault, ou HSMs) são geralmente overkill e complexas para homelab.

*   **Desafios do HashiCorp Vault em Homelab:**
    *   **Unsealing:** O processo de unsealing manual pode ser inconveniente após reinícios do servidor.
    *   **Gerenciamento de Tokens e Políticas:** Configurar corretamente os métodos de autenticação e as políticas de acesso requer um bom entendimento do Vault e pode ser complexo.
    *   **Backup do Backend do Vault:** O backend de armazenamento do Vault (e.g., o diretório `/opt/vault/data` se usar backend file) precisa ser backupeado de forma segura e regular.
    *   **Recursos:** Embora o Vault em si não seja extremamente pesado, ele adiciona outro serviço para gerenciar e monitorar.

!!! tip "Quando Considerar Usar HashiCorp Vault no Seu Homelab?"
    *   Se você tem um **grande número de segredos** espalhados por vários arquivos ou sistemas e deseja um local centralizado, seguro e auditável para gerenciá-los.
    *   Se você precisa de **controle de acesso granular** a diferentes segredos para diferentes aplicações ou scripts.
    *   Se você está interessado em **credenciais dinâmicas** para bancos de dados ou outros serviços.
    *   Se você está **aprendendo Vault para fins profissionais**, pois é uma ferramenta amplamente usada na indústria.
    *   Se a ideia de **unsealing manual** após reinícios do servidor Vault não te assusta.

## 2. Mozilla SOPS (Secrets OPerationS)

[**SOPS (Secrets OPerationS)**](https://github.com/mozilla/sops) é uma ferramenta de linha de comando de código aberto, desenvolvida pela Mozilla, que oferece uma abordagem diferente para o gerenciamento de segredos: ela permite **criptografar valores dentro de arquivos de dados estruturados (YAML, JSON, ENV, INI) ou arquivos binários**.

A principal vantagem desta abordagem é que os arquivos de configuração contendo segredos criptografados pelo SOPS **podem ser commitados de forma segura em um repositório Git**. Os segredos são descriptografados apenas em tempo de execução ou quando um usuário/processo autorizado precisa acessá-los.

*   **Como o SOPS Funciona:**
    *   SOPS utiliza um ou mais **sistemas de gerenciamento de chaves (KMS)** ou **chaves criptográficas assíncronas** (como PGP/GPG ou Age) para criptografar e descriptografar os dados dentro dos arquivos.
    *   **PGP/GPG:** Você pode usar sua chave GPG pessoal (ou as chaves GPG de membros da sua equipe) para criptografar o arquivo. Apenas alguém que possua uma das chaves privadas GPG correspondentes (e sua passphrase, se a chave privada for protegida) pode descriptografar os valores.
    *   **Age:** Um sistema de criptografia moderno, simples e seguro, conceitualmente similar ao PGP, usando pares de chaves públicas/privadas (chaves `age1...` para públicas, `AGE-SECRET-KEY-1...` para privadas).
    *   **Cloud KMS (AWS KMS, GCP KMS, Azure Key Vault):** SOPS pode se integrar com KMS de provedores de nuvem, onde a chave de criptografia mestra reside no KMS.
    *   **Arquivo de Configuração `.sops.yaml`:** Geralmente colocado na raiz do seu projeto Git, este arquivo define as **regras de criação (creation rules)** que especificam quais chaves (PGP, Age, KMS) devem ser usadas para criptografar quais arquivos (com base em padrões de nome de arquivo, como `*.secret.yaml` ou caminhos específicos).
    *   Quando você edita um arquivo com `sops arquivo.yaml`, ele é descriptografado na memória para edição. Ao salvar, ele é automaticamente re-criptografado usando as chaves definidas nas regras.

*   **Fluxo de Trabalho Típico com SOPS e Git:**
    1.  **Instale SOPS** na sua máquina de controle: [Instruções de Instalação do SOPS](https://github.com/mozilla/sops#stable-releases).
    2.  **Configure seu Backend de Chave:**
        *   **GPG:** Certifique-se de ter uma chave GPG gerada e sua chave pública/fingerprint disponíveis.
        *   **Age:** Gere um par de chaves Age: `age-keygen -o key.txt`. O arquivo `key.txt` conterá sua chave privada (mantenha-a segura!) e sua chave pública correspondente.
    3.  **Crie um Arquivo `.sops.yaml` na Raiz do seu Projeto `home-server/`:**
        ```yaml
        # Exemplo: home-server/.sops.yaml
        # Define regras para criptografia de arquivos.
        creation_rules:
          - path_regex: .*\.secret\.yaml$ # Criptografa quaisquer arquivos terminando com .secret.yaml
            # Usando Age (substitua pela sua chave pública Age)
            age: "age1sua0chave0publica0age0aqui0exemplo00000000000000"
            # Ou usando PGP (substitua pelo fingerprint da sua chave GPG)
            # pgp: "FINGERPRINT_COMPLETO_DA_SUA_CHAVE_GPG_AQUI,FINGERPRINT_CHAVE_COLEGA1,..."

          # Exemplo para um arquivo específico que poderia substituir o Ansible Vault
          - path_regex: ansible/inventories/home/group_vars/all/vault\.sops\.yml
            age: "age1sua0chave0publica0age0aqui0exemplo00000000000000"
        ```
    4.  **Crie seu Arquivo de Segredos (e.g., `ansible/inventories/home/group_vars/all/meus_segredos_app.secret.yaml`):**
        ```yaml
        # ansible/inventories/home/group_vars/all/meus_segredos_app.secret.yaml
        # Este arquivo será criptografado por SOPS
        app_db_user: "usuario_app_secreto"
        app_db_password: "SENHA_MUITO_FORTE_PARA_O_DB_DO_APP"
        app_api_key: "um_token_de_api_longo_e_aleatorio_para_o_app"
        ```
    5.  **Criptografe o Arquivo com SOPS (ou edite-o com SOPS):**
        *   Para criptografar um arquivo existente no local:
            ```bash
            sops --encrypt --in-place ansible/inventories/home/group_vars/all/meus_segredos_app.secret.yaml
            ```
        *   Para criar e editar um arquivo de forma que ele seja automaticamente criptografado ao salvar (SOPS abrirá seu editor padrão):
            ```bash
            sops ansible/inventories/home/group_vars/all/meus_segredos_app.secret.yaml
            ```
        O arquivo agora conterá os valores criptografados, mas a estrutura das chaves YAML (e.g., `app_db_user:`) permanecerá visível. Apenas os *valores* são criptografados.
    6.  **Commit o Arquivo Criptografado no Repositório Git.**
        Agora você pode com segurança versionar este arquivo no Git, pois os segredos estão protegidos.
    7.  **Descriptografar em Tempo de Execução ou para Visualização:**
        *   **Ansible:**
            *   Existe um [lookup plugin `sops`](https://github.com/crivetimihai/ansible-sops) de terceiros que pode ser instalado via `ansible-galaxy collection install crivetimihai.разум`.
                ```yaml
                # Exemplo em um playbook Ansible usando o lookup plugin
                # vars:
                #   segredos_app: "{{ lookup('crivetimihai.разум.sops', 'ansible/inventories/home/group_vars/all/meus_segredos_app.secret.yaml') }}"
                # tasks:
                #   - name: "Debug: Mostrar senha do DB do app (de SOPS)"
                #     ansible.builtin.debug:
                #       msg: "A senha do DB do app é: {{ segredos_app.app_db_password }}"
                #     no_log: true
                ```
            *   Alternativamente, você pode usar o módulo `ansible.builtin.command` para executar `sops --decrypt` e registrar a saída YAML/JSON, depois carregá-la com `from_yaml` ou `from_json`.
                ```yaml
                - name: "Descriptografar segredos com SOPS via comando"
                  ansible.builtin.command: "sops --decrypt {{ playbook_dir }}/../inventories/home/group_vars/all/meus_segredos_app.secret.yaml"
                  register: sops_decrypted_output
                  changed_when: false
                  check_mode: no # Garante que rode mesmo em --check mode para ter as vars
                  no_log: true   # Não logue a saída do comando que contém segredos

                - name: "Carregar segredos SOPS descriptografados como fatos"
                  ansible.builtin.set_fact:
                    segredos_app: "{{ sops_decrypted_output.stdout | from_yaml }}"
                  when: sops_decrypted_output.rc == 0
                  no_log: true
                ```
        *   **Linha de Comando (para visualização ou scripts):**
            ```bash
            sops --decrypt ansible/inventories/home/group_vars/all/meus_segredos_app.secret.yaml
            # Para usar em scripts, e.g., exportar para variáveis de ambiente:
            # export $(sops -d ansible/../secrets.yaml | jq -r 'to_entries|map("\(.key)=\(.value|tostring)")|.[]')
            ```
        *   **`sops exec-file` (para Docker Compose ou outros comandos):**
            Esta é uma maneira poderosa de injetar segredos descriptografados como variáveis de ambiente para um comando que você executa, sem que os segredos toquem o disco descriptografados.
            ```bash
            # Exemplo: Rodar docker compose up, injetando DB_PASSWORD do arquivo SOPS
            sops exec-file 'ansible/inventories/home/group_vars/all/meus_segredos_app.secret.yaml' \
              'DB_PASSWORD="{= app_db_password =}" docker compose -f docker/stacks/minha_app/docker-compose.yml up -d'
            # Aqui, {= app_db_password =} é a sintaxe de template do sops exec-file para injetar o valor.
            ```

*   **Vantagens do SOPS:**
    *   **Segredos Versionados no Git:** Os arquivos de configuração contendo segredos podem ser commitados e versionados de forma segura.
    *   **Descentralizado:** Não requer um servidor de gerenciamento de segredos separado (como o HashiCorp Vault) rodando. A "fonte da verdade" para as chaves de descriptografia são as chaves PGP/Age dos usuários autorizados ou um KMS.
    *   **Bom para Colaboração em Equipe:** Se os membros da equipe compartilham suas chaves públicas PGP/Age, eles podem ser adicionados como destinatários dos arquivos SOPS, permitindo que apenas eles descriptografem.
    *   **Integração com Git Hooks:** Pode ser configurado com Git hooks para criptografar/descriptografar arquivos automaticamente em eventos como `commit` ou `checkout` (usando filtros `smudge`/`clean`).
*   **Desafios do SOPS:**
    *   **Gerenciamento de Chaves PGP/Age:** Requer que os usuários gerenciem suas próprias chaves privadas PGP/Age de forma segura. A distribuição de chaves públicas e a revogação de acesso (removendo uma chave pública do `.sops.yaml` e re-criptografando) precisam ser gerenciadas.
    *   **Estrutura do Arquivo Visível:** A estrutura do arquivo (as chaves YAML/JSON, e.g., `app_db_password:`) permanece visível no arquivo criptografado. Apenas os *valores* correspondentes a essas chaves são criptografados. Isso geralmente não é um problema, mas é uma diferença em relação ao Ansible Vault que criptografa o arquivo inteiro.

!!! tip "SOPS em Conjunto com Ansible Vault?"
    *   **SOPS para o arquivo `vault.yml`:** Você poderia, teoricamente, usar SOPS para criptografar o arquivo que *seria* seu `ansible/inventories/home/group_vars/all/vault.yml`. Em vez de usar `ansible-vault create/edit`, você usaria `sops ansible/.../vault.sops.yml`. Para executar playbooks, você descriptografaria o `vault.sops.yml` para o stdin e o passaria para `ansible-playbook --vault-password-file /dev/stdin`. Isso move o gerenciamento da "senha mestra do vault" para o gerenciamento de chaves PGP/Age.
    *   **SOPS para arquivos de variáveis carregados pelo Ansible:** Você pode ter arquivos de variáveis YAML separados (e.g., `prod_secrets.secret.yaml`) criptografados com SOPS e depois usar um lookup plugin ou `sops -d` para carregá-los em seus playbooks.

## Escolhendo a Ferramenta Certa para Seu Homelab

*   **Para a maioria dos homelabs individuais, o Ansible Vault (usado conforme nosso manual) é geralmente suficiente, prático e bem integrado ao ecossistema Ansible.** A principal coisa a proteger é a senha do seu Ansible Vault.
*   **Considere HashiCorp Vault se:**
    *   Você deseja uma solução de gerenciamento de segredos **centralizada, com UI, auditoria detalhada, e a capacidade de gerar credenciais dinâmicas**.
    *   Você está disposto a gerenciar o servidor Vault e, crucialmente, o **processo de unsealing** após reinícios.
    *   Você precisa de integrações com muitos sistemas diferentes ou está aprendendo Vault para fins profissionais (é uma habilidade muito valiosa).
*   **Considere Mozilla SOPS se:**
    *   Sua prioridade é **versionar seus arquivos de configuração contendo segredos diretamente no Git de forma criptografada**.
    *   Você prefere uma abordagem **descentralizada** que não requer um servidor de segredos dedicado rodando.
    *   Você (e sua equipe, se houver) está confortável com o **gerenciamento de chaves PGP/GPG ou Age**.
    *   Você precisa que os mesmos arquivos de segredos sejam facilmente consumidos por múltiplas ferramentas (Ansible, scripts shell, Docker Compose via `sops exec-file`).

Ambas as ferramentas, HashiCorp Vault e SOPS, representam um passo significativo em termos de maturidade e segurança no gerenciamento de segredos em comparação com armazenar segredos em texto plano ou apenas com Ansible Vault se a senha do vault for compartilhada de forma insegura ou for fraca. A escolha depende do seu nível de conforto com a complexidade adicional e dos benefícios específicos que você busca.