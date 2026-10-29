---
description: "Stack notes na VM de IA: vaults do Obsidian sincronizados pelo Syncthing, busca local com qmd sobre as notas e os documentos do Nextcloud, e MCP para o Claude com escopo por vault."
---

# Seção 12: Segundo cérebro (Obsidian, Syncthing, busca local e MCP)

Os vaults do Obsidian **Pessoal**, **Trabalho** e **Estudos**, editados no PC e no celular, ficam sincronizados com o servidor pelo **Syncthing**. No servidor, o **qmd** indexa as notas e os documentos do Nextcloud (convertidos para Markdown) com busca local, sem custo de API. O Claude (app, claude.ai e Claude Code), o Open WebUI e os agentes acessam tudo por **MCP**, com escopo por vault:

| Vault | O Claude pode |
|---|---|
| Pessoal | buscar e ler |
| Trabalho | buscar, ler, criar, editar e mover |
| Estudos | buscar, ler, criar, editar e mover |
| Documentos (Nextcloud) | buscar e ler (cópia convertida) |

## Arquivos

- Stack: `docker/stacks/notes/docker-compose.yml` (Portainer, endpoint da `ai-desktop-vm`, variáveis em `/opt/portainer_stack_envs/notes.env`).
- Preparação: `ansible/playbooks/setup-notes-volumes.yml` (diretórios, imagens locais, coleções do qmd, `notes.env`), rodado antes do deploy.
- Arquivos literais nesta página: `ansible/templates/notes/`.

## Dados

O dataset `data/notes` (cota de 20G, [seção 2](02-proxmox-ve-host.md)) é exportado só para a `ai-desktop-vm` e tem snapshots automáticos a cada 15 minutos ([guia de snapshots](../03-guias-sustentacao/11-guia-snapshots-zfs.md)): é por eles que se desfaz uma edição da IA. O dataset `files` do Nextcloud é montado **só leitura** na mesma VM.


| Dado | Onde | Proteção |
|---|---|---|
| Vaults (`pessoal/`, `trabalho/`, `estudos/`) | `data/notes` (NFS) | snapshots automáticos + cópias completas no PC e no celular |
| Configuração e chaves do Syncthing; coleções do qmd | `docker-volumes/syncthing/config`, `docker-volumes/qmd/config` (NFS) | como o resto de `docker-volumes` |
| Banco do Syncthing, índice e modelos do qmd, documentos convertidos, estado OAuth dos proxies | `/opt/local-data/{syncthing,qmd,notes-documentos,mcp-auth-busca,mcp-auth-escrita}` | **fora dos snapshots ZFS e sem backup**: tudo é regerável (varredura do Syncthing, `qmd update`/`embed`, conversor; perder o estado OAuth = fazer login de novo nos conectores) |

## Deploy

1. **Host Proxmox:** crie o dataset (`zfs create -o refquota=20G data/notes` e o `chown`, [seção 2](02-proxmox-ve-host.md)) e rode o `setup-proxmox-host.yml` (export do `notes` para a VM de IA, `zfs-auto-snapshot` e a propriedade por dataset). Depois, `setup-base-ubuntu.yml` para montar `notes` e `files` (só leitura) na `ai-desktop-vm`.
2. **Vault** (`ansible-vault edit inventories/home/group_vars/all/vault.yml`, a partir de `server/ansible`): `syncthing_gui_password`, `syncthing_api_key` (`openssl rand -hex 24`), `mcp_auth_hmac_secret` (`openssl rand -base64 32`) e `oidc_clients.mcp` — `secret` (`openssl rand -hex 32`) e `secret_digest` gerado como os outros clientes ([seção 11](11-fotos-arquivos.md#deploy)). No `group_vars`, `notes_nextcloud_usuario` = o seu id no Nextcloud (`docker exec -u www-data nextcloud_app php occ user:list`).
3. **Authelia e Traefik:** rode o `setup-core-networking.yml` (cliente `mcp`, regras `bypass` de `notas.` e `escrita.`, routers `notas.`, `escrita.` e `sync.`) e `docker restart authelia`.
4. **Volumes, imagens e `.env`** (primeiro com `--check`; o build das três imagens leva alguns minutos):
   ```bash
   ansible-playbook -i inventories/home/hosts.ini playbooks/setup-notes-volumes.yml --ask-vault-pass --check
   ansible-playbook -i inventories/home/hosts.ini playbooks/setup-notes-volumes.yml --ask-vault-pass
   ```
5. **Portainer → Stacks → Add Stack** no endpoint da `ai-desktop-vm`: `notes` com `docker/stacks/notes/docker-compose.yml` e o `/opt/portainer_stack_envs/notes.env` → **Deploy the stack**. Só depois, **Update the stack** da `ai` (o Open WebUI entra na rede `notes_mcp`, que a stack `notes` cria).
6. **Timers**, na `ai-desktop-vm`: `sudo systemctl start notes-documentos.timer notes-indice.timer`. A primeira conversão e o primeiro `embed` podem levar horas; acompanhe com `journalctl -fu notes-documentos -u notes-indice`.
7. **Monitoramento:** `setup-monitoring-stack-volumes.yml` (sondas, painel e o alerta) e `setup-base-ubuntu.yml` na `ai-desktop-vm` (coletor `systemd` do Alloy).
8. Pareie os aparelhos ([Sincronização](#sincronização-syncthing)) e conecte o Claude ([Conectores](#conectores-para-o-claude)).

## Documentos do Nextcloud

Todos os seus arquivos do Nextcloud (`<files>/<notes_nextcloud_usuario>/files`), exceto imagem, vídeo e áudio, são convertidos para Markdown pelo **markitdown** e indexados como a coleção `documentos`. A conversão roda a cada 10 minutos (timer `notes-documentos`) e é incremental: só converte o que mudou (tamanho ou data) e remove a cópia do que você apagou ou moveu. O resultado fica no disco local da VM (`/opt/local-data/notes-documentos`), porque pode ser regerado a qualquer momento. Arquivos ocultos, links simbólicos e arquivos acima de `notes_documentos_max_mb` ficam de fora; um arquivo que o markitdown não consegue ler aparece no log (`journalctl -u notes-documentos`) e é tentado de novo na próxima rodada.

Se a origem estiver vazia ou não existir (por exemplo, o NFS do `files` não montou), o conversor **não apaga nada** e termina com código 2 — o alerta `timer-falhou` avisa. Com o NFS desmontado, a unit falha já no `ExecStartPre` (`mountpoint -q`), e o mesmo alerta avisa. Para recomeçar do zero, apague `/opt/local-data/notes-documentos` inteiro.

```python title="ansible/templates/notes/conversor.py"
"""Converte os documentos do Nextcloud para Markdown, de forma incremental (segundo cérebro, página 12).

Uso: conversor.py --origem DIR --destino DIR --extensoes pdf,docx,... --max-mb N
Cada <origem>/<rel> vira <destino>/<rel>.md, com o caminho original no cabeçalho. O manifesto
<destino>/.manifesto.json guarda tamanho e data de cada arquivo convertido; o que sumiu da origem sai do destino.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

MANIFESTO = ".manifesto.json"
SALVAR_A_CADA = 20


@dataclass
class Resumo:
    convertidos: int = 0
    mantidos: int = 0
    removidos: int = 0
    falhas: list[str] = field(default_factory=list)


class OrigemVazia(Exception):
    """A origem não existe ou não tem arquivos, mas o manifesto tem: provável montagem ausente."""


def _arquivos(origem: Path) -> list[Path]:
    """Arquivos regulares da origem, sem ocultos e sem seguir links simbólicos."""
    achados = []
    for raiz, pastas, nomes in os.walk(origem, followlinks=False):
        pastas[:] = [p for p in pastas if not p.startswith(".")]
        for nome in nomes:
            p = Path(raiz) / nome
            if not nome.startswith(".") and not p.is_symlink() and p.is_file():
                achados.append(p)
    return achados


def _gravar(caminho: Path, texto: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.parent / f".{os.getpid()}.tmp"  # nome curto: o do arquivo pode já estar no limite de 255 bytes
    try:
        tmp.write_text(texto, encoding="utf-8")
        os.replace(tmp, caminho)
    finally:
        tmp.unlink(missing_ok=True)


def _apagar(caminho: Path) -> None:
    try:
        caminho.unlink(missing_ok=True)
    except OSError:  # nome longo demais: a cópia nunca chegou a existir
        pass


def _podar(pasta: Path, destino: Path) -> None:
    while pasta != destino and pasta.is_dir() and not any(pasta.iterdir()):
        pasta.rmdir()
        pasta = pasta.parent


def sincronizar(origem: Path, destino: Path, extensoes: set[str], max_bytes: int,
                converter: Callable[[Path], str]) -> Resumo:
    arq_manifesto = destino / MANIFESTO
    manifesto = json.loads(arq_manifesto.read_text(encoding="utf-8")) if arq_manifesto.exists() else {}
    arquivos = _arquivos(origem) if origem.is_dir() else []
    if not arquivos and manifesto:
        raise OrigemVazia(f"{origem} vazia ou ausente; nada foi apagado")

    resumo = Resumo()
    vistos = set()
    try:  # o manifesto é salvo no fim, a cada SALVAR_A_CADA conversões e se a rodada for interrompida
        for p in sorted(arquivos):
            if p.suffix.lower().lstrip(".") not in extensoes:
                continue
            rel = p.relative_to(origem).as_posix()
            saida = destino / (rel + ".md")
            try:  # um documento ruim (ou que sumiu no meio da rodada) não para os outros
                st = p.stat()
                if st.st_size > max_bytes:
                    print(f"grande demais, ignorado: {p}", file=sys.stderr)
                    continue
                vistos.add(rel)
                assinatura = [st.st_size, st.st_mtime_ns]
                if manifesto.get(rel) == assinatura and saida.exists():
                    resumo.mantidos += 1
                    continue
                texto = converter(p)
                origem_yaml = rel.replace("\\", "\\\\").replace('"', '\\"')  # aspas duplas do YAML
                _gravar(saida, f'---\norigem: "Nextcloud/{origem_yaml}"\n---\n\n{texto}')
            except Exception as erro:
                print(f"falha ao converter {rel}: {erro}", file=sys.stderr)
                resumo.falhas.append(rel)
                manifesto.pop(rel, None)
                vistos.discard(rel)
                _apagar(saida)  # a versão antiga não fica no índice depois que a nova falhou
                continue
            manifesto[rel] = assinatura
            resumo.convertidos += 1
            if resumo.convertidos % SALVAR_A_CADA == 0:
                _gravar(arq_manifesto, json.dumps(manifesto, ensure_ascii=False, indent=1, sort_keys=True))

        for rel in sorted(set(manifesto) - vistos):
            saida = destino / (rel + ".md")
            _apagar(saida)
            _podar(saida.parent, destino)
            del manifesto[rel]
            resumo.removidos += 1
    finally:
        _gravar(arq_manifesto, json.dumps(manifesto, ensure_ascii=False, indent=1, sort_keys=True))
    return resumo


def _converter_real(p: Path) -> str:
    if p.suffix.lower() in (".md", ".txt"):
        return p.read_text(encoding="utf-8", errors="replace")
    from markitdown import MarkItDown  # importado aqui: os testes não precisam do markitdown
    return MarkItDown().convert(str(p)).text_content


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--origem", required=True, type=Path)
    ap.add_argument("--destino", required=True, type=Path)
    ap.add_argument("--extensoes", required=True)
    ap.add_argument("--max-mb", type=int, default=50)
    a = ap.parse_args(argv)
    extensoes = {e.strip().lower().lstrip(".") for e in a.extensoes.split(",") if e.strip()}
    try:
        r = sincronizar(a.origem, a.destino, extensoes, a.max_mb * 1024 * 1024, _converter_real)
    except OrigemVazia as erro:
        print(f"abortado: {erro}", file=sys.stderr)
        return 2
    print(f"convertidos={r.convertidos} mantidos={r.mantidos} removidos={r.removidos} falhas={len(r.falhas)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

A imagem do conversor (construída pelo `setup-notes-volumes.yml`):

```jinja title="ansible/templates/notes/Dockerfile.conversor.j2"
# Imagem do conversor de documentos do segundo cérebro (página 12).
FROM python:3.13-slim
RUN pip install --no-cache-dir "markitdown[pdf,docx,pptx,xlsx]=={{ markitdown_version }}"
COPY conversor.py /app/conversor.py
USER 65534:65534
ENTRYPOINT ["python", "/app/conversor.py"]
```

## Busca (qmd)

O **qmd** junta busca por palavra-chave (BM25), busca semântica e reordenação, com modelos GGUF que rodam na própria VM (na GPU, pelo Vulkan; sem ela, na CPU). Na primeira indexação ele baixa os modelos do Hugging Face (cerca de 2 GB) para `/opt/local-data/qmd`. O container monta os vaults e os documentos **só leitura** e expõe um MCP (`query`, `get`, `multi_get`, `metadata`, `status`) em `http://qmd:8181/mcp`, só na rede Docker `notes_mcp`.

A imagem local, construída pelo `setup-notes-volumes.yml` (reconstrói quando o Dockerfile muda):

```jinja title="ansible/templates/notes/Dockerfile.qmd.j2"
# Imagem do qmd (busca local do segundo cérebro, página 12): Node 22 + Mesa/RADV para o Vulkan.
FROM node:22-bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends mesa-vulkan-drivers libvulkan1 ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN npm install -g @tobilu/qmd@{{ qmd_version }}
```

As coleções (gerado em `docker-volumes/qmd/config/index.yml`). O contexto de cada coleção é devolvido junto com os resultados, para o Claude saber o que pode alterar:

```jinja title="ansible/templates/notes/index.yml.j2"
# Coleções do qmd (segundo cérebro, página 12). Gerado pelo setup-notes-volumes.yml; não edite na VM.
{% set ignorar = ['.obsidian/**', '.trash/**', '**/*.sync-conflict-*'] %}
{% set colecoes = {
  'pessoal': 'Vault Pessoal do Obsidian. Somente leitura: não há ferramenta que altere estas notas.',
  'trabalho': 'Vault de Trabalho e projetos do Obsidian. Pode ser editado pelo MCP de escrita (/notes/trabalho).',
  'estudos': 'Vault de Estudos e conhecimento do Obsidian. Pode ser editado pelo MCP de escrita (/notes/estudos).',
  'documentos': 'Documentos do Nextcloud convertidos para Markdown (somente leitura). O campo origem aponta o arquivo original.',
} %}
{% if qmd_modelos %}
models: {{ qmd_modelos | to_json }}
{% endif %}
collections:
{% for nome, descricao in colecoes.items() %}
  {{ nome }}:
    path: /notes/{{ nome }}
    pattern: "**/*.md"
    ignore: {{ ignorar | to_json }}
    context:
      "/": "{{ descricao }}"
{% endfor %}
```

## Escrita (Trabalho e Estudos)

O MCP oficial de arquivos (`@modelcontextprotocol/server-filesystem`) roda dentro do **supergateway**, que o expõe em `http://notes_escrita:8000/mcp` (Streamable HTTP), também só na rede `notes_mcp`. O container monta **apenas** `trabalho/` e `estudos/`: o vault Pessoal e os arquivos do Nextcloud não existem para ele, então nenhuma instrução (nem uma nota maliciosa) consegue alterá-los. A pasta `.obsidian` de cada vault entra **só leitura** por cima: ela guarda os plugins do Obsidian, que rodam JavaScript no PC — uma injeção de prompt não pode instalar ou ligar um plugin. O playbook cria essas pastas antes do deploy (a montagem precisa delas). O resto do container é **só leitura** (`read_only: true`, com `/tmp` em memória): o cliente MCP pode pedir outras pastas (as *roots* do protocolo substituem as da linha de comando), mas fora de `trabalho/` e `estudos/` só existem os arquivos do sistema, e nenhum aceita escrita. Continua possível a IA escrever blocos `dataviewjs` ou de Templater numa nota; se você usa esses plugins, revise o que a IA escreveu antes de abrir a nota. Ferramentas: ler, listar, buscar por nome, criar, sobrescrever (`write_file`), editar trechos (`edit_file`, com prévia), criar pastas e mover — **não há ferramenta de apagar**, e mover não sobrescreve um destino existente.

```jinja title="ansible/templates/notes/Dockerfile.escrita.j2"
# Imagem do MCP de escrita do segundo cérebro (página 12): server-filesystem exposto em HTTP pelo supergateway.
FROM node:24-bookworm-slim
RUN npm install -g supergateway@{{ supergateway_version }} @modelcontextprotocol/server-filesystem@{{ mcp_filesystem_version }}
USER node
```

## Sincronização (Syncthing)

O servidor é um nó sempre ligado do Syncthing. Cada vault é uma pasta do Syncthing, compartilhada entre o servidor, o PC (Syncthing) e o celular (**Syncthing-Fork**, do F-Droid). Fora de casa, os aparelhos se encontram pelos relays públicos do Syncthing: o tráfego é criptografado de ponta a ponta e o relay não lê nada. Com o Tailscale ligado ([seção 14](14-vpn-tailscale.md)), o endereço fixo `tcp://<IP da ai-desktop-vm>:22000` funciona também fora de casa e a conexão é direta, sem relay.

O `setup-notes-volumes.yml` gera as chaves e o `config.xml` antes do primeiro deploy, com o usuário `syncthing_gui_user` e a senha `syncthing_gui_password` do vault no painel. O painel fica em `https://sync.<domínio>` (atrás do Authelia) e em `http://<IP da ai-desktop-vm>:8384` na rede de casa.

### Parear os aparelhos

1. No servidor (painel `sync.`), em **Ações → Mostrar ID**, copie o ID do dispositivo.
2. No PC e no celular, adicione o dispositivo com esse ID. Como o container não recebe a descoberta local, informe o endereço `tcp://<IP da ai-desktop-vm>:22000` (e deixe `dynamic` também, para fora de casa). A porta `21027/udp` da descoberta local não é publicada de propósito: o broadcast da LAN não atravessa a ponte do Docker, e o endereço fixo resolve.
3. No servidor, aceite os dispositivos e crie três pastas, com caminhos `/var/syncthing/notes/pessoal`, `/var/syncthing/notes/trabalho` e `/var/syncthing/notes/estudos`, compartilhadas com os dois aparelhos. Em cada aparelho, aceite a pasta e aponte para o vault correspondente do Obsidian.
4. Nos aparelhos (não no servidor), ligue o **versionamento "Staggered"** em cada pasta: é ele que guarda a versão anterior quando uma edição chega de outro lugar — inclusive uma edição da IA no servidor.
5. Em cada pasta, crie o `.stignore` com as linhas abaixo, para não sincronizar o estado da janela do Obsidian, que muda o tempo todo:

    ```text
    .obsidian/workspace.json
    .obsidian/workspace-mobile.json
    .trash
    ```

Se você e a IA editarem a mesma nota ao mesmo tempo, o Syncthing guarda as duas versões (`*.sync-conflict-*`): abra as duas, junte à mão e apague a cópia. A busca ignora esses arquivos.

## Conectores para o Claude

Os dois MCPs são publicados pelo túnel em `https://notas.<domínio>/mcp` (busca) e `https://escrita.<domínio>/mcp` (escrita), cada um atrás de um **mcp-auth-proxy**. O claude.ai exige OAuth com registro dinâmico de cliente, que o Authelia (4.39) não oferece; o proxy faz esse papel e manda o login para o OIDC do Authelia (cliente `mcp`, com 2FA). Só quem está no grupo `admins` passa. Os proxies falam com o Authelia pela LAN (`extra_hosts` de `auth.` para o Traefik na `core-services-vm`). Por isso os dois subdomínios ficam fora do forward-auth do Authelia (regras `bypass` e routers sem middleware na [seção 5](05-rede-segura.md)); o hostname curinga `*` do túnel já os encaminha ao Traefik. O `sync.` fica atrás do Authelia como os demais.

| Cliente | Como conectar |
|---|---|
| claude.ai (navegador e app) | **Configurações → Conectores → Adicionar conector personalizado**, um para cada URL acima (`Notas` e `Notas – escrita`). O botão **Conectar** abre o login do Authelia. Os conectores criados no navegador aparecem no app do celular. |
| Claude Code (PC) | `claude mcp add --transport http notas https://notas.<domínio>/mcp` e `claude mcp add --transport http escrita https://escrita.<domínio>/mcp`; depois `/mcp` → **Authenticate** abre o login no navegador. |
| Open WebUI | Já vem configurado ([seção 8](08-stack-ia.md#ferramentas-notas)): ferramentas **Notas (busca)** e **Notas (escrita)**, pela rede interna, só para administradores. |

Dica: deixe só o conector de busca ligado na conversa e ligue o de escrita quando quiser que o Claude crie ou edite notas.

## Conversão e indexação periódicas

Dois timers systemd na `ai-desktop-vm`, instalados pelo `setup-notes-volumes.yml` (habilitados, mas só iniciados depois do deploy da stack): `notes-documentos` converte os documentos do Nextcloud a cada 10 minutos, e `notes-indice` roda `qmd update` (lê o que mudou) e `qmd embed` (gera os vetores) 5 minutos depois. O `flock` impede duas rodadas ao mesmo tempo — a primeira conversão e o primeiro `embed` podem levar horas; enquanto isso, as rodadas seguintes saem sem fazer nada. Se uma rodada falhar, o Alloy (coletor `systemd`) vê a unit em `failed` e o Grafana manda o alerta **timer-falhou** (uma vez: a regra olha os últimos 30 minutos, então a falha que se repete a cada rodada não gera um aviso novo a cada 10 minutos).

```jinja title="ansible/templates/notes/notes-documentos.service.j2"
# Conversão dos documentos do Nextcloud (segundo cérebro, página 12). Origem só leitura.
[Unit]
Description=Converte os documentos do Nextcloud para Markdown (segundo cérebro)
Requires=docker.service
After=docker.service remote-fs.target

[Service]
Type=oneshot
# Um PDF que trave a conversão não para tudo: depois de 4 h a rodada é encerrada (a próxima retoma pelo manifesto).
# O timeout mata o cliente docker, não o container; por isso o rm -f antes e depois.
TimeoutStartSec=4h
# Sem o NFS do files montado, falha logo e o alerta timer-falhou avisa (o conversor também não apagaria nada).
ExecStartPre=/usr/bin/mountpoint -q {{ vm_nfs_mount_base_path }}/{{ zfs_files_dataset_name }}
ExecStartPre=-/usr/bin/docker rm -f notes_conversor
ExecStopPost=-/usr/bin/docker rm -f notes_conversor
ExecStart=/usr/bin/flock -E 0 -n /run/notes-documentos.lock /usr/bin/docker run --rm --name notes_conversor --user {{ docker_puid }}:{{ docker_pgid }} -v {{ vm_nfs_mount_base_path }}/{{ zfs_files_dataset_name }}/{{ notes_nextcloud_usuario }}/files:/origem:ro -v {{ vm_local_data_path }}/notes-documentos:/destino localhost/homeserver/notes-conversor:{{ markitdown_version }} --origem /origem --destino /destino --extensoes {{ notes_documentos_extensoes | join(',') }} --max-mb {{ notes_documentos_max_mb }}
```

```jinja title="ansible/templates/notes/notes-documentos.timer.j2"
[Unit]
Description=Agenda a conversão dos documentos do Nextcloud (a cada 10 min)

[Timer]
OnCalendar=*:0/10
Persistent=false

[Install]
WantedBy=timers.target
```

```jinja title="ansible/templates/notes/notes-indice.service.j2"
# Reindexação do qmd (segundo cérebro, página 12): lê o que mudou e gera os vetores novos.
[Unit]
Description=Atualiza o índice do qmd (segundo cérebro)
Requires=docker.service
After=docker.service notes-documentos.service

[Service]
Type=oneshot
# Sem os vaults montados, o qmd veria as pastas vazias e tiraria tudo do índice: falha e avisa.
ExecStartPre=/usr/bin/mountpoint -q {{ vm_nfs_mount_base_path }}/{{ zfs_notes_dataset_name }}
ExecStart=/usr/bin/flock -E 0 -n /run/notes-indice.lock /usr/bin/docker exec qmd sh -c 'qmd update && qmd embed'
```

```jinja title="ansible/templates/notes/notes-indice.timer.j2"
[Unit]
Description=Agenda a reindexação do qmd (a cada 10 min, 5 min depois da conversão)

[Timer]
OnCalendar=*:5/10
Persistent=false

[Install]
WantedBy=timers.target
```

## Desfazer uma edição

Toda escrita da IA cai em `trabalho/` ou `estudos/`. Para voltar uma nota, no host Proxmox:

```bash
zfs list -t snapshot -o name,creation data/notes | tail       # snapshots: a cada 15 min, de hora em hora, diários...
ls /data/notes/.zfs/snapshot/                                  # cada snapshot é uma pasta só de leitura
cp "/data/notes/.zfs/snapshot/<snapshot>/trabalho/<nota>.md" "/data/notes/trabalho/<nota>.md"
```

O Syncthing propaga a versão restaurada para o PC e o celular. Nos aparelhos, o versionamento "Staggered" (em `.stversions/`) também guarda a versão anterior de cada nota que a IA alterou. `zfs rollback data/notes@<snapshot>` volta o dataset inteiro e apaga o que veio depois — só em último caso.

## Falhas

| Falha | O que acontece | O que fazer |
|---|---|---|
| Servidor fora | O Obsidian segue funcionando; o PC e o celular sincronizam direto entre si quando os dois estão ligados | Nada: o servidor recebe tudo ao voltar |
| Conflito (você e a IA na mesma nota) | Syncthing cria `*.sync-conflict-*` | Juntar à mão e apagar a cópia |
| Busca desatualizada ou estranha | Índice parado ou corrompido | `docker exec qmd sh -c 'qmd update && qmd embed'`; em último caso, pare o `qmd`, apague `/opt/local-data/qmd/qmd` e rode de novo |
| Alerta `timer-falhou` (`notes-*`) | Conversão ou indexação falhou | `journalctl -u notes-documentos` / `-u notes-indice`; código 2 no conversor = origem vazia (NFS do `files` não montou) |
| Vulkan não pega | O qmd usa a CPU (indexação mais lenta) | Nada; `docker logs qmd` mostra o backend |
| Conector pede login de novo | Estado OAuth perdido ou `mcp_auth_hmac_secret` trocado | Conectar de novo no claude.ai / `/mcp` no Claude Code |
| Login no conector recusado | Usuário fora do grupo `admins` do Authelia, ou redirect errado no cliente `mcp` | Conferir o grupo e o `configuration.yml` |
| Authelia fora | Login novo nos conectores falha; os já conectados seguem até o token expirar | Restaurar o Authelia |

## Teste de ponta a ponta

1. `docker ps` na `ai-desktop-vm`: `syncthing`, `qmd`, `notes_escrita`, `mcp_auth_busca` e `mcp_auth_escrita` em `Up` (o `syncthing` e o `notes_escrita` `healthy`).
2. Crie `teste-ia.md` em Trabalho no PC; em até 1 minuto ela aparece em `/data/notes/trabalho/` no host.
3. Depois de uma rodada do `notes-indice`: no claude.ai, com o conector **Notas**, peça "procure a nota teste-ia nas minhas notas" — o resultado vem da coleção `trabalho`.
4. Com o conector **Notas – escrita**, peça para acrescentar uma linha em `teste-ia.md`; a mudança chega ao PC. Peça para editar uma nota do Pessoal: não existe ferramenta para isso (o caminho `/notes/pessoal` não existe no container de escrita).
5. Ponha um PDF numa pasta do Nextcloud; depois da conversão, ele aparece em `/opt/local-data/notes-documentos/` e na busca (coleção `documentos`).
6. Desfaça a linha do passo 4 com um snapshot ([Desfazer uma edição](#desfazer-uma-edição)).
7. No Prometheus, `probe_success{app=~"notas|notas-escrita|syncthing"}` = 1; na Homepage, os três em verde.
