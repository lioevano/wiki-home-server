"""Pendências do sub-projeto B (painel e notificações): spec 2026-10-20-pendencias-menores, #51 a #55."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest
import yaml

from test_observabilidade import ROOT, render
from test_midia import _env, _svc

APPS = ROOT / "server/docker/stacks/apps/docker-compose.yml"
AI = ROOT / "server/docker/stacks/ai/docker-compose.yml"
P07 = ROOT / "wiki/docs/01-manual-implementacao/07-deploy-apps.md"
P09 = ROOT / "wiki/docs/01-manual-implementacao/09-painel-notificacoes.md"


def _regras():
    return {r["uid"]: r for r in yaml.safe_load(render("templates/grafana/alerting/rules.yml.j2"))["groups"][0]["rules"]}


def test_disco_cheio_ignora_nfs():
    """#51: o espaço do pool é medido no host; cada VM que monta o NFS repetiria o mesmo alerta."""
    expr = _regras()["disco-cheio"]["data"][0]["model"]["expr"]
    assert 'fstype!~"tmpfs|overlay|squashfs|nfs.*"' in expr


@pytest.mark.skipif(shutil.which("node") is None, reason="node ausente")
def test_webhook_recusa_sem_token_configurado():
    """#52: sem a variável, 'Bearer ' + undefined viraria 'Bearer undefined' e aceitaria quem mandasse isso."""
    wf = json.loads((ROOT / "server/ansible/files/n8n/notificar.json").read_text(encoding="utf-8"))
    cond = next(n for n in wf["nodes"] if n["name"] == "Autorizado?")["parameters"]["conditions"]["conditions"][0]
    assert cond["leftValue"].startswith("={{ !!$env.NOTIFICACOES_WEBHOOK_TOKEN && ")
    js = cond["leftValue"][len("={{ "):-len(" }}")].replace("$env", "env").replace("$json", "json")
    teste = f"""
const casos = [
  [{{}}, {{headers: {{authorization: 'Bearer undefined'}}}}, false],
  [{{NOTIFICACOES_WEBHOOK_TOKEN: ''}}, {{headers: {{authorization: 'Bearer '}}}}, false],
  [{{NOTIFICACOES_WEBHOOK_TOKEN: 'abc'}}, {{headers: {{authorization: 'Bearer abc'}}}}, true],
  [{{NOTIFICACOES_WEBHOOK_TOKEN: 'abc'}}, {{headers: {{}}}}, false],
];
for (const [env, json, esperado] of casos) {{
  const r = Boolean({js});
  if (r !== esperado) {{ console.error(JSON.stringify([env, json, r])); process.exit(1); }}
}}
"""
    r = subprocess.run(["node", "-e", teste], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_publicar_workflow_no_n8n_2():
    """#53: no n8n 2.x, update:workflow --active está obsoleto; o comando é publish:workflow."""
    texto = P09.read_text(encoding="utf-8")
    assert "n8n publish:workflow --id=HsNotificar00001" in texto
    assert "update:workflow" not in texto


TASK_APPS_ENV = ROOT / "server/ansible/playbooks/tasks/apps-env.yml"


def test_apps_env_montado_pelos_playbooks(tmp_path):
    """#54 e rodada de arrumação: os playbooks da stack apps montam o apps.env sozinhos, sem nomes repetidos."""
    tarefas = yaml.safe_load(TASK_APPS_ENV.read_text(encoding="utf-8"))
    sh = tarefas[0]["ansible.builtin.shell"].replace("{{ portainer_env_files_dest_path_on_vm }}", str(tmp_path))
    assert tarefas[0]["no_log"] is True and tarefas[0]["check_mode"] is False
    assert tarefas[1]["ansible.builtin.copy"]["mode"] == "0600" and tarefas[1]["no_log"] is True
    for nome, conteudo in {"productivity.env": "# x\nTZ=1\nA=1\n", "n8n.env": "TELEGRAM_BOT_TOKEN=t\nB=2\n",
                           "monitoring.env": "TELEGRAM_BOT_TOKEN=t\nC=3\n"}.items():  # automation.env ainda não existe
        (tmp_path / nome).write_text(conteudo, encoding="utf-8")
    r = subprocess.run(["bash", "-c", sh], capture_output=True, text=True, check=True)
    assert r.stdout.split() == ["TZ=1", "A=1", "TELEGRAM_BOT_TOKEN=t", "B=2", "C=3"]
    for pb in ("setup-productivity-automation-volumes.yml", "setup-n8n-volumes.yml", "setup-monitoring-stack-volumes.yml"):
        play = yaml.safe_load((ROOT / "server/ansible/playbooks" / pb).read_text(encoding="utf-8"))[0]
        assert play["tasks"][-1].get("ansible.builtin.include_tasks") == "tasks/apps-env.yml", pb


def test_diun_pelo_socket_proxy():
    """#55: o Diun não monta mais o socket do Docker; lê pelo proxy só de leitura."""
    for compose, diun, proxy in ((APPS, "diun", "docker-socket-proxy"), (AI, "diun_ai", "docker-socket-proxy-ai")):
        s = _svc(compose)
        d = s[diun]
        assert not any("docker.sock" in v for v in d.get("volumes", [])), diun
        assert _env(d)["DIUN_PROVIDERS_DOCKER_ENDPOINT"] == f"tcp://{proxy}:2375"
        p = _env(s[proxy])
        assert p["CONTAINERS"] == "1" and p["IMAGES"] == "1" and p["POST"] == "0"
        assert set(d["networks"]) & set(s[proxy]["networks"]), diun
        assert "ports" not in s[proxy]


def test_socket_proxy_em_rede_isolada():
    """Revisão final: CONTAINERS=1 mostra o Env de qualquer container (ex.: chaves do LiteLLM). Só quem precisa
    (Diun, Homepage) alcança o proxy, por uma rede interna própria; nenhuma rede de aplicações o enxerga."""
    for compose, proxy, rede, clientes in ((APPS, "docker-socket-proxy", "docker_socket", {"diun", "homepage"}),
                                           (AI, "docker-socket-proxy-ai", "diun_ai_socket", {"diun_ai"})):
        doc = yaml.safe_load(compose.read_text(encoding="utf-8"))
        assert doc["networks"][rede] == {"name": rede, "internal": True}, rede
        s = doc["services"]
        assert s[proxy]["networks"] == [rede], proxy
        com_acesso = {n for n, v in s.items() if rede in (v.get("networks") or [])} - {proxy}
        assert com_acesso == clientes, compose.name
