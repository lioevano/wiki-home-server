---
description: "Estratégia de IA híbrida com LiteLLM: quando usar modelos locais no Ollama ou APIs externas, com foco em custo."
---

# Estratégia de APIs de LLM e Arquitetura Híbrida de IA

Com a introdução do LiteLLM em nossa stack, a capacidade de processamento de linguagem do nosso home server evolui de um sistema puramente local para uma **arquitetura de IA híbrida, elástica e consciente dos custos**. Esta página aprofunda a visão estratégica por trás dessa abordagem, detalhando como, quando e por que utilizar modelos de linguagem locais (via Ollama) versus modelos de ponta na nuvem (via APIs externas).

O objetivo não é substituir o Ollama, mas sim aumentá-lo, criando um sistema inteligente que utiliza o recurso certo para a tarefa certa, otimizando a relação entre performance, custo e privacidade.

## O Modelo Híbrido: O Melhor de Dois Mundos

A combinação de LLMs locais e em nuvem nos permite superar as limitações inerentes de cada abordagem quando usadas isoladamente.

| Característica | Ollama (Local) | APIs Externas (Nuvem) |
| :--- | :--- | :--- |
| **Performance** | Limitada pelo hardware (GPU/RAM). Rápido para modelos pequenos. | Acesso a modelos de última geração (SOTA). Altamente escalável. |
| **Custo** | Custo de capital (hardware) e energia. Custo marginal por inferência é zero. | Custo operacional (pago por token). Pode se tornar caro com uso intenso. |
| **Privacidade** | Máxima. Os dados nunca saem da sua rede local. | Os dados são enviados para o provedor da API. Requer confiança nas políticas de privacidade do provedor. |
| **Disponibilidade** | Dependente da estabilidade do seu servidor e conexão. | Alta disponibilidade garantida pelo provedor de nuvem (SLA). |
| **Manutenção** | Requer gerenciamento de modelos, drivers e atualizações. | Nenhuma manutenção de modelo ou infraestrutura necessária. |

Nossa estratégia visa combinar esses pontos fortes. O diagrama a seguir ilustra o fluxo de decisão que o LiteLLM nos permite implementar:

```mermaid
graph TD
    A[Aplicação Cliente \n(Open WebUI, n8n, Script Custom)] -- Requisição API OpenAI-Compatible --> B(LiteLLM Proxy);

    subgraph LiteLLM - Lógica de Roteamento
        B -- Avalia a Requisição --> C{Qual modelo foi solicitado?};
        C -- Modelo Específico \n(ex: "gpt-4o") --> D[Roteia para API Externa Específica];
        C -- Modelo Genérico \n(ex: "modelo-chat") --> E{Roteamento Inteligente};
    end

    subgraph Roteamento Inteligente
        E -- Requisição Simples? \n(Baixo número de tokens, prompt curto) --> F[Ollama (Local)];
        E -- Requisição Complexa? \n(Análise de documento, geração de código) --> G[API Externa (Fallback)];
    end

    subgraph Endpoints de IA
        F -- Conecta-se via IP local --> H[Serviço Ollama \n(llama3, phi3, etc.)];
        G -- Tenta o 1º da lista --> I(API do Google Gemini);
        I -- Falhou ou Timeout? --> J(API da Anthropic);
        J -- Falhou ou Timeout? --> K(API da OpenAI);
    end

    D --> I;
    D --> J;
    D --> K;

    H -- Resposta --> B;
    I -- Resposta --> B;
    J -- Resposta --> B;
    K -- Resposta --> B;

    B -- Resposta Unificada --> A;
```

## Estratégias de Roteamento e Casos de Uso

O roteamento do homeserver é feito por **apelidos** declarados em `llm_models` (`group_vars/all/main.yml`) e renderizados no `config.yaml` do LiteLLM ([Stack de IA](../01-manual-implementacao/08-stack-ia.md#modelos-e-apelidos)). O cliente escolhe a intenção; o código decide o modelo.

| Apelido | Estratégia | Exemplos de uso |
|---|---|---|
| `rapido` | custo baixo e latência baixa | resumir, classificar, responder notificações, automações do n8n |
| `principal` | qualidade | análise de documentos, geração de código, textos técnicos |
| `local` | privacidade e custo zero | dados que não devem sair de casa; tarefas leves |
| `decisao` | decisão tipada (Jev) | triagem, roteamento, "aprovar ou não" dentro de automações e agentes |

* **Fallback:** `principal` e `rapido` têm um modelo de outro provedor como reserva (`llm_fallbacks`): se a Anthropic cair, a chamada vai para a OpenAI sem o cliente perceber.
* **Modelo específico:** quando a tarefa exige um modelo exato, o cliente pede pelo nome próprio (ex.: `claude-opus-5-5`), que também está no `llm_models`. O Claude Code usa sempre nomes de modelos Claude.
* **Trocar de LLM:** muda-se o `model` do apelido e roda-se o `setup-ai-volumes.yml`; nenhum cliente é alterado.
* **Contexto pessoal (segundo cérebro):** as notas e os documentos não passam pelo gateway: a busca e os embeddings rodam localmente no qmd, e o Claude (app, claude.ai, Claude Code) ou o Open WebUI só leem o trecho que consultam pelos MCPs `notas` e `escrita` ([Segundo cérebro](../01-manual-implementacao/12-segundo-cerebro.md)). O modelo que responde continua sendo escolhido pelo cliente.

## Gerenciamento de Custos e Orçamentos

O maior risco de uma arquitetura híbrida é o custo inesperado com APIs externas. No homeserver:

*   **Orçamento por cliente:** cada cliente tem uma chave virtual própria (`litellm_client_keys`) com orçamento mensal (`litellm_key_budgets`), aplicado pelo `setup-ai-keys.yml`. Estourou, aquele cliente recebe erro; os outros seguem.
*   **Alerta de gasto:** o Prometheus raspa as métricas do LiteLLM e o alerta `llm-gasto-alto` avisa no Telegram quando o gasto das últimas 24 h passa de `llm_gasto_diario_alerta`.
*   **Observabilidade:** a tela do LiteLLM em `https://llm.seudominio.com` (atrás do Authelia) mostra gasto, tokens e chamadas por chave e por modelo. O rastreamento passo a passo de agentes (Langfuse) entra com os agentes.
*   **Cache:** o cache de respostas do LiteLLM não está ligado; pode ser acrescentado em `litellm_settings` se houver muitas perguntas repetidas.

Ao adotar esta arquitetura de IA híbrida, seu home server se torna uma plataforma de IA resiliente e flexível, com um único lugar para trocar modelos, controlar custos e ver o uso.
