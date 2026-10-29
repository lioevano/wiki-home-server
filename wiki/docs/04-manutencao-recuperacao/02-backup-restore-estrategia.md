---
description: "Backup 3-2-1 do homeserver: dumps diários dos bancos, restic no host Proxmox (disco externo e nuvem), restauração e testes."
---

# Estratégia de Backup e Procedimentos de Restauração

O backup é automático e segue a regra **3-2-1**: três cópias, em duas mídias, uma delas fora de casa. Nada aqui depende de lembrar de rodar um comando. Quando algo falha, chega o alerta `timer-falhou` no Telegram ([seção 9](../01-manual-implementacao/09-painel-notificacoes.md)).

| Cópia | Onde | O que tem | Quem faz |
|---|---|---|---|
| 1 | Pool ZFS `data` (produção) | Tudo | — |
| 2 | Disco externo no host Proxmox | `docker-volumes` (configs e dumps dos bancos), `photos`, `files`, `notes` e o `/etc` do host | restic, todo dia às 04:30 |
| 3 | Nuvem compatível com S3 (ex.: Backblaze B2) | O mesmo, cifrado antes de sair de casa | restic, na mesma rodada |

Além disso:

- **`data/notes`:** snapshots automáticos para desfazer edições da IA ([seção 12](../01-manual-implementacao/12-segundo-cerebro.md#desfazer-uma-edição)).
- **Vaults do Obsidian:** cópia completa no PC e no celular (Syncthing).
- **Repositório:** fica no GitHub. O `vault.yml` vai criptografado.

!!! critical "Guarde a senha do restic fora do servidor"
    Os repositórios são cifrados com `restic_senha` (vault). Sem ela, **nenhum backup se restaura**. Ela também fica no `vault.yml`, que só abre com a senha do Ansible Vault. Guarde as duas num gerenciador de senhas, fora do servidor e fora deste repositório.

## O que é copiado e o que não é

| Dados | Backup | Por quê |
|---|---|---|
| `docker-volumes`: configurações das aplicações, hooks, `immich.json` regerável, **dumps dos bancos** | restic | É o estado das aplicações |
| `photos` (Immich, com os dumps do banco dele em `photos/backups/`) e `files` (Nextcloud) | restic | Insubstituíveis |
| `notes` (vaults do Obsidian) | restic + snapshots + Syncthing | Insubstituíveis |
| `/etc` do host Proxmox (rede, GRUB/IOMMU, `/etc/pve` com a definição das VMs) | restic | Atalho para reinstalar o host igual |
| `media` (filmes, séries, músicas, torrents) | **não** | Pode ser baixada de novo e não cabe na nuvem. Para mudar, inclua o dataset em `restic_datasets` |
| `docker-volumes/prometheus/data` e `loki/data` | **não** (`restic_excluir`) | Métricas e logs mudam o tempo todo; perder o histórico não para nada |
| `docker-volumes/ollama/models`, `photos/thumbs` e `photos/encoded-video` | **não** (`restic_excluir`) | Modelos se baixam de novo; miniaturas e vídeos convertidos o Immich regera (*Administração → Tarefas*) |
| Disco local das VMs (`/opt/local-data`): bancos, índice do qmd, documentos convertidos, banco do Syncthing, estado dos mcp-auth-proxy, base dos agentes (config do hub `agentgateway`, clone e segredos do runner do `ops`; [seção 13](../01-manual-implementacao/13-agentes-base.md)), Langfuse | só os **bancos**, pelos dumps | O resto é regerável pelos playbooks a partir do vault, ou é descartável (traces do Langfuse) |
| Discos das VMs | **não** | As VMs são recriadas pelo `vm-deploy.yml` e pelos playbooks ([reconstrução](04-reconstruindo-infraestrutura.md)) |

## Bancos de dados: dumps diários

Todo Postgres roda no disco local da sua VM (o Postgres exige ser dono dos arquivos, o que o NFS com `all_squash` não permite; regra DAD-5). Um dump diário vai para o NFS, onde o restic o pega às 04:30. Todos usam o mesmo `ansible/playbooks/tasks/dump-postgres.yml` (script `ansible/templates/backup-postgres.sh.j2`, unit e timer `backup-<nome>-db`), que guarda duas semanas:

| Banco | VM | Horário | Destino (em `/data/docker-volumes`) | Instalado por |
|---|---|---|---|---|
| Authelia (2FA, sessões, consentimentos OIDC) | core | 03:15 | `authelia/db-dumps/` | `setup-core-networking.yml` |
| Grafana (usuários, service accounts, painéis da tela) | core | 03:20 | `grafana/db-dumps/` | `setup-monitoring-stack-volumes.yml` |
| Nextcloud (banco e o `config/`) | core | 03:30 | `nextcloud/db-dumps/` | `setup-cloud-stack-volumes.yml` |
| LiteLLM (chaves, orçamentos, uso) | ai | 03:45 | `litellm/db-dumps/` | `setup-ai-volumes.yml` |
| Immich | core | 02:00 | `/data/photos/backups/` (o próprio Immich) | `immich.json` |

Antes do deploy da stack, sem o container do banco, o dump só registra um aviso no journal e não falha. Depois do deploy, uma falha deixa a unit em `failed` e o alerta `timer-falhou` avisa.

## Restic no host Proxmox

O role `ansible/roles/infra/restic/` (aplicado pelo `setup-proxmox-host.yml`) instala o restic do Debian e roda o `backup-restic` todo dia às `restic_horario` (04:30). Para cada dataset de `restic_datasets`, ele:

1. Tira um snapshot ZFS (`data/<dataset>@restic`), para copiar um estado consistente mesmo com as aplicações gravando.
2. Monta o snapshot só leitura em `/mnt/restic/<dataset>`. O caminho é sempre o mesmo, então o restic deduplica contra o backup anterior.
3. Copia para **cada** repositório de `restic_repositorios`. Um repositório que falha (nuvem fora, disco desligado) não impede o outro.
4. Apaga os backups antigos (`restic_retencao`: 7 diários, 4 semanais, 12 mensais).
5. Aos domingos, relê 5% dos dados de cada repositório (`restic check --read-data-subset`) para achar corrupção.
6. Desmonta e apaga o snapshot, também em caso de erro.

Qualquer falha deixa a unit em `failed` e dispara o alerta `timer-falhou`: o Alloy do host vê as units `backup-*`. A unit roda com prioridade baixa de CPU (`Nice=10`) e guarda o cache dos índices em `/var/cache/restic`, para não baixar tudo da nuvem a cada rodada. Os backups são agrupados só pelo host (`--group-by host`): um dia em que um dataset falhou não cria um grupo que nunca expira.

### Preparar os destinos

1. **Disco externo:** formate um HD USB (ext4 serve), descubra o UUID (`blkid`) e monte-o pelo `/etc/fstab` do host em `/mnt/backup-externo`, com `nofail` para o host subir sem ele:
   ```text
   UUID=<uuid-do-disco>  /mnt/backup-externo  ext4  defaults,nofail,x-systemd.device-timeout=10s  0  2
   ```
   O backup confere a `montagem` antes de gravar. Com o disco desligado, aquele repositório falha (e você é avisado), em vez de encher o disco do sistema.
2. **Nuvem:** crie um bucket privado no Backblaze B2 (ou outro S3) e uma *application key* só para ele. O endereço no formato `s3:https://<endpoint>/<bucket>/homeserver` e as chaves vão para `restic_repositorios` (página 01). O restic cifra tudo antes de enviar.
3. **Vault:** `restic_senha` (`openssl rand -base64 32`) e `restic_repositorios`, conforme o `vault.yml.example` (página 01).
4. Aplique: `ansible-playbook -i inventories/home/hosts.ini playbooks/setup-proxmox-host.yml --ask-vault-pass --check`, depois sem `--check`.
5. **Primeira rodada,** pelo shell do host Proxmox: `systemctl start --no-block backup-restic.service` (sem o `--no-block`, o comando só volta quando o backup terminar) e acompanhe com `journalctl -fu backup-restic`. Na primeira vez, o script cria os repositórios (`restic init`). A primeira cópia para a nuvem pode levar dias; as seguintes só mandam o que mudou.

Para ver o que existe num repositório, carregue as variáveis dele e use o restic:

```bash
sudo -i
set -a; . /etc/restic/repositorios/nuvem.env; set +a
restic snapshots
restic stats latest
```

### Arquivos do role

```yaml title="ansible/roles/infra/restic/tasks/main.yml"
# ansible/roles/infra/restic/tasks/main.yml
# Backup automatizado no host Proxmox (página 04/02): restic copia os datasets de restic_datasets, a partir de
# snapshots ZFS, para cada repositório de restic_repositorios (vault), todo dia às restic_horario.

- name: "Instalar o restic"
  ansible.builtin.apt:
    name: restic
    state: present
    update_cache: true
    cache_valid_time: 3600

- name: "Diretório dos repositórios (só root: senha e credenciais)"
  ansible.builtin.file:
    path: /etc/restic/repositorios
    state: directory
    owner: root
    group: root
    mode: '0700'

- name: "Ponto de montagem dos snapshots"
  ansible.builtin.file:
    path: /mnt/restic
    state: directory
    owner: root
    group: root
    mode: '0700'

- name: "Variáveis de cada repositório"
  ansible.builtin.copy:
    dest: "/etc/restic/repositorios/{{ item.nome }}.env"
    owner: root
    group: root
    mode: '0600'
    content: |
      RESTIC_REPOSITORY={{ item.repositorio | quote }}
      RESTIC_PASSWORD={{ restic_senha | quote }}
      {% if item.montagem | default('') %}
      RESTIC_MONTAGEM={{ item.montagem | quote }}
      {% endif %}
      {% for chave, valor in (item.ambiente | default({})).items() %}
      {{ chave }}={{ valor | quote }}
      {% endfor %}
  loop: "{{ restic_repositorios | default([]) }}"
  loop_control:
    label: "{{ item.nome }}"
  no_log: true # senha e credenciais

- name: "Listar os arquivos de repositório existentes"
  ansible.builtin.find:
    paths: /etc/restic/repositorios
    patterns: "*.env"
  register: restic_envs

- name: "Apagar repositórios que saíram de restic_repositorios"
  ansible.builtin.file:
    path: "{{ item.path }}"
    state: absent
  loop: "{{ restic_envs.files }}"
  loop_control:
    label: "{{ item.path }}"
  when: (item.path | basename | regex_replace('\.env$', '')) not in (restic_repositorios | default([]) | map(attribute='nome') | list)

- name: "Script do backup"
  ansible.builtin.template:
    src: backup-restic.sh.j2
    dest: /usr/local/sbin/backup-restic.sh
    owner: root
    group: root
    mode: '0750'

- name: "Serviço systemd do backup"
  ansible.builtin.copy:
    dest: /etc/systemd/system/backup-restic.service
    owner: root
    group: root
    mode: '0644'
    content: |
      [Unit]
      Description=Backup dos datasets ZFS com restic (página 04/02)
      After=zfs-mount.service network-online.target
      Wants=network-online.target

      [Service]
      Type=oneshot
      ExecStart=/usr/local/sbin/backup-restic.sh
      # Cache dos índices do restic: sem ele, cada rodada baixa de novo os índices da nuvem.
      CacheDirectory=restic
      Environment=RESTIC_CACHE_DIR=/var/cache/restic
      # Prioridade baixa de CPU: não disputa com as VMs.
      Nice=10

- name: "Timer systemd do backup"
  ansible.builtin.copy:
    dest: /etc/systemd/system/backup-restic.timer
    owner: root
    group: root
    mode: '0644'
    content: |
      [Unit]
      Description=Agenda o backup diário com restic

      [Timer]
      OnCalendar={{ restic_horario }}
      Persistent=true

      [Install]
      WantedBy=timers.target

- name: "Habilitar o timer do backup"
  ansible.builtin.systemd_service:
    name: backup-restic.timer
    enabled: true
    state: started
    daemon_reload: true
  when: not ansible_check_mode # no --check a unit só foi simulada: o módulo falharia por ela não existir
```

```bash title="ansible/roles/infra/restic/templates/backup-restic.sh.j2"
#!/bin/bash
# ansible/roles/infra/restic/templates/backup-restic.sh.j2
# Backup diário dos datasets ZFS (restic_datasets) para cada repositório de restic_repositorios (página 04/02).
# Cada dataset sai de um snapshot (cópia consistente), montado só leitura sempre no mesmo caminho
# (/mnt/restic/<dataset>): o restic deduplica contra o backup anterior e a restauração não depende do snapshot.
# Um repositório que falha não impede os outros; qualquer falha termina com código 1 (unit 'failed', alerta
# timer-falhou). Gerado pelo role infra/restic.
set -uo pipefail

POOL="{{ zfs_base_pool_path | basename }}"
SNAP="restic"
BASE="${RESTIC_BASE:-/mnt/restic}"
ENV_DIR="${RESTIC_ENV_DIR:-/etc/restic/repositorios}"
DATASETS=({% for ds in restic_datasets %}"{{ ds }}"{{ " " if not loop.last }}{% endfor %})
EXCLUIR=({% for ex in restic_excluir %}--exclude "$BASE/{{ ex }}"{{ " " if not loop.last }}{% endfor %})
# Arquivos do próprio host (rede, GRUB/IOMMU, /etc/pve): pequenos, copiados direto, sem snapshot.
HOST=({% for c in restic_host_caminhos %}"{{ c }}"{{ " " if not loop.last }}{% endfor %})
read -r -a RETENCAO <<< "{{ restic_retencao }}"
CHECK_PARCIAL="{{ restic_check_parcial }}"
{% raw %}
falhas=0

limpar() {
    for ds in "${DATASETS[@]}"; do
        umount "$BASE/$ds" 2>/dev/null || true
        zfs destroy "$POOL/$ds@$SNAP" 2>/dev/null || true
    done
}
trap limpar EXIT
limpar # sobra de uma execução interrompida

caminhos=()
for ds in "${DATASETS[@]}"; do
    mkdir -p "$BASE/$ds"
    if zfs snapshot "$POOL/$ds@$SNAP" && mount -t zfs -o ro "$POOL/$ds@$SNAP" "$BASE/$ds"; then
        caminhos+=("$BASE/$ds")
    else
        echo "ERRO: não foi possível montar o snapshot de $POOL/$ds" >&2
        falhas=1
    fi
done
if [ "${#caminhos[@]}" -eq 0 ]; then
    echo "ERRO: nenhum dataset para copiar" >&2
    exit 1
fi

shopt -s nullglob
repositorios=("$ENV_DIR"/*.env)
if [ "${#repositorios[@]}" -eq 0 ]; then
    echo "ERRO: nenhum repositório em $ENV_DIR (restic_repositorios no vault)" >&2
    exit 1
fi

for env in "${repositorios[@]}"; do
    nome="$(basename "$env" .env)"
    echo "== repositório $nome"
    (
        set -a
        # shellcheck disable=SC1090
        . "$env"
        set +a
        if [ -n "${RESTIC_MONTAGEM:-}" ] && ! mountpoint -q "$RESTIC_MONTAGEM"; then
            echo "ERRO [$nome]: $RESTIC_MONTAGEM não está montado; nada gravado no disco do sistema" >&2
            exit 1
        fi
        restic cat config >/dev/null 2>&1 || restic init || exit 1
        restic backup --host homeserver --tag zfs "${EXCLUIR[@]}" "${caminhos[@]}" "${HOST[@]}" || exit 1
        # --group-by host: um dia com um dataset a menos (ou uma mudança em restic_datasets) não cria um grupo
        # de snapshots que nunca expira.
        restic forget --prune --host homeserver --group-by host "${RETENCAO[@]}" || exit 1
        if [ "$(date +%u)" = "7" ]; then
            restic check --read-data-subset "$CHECK_PARCIAL" || exit 1
        fi
    ) || { echo "ERRO: falha no repositório $nome" >&2; falhas=1; }
done

exit "$falhas"
{% endraw %}
```

## Restaurar

Todos os comandos rodam como root no host Proxmox, com as variáveis do repositório carregadas (`set -a; . /etc/restic/repositorios/<nome>.env; set +a`). Prefira o disco externo, que é mais rápido; a nuvem fica para quando a casa inteira se perdeu.

### Um arquivo ou uma pasta

```bash
restic snapshots                                   # escolha o snapshot (ou use latest)
restic ls latest /mnt/restic/files/leo/files/Documentos
restic restore latest --include /mnt/restic/files/leo/files/Documentos/contrato.pdf --target /tmp/restaurado
```

Ou navegue com `mkdir -p /mnt/restic-navegar && restic mount /mnt/restic-navegar` (em outro terminal) e copie o que precisar. Arquivos do Nextcloud restaurados direto em `/data/files` só aparecem na interface depois de `docker exec -u www-data nextcloud_app php occ files:scan --all`.

### Um dataset inteiro

1. Pare no Portainer as stacks que usam o dataset (ex.: `photos` para `/data/photos`).
2. Monte o dataset no caminho em que ele foi copiado e restaure por cima, sem cópia intermediária:
   ```bash
   mkdir -p /mnt/restic/photos && mount --bind /data/photos /mnt/restic/photos
   restic restore latest --include /mnt/restic/photos --target /
   umount /mnt/restic/photos
   ```
   Para comparar antes, restaure num disco com espaço (`--target /caminho/com/espaço`) e use `rsync -aHAX --delete` de lá.
3. `chown -R <docker_puid>:<docker_pgid> /data/photos` se o dono mudou, e suba as stacks de novo.

### Bancos de dados

Restaure o `docker-volumes` (ou só a pasta `db-dumps` do banco) e use o dump mais recente:

```bash
# na VM do banco, com o container do banco no ar e vazio (stack recém-criada)
docker exec -i <container> pg_restore -U <usuário> -d <banco> --clean --if-exists < <app>-<data>.dump
```

Os detalhes de cada aplicação: Nextcloud e Immich na [seção 11](../01-manual-implementacao/11-fotos-arquivos.md), LiteLLM na [seção 8](../01-manual-implementacao/08-stack-ia.md). Para o Authelia e o Grafana, pare o container da aplicação (`authelia`, `grafana`), restaure no `authelia_db`/`grafana_db` e suba de novo.

### O host Proxmox e as VMs

O host e as VMs são recriados, não restaurados: reinstale o Proxmox, rode o `setup-proxmox-host.yml`, o `vm-deploy.yml` e os playbooks das stacks ([reconstrução](04-reconstruindo-infraestrutura.md)). O `/etc` do host no restic serve de consulta para o que foi feito à mão: interfaces de rede, GRUB e IOMMU para o passthrough da GPU, definições das VMs em `/etc/pve/qemu-server/`. Restaure-o num diretório temporário e copie só o que precisar. **Nunca sobrescreva o `/etc` inteiro.**

## Snapshots ZFS

Os snapshots automáticos (`zfs-auto-snapshot`, instalado pelo `setup-proxmox-host.yml`) valem **só para `data/notes`**, pela propriedade `com.sun:auto-snapshot`. Eles servem para desfazer edições da IA nos vaults pelo `.zfs/snapshot` ([seção 12](../01-manual-implementacao/12-segundo-cerebro.md#desfazer-uma-edição)). Snapshot no mesmo pool não é backup: se o pool se perde, ele vai junto. Nos datasets com `quota` (`photos`, `files`), os snapshots ainda consumiriam a cota.

Para um ponto de volta antes de uma mudança arriscada, tire um à mão e apague depois ([guia de snapshots](../03-guias-sustentacao/11-guia-snapshots-zfs.md)):

```bash
zfs snapshot data/docker-volumes@antes-da-mudanca
zfs destroy data/docker-volumes@antes-da-mudanca
```

## Repositório e segredos

- O repositório (wiki, Ansible, stacks) está no GitHub; cada `git push` é uma cópia fora de casa.
- O `vault.yml` só entra no git criptografado. A senha do Ansible Vault e a `restic_senha` ficam no seu gerenciador de senhas.
- Sem essas duas senhas, o GitHub e o backup na nuvem não servem para nada.

## Testes de restauração

Um backup que nunca foi restaurado não é confiável. **A cada três meses:**

1. Escolha um arquivo de cada dataset (`docker-volumes`, `photos`, `files`, `notes`) e restaure-o do repositório **da nuvem** em `/tmp/teste-restauro`. Compare com o original: `sha256sum`.
2. Restaure o dump mais recente de um banco num Postgres descartável e apague o container: `docker run --rm -d --name pg-teste -e POSTGRES_PASSWORD=x postgres:17-alpine` (a mesma versão principal dos bancos; o `pg_restore` não lê dump de versão mais nova), espere o `docker exec pg-teste pg_isready`, rode `docker exec -i pg-teste pg_restore -U postgres -d postgres --no-owner --no-acl < <app>-<data>.dump` e faça uma consulta qualquer (`docker exec pg-teste psql -U postgres -c '\dt'`).
3. Confira que `restic snapshots` mostra backups diários recentes nos dois repositórios, e que o `journalctl -u backup-restic` do último domingo tem o `check` sem erro.
4. Anote a data do teste e qualquer passo que tenha faltado nesta página, e corrija a página.
