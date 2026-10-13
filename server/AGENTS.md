# server/ — convenções

Implementação do servidor. **Tudo aqui reflete a wiki** (`wiki/docs/`): mude a wiki primeiro,
depois `python tools/dev.py sync`. Consulte o `INDEX.md` para achar a página de cada arquivo.

## Ansible (`ansible/`)

- Rode os comandos a partir de `server/ansible/` (carrega `ansible.cfg`: inventário `inventories/home/hosts.ini`, `roles_path ./roles`).
- Grupos do inventário: `proxmox_hosts` (`proxmox_main_host`), `core_services` (`core-services-vm`),
  `ai_desktop` (`ai-desktop-vm`), `virtual_machines` e `ubuntu_vms` (filhos: `core_services`, `ai_desktop`).
- Variáveis globais não secretas: `inventories/home/group_vars/all/main.yml`.
  Segredos: `vault.yml` (criptografado com `ansible-vault`); modelo em `vault.yml.example`.
- Roles por categoria: `roles/common/`, `roles/infra/<role>/`, `roles/apps/<role>/`, `roles/tools/<role>/`,
  com `tasks/`, `handlers/`, `defaults/`, `templates/` conforme necessário.
- Playbooks em `playbooks/`: `setup-<alvo>.yml` para configurar hosts, `setup-<stack>-volumes.yml` para
  preparar volumes/configs de uma stack, `vm-deploy.yml` (VMs no Proxmox), `full-deploy.yml` (orquestra tudo).
- Módulos sempre com FQCN (`ansible.builtin.*`, `community.general.*`, `community.docker.*`);
  `block:` é palavra-chave (nunca `ansible.builtin.block:`).
- Valide com `python tools/dev.py lint` (syntax-check usa `-i localhost,` para não precisar do vault).

## Docker (`docker/stacks/`)

- Uma pasta por stack (`core/`, `apps/`, `ai/`) com `docker-compose.yml`; implantadas pelo Portainer
  ou pelos playbooks.
- Redes externas `proxy` (serviços expostos pelo Traefik) e `internal_services` (backend), criadas pelo Ansible.
- Exposição: labels do Traefik com ``Host(`<sub>.${BASE_DOMAIN_FROM_VAULT}`)`` e o middleware do Authelia
  para tudo que não for público.
- Toda variável `${...}` usada num compose deve existir em `docker/stacks/.env.template`.
- Imagens com versão fixada sempre que possível.

## Scripts (`scripts/`)

`bootstrap.sh` (prepara a máquina de controle), `restore.sh` (reaplica o full-deploy) e
`validation/` (diagnósticos de infraestrutura). Bash com `#!/usr/bin/env bash` e `set -euo pipefail`.
