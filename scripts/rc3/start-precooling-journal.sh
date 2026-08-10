#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/opt/stacks/smart-building-controller}"
ROOT="$REPO/rc3-precooling-journal"
PID_FILE="$ROOT/collector.pid"
LOG_FILE="$ROOT/collector.log"
COLLECTOR="$REPO/tools/rc3/precooling_advisory_collector.py"

mkdir -p "$ROOT"

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    echo "ERREUR : collecteur déjà actif (PID $PID)"
    exit 1
  fi
  rm -f "$PID_FILE"
fi

rm -f "$ROOT/.stop"
nohup python3 "$COLLECTOR" >> "$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"
sleep 2

if ! kill -0 "$PID" 2>/dev/null; then
  echo "ERREUR : démarrage impossible"
  tail -100 "$LOG_FILE" || true
  exit 1
fi

echo "============================================================"
echo " PRECOOLING SHADOW JOURNAL DEMARRE"
echo "============================================================"
echo "PID        : $PID"
echo "Intervalle : ${GEOCOOLING_PRECOOL_JOURNAL_INTERVAL_SECONDS:-300}s"
echo "Données    : $ROOT"
echo "GET only   : advisory + prediction + context"
echo "Hardware   : AUCUNE ECRITURE"
