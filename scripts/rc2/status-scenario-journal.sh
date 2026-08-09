#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/opt/stacks/smart-building-controller}"
DATA_ROOT="$REPO/scenario-journal"
PID_FILE="$DATA_ROOT/collector.pid"
ACTIVE_FILE="$DATA_ROOT/.active-session"

echo "============================================================"
echo " RC2.1C — ÉTAT DU JOURNAL DES SCÉNARIOS"
echo "============================================================"

PID="$(cat "$PID_FILE" 2>/dev/null || true)"

if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  echo "Collecteur : ACTIF"
  echo "PID        : $PID"
else
  echo "Collecteur : ARRÊTÉ"
fi

if [ -f "$ACTIVE_FILE" ]; then
  SESSION="$(cat "$ACTIVE_FILE")"
  echo "Session    : $SESSION"

  if [ -f "$SESSION/scenario-decisions.jsonl" ]; then
    COUNT="$(
      wc -l < "$SESSION/scenario-decisions.jsonl"
    )"
    echo "Échantillons : $COUNT"
    echo
    echo "Dernière décision :"

    tail -1 "$SESSION/scenario-decisions.jsonl" \
      | python3 -m json.tool \
      | sed -n '1,220p'
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
