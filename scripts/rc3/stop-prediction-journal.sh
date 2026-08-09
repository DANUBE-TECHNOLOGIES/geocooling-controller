#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/opt/stacks/smart-building-controller}"
ROOT="$REPO/rc3-prediction-journal"
PID_FILE="$ROOT/collector.pid"

mkdir -p "$ROOT"
touch "$ROOT/.stop"

PID="$(cat "$PID_FILE" 2>/dev/null || true)"

if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  for _ in $(seq 1 20); do
    if ! kill -0 "$PID" 2>/dev/null; then
      break
    fi
    sleep 1
  done
fi

rm -f "$PID_FILE"

echo "Collecteur RC3.7 arrêté."
