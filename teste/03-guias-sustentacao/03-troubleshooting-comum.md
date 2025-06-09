# Guia de Troubleshooting Comum

Mesmo com uma configuração cuidadosa, problemas podem surgir. Este guia oferece um ponto de partida para diagnosticar e resolver alguns dos problemas mais comuns que você pode encontrar no seu servidor doméstico.

## Ferramentas Essenciais de Diagnóstico

Familiarize-se com estas ferramentas. Elas serão indispensáveis.

*   **Logs de Containers Docker:**
    *   **Via Portainer:** Selecione o container -> "Logs". Opções para ver logs desde um certo tempo, auto-refresh.
    *   **Via Linha de Comando (na VM onde o Docker roda):**
        ```bash
        docker logs <nome_do_container_ou_id>
        docker logs -f <nome_do_container_ou_id> # Para seguir os logs em tempo real
        docker logs --tail 50 <nome_do_container_ou_id> # Para ver as últimas 50 linhas
        ```
*   **Dashboard do Traefik:**
    *   Acessível em `https://traefik.{{ base_domain }}` (se configurado e protegido por Authelia).
    *   Mostra:
        *   **Routers:** Quais regras de host estão ativas, a que serviços estão ligadas, quais middlewares estão aplicados.
        *   **Services:** Os backends (seus containers Docker) e seu status.
        *   **Middlewares:** Quais middlewares estão configurados.
        *   **Entrypoints:** Status dos seus pontos de entrada (HTTP, HTTPS).
        *   Pode mostrar erros de configuração do Traefik.
*   **Logs do Traefik:**
    *   No Portainer, veja os logs do container `traefik`.
    *   Procure por erros ao processar labels, obter certificados SSL, ou conectar-se a backends.
*   **Logs do Authelia:**
    *   No Portainer, veja os logs do container `authelia`.
    *   Útil para problemas de login, 2FA, ou regras de acesso.
*   **Logs do Sistema (Host Proxmox e VMs):**
    *   `journalctl -xe` (para erros do systemd e do sistema).
    *   `dmesg` (para mensagens do kernel, útil para problemas de hardware/drivers).
    *   `/var/log/syslog`, `/var/log/auth.log` (na VM).
*   **Ferramentas de Rede (na máquina de controle ou dentro de uma VM/container para teste):**
    *   `ping <hostname_ou_IP>`: Testa conectividade básica.
    *   `nslookup <hostname>` ou `dig <hostname>`: Verifica resolução DNS.
    *   `curl -vL <URL>`: Faz uma requisição HTTP/S e mostra detalhes da conexão, headers e redirecionamentos. Muito útil para testar Traefik e Authelia.
    *   `traceroute <hostname_ou_IP>` ou `mtr <hostname_ou_IP>`: Mostra o caminho de rede.
*   **Browser Developer Tools (F12 no seu navegador):**
    *   **Aba Network:** Inspecione todas as requisições feitas pela página, seus status, headers, tempos. Veja se há erros 4xx (cliente) ou 5xx (servidor).
    *   **Aba Console:** Verifique por erros JavaScript que podem quebrar a funcionalidade da UI de um serviço.

## Problemas Comuns e Estratégias de Solução

### 1. Serviço Inacessível Externamente (`https://meuservico.{{ base_domain }}`)

*   **Sintomas:** Timeout, erro "Site não pode ser alcançado", erro 5xx da Cloudflare, erro 404 do Traefik.
*   **Checklist de Diagnóstico:**
    1.  **DNS:**
        *   O subdomínio está configurado corretamente na Cloudflare (CNAME para o túnel ou Ingress Rule)?
        *   A nuvem do proxy está Laranja (Proxied)?
        *   Use `nslookup meuservico.{{ base_domain }}` na sua máquina. Deve resolver para IPs da Cloudflare.
    2.  **Cloudflare Tunnel:**
        *   O container `cloudflared` está rodando na `core-services-vm`? (Verifique no Portainer).
        *   Veja os logs do `cloudflared`: `docker logs cloudflared`. Procure por erros de conexão com a Cloudflare ou com o Traefik (se estiver usando `--url http://traefik:80`).
        *   No dashboard Cloudflare Zero Trust, verifique o status do túnel e dos hostnames públicos.
    3.  **Traefik:**
        *   O container `traefik` está rodando?
        *   Acesse o dashboard do Traefik (`https://traefik.{{ base_domain }}`).
            *   O roteador para `meuservico.{{ base_domain }}` existe e está ativo?
            *   O serviço backend associado ao roteador está saudável (apontando para o container correto e a porta interna correta)?
            *   Há algum erro de middleware?
        *   Verifique as labels Docker do container `meuservico` no seu `docker-compose.yml`. Estão corretas? (Nome do host, entrypoint, serviço, porta).
        *   Verifique os logs do Traefik para erros relacionados a este serviço.
    4.  **Authelia (se o serviço estiver protegido):**
        *   O container `authelia` está rodando?
        *   Você consegue acessar o portal Authelia (`https://auth.{{ base_domain }}`)?
        *   Verifique os logs do Authelia para erros de autenticação ou problemas com as regras de acesso.
        *   Tente acessar o serviço com `?authelia_bypass=true` no final da URL (se você configurou uma regra de bypass para teste, o que não é recomendado para produção).
    5.  **Container do Serviço (`meuservico`):**
        *   O container está rodando?
        *   Ele está escutando na porta interna que o Traefik espera (e.g., se Traefik aponta para a porta 8000, o container deve estar escutando na porta 8000)?
        *   Verifique os logs do container `meuservico` para erros de inicialização ou de processamento de requisições.
    6.  **Firewalls:**
        *   O UFW na `core-services-vm` está permitindo tráfego nas portas 80 e 443 (para Traefik)? (Já deve estar configurado pelo Ansible).
        *   O PVE Firewall no host Proxmox não deve estar bloqueando tráfego para a `core-services-vm` (geralmente não é um problema se as VMs estão na mesma bridge `vmbr0` e o firewall PVE é para tráfego externo ao host).

### 2. Container Não Inicia ou em Loop de Crash (Restarting)

*   **Sintomas:** Container aparece como "Stopped" ou fica reiniciando no Portainer.
*   **Diagnóstico:**
    1.  **`docker logs <nome_do_container>`:** Esta é a primeira e mais importante etapa. Os logs geralmente indicam o motivo da falha.
    2.  **Problemas de Configuração:**
        *   Variável de ambiente faltando ou incorreta?
        *   Arquivo de configuração essencial faltando ou malformado dentro de um volume?
    3.  **Problemas de Permissão em Volumes:**
        *   O PUID/PGID configurado para o container corresponde às permissões do diretório NFS mapeado? Lembre-se que o NFS está configurado para `all_squash` para `{{ docker_puid }}:{{ docker_pgid }}`. Se o container tentar rodar como um usuário diferente internamente e precisar escrever, pode falhar.
        *   Verifique as permissões no diretório NFS na VM (`ls -ld /mnt/pve_data_zfs/docker-volumes/meuservico/config`).
    4.  **Porta Já em Uso:**
        *   Se o container tenta mapear uma porta no host da VM (e.g., `-p 8080:80`) que já está sendo usada por outro processo ou container, ele falhará.
        *   Use `sudo ss -tulnp | grep <numero_da_porta>` na VM para ver qual processo está usando a porta.
    5.  **Recursos Insuficientes:**
        *   A VM tem RAM ou CPU suficiente para o container iniciar? (Menos comum para falha imediata, mais para performance ruim).
    6.  **Dependências Não Satisfeitas:**
        *   Se o container depende de outro (e.g., uma aplicação que precisa de um banco de dados), o `depends_on` no `docker-compose.yml` com `condition: service_healthy` pode ajudar, mas o container dependente ainda pode falhar se o serviço principal não estiver acessível ou configurado corretamente.

### 3. Problemas com Volumes NFS

*   **Sintomas:** Containers não conseguem ler/escrever em seus volumes, dados não persistem, erros de "Permission denied" nos logs do container.
*   **Diagnóstico:**
    1.  **Servidor NFS no Host Proxmox:**
        *   O serviço está rodando? `systemctl status nfs-kernel-server` no host Proxmox.
        *   O arquivo `/etc/exports` está correto? (Verifique caminhos, IPs permitidos, opções de squash e `anonuid`/`anongid`).
        *   Execute `sudo exportfs -rav` no host Proxmox para recarregar os exports e ver se há erros.
    2.  **Cliente NFS na VM:**
        *   Os compartilhamentos NFS estão montados? `df -h` ou `mount | grep nfs` na VM.
        *   O arquivo `/etc/fstab` na VM tem as entradas corretas para montagem automática?
        *   Consegue listar o conteúdo do ponto de montagem NFS na VM? (e.g., `ls -l /mnt/pve_data_zfs/docker-volumes`).
    3.  **Permissões:**
        *   No host Proxmox, quais são as permissões dos diretórios ZFS exportados (e.g., `/data/docker-volumes`)?
        *   Na VM, após a montagem, quais são as permissões e o proprietário/grupo do ponto de montagem e seus subdiretórios? Devido ao `all_squash` e `anonuid`/`anongid`, eles devem pertencer a `{{ docker_puid }}:{{ docker_pgid }}` (e.g., 1000:1000).
        *   O PUID/PGID do container corresponde a essas permissões?
    4.  **Firewall:** O firewall no host Proxmox (PVE Firewall) ou na VM (UFW) está bloqueando portas NFS (TCP/UDP 2049, e possivelmente portas para portmapper/rpcbind se usar NFSv3 ou inferior - NFSv4 geralmente só precisa da 2049)? (Ansible deve ter configurado isso, mas verifique).

### 4. Problemas de Autenticação (Authelia)

*   **Sintomas:** Redirecionamentos inesperados, erros no portal de login do Authelia, acesso negado mesmo com credenciais corretas.
*   **Diagnóstico:**
    1.  **Logs do Authelia:** `docker logs authelia`. Procure por mensagens de erro detalhadas.
    2.  **Configuração do Authelia (`configuration.yml`):**
        *   `jwt_secret` e `session.secret` estão definidos e são complexos?
        *   `session.domain` está configurado para o domínio pai (e.g., `{{ base_domain }}`), não `auth.{{ base_domain }}`?
        *   As regras em `access_control` estão corretas? A `default_policy` e as regras específicas para domínios estão como esperado?
        *   A configuração do `storage` (PostgreSQL) está correta (host, usuário, senha, DB)?
    3.  **Conectividade com o Banco de Dados do Authelia:** O container Authelia consegue alcançar o container `authelia_db`? (Eles devem estar na mesma rede `internal_services`).
    4.  **Cookies do Navegador:** Tente limpar os cookies para `{{ base_domain }}` e `auth.{{ base_domain }}` e tente novamente.
    5.  **Relógio do Sistema:** Certifique-se de que o relógio na `core-services-vm` (e consequentemente nos containers) está sincronizado corretamente (NTP). Problemas de sincronia de relógio podem afetar TOTP.
    6.  **Configuração do Middleware no Traefik:** A label `traefik.http.middlewares.authelia.forwardauth.address` no compose do Authelia aponta corretamente para `http://authelia:9091/api/verify...`?

### 5. Problemas com Certificados SSL/TLS (Let's Encrypt via Traefik)

*   **Sintomas:** Aviso de certificado inválido/expirado no navegador, erros de "SSL handshake failed".
*   **Diagnóstico:**
    1.  **Logs do Traefik:** Procure por mensagens de erro relacionadas a "ACME", "Let's Encrypt", ou "TLS challenge".
    2.  **Configuração do Resolvedor ACME no `traefik.yml`:**
        *   O email está correto?
        *   O `storage` (caminho para `acme.json`) está correto e o container Traefik tem permissão de escrita nele? (Verifique permissões do volume NFS).
        *   Para `dnsChallenge` com Cloudflare:
            *   A variável de ambiente `CF_DNS_API_TOKEN` está sendo passada corretamente para o container Traefik?
            *   O token API da Cloudflare é válido e tem as permissões corretas (Zone.DNS - Edit) para o seu `{{ base_domain }}`?
    3.  **Arquivo `acme.json`:**
        *   Verifique o conteúdo (com cuidado, é JSON). Ele contém os certificados? Há erros?
        *   **NÃO EDITE MANUALMENTE.** Se estiver corrompido, pode ser necessário pará-lo, remover `acme.json`, e reiniciar Traefik para que ele tente obter novos certificados (isso pode acionar limites de taxa da Let's Encrypt se feito repetidamente).
    4.  **Limites de Taxa da Let's Encrypt:** Se você tentou obter certificados muitas vezes sem sucesso, pode ter atingido um limite de taxa. Aguarde (geralmente uma hora ou mais) antes de tentar novamente.
    5.  **DNS Propagation:** Para o desafio DNS-01, Traefik precisa criar um registro TXT que seja publicamente resolúvel. Se sua propagação DNS for muito lenta, o desafio pode falhar.

Lembre-se que o troubleshooting é um processo iterativo. Comece com os logs, formule hipóteses e teste-as sistematicamente.
