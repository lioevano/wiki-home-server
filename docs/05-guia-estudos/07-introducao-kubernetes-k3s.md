# Introdução ao Kubernetes com K3s/K0s para Homelab

**Kubernetes** (frequentemente abreviado como **K8s**) é uma plataforma de orquestração de containers open-source extremamente poderosa e flexível, originalmente desenvolvida pelo Google e agora mantida pela Cloud Native Computing Foundation (CNCF). Ele automatiza o deploy, o escalonamento, a manutenção e o gerenciamento de aplicações containerizadas em um cluster de máquinas (nós).

Embora o Kubernetes completo ("vanilla" K8s) possa ser complexo de configurar e consumir muitos recursos, tornando-o um pouco intimidador para um ambiente de homelab com recursos limitados, surgiram **distribuições Kubernetes mais leves**, como **K3s** e **K0s**. Essas distribuições são projetadas para serem mais fáceis de instalar e gerenciar, e requerem menos recursos, tornando-as ideais para ambientes de borda (edge), IoT, desenvolvimento e, crucialmente, para **homelabs e aprendizado**.

!!! warning "Requisitos de Recursos e Complexidade Adicional"
    Rodar Kubernetes, mesmo uma distribuição leve como K3s ou K0s, **adicionará uma camada significativa de complexidade** à sua infraestrutura de servidor doméstico em comparação com o setup Docker/Portainer que implementamos. Além disso, ele **consumirá mais recursos do sistema (CPU e, especialmente, RAM)**.
    *   Com os 48GB de RAM do nosso host Proxmox, você tem mais margem, mas ainda precisará planejar cuidadosamente a alocação de recursos para as VMs que hospedarão seu cluster K3s/K0s.
    *   Pode ser necessário desligar outras VMs (como a `ai-desktop-vm` ou reduzir seus recursos) ou diminuir a alocação da `core-services-vm` se você decidir dedicar recursos significativos para um cluster Kubernetes.
    *   Considere começar com um cluster de nó único para aprendizado e expandir apenas se necessário e se os recursos permitirem.

## 1. Por que Considerar Kubernetes em um Homelab?

Mesmo que possa parecer um exagero para algumas necessidades de homelab, explorar Kubernetes oferece vários benefícios:

*   **Aprendizado de uma Tecnologia Chave da Indústria:** Kubernetes é a plataforma de orquestração de containers dominante em ambientes de produção e nuvem. Aprender K8s no seu homelab pode ser **extremamente valioso profissionalmente** e abrir portas para novas oportunidades de carreira.
*   **Portabilidade e Padronização de Aplicações:** Muitas aplicações modernas e projetos open-source são cada vez mais distribuídos como **Helm charts** (o gerenciador de pacotes para Kubernetes) ou manifestos YAML para Kubernetes. Isso facilita o deploy dessas aplicações em qualquer cluster K8s, incluindo o seu.
*   **Resiliência e Auto-Recuperação (Self-Healing):** Kubernetes é projetado para manter o estado desejado das suas aplicações. Ele pode automaticamente:
    *   Reiniciar containers que falharam.
    *   Substituir pods (conjuntos de containers) que não estão respondendo.
    *   Mover cargas de trabalho para nós saudáveis em um cluster multi-nó, caso um nó falhe (requer configuração apropriada).
*   **Escalabilidade (Conceitual para Homelab):** Embora você provavelmente não precise de escalabilidade massiva em casa, entender os conceitos de escalonamento horizontal de pods (aumentar/diminuir o número de réplicas de uma aplicação) e o auto-escalonamento (HPA - Horizontal Pod Autoscaler) é uma habilidade útil.
*   **Ecossistema Vibrante e Extensível:** Existe uma vasta gama de ferramentas, plugins e integrações construídas em torno do Kubernetes para:
    *   Monitoramento (e.g., Prometheus, Grafana via `kube-prometheus-stack`).
    *   Logging (e.g., Fluentd/Fluent Bit com Elasticsearch/Loki).
    *   Service Mesh (e.g., Istio, Linkerd) para gerenciamento avançado de tráfego entre microsserviços.
    *   CI/CD (e.g., ArgoCD, Flux).
*   **Infraestrutura como Código (IaC) para Aplicações:** Manifestos YAML do Kubernetes são uma forma de IaC para definir suas aplicações.

## 2. K3s e K0s: Distribuições Kubernetes Leves e Certificadas

Para tornar o Kubernetes mais acessível e menos intensivo em recursos, especialmente para casos de uso fora de grandes data centers, surgiram distribuições leves e certificadas pela CNCF (o que significa que são Kubernetes conformantes).

### K3s (Desenvolvido pela Rancher, agora parte da SUSE)

*   **Leve e Compacto:** Empacotado como um **único binário** com menos de 100MB.
*   **Totalmente Certificado pela CNCF:** É uma distribuição Kubernetes 100% compatível, o que significa que aplicações projetadas para Kubernetes vanilla devem rodar sem problemas no K3s.
*   **Simplificado e Otimizado:**
    *   Remove muitos componentes legados, alpha ou não essenciais do Kubernetes completo.
    *   Usa **SQLite como o backend de armazenamento de dados padrão** para o control plane (em vez do etcd, que é mais pesado), embora o etcd também seja suportado para setups HA.
    *   Substitui alguns componentes internos por alternativas mais leves.
*   **Fácil de Instalar e Operar:**
    *   Um script de instalação simples (`curl ... | sh -`) é geralmente suficiente para iniciar um cluster de nó único ou para adicionar nós worker.
    *   Menor sobrecarga operacional.
*   **Baixo Consumo de Recursos:** Requer significativamente menos RAM e CPU do que uma instalação K8s vanilla. Um nó de controle K3s pode rodar com apenas 512MB de RAM (embora mais seja recomendado para cargas de trabalho reais).
*   **Componentes "Batteries Included" (Opcionais):**
    *   Pode vir com um **Traefik Ingress Controller** embutido e habilitado por padrão (você pode desabilitá-lo se quiser usar outro).
    *   Inclui um **Service Load Balancer (Klipper LB)** simples que pode alocar IPs de uma faixa para serviços do tipo `LoadBalancer` em ambientes bare-metal/VM (útil se você não tem um provedor de nuvem).
    *   Pode incluir um sistema de métricas básico.
*   **Ideal para:** Homelabs, desenvolvimento local, ambientes de borda (edge computing), IoT, e pequenos clusters de produção.

### K0s (Desenvolvido pela Mirantis)

*   **Filosofia Similar ao K3s:** Também distribuído como um **único binário**, focado em simplicidade, conformidade com Kubernetes e redução de sobrecarga.
*   **Flexível e Customizável:**
    *   Permite uma maior customização na escolha de componentes do cluster durante a instalação, como a CNI (Container Network Interface - e.g., Calico, Cilium, Flannel) e o backend de armazenamento para o control plane.
*   **Seguro por Padrão:** Tem um forte foco em configurações seguras desde o início.
*   **Instalação e Gerenciamento:** Utiliza uma ferramenta de linha de comando chamada `k0sctl` para gerenciar a instalação, configuração e upgrade do cluster.
*   **Backend do Control Plane:** Suporta SQLite (padrão para single-node), etcd (para multi-node HA), ou até mesmo um backend de armazenamento externo usando `kine` (que permite usar PostgreSQL, MySQL, etc., como datastore para o Kubernetes API server).
*   **Ideal para:** Usuários que precisam de uma distribuição Kubernetes leve mas querem mais controle sobre a configuração dos componentes do cluster.

!!! tip "K3s ou K0s para Começar no Homelab?"
    Ambos são excelentes opções e muito capazes para um ambiente de homelab.
    *   **K3s** é frequentemente citado como sendo um pouco **mais fácil e rápido para iniciar um cluster de aprendizado rapidamente**, especialmente um de nó único, devido ao seu script de instalação direto.
    *   **K0s** oferece um pouco mais de **flexibilidade e controle sobre a configuração inicial** se você tiver requisitos específicos para componentes como a CNI ou o datastore do control plane.
    Para um primeiro contato e para seguir tutoriais, **K3s pode ser uma escolha ligeiramente mais simples para começar.**

## 3. Conceitos Fundamentais do Kubernetes (Revisão e Expansão)

Entender estes conceitos é absolutamente essencial antes de começar a trabalhar com Kubernetes:

*   **Nó (Node):** Uma máquina (física ou virtual, como nossas VMs Proxmox) que faz parte do seu cluster Kubernetes.
    *   **Nó do Plano de Controle (Control Plane Node / Master Node):**
        Gerencia o estado geral do cluster. Armazena os dados de configuração do cluster (no etcd ou SQLite). Executa componentes críticos como o `kube-apiserver` (a API do Kubernetes), `kube-scheduler` (que decide em qual nó um Pod deve rodar), e `kube-controller-manager` (que executa vários controladores para manter o estado desejado). Em clusters K3s/K0s de nó único, este nó também atua como worker.
    *   **Nó de Trabalho (Worker Node):**
        É onde suas aplicações (em containers dentro de Pods) realmente rodam. Cada nó worker executa:
        *   `kubelet`: Um agente que se comunica com o `kube-apiserver` do control plane e gerencia os containers no seu nó.
        *   `kube-proxy`: Mantém as regras de rede nos nós para permitir a comunicação com os Pods e Services.
        *   Um **Container Runtime Interface (CRI)** compatível, como `containerd` (que é o padrão para K3s, K0s e Kubernetes moderno, substituindo o DockerShim).

*   **Pod:**
    *   A **menor e mais básica unidade de deploy** no Kubernetes.
    *   Um Pod representa um **grupo de um ou mais containers** (como containers Docker) que são sempre **co-localizados** (rodam no mesmo nó), **co-agendados**, e rodam em um **contexto compartilhado**.
    *   **Contexto Compartilhado:** Containers dentro do mesmo Pod compartilham:
        *   O mesmo namespace de rede (o mesmo endereço IP dentro do cluster, podem se comunicar via `localhost`).
        *   Opcionalmente, os mesmos volumes de armazenamento (PersistentVolumes).
    *   **Geralmente, um Pod contém um único container principal** que executa sua aplicação, mas pode ter containers "sidecar" para tarefas auxiliares (e.g., coleta de logs, proxy, injeção de configuração).
    *   Pods são considerados **efêmeros**; eles podem ser destruídos e recriados (com um novo IP) pelo Kubernetes.

*   **Deployment (Implantação):**
    *   Um objeto Kubernetes que gerencia um conjunto de Pods replicados e define o **estado desejado** para eles.
    *   Você declara: "Eu quero 3 réplicas do meu Pod da aplicação X rodando a imagem Y". O Deployment (através de um ReplicaSet que ele cria) garante que esse número de réplicas esteja sempre rodando.
    *   Lida com **atualizações de aplicações** (e.g., rolling updates para atualizar para uma nova versão da imagem sem downtime) e **rollbacks** para versões anteriores.

*   **Service (Serviço):**
    *   Como os Pods são efêmeros e seus IPs podem mudar, o Service define uma **abstração de rede estável** para expor um conjunto de Pods (geralmente selecionados por `labels`) como um serviço de rede único.
    *   Um Service obtém um **endereço IP virtual estável (ClusterIP)** e um **nome DNS interno ao cluster** (e.g., `meu-servico.meu-namespace.svc.cluster.local`). Outros Pods no cluster podem acessar os Pods do serviço usando este IP/DNS estável.
    *   **Tipos de Service:**
        *   `ClusterIP` (Padrão): Expõe o serviço apenas em um IP interno ao cluster. Acessível apenas de dentro do cluster.
        *   `NodePort`: Expõe o serviço em uma porta estática (na faixa de 30000-32767) em *cada um* dos seus nós worker. Você pode acessar o serviço via `<IP_DO_NÓ>:<NodePort>`. Útil para acesso externo simples em desenvolvimento ou quando um LoadBalancer não está disponível.
        *   `LoadBalancer`: Expõe o serviço externamente usando um balanceador de carga de um provedor de nuvem (AWS, GCP, Azure). Para clusters bare-metal/VM como o nosso, isso requer uma implementação de balanceador de carga adicional, como:
            *   **MetalLB:** Uma solução popular para fornecer serviços do tipo `LoadBalancer` em clusters bare-metal, alocando IPs da sua rede LAN.
            *   **Klipper LB (ServiceLB):** Um balanceador de carga mais simples incluído no K3s, que usa portas disponíveis nos nós do cluster para expor serviços `LoadBalancer`.
        *   `ExternalName`: Mapeia um Service para um nome DNS externo (usando um CNAME).

*   **Ingress:**
    *   Gerencia o **acesso HTTP e HTTPS externo** aos Services dentro do seu cluster. Atua como um proxy reverso ou API gateway para seus serviços web.
    *   Para que um Ingress resource funcione, você precisa de um **Ingress Controller** rodando no seu cluster. O Ingress Controller é o software que realmente implementa as regras definidas nos seus Ingress resources.
        *   Exemplos de Ingress Controllers: **Traefik** (K3s pode vir com ele), **Nginx Ingress Controller**, Caddy Ingress Controller, HAProxy Ingress, etc.
    *   **Regras de Roteamento:** Você define Ingress resources (arquivos YAML) com regras para rotear tráfego baseado em:
        *   **Host:** (e.g., `app1.meudominio.com` vai para `service-A`, `app2.meudominio.com` vai para `service-B`).
        *   **Path:** (e.g., `meudominio.com/app1` vai para `service-A`, `meudominio.com/app2` vai para `service-B`).
    *   **Terminação SSL/TLS:** O Ingress Controller pode lidar com a terminação SSL/TLS (descriptografar tráfego HTTPS) e gerenciar certificados, muitas vezes integrando-se com `cert-manager` para certificados Let's Encrypt.

*   **Namespace:**
    *   Uma forma de **dividir os recursos do seu cluster Kubernetes em múltiplos "clusters virtuais" isolados logicamente**.
    *   Útil para organizar aplicações, separar ambientes (desenvolvimento, teste, produção em um mesmo cluster), ou para cenários multi-tenant.
    *   Recursos como Pods, Deployments, Services são criados dentro de um namespace específico (o namespace `default` é usado se nenhum for especificado). Nomes de recursos devem ser únicos dentro de um namespace.

*   **ConfigMap e Secret:**
    *   **ConfigMap:** Usado para armazenar dados de configuração **não sensíveis** (e.g., arquivos de configuração de aplicações, variáveis de ambiente, argumentos de linha de comando) em formato chave-valor. Esses dados podem ser consumidos por Pods (montados como volumes ou injetados como variáveis de ambiente).
    *   **Secret:** Usado para armazenar dados **sensíveis** (e.g., senhas, tokens de API, chaves SSH, certificados TLS).
        *   Os dados em Secrets são armazenados codificados em **base64** por padrão, o que **NÃO é criptografia**.
        *   Para segurança real, o backend de armazenamento do Kubernetes (etcd ou o datastore do K3s/K0s) deve ser configurado para **criptografia em repouso (encryption at rest)** para os Secrets. K3s e K0s têm mecanismos para isso.
        *   Secrets também podem ser consumidos por Pods como volumes montados ou variáveis de ambiente.

*   **Armazenamento Persistente: PersistentVolume (PV), PersistentVolumeClaim (PVC) e StorageClass:**
    Como os Pods (e seus containers) são efêmeros e podem ser destruídos/recriados, os dados que precisam persistir (e.g., bancos de dados, uploads de usuários) devem ser armazenados em volumes persistentes.
    *   **PersistentVolume (PV):** Representa um "pedaço" de armazenamento físico ou de rede que foi disponibilizado para o cluster. Pode ser provisionado manualmente por um administrador ou dinamicamente por um `StorageClass`.
    *   **PersistentVolumeClaim (PVC):** É uma **requisição de armazenamento** feita por um usuário ou uma aplicação (definida em um manifesto YAML). O PVC especifica o tamanho do armazenamento necessário, o modo de acesso (e.g., ReadWriteOnce, ReadOnlyMany, ReadWriteMany), e opcionalmente uma `StorageClass`.
    *   O Kubernetes tenta encontrar um PV existente que satisfaça as condições do PVC ou, se uma `StorageClass` com provisionamento dinâmico estiver configurada, ela tentará criar um PV automaticamente.
    *   **StorageClass:** Define **tipos de armazenamento** disponíveis no cluster e como o provisionamento dinâmico de PVs deve ocorrer. Cada `StorageClass` aponta para um "provisionador" de volume específico.
        *   **Exemplos de Provisionadores para Homelab/Bare-Metal:**
            *   **Local Path Provisioner (K3s/K0s podem incluir um):** Usa diretórios no sistema de arquivos do nó worker para criar PVs. Simples, mas o PV fica preso àquele nó. Se o nó falhar, o acesso ao PV é perdido até que o nó volte.
            *   **ZFS Local PV Provisioner (e.g., OpenEBS ZFS LocalPV):** Se seus nós worker têm ZFS, este provisionador pode criar ZFS datasets ou ZVOLs dinamicamente para os PVs. Os dados ainda são locais ao nó.
            *   **Longhorn (da Rancher):** Uma solução de storage distribuído e replicado, nativa do Kubernetes. Cria volumes replicados entre os nós worker, oferecendo resiliência a falhas de nó. Pode ser mais complexo de configurar e consumir mais recursos.
            *   **NFS CSI Driver (ou provisionador NFS externo):** Permite usar seu servidor NFS existente (como o do nosso host Proxmox) para fornecer armazenamento para PVs. Os PVs seriam diretórios no seu compartilhamento NFS.
            *   **Ceph (via Rook-Ceph ou Proxmox HCI):** Se você tiver um cluster Ceph, ele pode fornecer storage persistente altamente disponível e escalável para Kubernetes.

*   **`kubectl` (Kubernetes Command-Line Tool):**
    *   A ferramenta de linha de comando principal e indispensável para interagir com qualquer cluster Kubernetes.
    *   Usada para:
        *   Aplicar manifestos YAML para criar/atualizar recursos (`kubectl apply -f meu_manifesto.yaml`).
        *   Inspecionar o estado de recursos (`kubectl get pods`, `kubectl describe deployment meu-deploy`).
        *   Ver logs de Pods (`kubectl logs nome_do_pod -c nome_do_container`).
        *   Executar comandos dentro de containers (`kubectl exec -it nome_do_pod -- /bin/bash`).
        *   Gerenciar contextos de cluster (se você trabalha com múltiplos clusters).

## 4. Roteiro Básico para Instalar um Cluster K3s Simples em VMs Proxmox (Exemplo Conceitual)

Este é um exemplo muito básico para ilustrar os passos gerais. **Consulte sempre a documentação oficial do K3s para as instruções de instalação mais recentes e detalhadas.**

**Pré-requisitos:**
*   Pelo menos uma VM Linux no Proxmox (e.g., Ubuntu Server 22.04). Para um cluster multi-nó, você precisará de mais VMs.
*   **Recursos da VM:**
    *   **Nó de Controle (Master):** Pelo menos 1-2 vCPUs, 2-4GB RAM (K3s é leve, mas o control plane precisa de alguma margem).
    *   **Nó Worker:** Pelo menos 1-2 vCPUs, 2GB+ RAM (depende das cargas de trabalho que você rodará).
*   As VMs devem ter endereços IP estáticos ou nomes DNS resolúveis dentro da sua LAN.
*   Se for um cluster multi-nó, as VMs precisam de conectividade de rede entre si (e com a internet para baixar imagens).
*   Acesso SSH à(s) VM(s).

**Passo 1: Instalar K3s no Nó de Controle (Master)**

1.  Conecte-se via SSH à VM que será seu nó de controle.
2.  Execute o script de instalação oficial do K3s. Este script detecta o sistema e instala o K3s como um serviço systemd.
    ```bash
    curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644
    # A flag --write-kubeconfig-mode 644 torna o arquivo kubeconfig legível pelo usuário atual,
    # o que é conveniente para acesso imediato com kubectl na própria VM.
    #
    # Para instalar com opções, como desabilitar o Traefik Ingress embutido (se você planeja usar outro):
    # curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --disable=traefik" sh -s - --write-kubeconfig-mode 644
    #
    # Para especificar um IP/Interface para o K3s escutar (se a VM tiver múltiplos IPs):
    # curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --node-ip=IP_DA_VM_PARA_K3S --flannel-iface=eth0" sh -s -
    ```
3.  **Verifique se o serviço K3s está rodando:**
    ```bash
    sudo systemctl status k3s
    # Deve estar 'active (running)'
    ```
4.  **Acessar o Cluster com `kubectl`:**
    *   **Na própria VM do K3s Control Plane:**
        O K3s instala um `kubectl` embutido e configura o acesso. Você pode usar:
        ```bash
        sudo k3s kubectl get nodes
        # Ou, se você definiu --write-kubeconfig-mode 644 e tem kubectl instalado:
        # kubectl get nodes (usará /etc/rancher/k3s/k3s.yaml)
        ```
    *   **De uma Máquina de Controle Remota (seu desktop/laptop):**
        1.  **Copie o arquivo `kubeconfig`:** O arquivo de configuração para acessar o cluster é criado em `/etc/rancher/k3s/k3s.yaml` no nó de controle K3s. Você precisa copiar este arquivo para sua máquina de controle, no diretório `~/.kube/config` (este é o local padrão que `kubectl` procura).
            ```bash
            # Na VM do K3s control plane:
            sudo cat /etc/rancher/k3s/k3s.yaml
            ```
            Copie o conteúdo YAML exibido.
        2.  **Na sua máquina de controle:**
            Crie o diretório `~/.kube` se não existir: `mkdir -p ~/.kube`
            Crie/edite o arquivo `~/.kube/config` e cole o conteúdo YAML.
            **Importante:** No arquivo `kubeconfig` colado, localize a linha `server: https://127.0.0.1:6443`. Você precisará mudar `127.0.0.1` para o **endereço IP real da sua VM do K3s control plane** (e.g., `server: https://192.168.15.X:6443`).
            Proteja o arquivo: `chmod 600 ~/.kube/config`
        3.  **Instale `kubectl` na sua máquina de controle** se ainda não o tiver. Siga as [instruções oficiais de instalação do kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/) (ou para macOS/Windows).
        4.  **Teste a conexão da sua máquina de controle:**
            ```bash
            kubectl get nodes
            # Você deve ver seu nó de controle K3s listado com status "Ready".
            ```

**Passo 2: (Opcional) Adicionar Nós Worker ao Cluster K3s**

Se você quiser um cluster multi-nó (requer mais VMs):

1.  **Prepare uma nova VM Linux** para ser o nó worker (com IP estático, conectividade de rede com o nó de controle).
2.  **No Nó de Controle K3s, obtenha o token do cluster:**
    Este token é usado para que os nós worker possam se juntar ao cluster de forma segura.
    ```bash
    # Na VM do K3s control plane
    sudo cat /var/lib/rancher/k3s/server/node-token
    ```
    Copie este token.
3.  **Na VM que será o Nó Worker, execute o script de instalação do K3s como agente:**
    Você precisa fornecer a URL do servidor K3s (o nó de controle) e o token.
    ```bash
    # Na VM worker, substitua IP_DO_CONTROL_PLANE e SEU_TOKEN_AQUI
    curl -sfL https://get.k3s.io | K3S_URL=https://IP_DO_CONTROL_PLANE:6443 K3S_TOKEN=SEU_TOKEN_AQUI sh -
    ```
4.  **Verifique se o Novo Nó se Juntou ao Cluster:**
    Na sua máquina de controle (ou no nó de controle K3s), execute:
    ```bash
    kubectl get nodes -o wide
    ```
    Você deverá ver ambos os nós (controle e worker) listados com status "Ready".

**Passo 3: Configurar Armazenamento Persistente (StorageClass)**

Para que suas aplicações no Kubernetes possam armazenar dados de forma persistente, você precisará de uma **StorageClass** e um provisionador de volume.
*   **Local Path Provisioner (Padrão no K3s):** K3s geralmente vem com o "Local Path Provisioner" habilitado por padrão. Ele cria uma `StorageClass` chamada `local-path`. Quando um `PersistentVolumeClaim` (PVC) solicita esta `StorageClass`, ele provisiona um `PersistentVolume` (PV) usando um diretório no sistema de arquivos do nó worker onde o Pod está agendado (geralmente em `/var/lib/rancher/k3s/storage/<NOME_DO_PV>`).
    *   **Simples para começar, mas tem limitações:** Os dados são locais ao nó. Se o nó falhar, o acesso ao PV é perdido. Não é adequado para dados que precisam ser acessíveis de qualquer nó ou que exigem replicação.
*   **Outras Opções para Homelab (Mais Robustas):**
    *   **NFS CSI Driver:** Se você tem seu servidor NFS no host Proxmox (como fizemos), você pode instalar o [NFS Subdir External Provisioner](https://github.com/kubernetes-sigs/nfs-subdir-external-provisioner) (ou o driver CSI NFS mais moderno) no seu cluster K3s. Isso permite que PVs sejam criados como subdiretórios no seu compartilhamento NFS, tornando os dados acessíveis de qualquer nó.
    *   **ZFS Local PV (e.g., OpenEBS ZFS LocalPV):** Se suas VMs worker K3s têm acesso a storage ZFS, este provisionador pode criar ZFS datasets/ZVOLs dinamicamente para PVs. Os dados ainda são locais ao nó.
    *   **Longhorn:** Uma solução de storage distribuído e replicado, nativa do Kubernetes. Pode criar volumes replicados entre os nós worker, oferecendo resiliência. Mais complexo de configurar.

**Passo 4: Instalar um Ingress Controller (se você desabilitou o Traefik padrão do K3s)**

Se você desabilitou o Traefik Ingress embutido no K3s (e.g., com `INSTALL_K3S_EXEC="server --disable=traefik"`), você precisará instalar um Ingress Controller manualmente para gerenciar o acesso HTTP/S externo aos seus serviços.
*   **Opções Populares:**
    *   **Traefik (via Helm Chart):** Você pode instalar a versão oficial do Traefik Proxy usando seu Helm chart.
    *   **Nginx Ingress Controller:** Uma implementação muito popular e robusta.
    *   **Caddy Ingress Controller:** Se você prefere o Caddy.
*   A instalação geralmente envolve aplicar manifestos YAML ou usar Helm.

## 5. Exemplo: Deploy de uma Aplicação Simples no K3s (Nginx)

Suponha que você queira rodar um servidor web Nginx simples no seu cluster K3s.

1.  **Crie um arquivo de manifesto YAML (e.g., `nginx-k3s.yaml`):**
    ```yaml
    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: nginx-deployment
      labels:
        app: nginx
    spec:
      replicas: 2 # Queremos 2 instâncias (Pods) do Nginx
      selector:
        matchLabels:
          app: nginx # O Deployment gerencia Pods com esta label
      template: # Define o template do Pod
        metadata:
          labels:
            app: nginx # Os Pods terão esta label
        spec:
          containers:
          - name: nginx-container
            image: nginx:1.25-alpine # Imagem Docker do Nginx
            ports:
            - containerPort: 80 # Nginx escuta na porta 80 dentro do container
    ---
    apiVersion: v1
    kind: Service
    metadata:
      name: nginx-service
    spec:
      selector:
        app: nginx # Este Service seleciona Pods com a label app=nginx
      ports:
        - protocol: TCP
          port: 80       # Porta que o Service expõe DENTRO do cluster
          targetPort: 80 # Porta nos Pods para onde o tráfego é direcionado
      # type: ClusterIP # Padrão. Acessível apenas de dentro do cluster pelo IP do Service.
      # Para acesso externo simples em desenvolvimento/homelab:
      type: NodePort   # Expõe o serviço em uma porta aleatória (30000-32767) em CADA nó do cluster.
      # Ou, se tiver um LoadBalancer como MetalLB ou o KlipperLB do K3s:
      # type: LoadBalancer
    ```

2.  **Aplique o Manifesto ao Cluster K3s:**
    Na sua máquina de controle (ou na VM do K3s control plane, usando `sudo k3s kubectl`), execute:
    ```bash
    kubectl apply -f nginx-k3s.yaml
    ```

3.  **Verifique os Recursos Criados:**
    *   Ver o Deployment: `kubectl get deployments`
    *   Ver os Pods (e em quais nós eles estão rodando): `kubectl get pods -o wide`
    *   Ver o Service: `kubectl get service nginx-service`
        Se `type: NodePort`, a saída mostrará a porta mapeada (e.g., `80:3XXXX/TCP`).

4.  **Acessar o Nginx:**
    *   Se `type: NodePort`, você pode acessar o Nginx em `http://<IP_DE_QUALQUER_NÓ_DO_CLUSTER>:<NodePort_MAPEADA>`.
    *   Se `type: LoadBalancer` e você tem MetalLB/KlipperLB configurado, use o `EXTERNAL-IP` mostrado por `kubectl get service nginx-service`.
    *   Se você tem um **Ingress Controller** configurado, você criaria um recurso `Ingress` para expor o `nginx-service` através de um hostname (e.g., `nginx.meudominio.com`) com SSL.

## Considerações Adicionais e Próximos Passos no Aprendizado de K8s

*   **Gerenciamento de Configuração e Deploy:**
    *   **Helm:** O gerenciador de pacotes para Kubernetes. Permite instalar e gerenciar aplicações complexas (definidas em "charts") de forma fácil.
    *   **Kustomize:** Uma ferramenta para customizar manifestos YAML do Kubernetes sem "templating". Integrada ao `kubectl`.
*   **Monitoramento e Logging no Kubernetes:**
    *   **Prometheus e Grafana:** A stack `kube-prometheus-stack` (um Helm chart) é a forma padrão de instalar um sistema de monitoramento completo para seu cluster K8s.
    *   **Logging:** Fluentd, Fluent Bit, ou Promtail para coletar logs dos Pods e enviá-los para um backend como Elasticsearch ou Loki.
*   **Segurança no Kubernetes:**
    *   RBAC (Role-Based Access Control): Define quem pode fazer o quê no cluster.
    *   NetworkPolicies: Controlam o tráfego de rede entre Pods (como um firewall para Pods).
    *   Pod Security Standards (ou as antigas PodSecurityPolicies): Definem restrições de segurança para Pods.
    *   Secrets Management: Uso de Secrets do Kubernetes e integração com soluções como HashiCorp Vault.
*   **Service Mesh (Avançado):**
    *   Ferramentas como Istio ou Linkerd para gerenciamento avançado de tráfego, observabilidade e segurança entre microsserviços.

Explorar Kubernetes, mesmo em um ambiente leve como K3s ou K0s, é uma jornada de aprendizado contínua e recompensadora. Comece com um cluster de nó único, implante aplicações simples, entenda os conceitos básicos de Pods, Deployments e Services, e depois expanda gradualmente para armazenamento persistente, Ingress, e outros conceitos mais avançados.

**Recursos Recomendados:**
*   ➡️ **[Documentação Oficial do K3s](https://docs.k3s.io/)**
*   ➡️ **[Documentação Oficial do K0s](https://docs.k0sproject.io/)**
*   ➡️ **[Documentação Oficial do Kubernetes](https://kubernetes.io/docs/)**
*   Canais do YouTube como "Techno Tim", "NetworkChuck" (para iniciantes), "Just Me and Opensource" têm ótimos tutoriais sobre K3s em homelabs.