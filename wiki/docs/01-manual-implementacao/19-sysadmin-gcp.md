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
- `docker/images/sysadmin/Dockerfile` — imagem do sysadmin: Hermes Agent mais Ansible, `gh`, git, ssh, o ambiente do `tools/dev.py` e o cliente do Honcho (`honcho-ai`); o contexto de build traz `requirements-dev.txt` e `wiki/requirements.txt`.
- `ansible/templates/sysadmin/config.yaml.j2` — `config.yaml` do Hermes: modelos, memória no Honcho, executor por MCP, webhook da equipe e ferramentas desligadas.
- `ansible/templates/sysadmin/SOUL.md.j2` — identidade e regras do sysadmin (wiki primeiro, só por PR, tudo pelo executor, segredos só por `vault_preencher`).
- `ansible/templates/sysadmin/honcho.json.j2` — `honcho.json` do plugin: servidor próprio, workspace e pares.
- `ansible/templates/sysadmin/honcho-config.toml.j2` — `config.toml` do Honcho: só Gemini, sem Redis e sem telemetria.
- `scripts/gcp/separar_segredos.py` — separa o JSON do Secret Manager em arquivos por container no tmpfs `/run/sysadmin`: o sysadmin nunca recebe a senha do vault, a chave SSH nem a chave do Tailscale da casa; falha fechada se faltar campo.
- `docker/stacks/sysadmin/docker-compose.yml` — stack do sysadmin na VM da GCP: Hermes (gateway e painel em `127.0.0.1:9119`), executor e Honcho (API, deriver e banco), em redes separadas.
- `ansible/roles/infra/sysadmin-gcp/templates/firewall-sysadmin.sh.j2` — firewall da rede do sysadmin (cadeia `SYSADMIN` na tabela `raw` PREROUTING, pela bridge `br-sysadmin`): bloqueia o tailnet, a LAN de casa e o servidor de metadados da GCP.

## Teste de ponta a ponta

Texto na Task 14.

## Falhas

Texto na Task 14.
