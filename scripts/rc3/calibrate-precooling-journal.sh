#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/opt/stacks/smart-building-controller}"
ROOT="$REPO/rc3-precooling-journal"
ANALYZER="$REPO/tools/rc3/calibrate_precooling_journal.py"

SESSION="${1:-}"

if [ -z "$SESSION" ]; then
  if [ -f "$ROOT/.active-session" ]; then
    SESSION="$(cat "$ROOT/.active-session")"
  else
    SESSION="$(find "$ROOT" -maxdepth 1 -type d -name 'session-*' 2>/dev/null | sort | tail -1)"
  fi
fi

if [ -z "$SESSION" ] || [ ! -d "$SESSION" ]; then
  echo "ERREUR : aucune session de pré-refroidissement disponible"
  exit 1
fi

JOURNAL="$SESSION/precooling-snapshots.jsonl"

if [ ! -f "$JOURNAL" ]; then
  echo "ERREUR : journal introuvable : $JOURNAL"
  exit 1
fi

python3 "$ANALYZER" "$JOURNAL"
