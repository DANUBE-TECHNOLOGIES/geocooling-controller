#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/opt/stacks/smart-building-controller}"
DATA_ROOT="$REPO/decision-journal"
PID_FILE="$DATA_ROOT/collector.pid"
ACTIVE="$DATA_ROOT/.active"

echo "============================================================"
echo " RC1.7D — ÉTAT DU JOURNAL PASSIF"
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

  if [ -f "$SESSION/contexts.jsonl" ]; then
    COUNT="$(wc -l < "$SESSION/contexts.jsonl")"
    echo "Échantillons: $COUNT"
    echo
    echo "Dernier contexte :"
    tail -1 "$SESSION/contexts.jsonl" \
      | python3 -m json.tool \
      | sed -n '1,180p'
  fi
else
  LATEST="$(
    find "$DATA_ROOT" \
      -maxdepth 1 \
      -type d \
      -name 'session-*' \
      | sort \
      | tail -1
  )"

  if [ -n "$LATEST" ]; then
    echo "Dernière session : $LATEST"
  fi
fi
