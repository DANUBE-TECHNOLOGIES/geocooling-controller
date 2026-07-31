#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${1:-/opt/stacks/smart-building-controller}"
ARCHIVE="${2:-/tmp/Sprint-UI001.zip}"
STAMP="$(date +%Y%m%d-%H%M%S)"

if [[ ! -d "$PROJECT_DIR" ]]; then
  echo "ERREUR: projet introuvable: $PROJECT_DIR" >&2
  exit 1
fi
if [[ ! -f "$ARCHIVE" ]]; then
  echo "ERREUR: archive introuvable: $ARCHIVE" >&2
  exit 1
fi

cd "$PROJECT_DIR"
mkdir -p backups
BACKUP="backups/sprint-ui001-$STAMP.tar.gz"
tar --exclude='./backups' -czf "$BACKUP" \
  frontend/geocooling-ui/src \
  frontend/geocooling-ui/package.json \
  frontend/geocooling-ui/package-lock.json 2>/dev/null || true

unzip -o "$ARCHIVE" -d "$PROJECT_DIR"

cd "$PROJECT_DIR/frontend/geocooling-ui"
npm ci
npm run build

echo
echo "Sprint UI-001 installé et compilé."
echo "Sauvegarde: $PROJECT_DIR/$BACKUP"
echo "Vérifier GEOCOOLING_API_URL dans l'environnement du frontend."
