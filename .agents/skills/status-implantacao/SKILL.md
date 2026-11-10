---
name: status-implantacao
description: Use quando o Léo perguntar como está a implantação (ou mandar /status-implantacao) (fase atual, o que falta dele, pedidos abertos, gasto, memória da VM).
---

# Status da implantação

Responda curto, numa mensagem do Telegram, com estas cinco partes. Só leitura: nada aqui muda a casa.

## O que compõe o status (`/status-implantacao`)

1. **Fase atual.** Procure no repositório da equipe (`lioevano/homeserver-equipe`, o valor de `equipe_repo`) a issue `diario` aberta: `gh issue list -R lioevano/homeserver-equipe --label diario --state open`. Diga a fase, quantos passos da lista estão marcados e o que está em curso. Sem diário aberto, diga que nenhuma fase está em andamento e qual é a próxima do roteiro (`wiki/docs/01-manual-implementacao/18-roteiro-primeiro-deploy.md`).
2. **Pendências do Léo.** Os itens do diário que são dele e ainda não foram confirmados (contas, físico, telas com pessoa, stacks no Portainer, merges), cada um com o link da seção.
3. **Pedidos e aprovações abertos.**
   - Segredos: `vault_status()` (pedidos pendentes, gravados e quando o `saida/vault.yml` foi atualizado).
   - Botões esperando o Léo: os `aprovacao_id` que você mesmo pediu e ainda não usou (valem 30 minutos).
   - Pedidos da equipe: `gh issue list -R lioevano/homeserver-equipe --state open --label estado:aberto` e `--label estado:em-andamento`, com o papel de cada um (skill `equipe`).
   - PRs aguardando merge: `gh pr list --state open`.
4. **Gasto do mês.** Você não tem o valor: aponte onde ver. Modelo: console da Anthropic (teto de US$ 30/mês na implantação, US$ 10/mês depois). GCP: faturamento do projeto (alerta de orçamento em US$ 2; o esperado é zero, free tier). Nunca invente número.
5. **Memória da VM.** O `diagnostico(host, "free -m")` **não serve** para a própria VM do sysadmin (o executor recusa esse host). Rode `free -m` (e `df -h /`) no seu próprio terminal: dentro do container você lê o `/proc/meminfo` da VM, sem portão. Para os hosts de casa, `diagnostico` com `free -m` e `df -h` funciona.

## Formato

- Primeiro a frase de uma linha ("Fase 3, passo 4 de 7; esperando o Léo no Portainer").
- Depois as partes acima, só as que têm algo a dizer. Link do diário no fim.
- Sem segredos, sem saída bruta longa.

## Erros comuns

| Erro | Correção |
|---|---|
| Responder de memória | Consulte o diário, `vault_status` e o `gh` agora. |
| Citar um gasto "estimado" | Diga onde olhar. |
| Rodar `diagnostico` para a memória da VM do sysadmin | Rode `free -m` no seu terminal. |
