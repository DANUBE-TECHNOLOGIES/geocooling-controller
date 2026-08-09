#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-/opt/stacks/smart-building-controller}"
SCRIPT="$REPO/tools/audit/dependency_analyzer.py"

cd "$REPO"

python3 -m py_compile "$SCRIPT"
python3 "$SCRIPT"

REPORT="$REPO/audits/dependency-latest/DEPENDENCY_REPORT.md"

echo
echo "============================================================"
echo " APERÇU DU RAPPORT"
echo "============================================================"
sed -n '1,240p' "$REPORT"

echo
echo "Rapport : $REPORT"
echo "JSON    : $REPO/audits/dependency-latest/dependency-report.json"
echo "DOT     : $REPO/audits/dependency-latest/dependency-graph.dot"
