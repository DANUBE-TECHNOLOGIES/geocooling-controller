#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/opt/stacks/smart-building-controller}"
ROOT="$REPO/rc3-precooling-journal"
PID_FILE="$ROOT/collector.pid"
ACTIVE_FILE="$ROOT/.active-session"
LOG_FILE="$ROOT/collector.log"

PID=""
if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
fi

if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  STATE="RUNNING"
else
  STATE="STOPPED"
fi

echo "============================================================"
echo " PRECOOLING SHADOW JOURNAL STATUS"
echo "============================================================"
echo "state=$STATE"
echo "pid=${PID:-none}"

if [ -f "$ACTIVE_FILE" ]; then
  SESSION="$(cat "$ACTIVE_FILE")"
  echo "session=$SESSION"
  if [ -f "$SESSION/precooling-snapshots.jsonl" ]; then
    echo "samples=$(wc -l < "$SESSION/precooling-snapshots.jsonl" | tr -d ' ')"
    echo "last_snapshot:"
    tail -1 "$SESSION/precooling-snapshots.jsonl" || true
  else
    echo "samples=0"
  fi
else
  echo "session=none"
fi

if [ -f "$LOG_FILE" ]; then
  echo "log_tail:"
  tail -20 "$LOG_FILE" || true
fi
