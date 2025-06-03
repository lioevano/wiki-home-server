# Alternativas para Servidores de Mídia

Para organizar, transmitir e acessar sua coleção de filmes, séries, músicas e fotos, um servidor de mídia é essencial. Neste guia, mencionamos **Plex** e **Jellyfin** como as principais opções para rodar em nossa `core-services-vm`. Ambos são poderosos, mas têm filosofias e conjuntos de recursos ligeiramente diferentes.

## 1. Plex (Mencionado em Nosso Guia)

*   **Tipo:** Servidor de mídia proprietário (com componentes de servidor gratuitos e funcionalidades Plex Pass pagas).
*   **Prós:**
    *   **Interface de Usuário Polida e Amigável:** Considerada uma das melhores e mais intuitivas.
    *   **Ampla Compatibilidade de Clientes:** Aplicativos Plex estão disponíveis para praticamente todas as plataformas (Smart TVs, consoles de jogos, dispositivos móveis, desktops, web).
    *   **Fácil Configuração Inicial:** Geralmente muito simples de configurar e começar a adicionar bibliotecas.
    *   **Plex Relay:** Permite acesso remoto aos seus amigos e familiares (ou a você mesmo) sem necessidade de configurar encaminhamento de porta complexo, mesmo que a qualidade possa ser limitada na versão gratuita do relay.
    *   **Descoberta de Conteúdo e Metadados:** Excelente em buscar metadados, capas, trailers, etc.
    *   **Plex Pass (Pago):** Desbloqueia funcionalidades como:
        *   Hardware Transcoding (para algumas plataformas/GPUs).
        *   Mobile Sync (baixar mídia para visualização offline em dispositivos móveis).
        *   Visualização de TV Ao Vivo e DVR (requer sintonizador compatível).
        *   Múltiplos usuários com controles parentais.
        *   Lyrics, Plexamp (player de música dedicado).
*   **Contras:**
    *   **Proprietário e Centralizado (Parcialmente):** Embora o software do servidor rode localmente, a autenticação e algumas funcionalidades dependem dos servidores Plex. Se os servidores Plex estiverem offline, o login e o acesso remoto podem ser afetados.
    *   **Coleta de Dados (Com Opt-out):** Plex coleta dados de uso (você pode optar por não participar de parte disso).
    *   **Hardware Transcoding com Plex Pass:** Algumas funcionalidades de hardware transcoding, especialmente as mais eficientes, estão bloqueadas atrás do Plex Pass.
    *   **Menos Customizável que Jellyfin.**

## 2. Jellyfin (Mencionado em Nosso Guia)

*   **Tipo:** Servidor de mídia totalmente open-source e gratuito, um fork do Emby.
*   **Prós:**
    *   **100% Open Source e Gratuito:** Todas as funcionalidades, incluindo hardware transcoding (se seu hardware e drivers suportarem), são gratuitas. Nenhuma feature paga.
    *   **Foco na Privacidade e Controle do Usuário:** Nenhum servidor central para autenticação (além da sua própria instância), sem coleta de dados para terceiros. Você tem controle total.
    *   **Hardware Transcoding:** Suporte robusto para hardware transcoding via VAAPI (Intel/AMD), NVENC/NVDEC (NVIDIA), VideoToolbox (macOS), OpenMAX, etc., sem custo adicional.
    *   **Comunidade Ativa e Desenvolvimento Rápido.**
    *   **Customizável:** Muitas opções de configuração e suporte a plugins.
    *   **Múltiplos Usuários e Sincronização (SyncPlay):** Funcionalidades nativas.
*   **Contras:**
    *   **Interface de Usuário e Cliente:** Embora tenha melhorado muito, a UI e a experiência do cliente podem não ser tão polidas ou consistentes em todas as plataformas quanto o Plex para alguns usuários.
    *   **Compatibilidade de Clientes:** A gama de aplicativos cliente é boa e crescente (Android, iOS, Web, Android TV, Roku, Kodi via plugin), mas pode não ser tão universal quanto o Plex em algumas plataformas de Smart TV mais antigas ou nichadas.
    *   **Configuração Inicial de Metadados:** Às vezes, pode exigir um pouco mais de ajuste fino para obter metadados perfeitos comparado ao Plex.
    *   **Acesso Remoto:** Requer configuração manual para acesso externo (e.g., via proxy reverso como Traefik - que é o nosso caso, ou VPN). Não possui um serviço de relay "fácil" como o Plex Relay.

## 3. Emby

*   **Tipo:** Servidor de mídia proprietário, do qual Jellyfin foi forkado. Possui um modelo de licenciamento similar ao Plex (servidor base gratuito, Emby Premiere para funcionalidades avançadas).
*   **Prós:**
    *   **Interface de Usuário Madura e Boas Aplicações Cliente:** Similar ao Plex em termos de polimento e disponibilidade de apps.
    *   **Boas Funcionalidades de Gerenciamento de Mídia e Metadados.**
    *   **Emby Premiere (Pago):** Desbloqueia hardware transcoding, DVR, mobile sync, etc.
*   **Contras:**
    *   **Proprietário com Componentes Core Open Source:** O servidor principal tem código aberto, mas muitas funcionalidades e apps cliente são proprietários.
    *   **Mudança para Modelo Proprietário:** A razão pela qual Jellyfin foi criado foi a decisão do Emby de fechar o código de partes importantes. Isso pode ser uma preocupação para alguns usuários que preferem soluções totalmente open-source.
    *   **Custo do Premiere:** Similar ao Plex Pass, funcionalidades chave estão atrás de um paywall.

## 4. Kodi (com Plugins para Acesso Remoto/Compartilhamento)

*   **Tipo:** Um media *player* e centro de entretenimento open-source extremamente poderoso e customizável, não um "servidor" no mesmo sentido que Plex/Jellyfin/Emby.
*   **Como Funciona para Múltiplos Dispositivos:**
    *   Kodi em si é focado na reprodução local de mídia (de arquivos locais, SMB/NFS shares).
    *   Para uma experiência de "servidor", você geralmente usa Kodi em um dispositivo central (e.g., um HTPC) e depois:
        *   **Compartilhamento de Biblioteca via UPnP/DLNA:** Kodi pode atuar como um servidor UPnP para outros dispositivos na rede.
        *   **Sincronização de Biblioteca com MySQL/MariaDB:** Múltiplas instâncias Kodi podem compartilhar uma biblioteca centralizada (estado de visualização, metadados) usando um backend de banco de dados.
        *   **Plugins de Acesso Remoto:** Existem plugins que tentam fornecer acesso à sua biblioteca Kodi de fora da sua rede, mas geralmente são menos robustos que soluções de servidor dedicadas.
*   **Prós:**
    *   **Extremamente Customizável:** Skins, add-ons para tudo (streaming, legendas, utilitários).
    *   **Excelente Qualidade de Reprodução:** Suporte para uma vasta gama de formatos e codecs.
    *   **Open Source e Gratuito.**
*   **Contras (Como Solução de Servidor):**
    *   **Não é um Servidor Dedicado:** Gerenciar acesso multiusuário, transcodificação para clientes remotos e acesso web/móvel não é seu ponto forte nativo.
    *   **Configuração Mais Complexa para Experiência Multi-Dispositivo:** Sincronizar bibliotecas e estado de visualização requer setup adicional (e.g., MySQL).
    *   **Transcodificação Limitada:** A transcodificação não é uma feature central como em Plex/Jellyfin.
*   **Quando Considerar:** Se seu foco principal é um media center local altamente customizável para um ou poucos dispositivos de reprodução, e você está disposto a configurar o compartilhamento/sincronização de biblioteca se necessário. Pode ser usado *em conjunto* com Jellyfin/Plex (e.g., Kodi como frontend com plugin para Jellyfin/Plex).

## 5. Outras Soluções (Menos Comuns para Vídeo/Séries)

*   **Subsonic / Airsonic / Navidrome (Foco em Música):** Excelentes servidores de streaming de música auto-hospedados, com UIs web e apps móveis. Se seu foco principal é música, estas são ótimas alternativas ou complementos.
*   **PhotoPrism / Immich (Foco em Fotos/Vídeos Pessoais):** Plataformas para gerenciar e visualizar suas coleções de fotos e vídeos pessoais, com funcionalidades de IA para marcação, reconhecimento facial, etc.

## Conclusão da Escolha: Flexibilidade com Plex e Jellyfin

Para este guia, apresentar **Plex e Jellyfin** como opções principais oferece flexibilidade:

*   **Jellyfin** é a escolha ideal para quem valoriza o **open-source total, controle completo, privacidade e funcionalidades avançadas (como hardware transcoding) sem custo adicional.** Sua integração com Traefik/Authelia é direta.
*   **Plex** é uma ótima opção para quem busca a **interface mais polida, a mais ampla compatibilidade de clientes "out-of-the-box" e a facilidade do Plex Relay para compartilhamento simples,** mesmo que isso venha com o trade-off de ser um software proprietário com algumas funcionalidades pagas.

Você pode até mesmo rodar ambos (se os recursos do servidor permitirem e suas bibliotecas estiverem bem organizadas para serem acessadas por ambos), e escolher qual usar dependendo do cliente ou da situação.

A escolha do servidor de mídia depende muito das suas prioridades pessoais em termos de facilidade de uso, ecossistema de clientes, filosofia open-source e funcionalidades específicas que você precisa.