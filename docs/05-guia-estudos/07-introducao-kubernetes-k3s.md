# Introdução ao Kubernetes com K3s/K0s para Homelab

Kubernetes (frequentemente abreviado como K8s) é uma plataforma de orquestração de containers open-source poderosa, originalmente desenvolvida pelo Google. Ele automatiza o deploy, o escalonamento e o gerenciamento de aplicações containerizadas. Embora o Kubernetes completo (K8s "vanilla") possa ser complexo e consumir muitos recursos, existem distribuições mais leves como K3s e K0s que são adequadas para ambientes de homelab e aprendizado.

!!! warning "Requisitos de Recursos e Complexidade"
    Rodar Kubernetes, mesmo uma distribuição leve, adicionará uma camada significativa de complexidade e **consumirá mais recursos (CPU, e especialmente RAM)** do que um setup Docker/Portainer simples. Com 16GB de RAM no host Proxmox, você precisará planejar cuidadosamente a alocação de recursos se decidir explorar o K3s/K0s. Pode ser necessário desligar outras VMs ou reduzir drasticamente seus recursos.

## 1. Por que Kubernetes em um Homelab?

*   **Aprendizado:** É uma tecnologia dominante na indústria para gerenciamento de containers em escala. Aprender K8s no seu homelab pode ser extremamente valioso profissionalmente.
*   **Portabilidade de Aplicações:** Muitas aplicações modernas são distribuídas como Helm charts ou manifestos Kubernetes, facilitando o deploy em qualquer cluster K8s.
*   **Resiliência e Auto-Recuperação:** K8s pode automaticamente reiniciar containers falhos, mover cargas de trabalho para nós saudáveis (em um cluster multi-nó) e gerenciar o estado desejado das suas aplicações.
*   **Escalabilidade (Conceitual para Homelab):** Embora você provavelmente não precise de escalabilidade massiva em casa, entender os conceitos de escalonamento horizontal de pods é útil.
*   **Ecossistema Vibrante:** Uma vasta gama de ferramentas e integrações (monitoramento, logging, service mesh, etc.) são construídas em torno do Kubernetes.

## 2. K3s e K0s: Distribuições Leves de Kubernetes

Para tornar o Kubernetes mais acessível para casos de uso de borda, IoT e homelab, surgiram distribuições leves:

### K3s (Desenvolvido pela Rancher/SUSE)

*   **Leve:** Empacotado como um único binário de menos de 100MB.
*   **Certificado CNCF:** É uma distribuição Kubernetes totalmente compatível.
*   **Simplificado:** Remove componentes legados, alpha ou não essenciais do K8s vanilla. Usa SQLite como backend de dados padrão (em vez de etcd, embora etcd seja suportado).
*   **Fácil de Instalar:** Um script simples geralmente é suficiente para iniciar um cluster de nó único ou multi-nó.
*   **Baixo Consumo de Recursos:** Requer significativamente menos RAM e CPU que o K8s completo.
*   **Componentes Incluídos (Opcionais):** Pode vir com Traefik Ingress Controller, Service Load Balancer (Klipper LB) e um sistema de métricas básico.
*   **Ideal para:** Homelabs, desenvolvimento, IoT, borda.

### K0s (Desenvolvido pela Mirantis)

*   **Filosofia Similar ao K3s:** Também um único binário, focado em simplicidade e conformidade.
*   **Flexível:** Permite mais customização na escolha de componentes (e.g., CNI - Container Network Interface, backend de armazenamento para o control plane).
*   **Seguro por Padrão:** Foco em configurações seguras desde o início.
*   **Instalação:** Usa uma ferramenta `k0sctl` para gerenciar a instalação e configuração do cluster.
*   **Backend:** Suporta SQLite, etcd, ou até mesmo um backend externo como kine (para usar com PostgreSQL, MySQL).

!!! tip "K3s ou K0s para Começar?"
    Ambos são excelentes opções. **K3s é frequentemente citado como sendo um pouco mais fácil e rápido para iniciar um cluster de aprendizado rapidamente** devido ao seu script de instalação simples. K0s oferece um pouco mais de flexibilidade se você tiver requisitos específicos. Para um primeiro contato, K3s pode ser uma boa escolha.

## 3. Conceitos Fundamentais do Kubernetes

Entender estes conceitos é essencial antes de mergulhar:

*   **Node (Nó):** Uma máquina (física ou virtual) que faz parte do cluster Kubernetes.
    *   **Control Plane Node (Master Node):** Gerencia o estado do cluster, armazena dados de configuração (no etcd ou SQLite), executa o API server, scheduler e controller manager.
    *   **Worker Node:** Executa as cargas de trabalho (suas aplicações em containers). Contém o `kubelet` (agente que comunica com o control plane) e um container runtime (e.g., containerd, que é o padrão para K3s/K0s).
*   **Pod:** A menor unidade de deploy no Kubernetes. Um Pod representa um ou mais containers que são sempre co-localizados, co-agendados e rodam em um contexto compartilhado (compartilham rede e, opcionalmente, volumes). Geralmente, um Pod contém um único container principal.
*   **Deployment:** Define o estado desejado para seus Pods (e ReplicaSets, que gerenciam o número de réplicas de Pods). Lida com atualizações (rolling updates, recreate) e rollbacks. Você declara "quero 3 réplicas do meu Pod da aplicação X" e o Deployment garante isso.
*   **Service (Serviço):** Define uma forma abstrata de expor um conjunto de Pods (geralmente selecionados por labels) como um serviço de rede. Fornece um endereço IP estável e um nome DNS para acessar os Pods, mesmo que os IPs dos Pods mudem ou eles sejam recriados.
    *   **Tipos de Service:** `ClusterIP` (apenas interno ao cluster), `NodePort` (expõe em uma porta em cada nó), `LoadBalancer` (requer integração com um provedor de nuvem ou um balanceador de carga como MetalLB/KlipperLB para IPs externos).
*   **Ingress:** Gerencia o acesso HTTP/S externo aos serviços dentro do cluster. Atua como um proxy reverso/API gateway. Precisa de um **Ingress Controller** (e.g., Traefik, Nginx Ingress, Caddy) para funcionar.
    *   Define regras para rotear tráfego baseado em host (e.g., `app1.meudominio.com`) e path para diferentes Services.
    *   Pode lidar com terminação SSL/TLS.
*   **Namespace:** Uma forma de dividir os recursos do cluster em múltiplos "clusters virtuais". Útil para organizar aplicações ou para ambientes multi-tenant.
*   **ConfigMap e Secret:**
    *   **ConfigMap:** Armazena dados de configuração não sensíveis (e.g., arquivos de configuração, variáveis de ambiente) que podem ser consumidos por Pods.
    *   **Secret:** Armazena dados sensíveis (e.g., senhas, tokens API, certificados TLS) de forma codificada (base64, não criptografada por padrão no etcd, mas K3s/K0s podem ter opções de criptografia em repouso).
*   **PersistentVolume (PV) e PersistentVolumeClaim (PVC):**
    *   Abstraem o armazenamento. Os Pods são efêmeros, mas os dados precisam persistir.
    *   **PV:** Um pedaço de armazenamento no cluster que foi provisionado por um administrador ou dinamicamente.
    *   **PVC:** Uma requisição de armazenamento feita por um usuário/aplicação. O K8s tenta encontrar um PV que satisfaça o PVC.
    *   **StorageClass:** Define tipos de armazenamento disponíveis e como provisioná-los dinamicamente (e.g., usando o ZFS Local PV provisioner, Longhorn, NFS).
*   **`kubectl`:** A ferramenta de linha de comando principal para interagir com um cluster Kubernetes (deploy de aplicações, inspeção de recursos, logs, etc.).

## 4. Como Instalar um Cluster K3s Simples em VMs Proxmox (Exemplo)

Este é um exemplo muito básico para um cluster de nó único ou um control plane + worker.

**Pré-requisitos:**
*   Pelo menos uma VM Linux no Proxmox (e.g., Ubuntu Server 22.04) com recursos decentes (pelo menos 2 vCPUs, 4GB RAM para um nó de controle K3s). Se for rodar cargas de trabalho nela, mais RAM.
*   A VM deve ter um IP estático ou um nome DNS resolúvel.
*   Se for um cluster multi-nó, as VMs precisam poder se comunicar entre si.

**Passo 1: Instalar K3s no Nó de Controle (Master)**

1.  Conecte-se à VM que será seu nó de controle via SSH.
2.  Execute o script de instalação oficial do K3s:
    ```bash
    curl -sfL https://get.k3s.io | sh -
    # Para instalar com opções, e.g., desabilitar Traefik Ingress embutido se você for usar outro:
    # curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable=traefik" sh -
    ```
3.  Verifique se o serviço K3s está rodando:
    ```bash
    sudo systemctl status k3s
    ```
4.  O arquivo de configuração `kubeconfig` para acessar o cluster é criado em `/etc/rancher/k3s/k3s.yaml`. Copie-o para sua máquina de controle (onde você tem `kubectl` instalado) para `~/.kube/config` ou use-o com `kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml ...`.
    ```bash
    # Na VM do K3s control plane:
    sudo cat /etc/rancher/k3s/k3s.yaml
    # Copie o conteúdo. Na sua máquina de controle:
    mkdir -p ~/.kube
    nano ~/.kube/config # Cole o conteúdo e ajuste o IP do servidor se necessário
    sudo chmod 600 ~/.kube/config
    ```
    Ou, para acesso rápido na própria VM do K3s:
    ```bash
    sudo k3s kubectl get nodes # k3s kubectl é um wrapper
    ```
5.  Instale `kubectl` na sua máquina de controle se ainda não tiver (siga a [documentação oficial do Kubernetes](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/)).
6.  Teste a conexão da sua máquina de controle: `kubectl get nodes`.

**Passo 2: (Opcional) Adicionar Nós Worker**

1.  Prepare outra VM Linux.
2.  No nó de controle, obtenha o token do cluster:
    ```bash
    # Na VM do K3s control plane
    sudo cat /var/lib/rancher/k3s/server/node-token
    ```
3.  Na VM que será o nó worker, execute o script de instalação do K3s, especificando o URL do servidor K3s (nó de controle) e o token:
    ```bash
    # Na VM worker
    curl -sfL https://get.k3s.io | K3S_URL=https://IP_OU_HOSTNAME_DO_CONTROL_PLANE:6443 K3S_TOKEN=SEU_TOKEN_AQUI sh -
    ```
4.  Na sua máquina de controle (ou no nó de controle), verifique se o novo nó aparece: `kubectl get nodes`.

**Passo 3: Configurar Armazenamento Persistente (Exemplo: ZFS Local PV)**

Para dados persistentes, você precisará de um StorageClass e um provisionador. Se suas VMs K3s rodam em Proxmox e têm acesso a storage ZFS (ou LVM), você pode usar provisionadores como:

*   **[ZFS Local PV](https://github.com/openebs/zfs-localpv):** Cria ZFS datasets ou ZVOLs dinamicamente para PVs.
*   **[Proxmox CSI Plugin](https://github.com/democratic-csi/democratic-csi):** (Mais complexo) Permite usar storage Proxmox.
*   **[Local Path Provisioner](https://github.com/rancher/local-path-provisioner):** (Vem com K3s por padrão) Usa diretórios no sistema de arquivos do nó para PVs. Simples, mas os dados ficam presos ao nó, não ideal para multi-nó com falha de nó.
*   **[NFS CSI Driver](https://github.com/kubernetes-csi/csi-driver-nfs):** Se você tem um servidor NFS (como o do nosso host Proxmox), pode usá-lo para PVs.

**Passo 4: Instalar um Ingress Controller (se desabilitou o Traefik do K3s)**

Se você desabilitou o Traefik Ingress embutido no K3s, precisará instalar um (e.g., Nginx Ingress, Caddy Ingress Controller, ou o Traefik Helm chart).

## 5. Deploy de uma Aplicação Simples no K3s (Exemplo com `kubectl`)

Suponha que você queira rodar um servidor Nginx simples.

1.  Crie um arquivo `nginx-deployment.yaml`:
    ```yaml
    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: nginx-deployment
    spec:
      replicas: 2 # Queremos 2 instâncias do Nginx
      selector:
        matchLabels:
          app: nginx
      template:
        metadata:
          labels:
            app: nginx
        spec:
          containers:
          - name: nginx
            image: nginx:latest # Imagem Docker do Nginx
            ports:
            - containerPort: 80 # Nginx escuta na porta 80
    ---
    apiVersion: v1
    kind: Service
    metadata:
      name: nginx-service
    spec:
      selector:
        app: nginx # Seleciona Pods com a label app=nginx
      ports:
        - protocol: TCP
          port: 80 # Porta que o Service expõe internamente no cluster
          targetPort: 80 # Porta nos Pods para onde o tráfego é direcionado
      # type: ClusterIP # Padrão, apenas acessível de dentro do cluster
      # type: NodePort # Expõe em uma porta em cada nó (e.g., 30080)
      # type: LoadBalancer # Para IP externo (precisa de MetalLB/KlipperLB em bare-metal)
    ```

2.  Aplique o manifesto ao cluster:
    ```bash
    kubectl apply -f nginx-deployment.yaml
    ```

3.  Verifique os Pods e o Service:
    ```bash
    kubectl get deployments
    kubectl get pods -o wide
    kubectl get services
    ```

4.  Para acessar (se `type: NodePort`): `http://IP_DE_UM_NO_K3S:PORTA_DO_NODEPORT`. Se usar `LoadBalancer` com MetalLB, use o IP externo alocado. Se usar `Ingress`, configure um Ingress resource.

## Considerações Adicionais

*   **Gerenciamento de Configuração:** Ferramentas como Helm (gerenciador de pacotes para Kubernetes) e Kustomize ajudam a gerenciar manifestos YAML complexos.
*   **Monitoramento e Logging no K8s:** Prometheus e Grafana são comumente usados (via kube-prometheus-stack). Para logs, Fluentd/Fluent Bit com Elasticsearch/Loki.
*   **Segurança no K8s:** RBAC (Role-Based Access Control), NetworkPolicies, PodSecurityPolicies/Standards.

Explorar Kubernetes, mesmo em um ambiente leve como K3s, é uma jornada de aprendizado significativa. Comece pequeno, entenda os conceitos básicos e expanda gradualmente. A [documentação do K3s](https://docs.k3s.io/) e [K0s](https://docs.k0sproject.io/) são seus melhores amigos.