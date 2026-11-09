#!/bin/bash
# Prepara o host Proxmox para o sysadmin (página 19). O Léo cola no console do host o comando que o bot de
# aprovações envia:  curl -fsSL <raw>/server/scripts/gcp/preparar-host.sh | bash -s -- '<tskey>' '<chave pública>' '<usuário>' '<rotas>'
# Pode ser repetido: não duplica o sudoers nem a chave autorizada. Nunca imprime a chave do Tailscale.
set -euo pipefail

main() {
    uso() {
        echo "uso: preparar-host.sh <chave_tailscale> <chave_publica_ssh> <usuario> <rotas>" >&2
        exit 2
    }

    [ "$#" -eq 4 ] || uso
    for argumento in "$@"; do
        [ -n "${argumento//[[:space:]]/}" ] || uso
    done
    CHAVE_TS=$1
    CHAVE_PUB=$2
    USUARIO=$3
    ROTAS=$4

    # O usuário vira nome de arquivo do sudoers e de pasta; a chave pública, uma linha só; as rotas, CIDRs.
    [[ "$USUARIO" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || { echo "preparar-host: usuário inválido" >&2; exit 2; }
    [[ "$CHAVE_PUB" != *$'\n'* ]] || { echo "preparar-host: a chave pública deve ter uma linha" >&2; exit 2; }
    [[ "$ROTAS" =~ ^[0-9a-fA-F:./,]+$ ]] || { echo "preparar-host: rotas inválidas" >&2; exit 2; }
    [ "$(id -u)" -eq 0 ] || { echo "preparar-host: rode como root" >&2; exit 1; }

    echo "1/6 Tailscale"
    command -v tailscale >/dev/null 2>&1 || curl -fsSL https://tailscale.com/install.sh | sh

    echo "2/6 encaminhamento de pacotes"
    echo 'net.ipv4.ip_forward = 1' > /etc/sysctl.d/99-tailscale.conf
    sysctl -w net.ipv4.ip_forward=1 >/dev/null

    echo "3/6 entrada no tailnet"
    tailscale up --auth-key="$CHAVE_TS" --hostname=pve --advertise-tags=tag:homeserver \
        --advertise-routes="$ROTAS" --accept-dns=false

    echo "4/6 usuário $USUARIO"
    id "$USUARIO" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$USUARIO"
    GRUPO=$(id -gn "$USUARIO")

    echo "5/6 sudo sem senha"
    SUDOERS="/etc/sudoers.d/010_${USUARIO}_nopasswd"
    command -v visudo >/dev/null || { apt-get update && apt-get install -y sudo; } </dev/null   # o Proxmox não traz sudo
    TMP=$(mktemp)
    trap 'rm -f "$TMP"' EXIT
    echo "$USUARIO ALL=(ALL) NOPASSWD: ALL" > "$TMP"
    visudo -cf "$TMP" >/dev/null
    install -m 0440 -o root -g root "$TMP" "$SUDOERS"

    echo "6/6 chave SSH autorizada"
    CASA=$(getent passwd "$USUARIO" | cut -d: -f6)
    install -d -m 0700 -o "$USUARIO" -g "$GRUPO" "$CASA/.ssh"
    AUTORIZADAS="$CASA/.ssh/authorized_keys"
    touch "$AUTORIZADAS"
    [ ! -s "$AUTORIZADAS" ] || [ -z "$(tail -c1 "$AUTORIZADAS")" ] || echo >> "$AUTORIZADAS"   # fecha a última linha
    grep -qxF -- "$CHAVE_PUB" "$AUTORIZADAS" || echo "$CHAVE_PUB" >> "$AUTORIZADAS"
    chown "$USUARIO:$GRUPO" "$AUTORIZADAS"
    chmod 0600 "$AUTORIZADAS"

    echo "Pronto: host preparado."
}

main "$@"
