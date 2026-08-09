#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-/opt/stacks/smart-building-controller}"
MAIN="$REPO/backend/app/main.py"
BRANCH="feature/geocooling-ui-v1"
TEMPLATE="$REPO/tools/patches/rc37/frontend/page.tsx"

cd "$REPO"

echo "============================================================"
echo " RC3.7 — PREDICTION VALIDATION FULLSTACK"
echo "============================================================"

CURRENT_BRANCH="$(git branch --show-current)"

if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
  echo "ERREUR : branche actuelle $CURRENT_BRANCH"
  exit 1
fi

for required in \
  backend/app/geocooling/rc3/weather_inertia_predictor.py \
  backend/app/geocooling/rc3/predictor_calibration.py \
  "$TEMPLATE"
do
  test -f "$required" || {
    echo "ERREUR : prérequis absent : $required"
    exit 1
  }
done

FRONTEND_ROOT="$(
python3 - "$REPO" <<'PYFRONT'
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
ignored = {
    "node_modules",
    ".next",
    ".git",
    "backups",
}

candidates = []

for package_file in repo.rglob("package.json"):
    if any(part in ignored for part in package_file.parts):
        continue

    try:
        payload = json.loads(
            package_file.read_text(encoding="utf-8")
        )
    except Exception:
        continue

    dependencies = {}

    for section in (
        "dependencies",
        "devDependencies",
        "peerDependencies",
    ):
        value = payload.get(section)
        if isinstance(value, dict):
            dependencies.update(value)

    root = package_file.parent
    score = 100 if "next" in dependencies else 0

    for relative in (
        "src/app",
        "app",
        "src/pages",
        "pages",
    ):
        if (root / relative).is_dir():
            score += 20

    if score:
        candidates.append((score, len(root.parts), str(root)))

if not candidates:
    raise SystemExit(1)

candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
print(candidates[0][2])
PYFRONT
)" || true

if [ -z "$FRONTEND_ROOT" ]; then
  echo "ERREUR : projet Next.js introuvable."
  exit 1
fi

if [ -d "$FRONTEND_ROOT/src/app" ]; then
  MODE="app"
  PAGE="$FRONTEND_ROOT/src/app/geocooling/prediction-validation/page.tsx"
elif [ -d "$FRONTEND_ROOT/app" ]; then
  MODE="app"
  PAGE="$FRONTEND_ROOT/app/geocooling/prediction-validation/page.tsx"
elif [ -d "$FRONTEND_ROOT/src/pages" ]; then
  MODE="pages"
  PAGE="$FRONTEND_ROOT/src/pages/geocooling/prediction-validation/index.tsx"
else
  MODE="pages"
  PAGE="$FRONTEND_ROOT/pages/geocooling/prediction-validation/index.tsx"
fi

echo
echo "[1/7] Vérification syntaxique..."

python3 -m py_compile \
  backend/app/geocooling/rc3/prediction_validation.py \
  backend/app/geocooling/rc3/prediction_validation_live.py \
  backend/app/geocooling/rc3/prediction_validation_router.py \
  backend/tests/test_prediction_validation.py \
  tools/rc3/rc37_prediction_collector.py \
  tools/audit/validate_prediction_validation.py

bash -n \
  scripts/rc3/start-prediction-journal.sh \
  scripts/rc3/status-prediction-journal.sh \
  scripts/rc3/stop-prediction-journal.sh

echo "Syntaxe : OK"

echo
echo "[2/7] Validation sécurité et fonctionnelle..."

PYTHONPATH="$REPO/backend" \
python3 tools/audit/validate_prediction_validation.py

echo
echo "[3/7] Raccordement du router..."

python3 - "$MAIN" <<'PY'
from pathlib import Path
import ast
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

import_line = (
    "from app.geocooling.rc3.prediction_validation_router "
    "import router as geocooling_rc3_prediction_validation_router"
)
include_line = (
    "app.include_router("
    "geocooling_rc3_prediction_validation_router"
    ")"
)

lines = [
    line
    for line in text.splitlines()
    if line.strip() not in {
        import_line,
        include_line,
    }
]

clean = "\n".join(lines).rstrip() + "\n"
updated = clean + "\n" + import_line + "\n" + include_line + "\n"

ast.parse(updated)
path.write_text(updated, encoding="utf-8")
PY

python3 -m py_compile backend/app/main.py

echo
echo "[4/7] Installation frontend..."

mkdir -p "$(dirname "$PAGE")"

if [ "$MODE" = "app" ]; then
  cp -a "$TEMPLATE" "$PAGE"
else
  python3 - "$TEMPLATE" "$PAGE" <<'PYPAGE'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
source = source.replace('"use client";\n\n', "", 1)
Path(sys.argv[2]).write_text(source, encoding="utf-8")
PYPAGE
fi

echo "Page : ${PAGE#$REPO/}"

echo
echo "[5/7] Installation des commandes..."

ln -sfn \
  "$REPO/scripts/rc3/start-prediction-journal.sh" \
  "$REPO/START_RC3_PREDICTION_JOURNAL.sh"

ln -sfn \
  "$REPO/scripts/rc3/status-prediction-journal.sh" \
  "$REPO/STATUS_RC3_PREDICTION_JOURNAL.sh"

ln -sfn \
  "$REPO/scripts/rc3/stop-prediction-journal.sh" \
  "$REPO/STOP_RC3_PREDICTION_JOURNAL.sh"

echo
echo "[6/7] État Git..."

git diff --check -- \
  backend/app/main.py \
  backend/app/geocooling/rc3/ \
  backend/tests/test_prediction_validation.py \
  tools/rc3/ \
  tools/audit/validate_prediction_validation.py \
  scripts/rc3/ \
  "${PAGE#$REPO/}"

echo
echo "[7/7] Résultat..."

echo "============================================================"
echo " ✅ RC3.7 VALIDATION PRÉDICTIVE INSTALLÉE"
echo "============================================================"
echo "Collecte                : toutes les 5 minutes"
echo "Horizons validés        : 30 min à 48 h"
echo "Activation automatique  : non"
echo "Controller autorisé      : non"
echo "Page frontend            : /geocooling/prediction-validation"
echo
echo "Après reconstruction, démarrer :"
echo " ./START_RC3_PREDICTION_JOURNAL.sh"
