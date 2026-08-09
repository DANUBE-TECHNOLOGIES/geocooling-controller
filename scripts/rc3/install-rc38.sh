#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-/opt/stacks/smart-building-controller}"
MAIN="$REPO/backend/app/main.py"
TEMPLATE="$REPO/tools/patches/rc38/frontend/page.tsx"
BRANCH="feature/geocooling-ui-v1"

cd "$REPO"

echo "============================================================"
echo " RC3.8 — VALIDATION/CALIBRATION BRIDGE FULLSTACK"
echo "============================================================"

[ "$(git branch --show-current)" = "$BRANCH" ] || {
  echo "ERREUR : branche incorrecte"
  exit 1
}

for required in \
  backend/app/geocooling/rc3/prediction_validation.py \
  backend/app/geocooling/rc3/predictor_calibration.py \
  backend/app/geocooling/rc3/weather_inertia_live.py \
  "$TEMPLATE"
do
  test -f "$required" || {
    echo "ERREUR : prérequis absent : $required"
    exit 1
  }
done

FRONTEND_ROOT="$(
python3 - "$REPO" <<'PYFRONT'
import json, sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
candidates = []

for package in repo.rglob("package.json"):
    if any(part in {"node_modules", ".next", ".git", "backups"} for part in package.parts):
        continue

    try:
        payload = json.loads(package.read_text(encoding="utf-8"))
    except Exception:
        continue

    deps = {}
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        value = payload.get(section)
        if isinstance(value, dict):
            deps.update(value)

    root = package.parent
    score = 100 if "next" in deps else 0
    for relative in ("src/app", "app", "src/pages", "pages"):
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

[ -n "$FRONTEND_ROOT" ] || {
  echo "ERREUR : projet Next.js introuvable"
  exit 1
}

if [ -d "$FRONTEND_ROOT/src/app" ]; then
  MODE="app"
  PAGE="$FRONTEND_ROOT/src/app/geocooling/learning/page.tsx"
elif [ -d "$FRONTEND_ROOT/app" ]; then
  MODE="app"
  PAGE="$FRONTEND_ROOT/app/geocooling/learning/page.tsx"
elif [ -d "$FRONTEND_ROOT/src/pages" ]; then
  MODE="pages"
  PAGE="$FRONTEND_ROOT/src/pages/geocooling/learning/index.tsx"
else
  MODE="pages"
  PAGE="$FRONTEND_ROOT/pages/geocooling/learning/index.tsx"
fi

echo "[1/6] Syntaxe..."
python3 -m py_compile \
  backend/app/geocooling/rc3/validation_calibration_bridge.py \
  backend/app/geocooling/rc3/validation_calibration_bridge_live.py \
  backend/app/geocooling/rc3/validation_calibration_bridge_router.py \
  backend/tests/test_validation_calibration_bridge.py \
  tools/audit/validate_validation_calibration_bridge.py

echo "[2/6] Validation..."
PYTHONPATH="$REPO/backend" \
python3 tools/audit/validate_validation_calibration_bridge.py

echo "[3/6] Router..."
python3 - "$MAIN" <<'PY'
from pathlib import Path
import ast, sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
import_line = (
    "from app.geocooling.rc3.validation_calibration_bridge_router "
    "import router as geocooling_rc3_learning_router"
)
include_line = "app.include_router(geocooling_rc3_learning_router)"

lines = [
    line for line in text.splitlines()
    if line.strip() not in {import_line, include_line}
]
updated = "\n".join(lines).rstrip() + "\n\n" + import_line + "\n" + include_line + "\n"
ast.parse(updated)
path.write_text(updated, encoding="utf-8")
PY

python3 -m py_compile backend/app/main.py

echo "[4/6] Frontend..."
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

echo "[5/6] Git..."
git diff --check -- \
  backend/app/main.py \
  backend/app/geocooling/rc3/ \
  backend/tests/test_validation_calibration_bridge.py \
  tools/audit/validate_validation_calibration_bridge.py \
  "${PAGE#$REPO/}"

echo "[6/6] Résultat..."
echo "============================================================"
echo " ✅ RC3.8 BOUCLE D'APPRENTISSAGE INSTALLÉE"
echo "============================================================"
echo "Page frontend : /geocooling/learning"
echo "Activation automatique : non"
echo "Controller autorisé : non"
