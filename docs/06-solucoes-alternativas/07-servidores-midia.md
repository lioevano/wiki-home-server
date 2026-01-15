# Alternativas para Servidores de Mídia (Plex, Jellyfin, Emby, Kodi)

Organizar, transmitir e acessar sua coleção pessoal de filmes, séries de TV, músicas e fotos é um dos casos de uso mais populares e gratificantes para um servidor doméstico. Para esta funcionalidade, um **software de servidor de mídia** é essencial.

No [Manual de Implementação (Seção 8)](../01-manual-implementacao/08-stack-midia.md), focamos em **Plex** e **Jellyfin** como as principais opções para rodar em containers Docker na nossa `core-services-vm`. Ambos são extremamente capazes, mas possuem filosofias, modelos de licenciamento e conjuntos de recursos que podem agradar a diferentes tipos de usuários. Esta seção explora essas duas opções mais a fundo e apresenta algumas alternativas.

## 1. Plex (Opção Principal no Guia)

*   **Tipo:** Servidor de mídia proprietário, com um modelo "freemium". O software do servidor principal é gratuito para uso, mas funcionalidades avançadas e alguns aplicativos cliente requerem uma subscrição **Plex Pass** (mensal, anual ou vitalícia).
*   **Prós:**
    *   **Interface de Usuário Extremamente Polida e Amigável:** Tanto a interface web do servidor quanto os aplicativos cliente são geralmente considerados muito bem desenhados, intuitivos e fáceis de usar, mesmo para usuários menos técnicos.
    *   **Ampla Compatibilidade de Clientes (Apps):** Este é um dos maiores pontos fortes do Plex. Aplicativos cliente Plex estão disponíveis para praticamente **todas as plataformas imagináveis**:
        *   Smart TVs (Samsung, LG, Sony, Vizio, etc.)
        *   Dispositivos de Streaming (Roku, Amazon Fire TV, Apple TV, Chromecast com Google TV, NVIDIA Shield)
        *   Consoles de Jogos (PlayStation, Xbox)
        *   Dispositivos Móveis (Android, iOS)
        *   Desktops (Windows, macOS, Linux via Plex HTPC ou web app)
        *   Navegadores Web.
    *   **Facilidade de Configuração Inicial:** Geralmente muito simples de instalar (especialmente via Docker), configurar e começar a adicionar suas bibliotecas de mídia.
    *   **Plex Relay e Acesso Remoto Simplificado:**
        *   O Plex oferece um serviço de "Relay" que permite que você (e usuários com quem você compartilha sua biblioteca) acesse seu servidor Plex remotamente, mesmo que você não configure encaminhamento de porta ou um proxy reverso complexo. A qualidade do stream via relay pode ser limitada na versão gratuita (e.g., a 1-2 Mbps), mas o Plex Pass geralmente permite conexões diretas de melhor qualidade se sua rede estiver configurada corretamente.
        *   O acesso remoto "direto" (sem relay) pode ser configurado manualmente (port forwarding) ou, como em nossa arquitetura, você pode expor o Plex através de um túnel ou proxy reverso (embora a integração do Plex com proxies reversos possa, às vezes, ser um pouco temperamental para todos os clientes).
    *   **Excelente Descoberta de Conteúdo e Metadados:** Plex é muito bom em buscar automaticamente metadados ricos para seus filmes e séries (capas, resumos, elenco, classificações, trailers, etc.) de várias fontes online.
    *   **Funcionalidades do Plex Pass (Pago):**
        *   **Hardware Transcoding:** Permite usar a aceleração de hardware da sua CPU (Intel Quick Sync Video - QSV) ou GPU (NVIDIA NVENC/NVDEC, e algum suporte para AMD) para transcodificação de vídeo, o que alivia a carga na CPU e permite mais streams simultâneos.
        *   **Mobile Sync:** Permite baixar mídia para seus dispositivos móveis para visualização offline.
        *   **Live TV & DVR:** Se você tiver um sintonizador de TV compatível e uma antena, pode assistir e gravar TV ao vivo.
        *   **Múltiplos Usuários com Controles Parentais Detalhados (Plex Home).**
        *   **Lyrics para Músicas, Integração com TIDAL, Plexamp (um excelente player de música dedicado).**
        *   Trailers e extras para filmes.
        *   Downloads de legendas.
*   **Contras:**
    *   **Software Proprietário e Parcialmente Centralizado:** Embora o software do Plex Media Server rode localmente no seu servidor, a autenticação dos usuários e algumas funcionalidades de descoberta e acesso remoto dependem dos servidores da Plex. Se os servidores da Plex tiverem uma interrupção, o login e o acesso remoto podem ser afetados, embora o acesso local à sua LAN geralmente continue funcionando.
    *   **Coleta de Dados de Uso (com Opção de Opt-out Parcial):** Plex coleta dados de uso anonimizados. Você pode gerenciar algumas dessas configurações de privacidade na sua conta Plex.
    *   **Hardware Transcoding Geralmente Requer Plex Pass:** As funcionalidades de hardware transcoding mais eficazes e para mais plataformas estão bloqueadas atrás da subscrição Plex Pass.
    *   **Menos Customizável e Aberto que Alternativas como Jellyfin.**
    *   **Segurança de Compartilhamento:** Embora o compartilhamento com amigos seja uma feature, é importante estar ciente das implicações de segurança e da carga no seu servidor/internet se muitos streams remotos estiverem ativos.

## 2. Jellyfin (Opção Principal no Guia, Alternativa Open Source)

*   **Tipo:** Servidor de mídia **totalmente open-source e gratuito**, que é um fork comunitário do Emby (após o Emby ter se tornado mais proprietário).
*   **Prós:**
    *   **100% Open Source e Gratuito (FOSS):** Todas as funcionalidades, incluindo **hardware transcoding** (se seu hardware e drivers Linux suportarem), são completamente gratuitas. Não há nenhuma feature paga ou subscrição premium.
    *   **Foco na Privacidade e Controle Total do Usuário:** Nenhum servidor central de terceiros é necessário para autenticação ou funcionamento básico (além de fontes de metadados opcionais). Você tem controle total sobre seus dados e como seu servidor opera. Nenhuma coleta de dados para terceiros.
    *   **Hardware Transcoding Robusto e Gratuito:** Excelente suporte para hardware transcoding via:
        *   **VAAPI** (Video Acceleration API) para GPUs Intel (Quick Sync Video - QSV) e AMD no Linux. (Nossa iGPU Vega do Ryzen 5 5600G usa VAAPI).
        *   **NVENC/NVDEC** para GPUs NVIDIA no Linux.
        *   VideoToolbox no macOS, OpenMAX em algumas plataformas ARM.
    *   **Comunidade Ativa e Desenvolvimento Rápido:** Jellyfin tem uma comunidade de desenvolvedores e usuários muito engajada, e o projeto está evoluindo rapidamente com novas features e melhorias.
    *   **Altamente Customizável:** Muitas opções de configuração e um sistema de plugins para estender funcionalidades (e.g., autenticação LDAP, Trakt.tv scrobbling, downloads de legendas).
    *   **Múltiplos Usuários, Controles Parentais e Sincronização (SyncPlay):** Todas estas funcionalidades são nativas e gratuitas. SyncPlay permite assistir mídia sincronizadamente com amigos/familiares remotamente.
*   **Contras:**
    *   **Interface de Usuário e Experiência do Cliente:** Embora tenha melhorado drasticamente e seja muito funcional, a interface web e a experiência em alguns aplicativos cliente podem não ser percebidas como tão "polidas" ou consistentes em todas as plataformas quanto as do Plex para alguns usuários. Isso é subjetivo e está em constante melhoria.
    *   **Compatibilidade de Aplicativos Cliente:** A gama de aplicativos cliente para Jellyfin é boa e está crescendo rapidamente:
        *   Web (excelente), Android (app oficial), iOS (app oficial), Android TV (app oficial), Amazon Fire TV.
        *   Roku (app oficial).
        *   Kodi (via plugin Jellyfin for Kodi, que é excelente).
        *   Clientes desktop (Jellyfin Media Player).
        *   No entanto, a disponibilidade de apps nativos em algumas plataformas de Smart TV mais antigas ou de nicho pode não ser tão universal quanto a do Plex. Muitos usam um dispositivo de streaming dedicado (Fire Stick, Chromecast com Google TV, NVIDIA Shield) com o app Jellyfin.
    *   **Configuração Inicial de Metadados:** Embora o Jellyfin use provedores de metadados padrão (como The Movie Database, TheTVDB, Open Movie Database), às vezes pode exigir um pouco mais de ajuste fino na nomeação de arquivos ou nas configurações dos "scrapers" para obter metadados perfeitos, em comparação com o Plex que é muitas vezes mais "mágico" nisso.
    *   **Acesso Remoto Requer Configuração Manual:** Jellyfin não possui um serviço de "relay" embutido e fácil como o Plex Relay. Para acesso externo, você precisa configurar seu próprio método, que em nossa arquitetura é feito de forma ideal através do **Traefik como proxy reverso** (expondo `https://jellyfin.{{ base_domain }}`), protegido por Authelia. Uma VPN para sua LAN também é uma opção.

## 3. Emby

*   **Tipo:** Servidor de mídia proprietário, do qual o Jellyfin foi originalmente forkado. Emby também segue um modelo "freemium", com um servidor base que pode ser usado gratuitamente e uma subscrição **Emby Premiere** para desbloquear funcionalidades avançadas.
*   **Prós:**
    *   **Interface de Usuário Madura e Boas Aplicações Cliente:** Em termos de polimento da UI e disponibilidade de aplicativos cliente em várias plataformas, o Emby é bastante comparável ao Plex.
    *   **Boas Funcionalidades de Gerenciamento de Mídia e Metadados.**
    *   **Hardware Transcoding e Live TV/DVR (com Emby Premiere):** Similar ao Plex Pass, a subscrição Emby Premiere desbloqueia hardware transcoding, funcionalidades de TV Ao Vivo e DVR, mobile sync, e outras features premium.
*   **Contras:**
    *   **Software Proprietário com Componentes Core Open Source (Histórico):** Embora o servidor Emby principal tenha tido partes do seu código abertas no passado, a direção do projeto se tornou mais focada em seus componentes proprietários e no serviço Premiere. Muitas das funcionalidades mais desejadas e os aplicativos cliente mais polidos são proprietários e/ou requerem Premiere.
    *   **Mudança para Modelo Mais Fechado:** A decisão do Emby de fechar o código de partes importantes do servidor e focar no modelo de subscrição foi a principal razão pela qual a comunidade forkou o projeto para criar o Jellyfin (que se comprometeu a permanecer 100% FOSS). Isso pode ser uma preocupação para usuários que priorizam soluções totalmente open-source e controladas pela comunidade.
    *   **Custo da Subscrição Emby Premiere:** Similar ao Plex Pass, as funcionalidades chave que muitos usuários desejam (especialmente hardware transcoding eficiente) estão atrás de um paywall.

## 4. Kodi (com Plugins e Estratégias para Acesso Remoto/Compartilhamento)

*   **Tipo:** Kodi (anteriormente XBMC) é primariamente um **media *player*** e um centro de entretenimento open-source extremamente poderoso, flexível e customizável. Ele **não é um "servidor" de mídia** no mesmo sentido cliente-servidor que Plex, Jellyfin ou Emby.
*   **Como Funciona para uma Experiência Multi-Dispositivo ou "Servidor-Like":**
    *   Kodi em si é focado na **reprodução local de mídia** (a partir de arquivos armazenados localmente no dispositivo onde o Kodi está rodando, ou de compartilhamentos de rede como SMB/NFS).
    *   Para criar uma experiência que se assemelhe a um servidor para múltiplos dispositivos, você geralmente configura uma instância "principal" do Kodi em um dispositivo central (e.g., um HTPC - Home Theater PC, ou uma NVIDIA Shield) e então:
        *   **Compartilhamento de Biblioteca via UPnP/DLNA:** A instância principal do Kodi pode atuar como um servidor UPnP/DLNA, permitindo que outros dispositivos e players compatíveis na sua rede local acessem e reproduzam a mídia da biblioteca do Kodi.
        *   **Sincronização de Biblioteca e Estado de Visualização com um Banco de Dados Compartilhado (MySQL/MariaDB):** Para ter múltiplas instâncias Kodi (em diferentes cômodos, por exemplo) compartilhando uma única biblioteca centralizada, o estado de "assistido/não assistido", e o progresso da reprodução, você pode configurar o Kodi para usar um backend de banco de dados MySQL ou MariaDB compartilhado. Isso requer um setup mais avançado.
        *   **Plugins de Acesso Remoto ou "Servidor":** Existem alguns add-ons (plugins) para Kodi que tentam fornecer funcionalidades de servidor ou acesso remoto à sua biblioteca Kodi de fora da sua rede, mas estes são geralmente menos robustos, menos seguros e menos fáceis de usar do que soluções de servidor de mídia dedicadas como Plex ou Jellyfin.
*   **Prós do Kodi:**
    *   **Extremamente Customizável:** A aparência (via skins) e as funcionalidades (via um vasto ecossistema de add-ons para streaming de serviços online, legendas, utilitários, etc.) do Kodi são imensamente customizáveis.
    *   **Excelente Qualidade de Reprodução e Suporte a Formatos:** Kodi é renomado por sua capacidade de reproduzir uma vasta gama de formatos de áudio e vídeo com alta qualidade, e oferece muitas opções de ajuste de áudio/vídeo.
    *   **Totalmente Open Source e Gratuito.**
    *   **Roda em Muitas Plataformas:** Disponível para Windows, macOS, Linux, Android, iOS (com jailbreak/sideloading), Raspberry Pi, e muitos dispositivos de streaming.
*   **Contras do Kodi (quando se tenta usá-lo como uma solução de "servidor" de mídia para múltiplos clientes remotos):**
    *   **Não é um Servidor Dedicado por Design:** Gerenciar acesso para múltiplos usuários, realizar transcodificação em tempo real para clientes remotos com diferentes capacidades de reprodução, e fornecer acesso fácil via interfaces web ou aplicativos móveis dedicados não são os pontos fortes nativos do Kodi.
    *   **Configuração Mais Complexa para uma Experiência Multi-Dispositivo Coesa:** Sincronizar bibliotecas e o estado de visualização entre múltiplas instâncias Kodi requer um setup adicional significativo (e.g., configurar e manter um servidor MySQL/MariaDB).
    *   **Transcodificação Limitada ou Inexistente:** A transcodificação de mídia em tempo real para se adequar à largura de banda ou às capacidades do dispositivo cliente não é uma feature central do Kodi como é no Plex ou Jellyfin.
*   **Quando Considerar Kodi em seu Homelab:**
    *   Se seu foco principal é ter um **media center local altamente customizável e poderoso** para um ou poucos dispositivos de reprodução principais (e.g., sua TV da sala, um HTPC).
    *   Se você está disposto a investir tempo na configuração do compartilhamento/sincronização de biblioteca (via UPnP ou MySQL) se precisar de acesso em múltiplos dispositivos na sua LAN.
    *   Kodi pode ser usado **em conjunto com Jellyfin ou Plex**:
        *   Muitas pessoas usam Kodi como o **frontend (player)** em seus dispositivos de mídia (como uma NVIDIA Shield ou Raspberry Pi) e instalam o **plugin Jellyfin for Kodi** ou o **PlexKodiConnect (PKC)** add-on. Isso combina a excelente interface de reprodução e customização do Kodi com o poderoso backend de gerenciamento de servidor do Jellyfin ou Plex.

## 5. Outras Soluções Focadas em Tipos Específicos de Mídia

*   **Para Música:**
    *   **Subsonic (e seus forks open-source como Airsonic, Airsonic-Advanced, Navidrome):** Excelentes servidores de streaming de música auto-hospedados. Eles focam em grandes coleções de música, oferecem interfaces web para navegação e reprodução, e suportam uma variedade de aplicativos cliente móveis (compatíveis com a API Subsonic). Navidrome é particularmente popular por ser moderno, leve e fácil de usar.
    *   **Plexamp (do Plex):** Se você usa Plex e tem Plex Pass, o Plexamp é um aplicativo de música dedicado (desktop e móvel) que oferece uma experiência de audição de música excelente, com funcionalidades como downloads, rádios baseadas no seu humor ou biblioteca, e uma interface muito bonita.
    *   **LMS (Logitech Media Server) / Squeezebox Server:** Uma plataforma de áudio multi-room muito antiga, mas ainda amada por audiófilos, totalmente open-source, com um vasto ecossistema de plugins e suporte para muitos players de hardware e software.
*   **Para Fotos e Vídeos Pessoais (Alternativas ao Google Photos/Apple Photos):**
    *   **PhotoPrism:** Uma aplicação de gerenciamento de fotos auto-hospedada, baseada em servidor, que usa IA para marcação automática, reconhecimento de pessoas e objetos, e visualização de mapas.
    *   **Immich:** Uma solução de backup e auto-hospedagem para fotos e vídeos de celulares, com uma interface muito similar ao Google Photos, e funcionalidades como álbuns, compartilhamento, e busca por IA. Está em desenvolvimento ativo e ganhando muita popularidade.
    *   **Nextcloud Memories:** Um app dentro do Nextcloud que melhora a visualização e organização de fotos armazenadas no seu Nextcloud.

## Conclusão da Escolha do Servidor de Mídia para Este Guia

Para a arquitetura de servidor doméstico detalhada neste guia, apresentar **Plex e Jellyfin** como as opções principais no `docker-compose.yml` da stack de mídia oferece uma boa flexibilidade inicial:

*   **Jellyfin** é a escolha ideal para usuários que valorizam o **software 100% open-source, controle total sobre seus dados, privacidade absoluta, e acesso a todas as funcionalidades (incluindo hardware transcoding robusto) sem nenhum custo adicional.** Sua integração com o nosso setup Traefik/Authelia é direta e funciona muito bem.
*   **Plex** é uma excelente opção para usuários que buscam a **interface de usuário mais polida e reconhecida, a mais ampla compatibilidade de aplicativos cliente "out-of-the-box" em virtualmente qualquer dispositivo, e a facilidade do Plex Relay para compartilhamento simples com amigos e familiares (mesmo que com algumas limitações na versão gratuita do relay).** O trade-off é o software proprietário, a dependência parcial de servidores Plex para algumas funcionalidades, e o fato de que features chave como hardware transcoding eficiente geralmente requerem a subscrição Plex Pass.

Você pode optar por rodar apenas um deles, ou até mesmo ambos (se os recursos do seu servidor permitirem e suas bibliotecas de mídia estiverem organizadas de forma que ambos possam acessá-las sem conflitos), e então escolher qual servidor de mídia usar dependendo do dispositivo cliente que você está usando ou da situação específica.

A escolha final do servidor de mídia dependerá muito das suas prioridades pessoais em termos de filosofia (open-source vs. proprietário), facilidade de uso percebida, o ecossistema de dispositivos cliente que você já possui, e as funcionalidades específicas que são mais importantes para você.