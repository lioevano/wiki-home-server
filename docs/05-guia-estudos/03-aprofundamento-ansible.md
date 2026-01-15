# Aprofundamento em Ansible

Ansible é a espinha dorsal da automação da nossa infraestrutura de servidor doméstico, permitindo-nos definir e gerenciar a configuração de forma consistente e repetível (Infraestrutura como Código - IaC). O [Manual de Implementação](../01-manual-implementacao/index.md) cobriu o uso básico de playbooks, roles, o inventário e o Ansible Vault.

Esta seção tem como objetivo aprofundar seu conhecimento sobre Ansible, explorando conceitos e técnicas mais avançadas para escrever código Ansible mais eficiente, reutilizável, robusto e poderoso. Dominar esses aspectos pode transformar a maneira como você gerencia não apenas seu homelab, mas também ambientes mais complexos.

## 1. Escrevendo Roles Ansible Mais Complexos e Reutilizáveis

Roles são a principal forma de organizar e encapsular a lógica de automação no Ansible, promovendo a reutilização de código e a modularidade.

### Estrutura Detalhada de um Role Ansible

Um role bem estruturado no Ansible pode conter os seguintes diretórios e arquivos principais. Lembre-se que nem todos são obrigatórios para todo role, mas conhecer sua função é importante:

*   **`defaults/main.yml`:**
    *   Define as **variáveis padrão** para o role. Estas têm a **menor precedência** e são facilmente sobrescritas por variáveis de inventário, `group_vars`, `host_vars`, ou variáveis passadas ao incluir o role.
    *   Use este arquivo para definir valores sensatos que tornem o role utilizável "out-of-the-box", mas que o usuário do role possa customizar facilmente.
*   **`vars/main.yml`:**
    *   Define variáveis que são **específicas para o role** e têm **maior precedência** que as variáveis em `defaults/main.yml`.
    *   Geralmente usadas para variáveis que o role precisa internamente e que o usuário do role **não deveria sobrescrever facilmente** (embora ainda seja possível com precedência mais alta).
*   **`tasks/main.yml`:**
    *   Este é o **ponto de entrada principal** para as tarefas do role. Ele define a sequência de ações que o role executará.
    *   Para roles mais complexos, você pode (e deve) **dividir suas tarefas em múltiplos arquivos YAML** dentro do diretório `tasks/` e incluí-los no `tasks/main.yml` usando `ansible.builtin.include_tasks`:
        ```yaml
        # tasks/main.yml
        - name: Incluir tarefas de instalação de pacotes
          ansible.builtin.include_tasks: install_packages.yml
          tags: ['install'] # Pode aplicar tags à inclusão

        - name: Incluir tarefas de configuração de arquivos
          ansible.builtin.include_tasks: configure_files.yml
          tags: ['configure']
        ```
*   **`handlers/main.yml`:**
    *   Define **handlers**, que são tarefas especiais acionadas por uma notificação de outra tarefa (usando a diretiva `notify:`).
    *   Handlers são executados **apenas se a tarefa notificadora reportar uma mudança ("changed")**, e geralmente são executados no final do play em cada host, após todas as outras tarefas terem sido concluídas para aquele host.
    *   Comum para reiniciar serviços apenas se seus arquivos de configuração foram alterados.
*   **`templates/`:**
    *   Contém arquivos de template Jinja2 (com extensão `.j2`). O módulo `ansible.builtin.template` usa esses templates para gerar arquivos de configuração dinamicamente nos hosts gerenciados, preenchendo variáveis Ansible.
*   **`files/`:**
    *   Contém arquivos estáticos que o role pode precisar copiar para os hosts gerenciados (e.g., binários, scripts, chaves públicas, arquivos de configuração que não precisam de templating). Usados pelo módulo `ansible.builtin.copy`.
*   **`meta/main.yml`:**
    *   Contém metadados sobre o role, como informações do autor, descrição, licença e, mais importante, **dependências de outros roles**.
        ```yaml
        # Exemplo de ansible/roles/meu_app/meta/main.yml
        galaxy_info:
          author: "Seu Nome"
          description: "Role para instalar e configurar MeuApp."
          company: "Homelab Inc."
          license: "MIT"
          min_ansible_version: "2.12" # Versão mínima do Ansible requerida
          platforms:
            - name: Ubuntu
              versions:
                - focal # 20.04
                - jammy # 22.04
        dependencies:
          # Este role depende do role 'common_setup' para rodar primeiro.
          - role: common_setup
            vars: # Variáveis que podem ser passadas para o role dependente
              alguma_var_para_common_setup: true
          # Pode depender de um role do Ansible Galaxy
          # - src: geerlingguy.nginx
          #   version: "2.3.0"
        ```

### Loops Avançados e Estruturas de Controle de Fluxo

Ansible oferece formas poderosas de iterar sobre dados e controlar o fluxo de execução das tarefas.

*   **Loops com `loop` (Substitui `with_items` e outros `with_*` legados):**
    *   **Loop Simples sobre uma Lista:**
        ```yaml
        - name: Instalar múltiplos pacotes essenciais
          ansible.builtin.apt:
            name: "{{ item }}" # 'item' é a variável padrão para cada elemento no loop
            state: present
          loop:
            - nginx
            - htop
            - git
            - vim
        ```
    *   **Loop sobre uma Lista de Dicionários (Hashes):**
        ```yaml
        - name: Criar múltiplos usuários com grupos específicos
          ansible.builtin.user:
            name: "{{ item.name }}"
            group: "{{ item.group }}"
            state: present
          loop:
            - { name: 'alice', group: 'developers' }
            - { name: 'bob', group: 'operations' }
            - { name: 'charlie', group: 'developers' }
        ```
    *   **`loop_control` para Personalizar o Loop:**
        ```yaml
        - name: Loop com nome de variável customizado
          ansible.builtin.debug:
            msg: "Processando pacote: {{ pkg.name }} para a versão {{ pkg.version }}"
          loop:
            - { name: 'apache2', version: '2.4' }
            - { name: 'mysql-server', version: '8.0' }
          loop_control:
            loop_var: pkg # Define 'pkg' como a variável do item em vez de 'item'
            label: "{{ pkg.name }}" # Customiza a saída do Ansible para esta task
        ```
*   **Condicionais com `when`:**
    Permite executar tarefas apenas se uma ou mais condições forem verdadeiras.
    ```yaml
    - name: Instalar Apache apenas em hosts Debian/Ubuntu
      ansible.builtin.apt:
        name: apache2
        state: present
      when: ansible_facts['os_family'] == "Debian"

    - name: Criar arquivo de configuração apenas se uma variável estiver definida
      ansible.builtin.template:
        src: meu_servico.conf.j2
        dest: /etc/meu_servico/meu_servico.conf
      when: minha_variavel_de_config is defined and minha_variavel_de_config == "valor_esperado"

    - name: Executar task se QUALQUER condição for verdadeira (lista de condições)
      ansible.builtin.debug:
        msg: "Pelo menos uma condição foi atendida."
      when:
        - var1 == "foo"
        - var2 > 10
        - inventory_hostname in groups['webservers']
      # Por padrão, uma lista de 'when' é um AND. Para OR, você precisa agrupar com parênteses e 'or'.
      # when: (var1 == "foo") or (var2 > 10)
    ```
*   **Loops com Condicionais Internos (Usando `when` na task, aplicado a cada item):**
    ```yaml
    - name: Criar diretórios apenas se o tipo for 'dir' e o modo estiver definido
      ansible.builtin.file:
        path: "{{ item.path }}"
        state: directory
        mode: "{{ item.mode }}"
      loop:
        - { path: '/opt/app1', type: 'dir', mode: '0755' }
        - { path: '/opt/app1/data.txt', type: 'file' } # Esta iteração será pulada pelo 'when'
        - { path: '/opt/app2_config', type: 'dir', mode: '0700' }
      when: item.type == 'dir' and item.mode is defined
    ```

### Blocos de Tarefas (`block`, `rescue`, `always`)

Permitem agrupar tarefas e implementar tratamento de erros e limpeza, similar a `try...catch...finally` em linguagens de programação.

```yaml
- name: "Exemplo de Bloco com Tratamento de Erro e Limpeza"
  hosts: webservers
  tasks:
    - name: "Operação Principal (pode falhar)"
      ansible.builtin.block:
        - name: "Task 1: Tentar configurar o serviço web"
          ansible.builtin.command: /usr/local/bin/configurar_web_app --force
          register: resultado_config_web
          changed_when: "'SUCCESS' in resultado_config_web.stdout"
          failed_when: resultado_config_web.rc != 0 and 'IGNORE_THIS_ERROR' not in resultado_config_web.stderr

        - name: "Task 2: Reiniciar o serviço web se a configuração mudou"
          ansible.builtin.service:
            name: meu_web_service
            state: restarted
          when: resultado_config_web.changed

      rescue: # Se qualquer task no bloco 'block' falhar (e não for ignorada por failed_when)
        - name: "Ação de Resgate: Enviar notificação de falha"
          community.general.mail: # Exemplo de módulo de email
            host: smtp.example.com
            to: admin@example.com
            subject: "Falha na configuração do Web App em {{ inventory_hostname }}"
            body: "A configuração do web app falhou. Verifique os logs."
          delegate_to: localhost # Enviar email da máquina de controle
          run_once: true # Apenas uma vez, mesmo se vários hosts falharem

        - name: "Ação de Resgate: Tentar reverter para uma configuração segura (exemplo)"
          ansible.builtin.command: /usr/local/bin/reverter_config_web_app
          changed_when: false

      always: # Este bloco SEMPRE executa, independentemente do sucesso ou falha do 'block' ou 'rescue'
        - name: "Ação de Limpeza: Remover arquivo de lock"
          ansible.builtin.file:
            path: /tmp/config_web_app.lock
            state: absent
```

## 2. Uso Avançado de Jinja2 em Templates Ansible

Jinja2 é o motor de templating usado pelo Ansible para gerar arquivos de configuração dinamicamente. Dominar Jinja2 permite criar templates muito mais flexíveis e poderosos.

*   **Filtros Jinja2:**
    Filtros transformam o valor de uma variável. Eles são aplicados com o caractere pipe `|`.
    *   `{{ minha_variavel | default('valor_padrao_se_indefinida') }}`: Fornece um valor padrão.
    *   `{{ minha_lista_de_strings | join(', ') }}`: Junta elementos de uma lista em uma string.
    *   `{{ "alguma string" | upper }}`: Converte para maiúsculas. `lower` para minúsculas.
    *   `{{ "true" | bool }}`: Converte uma string ("true", "yes", "on", "1") para um booleano.
    *   `{{ meu_dicionario | to_nice_yaml }}` ou `{{ minha_lista | to_json }}`: Formata dados como YAML ou JSON.
    *   `{{ "/caminho/para/arquivo.txt" | basename }}`: Retorna `arquivo.txt`. `dirname` retorna o diretório.
    *   `{{ "algum texto com espaços" | urlencode }}`: Codifica para URL.
    *   **Filtros de Seleção e Mapeamento (com `selectattr`, `map`, `rejectattr`):**
        ```jinja
        # Em um template, se 'users' é uma lista de dicionários com chaves 'name' e 'shell'
        # Pegar apenas os nomes dos usuários que usam /bin/bash
        Nomes dos usuários bash: {{ users | selectattr('shell', 'equalto', '/bin/bash') | map(attribute='name') | list | join(', ') }}
        ```
    *   **A lista completa de filtros é extensa:** Consulte a [Documentação Oficial de Filtros Ansible](https://docs.ansible.com/ansible/latest/user_guide/playbooks_filters.html).
*   **Testes Jinja2:**
    Testes verificam uma condição sobre uma variável, retornando `true` ou `false`. Usados com `is`.
    *   `{% if minha_variavel is defined %}` ... `{% endif %}`
    *   `{% if meu_numero is even %}` ... `{% endif %}` (ou `odd`)
    *   `{% if 'valor_x' in minha_lista_de_strings %}` ... `{% endif %}`
    *   `{% if minha_string is startingwith('prefixo') %}` ... `{% endif %}` (ou `endswith`)
    *   `{% if resultado_comando is succeeded %}` ... `{% endif %}` (para resultados de tasks registradas)
    *   **A lista completa de testes:** Consulte a [Documentação Oficial de Testes Ansible](https://docs.ansible.com/ansible/latest/user_guide/playbooks_tests.html).
*   **Lookups Ansible:**
    Lookups permitem buscar dados de fontes externas *durante a execução do playbook* e usá-los em variáveis ou templates. Eles são chamados com `lookup('plugin_nome', 'argumentos_do_plugin')`.
    *   `{{ lookup('file', '/etc/ssh/ssh_host_rsa_key.pub') }}`: Lê o conteúdo de um arquivo na máquina de controle Ansible.
    *   `{{ lookup('env', 'HOME') }}`: Lê o valor de uma variável de ambiente na máquina de controle.
    *   `{{ lookup('pipe', 'date +%Y-%m-%d') }}`: Executa um comando shell na máquina de controle e retorna sua saída padrão.
    *   `{{ lookup('template', 'outro_template.j2') }}`: Renderiza outro template Jinja2 e retorna seu conteúdo.
    *   `{{ lookup('vars', 'ansible_default_ipv4.address') }}`: Acessa variáveis Ansible dinamicamente usando uma string como nome da variável.
    *   `{{ lookup('password', '/caminho/para/arquivo_de_senha chars=ascii_letters,digits length=15') }}`: Gera uma senha aleatória e a armazena em um arquivo (criptografado se o arquivo for `/dev/null`).
    *   `{{ lookup('community.hashi_vault.hashi_vault', 'secret=kv/myapp:password token=...') }}`: (De uma coleção) Busca um segredo do HashiCorp Vault.
*   **Estruturas de Controle Jinja2 em Templates (Loops e Condicionais):**
    Permitem lógica mais complexa dentro dos seus arquivos `.j2`.
    ```jinja
    # Exemplo em um arquivo de configuração .j2
    {% for user_data in users_list %}
    UserEntry:
      Username: {{ user_data.name }}
      FullName: {{ user_data.full_name | default(user_data.name) }}
      {% if user_data.shell is defined and user_data.shell != "/sbin/nologin" %}
      LoginShell: {{ user_data.shell }}
      {% else %}
      LoginShell: /bin/bash  # Padrão se não definido ou nologin
      {% endif %}
    {% endfor %}

    {% if enable_feature_x | default(false) | bool %}
    FeatureX_IsEnabled: true
    SettingForFeatureX: {{ feature_x_setting | default("default_value") }}
    {% else %}
    FeatureX_IsEnabled: false
    {% endif %}
    ```

## 3. Inventários Dinâmicos

Para ambientes onde a lista de hosts muda frequentemente (e.g., instâncias de nuvem que são criadas e destruídas, VMs Proxmox adicionadas/removidas), manter um arquivo `hosts.ini` estático pode ser impraticável. Inventários dinâmicos resolvem isso.

*   **Como Funcionam:**
    *   Um inventário dinâmico é um **script executável** (Python, Bash, Go, etc.) ou um **plugin de inventário Ansible** que o Ansible executa para obter a lista de hosts e suas variáveis em tempo real.
    *   O script/plugin se conecta a uma "fonte da verdade" (e.g., API do Proxmox, API de um provedor de nuvem, um CMDB) e formata a saída em JSON conforme esperado pelo Ansible.
    *   O JSON deve conter uma estrutura que define grupos de hosts e, opcionalmente, variáveis para cada host (`_meta: { hostvars: { ... } }`).
*   **Plugin de Inventário Proxmox (da coleção `community.general` ou `community.proxmox`):**
    *   A coleção `community.general.proxmox` (que já instalamos) inclui um plugin de inventário dinâmico que pode buscar informações sobre suas VMs e containers diretamente da API do Proxmox VE.
    *   **Configuração:** Você cria um arquivo YAML (e.g., `proxmox_inventory.yml` ou `meu_inventario_pve.proxmox.yml` - o nome do arquivo com a extensão do plugin é importante) para configurar o plugin.
        ```yaml
        # Exemplo: ansible/inventories/home/meu_inventario_pve.proxmox.yml
        # O nome do arquivo DEVE terminar com .proxmox.yml ou .proxmox.yaml
        # para que o Ansible o reconheça como um inventário usando este plugin.

        plugin: community.general.proxmox
        # URL da API do Proxmox
        # Pode ser uma variável Ansible, e.g., {{ lookup('env', 'PVE_API_URL') }}
        # ou hardcodado (menos ideal), ou vir de um ansible.cfg
        proxmox_url: "https://{{ hostvars['proxmox_main_host']['ansible_host'] }}:8006" # Usa o IP do host Proxmox do inventário estático

        # Credenciais da API (MAIS SEGURO usar variáveis de ambiente ou Ansible Vault para isso)
        # proxmox_user: "{{ proxmox_api_user }}" # Do vault.yml
        # proxmox_password: "{{ proxmox_api_password }}" # Do vault.yml
        # Ou defina as variáveis de ambiente PVE_USER, PVE_PASSWORD, PVE_API_TOKEN_ID, PVE_API_TOKEN_SECRET

        # Desabilitar verificação de certificado SSL se usar certificado autoassinado (NÃO RECOMENDADO PARA PRODUÇÃO)
        validate_certs: false # Mude para true se tiver um certificado válido para a UI do Proxmox

        # Opções para agrupar VMs e adicionar variáveis
        # Por exemplo, agrupar por tags Proxmox:
        # group_by_tags: true
        # Ou criar grupos baseados em uma propriedade da VM:
        # keyed_groups:
        #   - key: "config.ostype" # Agrupa por tipo de SO (e.g., l26, ubuntu)
        #     prefix: "ostype"
        #     separator: "_"

        # Para usar este inventário dinâmico:
        # ansible-inventory -i ansible/inventories/home/ --graph
        # ansible-playbook -i ansible/inventories/home/ meu_playbook.yml
        # (O Ansible automaticamente descobre e usa plugins de inventário baseados na extensão do arquivo
        # se o diretório de inventário for especificado e o plugin estiver instalado.)
        ```
    *   **Uso:** Você pode então executar playbooks usando este diretório de inventário:
        `ansible-playbook -i ansible/inventories/home/ meu_playbook.yml`
        Ansible combinará seu `hosts.ini` estático com os hosts descobertos dinamicamente pelo plugin Proxmox.
*   **Vantagens dos Inventários Dinâmicos:**
    *   Mantém seu inventário Ansible sempre sincronizado com o estado real da sua infraestrutura.
    *   Reduz a necessidade de atualizar manualmente o `hosts.ini` ao adicionar/remover VMs.
    *   Pode extrair metadados da fonte da verdade (e.g., tags Proxmox, tipo de SO da VM) e usá-los como variáveis Ansible.

## 4. Orquestradores de Interface Gráfica para Ansible (AWX, Semaphore)

Para ambientes maiores, equipes, ou quando você precisa de mais controle sobre a execução de playbooks, agendamento, auditoria e uma interface gráfica para Ansible, existem ferramentas de orquestração:

*   **AWX (Projeto Open Source Upstream do Red Hat Ansible Automation Platform):**
    *   É uma aplicação web poderosa que fornece uma interface gráfica completa para gerenciar:
        *   **Inventários:** Pode sincronizar com inventários dinâmicos ou estáticos.
        *   **Credenciais:** Armazena de forma segura credenciais para SSH, Vault, nuvem, etc.
        *   **Projetos:** Aponta para seus repositórios Git que contêm playbooks Ansible.
        *   **Templates de Job:** Define como um playbook deve ser executado (qual playbook, qual inventário, quais credenciais, variáveis extras, etc.).
    *   **Funcionalidades:**
        *   **Agendamento de Jobs:** Execute playbooks em horários programados.
        *   **Controle de Acesso Baseado em Role (RBAC):** Define quem pode ver, executar ou modificar o quê.
        *   **APIs REST:** Para integração com outras ferramentas.
        *   **Logs Centralizados e Detalhados:** Histórico de todas as execuções de playbooks.
        *   **Workflows:** Permite encadear múltiplos templates de job com lógica condicional.
    *   **Instalação:** AWX geralmente é implantado como containers Docker ou em um cluster Kubernetes. Pode ser um pouco pesado para rodar em um homelab com recursos muito limitados, mas é possível.
*   **Ansible Semaphore:**
    *   Uma alternativa open-source mais leve e simples ao AWX para fornecer uma UI para Ansible.
    *   Também permite gerenciar inventários, credenciais, repositórios e executar playbooks.
    *   Mais fácil de instalar e consome menos recursos que AWX.
*   **Considerações para Homelab:**
    *   Se você é o único usuário e está confortável com a linha de comando, AWX/Semaphore podem ser um exagero.
    *   No entanto, podem ser **excelentes projetos de aprendizado** se você quiser experimentar uma forma mais "empresarial" de gerenciar Ansible, ou se precisar de agendamento robusto e uma UI para execuções.

## 5. Testando Roles Ansible com Molecule

Molecule é uma ferramenta projetada para ajudar no desenvolvimento e teste de roles Ansible de forma estruturada e automatizada. Ele facilita a criação de ambientes de teste isolados (e.g., containers Docker, VMs), a aplicação do seu role nesses ambientes, e a verificação do resultado com testes automatizados.

*   **Como Funciona (Ciclo de Teste Típico):**
    1.  **Inicializar Molecule em um Role:** `molecule init role nome_do_meu_role --driver docker` (cria uma estrutura de diretórios `molecule/default/` dentro do seu role, com arquivos de configuração para um cenário de teste padrão usando Docker como driver).
    2.  **Definir o Playbook de Convergência (`molecule/default/converge.yml`):** Este playbook simplesmente aplica o role que você está testando ao(s) host(s) de teste.
    3.  **Escrever Testes de Verificação (`molecule/default/verify.yml`):** Você define tasks Ansible (ou usa frameworks de teste como Testinfra) para verificar se o role configurou o sistema corretamente (e.g., "o pacote X está instalado?", "o serviço Y está rodando?", "o arquivo Z contém a linha esperada?").
    4.  **Executar o Ciclo de Teste Molecule:** `molecule test`
        O Molecule executa uma sequência de etapas:
        *   `dependency`: Instala dependências do role (de `meta/main.yml`).
        *   `create`: Cria o(s) ambiente(s) de teste (e.g., inicia um container Docker).
        *   `prepare`: (Opcional) Executa um playbook de preparação no ambiente de teste.
        *   `converge`: Executa o `converge.yml` (aplica seu role).
        *   `idempotence`: Executa o `converge.yml` novamente para verificar se o role é idempotente (não deve fazer mais nenhuma mudança).
        *   `verify`: Executa o `verify.yml` (seus testes).
        *   `destroy`: Limpa o(s) ambiente(s) de teste.
*   **Comandos Úteis:**
    *   `molecule test`: Roda o ciclo completo.
    *   `molecule create`: Apenas cria o ambiente.
    *   `molecule converge`: Aplica o role (cria o ambiente se não existir).
    *   `molecule login`: Loga via SSH (ou `docker exec`) no ambiente de teste para depuração manual.
    *   `molecule verify`: Roda apenas os testes de verificação.
    *   `molecule destroy`: Destrói o ambiente.
*   **Vantagens:**
    *   Aumenta significativamente a confiança na qualidade, corretude e idempotência dos seus roles Ansible.
    *   Facilita o desenvolvimento orientado a testes (TDD) para roles.
    *   Permite testar seu role em diferentes distribuições Linux (configurando múltiplos cenários Molecule).
*   **Considerações para Homelab:**
    *   Adiciona uma camada de aprendizado e configuração ao desenvolvimento de roles.
    *   Para roles muito simples, pode parecer um exagero.
    *   Mas para roles mais complexos, reutilizáveis, ou críticos para sua infraestrutura, investir tempo em aprender Molecule pode economizar muitas dores de cabeça no futuro.

## 6. Estratégias de Execução e Controle de Fluxo em Playbooks

Ansible oferece várias maneiras de controlar como e quando as tarefas são executadas em seus hosts.

*   **Paralelismo (`forks`):**
    *   Por padrão, Ansible executa tarefas em até 5 hosts em paralelo. Este valor é definido pela diretiva `forks` no `ansible.cfg` (ou pode ser passado na linha de comando com `-f NUM_FORKS`).
    *   Aumentar o número de forks pode acelerar a execução de playbooks em muitos hosts, mas também aumenta a carga na máquina de controle e nos hosts gerenciados.
*   **`serial: <numero_ou_porcentagem>` (Dentro de um Play):**
    Controla quantos hosts em um "play" (um conjunto de tarefas aplicadas a um grupo de hosts) são processados simultaneamente, criando "batches".
    ```yaml
    - hosts: webservers_producao
      serial: 1 # Processa um webserver de produção por vez (atualização rolling)
      # Ou: serial: 2 # Processa dois por vez
      # Ou: serial: "30%" # Processa 30% dos webservers por vez
      roles:
        - role: deploy_nova_versao_app
    ```
    Muito útil para atualizações "rolling" onde você não quer derrubar todos os servidores de um serviço de uma vez.
*   **Estratégias de Execução (`strategy`):**
    Define a ordem em que as tarefas são executadas nos hosts dentro de um batch (definido por `serial` ou `forks`).
    *   `strategy: linear` (Padrão): Ansible completa **todas as tarefas** do play em um host (ou no batch de hosts definido por `serial`) antes de passar para o próximo host (ou próximo batch).
    *   `strategy: free`: Permite que os hosts avancem para a próxima tarefa assim que a completarem, sem necessariamente esperar que outros hosts no mesmo batch terminem a mesma tarefa. Pode ser mais rápido para plays com tarefas que têm durações muito variáveis entre os hosts, mas pode tornar a saída mais difícil de acompanhar.
    *   `strategy: debug`: Roda uma tarefa por vez em todos os hosts, com um debugger entre as tarefas. Útil para depuração.
*   **Controle de Falhas:**
    *   `max_fail_percentage: <numero_de_0_a_100>`: Define a porcentagem de hosts em um play que podem falhar antes que o Ansible aborte a execução para o restante dos hosts naquele play.
        ```yaml
        - hosts: all_minhas_vms
          max_fail_percentage: 20 # Se mais de 20% das VMs falharem, para o play.
          tasks:
            # ...
        ```
    *   `any_errors_fatal: true`: Se qualquer host falhar em qualquer tarefa do play, aborta a execução para todos os hosts imediatamente.
*   **Tags:**
    Permitem executar ou pular seletivamente partes de um playbook ou role.
    *   **Definindo Tags em Tarefas ou Roles:**
        ```yaml
        # Em tasks/main.yml de um role ou em um playbook
        - name: Configurar NTP Client
          ansible.builtin.apt:
            name: ntp
            state: present
          tags: [config, network, ntp] # Uma task pode ter múltiplas tags

        - name: Iniciar serviço NTP
          ansible.builtin.service:
            name: ntp
            state: started
          tags: [service, ntp]
        ```
    *   **Executando Playbooks com Tags:**
        ```bash
        # Roda apenas tasks com a tag 'ntp'
        ansible-playbook meu_playbook.yml --tags "ntp"

        # Roda tasks com a tag 'config' OU 'network'
        ansible-playbook meu_playbook.yml --tags "config,network"

        # Pula todas as tasks com a tag 'service'
        ansible-playbook meu_playbook.yml --skip-tags "service"

        # Lista todas as tags disponíveis em um playbook
        ansible-playbook meu_playbook.yml --list-tags
        ```
    *   **Tags Especiais:**
        *   `always`: Uma task com `tags: [always]` sempre rodará, a menos que seja explicitamente pulada com `--skip-tags always` ou se o play for filtrado por outra tag que não a inclua. Útil para tasks de setup/teardown.
        *   `never`: Uma task com `tags: [never]` nunca rodará, a menos que seja explicitamente chamada com `--tags never` (ou uma tag que ela também possua). Útil para tasks de debug ou experimentais.

Dominar esses conceitos avançados do Ansible pode levar tempo e prática, mas eles abrem portas para criar automações muito mais sofisticadas, robustas, testáveis e fáceis de manter, transformando seu homelab em uma verdadeira plataforma de aprendizado e eficiência. Sempre consulte a [documentação oficial do Ansible](https://docs.ansible.com/) para obter os detalhes mais precisos e exemplos.