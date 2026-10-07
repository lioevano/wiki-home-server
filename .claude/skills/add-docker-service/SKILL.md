---
name: add-docker-service
description: Use when the user wants to add, expose or move a containerized service (Docker/Compose) in the homeserver stacks core, apps or ai, including Traefik routing, Authelia protection and volumes.
---

# Adicionar um serviço Docker

**REQUIRED SUB-SKILL:** siga `wiki-first-change`; este é o checklist específico.

## Decisões antes de editar

| Pergunta | Onde olhar |
|---|---|
| Qual stack? (`core` rede/autenticação, `apps` aplicações, `ai` IA na ai-desktop-vm) | `INDEX.md` → Serviços |
| Público ou protegido? (padrão: protegido pelo Authelia) | `wiki/docs/02-visao-geral-arquitetura/06-principios-seguranca.md` |
| Dados em NFS (ZFS, com snapshots) ou disco local? (SQLite e bancos sensíveis a lock → local, com aviso de backup) | página da stack |
| Imagem com versão fixa | sempre (`imagem:x.y.z`) |

## Checklist

1. **Wiki** — na página da stack (`01-manual-implementacao/0X-...`): linha na tabela de serviços, nota do serviço (porta, redes, acesso, primeiro login) e, se houver, aviso sobre volume local.
2. **Variáveis** — cada `${VAR}` nova entra no bloco literal `docker/stacks/.env.template` (página `00-preparacao-planejamento.md`) → `dev.py sync --yes`.
3. **Compose** — `server/docker/stacks/<stack>/docker-compose.yml`, copiando o padrão de um serviço vizinho:
   - redes `proxy` (se exposto) e `internal_services` (se fala com backends);
   - labels `traefik.enable=true`, ``traefik.http.routers.<svc>.rule=Host(`<sub>.${BASE_DOMAIN_FROM_VAULT}`)``, entrypoint/TLS iguais aos vizinhos, `traefik.http.services.<svc>.loadbalancer.server.port=<porta>`;
   - middleware do Authelia igual ao dos vizinhos protegidos (não invente nome).
4. **Volumes** — diretórios e entradas do `.env` no `server/ansible/playbooks/setup-<stack>-volumes.yml` correspondente; cite o playbook na página.
5. **Validar** — skill `validate-infra`; confira que toda `${VAR}` do compose existe no `.env.template`.
6. `dev.py index` e commit único.

## Fora do escopo desta skill

Implantar (`ansible-playbook`, Portainer, `docker compose up`) — liste esses passos para o usuário no final.
