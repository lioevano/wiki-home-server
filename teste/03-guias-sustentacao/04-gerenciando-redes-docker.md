# Gerenciando Redes Docker

Docker permite criar redes virtuais para isolar containers ou permitir que eles se comuniquem. Nesta arquitetura, utilizamos principalmente duas redes customizadas, `proxy` e `internal_services`, além da rede `bridge` padrão do Docker.

## Redes Docker Utilizadas na Arquitetura

### 1. Rede `proxy`

*   **Propósito:** Esta é a rede à qual o Traefik (nosso proxy reverso) e todos os containers que precisam ser expostos externamente (ou acessados via Traefik) são conectados.
*   **Criação:** Criada como uma rede externa pelo playbook Ansible `setup-core-networking.yml` antes do deploy de qualquer stack que a utilize.
    ```bash
    # Comando Ansible usado (aproximadamente)
    # community.docker.docker_network:
    #   name: proxy
    #   state: present
    ```
*   **Uso no `docker-compose.yml`:**
    ```yaml
    networks:
      proxy:
        external: true # Indica que a rede já existe e não deve ser criada por este compose

    services:
      meu_servico_exposto:
        networks:
          - proxy
        # ... labels Traefik ...
    ```
*   **Comunicação:** Containers na rede `proxy` podem se comunicar entre si usando seus nomes de serviço Docker como hostnames. Traefik também usa esta rede para descobrir e rotear para os serviços baseados em suas labels.

### 2. Rede `internal_services`

*   **Propósito:** Usada para comunicação backend entre containers que **não** precisam ser expostos diretamente pela rede `proxy` ou externamente. Por exemplo, uma aplicação web (na rede `proxy`) comunicando-se com seu banco de dados (na rede `internal_services`).
*   **Criação:** Também criada como uma rede externa pelo playbook Ansible `setup-core-networking.yml`.
*   **Uso no `docker-compose.yml`:**
    ```yaml
    networks:
      proxy: # Se o serviço principal também precisa ser exposto
        external: true
      internal_services:
        external: true

    services:
      minha_app_web:
        networks:
          - proxy           # Para Traefik
          - internal_services # Para falar com o DB
        # ...
      meu_banco_de_dados:
        networks:
          - internal_services # Apenas nesta rede, não acessível via proxy
        # ...
    ```
*   **Isolamento:** Serviços apenas na rede `internal_services` não são diretamente acessíveis pela rede `proxy` (a menos que um container esteja em ambas as redes e atue como um gateway, o que não é o design comum aqui).

### 3. Rede `bridge` Padrão

*   Se um container é iniciado sem especificar uma rede, ele é conectado à rede `bridge` padrão do Docker.
*   Containers na rede `bridge` padrão podem se comunicar entre si usando seus endereços IP internos (a resolução por nome pode ser limitada).
*   Neste guia, explicitamente atribuímos containers às redes `proxy` ou `internal_services` para melhor controle e organização.

## Comandos Docker Úteis para Gerenciamento de Redes

Execute estes comandos na VM onde o Docker está rodando (e.g., `core-services-vm`):

*   **Listar todas as redes Docker:**
    ```bash
    docker network ls
    ```
*   **Inspecionar uma rede específica (ver containers conectados, config da rede):**
    ```bash
    docker network inspect proxy
    docker network inspect internal_services
    ```
*   **Criar uma nova rede Docker (se não usar Ansible):**
    ```bash
    docker network create minha_nova_rede
    ```
*   **Conectar um container existente a uma rede:**
    ```bash
    docker network connect minha_nova_rede nome_do_container_existente
    ```
*   **Desconectar um container de uma rede:**
    ```bash
    docker network disconnect minha_nova_rede nome_do_container_existente
    ```
*   **Remover uma rede Docker (só funciona se nenhum container estiver conectado a ela):**
    ```bash
    docker network rm minha_nova_rede
    ```

## Quando Criar Novas Redes Docker?

Embora `proxy` e `internal_services` cubram a maioria dos nossos casos de uso, você pode considerar criar redes adicionais para:

*   **Isolamento Mais Granular:** Se você tem um grupo de serviços que precisam se comunicar intensamente entre si, mas devem ser completamente isolados de outros grupos, uma rede dedicada para eles pode ser útil.
*   **Configurações de Rede Específicas:** Se um conjunto de containers precisa de um driver de rede diferente (além do `bridge` padrão), ou uma sub-rede IP específica.
*   **Stacks de Terceiros:** Algumas aplicações Docker Compose de terceiros podem vir com suas próprias definições de rede. Você pode optar por usá-las ou adaptá-las para se integrarem às suas redes `proxy`/`internal_services`.

## Resolução de Nomes DNS Interna do Docker

*   **Redes Customizadas (como `proxy`, `internal_services`):** Docker fornece resolução DNS automática para containers dentro da mesma rede customizada. Um container pode alcançar outro usando o nome do serviço definido no `docker-compose.yml` (ou o nome do container se especificado e único).
    *   Exemplo: No `docker-compose.yml` do Nextcloud, o serviço `nextcloud_app` pode se conectar ao serviço `nextcloud_db` usando o hostname `nextcloud_db` porque ambos estão conectados à rede `internal_services`.
*   **Rede `bridge` Padrão:** A resolução por nome é mais limitada. É mais confiável usar os endereços IP internos dos containers (que podem mudar) ou configurar links (obsoleto). É por isso que redes customizadas são preferíveis.

Entender como as redes Docker funcionam e como seus containers estão conectados é crucial para garantir a comunicação correta entre os serviços e para o troubleshooting de problemas de conectividade.
