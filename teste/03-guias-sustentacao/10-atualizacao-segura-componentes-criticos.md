# Atualização Segura de Componentes Críticos da Infraestrutura

Manter sua infraestrutura atualizada é vital para segurança e acesso a novas funcionalidades. No entanto, atualizar componentes críticos como Proxmox VE, Traefik, Authelia, ou o Docker Engine requer mais cautela do que atualizar uma aplicação Docker comum. Falhas durante essas atualizações podem ter um impacto significativo.

Este guia fornece estratégias e pontos de atenção para atualizar esses componentes de forma mais segura.

## Princípios Gerais para Atualizações Críticas

1.  **LEIA AS NOTAS DE RELEASE (Release Notes):**
    *   !!! critical "Passo Mais Importante!"
        Antes de qualquer atualização de um componente crítico, **SEMPRE** leia as notas de release da nova versão. Procure por:
        *   **Breaking Changes:** Mudanças que podem quebrar sua configuração existente.
        *   **Procedimentos de Upgrade Específicos:** Alguns softwares podem exigir passos manuais durante a atualização.
        *   **Problemas Conhecidos:** Outros usuários podem ter reportado problemas com a nova versão.
        *   **Dependências:** A nova versão pode exigir uma versão mais nova de outra dependência (e.g., Docker, Go).
2.  **FAÇA BACKUP PRIMEIRO:**
    *   **Proxmox VE Host:** Faça um backup completo da configuração do host e, crucialmente, **backups de todas as suas VMs** antes de atualizar o Proxmox VE.
    *   **Volumes Docker:** Faça snapshots ZFS dos seus datasets de volumes (e.g., `data/docker-volumes`) antes de atualizar Docker Engine, Traefik, Authelia, ou qualquer container que gerencie dados críticos.
    *   **Arquivos de Configuração:** Faça uma cópia dos arquivos de configuração relevantes (e.g., `traefik.yml`, `authelia/configuration.yml`) antes de uma atualização que possa alterá-los ou exigir um novo formato.
3.  **ATUALIZE EM UM AMBIENTE DE TESTE (SE POSSÍVEL):**
    *   Para um homelab, isso pode ser difícil. Mas se você tiver recursos, clonar uma VM crítica para teste e tentar a atualização nela primeiro é o ideal.
4.  **ATUALIZE UM COMPONENTE POR VEZ:**
    *   Evite atualizar múltiplos componentes críticos simultaneamente. Se algo quebrar, será mais fácil identificar a causa.
5.  **MONITORE DURANTE E APÓS A ATUALIZAÇÃO:**
    *   Acompanhe os logs do processo de atualização.
    *   Após a atualização, verifique os logs do serviço e teste sua funcionalidade exaustivamente.
6.  **TENHA UM PLANO DE ROLLBACK:**
    *   Saiba como reverter para a versão anterior se a atualização falhar ou causar problemas. Isso pode envolver:
        *   Restaurar de backups/snapshots.
        *   Reinstalar a versão anterior do software (se possível e as configs forem compatíveis).

## Atualizando Proxmox VE (Host)

*   **Fontes de Informação:** Fórum Proxmox, [Roadmap e Notas de Release Proxmox](https://pve.proxmox.com/wiki/Roadmap).
*   **Procedimento:**
    1.  Leia as notas de release para a versão para a qual você está atualizando.
    2.  **Faça backup de todas as VMs.**
    3.  (Opcional, mas recomendado para grandes atualizações) Faça backup da configuração do host Proxmox.
    4.  No shell do host Proxmox, como `root`:
        ```bash
        apt update
        apt dist-upgrade # Ou apt full-upgrade. 'dist-upgrade' lida melhor com dependências e remoção de pacotes obsoletos.
        ```
    5.  **Leia atentamente a saída do `apt dist-upgrade`**. Ele pode informar sobre pacotes que serão removidos ou mudanças importantes. Confirme se estiver de acordo.
    6.  Se a atualização incluir um novo kernel ou atualizações do PVE, um **reboot do host Proxmox será necessário.**
    7.  Após o reboot, verifique se todas as VMs iniciam corretamente e se os serviços do host (ZFS, NFS, etc.) estão funcionando.
    8.  Verifique os logs do sistema (`journalctl -xe`).

## Atualizando Docker Engine e Componentes (na VM)

*   **Fonte de Informação:** Documentação do Docker, notas de release.
*   **Procedimento (na VM, e.g., `core-services-vm`):**
    1.  **Pare todos os containers Docker (Opcional, mas mais seguro):**
        ```bash
        # Maneira rápida de parar todos os containers em todas as stacks gerenciadas por Portainer:
        # No Portainer, vá em cada Stack e clique em "Stop".
        # Ou, se você tiver os docker-compose.yml na VM:
        # cd /caminho/para/stack1 && docker compose down
        # cd /caminho/para/stack2 && docker compose down
        # ...
        # Ou, de forma mais bruta: docker stop $(docker ps -aq)
        ```
        Parar os containers garante que eles não estejam tentando usar o Docker Engine enquanto ele é atualizado.
    2.  **Faça backup dos volumes Docker importantes** (snapshots ZFS do dataset `data/docker-volumes` no host Proxmox é uma boa maneira).
    3.  Atualize os pacotes Docker:
        ```bash
        sudo apt update
        # Veja quais pacotes Docker seriam atualizados:
        # apt list --upgradable | grep docker
        sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
        ```
        O `apt install` com os nomes dos pacotes deve atualizá-los para a versão mais recente disponível no repositório Docker que você configurou.
    4.  **Reinicie o serviço Docker (geralmente feito automaticamente pelo apt, mas para garantir):**
        ```bash
        sudo systemctl restart docker
        ```
    5.  Verifique a versão: `docker --version` e `docker compose version`.
    6.  **Reinicie seus containers Docker:**
        *   Via Portainer: Vá em cada Stack e clique em "Start".
        *   Ou via linha de comando: `cd /caminho/para/stack && docker compose up -d`.
    7.  Verifique os logs dos containers para garantir que tudo iniciou corretamente.

## Atualizando Traefik

Traefik é um container Docker, então sua atualização segue o processo de atualização de imagens Docker.

*   **Fonte de Informação:** [Notas de Release do Traefik no GitHub](https://github.com/traefik/traefik/releases), [Documentação de Migração do Traefik](https://doc.traefik.io/traefik/getting-started/migrating/).
*   **Procedimento:**
    1.  **Leia as notas de release para a nova versão do Traefik.** Preste atenção especial a:
        *   Mudanças na estrutura do `traefik.yml` (configuração estática).
        *   Mudanças em como as labels Docker são interpretadas.
        *   Mudanças em middlewares ou provedores.
    2.  **Faça backup:**
        *   Do arquivo `traefik.yml` (ou do template `.j2` no Ansible).
        *   Do diretório de configuração dinâmica.
        *   Do arquivo `acme.json` (contém seus certificados SSL!).
    3.  **Atualize a tag da imagem do Traefik** no seu `docker/stacks/core/docker-compose.yml`.
        Exemplo: de `image: traefik:v2.10.5` para `image: traefik:v2.11.2`.
    4.  **Adapte suas configurações (se necessário):** Se as notas de release indicarem breaking changes, atualize seu `traefik.yml.j2`, arquivos de configuração dinâmica, ou labels Docker nos seus outros `docker-compose.yml` ANTES de atualizar a stack do Traefik.
    5.  **Atualize a Stack "core" no Portainer:**
        *   Vá para a stack "core".
        *   Editor -> Cole o `docker-compose.yml` com a nova tag da imagem do Traefik.
        *   Clique em "Update the stack", marcando "Re-pull image and redeploy".
    6.  **Monitore os Logs do Traefik:** Verifique por erros de inicialização ou de processamento de configuração.
    7.  **Teste:** Verifique se todos os seus serviços roteados pelo Traefik estão acessíveis e se o SSL está funcionando. Verifique o dashboard do Traefik.

## Atualizando Authelia

Similar ao Traefik, Authelia é um container Docker.

*   **Fonte de Informação:** [Notas de Release do Authelia no GitHub](https://github.com/authelia/authelia/releases), [Documentação de Migração do Authelia](https://www.authelia.com/integration/prologue/migration/).
*   **Procedimento:**
    1.  **Leia as notas de release para a nova versão do Authelia.** Atenção a:
        *   Mudanças no formato do `configuration.yml`.
        *   Mudanças no schema do banco de dados (Authelia geralmente lida com migrações de schema automaticamente, mas verifique).
    2.  **Faça backup:**
        *   Do arquivo `configuration.yml` (ou do template `.j2` no Ansible).
        *   Faça um dump do banco de dados PostgreSQL do Authelia.
    3.  **Atualize a tag da imagem do Authelia** no seu `docker/stacks/authelia/docker-compose.yml`.
    4.  **Adapte sua `configuration.yml` (se necessário):** Se houver breaking changes.
    5.  **Atualize a Stack "authelia" no Portainer:**
        *   Vá para a stack "authelia".
        *   Editor -> Cole o `docker-compose.yml` com a nova tag da imagem.
        *   Clique em "Update the stack", marcando "Re-pull image and redeploy".
    6.  **Monitore os Logs do Authelia:** Verifique por erros de inicialização, conexão com o DB, ou processamento de configuração.
    7.  **Teste:** Tente logar em um serviço protegido por Authelia. Verifique se o 2FA funciona.

## Atualizando Aplicações Docker Individuais (e.g., Nextcloud, Plex)

Já coberto em parte pela seção de [Watchtower](#2-atualizações-de-imagens-docker-containers) e pelo processo manual.

*   **Fonte de Informação:** Notas de release da aplicação específica.
*   **Procedimento:**
    1.  **Leia as notas de release.** Algumas aplicações podem ter passos de upgrade específicos (e.g., Nextcloud às vezes requer executar comandos `occ` após uma atualização).
    2.  **Faça backup dos volumes de dados da aplicação** (especialmente configurações e bancos de dados, se a aplicação usar um DB interno como SQLite). Snapshot ZFS é seu amigo. Se usar DB externo, faça dump do DB.
    3.  Atualize a tag da imagem no `docker-compose.yml` da stack da aplicação.
    4.  Atualize a stack no Portainer ("Re-pull image and redeploy").
    5.  Verifique os logs do container da aplicação.
    6.  Execute quaisquer passos de migração pós-atualização recomendados pela documentação da aplicação.
    7.  Teste a aplicação exaustivamente.

Lembre-se, a paciência e a preparação (leitura de documentação e backups) são suas melhores ferramentas ao realizar atualizações em componentes críticos.