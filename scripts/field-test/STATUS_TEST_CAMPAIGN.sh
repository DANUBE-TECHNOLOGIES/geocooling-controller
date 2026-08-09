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

CAMPAIGN="$(active_campaign_dir)" || {
  echo "Aucune campagne active."

  LATEST="$(
    find "$DATA_ROOT" \
      -maxdepth 1 \
      -type d \
      -name 'campaign-*' \
      | sort \
      | tail -1
  )"

  if [ -n "$LATEST" ]; then
    echo "Dernière campagne : $LATEST"
  fi

  exit 1
}

PID="$(
  cat "$CAMPAIGN/collector.pid" 2>/dev/null \
    || true
)"

SAMPLES="$(
  wc -l < "$CAMPAIGN/samples.jsonl" 2>/dev/null \
    || echo 0
)"

echo "============================================================"
echo " ÉTAT CAMPAGNE D’ESSAIS"
echo "============================================================"
echo "Dossier     : $CAMPAIGN"
echo "PID         : ${PID:-inconnu}"
echo "Échantillons: $SAMPLES"

if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  echo "Collecteur  : ACTIF"
else
  echo "Collecteur  : ARRÊTÉ"
fi

echo
echo "Dernière mesure :"

if [ -f "$CAMPAIGN/samples.jsonl" ]; then
  tail -1 "$CAMPAIGN/samples.jsonl" \
    | python3 -m json.tool
else
  echo "Aucune mesure disponible."
fi

echo
echo "Derniers statuts de collecte :"

tail -35 "$CAMPAIGN/collection-status.log" \
  2>/dev/null \
  || true
