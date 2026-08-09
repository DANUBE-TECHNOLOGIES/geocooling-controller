#!/usr/bin/env bash
set -euo pipefail
REPO="${1:-/opt/stacks/smart-building-controller}"
SCRIPT="$REPO/tools/audit/run_audit.py"
cd "$REPO"
[ -f "$SCRIPT" ] || { echo "ERREUR : $SCRIPT introuvable"; exit 1; }
python3 -m py_compile "$SCRIPT"
python3 "$SCRIPT"
echo
echo "============================================================"
echo " RAPPORT"
echo "============================================================"
echo
sed -n '1,220p' "$REPO/audits/latest/REPORT.md"
echo
echo "Rapport complet : $REPO/audits/latest/REPORT.md"
echo "JSON            : $REPO/audits/latest/report.json"
