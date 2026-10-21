---
description: "Como atualizar com segurança Proxmox VE, Docker, Traefik, Authelia e outros componentes críticos."
---

# Atualização Segura de Componentes Críticos da Infraestrutura

Manter sua infraestrutura de servidor doméstico atualizada é vital para a segurança (recebendo os últimos patches de vulnerabilidade) e para ter acesso a novas funcionalidades e correções de bugs. No entanto, atualizar componentes críticos como o sistema operacional do host Proxmox VE, o Docker Engine, ou os pilares da nossa rede como Traefik e Authelia, requer mais cautela do que simplesmente atualizar uma aplicação Docker comum. Falhas durante essas atualizações podem ter um impacto significativo em todos os seus serviços.

Este guia fornece estratégias, princípios e pontos de atenção para abordar a atualização desses componentes críticos de forma mais segura e controlada.

## Princípios Gerais para Atualizações Críticas

Antes de iniciar qualquer atualização em um componente fundamental, siga estes princípios:

1.  **LEIA AS NOTAS DE RELEASE (Release Notes) e Documentação de Migração:**
    *   !!! critical "Este é o Passo MAIS IMPORTANTE!"
        Antes de atualizar qualquer software crítico (Proxmox VE, Docker, Traefik, Authelia, versões maiores de bancos de dados, etc.), **SEMPRE** procure e leia as notas de release oficiais para a nova versão para a qual você está atualizando. Preste atenção especial a:
        *   **"Breaking Changes" (Mudanças Quebradiças):** Alterações que são incompatíveis com versões anteriores e que podem quebrar sua configuração existente ou exigir modificações manuais.
        *   **Procedimentos de Upgrade Específicos:** Alguns softwares podem ter um processo de atualização recomendado ou passos manuais que precisam ser executados antes, durante ou depois da atualização.
        *   **Problemas Conhecidos (Known Issues):** A comunidade ou os desenvolvedores podem ter identificado problemas com a nova versão que você deve estar ciente.
        *   **Mudanças de Dependência:** A nova versão pode requerer uma versão mais nova de outra dependência (e.g., uma nova versão do Docker pode requerer um kernel Linux mais recente, ou uma nova versão de um app pode requerer uma nova versão de um banco de dados).
        *   **Caminhos de Migração:** Para saltos de versão maiores, pode haver um caminho de migração recomendado (e.g., atualizar da v1 para v2, depois v2 para v3, em vez de pular direto da v1 para v3).

2.  **FAÇA BACKUP COMPLETO PRIMEIRO:**
    Não se pode enfatizar o suficiente. Antes de tocar em qualquer componente crítico:
    *   **Host Proxmox VE:** Faça um backup completo da [configuração do host Proxmox](../04-manutencao-recuperacao/02-backup-restore-estrategia.md#o-host-proxmox-e-as-vms) e, mais crucialmente, **backups atualizados de TODAS as suas máquinas virtuais (VMs)** usando o sistema de backup do Proxmox.
    *   **Volumes Docker (Dados Persistentes):** Para os datasets ZFS que contêm os volumes dos seus containers (e.g., `data/docker-volumes`, `data/media`), crie **snapshots ZFS** no host Proxmox antes de atualizar o Docker Engine, Traefik, Authelia, ou qualquer container que gerencie dados críticos. Veja o [Guia de Snapshots ZFS](11-guia-snapshots-zfs.md).
    *   **Arquivos de Configuração Específicos:** Faça uma cópia manual dos arquivos de configuração relevantes que podem ser afetados (e.g., `traefik.yml`, `authelia/configuration.yml`, `prometheus.yml`) antes de uma atualização que possa alterá-los ou introduzir um novo formato. (Seus arquivos Ansible já estão no Git, o que é um backup da *definição* da configuração).

3.  **ATUALIZE EM UM AMBIENTE DE TESTE (Se Possível):**
    *   Para um homelab, ter um ambiente de teste idêntico pode ser inviável. No entanto, se você tiver recursos, considere:
        *   Clonar uma VM crítica (e.g., `core-services-vm`) no Proxmox para um ambiente de teste.
        *   Restaurar backups recentes em uma VM de teste.
        *   Tentar a atualização primeiro neste ambiente de teste para identificar problemas potenciais.

4.  **ATUALIZE UM COMPONENTE CRÍTICO POR VEZ:**
    *   Evite atualizar múltiplos componentes críticos (e.g., Proxmox, Docker e Traefik) todos ao mesmo tempo. Se algo quebrar, será muito mais difícil identificar a causa raiz. Atualize um, teste exaustivamente, e só então passe para o próximo.

5.  **MONITORE CUIDADOSAMENTE DURANTE E APÓS A ATUALIZAÇÃO:**
    *   Acompanhe de perto os logs do processo de atualização.
    *   Após a atualização, verifique os logs do serviço atualizado e teste sua funcionalidade minuciosamente.
    *   Verifique também os logs e a funcionalidade dos serviços que dependem do componente atualizado.

6.  **TENHA UM PLANO DE ROLLBACK (Reversão):**
    *   Antes de começar, saiba como você reverteria para a versão anterior se a atualização falhar catastroficamente ou introduzir problemas inaceitáveis. O plano de rollback pode envolver:
        *   Restaurar a VM a partir de um backup do Proxmox.
        *   Reverter para um snapshot ZFS dos seus volumes de dados.
        *   Reinstalar a versão anterior do software (se os formatos de configuração e dados forem compatíveis com downgrade, o que nem sempre é o caso).

## Atualizando o Host Proxmox VE

Atualizar o Proxmox VE pode trazer novas features, melhorias de performance, correções de segurança e atualizações para o Debian base, KVM/QEMU e LXC.

*   **Fontes de Informação Primárias:**
    *   Fórum Oficial do Proxmox VE ([forum.proxmox.com](https://forum.proxmox.com/)).
    *   Wiki do Proxmox VE, especialmente a página de [Roadmap e Notas de Release](https://pve.proxmox.com/wiki/Roadmap).
*   **Procedimento Geral:**
    1.  **Leia as Notas de Release** para a versão do Proxmox VE para a qual você está atualizando. Preste atenção especial a quaisquer mudanças no ZFS, QEMU, LXC, ou rede que possam impactar seu setup.
    2.  **Faça backup de TODAS as suas VMs** e da [configuração do host Proxmox](../04-manutencao-recuperacao/02-backup-restore-estrategia.md#o-host-proxmox-e-as-vms).
    3.  (Opcional) Se você tem um cluster, atualize um nó por vez, migrando VMs se possível. (Não aplicável ao nosso setup de nó único).
    4.  No shell do host Proxmox, como `root`:
        ```bash
        # Sincronize os índices dos pacotes com os repositórios
        apt update

        # Simule a atualização para ver o que será alterado (recomendado)
        apt dist-upgrade --simulate
        # ou apt full-upgrade --simulate

        # Realize a atualização completa do sistema
        # 'dist-upgrade' ou 'full-upgrade' são recomendados para Proxmox, pois lidam melhor
        # com dependências e remoção de pacotes obsoletos do que um simples 'apt upgrade'.
        apt dist-upgrade -y
        # OU
        # apt full-upgrade -y
        ```
    5.  **Leia atentamente a saída do `apt dist-upgrade`** durante o processo. Ele pode informar sobre pacotes que serão removidos, mudanças de configuração importantes, ou solicitar confirmações.
    6.  **Reboot do Host Proxmox:** Se a atualização incluiu um novo kernel Linux, atualizações do PVE-kernel, QEMU, ou outras bibliotecas de sistema críticas, um **reboot do host Proxmox será necessário** para que as mudanças tenham efeito. O sistema geralmente informa se um reboot é recomendado.
    7.  **Verificações Pós-Atualização:**
        *   Após o reboot, verifique se a interface web do Proxmox está acessível e funcionando.
        *   Confirme se todas as suas VMs iniciam corretamente.
        *   Verifique se os serviços do host (ZFS, NFS, rede) estão operacionais.
        *   Examine os logs do sistema (`journalctl -xe`, `dmesg`) no host Proxmox por quaisquer novos erros ou avisos.

## Atualizando o Docker Engine e Componentes (nas VMs)

Manter o Docker Engine, `containerd`, e `docker-compose-plugin` atualizados na `core-services-vm` (e na `ai-desktop-vm` se estiver usando Docker nela) é importante para segurança e novas features do Docker.

*   **Fonte de Informação:** [Notas de Release do Docker Engine](https://docs.docker.com/engine/release-notes/), documentação do Docker.
*   **Procedimento (executado dentro da VM relevante, e.g., `core-services-vm`):**
    1.  **Leia as Notas de Release** do Docker Engine para a versão para a qual você está atualizando. Preste atenção a quaisquer mudanças que possam afetar a compatibilidade com suas imagens Docker ou configurações do `docker-compose.yml`.
    2.  **Faça Backup dos Volumes Docker Críticos:** Crie snapshots ZFS dos seus datasets de volumes (e.g., `data/docker-volumes`) no host Proxmox.
    3.  **(Opcional, mas Mais Seguro) Pare todos os containers Docker em execução na VM:**
        Isso garante que os containers não estejam tentando usar o Docker Engine enquanto ele é atualizado, e previne problemas se a atualização exigir um reinício do daemon Docker que não seja totalmente transparente.
        *   **Via Portainer:** Vá em cada Stack e clique em "Stop".
        *   **Via Linha de Comando (na VM):**
            ```bash
            # Para cada diretório de stack
            # cd /caminho/para/homeserver/server/docker/stacks/nome_da_stack/
            # docker compose down # Se os arquivos compose estiverem na VM
            # Ou, de forma mais geral e bruta:
            # docker stop $(docker ps -aq)
            ```
    4.  **Atualize os Pacotes Docker usando `apt`:**
        O repositório Docker que configuramos com Ansible deve fornecer as versões mais recentes.
        ```bash
        sudo apt update

        # Veja quais pacotes Docker seriam atualizados (opcional)
        # apt list --upgradable | grep -E 'docker-ce|containerd.io|docker-compose-plugin'

        # Atualize os pacotes Docker para a versão mais recente disponível no repositório
        sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
        ```
        O comando `apt install` com os nomes dos pacotes (se já instalados) atuará como um comando de atualização para eles.
    5.  **Reinicie o Serviço Docker (geralmente feito automaticamente pelo `apt`, mas para garantir):**
        ```bash
        sudo systemctl restart docker
        ```
    6.  **Verifique as Versões Instaladas:**
        ```bash
        docker --version
        docker compose version
        containerd --version
        ```
    7.  **Reinicie seus Containers Docker:**
        *   **Via Portainer:** Vá em cada Stack e clique em "Start".
        *   **Via Linha de Comando (na VM):**
            ```bash
            # Para cada diretório de stack
            # cd /caminho/para/homeserver/server/docker/stacks/nome_da_stack/
            # docker compose up -d
            ```
    8.  **Verifique os Logs dos Containers:** Após reiniciar os containers, verifique seus logs no Portainer para garantir que todos iniciaram corretamente e estão funcionando com a nova versão do Docker Engine.

## Atualizando Traefik e Authelia (Containers Docker)

Traefik e Authelia são componentes críticos da nossa camada de rede e segurança. Eles rodam como containers Docker, então sua atualização envolve puxar uma nova tag de imagem e recriar os containers.

*   **Fonte de Informação:**
    *   **Traefik:** [Notas de Release no GitHub](https://github.com/traefik/traefik/releases), [Documentação de Migração do Traefik](https://doc.traefik.io/traefik/getting-started/migrating/).
    *   **Authelia:** [Notas de Release no GitHub](https://github.com/authelia/authelia/releases), [Documentação de Migração do Authelia](https://www.authelia.com/integration/prologue/migration/).
*   **Procedimento Geral (para Traefik ou Authelia):**
    1.  **Leia as Notas de Release com ATENÇÃO** para a nova versão da imagem que você planeja usar. Procure por:
        *   **Breaking changes** na configuração estática (`traefik.yml` para Traefik, `configuration.yml` para Authelia).
        *   Mudanças na interpretação de labels Docker (para Traefik).
        *   Mudanças em middlewares ou provedores (para Traefik).
        *   Mudanças no schema do banco de dados (Authelia geralmente lida com migrações de schema automaticamente para seu DB PostgreSQL, mas é bom verificar).
    2.  **Faça Backup:**
        *   **Arquivos de Configuração:** Faça uma cópia dos seus arquivos de configuração atuais (e.g., `traefik.yml`, `authelia/configuration.yml` e o diretório de config dinâmica do Traefik) que estão nos volumes NFS. Seus templates Ansible `.j2` já estão no Git, mas o arquivo renderizado no volume é o que está em uso.
        *   **Dados Persistentes:**
            *   Para Traefik: Faça backup do `acme.json` (contém seus certificados SSL!).
            *   Para Authelia: Faça um dump do banco de dados PostgreSQL do Authelia ([ver estratégia de backup de DB](../04-manutencao-recuperacao/02-backup-restore-estrategia.md#bancos-de-dados-dumps-diários)).
        *   Crie um snapshot ZFS do dataset `data/docker-volumes` no host Proxmox.
    3.  **Adapte Suas Configurações (SE NECESSÁRIO):**
        *   Se as notas de release indicarem breaking changes que afetam sua configuração, atualize seus templates Ansible (`.j2` para `traefik.yml` ou `authelia/configuration.yml`) e/ou os arquivos de configuração dinâmica do Traefik, ou as labels Docker nos `docker-compose.yml` de outros serviços (se as mudanças do Traefik as afetarem).
        *   Execute os playbooks Ansible relevantes para aplicar essas mudanças de configuração aos volumes NFS **ANTES** de atualizar a imagem do container.
    4.  **Atualize a Tag da Imagem Docker no `docker-compose.yml`:**
        *   Edite o arquivo `docker-compose.yml` da stack relevante (`docker/stacks/core/docker-compose.yml`, que contém Traefik, Cloudflared e Authelia).
        *   Altere a tag da imagem para a nova versão desejada (e.g., de `image: traefik:v2.10.5` para `image: traefik:v2.11.2`).
    5.  **Reaplique a Stack `core` pelo Ansible** (ela não é gerenciada pelo Portainer). A partir de `server/ansible`:
        ```bash
        ansible-playbook -i inventories/home/hosts.ini playbooks/setup-core-networking.yml --ask-vault-pass --check
        ansible-playbook -i inventories/home/hosts.ini playbooks/setup-core-networking.yml --ask-vault-pass
        ```
        O playbook copia o compose atualizado para a VM e sobe a stack com `pull: always`.
    6.  **Monitore os Logs do Container Atualizado:**
        *   Imediatamente após a atualização, verifique os logs do container Traefik ou Authelia no Portainer. Procure por erros de inicialização, problemas ao carregar a configuração, ou falhas de conexão com dependências (como o DB do Authelia).
    7.  **Teste Exaustivamente:**
        *   **Traefik:** Verifique se todos os seus serviços roteados pelo Traefik ainda estão acessíveis, se o SSL está funcionando para todos eles, e se o dashboard do Traefik está operacional.
        *   **Authelia:** Tente logar em um serviço protegido por Authelia. Verifique se o 2FA funciona. Teste diferentes cenários de acesso definidos nas suas políticas.

## Atualizando Aplicações Docker Individuais (e.g., Nextcloud, Jellyfin, Sonarr)

Este processo é geralmente menos arriscado que os componentes de infraestrutura, mas ainda requer cuidado.

*   **Aviso de Novas Versões (Diun):**
    *   O Diun (`diun` na `core-services-vm`, `diun_ai` na `ai-desktop-vm`) verifica os registros e avisa no Telegram, via n8n, quando a imagem de um container ganha versão nova (ver [Painel e Notificações](../01-manual-implementacao/09-painel-notificacoes.md)). Ele **não** atualiza nada: a atualização é sempre o processo manual abaixo.
*   **Atualização Manual (Recomendado para Controle Fino ou Tags de Versão Específicas):**
    1.  **Leia as Notas de Release** da aplicação específica para a nova versão. Algumas aplicações (especialmente complexas como Nextcloud) podem ter passos de migração ou comandos `occ` que precisam ser executados após uma atualização.
    2.  **Faça Backup dos Volumes de Dados da Aplicação:** Crie um snapshot ZFS do subdiretório relevante em `data/docker-volumes` (e.g., `data/docker-volumes/nextcloud`). Se a aplicação usa um banco de dados dedicado (como o PostgreSQL para Nextcloud), faça um dump desse banco de dados.
    3.  **Atualize a Tag da Imagem** no `docker-compose.yml` da stack da aplicação.
    4.  **Atualize a Stack no Portainer**, marcando "Re-pull image and redeploy".
    5.  **Verifique os Logs do Container** da aplicação para quaisquer erros de inicialização ou migração.
    6.  **Execute quaisquer Passos de Migração Pós-Atualização** se especificado pela documentação da aplicação.
    7.  **Teste a Aplicação Exaustivamente.**

Lembre-se, a regra de ouro é: **Backup antes de qualquer mudança significativa, e leia a documentação!** Uma abordagem cautelosa e metódica para atualizações manterá seu servidor doméstico rodando de forma suave e segura.