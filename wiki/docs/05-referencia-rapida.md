---
description: "Referência rápida: tecnologias usadas, para que servem, links da documentação oficial e alternativas."
---

# 📎 Referência Rápida

Conceitos essenciais, links úteis e alternativas para o servidor doméstico.

## Tecnologias Principais

| Tecnologia | Para que serve | Doc oficial |
|---|---|---|
| **Proxmox VE** | Hypervisor KVM/LXC. Base de toda a virtualização. Permite criar VMs isoladas com GPU passthrough. | [proxmox.com](https://pve.proxmox.com/wiki/Main_Page) |
| **ZFS** | Sistema de arquivos com snapshots automáticos, checksum e RAID por software. Pool `/data` nos HDDs. | [openzfs.org](https://openzfs.org/wiki/Main_Page) |
| **Ansible** | Infraestrutura como Código. Provisiona VMs, configura redes e volumes via playbooks idempotentes. | [docs.ansible.com](https://docs.ansible.com/) |
| **Docker + Portainer** | Containers para cada serviço. Portainer como UI gerencial. Redes `proxy` e `internal_services`. | [docker.com](https://docs.docker.com/) / [portainer.io](https://docs.portainer.io/) |
| **Traefik** | Proxy reverso com auto-discovery via labels Docker. Roteia tráfego HTTPS para cada container. | [traefik.io](https://doc.traefik.io/traefik/) |
| **Cloudflare Tunnel** | Acesso externo sem abrir portas no roteador. Túnel criptografado direto para o Traefik. | [developers.cloudflare.com](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) |
| **Authelia** | SSO com 2FA (TOTP/WebAuthn). Protege todos os serviços via middleware do Traefik. | [authelia.com](https://www.authelia.com/) |
| **NFS** | Compartilhamento de volumes persistentes do host Proxmox para as VMs. | [nfs.org](https://wiki.archlinux.org/title/NFS) |

## Stack de IA

| Serviço | Função |
|---|---|
| **Ollama** | Executa modelos LLM locais (Llama 3, Phi 3, etc.) via GPU/CPU |
| **LiteLLM** | Proxy OpenAI-compatible. Roteia entre Ollama e APIs externas com fallback automático |
| **Open WebUI** | Interface de chat. Conecta ao LiteLLM para acesso unificado a todos os modelos |
| **OpenClaw** | CLI agent para interagir com LLMs via terminal |
| **OpenClaude** | Assistente AI com integração a ferramentas e contextos locais |

## Alternativas por Camada

Use apenas se algo não atender suas necessidades. A stack principal já funciona bem.

| Camada | Escolhido | Alternativa | Quando considerar |
|---|---|---|---|
| Hypervisor | Proxmox VE | libvirt/KVM puro | Se quiser minimalismo extremo sem UI |
| Automação | Ansible | Shell scripts | Se tiver < 2 máquinas e zero planos de expansão |
| Containers | Docker + Portainer | Podman, LXC direto | Se Docker consumir RAM demais |
| Proxy Reverso | Traefik | Caddy, Nginx | Se precisar de configuração manual granular |
| Auth SSO | Authelia | Authentik, Authelia + Keycloak | Se precisar de LDAP/Active Directory |
| Mídia | Jellyfin | Plex, Kodi | Se Plex Discovery for importante |
| Monitoramento | Prometheus + Grafana | Glances sozinho | Se precisar só de visão rápida da VM |
| Arquivos | Nextcloud | Syncthing, Samba | Se só precisa de sync, sem interface web |

## Comandos Úteis

```bash
# Criar snapshot ZFS antes de mudança arriscada
zfs snap data/docker-volumes@antes-da-mudanca

# Restaurar snapshot ZFS
zfs rollback data/docker-volumes@antes-da-mudanca

# Listar stacks Docker rodando
docker compose ls

# Ver logs de um serviço
docker logs -f --tail 50 nome_do_container

# Rodar playbook específico
ansible-playbook -i ansible/inventories/home/hosts.ini ansible/playbooks/setup-base-ubuntu.yml

# Verificar status da VM
qm status 100  # proxmox CLI para core-services-vm
```

## Solução de Problemas

| Sintoma | Provável causa | Ação |
|---|---|---|
| Serviço inacessível externamente | Cloudflare Tunnel caiu | `docker logs cloudflared` |
| 502 Bad Gateway | Traefik não resolve o serviço | Ver labels do container e rede `proxy` |
| Authelia pedindo login em loop | Cookie/SSL mismatch | Verificar que `traefik.http.routers.*.tls` está ativo |
| NFS mount falhando na VM | Serviço NFS parou no host | `systemctl status nfs-kernel-server` no Proxmox |
| Ollama não detecta GPU | Passthrough da GPU AMD ou `/dev/kfd`/`/dev/dri` ausentes | `docker logs ollama` e `ls /dev/kfd /dev/dri` na `ai-desktop-vm` (imagem `ollama/ollama:rocm`) |
| LiteLLM retornando erro 429 | Rate limit da API externa | Verificar config `config.yaml` do LiteLLM |
