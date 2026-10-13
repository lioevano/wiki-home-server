---
name: add-ansible-component
description: Use when creating or restructuring an Ansible role, playbook, inventory group or group_vars variable in the homeserver server/ansible tree.
---

# Novo role ou playbook Ansible

**REQUIRED SUB-SKILL:** siga `wiki-first-change`.

## Convenções (detalhe em `server/AGENTS.md`)

| Item | Padrão |
|---|---|
| Role | `roles/<common|infra|apps|tools>/<nome>/{tasks,handlers,defaults,templates}/` |
| Playbook de host | `playbooks/setup-<alvo>.yml`; de stack: `playbooks/setup-<stack>-volumes.yml` |
| Alvos (`hosts:`) | grupos do `inventories/home/hosts.ini`: `proxmox_hosts`, `core_services`, `ai_desktop`, `virtual_machines`, `ubuntu_vms` |
| Variáveis | não secretas → `group_vars/all/main.yml`; segredos → `vault.yml` **e** placeholder em `vault.yml.example` |
| Módulos | FQCN (`ansible.builtin.*`, `community.general.*`); `block:` é palavra-chave |

## Passos

1. Escreva cada arquivo novo como **bloco literal** na página da wiki do assunto (`title="ansible/roles/..."`), com o texto explicando o porquê.
2. Variável nova: atualize o bloco literal de `main.yml` ou de `vault.yml.example` (página `01-maquina-controle-ansible.md`).
3. Grupo novo: atualize o bloco literal do `hosts.ini` na mesma página.
4. `dev.py check` → `LIT-MISSING`/`LIT-DIFF` esperados → `dev.py sync` → `--yes`.
5. Se o playbook entra no fluxo completo, inclua-o no bloco de `full-deploy.yml` (página `04-manutencao-recuperacao/03-cicd-basico-ansible.md`).
6. Skill `validate-infra` (o `--syntax-check` do playbook novo precisa passar), skill `update-index`, commit.
