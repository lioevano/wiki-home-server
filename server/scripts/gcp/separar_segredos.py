#!/usr/bin/env python3
"""Separa o JSON do Secret Manager em arquivos por container, no tmpfs /run/sysadmin (página 02).

Uso (na VM, antes de subir o Docker):
    gcloud secrets versions access latest --secret=sysadmin | sudo python3 separar_segredos.py --destino /run/sysadmin

Cada container só recebe o que precisa: o sysadmin (agente com modelo) nunca vê a senha do vault, a chave SSH nem
a chave do Tailscale da casa; essas ficam só no executor (atrás dos botões do Telegram) e no host. Falha fechada:
campo ausente ou em branco encerra com código 1, lista só os NOMES dos campos no stderr e não escreve nada. O
diretório novo é montado num irmão temporário e trocado de uma vez, então nunca fica uma mistura de versões.
Nenhum valor de segredo é impresso. Só biblioteca padrão.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

CAMPOS = (
    "anthropic_api_key", "gemini_api_key", "telegram_bot_sysadmin", "telegram_bot_aprovacoes", "telegram_chat_id",
    "tailscale_chave_sysadmin", "tailscale_chave_homeserver", "github_token_sysadmin", "github_token_carteiro",
    "vault_senha", "ssh_chave_privada", "ssh_chave_publica", "honcho_db_senha", "executor_token", "webhook_segredo",
    "dashboard_usuario", "dashboard_senha", "dashboard_segredo",
)

# Campos de uma linha só (vão para arquivos .env); a chave privada SSH é a única de várias linhas.
_MULTILINHA = {"ssh_chave_privada"}


class SegredosInvalidos(ValueError):
    """Campos ausentes ou inválidos; a mensagem traz só os nomes."""


def _valores(dados: dict) -> dict[str, str]:
    invalidos = []
    valores = {}
    for campo in CAMPOS:
        v = dados.get(campo)
        if isinstance(v, int) and not isinstance(v, bool):  # chat id numérico no JSON
            v = str(v)
        if not isinstance(v, str) or not v.strip():
            invalidos.append(campo)
            continue
        v = v.strip()
        if campo not in _MULTILINHA and any(c in v for c in "\r\n\0"):
            invalidos.append(campo)  # quebra de linha injetaria outra variável no .env
            continue
        valores[campo] = v
    if invalidos:
        raise SegredosInvalidos(", ".join(invalidos))
    return valores


def _compose(v: str) -> str:
    """O compose interpola `$` nos env_file: dobra para chegar literal ao container."""
    return v.replace("$", "$$")


def _env(pares: dict[str, str], compose: bool = False) -> str:
    return "".join(f"{k}={_compose(v) if compose else v}\n" for k, v in pares.items())


def _escrever(caminho: Path, texto: str, modo: int, dono: int | None) -> None:
    fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)
    if dono is not None:
        os.chown(caminho, dono, dono)
    os.chmod(caminho, modo)


def separar(dados: dict, destino: Path, uid_executor: int, uid_sysadmin: int) -> None:
    """Escreve os arquivos em `destino` (trocado atomicamente). A posse só é aplicada quando roda como root."""
    v = _valores(dados)
    destino = Path(destino)
    raiz = os.geteuid() == 0
    dono_ex = uid_executor if raiz else None
    dono_sa = uid_sysadmin if raiz else None
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{destino.name}.novo-", dir=destino.parent))
    antigo = None
    try:
        # Tudo 0700: o dockerd (root) resolve a origem dos bind mounts, os containers não precisam atravessar.
        os.chmod(tmp, 0o700)
        for sub in ("executor", "host"):
            (tmp / sub).mkdir()
            os.chmod(tmp / sub, 0o700)

        # sysadmin: o agente com modelo. Sem vault, sem SSH, sem Tailscale da casa.
        _escrever(tmp / "sysadmin.env", _env({
            "ANTHROPIC_API_KEY": v["anthropic_api_key"], "GEMINI_API_KEY": v["gemini_api_key"],
            "TELEGRAM_BOT_TOKEN": v["telegram_bot_sysadmin"], "TELEGRAM_ALLOWED_USERS": v["telegram_chat_id"],
            # SYSADMIN_GITHUB_TOKEN, não GH_TOKEN: o Hermes tira GH_TOKEN/GITHUB_TOKEN dos comandos do agente; o gh da
            # imagem (docker/images/sysadmin/gh) o traduz.
            "TELEGRAM_HOME_CHANNEL": v["telegram_chat_id"], "SYSADMIN_GITHUB_TOKEN": v["github_token_sysadmin"],
            "EXECUTOR_TOKEN": v["executor_token"], "WEBHOOK_SEGREDO": v["webhook_segredo"],
            "HERMES_DASHBOARD_BASIC_AUTH_USERNAME": v["dashboard_usuario"],
            "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD": v["dashboard_senha"],
            "HERMES_DASHBOARD_BASIC_AUTH_SECRET": v["dashboard_segredo"],
        }), 0o600, dono_sa)

        # executor e Honcho: lidos pelo compose (root), por isso `$` dobrado.
        _escrever(tmp / "executor.env", _env({
            "EXECUTOR_TOKEN": v["executor_token"], "TELEGRAM_BOT_TOKEN": v["telegram_bot_aprovacoes"],
            "TELEGRAM_CHAT_ID": v["telegram_chat_id"], "TAILSCALE_CHAVE_HOST": v["tailscale_chave_homeserver"],
            "GITHUB_TOKEN_EQUIPE": v["github_token_carteiro"], "WEBHOOK_SEGREDO": v["webhook_segredo"],
        }, compose=True), 0o600, None)
        _escrever(tmp / "honcho.env", _env({
            "LLM_GEMINI_API_KEY": v["gemini_api_key"],
            "DB_CONNECTION_URI": f"postgresql+psycopg://honcho:{quote(v['honcho_db_senha'], safe='')}@honcho_db:5432/honcho",
        }, compose=True), 0o600, None)
        _escrever(tmp / "honcho-db.env", _env({
            "POSTGRES_USER": "honcho", "POSTGRES_DB": "honcho", "POSTGRES_PASSWORD": v["honcho_db_senha"],
        }, compose=True), 0o600, None)

        # arquivos do executor (montados em /segredos:ro): somente leitura, do UID dele.
        _escrever(tmp / "executor/vault_senha", v["vault_senha"] + "\n", 0o400, dono_ex)
        _escrever(tmp / "executor/id_ed25519", v["ssh_chave_privada"] + "\n", 0o400, dono_ex)
        _escrever(tmp / "executor/id_ed25519.pub", v["ssh_chave_publica"] + "\n", 0o400, dono_ex)
        # do host (lido pelo root da VM para subir o Tailscale do próprio sysadmin).
        _escrever(tmp / "host/tailscale_chave", v["tailscale_chave_sysadmin"] + "\n", 0o400, None)
        # do host: o alerta de falha das units (sysadmin-alerta.sh) fala pelo bot de aprovações.
        _escrever(tmp / "host/alerta.env", _env({
            "TELEGRAM_BOT_TOKEN": v["telegram_bot_aprovacoes"], "TELEGRAM_CHAT_ID": v["telegram_chat_id"],
        }), 0o400, None)
        if dono_ex is not None:
            os.chown(tmp / "executor", dono_ex, dono_ex)

        if destino.exists():  # troca: o antigo sai do caminho por rename e só então é apagado
            antigo = Path(tempfile.mkdtemp(prefix=f".{destino.name}.antigo-", dir=destino.parent))
            os.replace(destino, antigo / "d")
        os.replace(tmp, destino)
        tmp = None
    except BaseException:
        if antigo is not None and not destino.exists() and (antigo / "d").exists():
            os.replace(antigo / "d", destino)  # desfaz: mantém o que já estava
        raise
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
        if antigo is not None:
            shutil.rmtree(antigo, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Separa os segredos do sysadmin por container (JSON no stdin).")
    ap.add_argument("--destino", default="/run/sysadmin", type=Path)
    ap.add_argument("--uid-executor", type=int, default=1001)
    ap.add_argument("--uid-sysadmin", type=int, default=1000)
    args = ap.parse_args(argv)
    try:
        dados = json.loads(sys.stdin.read())
        if not isinstance(dados, dict):
            raise ValueError("o JSON precisa ser um objeto")
        separar(dados, args.destino, args.uid_executor, args.uid_sysadmin)
    except SegredosInvalidos as erro:
        print(f"ERRO: campos ausentes ou em branco no Secret Manager: {erro}", file=sys.stderr)
        return 1
    except (ValueError, OSError) as erro:  # JSON inválido ou falha de disco; sem eco do conteúdo
        print(f"ERRO: {type(erro).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
