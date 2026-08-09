#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/opt/stacks/smart-building-controller}"
DATA_ROOT="$REPO/scenario-journal"
PID_FILE="$DATA_ROOT/collector.pid"
LOG_FILE="$DATA_ROOT/collector.log"
COLLECTOR="$REPO/tools/scenario_engine/scenario_journal_collector.py"

mkdir -p "$DATA_ROOT"

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"

  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    echo "ERREUR : journal déjà actif (PID $PID)"
    exit 1
  fi

  rm -f "$PID_FILE"
fi

rm -f "$DATA_ROOT/.stop"

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
echo " ✅ JOURNAL DES SCÉNARIOS DÉMARRÉ"
echo "============================================================"
echo "PID        : $PID"
echo "Intervalle : ${GEOCOOLING_SCENARIO_JOURNAL_INTERVAL_SECONDS:-30}s"
echo "Données    : $DATA_ROOT"
echo "Méthode    : GET uniquement"
echo "Activation : aucune"
