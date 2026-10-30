#!/usr/bin/env python3
# scripts/gerar_vault.py
# Gera o vault.yml a partir do vault.yml.example (página 01): todos os segredos aleatórios (senhas de banco,
# tokens internos, chaves do LiteLLM e do hub, segredos e digests do OIDC, chave RSA do Authelia, chave SSH do
# runner do ops, segredos do Langfuse...) e já criptografa com o ansible-vault. O que vem de fora (Cloudflare,
# Telegram, provedores de LLM, Tailscale, B2, tokens criados nas telas depois do deploy) fica com o texto do
# modelo e aparece na lista do fim: preencha com `ansible-vault edit`.
# Uso (na pasta server/): python3 scripts/gerar_vault.py
# Só a biblioteca padrão e o pacote cryptography (que já vem com o Ansible).
from __future__ import annotations

import argparse
import base64
import datetime
import getpass
import hashlib
import os
import re
import secrets
import string
import subprocess
import sys
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

SERVER = Path(__file__).resolve().parent.parent
REPO = SERVER.parent
VAULT_DIR = SERVER / "ansible/inventories/home/group_vars/all"
MODELO = VAULT_DIR / "vault.yml.example"
ALFANUM = string.ascii_letters + string.digits


def hexa(n: int) -> str:
    return secrets.token_hex(n)  # n bytes (openssl rand -hex n)


def b64(n: int) -> str:
    return base64.b64encode(secrets.token_bytes(n)).decode()  # openssl rand -base64 n


def senha(n: int = 32) -> str:
    return "".join(secrets.choice(ALFANUM) for _ in range(n))  # só letras e números: serve a qualquer banco


def digest_pbkdf2(segredo: str) -> str:
    """O mesmo formato de `authelia crypto hash generate pbkdf2 --variant sha512` (base64 adaptado, sem '=')."""
    def ab64(b: bytes) -> str:
        return base64.b64encode(b).decode().rstrip("=").replace("+", ".")
    sal = secrets.token_bytes(16)
    return f"$pbkdf2-sha512$310000${ab64(sal)}${ab64(hashlib.pbkdf2_hmac('sha512', segredo.encode(), sal, 310000))}"


def chave_rsa() -> str:
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption()).decode()


def chave_ssh() -> tuple[str, str]:
    k = ed25519.Ed25519PrivateKey.generate()
    priv = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                           serialization.NoEncryption()).decode()
    pub = k.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()
    return priv, pub + " ops-runner"


# Caminho da chave no YAML ("*" = qualquer filho) → gerador. Senhas que você digita em alguma tela vão para o
# resumo do fim (PARA_ANOTAR); os outros segredos só o vault precisa saber.
GERADORES = {
    "vm_ansible_user_password_plain": lambda: senha(24),
    "authelia_jwt_secret": lambda: hexa(64),
    "authelia_session_secret": lambda: hexa(64),
    "authelia_storage_postgres_password": senha,
    "authelia_storage_encryption_key": lambda: hexa(32),
    "authelia_oidc_hmac_secret": lambda: hexa(32),
    "authelia_oidc_jwks_key": chave_rsa,
    "oidc_clients.*.secret": lambda: hexa(32),
    "nextcloud_db_password": senha,
    "nextcloud_admin_initial_password": lambda: senha(24),
    "immich_db_password": senha,
    "grafana_db_password": senha,
    "grafana_admin_initial_password": lambda: senha(24),
    "litellm_master_key": lambda: hexa(32),
    "litellm_db_password": senha,
    "litellm_client_keys.*": lambda: "sk-" + hexa(24),
    "openwebui_secret_key": lambda: hexa(32),
    "notificacoes_webhook_token": lambda: hexa(32),
    "syncthing_gui_password": lambda: senha(24),
    "syncthing_api_key": lambda: hexa(24),
    "mcp_auth_hmac_secret": lambda: b64(32),
    "arr_api_keys.*": lambda: hexa(16),
    "portainer_agent_secret": lambda: hexa(32),
    "agents_api_keys.*": lambda: "ag-" + hexa(24),
    "agents_autonomos_keys.*": lambda: "ag-" + hexa(24),
    "agents_tokens_internos.*": lambda: hexa(32),
    "observador_token": lambda: hexa(32),
    "aprovador_token": lambda: hexa(32),
    "aprovador_chave_proxy": lambda: hexa(32),
    "posto_chave_proxy": lambda: hexa(32),
    "langfuse_secrets.salt": lambda: b64(32),
    "langfuse_secrets.encryption_key": lambda: hexa(32),
    "langfuse_secrets.nextauth_secret": lambda: b64(32),
    "langfuse_secrets.db_password": senha,
    "langfuse_secrets.clickhouse_password": senha,
    "langfuse_secrets.redis_password": senha,
    "langfuse_secrets.minio_password": senha,
    "langfuse_secrets.public_key": lambda: "pk-lf-" + hexa(16),
    "langfuse_secrets.secret_key": lambda: "sk-lf-" + hexa(16),
    "restic_senha": lambda: b64(32),
}
PARA_ANOTAR = {
    "vm_ansible_user_password_plain": "usuário Ansible das VMs (sudo)",
    "nextcloud_admin_initial_password": "admin inicial do Nextcloud",
    "grafana_admin_initial_password": "admin inicial do Grafana",
    "syncthing_gui_password": "painel do Syncthing",
    "restic_senha": "restic (SEM ELA NENHUM BACKUP SE RESTAURA: guarde fora do servidor)",
}
# Texto de modelo que ainda precisa de você (maiúsculas, domínio e e-mail de exemplo).
PENDENTE = re.compile(r"[A-Z]{3,}_[A-Z_]{3,}|[A-Z]{3,}-[A-Z]{2,}-[A-Z]{3,}|seudominio\.com|example\.com")
LINHA = re.compile(r'^(?P<ind> *)(?P<chave>[A-Za-z_]\w*):(?P<resto>.*)$')


def _casa(caminho: list[str]) -> str | None:
    for padrao in GERADORES:
        partes = padrao.split(".")
        if len(partes) == len(caminho) and all(p in ("*", c) for p, c in zip(partes, caminho)):
            return padrao
    return None


def _valor(texto: str) -> str:
    """Escalar YAML entre aspas duplas (os geradores não produzem aspas nem barras invertidas)."""
    assert '"' not in texto and "\\" not in texto
    return f'"{texto}"'


def gerar(modelo: str, senha_admin: str, senha_vault: str, agora: str) -> tuple[str, dict[str, str], str, list[str]]:
    """Devolve (vault.yml em texto, senhas para anotar, chave pública do runner, chaves que faltam preencher)."""
    linhas = modelo.splitlines()
    saida: list[str] = [
        "# ansible/inventories/home/group_vars/all/vault.yml",
        f"# Gerado por scripts/gerar_vault.py em {agora} a partir do vault.yml.example (página 01).",
        "# Edite SEMPRE com: ansible-vault edit inventories/home/group_vars/all/vault.yml",
    ]
    pilha: list[tuple[int, str]] = []
    anotar: dict[str, str] = {}
    faltam: list[str] = []
    gerados: dict[str, str] = {}
    pub = ""
    i = 0
    # Pula o cabeçalho do modelo ("MODELO versionado...") até a primeira linha em branco.
    while i < len(linhas) and linhas[i].startswith("#"):
        i += 1
    while i < len(linhas):
        linha = linhas[i]
        i += 1
        m = LINHA.match(linha)
        if not m or linha.lstrip().startswith("#"):
            saida.append(linha)
            continue
        ind, chave, resto = len(m["ind"]), m["chave"], m["resto"].strip()
        while pilha and pilha[-1][0] >= ind:
            pilha.pop()
        caminho = [c for _, c in pilha] + [chave]
        pilha.append((ind, chave))
        nome = ".".join(caminho)
        bloco = resto.startswith("|")
        conteudo: list[str] = []
        if bloco:  # o bloco literal vai até a próxima linha menos indentada
            while i < len(linhas) and (not linhas[i].strip() or len(linhas[i]) - len(linhas[i].lstrip()) > ind):
                conteudo.append(linhas[i])
                i += 1
        if not resto or resto.startswith("#"):
            saida.append(linha)  # chave de um mapa (os filhos vêm nas próximas linhas)
            continue
        novo: str | None = None
        if nome == "authelia_admin_password_hash_initial":
            novo = digest_pbkdf2(senha_admin)
        elif nome == "ops_vault_password":
            novo = senha_vault
        elif nome == "ops_ssh_private_key":
            novo, pub = chave_ssh()
        elif caminho[0] == "oidc_clients" and chave == "secret_digest":
            novo = digest_pbkdf2(gerados[".".join(caminho[:-1] + ["secret"])])
        elif (padrao := _casa(caminho)) is not None:
            novo = GERADORES[padrao]()
        if novo is None:
            saida.append(linha)
            saida.extend(conteudo)
            if PENDENTE.search(resto) or any(PENDENTE.search(c) for c in conteudo):
                faltam.append(nome)
            continue
        gerados[nome] = novo
        if nome in PARA_ANOTAR:
            anotar[PARA_ANOTAR[nome]] = novo
        comentario = resto[resto.index(" #"):] if " #" in resto and not bloco else ""
        if bloco or "\n" in novo:
            saida.append(f"{' ' * ind}{chave}: |")
            saida.extend(f"{' ' * (ind + 2)}{l}" for l in novo.strip("\n").splitlines())
        else:
            saida.append(f"{' ' * ind}{chave}: {_valor(novo)}{comentario}")
    return "\n".join(saida) + "\n", anotar, pub, faltam


def _dentro_do_repo(caminho: Path) -> bool:
    try:
        caminho.resolve().relative_to(REPO)
        return True
    except ValueError:
        return False


def _senha_vault(arquivo: str | None) -> tuple[str, bool]:
    if arquivo:
        return Path(arquivo).read_text(encoding="utf-8").strip(), False
    print("Senha do ansible-vault (Enter em branco: gerar uma).")
    s1 = getpass.getpass("Senha do vault: ")
    if not s1:
        return b64(24), True
    if s1 != getpass.getpass("Repita: "):
        sys.exit("As senhas não conferem.")
    if len(s1) < 16:
        sys.exit("Use pelo menos 16 caracteres.")
    return s1, False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gera o vault.yml com todos os segredos aleatórios, já criptografado.")
    ap.add_argument("--saida", default=str(VAULT_DIR / "vault.yml"))
    ap.add_argument("--senha-vault-arquivo", help="arquivo com a senha do ansible-vault (senão, pergunta)")
    ap.add_argument("--admin-authelia-senha-arquivo", help="arquivo com a senha do admin do Authelia (senão, gera)")
    ap.add_argument("--sem-criptografar", action="store_true",
                    help="grava em texto puro (só fora do repositório ou em *.decrypted*; para conferir ou testar)")
    a = ap.parse_args(argv)
    destino = Path(a.saida)
    if destino.exists():
        sys.exit(f"{destino} já existe: não sobrescrevo. Para mudar segredos use ansible-vault edit.")
    if a.sem_criptografar and _dentro_do_repo(destino) and ".decrypted" not in destino.name:
        sys.exit("Em texto puro, só fora do repositório ou num nome *.decrypted* (ignorado pelo git).")
    senha_vault, vault_gerada = _senha_vault(a.senha_vault_arquivo)
    admin = (Path(a.admin_authelia_senha_arquivo).read_text(encoding="utf-8").strip()
             if a.admin_authelia_senha_arquivo else senha(24))
    agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    texto, anotar, pub, faltam = gerar(MODELO.read_text(encoding="utf-8"), admin, senha_vault, agora)

    if a.sem_criptografar:
        destino.write_text(texto, encoding="utf-8")
        os.chmod(destino, 0o600)
    else:
        # Texto puro só em arquivos temporários 0600 na mesma pasta, apagados mesmo se o ansible-vault falhar.
        with tempfile.TemporaryDirectory(dir=destino.parent, prefix=".gerar-vault-") as tmp:
            claro, chave = Path(tmp) / "vault.decrypted.yml", Path(tmp) / "senha"
            for arq, conteudo in ((claro, texto), (chave, senha_vault + "\n")):
                arq.touch(mode=0o600)
                arq.write_text(conteudo, encoding="utf-8")
            r = subprocess.run(["ansible-vault", "encrypt", "--vault-password-file", str(chave),
                                "--output", str(destino), str(claro)], capture_output=True, text=True)
            if r.returncode != 0:
                sys.exit(f"ansible-vault falhou: {r.stderr.strip()}")

    print(f"\n{destino} gerado" + (" (texto puro)." if a.sem_criptografar else " e criptografado."))
    print("\n=== Anote no seu gerenciador de senhas (não aparecem de novo) ===")
    if vault_gerada:
        print(f"  ansible-vault (e ops_vault_password): {senha_vault}")
    print(f"  admin do Authelia ({'arquivo' if a.admin_authelia_senha_arquivo else 'gerada'}): "
          f"{'(a do arquivo)' if a.admin_authelia_senha_arquivo else admin}")
    for nome, valor in anotar.items():
        print(f"  {nome}: {valor}")
    print("\n=== Chave pública do runner do ops (authorized_keys do usuário Ansible das VMs) ===")
    print(f"  {pub}")
    print("\n=== Ainda com texto de modelo: preencha com ansible-vault edit ===")
    for nome in faltam:
        print(f"  {nome}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
