---
description: "Instala o Gemini CLI nas VMs via Ansible e mostra como usá-lo no terminal para manutenção e troubleshooting."
---

# Usando o Gemini CLI para Interação Inteligente com o Servidor

Nossa arquitetura de home server é poderosa, mas a interação com ela, especialmente para tarefas de manutenção, análise de logs e troubleshooting, geralmente acontece através da linha de comando (CLI). Para turbinar essa interação, integramos o **Gemini CLI** (`@google/gemini-cli`), a ferramenta de código aberto do Google que leva o poder dos modelos de linguagem da Google (Gemini) diretamente para o seu terminal.

O GeminiCLI permite que você faça perguntas em linguagem natural sobre o seu sistema, gere comandos, analise arquivos e muito mais, tudo isso com o contexto do seu filesystem. É como ter um assistente de DevOps experiente disponível 24/7 diretamente no seu shell.

!!! warning "Ferramenta Não-Oficial e Segurança"
    O Gemini CLI é instalado via `npm` (pacote `@google/gemini-cli`), por isso o role instala `nodejs` e `npm` antes. Embora seja extremamente útil, sempre exerça cautela. **Nunca execute comandos gerados por uma IA em um ambiente de produção sem antes revisá-los cuidadosamente.** Trate as sugestões da IA como as de um assistente júnior: úteis, mas que exigem supervisão sênior (a sua!).

## Instalação e Configuração via Ansible

A instalação do GeminiCLI e a configuração da chave de API serão gerenciadas pelo Ansible para garantir consistência em todas as VMs relevantes (como a `core-services-vm` e a `ai-desktop-vm`).

1.  **Adicionar a Chave de API ao Vault:**
    Primeiro, obtenha uma chave de API para o Gemini no [Google AI Studio](https://aistudio.google.com/app/apikey). Em seguida, adicione-a ao seu `ansible/inventories/home/group_vars/all/vault.yml`.

    ```yaml title="Trecho: ansible/inventories/home/group_vars/all/vault.yml"
    # ansible/inventories/home/group_vars/all/vault.yml
    # ...
    llm_api_keys:
      # ...
      google_gemini: "sua-api-key-do-google-ai"
    ```

2.  **Role Ansible para Instalação:**
    Criaremos um novo role no Ansible para instalar ferramentas de CLI baseadas em IA. Este role pode ser expandido no futuro.

    *   **Crie a estrutura do role:** `ansible/roles/tools/ai-cli-tools/`
    *   **Adicione a tarefa em `tasks/main.yml`:**

        ```yaml title="ansible/roles/tools/ai-cli-tools/tasks/main.yml"
        # ansible/roles/tools/ai-cli-tools/tasks/main.yml
        - name: Instalar dependências do Gemini CLI
          ansible.builtin.apt:
            name:
              - nodejs
              - npm
            state: present
            update_cache: true

        - name: Instalar Gemini CLI globalmente
          community.general.npm:
            name: "@google/gemini-cli"
            global: true
            state: present

        - name: Configurar chave de API do Gemini para o usuário
          ansible.builtin.lineinfile:
            path: "/home/{{ vm_ansible_user_name }}/.bashrc"
            line: 'export GEMINI_API_KEY="{{ llm_api_keys.google_gemini }}"'
            create: true
            owner: "{{ vm_ansible_user_name }}"
            group: "{{ vm_ansible_user_name }}"
            mode: '0644'
        ```

3.  **Adicione o Role aos Playbooks:**
    Inclua este novo role nos playbooks que configuram suas VMs principais, como `setup-core-services-vm.yml`.

## Casos de Uso Práticos no Home Server

Após a execução do Ansible, você pode acessar a VM via SSH e começar a usar o `gemini` ou `g` na linha de comando. O grande diferencial do GeminiCLI é sua capacidade de interagir com arquivos e com a saída de outros comandos (stdin).

### 1. Análise de Logs do Sistema

Imagine que um container está se comportando de forma estranha. Em vez de ler centenas de linhas de log, você pode pedir ao Gemini para fazer isso por você.

```bash
# Peça ao Gemini para resumir os últimos 100 logs de um container
docker logs --tail 100 nextcloud_app | gemini "Resuma estes logs. Há algum erro crítico ou aviso recorrente?"

# Output (Exemplo):
# Parece que há múltiplos avisos de 'login failed' do endereço IP 192.168.1.100.
# Há também um erro de conexão com o banco de dados que ocorreu uma vez, mas não se repetiu.
```

### 2. Geração de Comandos e Scripts

Precisa de um comando `find` ou `awk` complexo que você nunca lembra de cabeça? Peça ao Gemini.

```bash
# Peça para gerar um comando
gemini "Gere um comando para encontrar todos os arquivos .log no diretório /var/log que foram modificados nos últimos 2 dias e que contenham a palavra 'ERROR'"

# Output (Exemplo):
# find /var/log -name "*.log" -mtime -2 -type f -exec grep -l "ERROR" {} +

# Você pode então copiar, revisar e executar o comando.
```

### 3. Troubleshooting Assistido por IA

Seu serviço Traefik não está funcionando. Você pode passar o arquivo de configuração para o Gemini e pedir uma análise.

```bash
# Analise um arquivo de configuração em busca de erros
gemini -f /etc/traefik/traefik.yml "Analise este arquivo de configuração do Traefik. Há algum erro de sintaxe ou configuração comum que possa estar causando problemas?"

# Output (Exemplo):
# Na seção 'entrypoints', o endereço 'websecure' está definido como ':443', mas não há uma configuração TLS associada a ele. Você precisa adicionar a seção 'tls:' com um 'certresolver'.
```

### 4. Documentação e Explicação de Comandos

Encontrou um script complexo na internet? Peça ao Gemini para explicá-lo.

```bash
# Explique um comando complexo
gemini "Explique o que este comando faz, passo a passo: tar -czf - /home/ubuntu/data | ssh user@remote 'cat > /backup/data.tar.gz'"

# Output (Exemplo):
# Este comando realiza um backup de um diretório para um servidor remoto de forma eficiente:
# 1. `tar -czf - /home/ubuntu/data`: Cria um arquivo tar (`-c`), o comprime com gzip (`-z`), e envia o resultado para a saída padrão (stdout), indicado pelo `-f -`.
# 2. `|`: O pipe redireciona a saída do comando `tar` para a entrada do comando `ssh`.
# 3. `ssh user@remote '...'`: Conecta-se ao servidor 'remote' como o usuário 'user'.
# 4. `'cat > /backup/data.tar.gz'`: Executa o comando `cat` no servidor remoto, que lê da sua entrada padrão (que está recebendo os dados do backup) e escreve os dados no arquivo `/backup/data.tar.gz`.
```

## Automações e Integrações

O poder do GeminiCLI é ampliado quando combinado com outras ferramentas e scripts.

*   **Scripts de Saúde do Sistema:** Crie um script bash que coleta várias métricas do sistema (uso de disco, status de containers, logs recentes) e as passa para o Gemini com um prompt para "gerar um relatório de saúde do sistema em uma frase". Agende este script para rodar via cron e enviar o resultado para uma notificação do n8n.
*   **Alertas Inteligentes:** Em vez de um alerta genérico "CPU acima de 90%", use um script para pegar os processos que mais consomem CPU (`ps aux | sort -nrk 3,3 | head -n 5`), passe para o Gemini e peça: "O processo 'X' está consumindo muita CPU. Com base no nome do processo, qual é a causa provável e qual o primeiro passo para investigar?". Envie essa resposta enriquecida como um alerta.

Ao integrar o GeminiCLI em seu fluxo de trabalho, você transforma a maneira como gerencia seu servidor, tornando a administração menos reativa e mais proativa, e permitindo que você resolva problemas e otimize seu sistema de forma mais rápida e inteligente.
