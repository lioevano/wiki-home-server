# Aprofundamento em Docker e Redes de Containers

Docker simplifica o empacotamento e a execução de aplicações, mas sua funcionalidade de rede é um componente poderoso e, por vezes, complexo. Entender melhor como as redes Docker funcionam pode ajudá-lo a projetar stacks mais seguras, eficientes e solucionar problemas de conectividade.

Nossa arquitetura já utiliza redes `bridge` customizadas (`proxy` e `internal_services`). Esta seção explora outros drivers de rede e conceitos.

## 1. Drivers de Rede Docker

Docker oferece vários drivers de rede, cada um com diferentes capacidades e casos de uso.

*   **`bridge` (Padrão para Redes Customizadas):**
    *   **Como Funciona:** Cria uma bridge Linux virtual no host Docker (a VM, no nosso caso). Containers conectados a esta rede recebem um endereço IP de uma sub-rede privada gerenciada pelo Docker. O Docker configura NAT para permitir que containers acessem redes externas (e.g., a internet) através do IP do host Docker.
    *   **Isolamento:** Containers na mesma rede `bridge` customizada podem se comunicar entre si usando seus nomes de serviço como hostnames (resolução DNS interna do Docker). Eles são isolados de containers em outras redes, a menos que um container esteja conectado a múltiplas redes.
    *   **Port Mapping:** Para expor um serviço de um container na rede `bridge` para o host Docker (e, portanto, potencialmente para fora), você usa o mapeamento de portas (e.g., `-p 8080:80`).
    *   **Nosso Uso:** As redes `proxy` e `internal_services` são do tipo `bridge`.

*   **`host`:**
    *   **Como Funciona:** Remove o isolamento de rede entre o container e o host Docker. O container compartilha diretamente a interface de rede do host Docker.
    *   **Sem NAT/Port Mapping:** Se um container escuta na porta 8000, ele está diretamente acessível na porta 8000 do IP do host Docker. Não há necessidade de `-p`.
    *   **Casos de Uso:**
        *   Quando a performance de rede é absolutamente crítica e o overhead do NAT da bridge é um problema (raro para homelab).
        *   Para serviços que precisam descobrir outros serviços na rede local do host usando broadcast/multicast (e.g., alguns aspectos de descoberta de rede do Plex ou Home Assistant, embora existam alternativas).
        *   Quando a configuração de rede do container precisa ser idêntica à do host.
    *   **Contras:** Menos seguro, pois o container tem mais acesso à rede do host. Conflitos de porta são mais prováveis se múltiplos containers tentarem usar a mesma porta no host.
    *   **Exemplo:** `docker run --network host ...` ou no compose: `network_mode: host`.

*   **`overlay`:**
    *   **Como Funciona:** Projetado para redes multi-host, permitindo que containers em diferentes hosts Docker (parte de um cluster Docker Swarm ou Kubernetes) se comuniquem como se estivessem na mesma rede. Cria uma rede virtual "sobreposta" à rede física dos hosts.
    *   **Casos de Uso:** Docker Swarm, Kubernetes.
    *   **Contras:** Mais complexo de configurar que `bridge`. Não relevante para nosso setup de Docker single-host (por VM).

*   **`macvlan`:**
    *   **Como Funciona:** Permite atribuir um endereço MAC a um container, fazendo com que ele apareça na rede local como um dispositivo físico separado, com seu próprio endereço IP da sua sub-rede LAN (obtido via DHCP da sua LAN ou configurado estaticamente).
    *   **Isolamento:** O container está diretamente na sua LAN, bypassando o NAT do Docker.
    *   **Casos de Uso:**
        *   Para aplicações que precisam de um IP dedicado na LAN (e.g., alguns servidores de jogos, ou se você quiser que um serviço seja descoberto como um dispositivo físico).
        *   Quando você precisa evitar o NAT do Docker por algum motivo.
    *   **Contras:**
        *   Mais complexo de configurar. Requer especificar a interface física do host Docker a ser usada.
        *   **Comunicação Host-Container:** Por padrão, o host Docker **não pode** se comunicar com containers na rede `macvlan` que usam sua própria interface física. São necessárias configurações adicionais (e.g., uma interface `macvlan` secundária no host).
        *   Pode exigir modo promíscuo na interface física do host.

*   **`ipvlan`:**
    *   Similar ao `macvlan` em que dá aos containers IPs da rede local, mas opera na camada 3 (IP) em vez da camada 2 (MAC). Containers compartilham o MAC da interface do host.
    *   Pode oferecer melhor performance e escalabilidade que `macvlan` em alguns cenários.
    *   Também tem complexidades na configuração e na comunicação host-container.

*   **`none`:**
    *   O container recebe sua própria stack de rede, mas sem nenhuma interface de rede configurada, exceto a interface de loopback (`lo`).
    *   **Casos de Uso:** Para containers que não precisam de acesso à rede (e.g., para processamento batch que só opera em volumes montados).

!!! tip "Qual Driver Usar?"
    Para a maioria dos casos de uso em um homelab single-host como o nosso, **redes `bridge` customizadas são a melhor escolha**. Elas oferecem bom isolamento, resolução DNS por nome de serviço e gerenciamento de portas flexível. `host` pode ser útil em casos específicos, mas use com cautela. `overlay`, `macvlan`, e `ipvlan` são para cenários mais avançados.

## 2. Resolução DNS Interna do Docker

Uma das grandes conveniências das redes `bridge` customizadas é a resolução DNS automática baseada em nome de serviço.

*   **Como Funciona:** Quando você cria uma rede `bridge` customizada (e.g., `proxy` ou `internal_services`), o Docker habilita um servidor DNS embutido para essa rede.
*   **Nome do Serviço como Hostname:** Se você tem dois serviços, `app_web` e `app_db`, definidos no mesmo `docker-compose.yml` e conectados à mesma rede customizada, o container `app_web` pode alcançar o container `app_db` usando o hostname `app_db`.
    ```yaml
    # Exemplo no docker-compose.yml
    version: '3.9'
    networks:
      minha_rede_interna:

    services:
      app_web:
        image: ...
        networks:
          - minha_rede_interna
        environment:
          - DB_HOST=app_db # app_web pode usar 'app_db' para se conectar
      app_db:
        image: ...
        networks:
          - minha_rede_interna
    ```
*   **Aliases de Rede:** Você pode definir aliases de rede para um serviço se precisar que ele seja acessível por múltiplos nomes dentro da rede.
    ```yaml
    services:
      meu_servico:
        networks:
          minha_rede:
            aliases:
              - alias1_para_meu_servico
              - outro_nome
    ```
*   **Limitações:**
    *   A resolução DNS por nome de serviço só funciona para containers na **mesma rede Docker customizada**.
    *   Não funciona por padrão na rede `bridge` default (a que os containers usam se nenhuma rede for especificada).

## 3. Expondo Portas de Containers

Existem duas maneiras principais de tornar um serviço de container acessível:

*   **Mapeamento de Portas (Port Publishing):**
    *   No `docker-compose.yml`:
        ```yaml
        services:
          meu_servico:
            ports:
              - "IP_DO_HOST_VM:PORTA_EXTERNA:PORTA_INTERNA_CONTAINER" # e.g., "192.168.1.11:8080:80"
              - "PORTA_EXTERNA:PORTA_INTERNA_CONTAINER" # Escuta em 0.0.0.0 na VM
        ```
    *   Isso usa `iptables` (ou `nftables`) no host Docker para redirecionar tráfego da `PORTA_EXTERNA` no IP da VM para a `PORTA_INTERNA_CONTAINER` do container.
    *   Necessário se você não estiver usando um proxy reverso ou se quiser acesso direto ao serviço em uma porta específica da VM.

*   **Via Proxy Reverso (e.g., Traefik):**
    *   **Sem Mapeamento de Portas Direto:** O container **não** precisa ter sua porta mapeada na seção `ports` do `docker-compose.yml` se ele só for acessado via Traefik.
    *   **Conexão à Rede do Proxy:** O container deve estar conectado à mesma rede Docker que o Traefik (e.g., a rede `proxy`).
    *   **Labels Traefik:** As labels Docker instruem o Traefik sobre como rotear o tráfego para a porta interna do container.
        ```yaml
        services:
          meu_servico_traefik:
            networks:
              - proxy
            labels:
              - "traefik.http.routers.meuservico.rule=Host(`meuservico.{{ base_domain }}`)"
              - "traefik.http.services.meuservico.loadbalancer.server.port=8000" # Porta interna do container
            # NENHUMA seção 'ports:' aqui para acesso via Traefik
        ```
    *   **Vantagem:** Centraliza o gerenciamento de acesso, SSL, autenticação no Traefik.

## 4. Segurança de Redes Docker

*   **Princípio do Menor Privilégio de Rede:**
    *   Conecte containers apenas às redes que eles absolutamente precisam. Se um container de banco de dados só precisa ser acessado por um container de aplicação, coloque ambos em uma rede `internal_services` e não conecte o DB à rede `proxy`.
*   **Firewall do Host Docker (UFW na VM):**
    *   O UFW na sua `core-services-vm` controla quais portas da VM são acessíveis de fora da VM.
    *   Se você mapeia uma porta de container para a VM (e.g., `-p 8080:80`), você também precisa permitir tráfego para a porta `8080` no UFW da VM se quiser acessá-la de outras máquinas na sua LAN.
    *   Traefik (escutando em 80/443 na VM) é o ponto de entrada principal, e essas portas são permitidas pelo UFW.
*   **Interação Docker e `iptables`/`nftables`:**
    *   Docker manipula as regras de `iptables` (ou `nftables` em sistemas mais novos) no host para fazer o NAT e o mapeamento de portas funcionar.
    *   Isso pode, às vezes, conflitar com regras de firewall gerenciadas por UFW ou `firewalld` se não configurado corretamente. Geralmente, para mapeamentos de porta simples, o UFW e o Docker coexistem bem se o Docker for iniciado antes do UFW ou se o UFW for configurado para não interferir nas cadeias do Docker. A configuração padrão do UFW geralmente permite o encaminhamento que o Docker precisa.
*   **Não use `network_mode: host` a menos que seja estritamente necessário,** pois reduz o isolamento.

## 5. Comunicação entre Containers em Diferentes Stacks (Docker Compose Projects)

Se você tem duas stacks Docker Compose diferentes (e.g., `stack_A` e `stack_B`) e um serviço em `stack_A` precisa se comunicar com um serviço em `stack_B`:

1.  **Rede Externa Compartilhada:**
    *   Crie uma rede Docker externa: `docker network create minha_rede_compartilhada`.
    *   No `docker-compose.yml` de `stack_A` e `stack_B`, defina esta rede como externa e conecte os serviços relevantes a ela:
        ```yaml
        # docker-compose.yml de stack_A
        networks:
          minha_rede_compartilhada:
            external: true
        services:
          servico_de_A:
            networks:
              - minha_rede_compartilhada
        # ...
        ```
        ```yaml
        # docker-compose.yml de stack_B
        networks:
          minha_rede_compartilhada:
            external: true
        services:
          servico_de_B:
            networks:
              - minha_rede_compartilhada
        # ...
        ```
    *   Agora, `servico_de_A` pode alcançar `servico_de_B` usando o hostname `servico_de_B` (e vice-versa), pois estão na mesma rede customizada.
    *   Nossas redes `proxy` e `internal_services` já são exemplos disso, permitindo comunicação entre diferentes stacks que se conectam a elas.

## 6. Inspecionando o Tráfego de Rede Docker (Avançado)

Para troubleshooting avançado, você pode querer inspecionar o tráfego de rede de um container.

*   **`tcpdump` ou `tshark` dentro do Container:**
    *   Se a imagem do container permitir (ou se você puder `docker exec` e instalar), você pode rodar `tcpdump` ou `tshark` dentro do namespace de rede do container.
*   **`tcpdump` no Host Docker na Interface da Bridge:**
    *   Encontre o nome da interface da bridge Docker (e.g., `br-xxxxxx` ou `docker0`) usando `ip addr show` ou `docker network inspect <nome_da_rede>`.
    *   Execute `sudo tcpdump -i br-xxxxxx -n -vv port <porta>` no host Docker (VM).

Um bom entendimento da rede Docker é essencial para construir aplicações distribuídas e seguras. A documentação oficial do Docker ([Networking overview](https://docs.docker.com/network/)) é um excelente recurso para aprofundamento.