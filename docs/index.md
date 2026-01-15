# Guia do Servidor do Léo Ivan

## 🤔 Por que? Pra que?
Esta wiki é o que eu fiz para não me perder quando resolvi elaborar uma grande arquitetura doméstica.  
Todo mundo que olha a primeira vista sempre me pergunta a mesma coisa: Beleza, muito legal as mil tecnologias desconhecidas que usou, **mas PRA QUE?**  

E aqui vai uma explicação amigável do grande motivo por trás de tudo:

### 😄 Utilidades Legais
1. **🎬 Streaming tá caro:** Um dos propósitos principais é um servidor de streaming de mídia, onde você poderá assistir filmes, vídeos, séries, ler livros, ouvir músicas, tudo de forma automatizada, sem precisar ficar procurando arquivos para baixar, e acessível de qualquer dispositivo através do meu domínio.
2. **🤖 IA é muito legal, mas tá caro também**: Muitas ferramentas de IA são extremamente poderosas, mas pouco práticas pro uso amplo, aqui a ideia é integrar o máximo da esperteza das máquinas no máximo de atividades que eu conseguir, priorizando rodar os modelos localmente. Dentre as integrações existentes temos integração com Obsidian, para prompts baseados em arquivos que eu mesmo escrevi, integração com o File System do computador, podendo fazer prompt baseado em diretórios inteiros, grupos de arquivos de diversos formatos.
3. **📁 Controle de Arquivos**: Aqui é um ponto sobre eu tentar diminuir a dependência de hardwares específicos, seja o computador ou o celular, todos os meus documentos, fotos, vídeos e projetos serão salvos de forma centralizada, sendo acessados via NextCloud, ferramenta semelhante ao Google Drive, que garante que em eventual falha de qualquer dispositivo eu sempre terei acesso a todos os meus arquivos de qualquer lugar.
4. **👨‍💻 Acesso Irrestrito**: Muitas vezes quando vou trabalhar em algum projeto, seja um código, um texto ou qualquer outra forma de criação de arquivos, eu só me sinto confortável no setup que eu montei no meu próprio computador, a ideia aqui é ter acesso a minha estrutura via browser de qualquer lugar, tendo os acessos eu serei capaz de fazer qualquer coisa que eu faria no meu computador pessoal de qualquer computador.
5. **🧠 Berço de Ideias**: Diversos templates e funcionalidades são visando uma infraestrutura fácil de criar e implementar qualquer ideia que eu possa ter. Quero aprender uma ferramenta nova? Em poucos passos eu tenho um ambiente pronto para explorar e implementar novas ideias, diminuindo os impactos de não conseguir terminar tarefas complexas que o TDAH põe na vida da pessoa que vos fala. Em síntese, é ter trabalho hoje (implementando tudo) para não ter trabalho nunca mais ~~espero~~.

### 🖥️ Tecnologias Legais
1. **🔒 Tudo seguro**: Existem diversas camadas de segurança e autenticação para cada serviço, sendo possível a criação de diferentes usuários para diferentes ambientes e acessos dentro da arquitetura, por exemplo a criação de um usuário de trabalho que terá apenas acessos a ferramentas de trabalho.
2. **⚙️ Infraestrutura como Código**: Todo o projeto é desenvolvido com a ideia de ser modular e automatizado, a menor quantidade de passos humanos é tomada, criando um ambiente facilmente replicavel e de fácil manutenção, sendo possível migrar tudo para um novo computador ou replicar para outra pessoa em um piscar de olhos.
3. **👀 Alto Monitoramento**: Com uma stack específica para isso, o monitoramento de todo o sistema é fácil e altamente responsivo, podendo acompanhar e resolver tranquilamente.

E, por fim: aprender diversas coisas, cada passo dessa jornada foram horas de estudo de coisas que eu nunca tinha tido contato, além de ser um facilitador da minha vida, esse projeto também foi uma grande escola, espero que aproveitem algo!

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