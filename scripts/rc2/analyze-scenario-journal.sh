#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/opt/stacks/smart-building-controller}"

cd "$REPO"

python3 \
  tools/scenario_engine/analyze_scenario_journal.py \
  "$@"
