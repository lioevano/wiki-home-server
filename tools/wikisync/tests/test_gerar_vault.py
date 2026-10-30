"""scripts/gerar_vault.py (página 01): gera todos os segredos aleatórios do vault.yml nos formatos certos e grava
criptografado. Os digests são conferidos com o binário do Authelia quando ele está no PATH."""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys

import pytest
import yaml

from test_observabilidade import ROOT

MODELO = ROOT / "server/ansible/inventories/home/group_vars/all/vault.yml.example"
VENV_BIN = os.path.dirname(sys.executable)

# Tudo o que vem de fora (ou é criado nas telas depois do deploy). Uma chave nova no modelo com texto de exemplo
# que não esteja aqui precisa de um gerador no script, ou de entrar nesta lista de propósito.
EXTERNOS = {
    "proxmox_api_password", "cloudflare_api_token", "cloudflare_tunnel_token", "letsencrypt_email", "base_domain",
    "llm_api_keys.openai", "llm_api_keys.anthropic", "llm_api_keys.google_gemini", "llm_api_keys.typesafe",
    "telegram_bot_token", "telegram_chat_id", "protonvpn_wireguard_private_key",
    "homepage_widget_keys.jellyfin", "homepage_widget_keys.bazarr", "homepage_widget_keys.seerr",
    "homepage_widget_keys.nextcloud", "homepage_widget_keys.immich", "homepage_widget_keys.homeassistant",
    "homepage_widget_keys.portainer", "homepage_widget_keys.qbittorrent_password",
    "hermes_telegram_bot_token", "grafana_sa_tokens.leitura", "grafana_sa_tokens.controle",
    "homeassistant_mcp_token", "n8n_mcp_token", "portainer_api_key", "tailscale_auth_key",
    "restic_repositorios.repositorio", "restic_repositorios.ambiente.AWS_ACCESS_KEY_ID",
    "restic_repositorios.ambiente.AWS_SECRET_ACCESS_KEY",
}


@pytest.fixture(scope="module")
def gv():
    spec = importlib.util.spec_from_file_location("gerar_vault", ROOT / "server/scripts/gerar_vault.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gerado(gv):
    texto, anotar, pub, faltam = gv.gerar(MODELO.read_text(encoding="utf-8"), "senha-do-admin", "senha-do-vault",
                                          "2026-10-30 12:00")
    return yaml.safe_load(texto), texto, anotar, pub, faltam


def _folhas(d, prefixo=""):
    if isinstance(d, dict):
        for k, v in d.items():
            yield from _folhas(v, f"{prefixo}{k}.")
    elif isinstance(d, list):
        for item in d:
            yield from _folhas(item, prefixo)
    else:
        yield prefixo[:-1], d


def test_mesma_estrutura_do_modelo(gerado):
    vault, texto, *_ = gerado
    modelo = yaml.safe_load(MODELO.read_text(encoding="utf-8"))
    assert [k for k, _ in _folhas(vault)] == [k for k, _ in _folhas(modelo)]
    assert texto.startswith("# ansible/inventories/home/group_vars/all/vault.yml\n# Gerado por scripts/gerar_vault.py")
    assert "MODELO versionado" not in texto


def test_so_o_que_vem_de_fora_fica_por_preencher(gerado):
    vault, _, _, _, faltam = gerado
    assert set(faltam) == EXTERNOS
    gerados = [(k, v) for k, v in _folhas(vault) if k not in EXTERNOS and isinstance(v, str) and v]
    assert not [k for k, v in gerados if re.search(r"[A-Z]{3,}_[A-Z_]{3,}", v) and "PRIVATE KEY" not in v]
    valores = [v for k, v in gerados if k not in ("proxmox_api_user", "authelia_admin_user_initial",
                                                  "system_timezone", "homepage_widget_keys.qbittorrent_user")]
    assert len(valores) == len(set(valores))  # nenhum segredo repetido


def test_formatos(gerado):
    v = gerado[0]
    assert all(re.fullmatch(r"sk-[0-9a-f]{48}", x) for x in v["litellm_client_keys"].values())
    assert all(re.fullmatch(r"ag-[0-9a-f]{48}", x) for x in [*v["agents_api_keys"].values(),
                                                              *v["agents_autonomos_keys"].values()])
    assert all(re.fullmatch(r"[0-9a-f]{32}", x) for x in v["arr_api_keys"].values())  # as *arr exigem 32 hex
    for chave in ("litellm_master_key", "aprovador_token", "aprovador_chave_proxy", "posto_chave_proxy",
                  "authelia_storage_encryption_key", "authelia_oidc_hmac_secret", "portainer_agent_secret"):
        assert re.fullmatch(r"[0-9a-f]{64}", v[chave]), chave
    assert re.fullmatch(r"[A-Za-z0-9]{32}", v["immich_db_password"])  # o Immich só aceita letras e números
    assert re.fullmatch(r"pk-lf-[0-9a-f]{32}", v["langfuse_secrets"]["public_key"])
    assert re.fullmatch(r"sk-lf-[0-9a-f]{32}", v["langfuse_secrets"]["secret_key"])
    assert v["ops_vault_password"] == "senha-do-vault"
    assert v["posto_github_token"] == "" and v["docker_puid"] == 1000


def test_chaves_rsa_e_ssh(gerado):
    from cryptography.hazmat.primitives import serialization
    v, _, _, pub, _ = gerado
    rsa = serialization.load_pem_private_key(v["authelia_oidc_jwks_key"].encode(), None)
    assert rsa.key_size == 2048 and v["authelia_oidc_jwks_key"].startswith("-----BEGIN PRIVATE KEY-----")
    ssh = serialization.load_ssh_private_key(v["ops_ssh_private_key"].encode(), None)
    publica = ssh.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
    assert pub == publica.decode() + " ops-runner" and pub.startswith("ssh-ed25519 ")


@pytest.mark.skipif(not shutil.which("authelia"), reason="binário authelia fora do PATH")
def test_digests_validam_no_authelia(gerado):
    v = gerado[0]
    pares = [("senha-do-admin", v["authelia_admin_password_hash_initial"])]
    pares += [(c["secret"], c["secret_digest"]) for c in v["oidc_clients"].values()]
    for segredo, digest in pares:
        assert digest.startswith("$pbkdf2-sha512$310000$")
        r = subprocess.run(["authelia", "crypto", "hash", "validate", "--password", segredo, "--", digest],
                           capture_output=True, text=True)
        assert "matches" in r.stdout and "not match" not in r.stdout, r.stdout + r.stderr
    errado = subprocess.run(["authelia", "crypto", "hash", "validate", "--password", "outra", "--",
                             v["oidc_clients"]["immich"]["secret_digest"]], capture_output=True, text=True)
    assert "does not match" in errado.stdout


def test_anotar_e_restic(gerado):
    _, _, anotar, _, _ = gerado
    assert any("restic" in k for k in anotar) and any("Nextcloud" in k for k in anotar)


def test_grava_criptografado_e_nao_sobrescreve(gv, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", VENV_BIN + os.pathsep + os.environ["PATH"])
    if not shutil.which("ansible-vault"):
        pytest.skip("ansible-vault fora do PATH")
    senha = tmp_path / "senha"
    senha.write_text("uma-senha-de-vault-longa\n", encoding="utf-8")
    destino = tmp_path / "vault.yml"
    assert gv.main(["--saida", str(destino), "--senha-vault-arquivo", str(senha)]) == 0
    assert destino.read_text(encoding="utf-8").startswith("$ANSIBLE_VAULT;")
    assert [p.name for p in tmp_path.iterdir()] == sorted(["senha", "vault.yml"]) or set(
        p.name for p in tmp_path.iterdir()) == {"senha", "vault.yml"}  # sem temporários esquecidos
    claro = subprocess.run(["ansible-vault", "view", "--vault-password-file", str(senha), str(destino)],
                           capture_output=True, text=True, check=True).stdout
    v = yaml.safe_load(claro)
    assert v["ops_vault_password"] == "uma-senha-de-vault-longa"
    saida = capsys.readouterr().out
    assert "ssh-ed25519 " in saida and "tailscale_auth_key" in saida
    with pytest.raises(SystemExit, match="já existe"):
        gv.main(["--saida", str(destino), "--senha-vault-arquivo", str(senha)])


def test_texto_puro_nunca_dentro_do_repositorio(gv, tmp_path):
    senha = tmp_path / "senha"
    senha.write_text("uma-senha-de-vault-longa\n", encoding="utf-8")
    dentro = ROOT / "server/ansible/inventories/home/group_vars/all/vault-teste.yml"
    with pytest.raises(SystemExit, match="Em texto puro"):
        gv.main(["--saida", str(dentro), "--senha-vault-arquivo", str(senha), "--sem-criptografar"])
    assert not dentro.exists()
    fora = tmp_path / "claro.yml"
    assert gv.main(["--saida", str(fora), "--senha-vault-arquivo", str(senha), "--sem-criptografar"]) == 0
    assert oct(fora.stat().st_mode & 0o777) == "0o600" and "ops_ssh_private_key: |" in fora.read_text(encoding="utf-8")
