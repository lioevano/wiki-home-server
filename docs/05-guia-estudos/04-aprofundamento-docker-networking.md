# Aprofundamento em Docker e Redes de Containers

O Docker simplificou enormemente o empacotamento, a distribuição e a execução de aplicações em containers isolados. Um dos seus componentes mais poderosos, e por vezes um pouco complexo de entender completamente, é a sua **funcionalidade de rede**. Uma boa compreensão de como as redes Docker funcionam é crucial para projetar stacks de containers seguras e eficientes, e para solucionar problemas de conectividade.

Em nossa arquitetura de servidor doméstico, já utilizamos redes `bridge` customizadas (`proxy` e `internal_services`) para organizar a comunicação entre nossos containers. Esta seção explora mais a fundo os drivers de rede Docker, a resolução DNS interna, e outros conceitos importantes.

## 1. Drivers de Rede Docker: Uma Visão Geral

O Docker oferece vários **drivers de rede**, cada um com diferentes capacidades e casos de uso. Quando você cria uma rede Docker, você especifica qual driver ela deve usar.

*   **`bridge` (Padrão para Redes Customizadas e para a Rede `docker0` Padrão):**
    *   **Como Funciona:** Este é o driver mais comum. Quando você cria uma rede `bridge` customizada (como fizemos para `proxy` e `internal_services`), o Docker cria uma **bridge Linux virtual** no host Docker (a VM, no nosso caso, e.g., `core-services-vm`). Containers conectados a esta rede recebem um endereço IP de uma sub-rede privada gerenciada pelo Docker para aquela rede específica.
    *   O Docker configura automaticamente regras de **NAT (Network Address Translation)** para permitir que containers nesta rede acessem redes externas (como a internet ou outras partes da sua LAN) através do endereço IP do host Docker (a VM).
    *   **Isolamento:**
        *   Containers na **mesma rede `bridge` customizada** podem se comunicar entre si usando seus nomes de serviço Docker como hostnames (graças à resolução DNS interna do Docker).
        *   Por padrão, containers em **diferentes redes `bridge` customizadas são isolados** e não podem se comunicar diretamente, a menos que um container esteja conectado a ambas as redes (atuando como uma ponte) ou você configure roteamento explícito.
    *   **Mapeamento de Portas (Port Publishing):** Para expor um serviço de um container na rede `bridge` para o host Docker (a VM) e, potencialmente, para o mundo exterior (via Traefik ou port forwarding no roteador da VM, se não usar Traefik), você usa o mapeamento de portas (e.g., `-p HOST_VM_PORTA:CONTAINER_PORTA` na CLI, ou `ports:` no Docker Compose).
    *   **Nosso Uso:** As redes `proxy` e `internal_services` em nossa arquitetura são do tipo `bridge`. A rede `docker0` (que é criada por padrão quando o Docker é instalado) também é uma rede bridge, mas geralmente é recomendado criar suas próprias redes customizadas para melhor isolamento e para habilitar a resolução DNS por nome de serviço.

*   **`host`:**
    *   **Como Funciona:** Este driver **remove completamente o isolamento de rede** entre o container e o host Docker (a VM). O container compartilha diretamente a pilha de rede do host Docker.
    *   **Sem NAT ou Mapeamento de Portas:** Se um serviço dentro de um container configurado com `network_mode: host` escuta na porta `8000`, ele estará diretamente acessível na porta `8000` do endereço IP do host Docker (a VM). Não há necessidade de usar a diretiva `ports:` no Docker Compose.
    *   **Casos de Uso:**
        *   Quando a performance de rede é absolutamente crítica e o pequeno overhead do NAT da rede `bridge` é considerado um problema (muito raro para a maioria das aplicações de homelab).
        *   Para serviços que precisam descobrir outros serviços na rede local do host Docker usando mecanismos como broadcast ou multicast (e.g., alguns aspectos de descoberta de rede do Plex Media Server ou do Home Assistant para certos dispositivos, embora existam alternativas como mDNS repeaters ou configurações específicas de rede `bridge` para permitir multicast limitado).
        *   Quando a configuração de rede exata do container precisa ser idêntica à do host.
    *   **Contras:**
        *   **Menos Seguro:** Reduz significativamente o isolamento. Um processo comprometido no container tem mais acesso à rede do host.
        *   **Conflitos de Porta:** Como o container usa diretamente as portas do host, conflitos de porta são mais prováveis se múltiplos containers (ou serviços no host) tentarem usar a mesma porta.
    *   **Exemplo de Uso (Docker Compose):**
        ```yaml
        services:
          meu_servico_host_mode:
            image: ...
            network_mode: host # Remove o isolamento de rede
            # A seção 'ports:' NÃO seria usada aqui.
        ```

*   **`overlay`:**
    *   **Como Funciona:** Projetado especificamente para **redes multi-host**, permitindo que containers rodando em diferentes hosts Docker (que fazem parte de um cluster Docker Swarm ou Kubernetes) se comuniquem de forma transparente como se estivessem na mesma rede lógica. Ele cria uma rede virtual "sobreposta" (overlay) à rede física dos hosts.
    *   **Casos de Uso Primários:** Docker Swarm, Kubernetes.
    *   **Contras:** Mais complexo de configurar do que redes `bridge` single-host. Requer um setup de cluster (Swarm init, K/V store para Swarm).
    *   **Não Relevante para Nosso Setup Atual:** Como estamos usando Docker em VMs single-host (do ponto de vista do Docker Engine em cada VM), o driver `overlay` não é aplicável diretamente à nossa arquitetura atual.

*   **`macvlan`:**
    *   **Como Funciona:** Permite que você atribua um **endereço MAC virtual** a um container. Com isso, o container aparece na sua rede local (LAN) como se fosse um **dispositivo físico separado**, obtendo seu próprio endereço IP da sua sub-rede LAN (geralmente via DHCP do seu roteador principal, ou você pode configurar um IP estático para ele dentro da faixa da sua LAN).
    *   **Isolamento e Acesso Direto à LAN:** O container está diretamente na sua LAN, bypassando a camada de NAT do Docker que ocorre com redes `bridge`.
    *   **Casos de Uso:**
        *   Para aplicações que precisam de um endereço IP dedicado na sua LAN (e.g., alguns servidores de jogos legados, ou se você quiser que um serviço seja descoberto na rede como um dispositivo físico individual).
        *   Quando você precisa que a aplicação dentro do container veja o tráfego broadcast/multicast da sua LAN diretamente.
        *   Para evitar o NAT do Docker por requisitos específicos da aplicação.
    *   **Contras e Complexidades:**
        *   **Configuração Mais Complexa:** Requer que você especifique a interface de rede física do host Docker (a VM) à qual a rede `macvlan` será "anexada" (e.g., `eth0` da VM).
        *   **Comunicação Host-Container:** Por padrão, o host Docker (a VM) **NÃO PODE** se comunicar diretamente com os containers que estão em uma rede `macvlan` usando sua própria interface física. Isso ocorre porque o tráfego do host para o IP do container `macvlan` sairia pela interface física e o switch não o retornaria para a mesma interface. São necessárias configurações adicionais para permitir essa comunicação (e.g., criar uma interface `macvlan` secundária no modo bridge no host Docker e rotear o tráfego por ela).
        *   **Modo Promíscuo:** Pode exigir que a interface física do host Docker (ou a interface virtual da VM no Proxmox) seja colocada em modo promíscuo, dependendo da configuração do seu switch e do driver `macvlan`.
        *   **Limitações com WiFi:** Geralmente não funciona bem (ou de forma alguma) com interfaces de rede WiFi no host Docker, pois muitas placas WiFi não suportam múltiplos MACs ou modo promíscuo da maneira necessária.

*   **`ipvlan`:**
    *   Similar ao `macvlan` no sentido de que permite que containers obtenham endereços IP da sua rede local, mas opera na **Camada 3 (IP)** em vez da Camada 2 (MAC). Os containers que usam `ipvlan` compartilham o endereço MAC da interface do host Docker.
    *   Pode oferecer melhor performance e escalabilidade do que `macvlan` em alguns cenários de alta densidade de containers.
    *   Também possui suas próprias complexidades de configuração e considerações para comunicação host-container.

*   **`none`:**
    *   **Sem Rede:** Se você usar `docker run --network none ...`, o container é criado com sua própria pilha de rede, mas **sem nenhuma interface de rede configurada**, exceto a interface de loopback (`lo`).
    *   **Casos de Uso:** Para containers que não precisam de nenhum tipo de acesso à rede (e.g., para realizar um processamento em lote que opera apenas em volumes de dados montados, ou para testes de isolamento extremo).

!!! tip "Qual Driver de Rede Escolher?"
    *   Para a **maioria dos casos de uso em um homelab single-host** (como o nosso, onde cada VM tem seu próprio Docker Engine), as **redes `bridge` customizadas são a melhor escolha padrão.** Elas oferecem um bom equilíbrio de isolamento, facilidade de uso (com resolução DNS por nome de serviço) e gerenciamento de portas flexível.
    *   Use `network_mode: host` com muita cautela e apenas se for estritamente necessário por requisitos de performance extrema ou descoberta de rede baseada em broadcast/multicast que não podem ser resolvidos de outra forma.
    *   Os drivers `overlay`, `macvlan`, e `ipvlan` são para cenários mais avançados ou específicos que geralmente não são necessários para a arquitetura base deste guia.

## 2. Resolução DNS Interna do Docker (para Redes Customizadas)

Uma das funcionalidades mais convenientes das redes Docker `bridge` customizadas (como `proxy` e `internal_services` que criamos) é a **resolução DNS automática baseada no nome do serviço**.

*   **Como Funciona:**
    Quando você cria uma rede `bridge` customizada, o Docker Engine habilita um **servidor DNS embutido** para aquela rede específica. Este servidor DNS é responsável por resolver os nomes dos serviços (conforme definidos nos seus arquivos `docker-compose.yml`) para os endereços IP internos dos containers correspondentes naquela rede.
*   **Nome do Serviço como Hostname:**
    Se você tem dois serviços, por exemplo, `meu_app_web` e `meu_app_db`, definidos no mesmo arquivo `docker-compose.yml` e ambos estão conectados à **mesma rede Docker customizada** (e.g., `internal_services`):
    ```yaml
    # Exemplo em um docker-compose.yml
    version: '3.9'
    networks:
      minha_rede_interna_da_stack: # Rede definida para esta stack
        # Se esta rede não for 'external: true', ela é local para esta stack.

    services:
      meu_app_web:
        image: ...
        container_name: container_app_web
        networks:
          - minha_rede_interna_da_stack
        environment:
          # O container 'meu_app_web' pode usar 'meu_app_db' como hostname para conectar ao banco de dados
          - DATABASE_HOST=meu_app_db
          - DATABASE_PORT=5432
        depends_on:
          - meu_app_db

      meu_app_db:
        image: postgres:latest
        container_name: container_app_db
        networks:
          - minha_rede_interna_da_stack
        # ...
    ```
    Neste exemplo, o container `meu_app_web` pode se conectar ao serviço `meu_app_db` usando o hostname `meu_app_db`. O DNS interno do Docker para a rede `minha_rede_interna_da_stack` resolverá `meu_app_db` para o endereço IP interno do container `container_app_db`.
*   **Aliases de Rede (`network_aliases`):**
    Você pode definir aliases de rede para um serviço se precisar que ele seja acessível por múltiplos nomes diferentes dentro da mesma rede Docker.
    ```yaml
    services:
      meu_servico_principal:
        image: ...
        networks:
          minha_rede_comum:
            aliases:
              - alias_amigavel_para_meu_servico
              - outro_nome_de_acesso
    ```
    Outros containers na `minha_rede_comum` poderiam então acessar `meu_servico_principal` usando `alias_amigavel_para_meu_servico` ou `outro_nome_de_acesso` como hostname.
*   **Limitações e Escopo:**
    *   A resolução DNS por nome de serviço funciona de forma confiável **apenas para containers que estão na mesma rede Docker customizada**.
    *   Ela **não funciona por padrão** na rede `bridge` default do Docker (a rede chamada `bridge` que os containers usam se nenhuma rede for especificada no `docker run` ou `docker-compose.yml`). É por isso que é sempre recomendado usar redes customizadas para suas aplicações.
    *   Para comunicação entre containers em **diferentes redes Docker customizadas**, um container precisaria estar conectado a ambas as redes, ou você precisaria de um mecanismo de proxy/roteamento entre as redes (o que o Traefik faz entre a rede `proxy` e as portas internas dos serviços).

## 3. Expondo Portas de Containers Docker

Existem duas maneiras principais de tornar um serviço rodando dentro de um container Docker acessível de fora do container (ou seja, da VM host ou da sua LAN/Internet):

*   **Mapeamento de Portas (Port Publishing / `-p` ou `ports:`):**
    *   No `docker-compose.yml` (ou com `docker run -p ...`):
        ```yaml
        services:
          meu_servico_com_porta_mapeada:
            image: ...
            ports:
              # Sintaxe: "[IP_DO_HOST_VM:]PORTA_NO_HOST_VM:PORTA_DENTRO_DO_CONTAINER[/protocolo]"
              # Exemplo: Mapeia a porta 8080 da VM para a porta 80 do container
              - "8080:80"
              # Exemplo: Mapeia a porta 9090 no IP específico 192.168.15.11 da VM para a porta 9000 do container
              - "192.168.15.11:9090:9000"
              # Exemplo: Mapeia uma porta UDP
              # - "53:53/udp"
        ```
    *   **Como Funciona:** O Docker Engine usa regras de firewall do host (geralmente `iptables` ou `nftables` no Linux da VM) para criar uma regra de NAT que redireciona o tráfego chegando na `PORTA_NO_HOST_VM` (no IP especificado ou em todos os IPs da VM se não especificado) para a `PORTA_DENTRO_DO_CONTAINER` do container.
    *   **Quando Usar:**
        *   Se você **não** está usando um proxy reverso como Traefik para gerenciar todo o acesso externo.
        *   Se você precisa de acesso direto ao serviço em uma porta específica da VM a partir da sua LAN (e o firewall UFW da VM permite essa porta).
        *   Para alguns serviços que não são HTTP/S (e.g., um banco de dados que você quer acessar diretamente da sua LAN para desenvolvimento, embora isso deva ser feito com cautela e firewall).
*   **Via Proxy Reverso (e.g., Traefik - Nossa Abordagem Principal):**
    *   **Sem Mapeamento de Portas Direto no Compose do Serviço:** O container da aplicação (e.g., Nextcloud, Grafana) **NÃO** precisa ter sua porta principal mapeada na seção `ports:` do seu `docker-compose.yml` se ele for acessado *exclusivamente* através do Traefik.
    *   **Conexão à Rede do Proxy:** O container da aplicação DEVE estar conectado à mesma rede Docker que o Traefik (em nosso caso, a rede `proxy`).
    *   **Labels Traefik:** As labels Docker no `docker-compose.yml` do serviço instruem o Traefik sobre:
        *   Qual hostname (subdomínio) deve ser roteado para este serviço.
        *   Qual a **porta interna** do container para a qual o Traefik deve encaminhar o tráfego (e.g., `traefik.http.services.meuservico.loadbalancer.server.port=8000`).
        *   Quais middlewares aplicar (Authelia, headers de segurança, etc.).
    *   **Vantagens:**
        *   **Centralização do Ponto de Entrada:** Traefik (escutando nas portas 80/443 da VM) é o único ponto de entrada da rede externa para seus serviços web.
        *   **Gerenciamento SSL/TLS Centralizado.**
        *   **Autenticação Centralizada com Authelia.**
        *   Não há necessidade de abrir múltiplas portas no firewall UFW da VM (apenas 80/443 para Traefik).

## 4. Segurança de Redes Docker e Interação com Firewalls

*   **Princípio do Menor Privilégio de Rede:**
    *   Conecte seus containers **apenas às redes Docker que eles absolutamente precisam** para funcionar.
    *   Se um container de banco de dados só precisa ser acessado por um container de aplicação específico, coloque ambos em uma rede `internal_services` e **NÃO** conecte o container do banco de dados à rede `proxy` (a menos que haja um motivo muito específico e seguro para isso).
*   **Firewall do Host Docker (UFW na VM `core-services-vm`):**
    *   O UFW (Uncomplicated Firewall) rodando na sua `core-services-vm` controla quais portas da *própria VM* são acessíveis de fora dela (e.g., da sua LAN ou de outras VMs).
    *   Se você usa mapeamento de portas no Docker (e.g., `ports: - "8080:80"`), para acessar o serviço na porta `8080` da VM a partir de outra máquina na sua LAN, você também precisa permitir tráfego de entrada para a porta `8080` no UFW da VM.
    *   Em nossa arquitetura, o Traefik escuta nas portas 80 e 443 da VM, e estas são as principais portas que o UFW permite para tráfego de entrada relacionado aos nossos serviços web. Outras portas (como 9100 para Node Exporter) são abertas para fins específicos como scraping do Prometheus.
*   **Interação Docker e `iptables`/`nftables` (Firewall do Kernel Linux):**
    *   O Docker Engine manipula diretamente as regras de `iptables` (ou `nftables` em sistemas Linux mais novos) no kernel da VM para fazer o NAT, o mapeamento de portas e o isolamento de rede entre containers funcionar.
    *   Por padrão, as regras que o Docker adiciona à cadeia `FORWARD` do `iptables` (com política `ACCEPT`) geralmente permitem que os containers acessem redes externas e que o tráfego de portas mapeadas chegue aos containers, muitas vezes **bypassando** as regras definidas em firewalls de frontend como UFW se o UFW não estiver configurado para gerenciar a cadeia `DOCKER-USER`.
    *   **Para um controle mais rigoroso com UFW:** Você pode configurar o UFW para gerenciar a cadeia `DOCKER-USER` do iptables, permitindo um controle mais fino sobre qual tráfego pode alcançar seus containers. Isso é mais avançado e requer edição dos arquivos de configuração do UFW (e.g., `/etc/default/ufw` e `/etc/ufw/before.rules`). Para a maioria dos homelabs, confiar no isolamento das redes Docker customizadas e no Traefik como ponto de entrada para serviços web é uma boa base.
*   **Não use `network_mode: host` a menos que seja estritamente necessário e você entenda as implicações de segurança**, pois ele remove uma camada importante de isolamento de rede.

## 5. Comunicação entre Containers em Diferentes Stacks (Projetos Docker Compose)

Se você tem duas ou mais stacks Docker Compose diferentes (cada uma definida em seu próprio `docker-compose.yml` e gerenciada como uma "Stack" separada no Portainer) e um serviço em `stack_A` precisa se comunicar com um serviço em `stack_B`:

1.  **Use uma Rede Docker Externa Compartilhada:**
    *   Primeiro, crie uma rede Docker que será compartilhada (se ela ainda não existe). Nossas redes `proxy` e `internal_services` já são exemplos disso, pois foram criadas pelo Ansible como redes externas.
        ```bash
        # Exemplo de criação manual (se não usar Ansible para isso)
        # docker network create minha_rede_compartilhada_externa
        ```
    *   Em seguida, nos arquivos `docker-compose.yml` de **ambas** as stacks (`stack_A` e `stack_B`), defina esta rede como externa e conecte os serviços relevantes a ela:
        ```yaml
        # No docker-compose.yml da stack_A
        networks:
          minha_rede_compartilhada_externa:
            external: true # Importante!
        services:
          servico_da_stack_A:
            image: ...
            networks:
              - minha_rede_compartilhada_externa # Conecta a esta rede
            # ...
        ```
        ```yaml
        # No docker-compose.yml da stack_B
        networks:
          minha_rede_compartilhada_externa:
            external: true # Importante!
        services:
          servico_da_stack_B:
            image: ...
            networks:
              - minha_rede_compartilhada_externa # Também conecta a esta rede
            # ...
        ```
    *   Agora, `servico_da_stack_A` pode alcançar `servico_da_stack_B` usando o hostname `servico_da_stack_B` (e vice-versa), pois eles estão efetivamente na mesma rede Docker customizada, mesmo sendo definidos e gerenciados em stacks Docker Compose separadas.

Um bom entendimento da rede Docker é essencial para construir aplicações distribuídas, seguras e para solucionar problemas de conectividade de forma eficaz. A [documentação oficial do Docker sobre networking](https://docs.docker.com/network/) é um recurso excelente e abrangente para aprofundamento.