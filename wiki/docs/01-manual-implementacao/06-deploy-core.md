---
description: "Deploy da stack core (Traefik, Cloudflared e Authelia) no Portainer a partir de docker/stacks/core/docker-compose.yml."
---

# Seção 6: Deploy da Infraestrutura Core (Traefik + Cloudflared + Authelia)

A stack core é a base de rede: Traefik (proxy reverso), Cloudflared (túnel) e Authelia (autenticação 2FA). Tudo consolidado em `docker/stacks/core/docker-compose.yml`.

## Deploy no Portainer

1. Acesse o Portainer em `https://portainer.seudominio.com`
2. **Stacks** > **Add Stack** > Nome: `core`
3. Selecione **Web editor**
4. Cole o conteúdo de `docker/stacks/core/docker-compose.yml`
5. Em **Environment variables**, clique em Advanced mode > **Load variables from .env file**
6. Caminho na VM: `/opt/portainer_stack_envs/core.env`
7. Adicione manualmente os segredos: `CLOUDFLARE_API_TOKEN_FROM_VAULT`, `CLOUDFLARE_TUNNEL_TOKEN_FROM_VAULT`, `AUTHELIA_STORAGE_POSTGRES_PASSWORD_FROM_VAULT`
8. **Deploy the stack**

## O que cada serviço faz

- **Traefik**: Proxy reverso HTTPS. Detecta containers via labels. Redireciona HTTP→HTTPS automaticamente.
- **Cloudflared**: Túnel para Cloudflare. Não precisa abrir portas no roteador.
- **Authelia**: SSO com 2FA. Protege todos os serviços via middleware `authelia-forwardauth@docker`.
- **Authelia DB**: Postgres para dados de sessão e 2FA do Authelia.

## Pré-requisitos

- Playbooks Ansible executados:
  ```bash
  ansible-playbook -i ansible/inventories/home/hosts.ini ansible/playbooks/setup-base-ubuntu.yml
  ansible-playbook -i ansible/inventories/home/hosts.ini ansible/playbooks/setup-core-networking.yml
  ```
- Rede Docker `proxy` e `internal_services` criadas pelo playbook de rede.
- Token do túnel Cloudflare gerado no dashboard Cloudflare Zero Trust.
- API Token DNS Cloudflare (para desafio Let's Encrypt DNS-01).
