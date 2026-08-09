#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/opt/stacks/smart-building-controller}"

cd "$REPO"

python3 tools/thermal_twin/build_baseline_model.py "$@"
