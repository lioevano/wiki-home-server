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
    "OPS_INVENTARIO": "server/ansible/inventories/home/hosts.ini",
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
