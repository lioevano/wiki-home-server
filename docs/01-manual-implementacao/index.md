# 🚀 Manual de Implementação Passo a Passo

E aqui começa a jornada! Este é o guia completo para a implementação da arquitetura que elaborei para o meu servidor doméstico, construído do zero. Meu objetivo com este projeto é ter uma infraestrutura duradoura, que possa evoluir mesmo com trocas de hardware, e que resolva problemas de longo prazo de forma elegante.

Se você tiver dúvidas sobre alguma escolha ou quiser explorar alternativas, tentarei ao máximo linkar para explicações mais detalhadas e opções para cada aplicação. Lembre-se: se alguma aplicação não for do seu agrado, você pode optar por não instalá-la, mas preste atenção às possíveis integrações com outros serviços.

## Objetivo

O objetivo deste manual é levá-lo, passo a passo, desde a preparação inicial do hardware e software até o deploy e configuração de todos os serviços essenciais. Ao final desta seção, você terá um servidor doméstico funcional, seguro e altamente automatizado.

!!! important "Siga a Ordem!"
    É crucial seguir os passos apresentados neste manual **na ordem exata** em que são listados. Muitas etapas dependem de configurações realizadas anteriormente. Pular passos ou alterar a ordem pode levar a problemas de configuração e instabilidade.

## Adaptações Necessárias

Ao longo deste manual, você encontrará placeholders e exemplos de valores (IPs, domínios, senhas, caminhos). **Você DEVE substituí-los pelos seus próprios valores.**

*   **Endereços IP:** Adapte para a sua sub-rede local (e.g., `192.168.X.Y`).
*   **Nomes de Domínio:** Use o seu domínio registrado (e.g., `meuhomelab.com`).
*   **Senhas e Tokens:** Gere senhas fortes e únicas. Segredos serão gerenciados pelo Ansible Vault.
*   **Caminhos de Arquivo:** Verifique se os caminhos correspondem à sua estrutura e preferências.

## Estrutura do Manual de Implementação

Este manual está dividido nas seguintes seções, que devem ser seguidas sequencialmente:

1.  **[Preparação e Planejamento](00-preparacao-planejamento.md):**
    Requisitos de hardware/software, estrutura do projeto Git e considerações iniciais.
2.  **[Configuração da Máquina de Controle Ansible](01-maquina-controle-ansible.md):**
    Preparando o ambiente de onde você gerenciará toda a infraestrutura.
3.  **[Instalação e Configuração Base do Proxmox VE](02-proxmox-ve-host.md):**
    Instalando o hypervisor, configurando ZFS e o servidor NFS.
4.  **[Provisionamento das Máquinas Virtuais (VMs) com Ansible](03-provisionamento-vms.md):**
    Criando as VMs `core-services-vm` e `ai-desktop-vm` de forma automatizada.
5.  **[Configuração Base das VMs Ubuntu](04-configuracao-base-vms-ubuntu.md):**
    Configurações essenciais, Docker, Portainer e cliente NFS nas VMs.
6.  **[Implementação da Rede Segura](05-rede-segura.md):**
    Deploy de Traefik, Cloudflare Tunnel e Authelia para acesso externo seguro.
7.  **[Gerenciamento e Deploy de Stacks Docker com Portainer](06-deploy-portainer-geral.md):**
    Processo geral para implantar aplicações Docker usando Portainer e volumes NFS.
8.  **[Stack de Inteligência Artificial (LLM/RAG com Ollama)](07-stack-ia-rag.md):**
    Configurando a `ai-desktop-vm` para rodar modelos de linguagem e aplicações RAG.
9.  **[Stack de Mídia (Plex/Jellyfin, *arrs)](08-stack-midia.md):**
    Deploy dos seus serviços de mídia.
10. **[Stack de Produtividade e Automação (Nextcloud, Home Assistant)](09-stack-produtividade-automacao.md):**
    Implementando Nextcloud para arquivos e Home Assistant para automação residencial.
11. **[Stack de Monitoramento (Glances, Prometheus, Grafana, Loki)](10-stack-monitoramento.md):**
    Configurando ferramentas para monitorar a saúde e performance do seu servidor.

Para começar, avance para a [Preparação e Planejamento](00-preparacao-planejamento.md).