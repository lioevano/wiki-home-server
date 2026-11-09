---
description: "Sysadmin no GCP: Hermes com memória Honcho numa e2-micro, executor com vault e SSH atrás de botões no Telegram, e a equipe de agentes pelo GitHub."
---

# Seção 19: Sysadmin no GCP

## Como funciona

Texto na Task 14.

## O que ele pode e o que não pode

Texto na Task 14.

## Rede e ACL

Texto na Task 14.

## Criar o sysadmin

Texto na Task 14.

## A equipe

Texto na Task 14.

## Arquivos

Arquivos desta seção (cada task acrescenta o seu):

- `docker/images/executor/executor/__init__.py` — docstring e versão do pacote do executor.
- `docker/images/executor/executor/config.py` — configuração do executor lida do ambiente (falha fechada) e a conversão para o `ops`.
- `docker/images/executor/executor/portao.py` — portão de aprovação: toda ação que muda a casa só roda com pedido aprovado pelo Léo no Telegram.
- `docker/images/executor/executor/remoto.py` — comandos remotos por Ansible ad-hoc e o validador dos comandos de diagnóstico.
- `docker/images/executor/executor/vault.py` — edita o vault do Ansible: troca o valor de uma folha do modelo e grava cifrado, de forma atômica, em `saida/vault.yml`.
- `docker/images/executor/executor/segredos.py` — canal de segredos: o Léo responde a um pedido no Telegram e o valor vai direto ao vault, sem passar pelo modelo, por log ou por mensagem.
- `docker/images/executor/executor/leitor.py` — leitor do Telegram do executor: cliques nos botões vão ao aprovador e mensagens ao canal de segredos.
- `docker/images/executor/executor/carteiro.py` — carteiro: sem modelo, consulta o repositório da equipe e acorda o sysadmin pelo webhook do Hermes (assinatura HMAC V2) quando há novidade para ele.
- `docker/images/executor/executor/ferramentas.py` — ferramentas MCP do executor: diagnóstico de leitura, comando e playbooks pelo portão de aprovação, pedido de segredos ao Léo e o comando de preparo do host.
- `docker/images/executor/executor/servidor.py` — ponto de entrada: sobe o leitor do Telegram e o carteiro em threads que se recuperam de erros e serve o MCP atrás do token.
- `docker/images/executor/executor/__main__.py` — `python -m executor` chama o `servidor.main`.
- `docker/images/executor/Dockerfile` — imagem do executor (FastMCP, ansible-core, git e ssh), como a do ops mais o aprovador; roda sem root.
- `docker/images/executor/.dockerignore` — deixa o cache do Python fora da imagem.
- `scripts/gcp/preparar-host.sh` — o comando único que o Léo cola no console do host Proxmox: Tailscale com a chave de uso único, usuário do Ansible com sudo e a chave SSH do sysadmin (repetível).
- `docker/images/sysadmin/Dockerfile` — imagem do sysadmin: Hermes Agent mais Ansible, `gh`, git, ssh, o ambiente do `tools/dev.py`, as coleções do Ansible (instaladas na construção) e o cliente do Honcho (`honcho-ai`); o contexto de build traz `requirements-dev.txt`, `wiki/requirements.txt` e `requirements.yml`.
- `ansible/templates/sysadmin/config.yaml.j2` — `config.yaml` do Hermes: modelos, memória no Honcho, executor por MCP, webhook da equipe e ferramentas desligadas.
- `ansible/templates/sysadmin/SOUL.md.j2` — identidade e regras do sysadmin (wiki primeiro, só por PR, tudo pelo executor, segredos só por `vault_preencher`).
- `ansible/templates/sysadmin/honcho.json.j2` — `honcho.json` do plugin: servidor próprio, workspace e pares.
- `ansible/templates/sysadmin/honcho-config.toml.j2` — `config.toml` do Honcho: só Gemini, sem Redis e sem telemetria.
- `scripts/gcp/separar_segredos.py` — separa o JSON do Secret Manager em arquivos por container no tmpfs `/run/sysadmin`: o sysadmin nunca recebe a senha do vault, a chave SSH nem a chave do Tailscale da casa; falha fechada se faltar campo.
- `docker/stacks/sysadmin/docker-compose.yml` — stack do sysadmin na VM da GCP: Hermes (gateway e painel em `127.0.0.1:9119`), executor e Honcho (API, deriver e banco), em redes separadas.
- `ansible/roles/infra/sysadmin-gcp/templates/firewall-sysadmin.sh.j2` — firewall da rede do sysadmin (cadeia `SYSADMIN` na tabela `raw` PREROUTING, pela bridge `br-sysadmin`): bloqueia o tailnet, a LAN de casa e o servidor de metadados da GCP.
- `ansible/playbooks/setup-sysadmin.yml` — configura a VM do sysadmin a partir dela mesma (`ansible-pull` da `main`, no primeiro boot e no timer diário): Docker sem Portainer, Tailscale com `tag:sysadmin` e o role `infra/sysadmin-gcp`; só o `main.yml` entra (por `vars_files`), nunca o vault, e fica fora do `full-deploy.yml`.
- `ansible/roles/infra/sysadmin-gcp/defaults/main.yml` — padrões do role: bucket (`<projeto>-sysadmin`), UIDs do Hermes e do executor, endereços do repositório e do Honcho, fuso dos containers.
- `ansible/roles/infra/sysadmin-gcp/tasks/main.yml` — swap de 4 GB, firewall, diretórios em `/opt/sysadmin`, os dois clones, o plugin do Honcho, as configurações do Hermes e do Honcho, as imagens `sysadmin` e `executor`, a stack, o painel pelo `tailscale serve` e os timers.
- `ansible/roles/infra/sysadmin-gcp/tasks/segredos.yml` — projeto da GCP pelo servidor de metadados, o `separar_segredos.py` em `/usr/local/lib/sysadmin/` e a unit dos segredos, executada na hora (o playbook a roda antes do Tailscale, que lê a chave do tmpfs).
- `ansible/roles/infra/sysadmin-gcp/templates/sysadmin-segredos.service.j2` — unit que, antes do Docker, lê o `sysadmin-segredos` do Secret Manager e o separa em `/run/sysadmin` (e traz o `vault.yml` de entrada do bucket, se ainda não houver um em `saida/`).
- `ansible/roles/infra/sysadmin-gcp/templates/firewall-sysadmin.service.j2` — unit que aplica o `firewall-sysadmin.sh` antes de cada (re)início do Docker.
- `ansible/roles/infra/sysadmin-gcp/templates/sysadmin-pull.service.j2` — o `ansible-pull` da `main` (de `/`, com o `ansible.cfg` do clone e sem `group_vars` automáticos, para o vault cifrado não ser lido).
- `ansible/roles/infra/sysadmin-gcp/templates/sysadmin-pull.timer.j2` — atualização diária às 05:17 UTC.
- `ansible/roles/infra/sysadmin-gcp/templates/sysadmin-backup.sh.j2` — backup da memória: `pg_dump` do banco do Honcho e o diretório do Hermes (sem `.env` nem `auth.json`) em `gs://<bucket>/backup/<data>/`.
- `ansible/roles/infra/sysadmin-gcp/templates/sysadmin-backup.service.j2` — unit do backup.
- `ansible/roles/infra/sysadmin-gcp/templates/sysadmin-backup.timer.j2` — backup diário às 06:07 UTC.
- `ansible/roles/infra/sysadmin-gcp/templates/sysadmin.env.j2` — `.env` da stack, só com valores não secretos: versões, caminhos, a sub-rede do sysadmin, os playbooks e as rotas do executor.

## Teste de ponta a ponta

Texto na Task 14.

## Falhas

Texto na Task 14.
