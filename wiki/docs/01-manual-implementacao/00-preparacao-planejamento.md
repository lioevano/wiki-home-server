# Seção 0: Preparação e Planejamento

Antes de sair apertando botão, um planejamento cuidadoso e a preparação do ambiente são fundamentais para o sucesso do seu servidor doméstico. ~~Tipo eu que elaborei esta wiki antes mesmo de começar a implementar.~~ Esta seção aborda os pré-requisitos, a organização do projeto e considerações iniciais de segurança e resiliência.

## 0.0. Glossário de Termos Essenciais

Aqui estão algumas palavras difíceis que vão aparecer frequentemente durante a implementação:

*   **[Ansible](../05-referencia-rapida.md):** É a nossa grande ferramenta de automação. Ela automatiza configurações e instalações inteiras, criando todo o contexto para o uso a partir de código (Infraestrutura como Código - IaC).
*   **[Ansible Vault](../05-referencia-rapida.md):** Recurso do Ansible que permite criptografar arquivos YAML inteiros ou variáveis específicas que contêm dados sensíveis, como senhas e chaves de API.
*   **Cloudflare Tunnel:** Serviço da Cloudflare que cria um túnel seguro e criptografado de saída da sua rede local para a rede global da Cloudflare. Isso permite que você exponha serviços internos à internet sem abrir portas no seu roteador e sem expor seu IP público.
*   **[Container (Docker)](../05-referencia-rapida.md):** Empacota uma aplicação para rodar isolada do sistema. Atribui a ela um endereço de IP e configurações de rede, comportando-se como se fosse uma máquina virtual, ~~mas é só uma aplicação com suas dependências.~~
*   **Docker Compose:** Um arquivo no formato YAML que configura um container ou uma "stack" inteira (um conjunto de containers). Define redes (onde os containers interagem apenas com quem você definir), serviços (os próprios containers) e volumes (locais onde os dados dos containers ficam armazenados).
*   **[Proxmox VE](../05-referencia-rapida.md):** É um sistema operacional baseado em Debian, otimizado para rodar máquinas virtuais (KVM) e containers Linux (LXC). É a minha escolha para este projeto, visando a experimentação com diversas ferramentas.
*   **Portainer:** Um gerenciador de containers com interface gráfica leve e intuitiva.
*   **[Traefik](../05-referencia-rapida.md):** Proxy reverso moderno e dinâmico, e também um balanceador de carga.
*   **[ZFS](../05-referencia-rapida.md):** Sistema de arquivos avançado e gerenciador de volumes lógicos, conhecido por sua resiliência e funcionalidades.
*   **NFS (Network File System):** Protocolo para compartilhar diretórios através de uma rede. Usaremos para compartilhar datasets ZFS do host Proxmox com as VMs para os volumes Docker.
*   **Ollama:** Plataforma para rodar e gerenciar modelos de linguagem grandes (LLMs) localmente.
*   **VM (Máquina Virtual):** Emulação de um sistema de computador completo, rodando seu próprio sistema operacional.
*   **RAG (Retrieval Augmented Generation):** Técnica de Inteligência Artificial que combina as capacidades de LLMs com a busca de informação em uma base de dados externa para gerar respostas mais contextuais e precisas.
*   **[Authelia](../05-referencia-rapida.md):** Servidor de autenticação e autorização, usado aqui para fornecer Single Sign-On (SSO) e autenticação de dois fatores (2FA).

## 0.1. Hardware e Software Necessários

Para esta implementação, estou utilizando o seguinte setup:

### Hardware do Servidor Físico (Host Proxmox)

*   **CPU:** AMD Ryzen 5 5600G (com iGPU Vega e suporte a virtualização AMD-V).
*   **GPU (para passthrough):** AMD RX 5600XT.
*   **RAM:** **48GB DDR4**.
!!! note "Upgrade de RAM"
    O guia original foi pensado para 16GB de RAM. Esta versão considera 48GB, o que oferece muito mais flexibilidade para o tamanho e número de VMs e serviços. As alocações de RAM para VMs serão mais generosas.
*   **Armazenamento Primário (Proxmox OS e Discos das VMs):** SSD NVMe 1TB.
*   **Armazenamento Secundário (Pool de Dados ZFS `/data`):** 2x HDDs de 500GB. Serão configurados em um pool ZFS espelhado (RAID 1) para redundância.
!!! note "Espaço Útil ZFS para Dados"
    Com 2x HDDs de 500GB em espelho (RAID 1), você terá aproximadamente **500GB de espaço útil** para os dados das suas aplicações Docker (configs, mídia, downloads, etc.). Planeje de acordo.

### Máquina de Controle Ansible

Para esta função, você precisará de uma máquina secundária (ou sua máquina principal) para executar os comandos Ansible remotamente.

*   Um computador pessoal ou notebook.
*   **Sistema Operacional Suportado:**
    *   Linux (Ubuntu, Fedora, etc.)
    *   macOS
    *   Windows com WSL2 (Windows Subsystem for Linux 2)

### Rede Doméstica

*   Roteador com servidor DHCP habilitado (para atribuição inicial de IPs, embora usemos IPs estáticos para os servidores).
*   Conexão à Internet.

### Software e Contas (Antes de Iniciar)

*   **ISO do Proxmox VE:** Baixe a versão estável mais recente do [site oficial do Proxmox](https://www.proxmox.com/en/downloads).
*   **Ferramenta para Pendrive Bootável:**
    *   [Ventoy](https://www.ventoy.net/en/download.html) (Windows, macOS, Linux) _<- Minha escolha pessoal pela flexibilidade._
    *   [Rufus](https://rufus.ie/) (Windows)
    *   [Balena Etcher](https://www.balena.io/etcher/) (Windows, macOS, Linux)
*   **Cliente SSH:**
    *   OpenSSH (nativo em Linux e macOS).
    *   PuTTY (popular para Windows, ou use o cliente SSH nativo do Windows Terminal/PowerShell).
    *   **Domínio Próprio Registrado:** (e.g., `meudominio.com`)
    !!! important "Domínio Próprio é Essencial"
        Este guia depende de um domínio próprio para acesso externo seguro via Cloudflare Tunnel e para a correta emissão de certificados SSL/TLS.
    *   **Conta Cloudflare:** Crie uma [conta gratuita na Cloudflare](https://www.cloudflare.com/).
    *   Você precisará configurar seu domínio para usar os **nameservers da Cloudflare**.

## 0.2. Estrutura do Repositório Git do Projeto (`home-server`)

Graças ao Ansible, vamos adotar a Infraestrutura como Código (IaC), gerenciando todas as configurações e scripts em um repositório Git.

### Estrutura de Diretórios Proposta

A estrutura do seu projeto `home-server/` será:
```text
home-server/
├── ansible/
│   ├── inventories/
│   │   └── home/
│   │       ├── group_vars/
│   │       │   └── all/
│   │       │       ├── main.yml
│   │       │       └── vault.yml
│   │       └── hosts.ini
│   ├── playbooks/
│   │   # ... (lista de playbooks) ...
│   │   └── full-deploy.yml
│   └── roles/
│       ├── common/
│       ├── infra/
│       │   # ... (lista de roles de infra) ...
│       └── apps/
│           # ... (lista de roles de apps) ...
├── docker/
│   ├── stacks/
│   │   ├── .env.template
│   │   # ... (lista de stacks docker-compose) ...
├── scripts/
│   ├── bootstrap.sh
│   └── restore.sh
├── homelab-wiki/ # Esta documentação
│   └── ...
├── .gitignore
└── README.md
```

### Ações Imediatas para Estruturação do Projeto

Na sua máquina de controle Ansible:

1.  **Crie o diretório raiz do projeto e navegue até ele:**
```bash
mkdir home-server && cd home-server
```
2.  **Inicialize o repositório Git:**
```bash
git init
```
3.  **Crie a estrutura de diretórios completa** conforme detalhado no seu documento original (e resumido acima). Use `mkdir -p` para eficiência.
Exemplo parcial:
```bash
mkdir -p ansible/inventories/home/group_vars/all ansible/playbooks ansible/roles/common docker/stacks/core scripts
```
!!! tip "Dica para Criar Estrutura"
    Você pode listar a estrutura completa e usar um script simples ou até pedir a uma IA para gerar os comandos `mkdir -p` para você.
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
!!! important "Segurança de Segredos com .gitignore"
    O arquivo `ansible/inventories/home/group_vars/all/vault.yml` conterá segredos e será criptografado. Adicioná-lo ao `.gitignore` é uma camada extra de precaução contra commits acidentais se você o descriptografar localmente. Arquivos `.env` reais com segredos (gerados nas VMs ou gerenciados pelo Portainer) **NUNCA** devem ser commitados.
5.  **Crie um arquivo `README.md` inicial** na raiz do projeto com uma breve descrição.
6.  **Adicione todos os arquivos criados e faça o primeiro commit:**
```bash
git add .
git commit -m "Estrutura inicial do projeto home-server e IaC"
```
7.  **(Recomendado)** Configure um repositório Git remoto (e.g., GitHub, GitLab) e envie (`push`) suas alterações.

## 0.3. Considerações de Segurança e Resiliência

Estes são os pilares que sustentam a arquitetura:

*   **Segurança:**
    *   **Princípio do Menor Privilégio:** Cada componente e usuário terá apenas as permissões estritamente necessárias.
    *   **Atualizações Constantes:** Manteremos Proxmox, VMs, imagens Docker e aplicações atualizadas.
    *   **Senhas Fortes e Únicas:** Gerenciadas pelo Ansible Vault para a infraestrutura e um gerenciador pessoal para contas de usuário.
    *   **Autenticação de Dois Fatores (2FA):** Implementada com Authelia para proteger o acesso aos serviços.
    *   **Isolamento de Rede e Firewall:** Uso de redes Docker distintas e firewalls (Proxmox PVE Firewall e UFW nas VMs).
*   **Resiliência:**
    *   **Estratégia de Backup 3-2-1:** Pelo menos 3 cópias dos dados, em 2 mídias diferentes, com 1 cópia off-site. Detalhado na [Seção de Manutenção e Recuperação](../04-manutencao-recuperacao/index.md).
    *   **ZFS para Proteção de Dados Local:** O pool `/data` com RAID 1 e snapshots ZFS.
    *   **Monitoramento:** Acompanhamento da saúde do sistema para detecção proativa de problemas.
    *   **Infraestrutura como Código (IaC):** Ansible permite reconstruir a infraestrutura de forma consistente e rápida.

Com este planejamento e estrutura inicial, você está pronto para avançar para a configuração da sua [Máquina de Controle Ansible](01-maquina-controle-ansible.md).

