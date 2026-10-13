---
name: validate-infra
description: Use when about to commit or hand off homeserver changes, or when asked whether the infrastructure code is valid, lints cleanly or is consistent with the wiki.
---

# Validar mudanças do homeserver

## Separe o que é seu do que já existia

Antes de editar (ou num `git stash`), rode a linha de base e guarde a saída:

```bash
python tools/dev.py check > /tmp/check-antes.txt; python tools/dev.py lint > /tmp/lint-antes.txt 2>&1
```

Depois das mudanças, rode de novo e compare (`diff`). **Só falhas novas bloqueiam**; as pré-existentes você relata, não corrige sem pedido.

## Sequência

| Comando | Passa quando |
|---|---|
| `python tools/dev.py test` | sempre (se tocou em `tools/`) |
| `python tools/dev.py check` | nenhum erro novo |
| `python tools/dev.py build` | código 0 (modo estrito) |
| `python tools/dev.py lint` | nenhuma falha nova; no Windows a parte Ansible é pulada — avise o usuário ou use WSL/CI |
| `bash server/scripts/validation/...` | apenas se o usuário pedir: rodam contra a infraestrutura real |

`lint` precisa das coleções Ansible: `ansible-galaxy collection install community.general community.docker community.proxmox ansible.posix`.

## Relatório final

Liste: comandos rodados e resultado; falhas novas (deve ser zero); falhas pré-existentes por nome; o que não pôde ser validado (ex.: docker ausente).
