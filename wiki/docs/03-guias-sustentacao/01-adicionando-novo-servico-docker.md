---
description: "Como adicionar uma aplicação Docker, numa stack nova ou existente: catálogo, integrações, compose, playbook de volumes, deploy e índice."
---

# Adicionando um Serviço Docker

Uma aplicação nova entra no servidor sempre pelo mesmo caminho. Primeiro ela ganha uma **linha no catálogo**. A linha decide quais integrações ela recebe, a **página da wiki** descreve a aplicação e só então o `server/` é alterado. Agentes de IA executam esse fluxo pela skill `add-app` (veja o `AGENTS.md` na raiz do repositório), e este guia mostra o mesmo caminho feito à mão.

!!! info "Fontes da verdade"
    - [Catálogo de Aplicações](../02-visao-geral-arquitetura/09-catalogo-aplicacoes.md): o que a aplicação é (stack, VM, exposição, subdomínio, dados, métricas).
    - [Índice de Integrações](../02-visao-geral-arquitetura/10-indice-integracoes.md): o que cada integração exige dela (regras ROT, AUT, EXT, MET, LOG, DAD, VAR, DOC, PNL, NTF…).

## 1. Pesquisar

Anote, com os links da documentação oficial (eles vão para a página da wiki):

- imagem e **versão fixa** (nunca `:latest`), porta interna, variáveis obrigatórias, volumes persistentes e healthcheck;
- se expõe métricas (`/metrics`), se aceita OIDC/SSO e se precisa de banco ou cache (viram serviços auxiliares na mesma stack);
- se usa SQLite ou Postgres: banco **não** fica em NFS. Ele vai para o disco local da VM (`{{ vm_local_data_path }}`), com dump diário para o NFS (regra DAD-5).

## 2. Stack nova ou existente?

| Situação | Onde |
|---|---|
| Auxiliar de uma aplicação que já existe (exporter, cron, worker) | Na stack dela |
| Aplicação do mesmo assunto de uma stack (ex.: mais uma *arr na `media`) | Na stack do assunto |
| Assunto novo, ciclo de vida próprio ou VM diferente | Stack nova em `docker/stacks/<stack>/` |

Uma stack existente ganha o serviço no próprio `docker-compose.yml` e as variáveis no playbook de volumes **dela**. Uma stack nova ganha compose, playbook `setup-<stack>-volumes.yml` e `.env` próprios.

## 3. Catálogo e página

1. Escreva a linha no catálogo com todas as colunas preenchidas. Exposição (`publica`, `protegida` ou `interna`), subdomínio e categoria são decisões suas; deixe `?` enquanto não decidir.
2. Para cada integração do índice, veja em "Aplica-se a" se ela vale para a linha nova, e siga os passos de "Ao adicionar". Na prática:

    | Integração | O que entra |
    |---|---|
    | roteamento | labels do Traefik com ``Host(`<sub>.${BASE_DOMAIN_FROM_VAULT}`)`` na rede `proxy` (ou um router no `dynamic_ai_services.yml.j2`, se a aplicação estiver na `ai-desktop-vm`) |
    | autenticacao | `protegida`: middleware `authelia-forwardauth@docker`, e o subdomínio em `authelia_dominios_admins` se for painel de administração. `publica`: regra `bypass` no Authelia antes do curinga |
    | metricas | job no `ansible/templates/prometheus.yml.j2`, se houver `/metrics` |
    | dados | diretórios criados pelo playbook de volumes; `*_PATH` apontando para o NFS (ou para o disco local, no caso de bancos) |
    | variaveis | toda `${VAR}` do compose no `docker/stacks/.env.template` e produzida pelo playbook |
    | painel e notificacoes | entrada no `ansible/templates/homepage/services.yaml.j2`, alvo do blackbox pela URL interna e webhook para o n8n, se a aplicação tiver |

3. Escreva a seção da aplicação na página da stack (ou uma página nova, pela skill `wiki-page-authoring`), com os links da pesquisa, as variáveis e o primeiro acesso.

## 4. Compose e playbook

Exemplo: um gerenciador de arquivos simples, protegido pelo Authelia, numa stack nova `ferramentas` da `core-services-vm`.

```yaml title="Exemplo: compose da stack ferramentas"
networks:
  proxy:
    name: proxy
    external: true

services:
  filebrowser:
    image: filebrowser/filebrowser:v2.31.2 # versão fixa (o Diun avisa quando sair outra)
    container_name: filebrowser
    restart: unless-stopped
    user: "${DOCKER_PUID}:${DOCKER_PGID}"
    networks:
      - proxy
    volumes:
      - "${FERRAMENTAS_FILEBROWSER_CONFIG_PATH}:/config"
    environment:
      - TZ=${SYSTEM_TIMEZONE}
    labels:
      traefik.enable: "true"
      traefik.http.routers.filebrowser.rule: "Host(`arquivos.${BASE_DOMAIN_FROM_VAULT}`)"
      traefik.http.routers.filebrowser.entrypoints: "websecure"
      traefik.http.routers.filebrowser.tls.certresolver: "letsencrypt"
      traefik.http.routers.filebrowser.middlewares: "authelia-forwardauth@docker"
      traefik.http.services.filebrowser-svc.loadbalancer.server.port: "80"
```

```yaml title="Exemplo: playbook setup-ferramentas-volumes.yml"
- name: Volumes e variáveis da stack ferramentas
  hosts: core_services
  become: true
  vars_files:
    - ../inventories/home/group_vars/all/main.yml
    - ../inventories/home/group_vars/all/vault.yml
  tasks:
    - name: Diretório de configuração do File Browser
      ansible.builtin.file:
        path: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/filebrowser/config"
        state: directory
        owner: "{{ docker_puid }}"
        group: "{{ docker_pgid }}"
        mode: '0750'

    - name: ferramentas.env
      ansible.builtin.template:
        src: ../templates/portainer_stack_env.j2
        dest: "{{ portainer_env_files_dest_path_on_vm }}/ferramentas.env"
        owner: root
        group: root
        mode: '0600'
      vars:
        stack_name: ferramentas
        stack_configs:
          - { name: 'FERRAMENTAS_FILEBROWSER_CONFIG_PATH', value: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/filebrowser/config" }
```

Acrescente `FERRAMENTAS_FILEBROWSER_CONFIG_PATH=` ao `docker/stacks/.env.template`: o `python tools/dev.py lint` falha se o compose usar uma variável fora dele. Segredos vêm do vault pelo playbook, nunca digitados no Portainer.

## 5. Validar e implantar

1. `python tools/dev.py check`, `sync` e `sync --yes`; depois `test`, `build` e `lint`.
2. Skill `audit-integrations` para a aplicação (sem `❌`/`⚠️`), `update-index` e um commit único com a wiki, o server e o índice.
3. Na máquina de controle: `ansible-playbook -i inventories/home/hosts.ini playbooks/setup-ferramentas-volumes.yml --check`, depois sem `--check`.
4. Portainer → **Stacks** → **Add Stack** (ou, numa stack existente, **Editor** + **Update the stack**) com o compose do repositório e o `.env` gerado em **Env**.
5. O hostname curinga do túnel já leva o subdomínio novo ao Traefik. Se a aplicação tiver regra ou router novo no Authelia ou no Traefik, rode também o `setup-core-networking.yml`.
6. Rode o `setup-monitoring-stack-volumes.yml` se a aplicação entrou no Prometheus, no blackbox ou na Homepage.

## Erros comuns

| Erro | Correção |
|---|---|
| Jinja do Ansible nas labels do compose | O compose usa `${BASE_DOMAIN_FROM_VAULT}`; as chaves duplas só existem nos templates do Ansible |
| Banco de dados no NFS | Disco local + dump (DAD-5) |
| Variável no compose e não no `.env.template` | O `lint` acusa; acrescente ao template e ao playbook |
| Middleware com outro nome | Sempre `authelia-forwardauth@docker` |
| Serviço novo sem linha no catálogo | O `audit-integrations` acusa DOC-4 |
