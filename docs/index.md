# Bem-vindo ao Guia do Meu Servidor Doméstico!

Esta wiki é o que eu fiz para não me perder quando resolvi elaborar uma grande arquitetura doméstica, pensando em longevidade, uma estrutura de diretórios, softwares, redes e tudo mais que pudesse perdurar mesmo após a troca de componentes do meu setup atual.

## Pra isso, escolhi essas tecnologias poderosas e open-source:
*   **Proxmox VE:** Para virtualização de servidores.
*   **Ansible:** Para automação da configuração (IaC).
*   **Docker & Portainer:** Para gerenciamento eficiente de containers.
*   **ZFS:** Para um sistema de arquivos resiliente e armazenamento de dados.
*   **Cloudflare Tunnel & Traefik:** Para acesso externo seguro e simplificado.
*   **Authelia:** Para autenticação forte de dois fatores (2FA).

## Como Usar Essa Wiki

A wiki está organizada nas seguintes seções:

1.  **[🚀 Manual de Implementação](01-manual-implementacao/index.md):**
    Guia passo a passo para construir a infraestrutura do zero.
2.  **[💡 Visão Geral da Arquitetura](02-visao-geral-arquitetura/index.md):**
    Entenda como todos os componentes se conectam e funcionam em conjunto.
3.  **[🛠️ Guias de Sustentação](03-guias-sustentacao/index.md):**
    Como modificar, expandir e solucionar problemas na sua infraestrutura.
4.  **[⚙️ Manutenção e Recuperação](04-manutencao-recuperacao/index.md):**
    Rotinas essenciais de manutenção, estratégias de backup e recuperação de desastres.

!!! tip "Comece Aqui!"
    Se você está iniciando, siga o [Manual de Implementação](01-manual-implementacao/index.md) na ordem apresentada.

---
*Última revisão: {{ git_revision_date_localized }}*