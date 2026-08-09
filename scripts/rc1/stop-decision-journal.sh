#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/opt/stacks/smart-building-controller}"
DATA_ROOT="$REPO/decision-journal"
PID_FILE="$DATA_ROOT/collector.pid"
STOP_FILE="$DATA_ROOT/.stop"
ACTIVE="$DATA_ROOT/.active"

mkdir -p "$DATA_ROOT"
touch "$STOP_FILE"

PID="$(cat "$PID_FILE" 2>/dev/null || true)"

if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  for _ in $(seq 1 15); do
    if ! kill -0 "$PID" 2>/dev/null; then
      break
    fi
    sleep 1
  done

  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
  fi
fi

rm -f "$PID_FILE"

SESSION=""
if [ -f "$ACTIVE" ]; then
  SESSION="$(cat "$ACTIVE")"
fi

sleep 1

if [ -n "$SESSION" ] && [ -d "$SESSION" ]; then
  ARCHIVE="$SESSION.tar.gz"
  tar -czf "$ARCHIVE" \
    -C "$(dirname "$SESSION")" \
    "$(basename "$SESSION")"

  echo "============================================================"
  echo " ✅ JOURNAL PASSIF ARRÊTÉ"
  echo "============================================================"
  echo "Session : $SESSION"
  echo "Archive : $ARCHIVE"
else
  echo "Journal arrêté."
fi
