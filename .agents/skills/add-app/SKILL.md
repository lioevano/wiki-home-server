---
name: add-app
description: Use when the user wants to add, install, deploy or expose a new application or service in the homeserver (Docker stacks core, apps, ai, or via Ansible).
---

# Adicionar uma aplicação

Fontes: catálogo `wiki/docs/02-visao-geral-arquitetura/09-catalogo-aplicacoes.md` e índice de integrações `wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md`.

## 1. Pesquisar

Consulte a documentação oficial da aplicação e anote (com links, que irão para a página da wiki):
- imagem e **versão estável fixa** (nunca `latest`); porta interna; variáveis obrigatórias; volumes persistentes; healthcheck;
- endpoint de métricas (`/metrics`?); suporte a OIDC/SSO; necessidade de banco/cache (viram serviços auxiliares);
- se usa SQLite ou exige disco local (Dados = `local`).

## 2. Escrever a linha do catálogo (rascunho)

Preencha todas as colunas. O que o usuário não disse e a pesquisa não resolve → `?` e **pergunte** antes de seguir (exposição, subdomínio e categoria são decisões dele).

## 3. Montar o plano

1. Avalie "Aplica-se a" de **todas** as integrações com a linha nova (+ Ajustes).
2. Para cada integração que se aplica, concretize os passos de **"Ao adicionar (por consumidor)"** com arquivos reais. Copie o padrão de um serviço vizinho da mesma stack (labels, redes, middleware **exatamente** `authelia-forwardauth@docker`).
3. Se a aplicação **provê** uma integração (coluna Provê), inclua no plano a oferta de `add-integration` para ligá-la nos consumidores.
4. Inclua: seção na página da stack (com as fontes da pesquisa), linha do catálogo, `update-index`.

Use o formato de plano da skill `remove-app` (título "Plano: adicionar `<app>`").

## 4. Aprovação

**Pare e peça aprovação do plano.** Só continue com um "sim" explícito.

## 5. Executar, verificar e fechar

1. `wiki-first-change`: catálogo e páginas (blocos literais) → `dev.py check` → `sync` → `--yes`; depois compose, playbook de volumes e templates.
2. Carregue e siga a skill `audit-integrations` (não substitua por script próprio) com `app=<id>`: sem `❌`/`⚠️` atribuível à aplicação nova (`✋` de passo manual é aceito e vai para o relatório).
3. `update-index`, `validate-infra`, commit único; relate passos manuais (deploy no Portainer, Public Hostname, primeiro login).
