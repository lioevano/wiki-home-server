---
description: "Rotinas periódicas de manutenção (atualizações, ZFS scrub, logs, certificados) e scripts de validação do server."
---

# Rotinas de Manutenção Essenciais

A manutenção preventiva e regular é a chave para um servidor doméstico estável, seguro e com bom desempenho a longo prazo. Estabelecer rotinas para as tarefas descritas abaixo ajudará a evitar problemas inesperados, a manter seu sistema protegido contra vulnerabilidades e a garantir que seus dados estejam seguros.

Pense nisso como as "revisões periódicas" do seu carro; elas são essenciais para a longevidade e confiabilidade.

## 1. Atualizações de Software e Sistema Operacional

Manter todo o software atualizado é uma das tarefas de manutenção mais críticas, principalmente por questões de segurança (aplicação de patches para vulnerabilidades conhecidas) e também para obter novas funcionalidades e correções de bugs.

### Host Proxmox VE

*   **Frequência Recomendada:** **Mensalmente**, ou imediatamente se houver alertas de segurança críticos para o Debian ou componentes Proxmox.
*   **Procedimento (no shell do host Proxmox, como `root` ou com `sudo`):**
    1.  **Leia as Notas de Release (Importante para atualizações maiores):** Antes de grandes atualizações de versão do Proxmox VE (e.g., de 7.x para 8.x), é crucial verificar o [fórum do Proxmox](https://forum.proxmox.com/) e as [notas de release oficiais](https://pve.proxmox.com/wiki/Roadmap) para quaisquer problemas conhecidos, breaking changes, ou procedimentos de upgrade específicos.
    2.  **Faça Backup das VMs:** Certifique-se de que seus backups de VMs ([conforme Seção 2.3](#2-verificação-de-backups) e [Estratégia de Backup](02-backup-restore-estrategia.md)) estão atualizados e funcionais antes de uma atualização do host.
    3.  **Execute a Atualização:**
        ```bash
        # Sincroniza a lista de pacotes com os repositórios
        apt update

        # Simula a atualização para ver o que será alterado (altamente recomendado)
        apt full-upgrade --simulate
        # ou
        # apt dist-upgrade --simulate

        # Realiza a atualização completa do sistema.
        # 'full-upgrade' (ou 'dist-upgrade') lida melhor com dependências e remoção
        # de pacotes obsoletos do que um simples 'apt upgrade'.
        apt full-upgrade -y
        ```
    4.  **Leia Atentamente a Saída:** Durante o `apt full-upgrade`, preste atenção a quaisquer mensagens sobre pacotes que serão removidos, mudanças de configuração importantes, ou prompts que exijam sua confirmação.
    5.  **Reboot do Host Proxmox (Geralmente Necessário):** Se a atualização incluir um novo kernel Linux, atualizações do `pve-kernel`, QEMU, ou outras bibliotecas de sistema críticas, um **reboot do host Proxmox será necessário** para que as mudanças tenham efeito completo. O sistema geralmente informa se um reboot é recomendado. Planeje este reboot para um momento de baixa utilização dos seus serviços.
    6.  **Verificações Pós-Atualização e Pós-Reboot:**
        *   Confirme se a interface web do Proxmox está acessível e funcionando.
        *   Verifique se todas as suas VMs iniciam corretamente.
        *   Confirme se os serviços do host (ZFS, NFS, rede) estão operacionais.
        *   Examine os logs do sistema (`journalctl -xe`, `dmesg`) no host Proxmox por quaisquer novos erros ou avisos.
*   **Repositórios:** Lembre-se que as atualizações do Proxmox virão do repositório `pve-no-subscription`, que foi configurado pelo Ansible.

### Máquinas Virtuais (VMs Ubuntu)

*   **`unattended-upgrades` (Para Segurança):**
    *   Este pacote, instalado e configurado pelo role Ansible `common` ([Seção 4.1 do Manual de Implementação](../01-manual-implementacao/04-configuracao-base-vms-ubuntu.md#41-role-ansible-common-ansiblerolescommon)), deve cuidar da aplicação automática de atualizações de segurança para os pacotes do sistema operacional nas suas VMs Ubuntu.
*   **Verificação dos Logs do `unattended-upgrades` (Periodicamente):**
    *   Conecte-se a cada VM via SSH e verifique os logs para garantir que as atualizações automáticas estão ocorrendo sem erros:
        `/var/log/unattended-upgrades/unattended-upgrades-dpkg.log`
*   **Atualizações Manuais de Todos os Pacotes (Opcional, com mais controle):**
    *   Se você preferir controlar quando todos os pacotes são atualizados (não apenas os de segurança), ou se `unattended-upgrades` não estiver configurado para cobrir todos os repositórios (e.g., repositórios de terceiros que você possa ter adicionado):
        ```bash
        # Dentro de cada VM
        sudo apt update
        sudo apt list --upgradable # Veja o que seria atualizado
        sudo apt full-upgrade -y
        sudo apt autoremove -y     # Remove pacotes órfãos e dependências não mais necessárias
        ```
    *   **Reboot da VM:** Um reboot da VM pode ser necessário após atualizações de kernel dentro da VM. O sistema geralmente avisa se um reboot é recomendado (e.g., o arquivo `/var/run/reboot-required` existirá).

## 2. Atualizações de Imagens Docker e Aplicações Containerizadas

Manter suas imagens Docker e as aplicações rodando dentro dos containers atualizadas é tão crucial quanto atualizar os sistemas operacionais.

Consulte a seção [Atualização Segura de Componentes Críticos da Infraestrutura](../03-guias-sustentacao/10-atualizacao-segura-componentes-criticos.md) para detalhes sobre como atualizar Traefik, Authelia e outras aplicações Docker individuais, incluindo o uso de **Watchtower** para automação ou o processo manual via Portainer.

**Princípios Chave para Atualizar Containers:**
1.  **Leia as Notas de Release da Aplicação/Imagem:** Verifique por breaking changes ou passos de migração.
2.  **Backup dos Volumes de Dados:** Antes de atualizar um container crítico, faça um snapshot ZFS do seu volume de dados.
3.  **Use Tags de Versão Específicas:** Em seus `docker-compose.yml`, prefira tags de versão específicas (e.g., `app:v1.2.3`) em vez de `app:latest` para atualizações mais controladas. Atualize a tag manualmente quando quiser mudar para uma nova versão.
4.  **Teste Após a Atualização:** Verifique os logs do container e a funcionalidade da aplicação.

## 3. Revisão Regular de Logs

Logs são seus olhos e ouvidos para o que está acontecendo no seu sistema. Uma revisão periódica pode ajudar a detectar problemas antes que se tornem críticos.

*   **Onde Encontrar Logs Detalhados:** Consulte a seção "Ferramentas Essenciais de Diagnóstico" no [Guia de Troubleshooting Comum](../03-guias-sustentacao/03-troubleshooting-comum.md#ferramentas-essenciais-de-diagnóstico).
*   **O Que Procurar:**
    *   Mensagens de `ERROR`, `WARN` (Aviso), `FATAL`, `CRITICAL`.
    *   Tentativas de login falhas (nos logs do Authelia, SSH via `/var/log/auth.log` nas VMs/host, logs de UIs de aplicações).
    *   Padrões incomuns de tráfego de rede ou atividade de disco (via sua stack de monitoramento).
    *   Erros de disco, sistema de arquivos ou ZFS (`dmesg`, `zpool status`, logs do sistema).
    *   Certificados SSL prestes a expirar (embora Traefik com Let's Encrypt deva renovar automaticamente).
*   **Frequência Sugerida:**
    *   **Diariamente (Rápida Verificação):** Logs de aplicações críticas, logs do Authelia, dashboard de monitoramento.
    *   **Semanalmente (Mais Detalhada):** Logs do sistema, logs de backups, status do ZFS scrub.

## 4. Monitoramento Contínuo da Saúde do Sistema

Utilize ativamente a Stack de Monitoramento (Prometheus, Grafana, Loki) — veja [Deploy de Apps](../01-manual-implementacao/07-deploy-apps.md).

*   **Dashboards Grafana:** Configure e consulte regularmente dashboards para visualizar:
    *   Uso de CPU, RAM, Espaço em Disco, Swap (para o Host Proxmox e cada VM).
    *   Tráfego de Rede (por interface, por VM).
    *   Status e Performance do Pool ZFS (saúde, capacidade, IOPS, latência, ARC stats).
    *   Métricas do Node Exporter de cada sistema.
    *   Métricas de containers Docker (se você adicionar um exportador como o cAdvisor).
    *   Métricas do Cloudflare Tunnel.
*   **Alertas (Prometheus Alertmanager / Grafana Alerting):**
    *   Configure alertas para condições críticas que exigem sua atenção imediata:
        *   Uso de disco acima de um limite (e.g., 85-90%).
        *   Uso de CPU ou RAM consistentemente muito alto.
        *   Serviço ou VM offline.
        *   Pool ZFS degradado ou com erros.
        *   Falha em backups.
*   **Frequência:** Verifique dashboards importantes diariamente ou configure alertas para ser notificado proativamente sobre problemas.

## 5. Verificação da Saúde do Pool ZFS (Host Proxmox)

Seu pool ZFS `/data` é o coração do armazenamento de dados.

*   **Verificação de Status Regular:**
    ```bash
    # No host Proxmox
    sudo zpool status -v data
    ```
    Verifique se o `state` do pool está `ONLINE` e se não há erros de leitura (`READ`), escrita (`WRITE`), ou checksum (`CKSUM`) listados para os discos.
*   **Scrub Agendado:**
    Um "scrub" ZFS lê todos os dados no pool e verifica sua integridade contra os checksums, corrigindo erros em pools redundantes (como nosso espelho) se possível.
    *   **Recomendação:** Agende um scrub para rodar **mensalmente**.
    *   **Comando para Iniciar Manualmente:** `sudo zpool scrub data`
    *   **Verificar Status do Scrub:** `sudo zpool status data` (mostrará o progresso).
    *   **Agendar com `cron` (e.g., `sudo crontab -e` no host Proxmox):**
        `0 2 1 * * /sbin/zpool scrub data # Roda às 2 AM no primeiro dia de cada mês`
*   **Alertas de Saúde do ZFS por Email:**
    *   O script `check_zfs.sh` (mencionado na Seção 11.2 do seu documento original, e que pode ser adaptado da nossa [seção de backups](02-backup-restore-estrategia.md#script-check_zfssh-no-proxmox-host)) pode ser agendado para verificar o status do pool e enviar um email se detectar problemas.
    *   Certifique-se de que o host Proxmox está configurado para enviar emails (e.g., `mailutils` instalado e configurado com `ssmtp` ou `postfix` para retransmitir através de um servidor SMTP).
    *   Agende este script para rodar com frequência (e.g., a cada poucas horas ou diariamente).

## 6. Verificação e Teste de Backups

!!! critical "A Rotina de Manutenção MAIS IMPORTANTE!"
    Seus backups são sua última linha de defesa contra a perda de dados. Um backup que não foi testado é um backup em que você não pode confiar.

*   **Verificar a Conclusão dos Backups:**
    *   **Backups de VMs Proxmox:** Na UI web do Proxmox, verifique a aba "Tasks" (no nível do Datacenter ou do Nó) para o status dos jobs de backup agendados. Verifique se eles estão sendo concluídos com sucesso e sem erros.
    *   **Dumps de Banco de Dados:** Se você tem scripts para fazer dump de bancos de dados (PostgreSQL para Authelia, Nextcloud, Grafana), verifique os logs desses scripts. Confirme se os arquivos de dump estão sendo criados no local esperado, se têm um tamanho razoável (não estão vazios) e se não há erros nos logs.
    *   **Backups de Volumes/Datasets ZFS (Borg, rsync, etc.):** Verifique os logs da sua ferramenta de backup (e.g., `borg list /caminho/repo` para ver os arquivos).
*   **Testes de Restauração Periódicos:**
    *   **Frequência:** Pelo menos **trimestralmente**, ou mais frequentemente se você fizer mudanças significativas na sua estratégia de backup ou nos dados críticos.
    *   **O Que Testar (Simule Cenários Reais):**
        1.  **Restaurar uma VM de Teste:** Restaure uma VM menos crítica (ou uma VM de teste que você possa deletar) a partir de um backup do Proxmox para um novo VM ID. Verifique se ela inicia e se os dados estão consistentes.
        2.  **Restaurar um Banco de Dados:** Restaure um dump de banco de dados para uma instância de teste do banco de dados (pode ser um container Docker temporário). Verifique se você consegue se conectar e consultar os dados.
        3.  **Restaurar Arquivos Individuais de Volumes:** Use sua ferramenta de backup de volumes (Borg, rsync) para restaurar alguns arquivos ou diretórios aleatórios para um local temporário. Verifique sua integridade e conteúdo.
        4.  **Testar Recuperação de Snapshots ZFS:** Tente acessar e copiar um arquivo de um snapshot ZFS recente para garantir que o mecanismo `.zfs/snapshot/` está funcionando como esperado.
    *   **Documente Seu Processo de Restauração:** Enquanto você testa, documente os passos exatos que você tomou. Isso será inestimável em uma emergência real quando você estiver sob pressão.

Estabelecer e seguir estas rotinas de manutenção, mesmo que pareçam trabalhosas inicialmente, é um investimento fundamental na estabilidade, segurança e longevidade do seu servidor doméstico. Automatize o que puder (atualizações, backups, verificações de saúde) e reserve tempo para as verificações manuais e testes.

## Scripts de Validação

Ferramentas de diagnóstico versionadas em `server/scripts/validation/`:

| Script | Para que serve |
|---|---|
| `scripts/validation/validate_infrastructure.sh` | Valida a infraestrutura inteira após um deploy (hosts, serviços, stacks). |
| `scripts/validation/check_nfs_permissions.sh` | Diagnostica e corrige problemas comuns de permissão nos compartilhamentos NFS. |
| `scripts/validation/check_yaml_integrity.py` | Verifica a sintaxe de todos os YAML de `ansible/` e `docker/`. |

A coerência entre esta wiki e o `server/` é verificada por `python tools/dev.py check` (veja o `CLAUDE.md` na raiz do repositório).
