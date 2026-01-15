# 🛠️ Guias de Sustentação e Modificação da Infraestrutura

Bem-vindo à seção de **Guias de Sustentação e Modificação** da sua infraestrutura de servidor doméstico! Após ter concluído a [Implementação Inicial](../01-manual-implementacao/index.md) e ter uma compreensão da [Visão Geral da Arquitetura](../02-visao-geral-arquitetura/index.md), esta seção é o seu manual prático para as operações do dia-a-dia, para realizar alterações, adicionar novos serviços e funcionalidades, solucionar problemas comuns, e gerenciar os diversos componentes do seu setup.

## Objetivo Desta Seção

O principal objetivo aqui é capacitá-lo a manter, evoluir e expandir sua infraestrutura de forma segura, consistente e alinhada com os princípios de Infraestrutura como Código (IaC) que estabelecemos. Queremos que você se sinta confiante para:

*   **Expandir sua gama de serviços:** Adicionar novas aplicações e containers Docker de forma integrada e segura, aproveitando a flexibilidade da nossa arquitetura com Traefik, Authelia e NFS.
*   **Modificar configurações existentes:** Entender onde residem as configurações chave dos seus sistemas e serviços (Ansible, Proxmox, Docker, Traefik, Authelia, etc.) e como alterá-las de forma controlada e segura.
*   **Diagnosticar e resolver problemas:** Fornecer um ponto de partida estruturado para o troubleshooting, com foco nas ferramentas de diagnóstico e nos logs disponíveis em sua infraestrutura.
*   **Gerenciar componentes de rede e hardware de forma eficaz:** Compreender como interagir com as redes Docker (`proxy`, `internal_services`) e como realizar o passthrough de hardware adicional (USB, PCI) para suas máquinas virtuais e containers.
*   **Manter a integridade da sua Infraestrutura como Código (IaC):** Reforçar as boas práticas ao fazer alterações, garantindo que sua configuração Ansible permaneça a fonte da verdade e que seu sistema seja sempre reprodutível.

Manter uma infraestrutura dinâmica e auto-hospedada é uma jornada contínua de aprendizado e ajustes. Esta seção visa fornecer os guias práticos para tornar essa jornada mais suave e bem-sucedida.

## Tópicos Cobertos nos Guias de Sustentação

Esta seção está organizada nos seguintes guias práticos para ajudá-lo a operar e evoluir seu servidor doméstico:

1.  **[Adicionando um Novo Serviço Docker à Infraestrutura](01-adicionando-novo-servico-docker.md):**
    Um checklist detalhado e um exemplo prático de como integrar uma nova aplicação containerizada ao seu setup, desde o planejamento até o deploy e configuração de acesso.
2.  **[Modificando Configurações Existentes](02-modificando-configuracoes-existentes.md):**
    Um guia essencial sobre onde encontrar as principais configurações da sua infraestrutura e dos seus serviços, e o processo seguro para alterá-las, mantendo a consistência com sua IaC.
3.  **[Troubleshooting Comum](03-troubleshooting-comum.md):**
    Dicas práticas, ferramentas essenciais de diagnóstico e estratégias para identificar e solucionar alguns dos problemas mais frequentes que podem surgir em sua rede, containers ou serviços.
4.  **[Gerenciando Redes Docker](04-gerenciando-redes-docker.md):**
    Uma exploração mais aprofundada das redes Docker `proxy` e `internal_services` que utilizamos, como elas funcionam, e quando você poderia considerar a criação de novas redes.
5.  **[Passthrough de Hardware Adicional para VMs e Containers](05-passthrough-hardware-adicional.md):**
    Instruções sobre como expor dispositivos USB (como dongles Zigbee/Zwave) ou outros dispositivos PCI do seu host Proxmox para suas máquinas virtuais e, subsequentemente, para os containers Docker que precisam deles.
6.  **[Gerenciando Recursos de Máquinas Virtuais (VMs)](06-gerenciando-recursos-vms.md):**
    Como redimensionar CPU, RAM e discos de VMs existentes de forma segura e consistente com sua configuração Ansible, e considerações sobre quando adicionar mais recursos ou criar novas VMs.
7.  **[Cenários Específicos de Criação de VMs](07-cenarios-especificos-criacao-vms.md):**
    Explorando a criação de máquinas virtuais para propósitos mais específicos, como um firewall/roteador dedicado (e.g., pfSense/OPNsense), ambientes de teste isolados, ou VMs Windows.
8.  **[Compartilhando Recursos Entre VMs ou com a Rede Local](08-compartilhando-recursos-entre-vms.md):**
    Diferentes métodos para compartilhar arquivos, bancos de dados ou outros recursos entre suas VMs ou com outros dispositivos na sua rede local (NFS, Samba, VirtIO-FS).
9.  **[Integrando Novos Serviços a Stacks Docker Existentes](09-integrando-novos-servicos-stacks-existentes.md):**
    Como adicionar um novo container a um arquivo `docker-compose.yml` já existente, em vez de criar uma stack totalmente nova para cada pequeno serviço.
10. **[Atualização Segura de Componentes Críticos da Infraestrutura](10-atualizacao-segura-componentes-criticos.md):**
    Estratégias e pontos de atenção para atualizar componentes fundamentais como Proxmox VE, Docker Engine, Traefik e Authelia de forma mais segura e controlada.
11. **[Hospedando uma Aplicação Pública no Domínio Raiz (e.g., Blog)](11-hospedando-aplicacao-publica-dominio-raiz.md):**
    Considerações de segurança e configuração no Traefik para expor uma aplicação (idealmente um site estático) diretamente no seu domínio principal (e.g., `https://meudominio.com`).
12. **[Guia Prático de Snapshots ZFS](12-guia-snapshots-zfs.md):**
    Um guia detalhado sobre como criar, listar, gerenciar e utilizar os poderosos snapshots ZFS para recuperação rápida de dados e proteção local no seu host Proxmox.

Estes guias são projetados para serem suas referências rápidas e acionáveis para as operações do dia-a-dia e para a evolução contínua do seu servidor doméstico. Lembre-se sempre da importância de testar as mudanças em ambientes menos críticos quando possível e de manter seus [backups atualizados e testados](../04-manutencao-recuperacao/02-backup-restore-estrategia.md)!