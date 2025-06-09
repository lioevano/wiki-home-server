# Guia do Servidor do Léo Ivan

Esta wiki é o que eu fiz para não me perder quando resolvi elaborar uma grande arquitetura doméstica, pensando em longevidade, uma estrutura que pudesse perdurar mesmo após a troca de componentes do meu computador atual e resolver problemas de longo prazo.

## Pra isso, escolhi essas tecnologias poderosas e open-source:
*   **[Proxmox VE](05-guia-estudos/01-aprofundamento-proxmox-ve.md):** Para virtualização de servidores.
*   **[Ansible](05-guia-estudos/03-aprofundamento-ansible.md):** Para automação da configuração (IaC).
*   **[Docker & Portainer](05-guia-estudos/04-aprofundamento-docker-networking.md):** Para gerenciamento eficiente de containers.
*   **[ZFS](05-guia-estudos/02-aprofundamento-zfs.md):** Para um sistema de arquivos resiliente e armazenamento de dados.
*   **[Cloudflare Tunnel & Traefik](05-guia-estudos/05-aprofundamento-traefik-authelia.md):** Para acesso externo seguro e simplificado.
*   **[Authelia](05-guia-estudos/05-aprofundamento-traefik-authelia.md):** Para autenticação forte de dois fatores (2FA).

## Como Usar Essa Wiki

A wiki está organizada nas seguintes seções:

1.  **[🚀 Implementação](01-manual-implementacao/index.md):**
    Guia passo a passo para construir a infraestrutura do zero.
2.  **[💡 Arquitetura](02-visao-geral-arquitetura/index.md):**
    Entenda como todos os componentes se conectam e funcionam em conjunto.
3.  **[🛠️ Sustentação](03-guias-sustentacao/index.md):**
    Como modificar, expandir e solucionar problemas na sua infraestrutura.
4.  **[⚙️ Manutenção](04-manutencao-recuperacao/index.md):**
    Rotinas essenciais de manutenção, estratégias de backup e recuperação de desastres.
5. **[📚 Guia de Estudos](05-guia-estudos/index.md):**
    Um compilado de guias sobre as principais ferramentas usadas para dar autonomia em tomadas de decisão.
6. **[🔄 Soluções Alternativas](06-solucoes-alternativas/index.md):**
    Um guia de escolhas alternativas às ferramentas que escolhi com prós e contras de cada uma.

!!! tip "Comece Aqui!"
    Se você está iniciando, siga o [Manual de Implementação](01-manual-implementacao/index.md) na ordem apresentada.

---
*Última revisão: {{ git_revision_date_localized }}*