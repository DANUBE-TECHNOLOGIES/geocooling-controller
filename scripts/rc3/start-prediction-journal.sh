#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/opt/stacks/smart-building-controller}"
ROOT="$REPO/rc3-prediction-journal"
PID_FILE="$ROOT/collector.pid"
LOG_FILE="$ROOT/collector.log"
COLLECTOR="$REPO/tools/rc3/rc37_prediction_collector.py"

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

nohup python3 "$COLLECTOR" \
  >> "$LOG_FILE" 2>&1 &

PID=$!
echo "$PID" > "$PID_FILE"

sleep 2

if ! kill -0 "$PID" 2>/dev/null; then
  echo "ERREUR : démarrage impossible"
  tail -100 "$LOG_FILE" || true
  exit 1
fi

echo "============================================================"
echo " ✅ COLLECTEUR DE PRÉDICTIONS DÉMARRÉ"
echo "============================================================"
echo "PID        : $PID"
echo "Intervalle : ${GEOCOOLING_RC37_INTERVAL_SECONDS:-300}s"
echo "Données    : $ROOT"
