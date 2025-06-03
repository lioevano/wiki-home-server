# Seção 0: Preparação e Planejamento

Antes de mergulhar na instalação e configuração, um planejamento cuidadoso e a preparação do ambiente são fundamentais para o sucesso do seu servidor doméstico. Esta seção aborda os pré-requisitos, a organização do projeto e considerações iniciais de segurança e resiliência.

## 0.0. Glossário de Termos Essenciais

Familiarize-se com estes termos chave que serão usados ao longo do guia:

*   **Ansible:** Ferramenta de automação de TI de código aberto para tarefas como gerenciamento de configuração, provisionamento de software e orquestração de implantações.
*   **Ansible Vault:** Recurso do Ansible que permite criptografar arquivos YAML inteiros ou variáveis específicas que contêm dados sensíveis, como senhas e chaves de API.
*   **Cloudflare Tunnel:** Serviço da Cloudflare que cria um túnel seguro e criptografado de saída da sua rede local para a rede global da Cloudflare, permitindo que você exponha serviços internos à internet sem abrir portas no seu roteador e sem expor seu IP público.
*   **Container (Docker):** Unidade padrão de software que empacota código e todas as suas dependências para que a aplicação rode de forma rápida e confiável de um ambiente computacional para outro.
*   **Docker Compose:** Ferramenta para definir e executar aplicações Docker multi-container. Usa arquivos YAML para configurar os serviços da aplicação, redes e volumes.
*   **Proxmox VE (Virtual Environment):** Plataforma de virtualização de servidor de código aberto. Permite gerenciar máquinas virtuais (KVM) e containers (LXC).
*   **Portainer:** Interface gráfica de usuário leve para gerenciar ambientes Docker.
*   **Traefik:** Proxy reverso moderno e dinâmico e balanceador de carga.
*   **ZFS:** Sistema de arquivos avançado e gerenciador de volumes lógicos.
*   **NFS (Network File System):** Protocolo para compartilhar diretórios através de uma rede. Usaremos para compartilhar datasets ZFS do host Proxmox com as VMs para os volumes Docker.
*   **Ollama:** Plataforma para rodar modelos de linguagem grandes (LLMs) localmente.
*   **VM (Máquina Virtual):** Emulação de um sistema de computador completo.
*   **RAG (Retrieval Augmented Generation):** Técnica de IA que combina LLMs com busca de informação externa.
*   **Authelia:** Servidor de autenticação e autorização (1FA/2FA).

## 0.1. Hardware e Software Necessários

Certifique-se de que você possui o seguinte:

### Hardware do Servidor Físico (Host Proxmox)

*   **CPU:** AMD Ryzen 5 5600G (com iGPU Vega e suporte a virtualização AMD-V).
*   **GPU (para passthrough, se usar a Stack de IA):** AMD RX 5600XT.
*   **RAM:** **16GB DDR4**.
    !!! warning "Atenção: Limitação de RAM (16GB)"
        Esta quantidade de RAM é o principal gargalo e influenciará o número e o tamanho das VMs e serviços que podem rodar simultaneamente. Este guia é otimizado para esta restrição, priorizando a estabilidade. Gerenciamento cuidadoso da memória será essencial.
*   **Armazenamento Primário (Proxmox OS e Discos das VMs):** SSD NVMe 1TB.
*   **Armazenamento Secundário (Pool de Dados ZFS `/data`):** 2x HDDs de 500GB. Estes serão configurados em um pool ZFS espelhado (RAID 1).
    !!! note "Espaço Útil ZFS para Dados"
        Com 2x HDDs de 500GB em espelho (RAID 1), você terá aproximadamente **500GB de espaço útil** para os dados das suas aplicações Docker (configs, mídia, downloads, etc.). Gerencie este espaço com atenção.
*   **Rede:** Pelo menos uma porta Ethernet Gigabit.

### Máquina de Controle Ansible

*   Um computador pessoal ou notebook.
*   **Sistema Operacional Suportado:**
    *   Linux (Ubuntu, Fedora, etc.)
    *   macOS
    *   Windows com WSL2 (Windows Subsystem for Linux 2)

### Rede Doméstica

*   Roteador com servidor DHCP habilitado (para atribuição inicial de IPs).
*   Portas Ethernet disponíveis no roteador ou switch.
*   Conexão estável com a Internet.

### Software e Contas (Antes de Iniciar)

*   **ISO do Proxmox VE:** Baixe a versão estável mais recente do [site oficial do Proxmox](https://www.proxmox.com/en/downloads).
*   **Ferramenta para Pendrive Bootável:**
    *   [Rufus](https://rufus.ie/) (Windows)
    *   [Balena Etcher](https://www.balena.io/etcher/) (Windows, macOS, Linux)
*   **Cliente SSH:**
    *   OpenSSH (nativo em Linux e macOS).
    *   PuTTY (popular para Windows).
*   **Domínio Próprio Registrado:** (e.g., `meudominio.com`)
    !!! important "Domínio Próprio é Essencial"
        Você precisará de um domínio que você possa gerenciar os registros DNS. Este guia depende disso para acesso externo seguro via Cloudflare.
*   **Conta Cloudflare:** Crie uma [conta gratuita na Cloudflare](https://www.cloudflare.com/).
    *   Configure seu domínio para usar os **nameservers da Cloudflare**. Isso é necessário para que o Cloudflare Tunnel e o gerenciamento de certificados SSL/TLS funcionem corretamente.

## 0.2. Estrutura do Repositório Git do Projeto (`infra-servidor-domestico`)

Adotaremos a prática de Infraestrutura como Código (IaC), gerenciando todas as configurações e scripts em um repositório Git.

### Estrutura de Diretórios Proposta

Crie a seguinte estrutura de diretórios e arquivos na sua máquina de controle Ansible:

```text
infra-servidor-domestico/
├── ansible/
│   ├── inventories/
│   │   └── home/
│   │       ├── group_vars/
│   │       │   └── all/
│   │       │       ├── main.yml         # Variáveis Ansible não sensíveis
│   │       │       └── vault.yml        # Variáveis Ansible sensíveis (criptografadas)
│   │       └── hosts.ini                # Definição dos hosts e grupos Ansible
│   ├── playbooks/
│   │   ├── vm-deploy.yml
│   │   ├── setup-proxmox-host.yml
│   │   ├── setup-base-ubuntu.yml
│   │   ├── setup-core-networking.yml
│   │   ├── setup-media-stack-volumes.yml
│   │   ├── setup-productivity-automation-volumes.yml
│   │   ├── setup-rag-llm-volumes.yml
│   │   ├── setup-monitoring-stack-volumes.yml
│   │   └── full-deploy.yml              # Playbook mestre para deploy completo
│   └── roles/                           # Roles Ansible reutilizáveis
│       ├── common/
│       ├── infra/
│       │   ├── proxmox-host-config/
│       │   ├── proxmox-vm/
│       │   ├── docker/
│       │   ├── traefik-config/
│       │   └── authelia-config/
│       └── apps/
│           ├── ml-tools/
│           ├── desktop-environment/
│           └── open-notebooklm-source-prep/
├── docker/
│   ├── stacks/                          # Stacks Docker Compose
│   │   ├── .env.template                # Template para arquivos .env das stacks
│   │   ├── core/docker-compose.yml
│   │   ├── authelia/docker-compose.yml
│   │   ├── media/docker-compose.yml
│   │   ├── rag/docker-compose.yml
│   │   ├── productivity/docker-compose.yml
│   │   ├── automation/docker-compose.yml
│   │   ├── monitoring/docker-compose.yml
│   │   └── watchtower/docker-compose.yml
├── scripts/                             # Scripts auxiliares
│   ├── bootstrap.sh                     # Configura a máquina de controle Ansible
│   └── restore.sh                       # Script para executar o deploy completo
├── homelab-wiki/                        # Esta documentação MkDocs
│   ├── docs/
│   │   ├── index.md
│   │   └── ... (outros arquivos da wiki)
│   └── mkdocs.yml
├── .gitignore                           # Especifica arquivos não versionados pelo Git
└── README.md                            # Descrição geral do projeto no repositório
```

### Ações Imediatas para Estruturação do Projeto

Siga estes passos na sua máquina de controle Ansible:

1.  **Crie o diretório raiz do projeto e navegue até ele:**
    ```bash
    mkdir infra-servidor-domestico && cd infra-servidor-domestico
    ```

2.  **Inicialize o repositório Git:**
    ```bash
    git init
    ```

3.  **Crie a estrutura de diretórios detalhada acima.** Você pode usar `mkdir -p` para criar diretórios aninhados de uma vez.
    Exemplo:
    ```bash
    mkdir -p ansible/inventories/home/group_vars/all ansible/playbooks ansible/roles/common ansible/roles/infra ansible/roles/apps docker/stacks/core scripts homelab-wiki/docs
    ```
    E continue para os demais diretórios.

4.  **Crie o arquivo `.gitignore` com o seguinte conteúdo:**
    ```gitignore
    # Arquivos de cache e temporários Python
    __pycache__/
    *.py[cod]
    *$py.class
    *.egg-info/
    .Python
    pip-log.txt
    pip-delete-this-directory.txt
    .tox/
    .coverage
    .pytest_cache/

    # Ansible
    *.retry
    *.సురక్షితం # Ansible vault backup files (se o nome do vault for "सुरक्षित")
    ansible/cp/ # Ansible control path directory
    .ansible/ # Ansible temp files and logs
    # Embora o vault.yml deva ser commitado criptografado,
    # adicionar ao .gitignore previne commits acidentais se descriptografado temporariamente.
    ansible/inventories/home/group_vars/all/vault.yml

    # Docker
    # O .env.template PODE ser commitado como exemplo.
    # Arquivos .env REAIS com segredos NUNCA devem ser commitados.
    # Estes são gerados nas VMs ou gerenciados pelo Portainer.
    docker/stacks/*/.env
    docker/stacks/.env

    # Arquivos de sistema operacional
    .DS_Store
    Thumbs.db

    # IDEs e editores
    .vscode/
    .idea/
    *.swp
    *~

    # Segredos e dados sensíveis explícitos
    secrets/
    *.key
    *.pem # Certificados privados, a menos que sejam públicos e parte da IaC
    *.token
    credentials.*

    # Logs
    *.log
    logs/

    # Binários e executáveis compilados (se houver)
    *.out
    *.exe
    *.dll
    *.so

    # MkDocs build
    site/
    ```
    !!! important "Segurança de Segredos"
        O arquivo `ansible/inventories/home/group_vars/all/vault.yml` conterá segredos e será criptografado pelo Ansible Vault. Mesmo assim, é uma boa prática adicioná-lo ao `.gitignore` para evitar que ele seja commitado acidentalmente se você o descriptografar localmente para edição e esquecer de criptografá-lo novamente. Os arquivos `.env` reais usados pelas stacks Docker **NUNCA** devem ser commitados.

5.  **Crie um arquivo `README.md` inicial** na raiz do projeto com uma breve descrição.

6.  **Adicione todos os arquivos criados e faça o primeiro commit:**
    ```bash
    git add .
    git commit -m "Initial project structure, .gitignore, and basic README"
    ```

7.  **(Opcional, mas Altamente Recomendado)** Configure um repositório Git remoto (e.g., GitHub, GitLab) e envie (`push`) suas alterações iniciais. Isso serve como backup e facilita a colaboração ou o acesso de outras máquinas.

## 0.3. Considerações de Segurança e Resiliência

Estes são princípios fundamentais que nortearão a construção da sua infraestrutura:

*   **Segurança:**
    *   **Princípio do Menor Privilégio:** Cada componente e usuário deve ter apenas as permissões estritamente necessárias para realizar suas funções.
    *   **Atualizações Constantes:** Manter todos os softwares (Proxmox VE, sistema operacional das VMs, imagens Docker, aplicações) atualizados é crucial para corrigir vulnerabilidades.
    *   **Senhas Fortes e Únicas:** Use senhas complexas para todas as contas. O Ansible Vault será usado para gerenciar senhas da infraestrutura, e você deve usar um gerenciador de senhas pessoal para suas contas de usuário nos serviços.
    *   **Autenticação de Dois Fatores (2FA):** Será implementada com Authelia para proteger o acesso aos seus serviços.
    *   **Isolamento de Rede e Firewall:** Uso de redes Docker distintas e firewalls (Proxmox PVE Firewall e UFW nas VMs) para controlar o tráfego.
*   **Resiliência:**
    *   **Estratégia de Backup 3-2-1:** Manter pelo menos **3 cópias** dos seus dados importantes, em **2 mídias diferentes**, com **1 cópia off-site** (fora da sua residência). Este tópico será detalhado na [Seção 11: Manutenção e Backups](TODO-criar-link-para-secao-11-quando-existir).
    *   **ZFS para Proteção de Dados Local:** O pool `/data` configurado com ZFS em espelho (RAID 1) protegerá contra a falha de um dos HDDs. Snapshots ZFS também permitirão reversões rápidas.
    *   **Monitoramento:** Acompanhar a saúde e o desempenho do sistema através de ferramentas como Glances, Prometheus e Grafana para identificar e resolver problemas proativamente.
    *   **Infraestrutura como Código (IaC):** Usar Ansible permite reconstruir a infraestrutura de forma consistente e rápida em caso de falha.

Com este planejamento e estrutura inicial, você está pronto para avançar para a configuração da sua [Máquina de Controle Ansible](01-maquina-controle-ansible.md).
