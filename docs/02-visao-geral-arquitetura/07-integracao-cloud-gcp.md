# Seção 7: Integração com a Nuvem e Arquitetura Híbrida (GCP)

Um dos objetivos fundamentais desta arquitetura de home server é a **longevidade e resiliência**. Embora a auto-hospedagem ofereça controle, privacidade e economia, depender exclusivamente de hardware físico em um único local apresenta riscos: falha de hardware, desastres locais (incêndio, inundação, roubo) ou a simples necessidade de abandonar o servidor físico por um período.

Para mitigar esses riscos, adotamos uma **arquitetura de nuvem híbrida**, utilizando o Google Cloud Platform (GCP) como nosso parceiro estratégico para backup, redundância e recuperação de desastres. Esta seção detalha a filosofia e a implementação dessa integração, garantindo que sua infraestrutura digital possa sobreviver e operar mesmo sem o servidor físico.

!!! tip "Por que GCP?"
    A escolha do Google Cloud Platform se baseia em uma combinação de fatores: um generoso *free tier* (nível gratuito), ferramentas de linha de comando poderosas (`gsutil`, `gcloud`), serviços robustos como Cloud Storage e Google Kubernetes Engine (GKE), e uma excelente infraestrutura de rede global. Os mesmos princípios, no entanto, podem ser aplicados a outros provedores de nuvem como AWS ou Azure.

## A Estratégia de Redundância: O Que e Como Sincronizar

Nossa estratégia não é replicar toda a infraestrutura 1:1 na nuvem, o que seria proibitivamente caro, especialmente para serviços de mídia. Em vez disso, focamos em uma **sincronização seletiva e inteligente** dos componentes mais críticos, permitindo uma reconstrução rápida e eficiente em um cenário de desastre.

O diagrama abaixo ilustra a arquitetura híbrida:

```mermaid
graph TD
    subgraph Home Server (Local)
        A[Proxmox Host]
        subgraph VMs
            B[core-services-vm]
            C[ai-desktop-vm]
            D[media-vm] --- E{VM de Mídia \n(NÃO SINCRONIZADA)}
        end
        F[Pool ZFS /data] -- NFS --> B
        F -- NFS --> C
        F -- NFS --> D
        G[Backups Locais \n(Snapshots ZFS, Backups Proxmox)]
        F --> G
    end

    subgraph Internet
        H[Cloudflare]
        H -- Cloudflare Tunnel --> I{Traefik @ core-services-vm}
    end

    subgraph Google Cloud Platform (GCP)
        J[Cloud Storage Bucket \n(Backup Off-site)]
        K[Google Kubernetes Engine (GKE) \n/ Cloud Run \n(Recuperação de Desastre)]
        L[Container Registry (GCR)]
    end

    B -- rclone/gsutil \n(Backup Diário) --> J
    C -- rclone/gsutil \n(Backup Diário) --> J
    G -- rclone/gsutil \n(Backup Semanal) --> J

    M[Usuário Final] --> H

    style E fill:#f9f,stroke:#333,stroke-width:2px
```

### Componentes Sincronizados para a Nuvem

1.  **Volumes de Dados Críticos (ZFS Datasets):**
    *   **O quê:** Os datasets ZFS que contêm as configurações e dados essenciais de seus serviços. Isso inclui:
        *   `docker-volumes`: Configurações de todos os seus containers (Nextcloud, Home Assistant, n8n, etc.).
        *   `rag-sources`: Seus documentos e bases de conhecimento para a stack de IA.
        *   `databases`: Backups de bancos de dados que não estão dentro dos volumes Docker.
    *   **Como:** Sincronização diária e incremental usando `rclone` ou `gsutil` para um bucket do Google Cloud Storage (GCS). O `rclone` é particularmente eficaz, pois pode criptografar os dados do lado do cliente antes de enviá-los para a nuvem, adicionando uma camada extra de privacidade.
    *   **Por quê:** Estes são os "cérebros" da sua operação. Com eles, você pode recriar todos os seus serviços sem perder dados de usuário, configurações ou workflows.

2.  **Backups de VMs e Configuração do Host (Proxmox):**
    *   **O quê:** Os arquivos de backup completos das VMs (`.vma.zst`) gerados pelo Proxmox e os arquivos de configuração do host Proxmox (`/etc/pve`, etc.).
    *   **Como:** Sincronização semanal para o Google Cloud Storage. Como esses arquivos são maiores e menos voláteis, uma frequência menor é aceitável.
    *   **Por quê:** Embora a meta seja recriar os serviços em uma plataforma nativa da nuvem (como Kubernetes), ter o backup completo da VM original serve como uma apólice de seguro definitiva, permitindo uma restauração completa em um novo hardware Proxmox, se necessário.

3.  **Arquivos de Infraestrutura como Código (IaC):**
    *   **O quê:** Todo o seu repositório `home-server`, contendo seus playbooks Ansible, arquivos Docker Compose, configurações do Traefik, etc.
    *   **Como:** `git push` para um repositório Git privado (GitHub, GitLab, ou até mesmo o Gitea auto-hospedado, cujo volume de dados já está sendo sincronizado).
    *   **Por quê:** Este é o manual de instruções para reconstruir tudo. Sem ele, a recuperação seria um processo manual e propenso a erros.

### Componentes **NÃO** Sincronizados (Intencionalmente)

1.  **VM de Mídia e Biblioteca de Mídia:**
    *   **Por quê:** O custo de armazenar terabytes de mídia em um provedor de nuvem é extremamente alto e, na maioria dos casos, inviável para um projeto doméstico. Além disso, a mídia geralmente pode ser readquirida ou redigitalizada, tornando-a um dado "recuperável", embora com esforço.
    *   **Estratégia Alternativa:** A redundância para a biblioteca de mídia deve ser focada localmente (RAIDZ no ZFS) e, se o orçamento permitir, em um backup *cold storage* (HDs externos guardados offline).

## O Plano de Recuperação de Desastres na GCP

No evento de uma falha total e permanente do seu servidor físico, a cópia off-site no GCP é sua salvação. O plano não é simplesmente rodar uma VM gigante no Google Compute Engine (GCE), mas sim adaptar os serviços para uma arquitetura nativa da nuvem, mais eficiente e escalável.

1.  **Infraestrutura Base com Terraform:**
    *   Usamos o Terraform, uma ferramenta de IaC, para provisionar a infraestrutura necessária na GCP. Um conjunto de scripts Terraform pré-configurados pode criar:
        *   Um cluster do Google Kubernetes Engine (GKE) ou configurar o Cloud Run.
        *   As redes VPC necessárias.
        *   Discos Persistentes (Persistent Disks) para armazenar os dados restaurados.
        *   As permissões e contas de serviço necessárias.

2.  **Restauração dos Dados:**
    *   Os dados críticos são restaurados do bucket do Cloud Storage para os Persistent Disks.

3.  **Deploy dos Serviços no GKE / Cloud Run:**
    *   Em vez de VMs, os serviços são reimplantados como containers no GKE ou no Cloud Run. Isso oferece melhor resiliência e gerenciamento.
    *   Os arquivos Docker Compose podem ser convertidos para manifestos do Kubernetes (usando ferramentas como o `kompose`) ou reimplementados como serviços do Cloud Run.
    *   O Traefik pode ser implantado como um Ingress Controller no GKE para gerenciar o tráfego de entrada.

4.  **Apontamento do DNS:**
    *   A única mudança manual final é atualizar o Cloudflare para apontar para o novo endereço IP do Load Balancer do GKE, em vez do Cloudflare Tunnel local.

Este processo, embora complexo, pode ser largamente automatizado. O resultado é a capacidade de trazer toda a sua infraestrutura de volta online, na nuvem, em questão de horas em vez de dias ou semanas, com perda mínima de dados. A documentação detalhada para este procedimento de migração e recuperação pode ser encontrada na seção [Migrando para a Nuvem em um Cenário de Desastre](/?path=docs/04-manutencao-recuperacao/07-migracao-para-cloud.md).
