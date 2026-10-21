<!-- Mantido pela skill update-index (.agents/skills/update-index/SKILL.md) — edite por ela -->
# Índice do repositório

Mapa do repositório. Caminhos de arquivos do server são relativos a `server/`; páginas, a `wiki/docs/`.

## Agentes e skills

| Skill | Quando usar | Caminho |
|---|---|---|
| `add-ansible-component` | criar role, playbook, grupo ou variável Ansible | `.agents/skills/add-ansible-component/SKILL.md` |
| `add-app` | adicionar uma aplicação | `.agents/skills/add-app/SKILL.md` |
| `add-integration` | criar uma integração e ligá-la em todos os consumidores | `.agents/skills/add-integration/SKILL.md` |
| `audit-integrations` | verificar integrações (catálogo × índice × arquivos) | `.agents/skills/audit-integrations/SKILL.md` |
| `fix-integrations` | corrigir achados da auditoria e gerar variáveis que faltam | `.agents/skills/fix-integrations/SKILL.md` |
| `remove-app` | remover uma aplicação | `.agents/skills/remove-app/SKILL.md` |
| `remove-integration` | desligar uma integração de todos e remover o provedor | `.agents/skills/remove-integration/SKILL.md` |
| `sync-wiki-server` | `dev.py check` com erros ou avisos | `.agents/skills/sync-wiki-server/SKILL.md` |
| `update-index` | manter o `INDEX.md` em dia (fim de toda mudança) | `.agents/skills/update-index/SKILL.md` |
| `validate-infra` | antes de commitar ou entregar mudanças | `.agents/skills/validate-infra/SKILL.md` |
| `wiki-first-change` | qualquer mudança na infraestrutura ou na wiki | `.agents/skills/wiki-first-change/SKILL.md` |
| `wiki-page-authoring` | criar, renomear ou editar páginas da wiki | `.agents/skills/wiki-page-authoring/SKILL.md` |

## Aplicações

| Aplicação | Stack / VM | Integrações ativas | Página |
|---|---|---|---|
| `agentgateway` | agents / core-services-vm | roteamento, autenticacao, acesso-externo, metricas, logs, dados, variaveis, mcp, documentacao, notificacoes, painel | `01-manual-implementacao/13-agentes-base.md` |
| `alloy` | ansible:infra/alloy / proxmox_main_host; ansible:infra/alloy / core-services-vm; ansible:infra/alloy / ai-desktop-vm | metricas, logs, documentacao, notificacoes | `01-manual-implementacao/04-configuracao-base-vms-ubuntu.md` |
| `authelia` | core / core-services-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/05-rede-segura.md` |
| `bazarr` | media / core-services-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/10-midia.md` |
| `blackbox-exporter` | apps / core-services-vm | metricas, logs, dados, variaveis, documentacao, notificacoes | `01-manual-implementacao/09-painel-notificacoes.md` |
| `cloudflared` | core / core-services-vm | metricas, logs, variaveis, documentacao, notificacoes | `01-manual-implementacao/05-rede-segura.md` |
| `collabora` | cloud / core-services-vm | roteamento, autenticacao, acesso-externo, logs, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/11-fotos-arquivos.md` |
| `diun` | apps / core-services-vm; ai / ai-desktop-vm | logs, dados, variaveis, documentacao, notificacoes | `01-manual-implementacao/09-painel-notificacoes.md` |
| `docker-socket-proxy` | apps / core-services-vm; ai / ai-desktop-vm | logs, variaveis, documentacao, notificacoes | `01-manual-implementacao/09-painel-notificacoes.md` |
| `flaresolverr` | media / core-services-vm | logs, variaveis, documentacao, notificacoes | `01-manual-implementacao/10-midia.md` |
| `gluetun` | media / core-services-vm | logs, dados, variaveis, documentacao, notificacoes | `01-manual-implementacao/10-midia.md` |
| `grafana` | apps / core-services-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/07-deploy-apps.md` |
| `homeassistant` | apps / core-services-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/07-deploy-apps.md` |
| `homepage` | apps / core-services-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, documentacao, notificacoes | `01-manual-implementacao/09-painel-notificacoes.md` |
| `immich` | photos / core-services-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/11-fotos-arquivos.md` |
| `jellyfin` | media / core-services-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/10-midia.md` |
| `langfuse` | langfuse / ai-desktop-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/13-agentes-base.md` |
| `lidarr` | media / core-services-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/10-midia.md` |
| `litellm` | ai / ai-desktop-vm | roteamento, autenticacao, acesso-externo, metricas, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/08-stack-ia.md` |
| `loki` | apps / core-services-vm | dados, variaveis, documentacao, notificacoes | `01-manual-implementacao/07-deploy-apps.md` |
| `n8n` | apps / core-services-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, documentacao, painel | `01-manual-implementacao/07-deploy-apps.md` |
| `nextcloud` | cloud / core-services-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/11-fotos-arquivos.md` |
| `notas` | notes / ai-desktop-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, mcp, documentacao, notificacoes, painel | `01-manual-implementacao/12-segundo-cerebro.md` |
| `notas-escrita` | notes / ai-desktop-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, mcp, documentacao, notificacoes, painel | `01-manual-implementacao/12-segundo-cerebro.md` |
| `ollama` | ai / ai-desktop-vm | logs, dados, variaveis, documentacao, notificacoes | `01-manual-implementacao/08-stack-ia.md` |
| `open-webui` | ai / ai-desktop-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, llm, documentacao, notificacoes, painel | `01-manual-implementacao/08-stack-ia.md` |
| `portainer` | ansible:infra/docker / core-services-vm | roteamento, autenticacao, acesso-externo, logs, dados, documentacao, notificacoes, painel | `01-manual-implementacao/04-configuracao-base-vms-ubuntu.md` |
| `prometheus` | apps / core-services-vm | roteamento, autenticacao, acesso-externo, metricas, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/07-deploy-apps.md` |
| `prowlarr` | media / core-services-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/10-midia.md` |
| `qbittorrent` | media / core-services-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/10-midia.md` |
| `radarr` | media / core-services-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/10-midia.md` |
| `recyclarr` | media / core-services-vm | logs, dados, variaveis, documentacao, notificacoes | `01-manual-implementacao/10-midia.md` |
| `seerr` | media / core-services-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/10-midia.md` |
| `sonarr` | media / core-services-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/10-midia.md` |
| `syncthing` | notes / ai-desktop-vm | roteamento, autenticacao, acesso-externo, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/12-segundo-cerebro.md` |
| `traefik` | core / core-services-vm | autenticacao, acesso-externo, logs, dados, variaveis, documentacao, notificacoes, painel | `01-manual-implementacao/05-rede-segura.md` |

## Integrações

| Integração | Provedor | Aplica-se a | Seção |
|---|---|---|---|
| `acesso-externo` | `cloudflared` | Exposição ≠ interna | [acesso-externo](wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md#acesso-externo) |
| `autenticacao` | `authelia` | Exposição ≠ interna | [autenticacao](wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md#autenticacao) |
| `dados` | infra (ZFS no host Proxmox, exportado por NFS) | Dados ≠ nenhum | [dados](wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md#dados) |
| `documentacao` | wiki | todas | [documentacao](wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md#documentacao) |
| `llm` | `litellm` | `+llm` | [llm](wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md#llm) |
| `logs` | `loki` (coleta pelo `alloy`) | todas | [logs](wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md#logs) |
| `mcp` | `authelia` | `+mcp` | [mcp](wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md#mcp) |
| `metricas` | `prometheus` | Métricas = sim | [metricas](wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md#metricas) |
| `notificacoes` | `n8n` (coletores: Grafana Alerting, `blackbox-exporter`, `diun`) | todas | [notificacoes](wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md#notificacoes) |
| `painel` | `homepage` | Exposição ≠ interna | [painel](wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md#painel) |
| `roteamento` | `traefik` | Exposição ≠ interna | [roteamento](wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md#roteamento) |
| `variaveis` | infra (Ansible gera os `.env`; Portainer os carrega) | todas (exceto `ansible:<role>`) | [variaveis](wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md#variaveis) |

## Páginas da wiki

| Página | Título | Descrição |
|---|---|---|
| `01-manual-implementacao/00-preparacao-planejamento.md` | Seção 0: Preparação e Planejamento | Pré-requisitos, estrutura do repositório (server/, wiki/, tools/), .gitignore e modelo de variáveis das stacks antes de começar. |
| `01-manual-implementacao/01-maquina-controle-ansible.md` | Seção 1: Configuração da Máquina de Controle Ansible | Prepara a máquina de controle: Ansible, chaves SSH, Ansible Vault, inventário hosts.ini e variáveis globais em group_vars. |
| `01-manual-implementacao/02-proxmox-ve-host.md` | Seção 2: Instalação e Configuração Base do Proxmox VE (Incluindo Servidor NFS) | Instala e configura o host Proxmox VE: repositórios, pool ZFS, servidor NFS, firewall e o coletor Grafana Alloy. |
| `01-manual-implementacao/03-provisionamento-vms.md` | Seção 3: Provisionamento das Máquinas Virtuais (VMs) com Ansible | Cria as VMs core-services-vm e ai-desktop-vm a partir de template Cloud-Init com o role proxmox-vm, incluindo passthrough de GPU. |
| `01-manual-implementacao/04-configuracao-base-vms-ubuntu.md` | Seção 4: Configuração Base das VMs Ubuntu (Docker, Portainer, Cliente NFS) | Configuração base das VMs Ubuntu com Ansible: pacotes, fuso horário, cliente NFS, Docker, Portainer e o coletor Grafana Alloy. |
| `01-manual-implementacao/05-rede-segura.md` | Seção 5: Implementação da Rede Segura (Traefik, Cloudflare Tunnel, Authelia) | Rede segura na core-services-vm: Traefik como proxy reverso, Cloudflare Tunnel para acesso externo e Authelia para 2FA. |
| `01-manual-implementacao/06-deploy-core.md` | Seção 6: Deploy da Infraestrutura Core (Traefik + Cloudflared + Authelia) | Deploy da stack core (Traefik, Cloudflared e Authelia) pelo Ansible, com o playbook setup-core-networking.yml. |
| `01-manual-implementacao/07-deploy-apps.md` | Seção 7: Deploy de Aplicações (Monitoramento, n8n, Home Assistant) | Deploy das aplicações na stack apps: monitoramento, n8n e Home Assistant, com preparação de volumes via Ansible. |
| `01-manual-implementacao/08-stack-ia.md` | Seção 8: Stack de IA (gateway LiteLLM, Open WebUI, Ollama e Claude Code) | Stack de IA na ai-desktop-vm: gateway LiteLLM com apelidos de modelo, chaves por cliente e uso, Jev, Open WebUI com OIDC, Ollama com Vulkan e o Claude Code. |
| `01-manual-implementacao/09-painel-notificacoes.md` | Seção 9: Painel e Notificações | Painel Homepage e notificações no Telegram via n8n: Grafana Alerting, blackbox-exporter, Diun, workflow notificar, passos manuais e teste de ponta a ponta. |
| `01-manual-implementacao/10-midia.md` | Seção 10: Mídia (Jellyfin, *arr, Seerr e VPN) | Stack media: Jellyfin, Seerr, Sonarr, Radarr, Lidarr, Prowlarr, Bazarr, Recyclarr e qBittorrent atrás da ProtonVPN (gluetun), com /data único e importação por hardlink. |
| `01-manual-implementacao/11-fotos-arquivos.md` | Seção 11: Fotos e Arquivos (Immich, Nextcloud e Collabora) | Stacks photos (Immich) e cloud (Nextcloud, cron e Collabora), públicas pelo túnel com login OIDC do Authelia, datasets com cota e bancos no disco local. |
| `01-manual-implementacao/12-segundo-cerebro.md` | Seção 12: Segundo cérebro (Obsidian, Syncthing, busca local e MCP) | Stack notes na VM de IA: vaults do Obsidian sincronizados pelo Syncthing, busca local com qmd sobre as notas e os documentos do Nextcloud, e MCP para o Claude com escopo por vault. |
| `01-manual-implementacao/13-agentes-base.md` | Seção 13: Agentes — base (hub de MCPs, operações e rastreio) | Base dos agentes: hub de MCPs (agentgateway) com rota de leitura pública e rota de controle na LAN, MCP de operações com runner Ansible, MCP do Grafana, Home Assistant e n8n, e Langfuse para rastrear LLM e ferramentas. |
| `01-manual-implementacao/index.md` | Manual de Implementação | Roteiro do manual de implementação: a ordem dos passos para construir o servidor doméstico do zero. |
| `02-visao-geral-arquitetura/01-fluxo-rede-acesso-externo.md` | Fluxo de Rede e Acesso Externo Seguro | Como uma requisição externa chega aos serviços: Cloudflare Tunnel, Traefik e Authelia, com diagrama do fluxo. |
| `02-visao-geral-arquitetura/02-virtualizacao-proxmox.md` | Virtualização com Proxmox VE | Por que Proxmox VE e como a virtualização organiza VMs, recursos e isolamento na arquitetura. |
| `02-visao-geral-arquitetura/03-armazenamento-zfs-nfs.md` | Estratégia de Armazenamento com ZFS e NFS | Estratégia de armazenamento: pool ZFS no host Proxmox, datasets e compartilhamento com as VMs via NFS. |
| `02-visao-geral-arquitetura/04-automacao-ansible.md` | Automação da Infraestrutura com Ansible | Infraestrutura como código com Ansible: inventário, roles, playbooks e Vault, e como eles se organizam no projeto. |
| `02-visao-geral-arquitetura/05-gerenciamento-containers.md` | Gerenciamento de Containers com Docker e Portainer | Docker, Docker Compose e Portainer: como as stacks de containers são definidas, implantadas e gerenciadas. |
| `02-visao-geral-arquitetura/06-principios-seguranca.md` | Princípios de Segurança Aplicados | Princípios de segurança aplicados: defesa em camadas, menor privilégio, 2FA, firewall e gestão de segredos. |
| `02-visao-geral-arquitetura/07-apis-llm-estrategia.md` | Estratégia de APIs de LLM e Arquitetura Híbrida de IA | Estratégia de IA híbrida com LiteLLM: quando usar modelos locais no Ollama ou APIs externas, com foco em custo. |
| `02-visao-geral-arquitetura/09-catalogo-aplicacoes.md` | Catálogo de Aplicações | Catálogo de aplicações do servidor: fatos de cada aplicação (stack, serviços, exposição, dados, métricas, integrações providas) que guiam as integrações. |
| `02-visao-geral-arquitetura/10-indice-integracoes.md` | Índice de Integrações | Índice declarativo das integrações entre aplicações: provedor, a quem se aplica, regras verificáveis e passos para adicionar ou remover. |
| `02-visao-geral-arquitetura/index.md` | 💡 Visão Geral da Arquitetura | Visão conceitual de como virtualização, armazenamento, automação, containers, rede e segurança se integram no servidor. |
| `03-guias-sustentacao/01-adicionando-novo-servico-docker.md` | Adicionando um Novo Serviço Docker à Infraestrutura | Checklist e exemplo prático para adicionar um novo serviço Docker com volumes, Traefik, Authelia e Ansible. |
| `03-guias-sustentacao/02-modificando-configuracoes-existentes.md` | Modificando Configurações Existentes | Onde ficam as configurações (Ansible, compose, Portainer) e como alterá-las com segurança e rastreabilidade. |
| `03-guias-sustentacao/03-troubleshooting-comum.md` | Guia de Troubleshooting Comum | Ferramentas e soluções para os problemas mais comuns: rede, containers, NFS, Traefik, Authelia e VMs. |
| `03-guias-sustentacao/04-gerenciando-redes-docker.md` | Gerenciando Redes Docker | Redes Docker da arquitetura (proxy e internal_services): como funcionam, como conectar serviços e diagnosticar. |
| `03-guias-sustentacao/05-passthrough-hardware-adicional.md` | Passthrough de Hardware Adicional para VMs e Containers | Como passar dispositivos de hardware adicionais (USB, discos, PCI) do host Proxmox para VMs e containers. |
| `03-guias-sustentacao/06-gerenciando-recursos-vms.md` | Gerenciando Recursos de Máquinas Virtuais (VMs) | Ajuste de CPU, RAM e disco das VMs no Proxmox mantendo o Ansible como fonte da verdade. |
| `03-guias-sustentacao/07-cenarios-especificos-criacao-vms.md` | Cenários Específicos de Criação de Máquinas Virtuais (VMs) | Cenários para criar VMs com propósito específico além da core-services-vm e da ai-desktop-vm. |
| `03-guias-sustentacao/08-compartilhando-recursos-entre-vms.md` | Compartilhando Recursos Entre VMs ou com a Rede Local | Compartilhamento de arquivos, bancos de dados e serviços entre VMs e com a rede local (NFS, Samba, PostgreSQL). |
| `03-guias-sustentacao/09-integrando-novos-servicos-stacks-existentes.md` | Integrando Novos Serviços a Stacks Docker Existentes | Quando e como adicionar um container a uma stack Docker existente em vez de criar uma stack nova. |
| `03-guias-sustentacao/10-atualizacao-segura-componentes-criticos.md` | Atualização Segura de Componentes Críticos da Infraestrutura | Como atualizar com segurança Proxmox VE, Docker, Traefik, Authelia e outros componentes críticos. |
| `03-guias-sustentacao/11-hospedando-aplicacao-publica-dominio-raiz.md` | Hospedando uma Aplicação Pública no Domínio Raiz (e.g., Blog) | Como publicar uma aplicação (ex.: blog) no domínio raiz com Cloudflare Tunnel e Traefik, sem passar pelo Authelia. |
| `03-guias-sustentacao/12-guia-snapshots-zfs.md` | Guia Prático de Snapshots ZFS | Guia prático de snapshots ZFS: criar, listar, reverter, automatizar e usá-los antes de mudanças arriscadas. |
| `03-guias-sustentacao/13-usando-geminicli.md` | Usando o Gemini CLI para Interação Inteligente com o Servidor | Instala o Gemini CLI nas VMs via Ansible e mostra como usá-lo no terminal para manutenção e troubleshooting. |
| `03-guias-sustentacao/index.md` | 🛠️ Guias de Sustentação e Modificação da Infraestrutura | Guias para modificar, expandir e manter a infraestrutura depois da implementação inicial. |
| `04-manutencao-recuperacao/01-rotinas-manutencao.md` | Rotinas de Manutenção Essenciais | Rotinas periódicas de manutenção (atualizações, ZFS scrub, logs, certificados) e scripts de validação do server. |
| `04-manutencao-recuperacao/02-backup-restore-estrategia.md` | Estratégia de Backup e Procedimentos de Restauração | Estratégia de backup 3-2-1 e procedimentos de restauração de VMs, volumes e configurações. |
| `04-manutencao-recuperacao/03-cicd-basico-ansible.md` | CI/CD Básico para Infraestrutura como Código (Ansible) | CI/CD básico para a infraestrutura como código: lint, testes e execução controlada dos playbooks Ansible. |
| `04-manutencao-recuperacao/04-reconstruindo-infraestrutura.md` | Reconstruindo a Infraestrutura Após uma Falha Grave | Como reconstruir a infraestrutura após falha grave do disco do sistema, usando Git, Ansible e o pool ZFS. |
| `04-manutencao-recuperacao/05-migrando-hardware-rede.md` | Adaptando a Infraestrutura para Novo Hardware ou Mudanças de Rede | Como adaptar a infraestrutura a um novo hardware ou a mudanças de rede (novo IP, sub-rede ou roteador). |
| `04-manutencao-recuperacao/index.md` | ⚙️ Manutenção Preventiva e Recuperação de Desastres | Manutenção preventiva e recuperação de desastres: rotinas, backups, CI/CD, reconstrução e migração. |
| `05-referencia-rapida.md` | 📎 Referência Rápida | Referência rápida: tecnologias usadas, para que servem, links da documentação oficial e alternativas. |
| `index.md` | Guia do Servidor do Léo Ivan | Wiki do servidor doméstico do Léo Ivan: Proxmox, Ansible, Docker, ZFS, Cloudflare Tunnel, Traefik e Authelia, com o mapa das seções. |

## Arquivos do server

| Arquivo | Tipo | Página que documenta |
|---|---|---|
| `ansible/ansible.cfg` | outro | `01-manual-implementacao/01-maquina-controle-ansible.md` |
| `ansible/files/n8n/notificar.json` | outro | `01-manual-implementacao/09-painel-notificacoes.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md` |
| `ansible/inventories/home/group_vars/all/main.yml` | inventario | `01-manual-implementacao/01-maquina-controle-ansible.md`, `01-manual-implementacao/02-proxmox-ve-host.md`, `01-manual-implementacao/03-provisionamento-vms.md`, `03-guias-sustentacao/02-modificando-configuracoes-existentes.md`, `04-manutencao-recuperacao/03-cicd-basico-ansible.md`, `04-manutencao-recuperacao/05-migrando-hardware-rede.md` |
| `ansible/inventories/home/group_vars/all/vault.yml.example` | inventario | `01-manual-implementacao/01-maquina-controle-ansible.md` |
| `ansible/inventories/home/hosts.ini` | inventario | `01-manual-implementacao/01-maquina-controle-ansible.md`, `01-manual-implementacao/02-proxmox-ve-host.md`, `01-manual-implementacao/03-provisionamento-vms.md`, `01-manual-implementacao/04-configuracao-base-vms-ubuntu.md`, `01-manual-implementacao/06-deploy-core.md`, `01-manual-implementacao/07-deploy-apps.md`, `01-manual-implementacao/08-stack-ia.md`, `03-guias-sustentacao/02-modificando-configuracoes-existentes.md`, `03-guias-sustentacao/07-cenarios-especificos-criacao-vms.md`, `04-manutencao-recuperacao/03-cicd-basico-ansible.md`, `04-manutencao-recuperacao/05-migrando-hardware-rede.md`, `05-referencia-rapida.md` |
| `ansible/playbooks/full-deploy.yml` | playbook | `04-manutencao-recuperacao/03-cicd-basico-ansible.md`, `04-manutencao-recuperacao/04-reconstruindo-infraestrutura.md`, `04-manutencao-recuperacao/05-migrando-hardware-rede.md` |
| `ansible/playbooks/setup-agents-volumes.yml` | playbook | `01-manual-implementacao/13-agentes-base.md` |
| `ansible/playbooks/setup-ai-keys.yml` | playbook | `01-manual-implementacao/08-stack-ia.md` |
| `ansible/playbooks/setup-ai-volumes.yml` | playbook | `01-manual-implementacao/08-stack-ia.md`, `01-manual-implementacao/13-agentes-base.md` |
| `ansible/playbooks/setup-base-ubuntu.yml` | playbook | `01-manual-implementacao/03-provisionamento-vms.md`, `01-manual-implementacao/04-configuracao-base-vms-ubuntu.md`, `01-manual-implementacao/06-deploy-core.md`, `04-manutencao-recuperacao/05-migrando-hardware-rede.md`, `05-referencia-rapida.md` |
| `ansible/playbooks/setup-cloud-stack-volumes.yml` | playbook | `01-manual-implementacao/11-fotos-arquivos.md` |
| `ansible/playbooks/setup-core-networking.yml` | playbook | `01-manual-implementacao/05-rede-segura.md`, `01-manual-implementacao/06-deploy-core.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md`, `03-guias-sustentacao/02-modificando-configuracoes-existentes.md`, `04-manutencao-recuperacao/03-cicd-basico-ansible.md` |
| `ansible/playbooks/setup-langfuse-volumes.yml` | playbook | `01-manual-implementacao/13-agentes-base.md` |
| `ansible/playbooks/setup-media-stack-volumes.yml` | playbook | `01-manual-implementacao/10-midia.md`, `03-guias-sustentacao/09-integrando-novos-servicos-stacks-existentes.md` |
| `ansible/playbooks/setup-monitoring-stack-volumes.yml` | playbook | `01-manual-implementacao/07-deploy-apps.md`, `01-manual-implementacao/09-painel-notificacoes.md`, `01-manual-implementacao/13-agentes-base.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md` |
| `ansible/playbooks/setup-n8n-volumes.yml` | playbook | `01-manual-implementacao/07-deploy-apps.md`, `01-manual-implementacao/09-painel-notificacoes.md` |
| `ansible/playbooks/setup-notes-volumes.yml` | playbook | `01-manual-implementacao/12-segundo-cerebro.md` |
| `ansible/playbooks/setup-photos-stack-volumes.yml` | playbook | `01-manual-implementacao/11-fotos-arquivos.md` |
| `ansible/playbooks/setup-productivity-automation-volumes.yml` | playbook | `01-manual-implementacao/07-deploy-apps.md` |
| `ansible/playbooks/setup-proxmox-host.yml` | playbook | `01-manual-implementacao/02-proxmox-ve-host.md`, `04-manutencao-recuperacao/05-migrando-hardware-rede.md` |
| `ansible/playbooks/vm-deploy.yml` | playbook | `01-manual-implementacao/03-provisionamento-vms.md`, `03-guias-sustentacao/06-gerenciando-recursos-vms.md`, `04-manutencao-recuperacao/05-migrando-hardware-rede.md` |
| `ansible/requirements.yml` | outro | `01-manual-implementacao/01-maquina-controle-ansible.md` |
| `ansible/roles/apps/desktop-environment/tasks/main.yml` | role-tasks | `01-manual-implementacao/03-provisionamento-vms.md` |
| `ansible/roles/apps/ml-tools/tasks/main.yml` | role-tasks | `01-manual-implementacao/08-stack-ia.md` |
| `ansible/roles/apps/ml-tools/templates/Dockerfile.ollama-vulkan.j2` | role-template | `01-manual-implementacao/08-stack-ia.md` |
| `ansible/roles/common/handlers/main.yml` | role-handlers | `01-manual-implementacao/04-configuracao-base-vms-ubuntu.md` |
| `ansible/roles/common/tasks/main.yml` | role-tasks | `01-manual-implementacao/04-configuracao-base-vms-ubuntu.md` |
| `ansible/roles/infra/alloy/defaults/main.yml` | role-defaults | `01-manual-implementacao/04-configuracao-base-vms-ubuntu.md` |
| `ansible/roles/infra/alloy/handlers/main.yml` | role-handlers | `01-manual-implementacao/04-configuracao-base-vms-ubuntu.md` |
| `ansible/roles/infra/alloy/tasks/main.yml` | role-tasks | `01-manual-implementacao/04-configuracao-base-vms-ubuntu.md` |
| `ansible/roles/infra/alloy/templates/config.alloy.j2` | role-template | `01-manual-implementacao/04-configuracao-base-vms-ubuntu.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md` |
| `ansible/roles/infra/authelia-config/defaults/main.yml` | role-defaults | `01-manual-implementacao/05-rede-segura.md` |
| `ansible/roles/infra/authelia-config/handlers/main.yml` | role-handlers | `01-manual-implementacao/05-rede-segura.md` |
| `ansible/roles/infra/authelia-config/tasks/main.yml` | role-tasks | `01-manual-implementacao/05-rede-segura.md` |
| `ansible/roles/infra/authelia-config/templates/configuration.yml.j2` | role-template | `01-manual-implementacao/05-rede-segura.md`, `01-manual-implementacao/09-painel-notificacoes.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md` |
| `ansible/roles/infra/authelia-config/templates/users_database.yml.j2` | role-template | `01-manual-implementacao/05-rede-segura.md` |
| `ansible/roles/infra/docker/defaults/main.yml` | role-defaults | `01-manual-implementacao/04-configuracao-base-vms-ubuntu.md` |
| `ansible/roles/infra/docker/handlers/main.yml` | role-handlers | `01-manual-implementacao/04-configuracao-base-vms-ubuntu.md` |
| `ansible/roles/infra/docker/tasks/main.yml` | role-tasks | `01-manual-implementacao/04-configuracao-base-vms-ubuntu.md` |
| `ansible/roles/infra/proxmox-host-config/handlers/main.yml` | role-handlers | `01-manual-implementacao/02-proxmox-ve-host.md` |
| `ansible/roles/infra/proxmox-host-config/tasks/main.yml` | role-tasks | `01-manual-implementacao/02-proxmox-ve-host.md` |
| `ansible/roles/infra/proxmox-host-config/templates/etc_exports.j2` | role-template | `01-manual-implementacao/02-proxmox-ve-host.md`, `03-guias-sustentacao/08-compartilhando-recursos-entre-vms.md` |
| `ansible/roles/infra/proxmox-vm/defaults/main.yml` | role-defaults | `01-manual-implementacao/03-provisionamento-vms.md` |
| `ansible/roles/infra/proxmox-vm/handlers/main.yml` | role-handlers | `01-manual-implementacao/03-provisionamento-vms.md` |
| `ansible/roles/infra/proxmox-vm/tasks/main.yml` | role-tasks | `01-manual-implementacao/03-provisionamento-vms.md` |
| `ansible/roles/infra/traefik-config/defaults/main.yml` | role-defaults | `01-manual-implementacao/05-rede-segura.md` |
| `ansible/roles/infra/traefik-config/handlers/main.yml` | role-handlers | `01-manual-implementacao/05-rede-segura.md` |
| `ansible/roles/infra/traefik-config/tasks/main.yml` | role-tasks | `01-manual-implementacao/05-rede-segura.md` |
| `ansible/roles/infra/traefik-config/templates/dynamic_rag_services.yml.j2` | role-template | `01-manual-implementacao/05-rede-segura.md`, `01-manual-implementacao/08-stack-ia.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md` |
| `ansible/roles/infra/traefik-config/templates/nextcloud_middleware.yml.j2` | role-template | `01-manual-implementacao/05-rede-segura.md` |
| `ansible/roles/infra/traefik-config/templates/security_headers.yml.j2` | role-template | `01-manual-implementacao/05-rede-segura.md` |
| `ansible/roles/infra/traefik-config/templates/traefik.yml.j2` | role-template | `01-manual-implementacao/05-rede-segura.md` |
| `ansible/roles/tools/ai-cli-tools/tasks/main.yml` | role-tasks | `03-guias-sustentacao/13-usando-geminicli.md` |
| `ansible/templates/agents/agentgateway.yaml.j2` | template | `01-manual-implementacao/13-agentes-base.md` |
| `ansible/templates/agents/ops-requirements.txt.j2` | template | `01-manual-implementacao/13-agentes-base.md` |
| `ansible/templates/backup-postgres.sh.j2` | template | `01-manual-implementacao/08-stack-ia.md`, `01-manual-implementacao/11-fotos-arquivos.md` |
| `ansible/templates/blackbox.yml.j2` | template | `01-manual-implementacao/07-deploy-apps.md`, `01-manual-implementacao/09-painel-notificacoes.md` |
| `ansible/templates/grafana/alerting/contact-points.yml.j2` | template | `01-manual-implementacao/07-deploy-apps.md`, `01-manual-implementacao/09-painel-notificacoes.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md` |
| `ansible/templates/grafana/alerting/policies.yml.j2` | template | `01-manual-implementacao/07-deploy-apps.md`, `01-manual-implementacao/09-painel-notificacoes.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md` |
| `ansible/templates/grafana/alerting/rules.yml.j2` | template | `01-manual-implementacao/07-deploy-apps.md`, `01-manual-implementacao/09-painel-notificacoes.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md` |
| `ansible/templates/homepage/docker.yaml.j2` | template | `01-manual-implementacao/07-deploy-apps.md`, `01-manual-implementacao/09-painel-notificacoes.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md` |
| `ansible/templates/homepage/services.yaml.j2` | template | `01-manual-implementacao/07-deploy-apps.md`, `01-manual-implementacao/09-painel-notificacoes.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md` |
| `ansible/templates/homepage/settings.yaml.j2` | template | `01-manual-implementacao/07-deploy-apps.md`, `01-manual-implementacao/09-painel-notificacoes.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md` |
| `ansible/templates/immich/immich.json.j2` | template | `01-manual-implementacao/11-fotos-arquivos.md` |
| `ansible/templates/litellm_config.yaml.j2` | template | `01-manual-implementacao/08-stack-ia.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md` |
| `ansible/templates/loki-local-config.yaml.j2` | template | `01-manual-implementacao/07-deploy-apps.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md` |
| `ansible/templates/nextcloud/10-homeserver.sh.j2` | template | `01-manual-implementacao/11-fotos-arquivos.md` |
| `ansible/templates/notes/Dockerfile.conversor.j2` | template | `01-manual-implementacao/12-segundo-cerebro.md` |
| `ansible/templates/notes/Dockerfile.escrita.j2` | template | `01-manual-implementacao/12-segundo-cerebro.md` |
| `ansible/templates/notes/Dockerfile.qmd.j2` | template | `01-manual-implementacao/12-segundo-cerebro.md` |
| `ansible/templates/notes/conversor.py` | template | `01-manual-implementacao/12-segundo-cerebro.md` |
| `ansible/templates/notes/index.yml.j2` | template | `01-manual-implementacao/12-segundo-cerebro.md` |
| `ansible/templates/notes/notes-documentos.service.j2` | template | `01-manual-implementacao/12-segundo-cerebro.md` |
| `ansible/templates/notes/notes-documentos.timer.j2` | template | `01-manual-implementacao/12-segundo-cerebro.md` |
| `ansible/templates/notes/notes-indice.service.j2` | template | `01-manual-implementacao/12-segundo-cerebro.md` |
| `ansible/templates/notes/notes-indice.timer.j2` | template | `01-manual-implementacao/12-segundo-cerebro.md` |
| `ansible/templates/portainer_stack_env.j2` | template | `01-manual-implementacao/07-deploy-apps.md`, `01-manual-implementacao/08-stack-ia.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md`, `03-guias-sustentacao/01-adicionando-novo-servico-docker.md` |
| `ansible/templates/prometheus.yml.j2` | template | `01-manual-implementacao/07-deploy-apps.md`, `01-manual-implementacao/09-painel-notificacoes.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md` |
| `ansible/templates/recyclarr.yml.j2` | template | `01-manual-implementacao/10-midia.md` |
| `docker/images/ops/.dockerignore` | outro | `01-manual-implementacao/13-agentes-base.md` |
| `docker/images/ops/Dockerfile` | outro | `01-manual-implementacao/13-agentes-base.md` |
| `docker/images/ops/ops/__init__.py` | script | `01-manual-implementacao/13-agentes-base.md` |
| `docker/images/ops/ops/auditoria.py` | script | `01-manual-implementacao/13-agentes-base.md` |
| `docker/images/ops/ops/config.py` | script | `01-manual-implementacao/13-agentes-base.md` |
| `docker/images/ops/ops/ferramentas.py` | script | `01-manual-implementacao/13-agentes-base.md` |
| `docker/images/ops/ops/politica.py` | script | `01-manual-implementacao/13-agentes-base.md` |
| `docker/images/ops/ops/portainer.py` | script | `01-manual-implementacao/13-agentes-base.md` |
| `docker/images/ops/ops/runner.py` | script | `01-manual-implementacao/13-agentes-base.md` |
| `docker/images/ops/ops/server.py` | script | `01-manual-implementacao/13-agentes-base.md` |
| `docker/stacks/.env.template` | env-template | `01-manual-implementacao/00-preparacao-planejamento.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md` |
| `docker/stacks/agents/docker-compose.yml` | stack | `01-manual-implementacao/13-agentes-base.md` |
| `docker/stacks/ai/docker-compose.yml` | stack | `01-manual-implementacao/08-stack-ia.md` |
| `docker/stacks/apps/docker-compose.yml` | stack | `01-manual-implementacao/07-deploy-apps.md`, `03-guias-sustentacao/05-passthrough-hardware-adicional.md`, `03-guias-sustentacao/09-integrando-novos-servicos-stacks-existentes.md` |
| `docker/stacks/cloud/docker-compose.yml` | stack | `01-manual-implementacao/11-fotos-arquivos.md` |
| `docker/stacks/core/docker-compose.yml` | stack | `01-manual-implementacao/05-rede-segura.md`, `01-manual-implementacao/06-deploy-core.md` |
| `docker/stacks/langfuse/docker-compose.yml` | stack | `01-manual-implementacao/13-agentes-base.md` |
| `docker/stacks/media/docker-compose.yml` | stack | `01-manual-implementacao/10-midia.md` |
| `docker/stacks/notes/docker-compose.yml` | stack | `01-manual-implementacao/12-segundo-cerebro.md` |
| `docker/stacks/photos/docker-compose.yml` | stack | `01-manual-implementacao/11-fotos-arquivos.md` |
| `scripts/bootstrap.sh` | script | `01-manual-implementacao/01-maquina-controle-ansible.md`, `04-manutencao-recuperacao/04-reconstruindo-infraestrutura.md` |
| `scripts/notify.sh` | script | `01-manual-implementacao/09-painel-notificacoes.md`, `02-visao-geral-arquitetura/10-indice-integracoes.md`, `04-manutencao-recuperacao/02-backup-restore-estrategia.md` |
| `scripts/restore.sh` | script | `04-manutencao-recuperacao/03-cicd-basico-ansible.md`, `04-manutencao-recuperacao/04-reconstruindo-infraestrutura.md`, `04-manutencao-recuperacao/05-migrando-hardware-rede.md` |
| `scripts/validation/check_nfs_permissions.sh` | script | `04-manutencao-recuperacao/01-rotinas-manutencao.md` |
| `scripts/validation/check_yaml_integrity.py` | script | `04-manutencao-recuperacao/01-rotinas-manutencao.md` |
| `scripts/validation/validate_infrastructure.sh` | script | `04-manutencao-recuperacao/01-rotinas-manutencao.md` |
