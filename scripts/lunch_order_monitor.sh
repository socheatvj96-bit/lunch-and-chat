#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/etc/lunch_order-monitor.env"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

PROJECT_DIR="${PROJECT_DIR:-/opt/lunch_order}"
PROJECT_NAME="${PROJECT_NAME:-lunch_order}"
CHECK_URL="${CHECK_URL:-https://pm.obed.pro/}"
STATE_FILE="${STATE_FILE:-/var/tmp/lunch_order_monitor_state}"
SERVICES=(web db redis celery celery-beat telegram-bot)

ALERT_BOT_TOKEN="${ALERT_BOT_TOKEN:-}"
ALERT_CHAT_ID="${ALERT_CHAT_ID:-}"

send_alert() {
  local text="$1"
  if [[ -z "$ALERT_BOT_TOKEN" || -z "$ALERT_CHAT_ID" ]]; then
    return 0
  fi
  curl -sS -X POST "https://api.telegram.org/bot${ALERT_BOT_TOKEN}/sendMessage" \
    -d "chat_id=${ALERT_CHAT_ID}" \
    -d "text=${text}" >/dev/null || true
}

check_service_running() {
  local service="$1"
  local cid
  cid=$(cd "$PROJECT_DIR" && DOCKER_BUILDKIT=0 COMPOSE_PROJECT_NAME="$PROJECT_NAME" docker compose ps -q "$service" 2>/dev/null || true)
  if [[ -z "$cid" ]]; then
    return 1
  fi
  local running
  running=$(docker inspect -f '{{.State.Running}}' "$cid" 2>/dev/null || echo "false")
  [[ "$running" == "true" ]]
}

errors=()

for s in "${SERVICES[@]}"; do
  if ! check_service_running "$s"; then
    errors+=("service:${s}")
  fi
done

if ! curl -fsS --max-time 10 "$CHECK_URL" >/dev/null; then
  errors+=("url:${CHECK_URL}")
fi

if ((${#errors[@]} > 0)); then
  current_state="FAIL:${errors[*]}"
else
  current_state="OK"
fi

prev_state=""
if [[ -f "$STATE_FILE" ]]; then
  prev_state="$(cat "$STATE_FILE" || true)"
fi

if [[ "$current_state" != "$prev_state" ]]; then
  if [[ "$current_state" == OK ]]; then
    send_alert "✅ lunch_order восстановлен. URL: ${CHECK_URL}"
  else
    send_alert "🚨 lunch_order проблема: ${current_state}"
  fi
  echo "$current_state" >"$STATE_FILE"
fi

if [[ "$current_state" != OK ]]; then
  exit 1
fi
