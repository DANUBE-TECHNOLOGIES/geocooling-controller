#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/opt/stacks/smart-building-controller}"
cd "$REPO"

printf '%s\n' '============================================================'
printf '%s\n' ' GEOCOOLING - DEPLOIEMENT LOGICIEL FINAL'
printf '%s\n' ' AUCUN ARMEMENT / AUCUN ACTIONNEMENT MATERIEL'
printf '%s\n' '============================================================'

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo 'ERREUR : fichiers versionnés modifiés localement.'
  git status --short
  exit 1
fi

if [ ! -f .env ]; then
  echo 'ERREUR : .env local absent.'
  exit 1
fi

read_env_value() {
  local name="$1"
  local fallback="${2:-}"
  local value
  value="$(grep -E "^${name}=" .env | tail -1 | cut -d= -f2- | xargs || true)"
  printf '%s' "${value:-$fallback}"
}

read_flag() {
  read_env_value "$1" '' | tr '[:upper:]' '[:lower:]'
}

for flag in \
  GEOCOOLING_HARDWARE_ARMED \
  GEOCOOLING_HARDWARE_SEQUENCE_ENABLED \
  GEOCOOLING_AUTOPILOT_ENABLED \
  GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER
do
  value="$(read_flag "$flag")"
  echo "$flag=${value:-UNSET}"
  if [ "$value" != 'false' ]; then
    echo "ERREUR : $flag doit être explicitement false avant déploiement."
    exit 1
  fi
done

api_port="$(read_env_value SBC_API_PORT 8000)"
ui_port="$(read_env_value GEOCOOLING_UI_PORT 3000)"

echo "SBC_API_PORT=$api_port"
echo "GEOCOOLING_UI_PORT=$ui_port"

echo
echo '===== CONFIGURATION COMPOSE ====='
docker compose config -q

echo
echo '===== BUILD ====='
docker compose build backend frontend

echo
echo '===== RECREATE BACKEND + FRONTEND ====='
docker compose up -d --force-recreate backend frontend

echo
echo '===== ATTENTE BACKEND ====='
backend_ready=false
for i in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:${api_port}/health/live" >/dev/null 2>&1; then
    backend_ready=true
    echo "backend=READY après ${i}s"
    break
  fi
  sleep 1
done
if [ "$backend_ready" != 'true' ]; then
  echo 'ERREUR : backend non healthy.'
  docker compose logs --tail=120 backend
  exit 1
fi

echo
echo '===== ATTENTE FRONTEND ====='
frontend_ready=false
for i in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:${ui_port}/geocooling/readiness" >/dev/null 2>&1; then
    frontend_ready=true
    echo "frontend=READY après ${i}s"
    break
  fi
  sleep 1
done
if [ "$frontend_ready" != 'true' ]; then
  echo 'ERREUR : frontend non healthy.'
  docker compose logs --tail=120 frontend
  exit 1
fi

echo
echo '===== SERVICES ====='
docker compose ps backend frontend esphome-bridge

echo
echo '===== FINAL READINESS ====='
GEOCOOLING_INTERNAL_API_BASE_URL="http://127.0.0.1:${api_port}" \
  bash scripts/release/geocooling-final-readiness-audit.sh

echo
echo '===== JOURNAL PRECOOLING ====='
if [ -f rc3-precooling-journal/.active-session ]; then
  bash scripts/rc3/status-precooling-journal.sh || true
else
  echo 'precooling_journal=NOT_RUNNING'
fi

echo
echo '============================================================'
echo ' DEPLOIEMENT LOGICIEL TERMINE'
echo ' EV / M11 / M13 NON COMMANDES'
echo '============================================================'
