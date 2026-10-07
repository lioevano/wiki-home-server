---
description: "Wiki do servidor doméstico do Léo Ivan: Proxmox, Ansible, Docker, ZFS, Cloudflare Tunnel, Traefik e Authelia, com o mapa das seções."
---

# Guia do Servidor do Léo Ivan

Esta wiki é o que eu fiz para não me perder quando resolvi elaborar uma grande arquitetura doméstica, pensando em longevidade, uma estrutura que pudesse perdurar mesmo após a troca de componentes do meu computador atual e resolver problemas de longo prazo.

## Pra isso, escolhi essas tecnologias poderosas e open-source:
*   **[Proxmox VE](05-referencia-rapida.md):** Para virtualização de servidores.
*   **[Ansible](05-referencia-rapida.md):** Para automação da configuração (IaC).
*   **[Docker & Portainer](05-referencia-rapida.md):** Para gerenciamento eficiente de containers.
*   **[ZFS](05-referencia-rapida.md):** Para um sistema de arquivos resiliente e armazenamento de dados.
*   **[Cloudflare Tunnel & Traefik](05-referencia-rapida.md):** Para acesso externo seguro e simplificado.
*   **[Authelia](05-referencia-rapida.md):** Para autenticação forte de dois fatores (2FA).

## Como Usar Essa Wiki

A wiki está organizada nas seguintes seções:

1.  **[🚀 Implementação](01-manual-implementacao/index.md):**
    Guia passo a passo para construir a infraestrutura do zero.
2.  **[💡 Arquitetura](02-visao-geral-arquitetura/index.md):**
    Entenda como todos os componentes se conectam e funcionam em conjunto.
3.  **[🛠️ Sustentação](03-guias-sustentacao/index.md):**
    Como modificar, expandir e solucionar problemas na sua infraestrutura.
4.  **[⚙️ Manutenção](04-manutencao-recuperacao/index.md):**
    Rotinas essenciais de manutenção e estratégias de backup.
5.  **[📎 Referência](05-referencia-rapida.md):**
    Resumo rápido de tecnologias, alternativas e comandos úteis.

!!! tip "Comece Aqui!"
    Se você está iniciando, siga o [Manual de Implementação](01-manual-implementacao/index.md) na ordem apresentada.

---
*Última revisão: {{ git_revision_date_localized }}*