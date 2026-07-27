#!/usr/bin/env bash
set -Eeuo pipefail

TARGET="${1:-/opt/stacks/smart-building-controller}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAYLOAD="$HERE/payload"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${TARGET}.backup-${STAMP}"

log() { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
fail() { printf '\nERREUR: %s\n' "$*" >&2; exit 1; }

[[ -d "$TARGET" ]] || fail "Dépôt cible introuvable : $TARGET"
[[ -f "$TARGET/.env" ]] || fail "Fichier $TARGET/.env introuvable"
command -v docker >/dev/null 2>&1 || fail "Docker est requis"
docker compose version >/dev/null 2>&1 || fail "docker compose est requis"

rollback() {
  local code=$?
  if [[ $code -ne 0 ]]; then
    printf '\nÉchec du déploiement. Restauration de %s...\n' "$BACKUP" >&2
    if [[ -d "$BACKUP" ]]; then
      rm -rf "$TARGET/backend" "$TARGET/tests"
      cp -a "$BACKUP/backend" "$TARGET/backend"
      [[ -d "$BACKUP/tests" ]] && cp -a "$BACKUP/tests" "$TARGET/tests"
      cp -a "$BACKUP/compose.yaml" "$TARGET/compose.yaml"
      cp -a "$BACKUP/VERSION" "$TARGET/VERSION"
      cd "$TARGET"
      docker compose up -d --build || true
    fi
  fi
  exit $code
}
trap rollback EXIT

log "Sauvegarde de la version actuelle"
mkdir -p "$BACKUP"
cp -a "$TARGET/backend" "$BACKUP/backend"
[[ -d "$TARGET/tests" ]] && cp -a "$TARGET/tests" "$BACKUP/tests"
cp -a "$TARGET/compose.yaml" "$BACKUP/compose.yaml"
cp -a "$TARGET/VERSION" "$BACKUP/VERSION"

log "Installation des fichiers 0.6.8"
rm -rf "$TARGET/backend" "$TARGET/tests"
cp -a "$PAYLOAD/backend" "$TARGET/backend"
cp -a "$PAYLOAD/tests" "$TARGET/tests"
cp -a "$PAYLOAD/compose.yaml" "$TARGET/compose.yaml"
cp -a "$PAYLOAD/VERSION" "$TARGET/VERSION"
cp -a "$PAYLOAD/CHANGELOG-0.6.8.md" "$TARGET/CHANGELOG-0.6.8.md"

log "Validation de la syntaxe Python"
docker run --rm -v "$TARGET/backend:/app/backend:rw" python:3.13-alpine \
  python -m compileall -q /app/backend

log "Construction et démarrage"
cd "$TARGET"
docker compose build backend
docker compose up -d

log "Attente du backend"
for _ in $(seq 1 40); do
  if docker compose exec -T backend python -c \
    'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health/live", timeout=3)' \
    >/dev/null 2>&1; then
    break
  fi
  sleep 3
done

docker compose exec -T backend python -c \
  'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health/live", timeout=3)'

log "Validation des imports GeoCooling"
docker compose exec -T backend python -c \
  'from app.geocooling.runtime import RuntimeGuards; from app.geocooling.safety import GeoCoolingSafetyManager; from app.geocooling.api import router; print("GeoCooling 0.6.8 OK")'

log "Tests unitaires GeoCooling"
docker compose exec -T backend sh -lc \
  'PYTHONPATH=/app python -m unittest discover -s /app/tests -p "test_geocooling_*.py" -v'

log "Validation des endpoints"
PORT="$(grep -E '^SBC_API_PORT=' .env | tail -1 | cut -d= -f2- || true)"
PORT="${PORT:-8000}"
python3 - <<PY
import json, urllib.request
base = "http://127.0.0.1:${PORT}"
for path in ("/health/live", "/geocooling/status", "/geocooling/diagnostics", "/geocooling/safety"):
    with urllib.request.urlopen(base + path, timeout=10) as response:
        assert response.status == 200, (path, response.status)
        json.load(response)
print("API 0.6.8 OK")
PY

trap - EXIT
log "Installation 0.6.8 terminée"
printf 'Sauvegarde conservée : %s\n' "$BACKUP"
