#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/opt/stacks/smart-building-controller}"
ROOT="$REPO/rc3-prediction-journal"
PID_FILE="$ROOT/collector.pid"
ACTIVE="$ROOT/.active-session"

echo "============================================================"
echo " RC3.7 — ÉTAT DU COLLECTEUR"
echo "============================================================"

PID="$(cat "$PID_FILE" 2>/dev/null || true)"

if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  echo "Collecteur : ACTIF"
  echo "PID        : $PID"
else
  echo "Collecteur : ARRÊTÉ"
fi

if [ -f "$ACTIVE" ]; then
  SESSION="$(cat "$ACTIVE")"
  echo "Session    : $SESSION"

  if [ -f "$SESSION/prediction-snapshots.jsonl" ]; then
    echo "Échantillons : $(
      wc -l < "$SESSION/prediction-snapshots.jsonl"
    )"
  fi
fi
