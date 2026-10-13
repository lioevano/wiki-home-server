---
name: remove-app
description: Use when the user wants to remove, decommission or uninstall an application or service from the homeserver (Docker stacks or Ansible-installed apps).
---

# Remover uma aplicação

Fontes: catálogo `wiki/docs/02-visao-geral-arquitetura/09-catalogo-aplicacoes.md` e índice de integrações `wiki/docs/02-visao-geral-arquitetura/10-indice-integracoes.md`.

## 1. Verificar se é provedora

Leia a coluna **Provê** da aplicação. Se ela provê alguma integração **e** existe consumidor (aplicação cuja "Aplica-se a" é verdadeira):
- **pare** e informe: "`<app>` provê `<id>` para: <consumidores>". Ofereça `remove-integration <id>` (desliga em todos e só então remove o provedor) ou substituir o provedor. Não continue sem a decisão do usuário.

## 2. Montar o plano

1. Liste as integrações ativas da aplicação (regras "Aplica-se a" + Ajustes).
2. Para cada uma, copie os passos de **"Ao remover (por consumidor)"** da seção do índice, concretizados com arquivos e linhas reais.
3. Acrescente: linha do catálogo; seção/menções na página da aplicação; `INDEX.md` (via `update-index`).
4. Variáveis: remover **só** as que nenhum outro serviço usa (`grep -rn '\${VAR' server/docker/stacks/*/docker-compose.yml` para cada uma). Diretórios/variáveis do playbook de volumes: idem.
5. Dados: **nunca** apagar; passo manual de arquivamento.
6. Menções à aplicação em páginas genéricas: remover a menção ou substituí-la por texto neutro — **não** introduzir outra aplicação que não está no catálogo.

Formato do plano (mostre ao usuário):

```markdown
### Plano: remover `<app>`
| # | Integração / regra | Arquivo ou página | Ação |
|---|---|---|---|
### Passos manuais (fora do repositório)
- redeploy da stack no Portainer; Public Hostname específico (se houver); arquivamento dos dados
```

## 3. Aprovação

**Pare e peça aprovação do plano.** Só continue com um "sim" explícito.

## 4. Executar

Siga `wiki-first-change`: catálogo e páginas primeiro (blocos literais na wiki → `dev.py check` → `dev.py sync` → `--yes`), depois os arquivos estruturais.

## 5. Verificar e fechar

1. Carregue e siga a skill `audit-integrations` (não substitua por script próprio) com escopo da integração afetada **e** as regras (sobra) — não pode restar `⚠️` ligado à aplicação removida nem `❌` novo em outras aplicações.
2. `grep -rIin <app>` fora de `docs/superpowers` e `wiki/site`: só podem sobrar menções intencionais (explique cada uma).
3. `update-index`, `validate-infra`, commit único.
4. Relate: arquivos alterados, passos manuais pendentes, achados pré-existentes (não corrigidos).
