#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/opt/stacks/smart-building-controller}"
ANALYZER="$REPO/tools/audit/analyze_decision_journal.py"

cd "$REPO"

python3 "$ANALYZER" "$@"

LATEST="$(
  find "$REPO/decision-journal" \
    -maxdepth 1 \
    -type d \
    -name 'session-*' \
    | sort \
    | tail -1
)"

if [ -n "$LATEST" ] && [ -f "$LATEST/analysis/ANALYSIS.md" ]; then
  echo
  sed -n '1,220p' "$LATEST/analysis/ANALYSIS.md"
fi
