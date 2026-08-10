#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/opt/stacks/smart-building-controller}"
ROOT="$REPO/rc3-precooling-journal"
ACTIVE_FILE="$ROOT/.active-session"
ANALYZER="$REPO/tools/rc3/analyze_precooling_journal.py"

SESSION=""
if [ -f "$ACTIVE_FILE" ]; then
  SESSION="$(cat "$ACTIVE_FILE")"
fi

if [ -z "$SESSION" ] || [ ! -d "$SESSION" ]; then
  SESSION="$(find "$ROOT" -maxdepth 1 -type d -name 'session-*' 2>/dev/null | sort | tail -1 || true)"
fi

if [ -z "$SESSION" ] || [ ! -d "$SESSION" ]; then
  echo "ERREUR : aucune session de journal de pré-refroidissement trouvée"
  exit 1
fi

SNAPSHOTS="$SESSION/precooling-snapshots.jsonl"
if [ ! -f "$SNAPSHOTS" ]; then
  echo "ERREUR : aucun snapshot dans $SESSION"
  exit 1
fi

echo "============================================================"
echo " PRECOOLING SHADOW JOURNAL ANALYSIS"
echo "============================================================"
echo "session=$SESSION"
python3 "$ANALYZER" "$SNAPSHOTS"

echo
echo "Aucune commande matérielle n'a été émise."
