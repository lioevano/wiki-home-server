#!/bin/bash
# scripts/notify.sh — envia uma notificação ao webhook do n8n (integração notificacoes).
# Uso: notify.sh <gravidade> <titulo> <mensagem> [app]
#   gravidade: critical | warning | ok | info
# Configuração (variáveis de ambiente ou /etc/default/homeserver-notify, modo 600):
#   NOTIFICACOES_WEBHOOK_URL   ex.: https://n8n.seudominio.com/webhook/notificar
#   NOTIFICACOES_WEBHOOK_TOKEN vault: notificacoes_webhook_token
# Nunca falha o chamador: erro de envio só vai para stderr e o script sai com 0.

if [ -r /etc/default/homeserver-notify ]; then
  # shellcheck disable=SC1091
  . /etc/default/homeserver-notify
fi

json_escape() {
  local s=$1
  s=${s//\\/\\\\}
  s=${s//\"/\\\"}
  s=${s//$'\n'/\\n}
  s=${s//$'\r'/}
  s=${s//$'\t'/\\t}
  printf '%s' "$s"
}

gravidade=${1:-info}
titulo=${2:-Notificação}
mensagem=${3:-}
app=${4:-}

if [ -z "${NOTIFICACOES_WEBHOOK_URL:-}" ] || [ -z "${NOTIFICACOES_WEBHOOK_TOKEN:-}" ]; then
  echo "notify.sh: NOTIFICACOES_WEBHOOK_URL/NOTIFICACOES_WEBHOOK_TOKEN não definidos; notificação não enviada" >&2
  exit 0
fi

body="{\"gravidade\":\"$(json_escape "$gravidade")\",\"titulo\":\"$(json_escape "$titulo")\",\"mensagem\":\"$(json_escape "$mensagem")\",\"app\":\"$(json_escape "$app")\"}"

if ! curl -fsS --max-time 10 -X POST "$NOTIFICACOES_WEBHOOK_URL" \
  -H "Authorization: Bearer ${NOTIFICACOES_WEBHOOK_TOKEN}" \
  -H "Content-Type: application/json" \
  --data-binary "$body" -o /dev/null; then
  echo "notify.sh: falha ao enviar notificação para ${NOTIFICACOES_WEBHOOK_URL}" >&2
fi
exit 0
