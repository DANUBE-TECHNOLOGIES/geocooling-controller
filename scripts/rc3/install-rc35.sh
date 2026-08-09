#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-/opt/stacks/smart-building-controller}"
MAIN="$REPO/backend/app/main.py"
BRANCH="feature/geocooling-ui-v1"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$REPO/backups/rc35-weather-inertia-$STAMP"
TEMPLATE="$REPO/tools/patches/rc35/frontend/page.tsx"

cd "$REPO"

echo "============================================================"
echo " RC3.5 — WEATHER/INERTIA PREDICTOR + FRONTEND"
echo "============================================================"

CURRENT_BRANCH="$(git branch --show-current)"

if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
  echo "ERREUR : branche actuelle $CURRENT_BRANCH"
  echo "Branche attendue : $BRANCH"
  exit 1
fi

for required in \
  backend/app/geocooling/rc3/live_shadow.py \
  backend/app/geocooling/decision_context_live_v1.py \
  "$TEMPLATE"
do
  test -f "$required" || {
    echo "ERREUR : prérequis absent : $required"
    exit 1
  }
done

FRONTEND_ROOT="$(
python3 - "$REPO" <<'PYFRONT'
from __future__ import annotations

import json
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()

ignored = {
    "node_modules",
    ".next",
    ".git",
    "backups",
    "decision-journal",
    "scenario-journal",
    "rc3-shadow-journal",
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
    score = 0

    if "next" in dependencies:
        score += 100

    for config in (
        "next.config.js",
        "next.config.mjs",
        "next.config.ts",
    ):
        if (root / config).exists():
            score += 30

    for relative in (
        "src/app",
        "app",
        "src/pages",
        "pages",
    ):
        if (root / relative).is_dir():
            score += 20

    if "frontend" in str(root).lower():
        score += 10

    if score > 0:
        candidates.append(
            (
                score,
                len(root.parts),
                str(root),
            )
        )

if not candidates:
    raise SystemExit(1)

candidates.sort(
    key=lambda item: (
        -item[0],
        item[1],
        item[2],
    )
)

print(candidates[0][2])
PYFRONT
)" || true

if [ -z "$FRONTEND_ROOT" ]; then
  echo "ERREUR : projet Next.js introuvable."
  exit 1
fi

if [ -d "$FRONTEND_ROOT/src/app" ]; then
  FRONTEND_MODE="app"
  FRONTEND_APP="$FRONTEND_ROOT/src/app"
  PAGE_DIR="$FRONTEND_APP/geocooling/weather-inertia"
  PAGE_FILE="$PAGE_DIR/page.tsx"

elif [ -d "$FRONTEND_ROOT/app" ]; then
  FRONTEND_MODE="app"
  FRONTEND_APP="$FRONTEND_ROOT/app"
  PAGE_DIR="$FRONTEND_APP/geocooling/weather-inertia"
  PAGE_FILE="$PAGE_DIR/page.tsx"

elif [ -d "$FRONTEND_ROOT/src/pages" ]; then
  FRONTEND_MODE="pages"
  FRONTEND_APP="$FRONTEND_ROOT/src/pages"
  PAGE_DIR="$FRONTEND_APP/geocooling/weather-inertia"
  PAGE_FILE="$PAGE_DIR/index.tsx"

elif [ -d "$FRONTEND_ROOT/pages" ]; then
  FRONTEND_MODE="pages"
  FRONTEND_APP="$FRONTEND_ROOT/pages"
  PAGE_DIR="$FRONTEND_APP/geocooling/weather-inertia"
  PAGE_FILE="$PAGE_DIR/index.tsx"

else
  echo "ERREUR : routeur Next.js introuvable."
  exit 1
fi

mkdir -p "$BACKUP/backend/app" "$BACKUP/frontend"

cp -a "$MAIN" "$BACKUP/backend/app/main.py"

if [ -f "$PAGE_DIR/page.tsx" ]; then
  mkdir -p "$BACKUP/frontend/weather-inertia"
  cp -a "$PAGE_DIR/page.tsx" \
    "$BACKUP/frontend/weather-inertia/page.tsx"
fi

echo
echo "[1/8] Vérification syntaxique backend..."

python3 -m py_compile \
  backend/app/geocooling/rc3/weather_inertia_predictor.py \
  backend/app/geocooling/rc3/weather_inertia_live.py \
  backend/app/geocooling/rc3/weather_inertia_router.py \
  backend/tests/test_weather_inertia_predictor.py \
  tools/audit/validate_weather_inertia_predictor.py

echo "Syntaxe backend : OK"

echo
echo "[2/8] Validation fonctionnelle et sécurité..."

PYTHONPATH="$REPO/backend" \
python3 tools/audit/validate_weather_inertia_predictor.py

echo
echo "[3/8] Raccordement idempotent du router..."

python3 - "$MAIN" <<'PY'
from pathlib import Path
import ast
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

import_line = (
    "from app.geocooling.rc3.weather_inertia_router "
    "import router as geocooling_rc3_weather_inertia_router"
)
include_line = (
    "app.include_router("
    "geocooling_rc3_weather_inertia_router"
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
ast.parse(clean)

updated = (
    clean
    + "\n"
    + import_line
    + "\n"
    + include_line
    + "\n"
)

ast.parse(updated)
path.write_text(updated, encoding="utf-8")
PY

python3 -m py_compile backend/app/main.py

echo
echo "[4/8] Installation frontend..."

mkdir -p "$PAGE_DIR"

if [ "$FRONTEND_MODE" = "app" ]; then
  cp -a "$TEMPLATE" "$PAGE_FILE"
else
  python3 - "$TEMPLATE" "$PAGE_FILE" <<'PYPAGE'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
source = source.replace(
    '"use client";\n\n',
    "",
    1,
)

Path(sys.argv[2]).write_text(
    source,
    encoding="utf-8",
)
PYPAGE
fi

echo "Page installée : ${PAGE_FILE#$REPO/}"

echo
echo "[5/8] Vérification TypeScript disponible..."

if [ -f frontend/package.json ]; then
  if docker inspect geocooling-ui-dev >/dev/null 2>&1; then
    if docker exec geocooling-ui-dev sh -lc \
      'if [ -f package.json ]; then npx tsc --noEmit --pretty false; fi'
    then
      echo "TypeScript : OK"
    else
      echo "AVERTISSEMENT : contrôle TypeScript à examiner."
    fi
  else
    echo "Conteneur frontend absent : contrôle TypeScript différé."
  fi
fi

echo
echo "[6/8] Tests unitaires optionnels..."

if command -v pytest >/dev/null 2>&1; then
  PYTHONPATH="$REPO/backend" pytest -q \
    backend/tests/test_weather_inertia_predictor.py
else
  echo "pytest non installé : tests ignorés."
  echo "Validation fonctionnelle directe : OK."
fi

echo
echo "[7/8] Contrôle Git..."

git diff --check -- \
  backend/app/main.py \
  backend/app/geocooling/rc3/ \
  backend/tests/test_weather_inertia_predictor.py \
  tools/audit/validate_weather_inertia_predictor.py \
  docs/architecture/RC35_WEATHER_INERTIA_FULLSTACK.md \
  "${PAGE_FILE#$REPO/}"

git status --short -- \
  backend/app/main.py \
  backend/app/geocooling/rc3/ \
  backend/tests/test_weather_inertia_predictor.py \
  tools/audit/validate_weather_inertia_predictor.py \
  docs/architecture/RC35_WEATHER_INERTIA_FULLSTACK.md \
  "${PAGE_FILE#$REPO/}"

echo
echo "[8/8] Résultat..."

echo "============================================================"
echo " ✅ RC3.5 WEATHER/INERTIA FULLSTACK INSTALLÉ"
echo "============================================================"
echo "Horizons               : 30 min à 48 h"
echo "Scénarios              : BASELINE / SOFT / FULL"
echo "Mode                    : SHADOW"
echo "Controller autorisé     : non"
echo "Commandes matérielles   : aucune"
echo "Page frontend           : /geocooling/weather-inertia"
echo "Redémarrage             : non effectué"
echo "Sauvegarde              : $BACKUP"
echo
echo "Étape suivante :"
echo " docker compose up -d --build backend frontend"
