#!/usr/bin/env bash
set -euo pipefail

python3 --version >/dev/null 2>&1 || { echo 'Python 3 é obrigatório.'; exit 1; }
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip ansible proxmoxer docker
ansible-galaxy collection install community.general community.docker community.proxmox --force
printf '\nAmbiente de controle preparado. Ative com: source .venv/bin/activate\n'
