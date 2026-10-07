---
description: "Redes Docker da arquitetura (proxy e internal_services): como funcionam, como conectar serviços e diagnosticar."
---

# Gerenciando Redes Docker

O Docker permite criar redes virtuais para isolar seus containers ou para permitir que eles se comuniquem de forma controlada. Em nossa arquitetura, utilizamos principalmente duas redes Docker `bridge` customizadas, `proxy` e `internal_services`, que foram criadas pelo Ansible ([Seção 5.4 do Manual de Implementação](../01-manual-implementacao/05-rede-segura.md#playbook-ansibleplaybookssetup-core-networkingyml)). Além dessas, o Docker possui uma rede `bridge` padrão.

Entender como essas redes funcionam e como gerenciá-las é importante para a conectividade e segurança dos seus serviços.

## Redes Docker Utilizadas em Nossa Arquitetura

### 1. Rede `proxy`

*   **Propósito Principal:** Esta é a rede à qual o nosso proxy reverso **Traefik** está conectado. Todos os containers que precisam ser expostos à internet (ou acessados através de um subdomínio via Traefik) também devem ser conectados a esta rede.
*   **Tipo:** Rede `bridge` customizada.
*   **Criação:** Foi criada como uma rede externa (ou seja, gerenciada fora de um `docker-compose.yml` específico de uma stack) pelo playbook Ansible `setup-core-networking.yml`.
    ```bash
    # Comando Ansible aproximado usado para criar a rede 'proxy'
    # community.docker.docker_network:
    #   name: proxy
    #   state: present
    ```
*   **Uso nos Arquivos `docker-compose.yml`:**
    Quando um serviço precisa ser acessado via Traefik, ele é conectado a esta rede.
    ```yaml
    # Exemplo em um docker-compose.yml
    networks:
      proxy:
        external: true # Indica que a rede 'proxy' já existe e não deve ser criada por este compose

    services:
      meu_servico_web:
        image: ...
        networks:
          - proxy # Conecta este serviço à rede proxy
        labels: # Labels para Traefik descobrir e rotear para este serviço
          - "traefik.enable=true"
          - "traefik.http.routers.meuservicoweb.rule=Host(`meuservico.{{ base_domain }}`)"
          # ... outras labels Traefik ...
    ```
*   **Comunicação:**
    *   Containers na rede `proxy` podem se comunicar entre si usando seus nomes de serviço Docker como hostnames (graças à resolução DNS interna do Docker para redes customizadas).
    *   Traefik (também na rede `proxy`) usa esta rede para descobrir e rotear tráfego para os serviços backend baseados em suas labels Docker.

### 2. Rede `internal_services`

*   **Propósito Principal:** Esta rede é usada para comunicação **backend** entre containers que **NÃO** precisam ser expostos diretamente pela rede `proxy` ou externamente. Ela fornece um canal de comunicação isolado.
*   **Exemplos de Uso:**
    *   O container da aplicação Nextcloud (`nextcloud_app`, que está na rede `proxy` para ser acessado externamente) se comunica com seu container de banco de dados (`nextcloud_db`) e com o container Redis (`nextcloud_redis`) através da rede `internal_services`. Os containers `nextcloud_db` e `nextcloud_redis` estão *apenas* na rede `internal_services`, não na `proxy`.
    *   Sonarr/Radarr (na rede `proxy` para suas UIs) se comunicam com qBittorrent (que também pode ter sua UI na `proxy`) através da rede `internal_services` para enviar tarefas de download.
*   **Tipo:** Rede `bridge` customizada.
*   **Criação:** Também criada como uma rede externa pelo playbook Ansible `setup-core-networking.yml`.
*   **Uso nos Arquivos `docker-compose.yml`:**
    ```yaml
    # Exemplo em um docker-compose.yml para um serviço com backend
    networks:
      proxy:
        external: true
      internal_services:
        external: true

    services:
      minha_aplicacao_frontend:
        image: ...
        networks:
          - proxy           # Para ser acessível via Traefik
          - internal_services # Para se comunicar com o backend_db
        # ...
      meu_servico_backend_db:
        image: ...
        networks:
          - internal_services # Apenas nesta rede, não acessível diretamente via proxy
        # ...
    ```
*   **Isolamento:** Serviços que estão *apenas* na rede `internal_services` não são diretamente acessíveis pela rede `proxy` (e, portanto, não são diretamente acessíveis via Traefik a partir da internet), a menos que um container na rede `proxy` atue explicitamente como um gateway para eles.

### 3. Rede `bridge` Padrão do Docker

*   **Comportamento:** Se você iniciar um container Docker sem especificar explicitamente uma rede (`--network` na CLI ou `networks:` no compose), ele é automaticamente conectado à rede `bridge` padrão criada pelo Docker Engine na sua inicialização.
*   **Isolamento:** Containers na rede `bridge` padrão podem se comunicar entre si (geralmente usando seus endereços IP internos, pois a resolução por nome pode ser limitada ou requerer links legados).
*   **Acesso Externo (Host):** Para expor um serviço de um container na rede `bridge` padrão, você precisa usar o mapeamento de portas (`-p HOST_PORT:CONTAINER_PORT`).
*   **Nosso Uso:** Em nossa arquitetura, nós **explicitamente atribuímos todos os nossos containers de aplicação às redes customizadas `proxy` ou `internal_services`** para melhor controle, organização e para aproveitar a resolução DNS por nome de serviço. Evitamos usar a rede `bridge` padrão para serviços definidos em stacks.

## Comandos Docker Úteis para Gerenciamento de Redes

Execute estes comandos na VM onde o Docker está rodando (e.g., na `core-services-vm` via SSH) para inspecionar e gerenciar suas redes Docker:

*   **Listar todas as redes Docker existentes:**
    ```bash
    docker network ls
    ```
    Você deverá ver `bridge`, `host`, `none`, e suas redes customizadas `proxy` e `internal_services`.

*   **Inspecionar uma rede específica:**
    Este comando fornece detalhes sobre a rede, incluindo sua sub-rede IP, gateway, e quais containers estão atualmente conectados a ela.
    ```bash
    docker network inspect proxy
    docker network inspect internal_services
    ```

*   **Criar uma nova rede Docker (se não for gerenciada pelo Ansible):**
    Embora nossas redes principais sejam criadas pelo Ansible, você pode precisar criar redes temporárias ou para outros propósitos.
    ```bash
    # Cria uma rede bridge customizada chamada 'minha_outra_rede'
    docker network create minha_outra_rede
    ```

*   **Conectar um container existente a uma rede:**
    Útil se um container foi iniciado sem estar na rede correta ou se você precisa que ele acesse recursos de outra rede temporariamente.
    ```bash
    docker network connect minha_outra_rede nome_do_meu_container
    ```

*   **Desconectar um container de uma rede:**
    ```bash
    docker network disconnect minha_outra_rede nome_do_meu_container
    ```

*   **Remover uma rede Docker:**
    Você só pode remover uma rede se nenhum container estiver atualmente conectado a ela.
    ```bash
    docker network rm minha_outra_rede
    ```
    !!! warning "Não Remova Redes Gerenciadas!"
        Evite remover manualmente as redes `proxy` ou `internal_services`, pois elas são gerenciadas pelo Ansible e são essenciais para o funcionamento das suas stacks. Se precisar recriá-las, é melhor usar o playbook Ansible.

## Quando Considerar a Criação de Novas Redes Docker?

Embora as redes `proxy` e `internal_services` cubram a maioria dos nossos casos de uso para esta arquitetura, podem surgir cenários onde redes adicionais sejam benéficas:

*   **Isolamento Mais Granular entre Stacks ou Grupos de Serviços:**
    Se você tem um grupo de serviços que precisam se comunicar intensamente entre si, mas devem ser completamente isolados de outros grupos (além do que `internal_services` já oferece), uma rede dedicada para eles pode adicionar uma camada extra de segmentação.
*   **Configurações de Rede Específicas para uma Stack:**
    Se uma stack particular requer um driver de rede Docker diferente do `bridge` padrão (embora raro para nosso escopo) ou se você precisa de uma sub-rede IP específica apenas para os containers daquela stack, sem que eles se misturem com `internal_services`.
*   **Stacks de Terceiros com Redes Próprias:**
    Algumas aplicações Docker Compose de terceiros que você pode encontrar online podem vir com suas próprias definições de rede internas (não marcadas como `external: true`). Ao implantá-las, o Docker Compose criará essas redes apenas para aquela stack. Isso é normal e ajuda no isolamento da stack. Se essa stack precisar interagir com nossas redes `proxy` ou `internal_services`, você pode adicioná-las como redes externas à definição da stack de terceiros.

## Resolução de Nomes DNS Interna do Docker (Revisão)

Uma das grandes vantagens de usar redes Docker `bridge` customizadas é a resolução DNS automática baseada no nome do serviço:

*   **Dentro da Mesma Rede Customizada:** Containers conectados à **mesma rede Docker customizada** (como `proxy` ou `internal_services`) podem se comunicar entre si usando diretamente o **nome do serviço** (conforme definido no `docker-compose.yml`) como se fosse um hostname. O Docker Engine fornece um servidor DNS embutido para cada rede customizada que lida com essa resolução.
    *   **Exemplo:** No `docker-compose.yml` da stack Nextcloud, o serviço `nextcloud_app` (conectado à rede `internal_services`) pode alcançar o serviço de banco de dados `nextcloud_db` (também na rede `internal_services`) simplesmente usando o hostname `nextcloud_db` nas suas configurações de conexão com o banco de dados.
*   **Rede `bridge` Padrão:** A resolução por nome de serviço é mais limitada ou inexistente na rede `bridge` padrão do Docker. Por isso, para aplicações definidas em `docker-compose.yml`, é sempre recomendado usar redes customizadas.

Entender como as redes Docker funcionam e como seus containers estão interconectados é crucial para garantir a comunicação correta e segura entre os serviços, bem como para o troubleshooting eficaz de problemas de conectividade.