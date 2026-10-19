---
description: "Deploy da stack core (Traefik, Cloudflared e Authelia) pelo Ansible, com o playbook setup-core-networking.yml."
---

# Seção 6: Deploy da Infraestrutura Core (Traefik + Cloudflared + Authelia)

A stack core é a base de rede: Traefik (proxy reverso), Cloudflared (túnel) e Authelia (autenticação 2FA). Tudo consolidado em `docker/stacks/core/docker-compose.yml`.

Diferente das stacks `apps` e `ai`, a `core` **não é criada no Portainer**: o próprio Ansible a implanta com `community.docker.docker_compose_v2`, porque o Portainer é acessado por `portainer.seudominio.com`, que depende do Traefik, do túnel e do Authelia já estarem de pé.

## Pré-requisitos

- Seções 1 a 5 concluídas: VMs provisionadas e configuradas (`setup-base-ubuntu.yml`), roles e templates da [Rede Segura](05-rede-segura.md) no repositório.
- No vault (`ansible/inventories/home/group_vars/all/vault.yml`):
    - `cloudflare_tunnel_token`: token do túnel gerado no Cloudflare Zero Trust.
    - `cloudflare_api_token`: API Token com permissão de DNS na zona (desafio DNS-01 do Let's Encrypt).
    - `authelia_storage_postgres_password` e os demais segredos do Authelia.

## Deploy

Na máquina de controle, a partir da pasta `server/ansible` do repositório:

```bash
ansible-playbook -i inventories/home/hosts.ini playbooks/setup-core-networking.yml --ask-vault-pass --check
ansible-playbook -i inventories/home/hosts.ini playbooks/setup-core-networking.yml --ask-vault-pass
```

O playbook:

1. Cria as redes Docker `proxy` e `internal_services` na `core-services-vm`.
2. Gera as configurações do Traefik e do Authelia no volume NFS (roles `infra/traefik-config` e `infra/authelia-config`).
3. Copia o compose para `/opt/stacks/core/` na VM e sobe a stack, passando as variáveis no bloco `environment:` da tarefa (sem `.env` em disco).
4. Espera o healthcheck do Traefik.

Detalhes de cada passo estão na [seção 5.4](05-rede-segura.md#54-playbook-ansibleplaybookssetup-core-networkingyml). Para mudar uma variável ou um segredo da stack, altere o vault ou `group_vars` e rode o playbook de novo.

## Depois do deploy

1. Configure os Public Hostnames do túnel (`https://traefik:443`, com *No TLS Verify*), conforme a [seção 5.5](05-rede-segura.md#55-configuração-de-dns-na-cloudflare).
2. Acesse `https://auth.seudominio.com` e registre o 2FA.
3. Acesse `https://portainer.seudominio.com` para seguir com as stacks `apps` e `ai` nas próximas seções.

## O que cada serviço faz

- **Traefik**: Proxy reverso HTTPS. Detecta containers via labels. Redireciona HTTP→HTTPS automaticamente.
- **Cloudflared**: Túnel para Cloudflare. Não precisa abrir portas no roteador.
- **Authelia**: SSO com 2FA. Protege todos os serviços via middleware `authelia-forwardauth@docker`.
- **Authelia DB**: Postgres para dados de sessão e 2FA do Authelia.

!!! info "Primeiro login no Authelia"
    Os usuários vêm do `users_database.yml` (backend `file`, gerado a partir do vault). Sem SMTP configurado, o Authelia usa o notificador `filesystem`: o link para registrar o 2FA (TOTP) aparece no arquivo `authelia/config/notification.txt` do volume NFS — leia-o na `core-services-vm` com `sudo cat <vm_nfs_mount_base_path>/<zfs_docker_volumes_dataset_name>/authelia/config/notification.txt`.
