"""Testes do observador (sub-projeto 4c2, página 15): configuração, cliente MCP (JSON e SSE), laço do agente,
filtro de alertas, servidor HTTP e agendador. O hub e o LiteLLM são servidores HTTP falsos, locais."""
from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from test_observabilidade import ROOT, render

sys.path.insert(0, str(ROOT / "server/docker/images/observador"))
# Sem __pycache__ dentro de docker/images: o copy do playbook o levaria e forçaria a reconstrução da imagem.
sys.dont_write_bytecode = True

from observador import agente, prompts, saida  # noqa: E402
from observador.config import Config, ConfigInvalida  # noqa: E402
from observador.llm import ClienteLLM, ErroLLM  # noqa: E402
from observador.mcp import ClienteMCP, ErroMCP, _mensagens_sse  # noqa: E402
from observador.servidor import Observador, fazer_handler, impressao, proximo_boletim  # noqa: E402

AMBIENTE = {
    "OBSERVADOR_HUB_URL": "http://agentgateway:4000/mcp",
    "OBSERVADOR_HUB_TOKEN": "tok-hub",
    "OBSERVADOR_LLM_URL": "http://192.168.15.68:4000",
    "OBSERVADOR_LLM_CHAVE": "sk-obs",
    "OBSERVADOR_TOKEN": "tok-grafana",
    "NOTIFICACOES_WEBHOOK_URL": "http://n8n:5678/webhook/notificar",
    "NOTIFICACOES_WEBHOOK_TOKEN": "tok-n8n",
}


def _cfg(**mudancas) -> Config:
    return Config.do_ambiente({**AMBIENTE, **mudancas})


# --- Configuração ---

def test_config_padroes_e_obrigatorias():
    c = _cfg()
    assert (c.modelo, c.boletim_hora, c.max_passos, c.max_por_hora, c.reanalise_h, c.porta) == ("rapido", "07:30", 8, 6, 12, 8080)
    assert "observador-falhou" in c.ignorar
    assert c.excluir == ("homeassistant_", "n8n_")  # o estado da casa não sai para o LLM à toa
    assert _cfg(OBSERVADOR_EXCLUIR="").excluir == ()
    with pytest.raises(ConfigInvalida, match="OBSERVADOR_HUB_TOKEN"):
        Config.do_ambiente({**AMBIENTE, "OBSERVADOR_HUB_TOKEN": ""})
    with pytest.raises(ConfigInvalida, match="HH:MM"):
        _cfg(OBSERVADOR_BOLETIM_HORA="7h30")
    with pytest.raises(ConfigInvalida):
        _cfg(OBSERVADOR_MAX_PASSOS="0")
    assert _cfg(OBSERVADOR_BOLETIM_HORA="").boletim_hora == ""  # vazio desliga o boletim
    # A própria falha nunca é analisada, mesmo que a lista seja trocada (evita o laço).
    assert _cfg(OBSERVADOR_IGNORAR="disco-cheio").ignorar == {"disco-cheio", "observador-falhou"}


# --- Servidores falsos ---

class _Falso:
    """Servidor HTTP local; 'responder(caminho, corpo, cabecalhos)' devolve (código, cabeçalhos, corpo)."""

    def __init__(self, responder):
        self.pedidos: list[tuple[str, dict, dict]] = []
        falso = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                falso.pedidos.append((self.path, dict(self.headers), corpo))
                codigo, cab, resposta = responder(self.path, corpo, self.headers)
                dados = resposta.encode() if isinstance(resposta, str) else json.dumps(resposta).encode()
                self.send_response(codigo)
                for k, v in cab.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def fechar(self):
        self.srv.shutdown()


FERRAMENTAS = [
    {"name": "grafana_query_prometheus", "description": "Consulta PromQL", "inputSchema": {
        "type": "object", "properties": {"expr": {"type": "string"}}, "required": ["expr"]}},
    {"name": "ops_container_logs", "description": "Logs de um container"},
    {"name": "nome inválido!", "description": "descartada"},
]


def _hub(sse: bool = True, sessao: str | None = "s-1"):
    def responder(caminho, corpo, cab):
        assert cab["Authorization"] == "Bearer tok-hub"
        metodo = corpo.get("method")
        if "id" not in corpo:
            return 202, {}, ""
        if metodo == "initialize":
            resultado = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "hub"}}
        elif metodo == "tools/list":
            resultado = {"tools": FERRAMENTAS}
        elif metodo == "tools/call":
            nome = corpo["params"]["name"]
            if nome == "ops_container_logs":
                resultado = {"content": [{"type": "text", "text": "x" * 10000}]}
            else:
                resultado = {"content": [{"type": "text", "text": f"{nome}: 97.5"}], "isError": False}
        else:
            return 200, {"Content-Type": "application/json"}, {"jsonrpc": "2.0", "id": corpo["id"],
                                                               "error": {"code": -32601, "message": "método?"}}
        msg = {"jsonrpc": "2.0", "id": corpo["id"], "result": resultado}
        cab_resp = {"Mcp-Session-Id": sessao} if sessao else {}
        if sse:
            return 200, {**cab_resp, "Content-Type": "text/event-stream"}, f": ping\n\nevent: message\ndata: {json.dumps(msg)}\n\n"
        return 200, {**cab_resp, "Content-Type": "application/json"}, msg
    return _Falso(responder)


# --- Cliente MCP ---

def test_sse_ignora_eventos_sem_json():
    assert _mensagens_sse(": ping\n\ndata: {\"id\": 1}\n\ndata: nada\n\n") == [{"id": 1}]
    assert _mensagens_sse('data: {"id":\ndata:  2}\n') == [{"id": 2}]  # várias linhas 'data:' num evento


@pytest.mark.parametrize("sse", [True, False])
def test_cliente_mcp_sse_e_json(sse):
    hub = _hub(sse=sse)
    try:
        c = ClienteMCP(hub.url + "/mcp", "tok-hub")
        c.iniciar()
        assert [f["name"] for f in c.ferramentas()] == [f["name"] for f in FERRAMENTAS]
        assert c.chamar("grafana_query_prometheus", {"expr": "up"}) == "grafana_query_prometheus: 97.5"
        metodos = [p[2].get("method") for p in hub.pedidos]
        assert metodos == ["initialize", "notifications/initialized", "tools/list", "tools/call"]
        # Depois do initialize: versão do protocolo e a sessão que o hub devolveu.
        assert hub.pedidos[-1][1]["Mcp-Protocol-Version"] == "2025-06-18"
        assert hub.pedidos[-1][1]["Mcp-Session-Id"] == "s-1"
        assert "application/json" in hub.pedidos[0][1]["Accept"] and "text/event-stream" in hub.pedidos[0][1]["Accept"]
    finally:
        hub.fechar()


def test_cliente_mcp_sem_sessao_e_erros():
    hub = _hub(sessao=None)  # hub em modo stateless: sem Mcp-Session-Id
    try:
        c = ClienteMCP(hub.url + "/mcp", "tok-hub")
        c.iniciar()
        assert c.sessao is None and "Mcp-Session-Id" not in hub.pedidos[1][1]
        with pytest.raises(ErroMCP, match="método"):
            c._pedido("resources/list")
    finally:
        hub.fechar()
    with pytest.raises(ErroMCP, match="inalcançável"):
        ClienteMCP("http://127.0.0.1:9/mcp", "x", timeout=2).iniciar()
    errado = _Falso(lambda *a: (401, {}, {"erro": "chave"}))
    try:
        with pytest.raises(ErroMCP, match="401"):
            ClienteMCP(errado.url, "x").iniciar()
    finally:
        errado.fechar()


def test_resultado_com_erro_da_ferramenta():
    falso = _Falso(lambda c, corpo, h: (200, {"Content-Type": "application/json"}, {
        "jsonrpc": "2.0", "id": corpo["id"], "result": {"content": [{"type": "text", "text": "sem permissão"}],
                                                        "isError": True}}))
    try:
        assert ClienteMCP(falso.url, "x").chamar("ops_x", {}) == "ERRO da ferramenta: sem permissão"
    finally:
        falso.fechar()


# --- LLM e laço do agente ---

def _llm(roteiro: list[dict]):
    """LiteLLM falso: devolve as mensagens do roteiro em ordem."""
    fila = list(roteiro)

    def responder(caminho, corpo, cab):
        assert caminho == "/v1/chat/completions" and cab["Authorization"] == "Bearer sk-obs"
        return 200, {"Content-Type": "application/json"}, {
            "choices": [{"message": fila.pop(0)}], "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}}
    return _Falso(responder)


def _chamada(nome, argumentos, id_="c1"):
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": id_, "type": "function", "function": {"name": nome, "arguments": json.dumps(argumentos)}}]}


def test_conversao_de_ferramentas():
    conv = agente.ferramentas_para_llm(FERRAMENTAS)
    assert [f["function"]["name"] for f in conv] == ["grafana_query_prometheus", "ops_container_logs"]
    assert conv[1]["function"]["parameters"] == {"type": "object", "properties": {}}
    assert conv[0]["function"]["parameters"]["required"] == ["expr"]


def test_investigar_chama_ferramentas_e_responde():
    hub = _hub()
    llm = _llm([_chamada("grafana_query_prometheus", {"expr": "disco"}),
                _chamada("ops_container_logs", {"container": "x"}, "c2"),
                {"role": "assistant", "content": "Resumo: disco cheio."}])
    try:
        res = agente.investigar("sis", "tarefa", ClienteMCP(hub.url, "tok-hub"),
                                ClienteLLM(llm.url, "sk-obs", "rapido"), max_passos=8, limite_saida=500,
                                tempo_max_s=60, metadata={"trace_name": "observador-alerta"})
        assert res.texto == "Resumo: disco cheio."
        assert res.passos == 2 and res.ferramentas == ["grafana_query_prometheus", "ops_container_logs"]
        assert res.uso["total_tokens"] == 330
        ultimo = llm.pedidos[-1][2]
        assert ultimo["model"] == "rapido" and ultimo["metadata"] == {"trace_name": "observador-alerta"}
        assert ultimo["tool_choice"] == "auto" and len(ultimo["tools"]) == 2
        assert ultimo["cache_control_injection_points"] == [{"location": "message", "role": "system"}]
        saidas = [m for m in ultimo["messages"] if m["role"] == "tool"]
        assert saidas[0]["content"] == "grafana_query_prometheus: 97.5"
        assert len(saidas[1]["content"]) < 600 and "cortado" in saidas[1]["content"]  # 10.000 → 500 + aviso
        assert ultimo["messages"][0] == {"role": "system", "content": "sis"}
    finally:
        hub.fechar()
        llm.fechar()


def test_investigar_para_no_limite_de_passos():
    hub = _hub()
    llm = _llm([_chamada("grafana_query_prometheus", {"expr": "a"})] * 3
               + [{"role": "assistant", "content": "Resumo: parcial."}])
    try:
        res = agente.investigar("sis", "t", ClienteMCP(hub.url, "tok-hub"), ClienteLLM(llm.url, "sk-obs", "rapido"),
                                max_passos=3, limite_saida=500, tempo_max_s=60)
        assert res.texto == "Resumo: parcial." and res.passos == 3
        final = llm.pedidos[-1][2]
        # Fecha sem novas chamadas, mas com as definições (a Anthropic recusa histórico de ferramentas sem elas).
        assert final["tool_choice"] == "none" and final["tools"]
        assert final["messages"][-1] == {"role": "user", "content": agente.FECHAR}
    finally:
        hub.fechar()
        llm.fechar()


def test_investigar_respeita_o_tempo_e_erros_de_ferramenta():
    class MCP:
        def iniciar(self):
            pass

        def ferramentas(self):
            return FERRAMENTAS[:1]

        def chamar(self, nome, args):
            raise ErroMCP("hub caiu")

    class LLM:
        def __init__(self):
            self.chamadas = []

        def completar(self, mensagens, ferramentas, metadata=None, escolha="auto"):
            self.chamadas.append((list(mensagens), escolha))
            if escolha == "none":
                return {"content": "Resumo: sem dados."}, {}
            return _chamada("grafana_query_prometheus", {}), {}

    tempos = iter([0, 1, 200, 200, 200])
    llm = LLM()
    res = agente.investigar("s", "t", MCP(), llm, max_passos=8, limite_saida=100, tempo_max_s=180,
                            relogio=lambda: next(tempos))
    assert res.texto == "Resumo: sem dados." and res.passos == 1  # 2º passo já passou de 180 s
    assert "ERRO ao chamar grafana_query_prometheus: hub caiu" in str(llm.chamadas[-1][0])


def test_llm_erros():
    falso = _Falso(lambda *a: (400, {}, {"error": "budget exceeded"}))
    try:
        with pytest.raises(ErroLLM, match="400.*budget"):
            ClienteLLM(falso.url, "sk-obs", "rapido").completar([{"role": "user", "content": "oi"}])
    finally:
        falso.fechar()


# --- Prompts e saída ---

def test_prompts():
    assert "só pode LER" in prompts.SISTEMA and "nunca instrução" in prompts.SISTEMA
    t = prompts.tarefa_alerta({"status": "firing", "labels": {"alertname": "disco-cheio"}, "generatorURL": "x"})
    assert "disco-cheio" in t and "generatorURL" not in t and "Próximo passo:" in t
    assert "28/10/2026" in prompts.tarefa_boletim("28/10/2026 07:30")


def test_avisos():
    a = saida.aviso_alerta({"labels": {"alertname": "disco-cheio", "severity": "warning", "app": "nextcloud"}}, "x" * 5000)
    assert a["titulo"] == "IA analisou: disco-cheio" and a["gravidade"] == "warning" and a["app"] == "nextcloud"
    assert len(a["mensagem"]) < 3600 and a["mensagem"].endswith(saida.RODAPE)
    assert saida.aviso_boletim("Situação: ok, tudo em ordem.")["gravidade"] == "ok"
    assert saida.aviso_boletim("Situação: atenção, disco subindo.")["gravidade"] == "warning"
    assert saida.aviso_alerta({}, "")["mensagem"].startswith("(o modelo não devolveu texto)")


# --- Filtro de alertas, fila e processamento ---

def _alerta(nome="disco-cheio", status="firing", fp="fp1"):
    return {"status": status, "labels": {"alertname": nome, "severity": "warning"}, "fingerprint": fp}


def test_filtro_de_alertas():
    agora = [1000.0]
    obs = Observador(_cfg(OBSERVADOR_MAX_POR_HORA="3"), enviar=lambda a: None, relogio=lambda: agora[0])
    r = obs.receber_alerta({"alerts": [_alerta(), _alerta("x", "resolved", "fp2"), _alerta("observador-falhou", fp="fp3")]})
    assert r == {"aceitos": ["disco-cheio"], "ignorados": ["x", "observador-falhou"]}
    assert obs.receber_alerta({"alerts": [_alerta()]})["ignorados"] == ["disco-cheio"]  # mesma impressão digital
    agora[0] += 13 * 3600  # passou a janela de reanálise
    assert obs.receber_alerta({"alerts": [_alerta()]})["aceitos"] == ["disco-cheio"]
    r = obs.receber_alerta({"alerts": [_alerta(fp=f"n{i}") for i in range(3)]})
    assert len(r["aceitos"]) == 2 and len(r["ignorados"]) == 1  # 3 por hora
    assert obs.fila.qsize() == 4


def test_fila_cheia_nao_marca_como_visto():
    obs = Observador(_cfg(OBSERVADOR_FILA_MAX="1"), enviar=lambda a: None)
    obs.receber_alerta({"alerts": [_alerta(fp="a")]})
    r = obs.receber_alerta({"alerts": [_alerta(fp="b")]})
    assert r["ignorados"] == ["disco-cheio"] and "b" not in obs.vistos


def test_impressao_sem_fingerprint():
    a = {"labels": {"alertname": "x", "app": "y"}}
    assert impressao(a) == impressao({"labels": {"app": "y", "alertname": "x"}}) != impressao({"labels": {}})


def test_processar_envia_e_registra(capsys):
    hub = _hub()
    llm = _llm([{"role": "assistant", "content": "Resumo: ok."}])
    enviados = []
    cfg = _cfg(OBSERVADOR_HUB_URL=hub.url, OBSERVADOR_LLM_URL=llm.url)
    try:
        reg = Observador(cfg, enviar=enviados.append).processar("alerta", _alerta())
        assert reg["resultado"] == "ok" and reg["aviso"] == "enviado" and reg["alerta"] == "disco-cheio"
        assert enviados[0]["titulo"] == "IA analisou: disco-cheio"
        meta = llm.pedidos[0][2]["metadata"]
        assert meta["trace_name"] == "observador-alerta" and meta["tags"] == ["observador", "alerta", "disco-cheio"]
        linha = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert linha["evento"] == "observador" and linha["resultado"] == "ok"
    finally:
        hub.fechar()
        llm.fechar()


def test_processar_registra_erro_sem_derrubar(capsys):
    cfg = _cfg(OBSERVADOR_HUB_URL="http://127.0.0.1:9/mcp")
    reg = Observador(cfg, enviar=lambda a: None).processar("boletim")
    assert reg["resultado"] == "erro" and "inalcançável" in reg["detalhe"]
    linha = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    # O alerta observador-falhou procura exatamente estes dois campos no Loki.
    assert '"evento": "observador"' in json.dumps(linha, ensure_ascii=False)
    assert '"resultado": "erro"' in json.dumps(linha, ensure_ascii=False)


# --- Servidor HTTP e agendador ---

def test_servidor_http():
    obs = Observador(_cfg(), enviar=lambda a: None)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), fazer_handler(obs))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(corpo: bytes, token="tok-grafana"):
        req = urllib.request.Request(base + "/alerta", data=corpo, method="POST",
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    try:
        assert post(json.dumps({"alerts": [_alerta()]}).encode()) == (202, {"aceitos": ["disco-cheio"], "ignorados": []})
        assert post(b"{}", token="errado")[0] == 401
        assert post(b"nao-json")[0] == 400
        with urllib.request.urlopen(base + "/saude", timeout=5) as r:
            assert json.loads(r.read()) == {"ok": True, "fila": 1}
    finally:
        srv.shutdown()


def test_proximo_boletim():
    from datetime import timezone
    tz = timezone.utc
    assert proximo_boletim(datetime(2026, 10, 28, 6, 0, tzinfo=tz), "07:30") == datetime(2026, 10, 28, 7, 30, tzinfo=tz)
    assert proximo_boletim(datetime(2026, 10, 28, 7, 30, tzinfo=tz), "07:30") == datetime(2026, 10, 29, 7, 30, tzinfo=tz)


# --- Ligação na infraestrutura (stack agents, playbook, Grafana, vault) ---

import yaml  # noqa: E402

from test_fotos_arquivos import COMUNS, _configs, _pb_tasks, _vars_compose  # noqa: E402
from test_midia import _env, _svc  # noqa: E402

AGENTS = ROOT / "server/docker/stacks/agents/docker-compose.yml"
PB_AGENTS = ROOT / "server/ansible/playbooks/setup-agents-volumes.yml"
ANS = ROOT / "server/ansible"


def test_servico_no_compose_sem_porta_e_sem_escrita():
    s = _svc(AGENTS)["observador"]
    assert s["image"] == "${OBSERVADOR_IMAGE}" and s["pull_policy"] == "never"
    assert "ports" not in s and set(s["networks"]) == {"agents_internal", "proxy"}
    assert s["labels"]["diun.enable"] == "false" and s["user"] == "${DOCKER_PUID}:${DOCKER_PGID}"
    e = _env(s)
    assert e["OBSERVADOR_HUB_URL"] == "http://agentgateway:4000/mcp"  # rota de leitura, nunca a 4100
    assert e["OBSERVADOR_HUB_TOKEN"] == "${AGENTS_TOKEN_OBSERVADOR}"
    assert e["OBSERVADOR_LLM_URL"] == "http://${AI_DESKTOP_VM_IP}:4000"
    assert e["OBSERVADOR_LLM_CHAVE"] == "${LITELLM_KEY_OBSERVADOR}"  # LLM-4: chave própria, nunca a mestra
    assert not any("MASTER" in v or "ANTHROPIC" in v or "PORTAINER" in v for v in e.values())
    # Todas as variáveis da configuração existem no compose (e as do compose, no .env.template: dev.py lint).
    assert {"OBSERVADOR_HUB_URL", "OBSERVADOR_HUB_TOKEN", "OBSERVADOR_LLM_URL", "OBSERVADOR_LLM_CHAVE",
            "OBSERVADOR_TOKEN", "NOTIFICACOES_WEBHOOK_URL", "NOTIFICACOES_WEBHOOK_TOKEN"} <= set(e)
    Config.do_ambiente({k: "x" for k in e} | {"OBSERVADOR_BOLETIM_HORA": "07:30"})


def test_imagem_e_variaveis_no_playbook():
    t = _pb_tasks(PB_AGENTS)
    build = next(x for x in t if x.get("community.docker.docker_image", {}).get("name") == "localhost/homeserver/observador")
    img = build["community.docker.docker_image"]
    assert img["tag"] == "{{ observador_version }}" and img["force_source"] == "{{ observador_codigo.changed }}"
    copia = next(x for x in t if x.get("register") == "observador_codigo")["ansible.builtin.copy"]
    assert copia["src"] == "../../docker/images/observador/"
    c = _configs(PB_AGENTS, "agents.env")
    assert c["OBSERVADOR_IMAGE"] == "localhost/homeserver/observador:{{ observador_version }}"
    assert c["AGENTS_TOKEN_OBSERVADOR"] == "{{ agents_tokens_internos.observador }}"
    assert c["LITELLM_KEY_OBSERVADOR"] == "{{ litellm_client_keys.observador }}"
    assert c["OBSERVADOR_TOKEN"] == "{{ observador_token }}"
    assert {"OBSERVADOR_MODELO", "OBSERVADOR_BOLETIM_HORA"} <= set(c)
    assert _vars_compose(AGENTS) - COMUNS <= set(c)
    dockerfile = (ROOT / "server/docker/images/observador/Dockerfile").read_text(encoding="utf-8")
    assert "RUN pip" not in dockerfile and "FROM python:3.13-slim" in dockerfile
    assert "__pycache__" in (ROOT / "server/docker/images/observador/.dockerignore").read_text(encoding="utf-8")


def test_codigo_so_com_biblioteca_padrao():
    """Sem dependências: nada para fixar nem vigiar (spec O1)."""
    import ast
    padrao = set(sys.stdlib_module_names) | {"observador"}
    for arq in (ROOT / "server/docker/images/observador/observador").glob("*.py"):
        for no in ast.walk(ast.parse(arq.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Import):
                nomes = [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom) and no.level == 0:
                nomes = [no.module or ""]
            else:
                continue
            for nome in nomes:
                assert nome.split(".")[0] in padrao, f"{arq.name}: {nome}"


def test_grafana_manda_os_alertas_ao_observador():
    cp = yaml.safe_load(render("templates/grafana/alerting/contact-points.yml.j2"))
    n8n = next(c for c in cp["contactPoints"] if c["name"] == "n8n")
    obs = next(r for r in n8n["receivers"] if r["uid"] == "observador-webhook")
    assert obs["settings"]["url"] == "http://observador:8080/alerta"
    assert obs["settings"]["authorization_credentials"] == "${OBSERVADOR_TOKEN}"
    assert obs["disableResolveMessage"] is True
    assert any(r["uid"] == "n8n-webhook" for r in n8n["receivers"])  # o n8n continua recebendo
    graf = _env(_svc(ROOT / "server/docker/stacks/apps/docker-compose.yml")["grafana"])
    assert graf["OBSERVADOR_TOKEN"] == "${OBSERVADOR_TOKEN}"
    mon = _configs(ANS / "playbooks/setup-monitoring-stack-volumes.yml", "monitoring.env")
    assert mon["OBSERVADOR_TOKEN"] == "{{ observador_token }}"


def test_alerta_observador_falhou():
    regras = yaml.safe_load(render("templates/grafana/alerting/rules.yml.j2", llm_gasto_diario_alerta=5))
    r = next(x for x in regras["groups"][0]["rules"] if x["uid"] == "observador-falhou")
    expr = r["data"][0]["model"]["expr"]
    # Os mesmos campos que saida.registrar grava (test_processar_registra_erro_sem_derrubar).
    assert '|= "\\"evento\\": \\"observador\\""' in expr and '|= "\\"resultado\\": \\"erro\\""' in expr
    assert "observador-falhou" in _cfg().ignorar  # o observador não analisa a própria falha


def test_vault_e_group_vars():
    main = yaml.safe_load((ANS / "inventories/home/group_vars/all/main.yml").read_text(encoding="utf-8"))
    vault = yaml.safe_load((ANS / "inventories/home/group_vars/all/vault.yml.example").read_text(encoding="utf-8"))
    assert main["observador_version"] and main["observador_modelo"] in {m["name"] for m in main["llm_models"]}
    assert main["litellm_key_budgets"]["observador"] > 0
    Config.do_ambiente({**AMBIENTE, "OBSERVADOR_BOLETIM_HORA": main["observador_boletim_hora"]})
    assert "observador" in vault["litellm_client_keys"] and "observador" in vault["agents_tokens_internos"]
    assert vault["observador_token"]
    assert "observador" not in main.get("litellm_key_models_ocultos", {})  # vê todos os apelidos


def test_comando_boletim(monkeypatch, capsys):
    from observador import __main__ as principal
    hub = _hub()
    llm = _llm([{"role": "assistant", "content": "Situação: ok, tudo em ordem."}])
    enviados = []
    original = Observador.__init__
    monkeypatch.setattr(principal.Observador, "__init__", lambda self, cfg: original(self, cfg, enviar=enviados.append))
    for k, v in {**AMBIENTE, "OBSERVADOR_HUB_URL": hub.url, "OBSERVADOR_LLM_URL": llm.url}.items():
        monkeypatch.setenv(k, v)
    try:
        assert principal.main(["boletim"]) == 0
        assert enviados[0]["titulo"] == "Boletim do servidor" and enviados[0]["gravidade"] == "ok"
        assert llm.pedidos[0][2]["metadata"]["trace_name"] == "observador-boletim"
        assert principal.main(["outra-coisa"]) == 2
    finally:
        hub.fechar()
        llm.fechar()


def test_exclui_prefixos_de_ferramentas():
    mcp = [{"name": "homeassistant_GetLiveContext"}, {"name": "n8n_search_workflows"}, {"name": "ops_containers_listar"}]
    nomes = [f["function"]["name"] for f in agente.ferramentas_para_llm(mcp, ("homeassistant_", "n8n_"))]
    assert nomes == ["ops_containers_listar"]


def test_erro_http_do_hub_traz_o_motivo():
    falso = _Falso(lambda c, corpo, h: (400, {"Content-Type": "application/json"},
                                        {"jsonrpc": "2.0", "id": corpo.get("id"), "error": {"message": "Unknown tool: ops_x"}}))
    try:
        with pytest.raises(ErroMCP, match="400 em tools/call: Unknown tool: ops_x"):
            ClienteMCP(falso.url, "x").chamar("ops_x", {})
    finally:
        falso.fechar()


def test_test_alert_do_grafana_nao_e_deduplicado():
    obs = Observador(_cfg(), enviar=lambda a: None)
    teste = {"status": "firing", "labels": {"alertname": "TestAlert", "instance": "Grafana"}}
    assert obs.receber_alerta({"alerts": [teste]})["aceitos"] == ["TestAlert"]
    assert obs.receber_alerta({"alerts": [teste]})["aceitos"] == ["TestAlert"]


def test_content_length_invalido_e_saude():
    import socket
    obs = Observador(_cfg(), enviar=lambda a: None)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), fazer_handler(obs))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    porta = srv.server_address[1]
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=5) as s:
            s.sendall(b"POST /alerta HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer tok-grafana\r\n"
                      b"Content-Length: abc\r\n\r\n")
            assert s.recv(100).startswith(b"HTTP/1.0 400")
        morta = threading.Thread(target=lambda: None)
        morta.start()
        morta.join()
        obs.threads.append(morta)  # o trabalhador morreu: o healthcheck do Docker precisa ver
        with pytest.raises(urllib.error.HTTPError) as erro:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/saude", timeout=5)
        assert erro.value.code == 503
    finally:
        srv.shutdown()


def test_boletim_sai_com_erro_se_o_aviso_falhar(monkeypatch):
    from observador import __main__ as principal
    hub = _hub()
    llm = _llm([{"role": "assistant", "content": "Situação: ok."}])

    def falhar(aviso):
        raise OSError("n8n fora")
    original = Observador.__init__
    monkeypatch.setattr(principal.Observador, "__init__", lambda self, cfg: original(self, cfg, enviar=falhar))
    for k, v in {**AMBIENTE, "OBSERVADOR_HUB_URL": hub.url, "OBSERVADOR_LLM_URL": llm.url}.items():
        monkeypatch.setenv(k, v)
    try:
        assert principal.main(["boletim"]) == 1
    finally:
        hub.fechar()
        llm.fechar()


# --- Contra o agentgateway de verdade (a mesma forma da rota de leitura: stateless, prefixo, lista fechada) ---

def _alvo_mcp(sse: bool):
    """Alvo MCP falso, como o mcp-grafana/ops: responde em SSE ou em JSON e sempre devolve sessão própria."""
    ferramentas = [{"name": "query_prometheus", "description": "PromQL", "inputSchema": {
        "type": "object", "properties": {"expr": {"type": "string"}}}},
                   {"name": "escrever", "description": "fora da lista", "inputSchema": {"type": "object", "properties": {}}}]

    def responder(caminho, corpo, cab):
        if "id" not in corpo:
            return 202, {}, ""
        m = corpo["method"]
        if m == "initialize":
            res = {"protocolVersion": corpo["params"].get("protocolVersion", "2025-06-18"),
                   "capabilities": {"tools": {}}, "serverInfo": {"name": "alvo", "version": "1"}}
        elif m == "tools/list":
            res = {"tools": ferramentas}
        else:
            res = {"content": [{"type": "text", "text": f"{corpo['params']['name']} = 42"}]}
        msg = {"jsonrpc": "2.0", "id": corpo["id"], "result": res}
        if sse:
            return 200, {"Content-Type": "text/event-stream", "Mcp-Session-Id": "s"}, f"event: message\ndata: {json.dumps(msg)}\n\n"
        return 200, {"Content-Type": "application/json", "Mcp-Session-Id": "s"}, msg
    return _Falso(responder)


def _porta_livre() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.skipif(__import__("shutil").which("agentgateway") is None, reason="binário agentgateway ausente")
def test_cliente_mcp_contra_o_agentgateway(tmp_path):
    import hashlib
    import subprocess
    import time
    graf, ops = _alvo_mcp(sse=True), _alvo_mcp(sse=False)
    porta = _porta_livre()
    hash_ = hashlib.sha256(b"tok-obs").hexdigest()
    cfg = f"""config:
  statsAddr: 127.0.0.1:{_porta_livre()}
  readinessAddr: 127.0.0.1:{_porta_livre()}
  adminAddr: 127.0.0.1:{_porta_livre()}
  enableIpv6: false
binds:
- port: {porta}
  listeners:
  - name: leitura
    routes:
    - name: leitura
      policies:
        apiKey:
          mode: strict
          location: {{header: {{name: Authorization, prefix: "Bearer "}}}}
          keys:
          - keyHash: "sha256:{hash_}"
            metadata: {{cliente: observador}}
        mcpAuthorization:
          rules:
          - allow: 'mcp.tool.target == "grafana"'
          - allow: 'mcp.tool.target == "ops" && mcp.tool.name in ["query_prometheus"]'
      backends:
      - mcp:
          statefulMode: stateless
          prefixMode: always
          failureMode: failOpen
          targets:
          - name: grafana
            mcp: {{host: "{graf.url}/mcp"}}
          - name: ops
            mcp: {{host: "{ops.url}/mcp"}}
"""
    (tmp_path / "config.yaml").write_text(cfg, encoding="utf-8")
    hub = subprocess.Popen(["agentgateway", "-f", str(tmp_path / "config.yaml")],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{porta}/mcp"
    try:
        for _ in range(100):
            try:
                c = ClienteMCP(url, "tok-obs", timeout=5)
                c.iniciar()
                break
            except ErroMCP:
                time.sleep(0.1)
        else:
            pytest.fail("agentgateway não subiu")
        nomes = {f["name"] for f in c.ferramentas()}
        assert {"grafana_query_prometheus", "grafana_escrever", "ops_query_prometheus"} <= nomes
        assert "ops_escrever" not in nomes  # fora da lista: some do tools/list
        assert c.chamar("grafana_query_prometheus", {"expr": "up"}) == "query_prometheus = 42"  # alvo em SSE
        assert c.chamar("ops_query_prometheus", {}) == "query_prometheus = 42"  # alvo em JSON
        with pytest.raises(ErroMCP):
            c.chamar("ops_escrever", {})
        with pytest.raises(ErroMCP, match="401"):
            ClienteMCP(url, "errado", timeout=5).iniciar()
    finally:
        hub.terminate()
        hub.wait(timeout=10)
        graf.fechar()
        ops.fechar()
