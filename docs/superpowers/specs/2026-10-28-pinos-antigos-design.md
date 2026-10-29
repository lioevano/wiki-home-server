# Design: migração dos pinos antigos (Traefik v3, Authelia 4.39, cloudflared, Portainer, Postgres)

- **Data:** 2026-10-28
- **Autor:** Léo Ivan (com Claude)
- **Status:** decidido de forma autônoma, a pedido do Léo ("pode seguir da mesma forma autônoma com os demais pontos").
- **Caminho:** bounded+. Troca versões da stack `core`, do Portainer e dos Postgres; ajusta a configuração do Traefik e do Authelia ao que as versões novas pedem. Não muda a arquitetura.
- **Origem:** decisão V5 da política de versões (`2026-10-21-politica-de-versoes-design.md`), que deixou esses pinos para uma migração própria.

## 1. Por que agora

- **Nada foi implantado.** Migrar hoje é trocar texto. Depois do deploy, cada um destes viraria uma migração com dados (o Postgres, principalmente).
- **O Docker 29 quebra os pinos atuais.** O role `infra/docker` instala o Docker mais novo (`docker_ce_version: ""`), e o Docker 29 subiu a versão mínima da API para 1.44. O Traefik v2.11.2 e o Portainer 2.19.4 falam uma API mais antiga e param de enxergar os containers.

## 2. Decisões

| # | Tema | Escolha | Por quê |
|---|---|---|---|
| P1 | Traefik | `v2.11.2` → **`v3.7.16`** | Última estável. As regras do repositório são todas `Host(...)` simples, que valem igual na v3. As opções de headers usadas (`browserXssFilter`, `customFrameOptionsValue`, `sts*`) continuam na v3. |
| P2 | Traefik: entrypoints | `http.aliasHeadersStrategy: delete` nos dois entrypoints | A v3.7 avisa no início quando falta. Com o forward-auth do Authelia (`Remote-User`, `Remote-Groups`), um cabeçalho `Remote_User` forjado poderia ser lido como o verdadeiro por um backend que normaliza nomes; `delete` o descarta. Nenhum app do repositório usa cabeçalho com `_`. |
| P3 | Traefik: ACME | O comentário do `delayBeforeCheck` vira `propagation.delayBeforeChecks` (nome da v3.3+) | Só comentário; o padrão continua. |
| P4 | Authelia | `4.38.0` → **`4.39.28`** | Última estável. |
| P5 | Authelia: forward-auth | `/api/verify?rd=…` → **`/api/authz/forward-auth`**, com `maxResponseBodySize: 8192` (o exemplo oficial) | O `/api/verify` é legado na 4.39. O endpoint novo tira a URL do portal de `session.cookies[].authelia_url`. |
| P6 | Authelia: sessão | `session.domain` e o `default_redirection_url` da raiz → **`session.cookies`** com `domain`, `authelia_url: https://auth.<domínio>` e `default_redirection_url: https://home.<domínio>` (o painel) | Forma atual (as chaves antigas são aceitas só com aviso). O `default_redirection_url` não pode ser o próprio portal. |
| P7 | Authelia: `jwt_secret` | Raiz → `identity_validation.reset_password.jwt_secret` | Mesma razão: chave antiga só com aviso. |
| P8 | Authelia: claims do ID token | Política `legado` em `claims_policies` (`rat`, `groups`, `email`, `email_verified`, `alt_emails`, `preferred_username`, `name` no ID token) e `claims_policy: "legado"` nos cinco clientes | A 4.39 passou a pôr no ID token só os claims padrão. Os clientes foram configurados contra o comportamento da 4.38; o Langfuse (NextAuth) e o mcp-auth-proxy leem o perfil do ID token. É a configuração "restaurar o comportamento anterior" da documentação do Authelia. |
| P9 | cloudflared | `2024.5.0` → **`2026.10.5`** | Última. O comando (`tunnel --no-autoupdate --metrics … run --token`) não muda. |
| P10 | Portainer | `2.19.4` → **`2.45.3`** (servidor e agente, a LTS atual) com `--http-enabled` | Funciona com o Docker 29. O `ops` fala com `http://portainer:9000` na rede `proxy`; o flag garante a porta HTTP. A imagem do servidor passa a vir de `portainer_ce_image` (antes estava repetida na tarefa). |
| P11 | Postgres | `15`, `15.6` e `16` → **`17-alpine`** (Authelia, Grafana, Nextcloud, LiteLLM; o Langfuse já usava) | Sem dados, a versão principal sai de graça agora; depois, cada troca exige dump e restauração. O 18 fica de fora: a imagem mudou o caminho do `PGDATA`, e os volumes do repositório montam `/var/lib/postgresql/data`. O do Immich segue a versão do Immich. |
| P12 | Defaults mortos | Saem `roles/infra/traefik-config/defaults/main.yml` e `roles/infra/authelia-config/defaults/main.yml` | Nenhuma variável deles era usada, e as versões que traziam (v2.11.2, 4.38.0, Postgres 15.6) já contradiziam o compose. A versão da stack `core` mora só no compose (página 05). |
| P13 | Teste | `test_authelia_validate_config` só roda quando o binário `authelia` do ambiente é a versão fixada no compose; senão pula dizendo a diferença | Um binário 4.38 rejeitaria as chaves da 4.39 (`claims_policies`) e o teste falharia por motivo errado. |

## 3. Riscos

- **Sem validação real do Authelia 4.39 neste ambiente:** o binário disponível aqui é o 4.38. A configuração segue a documentação da 4.39.28 (exemplos do próprio repositório do Authelia), e o roteiro "A conferir no primeiro deploy" ganha `docker logs authelia` sem erros nem avisos de chave obsoleta.
- **Traefik v3 com o Cloudflare Tunnel:** nada muda no caminho (o túnel chega ao `https://traefik:443` com *No TLS Verify*).
- **Portainer 2.45:** a primeira tela pede o admin como antes; o `ops` usa a API `/api/stacks` e `/api/endpoints`, estáveis nessas versões.

## 4. Correções da revisão final (2026-10-28)

- **`instance_name` não existe no schema** (nem na 4.38): na 4.39 a chave desconhecida é erro fatal e o Authelia não sobe. Saiu. O `validate-config` da 4.38 saía com 0 mesmo com erros, por isso o teste não pegou. Agora:
  - `test_authelia_so_chaves_validas` confere cada chave do config renderizado contra o schema da versão fixada (`tools/wikisync/tests/dados/authelia-4.39.28-chaves.txt`);
  - o `validate-config`, quando o binário da versão fixada existe, exige "loaded successfully without errors".
- **Forward-auth com `trustForwardHeader: "false"`**: com `true`, um `X-Forwarded-Host` forjado pela internet passava pelo cloudflared (proxy confiável), e o Authelia avaliava outro domínio (um `bypass`) enquanto o Traefik entregava o domínio real. Isso expunha o Prometheus, o painel do Traefik, a Homepage e as *arr. O problema vinha de antes da migração. O preço: o Authelia vê o IP do cloudflared, e o bloqueio por tentativas erradas continua por usuário. O roteiro do primeiro deploy ganhou o teste com `curl`.
- **Portainer:** a 9000 (HTTP, com `--http-enabled`) deixou de ser publicada na LAN; o `ops` a usa só pela rede `proxy`.
- **Traefik:** o entrypoint `traefik` do `/ping` foi declarado com `aliasHeadersStrategy` (sem isso, a v3.7 avisa).
- Textos: nível `WARN`, o que o `delete` descarta, `HostRegexp` da v3, `identity_validation` no troubleshooting e a docstring do `ops`.
