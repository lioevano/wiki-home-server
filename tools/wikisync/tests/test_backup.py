"""Backup automatizado (spec 2026-10-21-backup-design): restic no host Proxmox e dumps dos bancos."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest
import yaml

from test_observabilidade import ROOT, render

ANS = ROOT / "server/ansible"
ROLE = ANS / "roles/infra/restic"
MAIN = ANS / "inventories/home/group_vars/all/main.yml"
VAULT_EX = ANS / "inventories/home/group_vars/all/vault.yml.example"
DUMP_TASKS = ANS / "playbooks/tasks/dump-postgres.yml"


def _main() -> dict:
    return yaml.safe_load(MAIN.read_text(encoding="utf-8"))


def _vars_restic() -> dict:
    m = _main()
    nomes = {"{{ zfs_docker_volumes_dataset_name }}": "docker-volumes", "{{ zfs_photos_dataset_name }}": "photos",
             "{{ zfs_files_dataset_name }}": "files", "{{ zfs_notes_dataset_name }}": "notes"}

    def resolve(s: str) -> str:
        for k, v in nomes.items():
            s = s.replace(k, v)
        return s

    return {"zfs_base_pool_path": "/data", "restic_datasets": [resolve(d) for d in m["restic_datasets"]],
            "restic_excluir": [resolve(e) for e in m["restic_excluir"]], "restic_retencao": m["restic_retencao"],
            "restic_check_parcial": m["restic_check_parcial"], "restic_host_caminhos": m["restic_host_caminhos"]}


# --- Variáveis e role ---

def test_variaveis_do_backup():
    m = _main()
    assert m["restic_datasets"] == ["{{ zfs_docker_volumes_dataset_name }}", "{{ zfs_photos_dataset_name }}",
                                    "{{ zfs_files_dataset_name }}", "{{ zfs_notes_dataset_name }}"]
    assert "{{ zfs_media_dataset_name }}" not in m["restic_datasets"]  # rebaixável e grande demais
    assert m["restic_excluir"] == ["{{ zfs_docker_volumes_dataset_name }}/prometheus/data",
                                   "{{ zfs_docker_volumes_dataset_name }}/loki/data",
                                   "{{ zfs_docker_volumes_dataset_name }}/ollama/models",
                                   "{{ zfs_photos_dataset_name }}/thumbs", "{{ zfs_photos_dataset_name }}/encoded-video"]
    assert m["restic_horario"] == "*-*-* 04:30:00"  # depois de todos os dumps (o último às 03:45)
    assert m["restic_retencao"] == "--keep-daily 7 --keep-weekly 4 --keep-monthly 12"
    v = yaml.safe_load(VAULT_EX.read_text(encoding="utf-8"))
    assert v["restic_senha"]
    repos = {r["nome"]: r for r in v["restic_repositorios"]}
    assert repos["externo"]["montagem"] and repos["externo"]["repositorio"].startswith(repos["externo"]["montagem"])
    assert repos["nuvem"]["repositorio"].startswith("s3:")
    assert set(repos["nuvem"]["ambiente"]) == {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}


def test_role_no_host_proxmox():
    plays = yaml.safe_load((ANS / "playbooks/setup-proxmox-host.yml").read_text(encoding="utf-8"))
    roles = [r["role"] if isinstance(r, dict) else r for r in plays[0]["roles"]]
    assert "infra/restic" in roles and roles.index("infra/proxmox-host-config") < roles.index("infra/restic")
    assert any("vault.yml" in f for f in plays[0]["vars_files"])


def _tarefas():
    return yaml.safe_load((ROLE / "tasks/main.yml").read_text(encoding="utf-8"))


def test_segredos_do_restic_so_para_root():
    t = _tarefas()
    env = next(x for x in t if "/etc/restic/repositorios/" in str(x.get("ansible.builtin.copy", {}).get("dest", "")))
    assert env["ansible.builtin.copy"]["mode"] == "0600" and env.get("no_log") is True
    assert "| quote" in env["ansible.builtin.copy"]["content"]  # senha com caractere especial não quebra o source
    d = next(x for x in t if x.get("ansible.builtin.file", {}).get("path") == "/etc/restic/repositorios")
    assert d["ansible.builtin.file"]["mode"] == "0700"


def test_unit_e_timer():
    t = _tarefas()
    copias = {x["ansible.builtin.copy"]["dest"]: x["ansible.builtin.copy"]["content"]
              for x in t if "ansible.builtin.copy" in x and "content" in x["ansible.builtin.copy"]}
    svc = copias["/etc/systemd/system/backup-restic.service"]
    assert "Type=oneshot" in svc and "ExecStart=/usr/local/sbin/backup-restic.sh" in svc
    assert "Nice=10" in svc
    timer = copias["/etc/systemd/system/backup-restic.timer"]
    assert "OnCalendar={{ restic_horario }}" in timer and "Persistent=true" in timer
    # o nome backup-* entra no coletor systemd do Alloy do host e no alerta timer-falhou
    alloy = (ANS / "roles/infra/alloy/templates/config.alloy.j2").read_text(encoding="utf-8")
    assert '(notes|backup)-.+' in alloy


# --- Script, rodando com comandos falsos ---

FALSOS = {
    "zfs": 'echo "zfs $*" >> "$LOG"',
    "mount": 'echo "mount $*" >> "$LOG"',
    "umount": 'echo "umount $*" >> "$LOG"',
    "mountpoint": 'echo "mountpoint $*" >> "$LOG"; [ -e "$TMPDIR_TESTE/montado$2" ]',
    "date": 'echo "${DIA:-3}"',
    "restic": 'echo "restic[$RESTIC_REPOSITORY] $*" >> "$LOG"; '
              'case "$RESTIC_REPOSITORY:$1" in *falha*:backup) exit 3;; esac; exit 0',
}


def _rodar(tmp_path, repos: dict[str, str], dia="3"):
    script = tmp_path / "backup.sh"
    script.write_text(render("roles/infra/restic/templates/backup-restic.sh.j2", **_vars_restic()))
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for nome, corpo in FALSOS.items():
        f = bin_ / nome
        f.write_text("#!/bin/bash\n" + corpo + "\n")
        f.chmod(0o755)
    envs = tmp_path / "envs"
    envs.mkdir()
    for nome, conteudo in repos.items():
        (envs / f"{nome}.env").write_text(conteudo)
    log = tmp_path / "log"
    log.write_text("")
    env = dict(os.environ, PATH=f"{bin_}:{os.environ['PATH']}", LOG=str(log), RESTIC_BASE=str(tmp_path / "mnt"),
               RESTIC_ENV_DIR=str(envs), DIA=dia, TMPDIR_TESTE=str(tmp_path))
    r = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=30)
    return r, log.read_text().splitlines()


@pytest.mark.skipif(sys.platform == "win32", reason="bash")
def test_backup_completo(tmp_path):
    r, log = _rodar(tmp_path, {"nuvem": "RESTIC_REPOSITORY=s3:x\nRESTIC_PASSWORD='a b$c'\n"})
    assert r.returncode == 0, r.stderr
    mnt = tmp_path / "mnt"
    for ds in ("docker-volumes", "photos", "files", "notes"):
        assert f"zfs snapshot data/{ds}@restic" in log
        assert f"mount -t zfs -o ro data/{ds}@restic {mnt}/{ds}" in log
        assert log.index(f"zfs snapshot data/{ds}@restic") < log.index(next(l for l in log if " backup " in l))
        assert log[-8:].count(f"zfs destroy data/{ds}@restic") == 1  # limpeza no fim (trap)
    backup = next(l for l in log if " backup " in l)
    assert f"--exclude {mnt}/docker-volumes/prometheus/data" in backup
    assert f"--exclude {mnt}/docker-volumes/loki/data" in backup
    assert "media" not in backup
    assert backup.endswith(" /etc")  # configuração do host vai junto
    assert any("forget --prune --host homeserver --group-by host --keep-daily 7" in l for l in log)
    assert not any(" check " in l for l in log)  # só aos domingos


@pytest.mark.skipif(sys.platform == "win32", reason="bash")
def test_repositorio_que_falha_nao_impede_o_outro(tmp_path):
    r, log = _rodar(tmp_path, {"a-falha": "RESTIC_REPOSITORY=falha\nRESTIC_PASSWORD=x\n",
                               "b-nuvem": "RESTIC_REPOSITORY=s3:ok\nRESTIC_PASSWORD=x\n"})
    assert r.returncode == 1
    assert any(l.startswith("restic[s3:ok] backup") for l in log)
    assert not any(l.startswith("restic[falha] forget") for l in log)


@pytest.mark.skipif(sys.platform == "win32", reason="bash")
def test_disco_externo_desmontado_nao_grava_no_sistema(tmp_path):
    externo = {"externo": "RESTIC_REPOSITORY=/ext/restic\nRESTIC_PASSWORD=x\nRESTIC_MONTAGEM=/ext\n"}
    desmontado, montado = tmp_path / "a", tmp_path / "b"
    desmontado.mkdir(), montado.mkdir()
    r, log = _rodar(desmontado, externo)
    assert r.returncode == 1 and "não está montado" in r.stderr
    assert not any(l.startswith("restic[") for l in log)
    (montado / "montado").mkdir()
    (montado / "montado" / "ext").write_text("")
    r, log = _rodar(montado, externo)
    assert r.returncode == 0, r.stderr
    assert any(l.startswith("restic[/ext/restic] backup") for l in log)


@pytest.mark.skipif(sys.platform == "win32", reason="bash")
def test_verificacao_aos_domingos(tmp_path):
    r, log = _rodar(tmp_path, {"nuvem": "RESTIC_REPOSITORY=s3:x\nRESTIC_PASSWORD=x\n"}, dia="7")
    assert r.returncode == 0
    assert any("check --read-data-subset 5%" in l for l in log)


# --- Bancos no disco local com dump (DAD-5) ---

DUMPS = {  # playbook → (dump_nome, container, horário)
    "setup-core-networking.yml": ("authelia", "authelia_db", "*-*-* 03:15:00"),
    "setup-monitoring-stack-volumes.yml": ("grafana", "grafana_db", "*-*-* 03:20:00"),
    "setup-cloud-stack-volumes.yml": ("nextcloud", "nextcloud_db", "*-*-* 03:30:00"),
    "setup-ai-volumes.yml": ("litellm", "litellm_db", "*-*-* 03:45:00"),
}


def _include_dump(pb: str) -> dict:
    tarefas = yaml.safe_load((ANS / "playbooks" / pb).read_text(encoding="utf-8"))[0]["tasks"]
    return next(t for t in tarefas if t.get("ansible.builtin.include_tasks") == "tasks/dump-postgres.yml")


def test_quatro_bancos_com_o_mesmo_dump():
    for pb, (nome, container, horario) in DUMPS.items():
        v = _include_dump(pb)["vars"]
        assert (v["dump_nome"], v["dump_container"], v["dump_horario"]) == (nome, container, horario), pb
        assert v["dump_destino"].endswith(f"/{nome}/db-dumps"), pb
        assert "{{ zfs_docker_volumes_dataset_name }}" in v["dump_destino"], pb
    assert _include_dump("setup-cloud-stack-volumes.yml")["vars"]["dump_extra_dir"].endswith("nextcloud/config")


def test_tarefas_do_dump():
    t = yaml.safe_load(DUMP_TASKS.read_text(encoding="utf-8"))
    script = next(x for x in t if "ansible.builtin.template" in x)
    assert script["ansible.builtin.template"]["dest"] == "/usr/local/sbin/backup-{{ dump_nome }}-db.sh"
    assert script["ansible.builtin.template"]["src"].endswith("/../templates/backup-postgres.sh.j2")
    assert script["vars"]["backup_extra_dir"] == "{{ dump_extra_dir | default('') }}"
    destinos = [x["ansible.builtin.copy"]["dest"] for x in t if "ansible.builtin.copy" in x]
    assert destinos == ["/etc/systemd/system/backup-{{ dump_nome }}-db.service",
                        "/etc/systemd/system/backup-{{ dump_nome }}-db.timer"]
    sd = next(x["ansible.builtin.systemd"] for x in t if "ansible.builtin.systemd" in x)
    assert sd["name"] == "backup-{{ dump_nome }}-db.timer" and sd["enabled"] is True


def test_dump_sem_diretorio_extra():
    """O backup_extra_dir vazio não gera o tar (o 'is defined' antigo seria verdadeiro com string vazia)."""
    base = dict(backup_container="grafana_db", backup_db="grafana", backup_user="grafana",
                backup_dest="/mnt/x/grafana/db-dumps", backup_prefix="grafana")
    assert "tar " not in render("templates/backup-postgres.sh.j2", **base, backup_extra_dir="")
    assert "tar " in render("templates/backup-postgres.sh.j2", **base, backup_extra_dir="/opt/x")


def test_bancos_do_authelia_e_do_grafana_no_disco_local():
    core = yaml.safe_load((ROOT / "server/docker/stacks/core/docker-compose.yml").read_text(encoding="utf-8"))
    assert core["services"]["authelia_db"]["volumes"] == ["${AUTHELIA_DB_PATH}:/var/lib/postgresql/data"]
    pb = yaml.safe_load((ANS / "playbooks/setup-core-networking.yml").read_text(encoding="utf-8"))[0]["tasks"]
    deploy = next(t for t in pb if "community.docker.docker_compose_v2" in t)
    assert deploy["environment"]["AUTHELIA_DB_PATH"] == "{{ vm_local_data_path }}/authelia-db"
    role = yaml.safe_load((ANS / "roles/infra/authelia-config/tasks/main.yml").read_text(encoding="utf-8"))
    assert any(t.get("ansible.builtin.file", {}).get("path") == "{{ vm_local_data_path }}/authelia-db" for t in role)
    from test_fotos_arquivos import _configs
    cfg = _configs(ANS / "playbooks/setup-monitoring-stack-volumes.yml", "monitoring.env")
    assert cfg["MONITORING_GRAFANA_DB_PATH"] == "{{ vm_local_data_path }}/grafana-db"
    texto = "".join(p.read_text(encoding="utf-8") for p in (ANS / "playbooks").glob("*.yml"))
    assert "db_pg" not in texto


# --- Revisão final ---

def test_arquivo_do_repositorio_com_senha_dificil(tmp_path):
    """O content do role, renderizado com o filtro quote do Ansible, volta intacto pelo 'set -a; . arquivo'."""
    import shlex
    import jinja2
    t = yaml.safe_load((ROLE / "tasks/main.yml").read_text(encoding="utf-8"))
    env_task = next(x for x in t if "/etc/restic/repositorios/" in str(x.get("ansible.builtin.copy", {}).get("dest", "")))
    j = jinja2.Environment(trim_blocks=True)
    j.filters["quote"] = shlex.quote
    senha = "a b'c$d\"e"
    conteudo = j.from_string(env_task["ansible.builtin.copy"]["content"]).render(
        item={"nome": "nuvem", "repositorio": "s3:https://x/y", "ambiente": {"AWS_SECRET_ACCESS_KEY": "k$1 2"}},
        restic_senha=senha)
    arq = tmp_path / "nuvem.env"
    arq.write_text(conteudo)
    r = subprocess.run(["bash", "-c", f'set -a; . {arq}; printf "%s|%s|%s" "$RESTIC_PASSWORD" "$RESTIC_REPOSITORY" "$AWS_SECRET_ACCESS_KEY"'],
                       capture_output=True, text=True)
    assert r.stdout == f"{senha}|s3:https://x/y|k$1 2"


@pytest.mark.skipif(sys.platform == "win32", reason="bash")
def test_dataset_que_falha_deixa_codigo_1_mas_copia_os_outros(tmp_path):
    FALSOS["zfs"] = 'echo "zfs $*" >> "$LOG"; [ "$1 $2" != "snapshot data/photos@restic" ]'
    try:
        r, log = _rodar(tmp_path, {"nuvem": "RESTIC_REPOSITORY=s3:x\nRESTIC_PASSWORD=x\n"})
    finally:
        FALSOS["zfs"] = 'echo "zfs $*" >> "$LOG"'
    assert r.returncode == 1 and "data/photos" in r.stderr
    backup = next(l for l in log if " backup " in l)
    caminhos = backup.split()
    assert any(c.endswith("/mnt/files") for c in caminhos) and not any(c.endswith("/mnt/photos") for c in caminhos)
    assert any("forget --prune --host homeserver --group-by host" in l for l in log)


def test_cache_do_restic_e_verificacao_sem_check_mode():
    t = _tarefas()
    svc = next(x for x in t if x.get("ansible.builtin.copy", {}).get("dest") == "/etc/systemd/system/backup-restic.service")
    assert "Environment=RESTIC_CACHE_DIR=/var/cache/restic" in svc["ansible.builtin.copy"]["content"]
    timer = next(x for x in t if x.get("ansible.builtin.systemd_service", {}).get("name") == "backup-restic.timer")
    assert timer["when"] == "not ansible_check_mode"
    dump = yaml.safe_load(DUMP_TASKS.read_text(encoding="utf-8"))
    assert next(x for x in dump if "ansible.builtin.systemd" in x)["when"] == "not ansible_check_mode"
    assert "ollama/models" in str(_main()["restic_excluir"])
