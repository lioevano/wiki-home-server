# Design: backup automatizado (restic) e bancos no disco local

- **Data:** 2026-10-21
- **Autor:** Léo Ivan (com Claude)
- **Status:** decidido de forma autônoma, a pedido do Léo ("pode seguir da mesma forma autônoma com os demais pontos").
- **Caminho:** arquitetural: role novo no host Proxmox, mudança de volume de dois bancos e reescrita da página de backup.
- **Origem:** "Backup automatizado (sanoid, restic ou PBS)" nos itens adiados; achado da rodada de arrumação (Postgres do Authelia e do Grafana no NFS, contra a DAD-5).

## 1. Objetivo

Cumprir a regra 3-2-1 sem passos manuais:

- **Cópia 1:** os dados em produção.
- **Cópia 2:** um disco externo no host Proxmox.
- **Cópia 3:** fora de casa (nuvem compatível com S3, ex.: Backblaze B2).

Tudo instalado pelo Ansible a partir da wiki, avisando quando falhar e com restauração documentada e testável.

### Critérios de pronto

- Role `infra/restic` no `setup-proxmox-host.yml`, com repositórios, senha e credenciais no vault e a unit `backup-restic` diária.
- O alerta `timer-falhou` cobre a unit `backup-restic` (o coletor `systemd` do Alloy do host já inclui `backup-*`).
- Postgres do Authelia e do Grafana no disco local da VM, com dump diário no NFS (DAD-5), pelo mesmo `tasks/dump-postgres.yml` que passa a servir os quatro bancos.
- Página `04-manutencao-recuperacao/02-backup-restore-estrategia.md` reescrita: o que é copiado, para onde, quando, como restaurar e como testar.
- `test`, `check`, `build` e `lint` passam.

## 2. Decisões

| # | Tema | Escolha | Por quê |
|---|---|---|---|
| B1 | Ferramenta | **restic** (pacote do Debian no host Proxmox) | Deduplicação e criptografia no cliente. Um binário fala com disco local, SFTP e S3/B2 sem nada instalado do outro lado. O Borg exigiria Borg no destino. O PBS exige outra máquina e copia discos de VM, não arquivos. |
| B2 | Onde roda | **Host Proxmox** | É onde o ZFS está: o backup sai de um snapshot (consistente) e não passa pelo NFS. |
| B3 | Consistência | Para cada dataset da lista: `zfs snapshot data/<ds>@restic` → `mount -t zfs` em `/mnt/restic/<ds>` (só leitura) → `restic backup /mnt/restic/...` → desmonta e destrói o snapshot (também em erro, por `trap`) | O caminho é sempre o mesmo, o que permite deduplicar contra o backup anterior e restaurar sem adivinhar o nome do snapshot. |
| B4 | O que entra | `restic_datasets`: `docker-volumes` (configs e dumps dos bancos), `photos`, `files`, `notes`. Fora: `media` (rebaixável e grande demais para a nuvem) e `backups`. `restic_excluir`: `prometheus/data`, `loki/data` (métricas e logs, que mudam o tempo todo e não valem o espaço) | Só o que não se recupera de outro lugar. |
| B5 | Destinos | `restic_repositorios` no vault: lista de `{nome, repositorio, montagem?, ambiente}`. O modelo traz um disco externo (`/mnt/backup-externo/restic`, com `montagem` para não gravar no disco do sistema se o externo não estiver montado) e um B2 por S3. Mesma senha (`restic_senha`) para os dois. | Um repositório que falha não impede o outro; a unit termina com erro e o alerta avisa. |
| B6 | Retenção e verificação | `restic forget --prune --keep-daily 7 --keep-weekly 4 --keep-monthly 12` depois de cada backup; aos domingos, `restic check --read-data-subset 5%` | Um ano de mensais. A leitura parcial pega corrupção sem baixar o repositório inteiro toda semana. |
| B7 | Agenda | Timer `backup-restic` às 04:30, `Persistent=true` | Depois dos dumps: Immich às 02:00, Authelia 03:15, Grafana 03:20, Nextcloud 03:30, LiteLLM 03:45. |
| B8 | Bancos do Authelia e do Grafana | Saem do NFS para `{{ vm_local_data_path }}/authelia-db` e `/grafana-db`, com dump diário em `docker-volumes/<app>/db-dumps` | O Postgres não deve rodar sobre NFS com `all_squash` (o dono dos arquivos não é o usuário do Postgres). É a mesma regra DAD-5 dos outros bancos. Nada foi implantado, então não há dado a migrar. |
| B9 | Dump genérico | `ansible/playbooks/tasks/dump-postgres.yml` (script `backup-postgres.sh.j2`, `.service`, `.timer`, habilitar), incluído com variáveis pelos quatro bancos (Authelia, Grafana, Nextcloud, LiteLLM) | Hoje cada playbook repete as três tarefas; com quatro bancos, a repetição vira fonte de erro. |
| B10 | Snapshots locais | Continuam só em `data/notes` (desfazer edição da IA). O versionamento dos outros datasets fica com o restic | Snapshot no mesmo pool não é backup. E com `quota` (photos, files) os snapshots consumiriam a cota. |
| B11 | Discos das VMs e host | Sem backup de imagem (vzdump). O `/etc` do host (`restic_host_caminhos`) entra no restic, copiado direto | As VMs são recriadas pelo Ansible, e os bancos saem pelos dumps para o NFS. O `/etc` guarda o que foi feito à mão no host: rede, GRUB/IOMMU, `/etc/pve`. |
| B12 | Avisos | A falha vira unit `failed` → alerta `timer-falhou`. O sucesso não avisa | Para não acostumar o Telegram a mensagens que ninguém lê. |

## 3. Restauração (documentada na página 04/02)

- **Um arquivo ou pasta:** `restic -r <repo> snapshots`; `restic -r <repo> restore latest --include /mnt/restic/files/<caminho> --target /tmp/restaurado`, ou `restic mount /mnt/restic-montado` para navegar.
- **Dataset inteiro:** pare as stacks que usam o dataset e restaure em `--target /` com `--include /mnt/restic/<ds>`. Depois, `rsync -a --delete /mnt/restic/<ds>/ /data/<ds>/`.
- **Bancos:** pelo dump mais recente em `docker-volumes/<app>/db-dumps` (`pg_restore`), como já descrito nas páginas 08 e 11.
- **Teste trimestral:** restaurar um arquivo de cada dataset do repositório da nuvem num diretório temporário e comparar com `sha256sum`.

## 4. Fora do escopo

- Imagem do host Proxmox: ele é reinstalado, e o `/etc` copiado serve de consulta. O vault não entra porque fica no git, criptografado.
- Páginas 04/04 e 04/05 deixam de contar com backup de VM (vzdump); a migração de hardware ainda permite um backup pontual de VM, se o Léo quiser levá-las como estão.
- Backup dos traces do Langfuse e dos índices do qmd (regeráveis).
