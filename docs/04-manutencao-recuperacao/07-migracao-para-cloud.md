---

## 7. Migrando para a Nuvem em um Cenário de Desastre

Esta é a seção que você espera nunca precisar usar, mas que, se o pior acontecer, será a mais valiosa de toda a wiki. Um cenário de desastre implica a perda total e irrecuperável do seu hardware de servidor físico. Neste caso, nossos backups off-site no Google Cloud Storage (GCS) são nossa única linha de defesa para reconstruir nossa infraestrutura e restaurar nossos serviços.

Este guia é um procedimento passo a passo para executar uma migração de emergência para o Google Cloud Platform (GCP), transformando seus backups em uma infraestrutura funcional na nuvem. O objetivo é restaurar os serviços críticos o mais rápido possível, de forma automatizada e consistente.

!!! critical "Pré-requisitos para o Sucesso"
    Este plano de recuperação depende inteiramente da execução bem-sucedida e consistente das seguintes estratégias de backup, detalhadas em seções anteriores:
    1.  **Backups Off-site para GCS:** O script de sincronização com `rclone` deve estar funcionando corretamente, enviando os backups para o GCS.
    2.  **Infraestrutura como Código (IaC):** Seus playbooks Ansible, Docker Compose, configurações do Traefik e, crucialmente, os templates Terraform para este plano de recuperação devem estar versionados em um repositório Git acessível (ex: GitHub).
    3.  **Chaves e Senhas:** As senhas de criptografia do `rclone` e as chaves de API devem estar armazenadas de forma segura em um gerenciador de senhas que você possa acessar sem o seu home server.

### Fase 1: Preparação do Ambiente de Recuperação

Nesta fase, usaremos uma máquina local (seu laptop, por exemplo) para orquestrar a criação da nova infraestrutura na GCP.

1.  **Instale as Ferramentas Necessárias:**
    *   **Google Cloud SDK (`gcloud`):** Para autenticar e interagir com sua conta GCP.
    *   **Terraform:** Para provisionar a infraestrutura a partir de código.
    *   **`rclone`:** Para baixar e descriptografar seus backups do GCS.
    *   **Git:** Para clonar seu repositório de IaC.

2.  **Autenticação e Configuração:**
    *   Autentique-se no GCP: `gcloud auth login`
    *   Configure o projeto padrão: `gcloud config set project <seu-id-de-projeto-gcp>`
    *   Clone seu repositório `home-server`: `git clone <url-do-seu-repo-git>`
    *   Configure o `rclone` na sua máquina local com as mesmas configurações do host Proxmox, incluindo o remote criptografado e as senhas. Verifique se você consegue listar os arquivos no bucket: `rclone lsd gcs_backup_crypt:`

### Fase 2: Provisionamento da Infraestrutura com Terraform

Nesta fase, executaremos os scripts Terraform para construir a espinha dorsal da nossa nova casa na nuvem. Usaremos o Google Kubernetes Engine (GKE) como substituto para o Proxmox + Docker, pois ele oferece uma plataforma mais robusta e gerenciada para orquestração de containers.

Navegue até o diretório `terraform/gcp_disaster_recovery` no seu repositório clonado.

**Estrutura dos Arquivos Terraform (Exemplo):**

*   `main.tf`: Define o provedor GCP e a configuração principal.
*   `vpc.tf`: Cria a rede VPC, sub-redes e regras de firewall.
*   `gke.tf`: Provisiona um cluster GKE com um pool de nós.
*   `storage.tf`: Cria os Persistent Disks (substitutos dos datasets ZFS) que serão usados pelos nossos serviços.
*   `iam.tf`: Configura as contas de serviço e permissões necessárias para o GKE interagir com outros serviços GCP.
*   `variables.tf`: Define as variáveis (nome do projeto, região, etc.).

**Ações:**

1.  **Inicialize o Terraform:**
    ```bash
    terraform init
    ```

2.  **Planeje a Infraestrutura:**
    O Terraform irá mostrar todos os recursos que serão criados. Revise-os cuidadosamente.
    ```bash
    terraform plan
    ```

3.  **Aplique a Configuração:**
    Este comando irá de fato criar os recursos na sua conta GCP. Isso pode levar vários minutos.
    ```bash
    terraform apply --auto-approve
    ```

Ao final deste processo, você terá um cluster GKE funcional, discos persistentes vazios e a rede necessária para começar a restaurar os serviços.

### Fase 3: Restauração dos Dados

Agora, precisamos popular os Persistent Disks com os dados dos nossos backups.

1.  **Crie uma VM de "Trabalho" Temporária:**
    Provisione uma pequena VM no GCE (Google Compute Engine) dentro da mesma VPC que o cluster GKE. Esta VM servirá como uma ponte para mover os dados.

2.  **Anexe os Discos e Formate-os:**
    Anexe os Persistent Disks criados pelo Terraform a esta VM de trabalho. Formate-os com um sistema de arquivos (ex: `ext4`).

3.  **Baixe e Descriptografe os Backups:**
    Na VM de trabalho (que também precisa ter o `rclone` instalado e configurado), use o `rclone` para baixar os dados do GCS para os discos montados.

    ```bash
    # Exemplo para restaurar os volumes do Docker
    rclone sync gcs_backup_crypt:docker-volumes /mnt/persistent_disks/docker-volumes --progress
    ```

4.  **Desanexe os Discos:**
    Após a conclusão da sincronização, desanexe os Persistent Disks da VM de trabalho. Os dados agora estão prontos para serem usados pelo GKE.

### Fase 4: Deploy dos Serviços no GKE

Com a infraestrutura e os dados no lugar, é hora de subir os serviços.

1.  **Converta Docker Compose para Manifestos Kubernetes:**
    Para cada uma das suas stacks (produtividade, automação, etc.), você precisará de um conjunto de manifestos Kubernetes (`.yaml`) que definem os Deployments, Services, PersistentVolumeClaims e Ingresses.
    *   **PersistentVolumeClaim (PVC):** Declara a necessidade de armazenamento e se conecta a um dos Persistent Disks que restauramos.
    *   **Deployment:** Define o container a ser executado, similar ao `service` no Docker Compose. Ele montará o PVC para ter acesso aos dados.
    *   **Service:** Expõe o Deployment dentro do cluster.
    *   **Ingress:** Expõe o Service para o mundo exterior, gerenciado por um Ingress Controller (como o Traefik, que também pode ser instalado no GKE).

    Você pode usar uma ferramenta como o **Kompose** para uma conversão inicial, mas provavelmente precisará de ajustes manuais:
    ```bash
    kompose convert -f docker-compose.yml
    ```

2.  **Aplique os Manifestos ao Cluster GKE:**
    Autentique seu `kubectl` no novo cluster GKE:
    ```bash
    gcloud container clusters get-credentials <nome-do-cluster-gke> --region <sua-regiao>
    ```

    Em seguida, para cada serviço, aplique seus manifestos:
    ```bash
    kubectl apply -f nextcloud-deployment.yaml
    kubectl apply -f nextcloud-pvc.yaml
    kubectl apply -f nextcloud-service.yaml
    kubectl apply -f nextcloud-ingress.yaml
    ```

3.  **Instale o Traefik como Ingress Controller:**
    Siga a documentação oficial do Traefik para instalá-lo no GKE usando Helm. Configure-o para usar o Let's Encrypt para certificados SSL, assim como no ambiente local.

### Fase 5: Finalização e Validação

1.  **Atualize o DNS no Cloudflare:**
    O GKE provisionará um Load Balancer externo com um endereço IP público para o Traefik. Pegue este IP e atualize os registros DNS no Cloudflare para que seus subdomínios (ex: `nextcloud.seudominio.com`) apontem para este novo IP.

2.  **Teste Todos os Serviços:**
    Acesse cada um dos seus serviços e verifique se eles estão funcionando como esperado e se todos os dados foram restaurados corretamente.

Este processo transforma um evento catastrófico em um procedimento de recuperação gerenciável e previsível. Embora complexo, ele é a prova final da resiliência da sua arquitetura, garantindo que sua infraestrutura digital possa sobreviver até mesmo à perda completa do seu hardware físico.
