"""Testes unitários do MCP ops (base dos agentes, página 13): política, Portainer, auditoria, ferramentas e runner.
Sem rede, sem FastMCP e sem ansible-playbook reais: o Portainer e os comandos são falsos."""
from __future__ import annotations

import json
import struct
import sys

import pytest

from test_observabilidade import ROOT

sys.path.insert(0, str(ROOT / "server/docker/images/ops"))

from ops import auditoria  # noqa: E402
from ops.config import Config  # noqa: E402
from ops.ferramentas import ferramentas  # noqa: E402
from ops.politica import Recusado, limpar_saida  # noqa: E402
from ops.portainer import Portainer  # noqa: E402

AMBIENTE = {
    "OPS_MODO": "controle",
    "PORTAINER_URL": "http://portainer:9000",
    "PORTAINER_API_KEY": "ptr_x",
    "OPS_ENDPOINTS": json.dumps({"core": "local", "ai": "ai-desktop-vm"}),
    "OPS_CONTAINERS_PROTEGIDOS": "traefik,authelia,portainer",
    "OPS_STACKS_PROTEGIDAS": "core,agents",
    "OPS_PLAYBOOKS": json.dumps({"setup-media-stack-volumes.yml": "Mídia"}),
    "NOTIFICACOES_WEBHOOK_URL": "http://n8n:5678/webhook/notificar",
    "NOTIFICACOES_WEBHOOK_TOKEN": "tok",
    "OPS_REPO_DIR": "/repo",
    "OPS_REPO_URL": "https://github.com/x/y.git",
    "OPS_INVENTARIO": "inventories/home/hosts.ini",
    "OPS_CHAVE_SSH": "/segredos/id_ed25519",
    "OPS_PLANO_VALIDADE_MIN": "30",
}


def _cfg(**mudancas) -> Config:
    return Config.do_ambiente({**AMBIENTE, **mudancas})


def _frame(stream: int, texto: str) -> bytes:
    dados = texto.encode()
    return struct.pack(">BxxxL", stream, len(dados)) + dados


class PortainerFalso:
    """Responde (método, caminho) com (status, corpo) e guarda as chamadas."""

    def __init__(self, logs: bytes = b""):
        self.chamadas: list[tuple[str, str, dict | None]] = []
        self.rotas = {
            ("GET", "/api/endpoints"): (200, [{"Id": 1, "Name": "local"}, {"Id": 2, "Name": "ai-desktop-vm"}]),
            ("GET", "/api/endpoints/1/docker/containers/json?all=1"): (200, [
                {"Id": "c1", "Names": ["/jellyfin"], "Image": "jellyfin/jellyfin:10", "State": "running",
                 "Status": "Up 2 hours (healthy)"},
                {"Id": "c2", "Names": ["/traefik"], "Image": "traefik:v3", "State": "running", "Status": "Up 1 day"}]),
            ("GET", "/api/endpoints/2/docker/containers/json?all=1"): (200, [
                {"Id": "c9", "Names": ["/litellm_proxy"], "Image": "litellm", "State": "exited",
                 "Status": "Exited (1) 5 minutes ago"}]),
            ("POST", "/api/endpoints/1/docker/containers/c1/restart"): (204, b""),
            ("GET", "/api/endpoints/1/docker/containers/c1/logs?stdout=1&stderr=1&tail=100"): (200, logs),
            ("GET", "/api/stacks"): (200, [
                {"Id": 3, "Name": "core", "EndpointId": 1, "Status": 1, "Env": []},
                {"Id": 7, "Name": "media", "EndpointId": 1, "Status": 1, "Env": [{"name": "TZ", "value": "X"}]}]),
            ("GET", "/api/stacks/7/file"): (200, {"StackFileContent": "services: {}\n"}),
            ("PUT", "/api/stacks/7?endpointId=1"): (200, {"Id": 7}),
        }

    def __call__(self, metodo, caminho, corpo):
        self.chamadas.append((metodo, caminho, corpo))
        status, resposta = self.rotas.get((metodo, caminho), (404, {"message": "não encontrado"}))
        return status, resposta if isinstance(resposta, bytes) else json.dumps(resposta).encode()


def _ferr(cfg=None, falso=None, enviar=None):
    cfg = cfg or _cfg()
    falso = falso or PortainerFalso()
    avisos = []
    fs = ferramentas(cfg, Portainer(cfg, falso), None, enviar or avisos.append)
    return fs, falso, avisos


# --- Task 2: política, Portainer e auditoria ---

def test_modo_leitura_nao_tem_controle():
    fs, _, _ = _ferr(_cfg(OPS_MODO="leitura"))
    assert set(fs) == {"containers_listar", "container_logs", "stacks_listar", "playbooks_listar"}
    assert not any(f.destrutiva for f in fs.values())
    fs, _, _ = _ferr()
    assert set(fs) == {"containers_listar", "container_logs", "stacks_listar", "playbooks_listar",
                       "container_reiniciar", "stack_redeploy", "ansible_check", "ansible_aplicar"}
    for nome in ("container_reiniciar", "stack_redeploy", "ansible_aplicar"):
        assert fs[nome].destrutiva is True, nome
    assert fs["ansible_check"].destrutiva is False


def test_containers_protegidos_recusados(capsys):
    fs, falso, avisos = _ferr()
    with pytest.raises(Recusado):
        fs["container_reiniciar"].funcao(nome="traefik")
    assert not [c for c in falso.chamadas if c[0] == "POST"]
    registro = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert registro["evento"] == "ops_acao" and registro["resultado"] == "recusado"


def test_reiniciar_container():
    fs, falso, avisos = _ferr()
    texto = fs["container_reiniciar"].funcao(nome="jellyfin")
    assert ("POST", "/api/endpoints/1/docker/containers/c1/restart", None) in falso.chamadas
    assert "jellyfin" in texto
    assert avisos and "jellyfin" in avisos[-1]["mensagem"] and avisos[-1]["app"] == "ops"


def test_stack_protegida_e_redeploy():
    fs, falso, _ = _ferr()
    with pytest.raises(Recusado):
        fs["stack_redeploy"].funcao(nome="core")
    fs["stack_redeploy"].funcao(nome="media", puxar_imagens=True)
    put = next(c for c in falso.chamadas if c[0] == "PUT")
    assert put[1] == "/api/stacks/7?endpointId=1"
    assert put[2]["pullImage"] is True and put[2]["prune"] is False
    assert put[2]["stackFileContent"] == "services: {}\n"
    assert put[2]["env"] == [{"name": "TZ", "value": "X"}]


def test_listar_containers_das_duas_vms():
    fs, _, _ = _ferr()
    texto = fs["containers_listar"].funcao()
    assert "jellyfin" in texto and "litellm_proxy" in texto and "exited" in texto
    so_ai = fs["containers_listar"].funcao(vm="ai")
    assert "litellm_proxy" in so_ai and "jellyfin" not in so_ai


def test_logs_desmultiplexa_e_limpa():
    corpo = (_frame(1, "linha 1\n") + _frame(2, "DB_PASSWORD=segredo123\n")
             + _frame(1, "x" * 30_000 + "\n") + _frame(1, "ultima linha\n"))
    fs, _, _ = _ferr(_cfg(OPS_LIMITE_SAIDA="20000"), PortainerFalso(logs=corpo))
    texto = fs["container_logs"].funcao(nome="jellyfin", linhas=100)
    assert "segredo123" not in texto
    assert texto.rstrip().endswith("ultima linha")
    assert texto.startswith("[…truncado:")
    assert len(texto) <= 20000 + 60


def test_limpar_saida_mascara_segredos():
    texto = "ok\nvault_password: abc\nTOKEN=xyz\napi Secret here\nfim"
    limpo = limpar_saida(texto, 1000)
    for proibido in ("abc", "xyz", "Secret here"):
        assert proibido not in limpo
    assert limpo.count("[linha omitida: possível segredo]") == 3
    assert limpo.splitlines()[0] == "ok" and limpo.splitlines()[-1] == "fim"


def test_config_do_ambiente():
    cfg = _cfg()
    assert cfg.modo == "controle"
    assert cfg.endpoints == {"core": "local", "ai": "ai-desktop-vm"}
    assert cfg.containers_protegidos == frozenset({"traefik", "authelia", "portainer"})
    assert cfg.playbooks == {"setup-media-stack-volumes.yml": "Mídia"}
    assert cfg.limite_saida == 20000 and cfg.plano_validade_s == 1800
    with pytest.raises(ValueError):
        _cfg(OPS_MODO="tudo")


def test_aviso_que_falha_nao_derruba(capsys):
    def explode(_):
        raise OSError("n8n fora")
    fs, _, _ = _ferr(enviar=explode)
    fs["container_reiniciar"].funcao(nome="jellyfin")
    registro = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert registro["resultado"] == "ok" and registro["aviso"] == "falhou"


def test_registro_com_aviso():
    avisos = []
    reg = auditoria.registrar("container_reiniciar", "jellyfin", "erro", 1.234, "falhou", avisos.append)
    assert reg["duracao_s"] == 1.23 and reg["aviso"] == "enviado"
    assert avisos[0]["gravidade"] == "warning" and avisos[0]["app"] == "ops"


# --- Task 3: runner Ansible, servidor e imagem ---

from ops.runner import Runner  # noqa: E402

COMMIT_A, COMMIT_B = "a" * 40, "b" * 40


class Comandos:
    """executar falso: devolve o commit programado no rev-parse e saídas programadas no ansible-playbook."""

    def __init__(self, saida="PLAY RECAP ok=3 changed=1"):
        self.argvs: list[tuple[list[str], str, int]] = []
        self.commit = COMMIT_A
        self.saida = saida

    def __call__(self, argv, cwd, timeout):
        self.argvs.append((argv, cwd, timeout))
        if argv[:1] == ["git"] and "rev-parse" in argv:
            return 0, self.commit + "\n"
        if argv[:1] == ["git"]:
            return 0, "Already up to date.\n"
        return 0, self.saida

    def ansible(self):
        return [a for a in self.argvs if a[0][0] == "ansible-playbook"]


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _runner(cmd=None, relogio=None):
    return Runner(_cfg(), cmd or Comandos(), relogio or Relogio())


def test_check_gera_plano():
    cmd = Comandos()
    r = _runner(cmd).check("setup-media-stack-volumes.yml", None)
    assert r["plano_id"] and r["commit"] == COMMIT_A and r["rc"] == 0
    git = [a for a in cmd.argvs if a[0][0] == "git"]
    assert any("pull" in a[0] and "--ff-only" in a[0] for a in git)
    assert cmd.argvs.index(git[0]) < cmd.argvs.index(cmd.ansible()[0])
    argv, cwd, timeout = cmd.ansible()[0]
    assert cwd == "/repo/server/ansible" and timeout == 900
    assert argv[:3] == ["ansible-playbook", "-i", "inventories/home/hosts.ini"]
    assert "playbooks/setup-media-stack-volumes.yml" in argv
    assert "--check" in argv and "--diff" in argv
    assert argv[argv.index("-e") + 1] == "ansible_ssh_private_key_file=/segredos/id_ed25519"


def test_check_com_limite():
    cmd = Comandos()
    _runner(cmd).check("setup-media-stack-volumes.yml", "core-services-vm")
    argv = cmd.ansible()[0][0]
    assert argv[argv.index("-l") + 1] == "core-services-vm"


def test_aplicar_exige_plano_valido():
    cmd, relogio = Comandos(), Relogio()
    runner = _runner(cmd, relogio)
    with pytest.raises(Recusado):
        runner.aplicar("inexistente")
    # vencido
    plano = runner.check("setup-media-stack-volumes.yml", "core-services-vm")["plano_id"]
    relogio.t += 31 * 60
    with pytest.raises(Recusado):
        runner.aplicar(plano)
    # repositório mudou entre o check e o aplicar
    relogio.t += 1
    plano = runner.check("setup-media-stack-volumes.yml", "core-services-vm")["plano_id"]
    cmd.commit = COMMIT_B
    with pytest.raises(Recusado):
        runner.aplicar(plano)
    # válido: mesmo playbook e limite, sem --check/--diff; o plano só vale uma vez
    plano = runner.check("setup-media-stack-volumes.yml", "core-services-vm")["plano_id"]
    r = runner.aplicar(plano)
    argv, _, timeout = cmd.ansible()[-1]
    assert "--check" not in argv and "--diff" not in argv and timeout == 3600
    assert "playbooks/setup-media-stack-volumes.yml" in argv and argv[argv.index("-l") + 1] == "core-services-vm"
    assert r["playbook"] == "setup-media-stack-volumes.yml" and r["commit"] == COMMIT_B
    with pytest.raises(Recusado):
        runner.aplicar(plano)


def test_check_que_falha_nao_gera_plano():
    class Falha(Comandos):
        def __call__(self, argv, cwd, timeout):
            rc, out = super().__call__(argv, cwd, timeout)
            return (2, "fatal: UNREACHABLE") if argv[0] == "ansible-playbook" else (rc, out)
    r = _runner(Falha()).check("setup-media-stack-volumes.yml", None)
    assert r["rc"] == 2 and r["plano_id"] == ""


def test_playbook_fora_da_lista():
    cmd = Comandos()
    with pytest.raises(Recusado):
        _runner(cmd).check("vm-deploy.yml", None)
    assert cmd.argvs == []


def test_uma_execucao_por_vez():
    runner = _runner()
    assert runner._trava.acquire(blocking=False)
    try:
        with pytest.raises(Recusado, match="outra execução em andamento"):
            runner.check("setup-media-stack-volumes.yml", None)
    finally:
        runner._trava.release()


def test_saida_do_ansible_limpa():
    saida = "TASK [x]\nvault_password: segredo\n" + "y" * 50_000 + "\nPLAY RECAP"
    r = _runner(Comandos(saida)).check("setup-media-stack-volumes.yml", None)
    assert "segredo" not in r["saida"] and r["saida"].endswith("PLAY RECAP")
    assert len(r["saida"]) <= 20000 + 60


def test_ferramentas_ansible_pelo_runner(capsys):
    cfg = _cfg()
    avisos = []
    fs = ferramentas(cfg, Portainer(cfg, PortainerFalso()), _runner(), avisos.append)
    texto = fs["ansible_check"].funcao(playbook="setup-media-stack-volumes.yml")
    plano = texto.splitlines()[0].split(": ", 1)[1]
    assert "PLAY RECAP" in fs["ansible_aplicar"].funcao(plano_id=plano)
    assert [a["titulo"] for a in avisos][-1].startswith("IA: ansible_aplicar")


IMG = ROOT / "server/docker/images/ops"


def test_imagem_ops():
    import yaml
    from test_observabilidade import render
    d = (IMG / "Dockerfile").read_text(encoding="utf-8")
    assert [l for l in d.splitlines() if l and not l.startswith("#")][0] == "FROM python:3.13-slim"
    assert "git" in d and "openssh-client" in d and "ansible-galaxy collection install -r" in d
    assert "\nUSER " in d and "USER root" not in d.split("\nUSER ")[-1]
    m = yaml.safe_load((ROOT / "server/ansible/inventories/home/group_vars/all/main.yml").read_text(encoding="utf-8"))
    req = render("templates/agents/ops-requirements.txt.j2", ops_fastmcp_version=m["ops_fastmcp_version"],
                 ops_ansible_core_version=m["ops_ansible_core_version"])
    assert "fastmcp==4.1.2" in req and "ansible-core==2.21.5" in req


def test_servidor_registra_com_anotacoes():
    srv = (IMG / "ops/server.py").read_text(encoding="utf-8")
    for trecho in ('transport="http"', 'host="0.0.0.0"', "port=8000", 'path="/mcp"', "destructiveHint",
                   "readOnlyHint", "Config.do_ambiente(os.environ)", "enviar_webhook"):
        assert trecho in srv, trecho


# --- Revisão final (4c1) ---

import asyncio  # noqa: E402

from ops.autenticacao import ExigirToken  # noqa: E402


def _chamar_asgi(app, cabecalhos: list[tuple[bytes, bytes]]):
    enviados = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        enviados.append(msg)

    escopo = {"type": "http", "method": "POST", "path": "/mcp", "headers": cabecalhos}
    asyncio.run(app(escopo, receive, send))
    return enviados


def test_ops_exige_token_interno():
    """C1: sem o token do hub, o ops recusa (qualquer container nas redes compartilhadas alcançaria a porta 8000)."""
    chamadas = []

    async def app(escopo, receive, send):
        chamadas.append(escopo["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    protegido = ExigirToken(app, token="segredo-interno")
    for cab in ([], [(b"authorization", b"Bearer errado")], [(b"authorization", b"segredo-interno")]):
        resp = _chamar_asgi(protegido, cab)
        assert resp[0]["status"] == 401, cab
    assert chamadas == []
    resp = _chamar_asgi(protegido, [(b"authorization", b"Bearer segredo-interno")])
    assert resp[0]["status"] == 200 and chamadas == ["/mcp"]
    with pytest.raises(ValueError):
        ExigirToken(app, token="")


def test_saida_do_ansible_mascara_env_e_pem():
    """C2: o --diff de um .env mostra chaves cujo nome não tem 'token'/'password'."""
    saida = "\n".join([
        "--- before", "+++ after", "@@ -1,2 +1,4 @@",
        "+PORTAINER_API_KEY=ptr_abc123", "-OPENAI_API_KEY=sk-old", "+LANGFUSE_SALT=salzinho",
        "+LANGFUSE_OTEL_AUTH=cGs6c2s=",
        "-----BEGIN OPENSSH PRIVATE KEY-----", "b3BlbnNzaC1rZXktdjEAAAAA", "-----END OPENSSH PRIVATE KEY-----",
        "TASK [ok]", "changed: [core-services-vm]",
    ])
    limpo = limpar_saida(saida, 10_000)
    for proibido in ("ptr_abc123", "sk-old", "salzinho", "cGs6c2s=", "b3BlbnNzaC1rZXktdjEAAAAA"):
        assert proibido not in limpo, proibido
    assert "TASK [ok]" in limpo and "changed: [core-services-vm]" in limpo and "+++ after" in limpo


def test_playbook_que_falha_registra_erro(capsys):
    """I1: rc ≠ 0 vira resultado 'erro' (dispara o alerta ops-acao-falhou), mas a saída volta para a IA."""
    class Falha(Comandos):
        def __call__(self, argv, cwd, timeout):
            rc, out = super().__call__(argv, cwd, timeout)
            return (2, "fatal: [core-services-vm]: FAILED!") if argv[0] == "ansible-playbook" and "--check" not in argv else (rc, out)
    cfg = _cfg()
    avisos = []
    fs = ferramentas(cfg, Portainer(cfg, PortainerFalso()), Runner(cfg, Falha(), Relogio()), avisos.append)
    plano = fs["ansible_check"].funcao(playbook="setup-media-stack-volumes.yml").splitlines()[0].split(": ", 1)[1]
    texto = fs["ansible_aplicar"].funcao(plano_id=plano)
    assert "FAILED" in texto
    registro = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert registro["acao"] == "ansible_aplicar" and registro["resultado"] == "erro"
    assert registro["alvo"] == "setup-media-stack-volumes.yml"  # o playbook, não o plano_id
    assert avisos[-1]["gravidade"] == "warning"


def test_imagem_ops_usa_o_uid_do_compose():
    """I3: o ssh aborta ('No user exists for uid') se o UID do container não existir no /etc/passwd da imagem."""
    d = (IMG / "Dockerfile").read_text(encoding="utf-8")
    assert "ARG UID" in d and "ARG GID" in d
    assert "useradd --uid ${UID} --gid ${GID}" in d or "useradd --uid \"${UID}\" --gid \"${GID}\"" in d
