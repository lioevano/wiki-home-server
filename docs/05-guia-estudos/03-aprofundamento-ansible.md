# Aprofundamento em Ansible

Ansible é a espinha dorsal da automação da nossa infraestrutura. O manual de implementação cobriu o uso básico de playbooks, roles e o vault. Esta seção explora conceitos mais avançados para escrever código Ansible mais eficiente, reutilizável e poderoso.

## 1. Escrevendo Roles Mais Complexos e Reutilizáveis

Roles são a chave para organizar e reutilizar a lógica de automação.

### Estrutura Detalhada de um Role

Um role bem estruturado pode conter os seguintes diretórios:

*   **`defaults/main.yml`:** Define as variáveis padrão para o role. Estas têm a menor precedência e podem ser facilmente sobrescritas.
*   **`vars/main.yml`:** Define variáveis que são específicas para o role e têm maior precedência que `defaults`. Geralmente usadas para variáveis que o usuário do role não deveria sobrescrever facilmente.
*   **`tasks/main.yml`:** O arquivo principal que define as tarefas a serem executadas pelo role.
    *   Você pode incluir outros arquivos de tasks: `ansible.builtin.include_tasks: outras_tasks.yml`.
*   **`handlers/main.yml`:** Define handlers que são notificados por tarefas para executar ações (e.g., reiniciar um serviço).
*   **`templates/`:** Contém arquivos de template Jinja2 (`.j2`) que o role usará para gerar arquivos de configuração.
*   **`files/`:** Contém arquivos estáticos que o role pode precisar copiar para os hosts gerenciados (e.g., binários, scripts).
*   **`meta/main.yml`:** Contém metadados do role, como dependências de outros roles e informações do autor.
    ```yaml
    # Exemplo de meta/main.yml
    galaxy_info:
      author: Seu Nome
      description: Role para configurar o serviço X.
      license: MIT
      min_ansible_version: "2.9" # Versão mínima do Ansible requerida
    dependencies:
      - role: outro_role_necessario # Este role rodará antes
        vars: # Passa variáveis para o role dependente
          alguma_var: valor
    ```

### Loops Avançados e Condicionais

*   **Loops com `loop` (e `with_items` para versões mais antigas):**
    ```yaml
    - name: Instalar múltiplos pacotes
      ansible.builtin.apt:
        name: "{{ item }}"
        state: present
      loop:
        - nginx
        - htop
        - git
    ```
    Com listas de dicionários:
    ```yaml
    - name: Criar múltiplos usuários
      ansible.builtin.user:
        name: "{{ item.name }}"
        group: "{{ item.group }}"
        state: present
      loop:
        - { name: 'alice', group: 'dev' }
        - { name: 'bob', group: 'ops' }
    ```
*   **Condicionais (`when`):**
    ```yaml
    - name: Desligar firewall em hosts de desenvolvimento
      ansible.builtin.service:
        name: ufw
        state: stopped
      when: inventory_hostname in groups['development_hosts']

    - name: Instalar pacote apenas se uma variável for verdadeira
      ansible.builtin.apt:
        name: especial_package
        state: present
      when: instalar_pacote_especial | default(false) | bool
    ```
*   **Loops com Condicionais:**
    ```yaml
    - name: Criar diretórios apenas se o tipo for 'dir'
      ansible.builtin.file:
        path: "{{ item.path }}"
        state: directory
      loop:
        - { path: '/tmp/foo', type: 'dir' }
        - { path: '/tmp/bar.txt', type: 'file' }
      when: item.type == 'dir'
    ```

### Blocos (`block`, `rescue`, `always`)

Para tratamento de erros e execução de tarefas de limpeza.

```yaml
- name: Tentativa de operação crítica com fallback e limpeza
  ansible.builtin.block:
    - name: Tarefa crítica que pode falhar
      ansible.builtin.command: /usr/bin/operacao_critica
      register: resultado_critico
      changed_when: "'MUDOU' in resultado_critico.stdout"

    - name: Outra tarefa se a primeira foi bem-sucedida
      ansible.builtin.debug:
        msg: "Operação crítica bem-sucedida."
      when: resultado_critico.rc == 0

  rescue: # Executa se qualquer tarefa no 'block' falhar
    - name: Tarefa de fallback em caso de erro
      ansible.builtin.debug:
        msg: "A operação crítica falhou. Executando fallback."

  always: # Executa independentemente de falha ou sucesso no 'block' ou 'rescue'
    - name: Tarefa de limpeza
      ansible.builtin.file:
        path: /tmp/lock_operacao_critica
        state: absent
```

## 2. Uso Avançado de Jinja2 em Templates

Jinja2 é o motor de templating usado pelo Ansible.

*   **Filtros:** Transformam dados.
    *   `{{ minha_variavel | default('valor_padrao') }}`
    *   `{{ lista_de_strings | join(',') }}`
    *   `{{ alguma_string | upper }}`
    *   `{{ "true" | bool }}` (converte string para booleano)
    *   `{{ meu_dict | to_nice_yaml }}` ou `{{ meu_dict | to_json }}`
    *   Lista completa: [Filtros Jinja2 na Documentação Ansible](https://docs.ansible.com/ansible/latest/user_guide/playbooks_filters.html)
*   **Testes:** Verificam condições.
    *   `{% if minha_variavel is defined %}`
    *   `{% if numero is even %}`
    *   `{% if 'valor' in minha_lista %}`
    *   Lista completa: [Testes Jinja2 na Documentação Ansible](https://docs.ansible.com/ansible/latest/user_guide/playbooks_tests.html)
*   **Lookups:** Permitem buscar dados de fontes externas dentro de playbooks e templates.
    *   `{{ lookup('file', '/etc/some_file_on_control_node') }}` (lê um arquivo na máquina de controle)
    *   `{{ lookup('env', 'SOME_ENVIRONMENT_VARIABLE') }}` (lê uma variável de ambiente)
    *   `{{ lookup('pipe', 'date +%Y-%m-%d') }}` (executa um comando e pega a saída)
    *   `{{ lookup('template', 'outro_template.j2') }}` (renderiza outro template)
    *   `{{ lookup('vars', 'nome_da_variavel_do_ansible') }}` (para acessar variáveis Ansible dinamicamente)
    *   `{{ query('inventory_hostnames', 'grupo_de_hosts') }}` (um tipo de lookup para dados do inventário)
*   **Estruturas de Controle em Templates:**
    ```jinja
    {% for item in minha_lista %}
    Config para {{ item.name }}: {{ item.value }}
    {% endfor %}

    {% if alguma_condicao %}
    # Bloco condicional
    {% elif outra_condicao %}
    # Outro bloco
    {% else %}
    # Bloco else
    {% endif %}
    ```

## 3. Dynamic Inventories (Inventários Dinâmicos)

Para ambientes maiores ou que mudam frequentemente (e.g., nuvem, VMs Proxmox), um arquivo `hosts.ini` estático pode não ser prático. Inventários dinâmicos são scripts (ou plugins) que o Ansible executa para obter a lista de hosts e suas variáveis em tempo real.

*   **Como Funciona:**
    *   Você escreve um script (Python, Bash, etc.) que se conecta à sua fonte da verdade (API do Proxmox, API da nuvem, CMDB) e formata a saída em JSON conforme esperado pelo Ansible.
    *   O JSON deve conter grupos de hosts e, opcionalmente, variáveis para cada host (`hostvars`).
*   **Plugin de Inventário Proxmox:**
    *   A coleção `community.proxmox` (que já instalamos) inclui um plugin de inventário dinâmico para Proxmox.
    *   Você cria um arquivo YAML (e.g., `proxmox_inventory.yml`) para configurar o plugin:
        ```yaml
        # Exemplo: proxmox_inventory.yml
        plugin: community.general.proxmox # Ou community.proxmox.proxmox se a coleção for instalada de forma diferente
        # proxmox_url: https://{{ proxmox_host_ip_var }}:8006
        # proxmox_user: "{{ proxmox_api_user }}"
        # proxmox_password: "{{ proxmox_api_password }}"
        # proxmox_facts_vars_prefix: proxmox_ # Adiciona prefixo aos fatos coletados
        # validate_certs: false # Se usar certificado autoassinado (não ideal para produção)

        # Para passar credenciais de forma segura, use variáveis de ambiente
        # ou um arquivo de configuração Ansible que busca do vault.
        # Exemplo usando variáveis de ambiente (defina-as antes de rodar ansible):
        # PVE_USER, PVE_PASSWORD, PVE_HOST
        ```
    *   Execute playbooks com `-i proxmox_inventory.yml`.
*   **Vantagens:** Mantém seu inventário sempre atualizado automaticamente.

## 4. Ansible Tower / AWX / Semaphore

Para ambientes maiores, equipes, ou quando você precisa de mais controle, agendamento e uma UI para Ansible:

*   **AWX:** Projeto open-source upstream para o Red Hat Ansible Automation Platform (anteriormente Ansible Tower). É uma aplicação web que fornece:
    *   Interface gráfica para gerenciar inventários, credenciais, projetos (repositórios Git com playbooks), templates de job.
    *   Agendamento de jobs Ansible.
    *   Controle de Acesso Baseado em Role (RBAC).
    *   APIs para integração.
    *   Logs centralizados das execuções de playbooks.
*   **Ansible Semaphore:** Outra alternativa open-source de UI para Ansible, mais leve que AWX.
*   **Considerações para Homelab:**
    *   AWX pode ser um pouco pesado para rodar (geralmente como containers Docker/Kubernetes).
    *   Semaphore é mais leve.
    *   Ambos podem ser ótimos projetos de aprendizado se você quiser centralizar e agendar suas execuções Ansible.

## 5. Testando Roles com Molecule

Molecule é uma ferramenta para ajudar no desenvolvimento e teste de roles Ansible. Ele permite definir diferentes cenários de teste, provisionar ambientes de teste (e.g., containers Docker, VMs), aplicar seu role e verificar o resultado.

*   **Como Funciona:**
    1.  `molecule init role meu_novo_role --driver docker` (cria a estrutura do role com um cenário Molecule).
    2.  Você define o "playbook de convergência" (`converge.yml`) que aplica seu role.
    3.  Define "verificadores" (e.g., testes Ansible ou Testinfra) para validar se o role configurou o sistema corretamente.
    4.  Molecule executa um ciclo: `dependency` -> `create` (cria ambiente de teste) -> `prepare` (playbook de preparação) -> `converge` (aplica seu role) -> `idempotence` (roda converge de novo) -> `verify` (roda testes) -> `destroy` (limpa ambiente).
*   **Comandos:** `molecule test`, `molecule converge`, `molecule verify`.
*   **Vantagens:** Aumenta a confiança na qualidade e idempotência dos seus roles, especialmente se forem complexos ou compartilhados.
*   **Considerações para Homelab:** Adiciona uma camada de complexidade ao desenvolvimento de roles, mas pode valer a pena para roles críticos ou que você planeja reutilizar muito.

## 6. Estratégias de Execução Ansible

Por padrão, Ansible executa tarefas em paralelo em até 5 hosts (`forks = 5`). Você pode controlar como os playbooks são executados.

*   **`serial: <numero_ou_porcentagem>`:** Controla quantos hosts em um grupo são processados simultaneamente.
    ```yaml
    - hosts: webservers
      serial: 1 # Processa um webserver por vez
      # ou serial: "30%" # Processa 30% dos webservers por vez
      roles:
        - role: deploy_app
    ```
    Útil para atualizações "rolling" onde você não quer derrubar todos os servidores de uma vez.
*   **`strategy: linear` (Padrão):** Completa todas as tarefas em um host antes de passar para o próximo (dentro do limite de `serial`/`forks`).
*   **`strategy: free`:** Permite que os hosts avancem para a próxima tarefa assim que a completarem, sem esperar que outros hosts no "batch" atual terminem a mesma tarefa. Pode ser mais rápido para tarefas longas e independentes.
*   **`max_fail_percentage: <numero>`:** Define a porcentagem de hosts em um grupo que podem falhar antes que o Ansible aborte a execução para aquele grupo.

## 7. Tags

Tags permitem executar ou pular partes específicas de um playbook ou role.

*   **Definindo Tags:**
    ```yaml
    # Em tasks/main.yml de um role
    - name: Configurar NTP
      ansible.builtin.apt: name=ntp state=present
      tags: [ntp, configuration]

    - name: Iniciar serviço NTP
      ansible.builtin.service: name=ntp state=started
      tags: [ntp, services]
    ```
*   **Executando com Tags:**
    ```bash
    ansible-playbook meu_playbook.yml --tags "ntp" # Roda apenas tasks com a tag 'ntp'
    ansible-playbook meu_playbook.yml --tags "configuration"
    ansible-playbook meu_playbook.yml --skip-tags "services" # Roda tudo exceto tasks com a tag 'services'
    ```
*   **Tags Especiais:** `always` (sempre roda, a menos que skipado explicitamente), `never` (nunca roda, a menos que chamado explicitamente).

Dominar esses conceitos avançados do Ansible pode levar tempo, mas eles abrem portas para automações muito mais sofisticadas, robustas e fáceis de manter, mesmo em um ambiente de homelab.
