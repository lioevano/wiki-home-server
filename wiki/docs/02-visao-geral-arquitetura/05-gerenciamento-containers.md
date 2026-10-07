# Gerenciamento de Containers com Docker e Portainer

Containers Docker são a tecnologia fundamental para empacotar, distribuir e executar as diversas aplicações e serviços do nosso servidor doméstico. Portainer fornece uma interface gráfica amigável para gerenciar esses containers.

## Docker e Docker Compose: A Base da Containerização

### O que são Containers Docker?

*   **Isolamento Leve:** Containers fornecem isolamento em nível de processo e sistema de arquivos, permitindo que múltiplas aplicações rodem em um mesmo sistema operacional (na VM, neste caso) sem interferir umas com as outras. Eles compartilham o kernel do SO da VM host.
*   **Portabilidade:** Uma imagem Docker contém a aplicação e todas as suas dependências. Isso garante que a aplicação rodará da mesma forma em qualquer ambiente que suporte Docker.
*   **Eficiência de Recursos:** Comparados a VMs completas, containers são muito mais leves, consomem menos recursos (CPU, RAM, disco) e iniciam mais rapidamente.
*   **Imagens Docker:** São templates read-only que definem o container. São construídas a partir de um `Dockerfile` ou baixadas de registros como o Docker Hub (e.g., `plexinc/pms-docker`, `nextcloud:latest`).
*   **Containers Docker:** São instâncias executáveis de imagens Docker.

### Docker Compose para Aplicações Multi-Container (Stacks)

Muitas aplicações modernas são compostas por múltiplos serviços interdependentes (e.g., Nextcloud app + banco de dados + Redis). Docker Compose simplifica a definição e o gerenciamento dessas aplicações.

*   **Arquivo `docker-compose.yml`:** Um arquivo YAML que define:
    *   **Serviços:** Os containers que compõem a aplicação (e.g., `nextcloud_app`, `nextcloud_db`).
    *   **Imagem:** A imagem Docker a ser usada para cada serviço.
    *   **Volumes:** Como os dados persistentes são mapeados do host (neste caso, dos montados NFS na VM) para dentro do container. Isso garante que os dados sobrevivam a reinícios ou recriações do container.
        *   Exemplo: `- "${PROD_STACK_NEXTCLOUD_DATA_PATH}:/var/www/html/data"`
    *   **Redes:** As redes Docker às quais os containers se conectarão. Permite comunicação isolada ou controlada entre serviços.
        *   `proxy`: Para serviços que precisam ser expostos externamente via Traefik.
        *   `internal_services`: Para comunicação backend entre containers que não precisam de acesso direto da rede `proxy`.
    *   **Portas (Opcional):** Mapeamento de portas do host (VM) para o container, se não for usar um proxy reverso como Traefik para todo o acesso.
    *   **Variáveis de Ambiente:** Para passar configurações para os containers.
    *   **Labels:** Metadados, crucialmente usados pelo Traefik para descoberta de serviços e configuração de roteamento.
*   **Comandos:** `docker compose up -d` (para iniciar uma stack em background), `docker compose down` (para parar e remover containers da stack), `docker compose logs` (para ver logs). O Portainer abstrai esses comandos.

## Portainer: Interface Gráfica para Gerenciamento Docker

Embora o Docker Compose seja poderoso na linha de comando, o Portainer oferece uma interface web intuitiva para gerenciar seus ambientes Docker.

*   **Instalação:** Portainer foi instalado como um container Docker na `core-services-vm` pelo playbook Ansible `setup-base-ubuntu.yml`.
*   **Funcionalidades Principais Usadas Neste Guia:**
    *   **Gerenciamento de Endpoints:** Conecta-se ao Docker Engine local na `core-services-vm`. Opcionalmente, pode gerenciar outros Docker Engines remotos via Portainer Agent (como na `ai-desktop-vm`).
    *   **Stacks:** Permite implantar e gerenciar aplicações definidas por arquivos `docker-compose.yml`.
        *   Você pode colar o conteúdo do `docker-compose.yml` no editor web.
        *   Carregar variáveis de ambiente de um arquivo `.env` (preparado pelo Ansible).
        *   Definir secrets (variáveis de ambiente sensíveis) diretamente na UI do Portainer.
        *   Atualizar, parar, iniciar e remover stacks.
    *   **Containers:** Listar, inspecionar, ver logs, abrir console, parar, iniciar, remover containers individuais.
    *   **Volumes:** Listar e gerenciar volumes Docker (embora neste guia, os volumes principais sejam mapeamentos de caminhos NFS, não volumes Docker gerenciados pelo Portainer).
    *   **Redes:** Listar e gerenciar redes Docker.
    *   **Imagens:** Listar, puxar e remover imagens Docker.

## Fluxo de Deploy de um Serviço Docker com Portainer (Recapitulação)

1.  **Preparação Ansible (Opcional, mas Recomendado):**
    *   O playbook `setup-<stack>-volumes.yml` cria os diretórios necessários nos volumes NFS na VM de destino.
    *   Gera um arquivo `.env` (e.g., `/opt/portainer_stack_envs/minha_stack.env`) na VM com caminhos de volume e variáveis não sensíveis.
2.  **No Portainer:**
    *   Navegue para "Stacks" -> "+ Add stack".
    *   Dê um nome à stack.
    *   Cole o conteúdo do `docker-compose.yml` da aplicação.
    *   Em "Environment variables" (modo avançado):
        *   "Load variables from .env file": Especifique o caminho para o arquivo `.env` na VM (e.g., `/opt/portainer_stack_envs/minha_stack.env`).
        *   Adicione manualmente quaisquer secrets (senhas de DB, API keys) como variáveis de ambiente.
    *   Clique em "Deploy the stack".
3.  **Verificação:**
    *   Portainer executa os comandos `docker compose` para criar as redes (se definidas no compose e não `external`), puxar imagens e iniciar os containers.
    *   Verifique os logs dos containers no Portainer para garantir que tudo iniciou corretamente.
    *   Se o serviço usa Traefik para exposição, Traefik (se configurado com labels corretas no compose) deve detectar o novo serviço e configurar o roteamento e SSL.

Esta combinação de Docker, Docker Compose e Portainer oferece uma maneira poderosa e flexível de executar uma ampla gama de aplicações no seu servidor doméstico, mantendo a organização e facilitando o gerenciamento. Os volumes NFS garantem que os dados importantes das suas aplicações sejam armazenados de forma segura e persistente no seu pool ZFS.