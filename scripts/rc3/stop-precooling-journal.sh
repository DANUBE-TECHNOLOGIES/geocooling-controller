#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/opt/stacks/smart-building-controller}"
ROOT="$REPO/rc3-precooling-journal"
PID_FILE="$ROOT/collector.pid"
STOP_FILE="$ROOT/.stop"

mkdir -p "$ROOT"
touch "$STOP_FILE"

PID=""
if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
fi

if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  for _ in $(seq 1 30); do
    if ! kill -0 "$PID" 2>/dev/null; then
      break
    fi
    sleep 1
  done

  if kill -0 "$PID" 2>/dev/null; then
    kill -TERM "$PID" 2>/dev/null || true
  fi
fi

rm -f "$PID_FILE"

echo "============================================================"
echo " PRECOOLING SHADOW JOURNAL ARRETE"
echo "============================================================"
echo "Aucune commande materielle n'a ete emise."
