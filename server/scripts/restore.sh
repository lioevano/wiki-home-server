#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cd ansible
ansible-playbook -i inventories/home/hosts.ini playbooks/full-deploy.yml --ask-vault-pass
