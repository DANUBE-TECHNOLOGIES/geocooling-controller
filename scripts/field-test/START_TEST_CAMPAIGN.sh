#!/usr/bin/env bash
set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  SOURCE_DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
  SOURCE="$(readlink "$SOURCE")"

  if [[ "$SOURCE" != /* ]]; then
    SOURCE="$SOURCE_DIR/$SOURCE"
  fi
done

SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"

source "$SCRIPT_DIR/field-test-common.sh"

INTERVAL_SECONDS="${1:-30}"

if ! [[ "$INTERVAL_SECONDS" =~ ^[0-9]+$ ]]; then
  echo "ERREUR : intervalle invalide."
  exit 1
fi

if [ "$INTERVAL_SECONDS" -lt 10 ]; then
  echo "ERREUR : intervalle minimal = 10 secondes."
  exit 1
fi

if active_campaign_dir >/dev/null 2>&1; then
  echo "ERREUR : une campagne est déjà active :"
  active_campaign_dir
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
CAMPAIGN="$DATA_ROOT/campaign-$STAMP"

mkdir -p \
  "$CAMPAIGN/data" \
  "$CAMPAIGN/logs"

cat > "$CAMPAIGN/metadata.json" <<JSON
{
  "schema": "geocooling.field-test.v1",
  "started_at": "$(date --iso-8601=seconds)",
  "interval_seconds": $INTERVAL_SECONDS,
  "read_only": true,
  "hardware_commands_sent": false,
  "branch": "$(git -C "$REPO" branch --show-current)",
  "commit": "$(git -C "$REPO" rev-parse HEAD)"
}
JSON

printf '%s\n' "$CAMPAIGN" > "$ACTIVE_FILE"

docker ps \
  --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' \
  > "$CAMPAIGN/logs/docker-start.txt"

git -C "$REPO" status --short \
  > "$CAMPAIGN/logs/git-status-start.txt"

(
  while [ -f "$ACTIVE_FILE" ] \
    && [ "$(cat "$ACTIVE_FILE" 2>/dev/null || true)" = "$CAMPAIGN" ]
  do
    "$SCRIPT_DIR/collect-once.sh" || true
    sleep "$INTERVAL_SECONDS"
  done
) > "$CAMPAIGN/background.log" 2>&1 &

PID=$!

printf '%s\n' "$PID" > "$CAMPAIGN/collector.pid"

echo "============================================================"
echo " ✅ CAMPAGNE D’ESSAIS DÉMARRÉE"
echo "============================================================"
echo "Dossier    : $CAMPAIGN"
echo "Intervalle : ${INTERVAL_SECONDS}s"
echo "PID        : $PID"
echo
echo "Aucune commande matérielle envoyée."
