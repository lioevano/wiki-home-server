# Design: segundo cérebro (vaults do Obsidian sincronizados, busca local e MCP com escopo por vault)

- **Data:** 2026-10-20
- **Autor:** Léo Ivan (com Claude)
- **Status:** aguardando revisão
- **Caminho:** arquitetural — sub-projeto **4b** da refatoração do server (1 Alloy ✓, 2 mídia ✓, 3 fotos e arquivos ✓, 4a fundação de IA ✓, **4b segundo cérebro**, 4c agentes; VPN à parte).
- **Depende de:** fundação de IA (stack `ai`, Open WebUI), fotos e arquivos (Authelia OIDC, dataset `files` do Nextcloud), Alloy (métricas do host e journal), painel e notificações (regras de alerta do Grafana).

## 1. Objetivo

Um **segundo cérebro** com três vaults do Obsidian — **Pessoal**, **Trabalho** e **Estudos** — editados no PC Linux e no Android, sincronizados com o servidor, **indexados localmente** junto com os documentos do Nextcloud e expostos por **MCP** ao Claude Code (PC), ao app Claude (claude.ai e celular), ao Open WebUI e aos agentes da 4c, com **escopo por vault**:

| Vault | Claude pode |
|---|---|
| Pessoal | buscar e ler |
| Trabalho | buscar, ler, criar, editar e mover |
| Estudos | buscar, ler, criar, editar e mover |
| Documentos (Nextcloud) | buscar e ler (cópia convertida em Markdown) |

### Critérios de pronto

- Dataset `data/notes` (com cota) exportado e montado só na `ai-desktop-vm`; snapshots automáticos só nele.
- Stack `notes` na `ai-desktop-vm` com `syncthing`, `qmd`, `notes_escrita`, `mcp_auth_busca`, `mcp_auth_escrita`; imagens com versão fixada.
- O container de busca monta os vaults **somente leitura**; o de escrita monta **só** `trabalho/` e `estudos/`; nenhum serviço de escrita enxerga `pessoal/` nem os arquivos do Nextcloud.
- Conectores `notas.<domínio>` (busca) e `escrita.<domínio>` (escrita) funcionando no claude.ai e no Claude Code com login pelo Authelia (2FA, grupo `admins`); Open WebUI usando os dois pela rede interna.
- Documentos do Nextcloud convertidos e indexados de forma incremental; arquivo apagado no Nextcloud sai do índice.
- Página nova **12 · Segundo cérebro**, catálogo e índice atualizados, `audit-integrations` sem ❌/⚠️.
- `dev.py test`, `check` (só `REF-PENDING`), `build` estrito e `lint` passam.

## 2. Decisões

| # | Decisão | Escolha |
|---|---|---|
| B1 | Abordagem | **Arquivos puros + busca só leitura + escrita com escopo** (escolhida). O basic-memory foi descartado: ele sempre grava `permalink:` no cabeçalho de toda nota (inclusive no Pessoal) e não tem projeto só leitura. O Knowledge do Open WebUI foi descartado: só existe dentro do Open WebUI. MCPs que dependem do Obsidian aberto (plugin Local REST API) não servem num servidor sem tela. |
| B2 | Sincronização | **Syncthing**: nó sempre ligado no servidor, pareado com o PC (Syncthing) e o celular (Syncthing-Fork). Uma pasta Syncthing por vault. Fora de casa pelos **relays** (criptografia ponta a ponta); com o Tailscale (sub-projeto próprio), conexão direta. |
| B3 | Armazenamento | Dataset novo `data/notes` (cota inicial 20G), NFS só para a `ai-desktop-vm`, com `pessoal/`, `trabalho/`, `estudos/`. Configuração e chaves do Syncthing em `docker-volumes`; banco interno do Syncthing no disco local (`{{ vm_local_data_path }}/syncthing`), porque SQLite em NFS é arriscado e o banco se reconstrói com uma varredura. |
| B4 | Desfazer | `zfs-auto-snapshot` instalado no host Proxmox **só para `data/notes`** (propriedade `com.sun:auto-snapshot=false` no pool `data`, `true` em `data/notes`): a cada 15 min (guarda 8), de hora em hora (24), diário (14). A mídia e o resto não ganham snapshots automáticos. |
| B5 | Busca | **qmd** (MIT): BM25 + vetorial + reranking com modelos GGUF locais (node-llama-cpp), coleções `pessoal`, `trabalho`, `estudos`, `documentos`, MCP HTTP **só leitura** (`query`, `get`, `multi_get`, `metadata`, `status`). Imagem local `localhost/homeserver/qmd:<versão>` com Vulkan (mesmo esquema do Ollama), iGPU por `/dev/dri`; sem GPU, CPU. Vaults montados `:ro`. Embeddings locais, sem custo e sem mandar notas para fora para indexar. |
| B6 | Escrita | MCP oficial **`@modelcontextprotocol/server-filesystem`** (stdio), exposto em HTTP pelo **supergateway**, numa imagem local `localhost/homeserver/notes-escrita:<versão>`. Monta **apenas** `trabalho/` e `estudos/` (rw). O servidor não tem ferramenta de apagar; `move_file` não sobrescreve destino existente. |
| B7 | Documentos do Nextcloud | **Todos os arquivos do usuário** (exceto mídia): o dataset `files` é montado **só leitura** na `ai-desktop-vm`; um conversor (**markitdown**) gera Markdown de PDF, DOCX, PPTX, XLSX, HTML, CSV, TXT e MD em `{{ vm_local_data_path }}/notes-documentos` (regerável, fora de backup). Incremental por manifesto (caminho, tamanho, mtime); arquivo apagado ou movido no Nextcloud sai da cópia. Lista de extensões e pastas excluídas em variáveis. |
| B8 | Acesso remoto | Dois **mcp-auth-proxy** (`ghcr.io/sigbit/mcp-auth-proxy:<versão>`), um por MCP, com OAuth 2.1 + registro dinâmico de cliente (exigido pelo claude.ai) e login delegado ao Authelia (cliente OIDC novo `mcp`, `two_factor`, PKCE S256, `--oidc-allowed-attributes /groups=admins`). Subdomínios `notas.` (busca) e `escrita.` (escrita) pelo túnel; Traefik (file provider) sem middleware do Authelia nesses dois, porque o próprio proxy autentica. |
| B9 | Acesso interno | Rede Docker `notes_mcp` (criada pela stack `notes`), à qual o `open-webui` se junta como rede externa; Open WebUI e agentes da 4c falam com `http://qmd:8181/mcp` e `http://notes_escrita:8000/mcp` sem passar pela internet. Nenhuma porta dos MCPs sem autenticação é publicada na LAN. |
| B10 | Atualização | Timers systemd na `ai-desktop-vm`: `notes-documentos` (conversor, a cada 10 min) e `notes-indice` (`qmd update` + `qmd embed`, a cada 10 min, depois do conversor). Falha de timer gera alerta. |
| B11 | Claude Code | Os mesmos dois endereços (`claude mcp add --transport http notas https://notas.<domínio>/mcp`, idem `escrita`), login OAuth no navegador. Ele também lê o vault local sincronizado no PC. |
| B12 | Um conector ou dois | Dois agora (busca e escrita). Um gateway que una todos os MCPs fica para a 4c, onde surgem os MCPs de controle do servidor. |

## 3. Serviços (stack `notes`, `docker/stacks/notes/docker-compose.yml`, na `ai-desktop-vm`)

| Serviço | Imagem | Redes | Portas | Montagens |
|---|---|---|---|---|
| `syncthing` | `docker.io/syncthing/syncthing:<versão fixada>` | `notes_network` | `${AI_DESKTOP_VM_IP}:8384` (painel, Traefik), `22000/tcp+udp`, `21027/udp` | `${NOTES_STACK_DATA_PATH}:/var/syncthing/notes` (rw); config ← NFS; banco ← disco local |
| `qmd` | `localhost/homeserver/qmd:<versão>` (`pull_policy: never`, `diun.enable: "false"`) | `notes_network`, `notes_mcp` | nenhuma | vaults `:ro`; `${NOTES_STACK_DOCUMENTOS_PATH}:/notes/documentos:ro`; índice e modelos ← disco local; `/dev/dri`, `group_add ${AI_RENDER_GID}` |
| `notes_escrita` | `localhost/homeserver/notes-escrita:<versão>` | `notes_mcp` | nenhuma | **só** `trabalho/` e `estudos/` (rw) |
| `mcp_auth_busca` | `ghcr.io/sigbit/mcp-auth-proxy:<versão>` | `notes_mcp` | `${AI_DESKTOP_VM_IP}:8481:80` (Traefik) | dados (BoltDB) ← NFS |
| `mcp_auth_escrita` | idem | `notes_mcp` | `${AI_DESKTOP_VM_IP}:8482:80` (Traefik) | dados ← NFS |

- `syncthing`: `PUID/PGID` do `dockeruser` (escrita NFS com all_squash), `STGUIADDRESS=0.0.0.0:8384`; GUI com usuário e senha (vault) além do Authelia; versionamento "staggered" nas pastas do PC e do celular (documentado), porque no servidor ele só guarda versões de mudanças que chegam de outros aparelhos.
- `qmd`: comando `qmd mcp --http --host 0.0.0.0 --port 8181`; `QMD_ALLOWED_HOSTS=qmd`; configuração `index.yml` gerada pelo Ansible (coleções, máscara `**/*.md`, `ignore: [".obsidian/**", ".trash/**"]`, contexto por coleção); `QMD_EMBED_MODEL` em variável (padrão do qmd; alternativa multilíngue documentada).
- `notes_escrita`: `supergateway --stdio "mcp-server-filesystem /notes/trabalho /notes/estudos" --outputTransport streamableHttp --port 8000`; roda como `dockeruser`.
- `mcp_auth_*`: `EXTERNAL_URL=https://notas.<domínio>` / `https://escrita.<domínio>`, `NO_AUTO_TLS=true`, `LISTEN=:80`, `OIDC_CONFIGURATION_URL=https://auth.<domínio>/.well-known/openid-configuration`, `OIDC_CLIENT_ID=mcp`, `OIDC_CLIENT_SECRET`, `OIDC_SCOPES=openid,profile,email,groups`, `OIDC_ALLOWED_ATTRIBUTES=/groups=admins`, `AUTH_HMAC_SECRET` (vault), `TRUSTED_PROXIES` = IP da `core-services-vm`; backend `http://qmd:8181/mcp` e `http://notes_escrita:8000/mcp`.

## 4. Fluxo

```
PC (Obsidian + Syncthing) ─┐                       ┌─ qmd (:ro em todos) ── mcp_auth_busca ── notas.<dom> ─┐
                           ├─ Syncthing (servidor) ┤                                                         ├─ túnel ─ claude.ai / Claude Code
Celular (Syncthing-Fork) ──┘    data/notes (ZFS)   └─ notes_escrita (só trabalho/estudos) ─ mcp_auth_escrita ─ escrita.<dom> ─┘
Nextcloud (files, :ro) ── conversor (markitdown) ── notes-documentos (local) ── qmd
Open WebUI / agentes 4c ── rede notes_mcp ── qmd, notes_escrita
```

Uma edição feita pela IA em `trabalho/` é gravada no NFS pelo `notes_escrita`, detectada pelo Syncthing (inotify da própria VM ou varredura periódica) e propagada para o PC e o celular; o próximo `notes-indice` a indexa.

## 5. Dados e backup

| Dado | Onde | Proteção |
|---|---|---|
| Vaults | `data/notes` (NFS) | snapshots automáticos (B4) + cópias completas no PC e no celular |
| Configuração e chaves do Syncthing, dados dos mcp-auth-proxy | `docker-volumes` (NFS) | como o resto de `docker-volumes` |
| Banco do Syncthing, índice e modelos do qmd, documentos convertidos | disco local (`{{ vm_local_data_path }}`) | regeráveis (varredura, `qmd update`/`embed`, conversor); regra DAD-5 com a justificativa "regerável" |

## 6. Integrações

| Integração | Mudança |
|---|---|
| Host Proxmox | Export NFS de `data/notes` e de `data/files` (este já existe) — `files` passa a ser montado na `ai-desktop-vm` **com `ro` na montagem**; `zfs-auto-snapshot` com a propriedade por dataset (B4); página 02 ganha `zfs create -o quota=20G data/notes` e o `chown`. |
| Base das VMs | `roles/common`: montar `notes` (rw) e `files` (ro) na `ai-desktop-vm`. Conferir no plano a condição `'ai-desktop-vm' in group_names` (nome do grupo no inventário) usada hoje para `rag_sources`. |
| Authelia | Cliente OIDC `mcp` (`two_factor`, PKCE S256, método de autenticação conferido no plano), redirects `https://notas.<domínio>/.auth/oidc/callback` e `https://escrita.<domínio>/.auth/oidc/callback`; `oidc_clients.mcp.{secret,secret_digest}` no vault. |
| Traefik (file provider) | `dynamic_rag_services.yml.j2`: routers `notas.` → `:8481` e `escrita.` → `:8482` **sem** Authelia; `sync.` → `:8384` **com** Authelia. |
| Cloudflare | Public Hostnames `notas`, `escrita`, `sync` (ou o curinga, se existir), conforme a página 05. |
| Open WebUI | Junta-se à rede externa `notes_mcp`; dois servidores MCP (Streamable HTTP) cadastrados como ferramentas (conferir no plano o suporte na v0.12.3 e se dá para declarar por variável de ambiente, já que `ENABLE_PERSISTENT_CONFIG=false`). |
| Prometheus | Job `syncthing` (`/metrics` com o token da API do Syncthing, do vault); blackbox em `notas.`/`escrita.` (`/.well-known/oauth-protected-resource`) e `syncthing` (`/rest/noauth/health`). |
| Alloy | `prometheus.exporter.unix` com o coletor `systemd` restrito a `notes-*` na `ai-desktop-vm`. |
| Grafana (alertas) | `notes-timer-falhou`: `node_systemd_unit_state{name=~"notes-.*", state="failed"} == 1`; `syncthing-pasta-com-erro` se o Syncthing reportar erros de pasta. |
| Homepage | `syncthing` (`sync.`) e `notas` com `siteMonitor` pela LAN. |
| Catálogo | Linhas novas: `syncthing` (stack `notes`, protegida, `sync`, métricas sim), `qmd` + `notes_escrita` + `mcp_auth_*` (pública com OAuth próprio, `notas`/`escrita`). Exposição "pública com autenticação própria" conferida contra as regras do índice. |
| Índice | Regra nova **MCP-1**: todo MCP exposto fora da LAN passa por `mcp-auth-proxy` com OIDC do Authelia e restrição de grupo; MCPs sem autenticação só em rede Docker interna. Regra **MCP-2**: escopo de escrita da IA é garantido por montagem (o que não está montado não existe), nunca só por instrução. |
| Vault | `oidc_clients.mcp.{secret,secret_digest}`, `mcp_auth_hmac_secret`, `syncthing_gui_password`, `syncthing_api_key`. |

## 7. Páginas

- **Nova: `01-manual-implementacao/12-segundo-cerebro.md`** — arquitetura, criação do dataset, deploy da stack, pareamento (PC, celular, aceitar as pastas, versionamento nos aparelhos, `.stignore` para `.obsidian/workspace*.json`), conectores no claude.ai (Configurações → Conectores → URL `https://notas.<domínio>/mcp`; login; o que cada um permite), Claude Code (`claude mcp add`), Open WebUI, como desfazer uma edição (`zfs list -t snapshot data/notes`, `.zfs/snapshot/...`, `zfs rollback` só em último caso), conversor do Nextcloud (extensões, o que fica de fora), falhas, teste de ponta a ponta. Blocos literais dos arquivos novos.
- **Editadas:** 00 (`.env.template`), 01 (vault), 02 (dataset, exports, `zfs-auto-snapshot`), 04 (montagens), 05 (routers, Public Hostnames, cliente OIDC), 08 (Open WebUI com os MCPs), 09 (sondas, painel, alertas), backup, `02-visao-geral-arquitetura/03-armazenamento-zfs-nfs.md`, `07-apis-llm-estrategia.md`, guia 12 (snapshots), catálogo, índice, `INDEX.md`, navegação.

## 8. Falhas

| Falha | Comportamento | O que fazer |
|---|---|---|
| Servidor fora | Obsidian segue funcionando nos aparelhos; sincroniza PC↔celular direto quando ambos online | Nada; o servidor recebe tudo ao voltar |
| Conflito de edição (você e a IA na mesma nota) | Syncthing cria `*.sync-conflict-*` | Resolver à mão; a página explica |
| IA estraga uma nota | — | Snapshot de até 15 min antes; ou versão guardada no PC/celular |
| Índice desatualizado ou corrompido | Busca incompleta | `docker exec qmd qmd update && qmd embed`; em último caso apagar o índice local e regerar |
| Vulkan não pega | qmd em CPU (mais lento na indexação) | Nada; log documentado |
| Authelia fora | Login novo nos conectores falha; tokens já emitidos seguem até expirar | Restaurar o Authelia |
| Documento que o markitdown não lê | Fica fora do índice, registrado no log do conversor | Ver o log; formato não suportado |

## 9. Segurança

- **Injeção de prompt** por documento ou nota: o dano possível fica limitado a criar/editar em Trabalho e Estudos, sem apagar, com snapshots de 15 min.
- **Envio de conteúdo à Anthropic:** só o que o Claude consulta sai do servidor; indexação e embeddings são locais. O Pessoal é legível pelo Claude — a página deixa isso explícito.
- **Endpoints públicos:** OAuth 2.1 + login no Authelia com 2FA e grupo `admins`; backends sem autenticação nunca publicados na LAN.
- **Nextcloud:** montado `ro` na VM e `ro` no container; o conversor só escreve no disco local.

## 10. Verificação

- Novo `tools/wikisync/tests/test_segundo_cerebro.py`:
  - compose `notes`: `qmd` monta todos os vaults `:ro`; `notes_escrita` monta exatamente `trabalho` e `estudos` e nenhum outro caminho de dados; nenhum serviço além do `syncthing` monta `pessoal` com escrita; nenhum serviço monta `files` com escrita; `qmd` e `notes_escrita` sem `ports`; mcp-auth-proxy com `OIDC_ALLOWED_ATTRIBUTES=/groups=admins` e segredos só por variável; imagens sem `latest`; rede `notes_mcp` declarada;
  - stack `ai`: `open-webui` na rede externa `notes_mcp`;
  - Authelia com o cliente `mcp` (e `validate-config` com o binário 4.38.0);
  - Traefik: `notas.` e `escrita.` sem middleware do Authelia, `sync.` com;
  - `index.yml` do qmd renderizado com as quatro coleções e os `ignore`;
  - conversor: teste unitário do script (manifesto incremental, remoção de apagados, extensões filtradas) com arquivos de exemplo;
  - exports NFS com `notes`; montagem de `files` com `ro` na `ai-desktop-vm`; `zfs-auto-snapshot` com a propriedade;
  - alertas e sondas presentes.
- `check`, `sync`, `test`, `build`, `lint`; skills `update-index` e `audit-integrations`.

## 11. Fora de escopo

- `rag_sources` (continua montado na VM de IA, sem indexação); fotos e mídia (o Immich já tem busca própria).
- Gateway único de MCPs, Langfuse, MCPs de controle do servidor, agentes (4c).
- Tailscale (sub-projeto próprio).
- Busca por OCR em imagens e PDFs escaneados.

## 12. Riscos

- **qmd é novo e muda rápido** (v2.x): versão fixada; se a imagem com Vulkan não funcionar, CPU. Plano B se o qmd falhar no servidor: basic-memory só para leitura num espelho, sem tocar os vaults.
- **Embeddings em português:** o modelo padrão do qmd é multilíngue? (conferido no plano); a alternativa Qwen3-Embedding fica documentada em `QMD_EMBED_MODEL`.
- **mcp-auth-proxy é um projeto pequeno** (um mantenedor): versão fixada, dados persistentes, `AUTH_HMAC_SECRET` fixo; substituível por outro proxy OAuth sem mexer nos MCPs.
- **Open WebUI com MCP declarado por ambiente** pode não existir na versão fixada: então o cadastro fica manual e documentado (exceção ao `ENABLE_PERSISTENT_CONFIG=false`).
- **Syncthing em NFS:** inotify não vê escritas de outras máquinas no NFS — aqui só a própria VM escreve, então funciona; varredura periódica de segurança configurada.
- **Volume dos documentos do Nextcloud:** a primeira conversão e o primeiro `embed` podem levar horas; os timers não se sobrepõem (`flock`).
