# Pendências menores: Plano de implementação

> Execução direta no `main` (modo "direta"), pelo próprio Claude, com teste antes da correção quando há código ou template. Ledger em `.superpowers/sdd/pendencias-menores/progress.md`.

**Goal:** fechar as pendências menores dos sub-projetos 1, 2, 3, 4a, 4b, 4c1 e B, e devolver o CI `server-lint` ao verde.

**Spec:** `docs/superpowers/specs/2026-10-20-pendencias-menores-design.md`. Os números (#1…#55) abaixo são os da spec.

## Global Constraints

- Wiki-first: literal na wiki → `check` → `sync` → `sync --yes`. Os arquivos estruturais mudam direto, mas sempre citados na página.
- Ambiente: `export HOMESERVER_VENV=$HOME/.venvs/homeserver`. Os binários `agentgateway` 1.6.0 e `alloy` 1.20.0 ficam no `PATH`, para os testes que os usam rodarem.
- Cada task termina com `dev.py test`, `check` (só `REF-PENDING`), `build` e `lint`, e um commit temático com o trailer da sessão.
- Nada de `ansible-playbook` real, `docker compose up/down`, `ansible-vault` ou `ssh`. O push foi autorizado pelo Léo nesta sessão.

## Review Focus

1. Recusa de concorrência do runner não pode consumir o plano (#1). O tempo esgotado não pode deixar processo vivo (#2).
2. O cabeçalho `x-homeserver-cliente` só é confiável porque o `ops` exige o token interno. O `ops` não pode aceitar o cabeçalho sem o token (#3).
3. Regras do Authelia: a `deny` dos domínios de administração precisa vir depois da regra com `subject` e antes do curinga (#24). As políticas OIDC por cliente não podem deixar cliente sem política (#33).
4. `default-address-pools` (#50) não pode sobrepor a LAN `192.168.15.0/24`. O drop-in do Docker (#21) não pode **exigir** o NFS.
5. O `lint` com `--env-file` não pode esconder variável faltando no `.env.template`.

## Tasks

### Task 1: CI e `dev.py` (§2, #47)
- [ ] Teste: `test_cli.py`. O `lint` monta o env-file a partir do template, os valores vazios viram marcadores, e o `test` passa `-rs`.
- [ ] `tools/dev.py`: `_env_lint()` gera um arquivo temporário e passa `--env-file` ao `docker compose config -q`. Um aviso "variable is not set" vira falha.
- [ ] Rodar o `lint` e confirmar o verde.

### Task 2: 4c1 (#1–#13)
- [ ] `test_ops.py`: trava antes do plano, tempo esgotado com `killpg` e texto, cliente na auditoria, nome ambíguo exige `vm`.
- [ ] `ops/runner.py`, `ops/auditoria.py`, `ops/ferramentas.py`, `ops/portainer.py`, `ops/server.py` (cabeçalho → contexto).
- [ ] `agentgateway.yaml.j2`: `statefulMode`, `logging.fields.add.cliente` e o cabeçalho para o `ops`. Validar com o binário.
- [ ] `group_vars`: protegidos. Langfuse `TZ=UTC`. `.dockerignore`. `ansible.cfg` e compose `agents` sem as variáveis de contorno.
- [ ] Página 13: aceitos (#4, #12), deploy (#10).

### Task 3: 4b (#14–#21)
### Task 4: 4a (#22–#27)
### Task 5: 3 (#28–#36)
### Task 6: 2 (#37–#44)
### Task 7: 1 (#45–#50)
### Task 8: B (#51–#55)
### Task 9: roteiro "a conferir no primeiro deploy" (§4), `update-index`
### Task 10: revisão final em contexto novo e correções

Cada task de 3 a 8 segue o mesmo molde: teste em `tools/wikisync/tests/test_<área>.py` para cada template ou compose alterado, depois wiki → sync → arquivos estruturais → validação → commit.
