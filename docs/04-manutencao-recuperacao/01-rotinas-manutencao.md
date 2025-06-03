# Rotinas de Manutenção Essenciais

Manutenção preventiva é a chave para um servidor doméstico estável, seguro e com bom desempenho a longo prazo. Estabelecer rotinas regulares para as tarefas abaixo ajudará a evitar problemas e a manter seu sistema saudável.

## 1. Atualizações de Sistema

Manter o software atualizado é crucial para segurança (patches de vulnerabilidade) e para obter novas features e correções de bugs.

### Host Proxmox VE

*   **Frequência:** Mensalmente (ou conforme alertas de segurança críticos).
*   **Comando (no shell do host Proxmox, como `root`):**
    ```bash
    apt update && apt full-upgrade -y
    ```
*   **Pontos de Atenção:**
    *   **Leia as Notas de Release:** Antes de grandes atualizações do Proxmox, verifique o fórum do Proxmox ou as notas de release para quaisquer problemas conhecidos ou mudanças significativas.
    *   **Backups:** Certifique-se de que seus backups de VMs estão em dia antes de uma atualização do host.
    *   **Reboot:** Atualizações de kernel ou do próprio Proxmox geralmente requerem um reboot do host. Planeje um momento de baixa utilização.
    *   **Repositórios:** As atualizações virão do repositório `pve-no-subscription` (configurado pelo Ansible).

### Máquinas Virtuais (VMs Ubuntu)

*   **`unattended-upgrades`:** Este pacote, instalado e configurado pelo role Ansible `common`, deve cuidar da aplicação automática de atualizações de segurança.
*   **Verificação de Logs (na VM):**
    *   Verifique os logs de `unattended-upgrades` para garantir que estão funcionando:
        `/var/log/unattended-upgrades/unattended-upgrades-dpkg.log`
*   **Atualizações Manuais (Opcional, para outros pacotes):**
    *   Se você quiser atualizar todos os pacotes (não apenas os de segurança) ou se `unattended-upgrades` não estiver configurado para tudo:
        ```bash
        # Dentro da VM
        sudo apt update && sudo apt full-upgrade -y
        sudo apt autoremove -y # Remove pacotes órfãos
        ```
    *   Um reboot da VM pode ser necessário após atualizações de kernel.

## 2. Atualizações de Imagens Docker (Containers)

Manter suas imagens Docker atualizadas é tão importante quanto atualizar o SO.

### Usando Watchtower (Recomendado para Automação)

Watchtower é um container que monitora seus outros containers em execução e os atualiza automaticamente para a versão mais recente da imagem (respeitando a tag que você usou, e.g., `latest` ou uma tag de versão específica como `v2.1.0`).

*   **Deploy do Watchtower:**
    *   Foi incluído um `docker-compose.yml` para Watchtower em `infra-servidor-domestico/docker/stacks/watchtower/docker-compose.yml`.
    *   Implante esta stack na `core-services-vm` via Portainer.
    ```yaml
    # docker/stacks/watchtower/docker-compose.yml
    version: "3.9"
    services:
      watchtower:
        image: containrrr/watchtower:1.7.1 # Verifique a tag estável mais recente
        container_name: watchtower
        restart: unless-stopped
        volumes:
          - /var/run/docker.sock:/var/run/docker.sock # Para Watchtower interagir com o Docker daemon
          # - /etc/localtime:/etc/localtime:ro # Para logs com fuso horário correto
        environment:
          - WATCHTOWER_CLEANUP=true # Remove imagens antigas após a atualização
          - WATCHTOWER_SCHEDULE="0 0 4 * * *" # Agenda para rodar todo dia às 4 AM (formato cron)
          # Apenas atualiza containers que tenham a label "com.centurylinklabs.watchtower.enable=true"
          - WATCHTOWER_LABEL_ENABLE=true
          # Opcional: Configurar notificações (e.g., Shoutrrr para Discord, Telegram, Email)
          # - WATCHTOWER_NOTIFICATIONS=shoutrrr
          # - WATCHTOWER_NOTIFICATION_URL="discord://TOKEN@ID/ OutrosFormatos..."
          # - WATCHTOWER_NOTIFICATION_TEMPLATE="{{ . serviço }} atualizado para {{ .ImagemNova }}" # Exemplo
        # Labels para que o próprio Watchtower se auto-atualize (se WATCHTOWER_LABEL_ENABLE=true)
        # labels:
        #   - "com.centurylinklabs.watchtower.enable=true"
    ```
*   **Habilitando Atualizações para Containers Específicos:**
    *   Para cada serviço no seu `docker-compose.yml` que você quer que o Watchtower atualize, adicione a label:
        ```yaml
        services:
          meu_servico:
            # ... outras configs ...
            labels:
              - "com.centurylinklabs.watchtower.enable=true"
              # ... outras labels (e.g., Traefik) ...
        ```
    *   Atualize a stack no Portainer para aplicar a nova label.
*   **Logs do Watchtower:** Verifique os logs do container `watchtower` para ver quais containers foram atualizados.

### Atualização Manual via Portainer ou Linha de Comando

Se preferir mais controle ou se usar tags de versão específicas que não quer que mudem para `latest`:

1.  **Verifique Novas Versões:** Monitore os sites dos projetos ou Docker Hub para novas tags de versão das imagens que você usa.
2.  **No Portainer:**
    *   Vá para a Stack -> Editor.
    *   Altere a tag da imagem no `docker-compose.yml` (e.g., de `app:v1.0` para `app:v1.1`).
    *   Clique em "Update the stack". Marque a opção "Re-pull image and redeploy".
3.  **Via Linha de Comando (na VM):**
    ```bash
    # Para uma stack específica
    cd /caminho/para/docker/stacks/minha_stack/
    # Edite o docker-compose.yml com a nova tag da imagem
    docker compose pull # Puxa as imagens mais recentes definidas no compose
    docker compose up -d --remove-orphans # Recria os containers com as novas imagens
    docker image prune -f # Remove imagens antigas não utilizadas
    ```

## 3. Revisão de Logs

Logs são seus olhos para o que está acontecendo no sistema.

*   **Onde Encontrar:**
    *   **Containers Docker:** Via Portainer (selecione container -> Logs) ou `docker logs <container>`.
    *   **Traefik:** Logs do container `traefik` (especialmente `traefik.log` e `access.log` se mapeados para volumes).
    *   **Authelia:** Logs do container `authelia`.
    *   **Serviços de Aplicação:** Muitas aplicações têm seus próprios arquivos de log dentro dos seus volumes de configuração.
    *   **VMs (System Logs):** `journalctl -xe`, `/var/log/syslog`, `/var/log/auth.log`.
    *   **Host Proxmox:** UI web do Proxmox (Syslog, Tasks), ou no shell (`journalctl`, `/var/log/...`).
    *   **Loki/Grafana:** Se a stack de monitoramento estiver configurada, use Grafana para consultar logs centralizados de Promtail.
*   **O Que Procurar:**
    *   Mensagens de `ERROR`, `WARN`, `FATAL`, `CRITICAL`.
    *   Tentativas de login falhas (Authelia, SSH, UIs de apps).
    *   Padrões incomuns de tráfego ou atividade.
    *   Erros de disco ou sistema de arquivos (ZFS, `dmesg`).
*   **Frequência:** Diariamente para sistemas críticos, semanalmente para uma visão geral.

## 4. Monitoramento da Saúde do Sistema

Use sua [Stack de Monitoramento](../01-manual-implementacao/10-stack-monitoramento.md) (Prometheus, Grafana, Glances).

*   **Dashboards Grafana:** Crie ou importe dashboards para visualizar:
    *   Uso de CPU, RAM, Disco (Host Proxmox e VMs).
    *   Tráfego de Rede.
    *   Status do Pool ZFS (saúde, capacidade, IOPS).
    *   Métricas do Node Exporter, Glances.
    *   Métricas de containers (se usar cAdvisor).
    *   Métricas do Cloudflare Tunnel.
*   **Alertas:** Configure alertas no Prometheus (via Alertmanager, não coberto em detalhe neste guia) ou no Grafana para ser notificado de condições críticas (e.g., disco cheio, CPU alta por muito tempo, serviço offline).
*   **Glances WebUI:** Para uma visão rápida em tempo real (`https://glances.{{ base_domain }}`).
*   **Frequência:** Verifique dashboards diariamente ou configure alertas para problemas urgentes.

## 5. Verificação da Saúde do ZFS (Host Proxmox)

*   **Status Regular:**
    ```bash
    sudo zpool status -v data
    ```
    Verifique se o pool está `ONLINE` e se não há erros de leitura/escrita/checksum.
*   **Scrub Agendado:** ZFS scrub verifica a integridade de todos os dados no pool. É recomendado rodá-lo mensalmente.
    ```bash
    # Iniciar um scrub manualmente
    sudo zpool scrub data
    # Verificar o status do scrub
    sudo zpool status data
    ```
    Você pode agendar isso com `cron`. Exemplo de entrada cron (e.g., `sudo crontab -e`):
    `0 2 1 * * /sbin/zpool scrub data` (Roda às 2 AM no primeiro dia de cada mês).
*   **Alertas por Email (Script `check_zfs.sh`):**
    O script `check_zfs.sh` (mencionado na Seção 11.2 do documento original) pode ser agendado para verificar o status do pool e enviar um email se houver problemas.
    Certifique-se que o host Proxmox pode enviar emails (e.g., `mailutils` instalado e configurado com `ssmtp` ou `postfix`).
    **Conteúdo do Script (exemplo):**
    ```bash
    #!/bin/bash
    # /usr/local/sbin/check_zfs.sh
    POOL_NAME="data"
    ADMIN_EMAIL="{{ letsencrypt_email }}" # Substitua pelo seu email

    STATUS=$(/sbin/zpool status -vx "$POOL_NAME" 2>&1) # Captura stdout e stderr
    HEALTH=$(echo "$STATUS" | grep -E "state: ONLINE" | wc -l) # Conta linhas com "state: ONLINE"

    if [ "$HEALTH" -ne 1 ]; then # Se não for exatamente 1 (ou seja, não está ONLINE ou há múltiplas linhas)
      # Tenta pegar a linha de status real
      POOL_STATUS_LINE=$(echo "$STATUS" | grep -E "^\s*pool: $POOL_NAME" -A 1 | tail -n 1 | awk '{print $2}')
      echo -e "ALERTA ZFS: Pool '$POOL_NAME' no host $(hostname) está em estado: $POOL_STATUS_LINE\n\n$STATUS" | mail -s "ALERTA ZFS: Problema no Pool $POOL_NAME em $(hostname)" "$ADMIN_EMAIL"
    else
      # Opcional: log de status OK se desejar
      # echo "ZFS Pool '$POOL_NAME' está ONLINE em $(date)" >> /var/log/zfs_health.log
      : # No operation, ZFS is fine
    fi
    ```
    Agende com `cron`: `0 */6 * * * /usr/local/sbin/check_zfs.sh` (a cada 6 horas).

## 6. Verificação de Backups

!!! critical "A Rotina Mais Importante!"
    Backups são inúteis se não funcionarem. **TESTE SEUS BACKUPS REGULARMENTE!**

*   **Verificar Conclusão:**
    *   **Proxmox VM Backups:** Verifique a aba "Tasks" na UI do Proxmox para o status dos jobs de backup agendados.
    *   **Dumps de Banco de Dados:** Verifique os logs dos seus scripts de backup de DB. Certifique-se que os arquivos de dump estão sendo criados e não estão vazios.
    *   **Backups de Volumes (Borg, rsync):** Verifique os logs da ferramenta de backup.
*   **Testes de Restauração:**
    *   **Frequência:** Pelo menos trimestralmente, ou após mudanças significativas na sua estratégia de backup.
    *   **O que testar:**
        *   Restaure uma VM de teste a partir de um backup do Proxmox.
        *   Restaure um banco de dados de um dump para uma instância de teste.
        *   Restaure alguns arquivos aleatórios de um backup de volume (Borg/rsync).
        *   Tente restaurar um arquivo de um snapshot ZFS.
    *   Documente seu processo de restauração para que você saiba o que fazer em uma emergência real.

Estabelecer e seguir estas rotinas de manutenção ajudará a garantir que seu servidor doméstico permaneça uma plataforma confiável e segura para seus serviços.