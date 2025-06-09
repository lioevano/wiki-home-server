# Seção 0: Preparação e Planejamento

Antes de sair apertando botão, um planejamento cuidadoso e a preparação do ambiente são fundamentais para o sucesso do seu servidor doméstico, ~~tipo eu que elaborei esta wiki antes mesmo de começar a implementar~~. Esta seção aborda os pré-requisitos, a organização do projeto e considerações iniciais de segurança e resiliência.

## 0.0. Glossário de Termos Essenciais

Aqui estão algumas palavras difíceis que vão aparecer frequentemente durante a implementação:

*   **[Ansible](../05-guia-estudos/03-aprofundamento-ansible.md):** É a nossa grande ferramenta de automação, ela automatiza configurações e instalações inteiras, criando todo o contexto para o uso a partir de código (IaC).
*   **[Ansible Vault](../05-guia-estudos/03-aprofundamento-ansible.md):** Recurso do Ansible que permite criptografar arquivos YAML inteiros ou variáveis específicas que contêm dados sensíveis, como senhas e chaves de API.
*   **Cloudflare Tunnel:** Serviço da Cloudflare que cria um túnel seguro e criptografado de saída da sua rede local para a rede global da Cloudflare, permitindo que você exponha serviços internos à internet sem abrir portas no seu roteador e sem expor seu IP público.
*   **[Container (Docker)](../05-guia-estudos/04-aprofundamento-docker-networking.md):** Empacota uma aplicação para rodar isolada do sistema, atribui a ela um endereço de IP e configurações de rede, se comportando como se fosse uma máquina virtual ~~mas é só uma aplicação~~.
*   **Docker Compose:** Um arquivo no formato YAML que configura um container ou uma stack inteira, que é um conjunto de containers, atribui redes (onde os containers interagem apenas com quem você definir), stacks e volumes (locais que os dados dos containers ficam armazenados).
*   **[Proxmox VE](../05-guia-estudos/01-aprofundamento-proxmox-ve.md):** É um sistema operacional feito para rodar máquinas virtuais e containers, minha escolha para esse projeto que visa a experimentação de diversas ferramentas.
*   **Portainer:** Gerenciador de containers com interface gráfica.
*   **[Traefik](../05-guia-estudos/05-aprofundamento-traefik-authelia.md):** Proxy reverso e balanceamento de carga.
*   **[ZFS](../05-guia-estudos/02-aprofundamento-zfs.md):** Sistema de arquivos avançado e gerenciador de volumes lógicos.
*   **NFS:** Protocolo para compartilhar diretórios através de uma rede. Usaremos para compartilhar datasets ZFS do host Proxmox com as VMs para os volumes Docker.
*   **Ollama:** Plataforma para rodar modelos de linguagem grandes (LLMs) localmente.
*   **VM (Máquina Virtual):** Emulação de um sistema de computador completo.
*   **RAG (Retrieval Augmented Generation):** Técnica de IA que combina LLMs com busca de informação externa.
*   **[Authelia]((05-guia-estudos/05-aprofundamento-traefik-authelia.md)):** Servidor de autenticação e autorização (1FA/2FA).

## 0.1. Hardware e Software Necessários

Para essa implementação aqui, eu vou usar o seguinte:

### Hardware do Servidor Físico (Host Proxmox)

*   **CPU:** AMD Ryzen 5 5600G (com iGPU Vega e suporte a virtualização AMD-V).
*   **GPU (com passthrough):** AMD RX 5600XT.
*   **RAM:** **16GB DDR4**.
!!! warning "Limitação de RAM (16GB)"
    Esta quantidade de RAM é o principal gargalo do projeto e influenciará o número e o tamanho das VMs e serviços que podem rodar simultaneamente. Este guia é otimizado para esta restrição, priorizando a estabilidade. Gerenciamento cuidadoso da memória será essencial.
*   **Armazenamento Primário (Proxmox OS e Discos das VMs):** SSD NVMe 1TB.
*   **Armazenamento Secundário (Pool de Dados ZFS `/data`):** 2x HDDs de 500GB. Estes serão configurados em um pool ZFS espelhado (RAID 1), que é uma configuração que mantém os dois em redundância, diminuindo o risco de perdas.
!!! note "Espaço Útil ZFS para Dados"
    Com 2x HDDs de 500GB em espelho (RAID 1), você terá aproximadamente **500GB de espaço útil** para os dados das suas aplicações Docker (configs, mídia, downloads, etc.).

### Máquina de Controle Ansible

Para esse cenário, precisaremos de uma máquina secundária que irá servir para fazer as configurações iniciais do nosso ambiente remotamente (não é um limitante, apenas um facilitador).

*   Um computador pessoal ou notebook.
*   **Sistema Operacional Suportado:**
    *   Linux
    *   macOS
    *   Windows com WSL2 (Windows Subsystem for Linux 2)

### Rede Doméstica

*   Roteador com servidor DHCP habilitado (para atribuição inicial de IPs).

### Software e Contas (Antes de Iniciar)

*   **ISO do Proxmox VE:** Baixe a versão estável mais recente do [site oficial do Proxmox](https://www.proxmox.com/en/downloads).
*   **Ferramenta para Pendrive Bootável:**
    *   [Ventoy](https://www.ventoy.net/en/download.html) (Windows, macOS, Linux) _<- minha escolha_
    *   [Rufus](https://rufus.ie/) (Windows)
    *   [Balena Etcher](https://www.balena.io/etcher/) (Windows, macOS, Linux)
*   **Cliente SSH:**
    *   OpenSSH (nativo em Linux e macOS).
    *   PuTTY (popular para Windows).
*   **Domínio Próprio Registrado:** (e.g., `meudominio.com`)
!!! important "Domínio Próprio é Essencial"
    Este guia depende disso para acesso externo seguro via Cloudflare.
*   **Conta Cloudflare:** Crie uma [conta gratuita na Cloudflare](https://www.cloudflare.com/).
    *   Configure seu domínio para usar os **nameservers da Cloudflare**. Isso é necessário para que o Cloudflare Tunnel e o gerenciamento de certificados SSL/TLS funcionem corretamente.

## 0.2. Estrutura do Repositório Git do Projeto (`home-server`)

Graças ao Ansible, vamos usar a técnica de Infraestrutura como Código (IaC), gerenciando todas as configurações e scripts em um repositório Git.

### Estrutura de Diretórios Proposta

Crie a seguinte estrutura de diretórios e arquivos na sua máquina de controle Ansible:

```text
home-server/
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
├── .gitignore                           # Especifica arquivos não versionados pelo Git
└── README.md                            # Descrição geral do projeto no repositório
```

### Ações Imediatas para Estruturação do Projeto

Etapas na máquina de controle:

1.  **Crie o diretório raiz do projeto e navegue até ele:**
    ```bash
    mkdir home-server && cd home-server
    ```

2.  **Inicialize o repositório:**
    ```bash
    git init
    ```

3.  **Crie a estrutura de diretórios detalhada acima.** Você pode usar `mkdir -p` para criar vários diretórios de uma vez.
    Exemplo:
    ```bash
    mkdir -p ansible/inventories/home/group_vars/all ansible/playbooks ansible/roles/common ansible/roles/infra ansible/roles/apps docker/stacks/core scripts homelab-wiki/docs
    ```
    E assim para toda a estrutura de diretórios. ~~Você também pode copiar a estrutura de diretórios proposta e pedir para o ChatGPT gerar um arquivo .zip daquela estrutura para um commit inicial.~~

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
    *.safe  # Arquivos de backup do Ansible Vault (nome padrão se não customizado)
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
    ```
!!! important "Segurança de Segredos"
    O arquivo `ansible/inventories/home/group_vars/all/vault.yml` conterá segredos e será criptografado pelo Ansible Vault. Mesmo assim, é uma boa prática adicioná-lo ao `.gitignore` para evitar que ele seja commitado acidentalmente se você o descriptografar localmente para edição e esquecer de criptografá-lo novamente. Os arquivos `.env` reais usados pelas stacks Docker **NUNCA** devem ser commitados.

5.  **Crie um arquivo `README.md` inicial** com uma breve descrição do que planeja pro seu projeto.

6.  **Adicione todos os arquivos criados e faça o primeiro commit:**
    ```bash
    git add .
    git commit -m "Primeiro commit da estrutura do projeto =]"
    ```

7.  **(Opcional, mas Altamente Recomendado)** Configure um repositório Git remoto (e.g., GitHub, GitLab) e envie (`push`) suas alterações iniciais. Isso serve como backup e facilita a colaboração ou o acesso de outras máquinas.

## 0.3. Considerações de Segurança e Resiliência

Os pilares de segurança e resiliência que o projeto se fundamenta são:

*   **Segurança:**
    *   **Princípio do Menor Privilégio:** Cada componente e usuário deve ter apenas as permissões necessárias.
    *   **Atualizações Constantes:** Manter tudo constantemente atualizado para evitar vulnerabilidades.
    *   **Senhas Fortes e Únicas:** Use senhas complexas para todas as contas.
    *   **Autenticação de Dois Fatores (2FA):** Será implementada com Authelia para proteger o acesso aos seus serviços.
    *   **Isolamento de Rede e Firewall:** Uso de redes Docker distintas e firewalls (Proxmox PVE Firewall e UFW nas VMs) para controlar o tráfego.
*   **Resiliência:**
    *   **Estratégia de Backup 3-2-1:** Manter pelo menos **3 cópias** dos seus dados importantes, em **2 mídias diferentes**, com **1 cópia off-site** (fora da sua residência). Este tópico será detalhado na [Seção 11: Manutenção e Backups](../04-manutencao-recuperacao/index.md).
    *   **ZFS para Proteção de Dados Local:** O pool `/data` configurado com ZFS em RAID 1 protegerá contra a falha de um dos HDDs. Snapshots ZFS também permitirão reversões rápidas.
    *   **Monitoramento:** Acompanhar a saúde e o desempenho do sistema através de ferramentas como Glances, Prometheus e Grafana para identificar e resolver problemas.
    *   **Infraestrutura como Código (IaC):** Usar Ansible permite reconstruir a infraestrutura de forma consistente e rápida em caso de falha.

Dito isso, já podemos começar a configurar a [Máquina de Controle Ansible](01-maquina-controle-ansible.md).
