#!/usr/bin/env bash
set -euo pipefail

REPO="/opt/stacks/smart-building-controller"
REPORT_DIR="$REPO/audits/rc1-runtime"
STAMP="$(date +%Y%m%d-%H%M%S)"
REPORT="$REPORT_DIR/runtime-$STAMP.log"
LATEST="$REPORT_DIR/latest.log"

BACKEND_CONTAINER="sbc-backend"
FRONTEND_CONTAINER="geocooling-ui-dev"
BACKEND_URL="http://127.0.0.1:8000"
FRONTEND_URL="http://127.0.0.1:3000"

mkdir -p "$REPORT_DIR"

exec > >(tee "$REPORT") 2>&1

PASS=0
WARN=0
FAIL=0

pass() {
  PASS=$((PASS + 1))
  printf '✅ PASS — %s\n' "$1"
}

warn() {
  WARN=$((WARN + 1))
  printf '⚠️  WARN — %s\n' "$1"
}

fail() {
  FAIL=$((FAIL + 1))
  printf '❌ FAIL — %s\n' "$1"
}

json_get() {
  local url="$1"
  local output="$2"

  curl -fsS \
    --connect-timeout 5 \
    --max-time 30 \
    "$url" \
    > "$output"
}

test_json_route() {
  local name="$1"
  local route="$2"
  local file="$REPORT_DIR/${name//[^a-zA-Z0-9_-]/_}-$STAMP.json"

  if json_get "$BACKEND_URL$route" "$file"; then
    if python3 -m json.tool "$file" >/dev/null 2>&1; then
      pass "$name — $route"
    else
      fail "$name — JSON invalide"
    fi
  else
    fail "$name — $route inaccessible"
  fi
}

echo "============================================================"
echo " GEOCOOLING RC1.4 — VALIDATION DYNAMIQUE"
echo "============================================================"
echo "Date : $(date --iso-8601=seconds)"
echo
echo "MODE STRICTEMENT LECTURE SEULE"
echo "Aucune route POST/PUT/PATCH/DELETE ne sera appelée."
echo

echo "============================================================"
echo "1. DOCKER"
echo "============================================================"

if docker inspect "$BACKEND_CONTAINER" >/dev/null 2>&1; then
  BACKEND_STATE="$(
    docker inspect \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
      "$BACKEND_CONTAINER"
  )"

  if [ "$BACKEND_STATE" = "healthy" ] || [ "$BACKEND_STATE" = "running" ]; then
    pass "Backend Docker : $BACKEND_STATE"
  else
    fail "Backend Docker : $BACKEND_STATE"
  fi
else
  fail "Conteneur backend introuvable"
fi

if docker inspect "$FRONTEND_CONTAINER" >/dev/null 2>&1; then
  FRONTEND_STATE="$(
    docker inspect \
      --format '{{.State.Status}}' \
      "$FRONTEND_CONTAINER"
  )"

  if [ "$FRONTEND_STATE" = "running" ]; then
    pass "Frontend Docker : running"
  else
    fail "Frontend Docker : $FRONTEND_STATE"
  fi
else
  fail "Conteneur frontend introuvable"
fi

echo
echo "============================================================"
echo "2. IMPORTS APPLICATIFS"
echo "============================================================"

if docker exec "$BACKEND_CONTAINER" python - <<'PY'
import fastapi
import app.main
from app.geocooling.rc1_architecture import architecture_status
from app.geocooling.rc1_pipeline import pipeline_status

architecture = architecture_status()
pipeline = pipeline_status()

assert architecture["ready"] is True
assert pipeline["ready"] is True

print("FastAPI :", fastapi.__version__)
print("Architecture ready :", architecture["ready"])
print("Pipeline ready     :", pipeline["ready"])
PY
then
  pass "Imports applicatifs et contrat RC1"
else
  fail "Imports applicatifs ou contrat RC1"
fi

echo
echo "============================================================"
echo "3. ROUTES RC1"
echo "============================================================"

test_json_route \
  "RC1 architecture" \
  "/geocooling/rc1/architecture"

test_json_route \
  "RC1 pipeline" \
  "/geocooling/rc1/pipeline"

test_json_route \
  "RC1 readiness" \
  "/geocooling/rc1/readiness"

READINESS_FILE="$REPORT_DIR/RC1_readiness-$STAMP.json"

if [ -f "$READINESS_FILE" ]; then
  if python3 - "$READINESS_FILE" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())

if payload.get("ready") is not True:
    raise SystemExit(1)

if payload.get("failed_roles"):
    raise SystemExit(1)

print("RC1 ready :", payload["ready"])
PY
  then
    pass "Readiness RC1 globale"
  else
    fail "Readiness RC1 globale"
  fi
fi

echo
echo "============================================================"
echo "4. API OPÉRATIONNELLES"
echo "============================================================"

test_json_route \
  "GeoCooling status" \
  "/geocooling/status"

test_json_route \
  "GeoCooling health" \
  "/geocooling/health"

test_json_route \
  "Snapshot dashboard" \
  "/geocooling/dashboard"

test_json_route \
  "Thermal" \
  "/geocooling/thermal"

test_json_route \
  "Brain" \
  "/geocooling/brain"

test_json_route \
  "Prediction" \
  "/geocooling/prediction"

test_json_route \
  "Safety" \
  "/geocooling/safety"

test_json_route \
  "Runtime" \
  "/geocooling/runtime"

test_json_route \
  "Historian status" \
  "/geocooling/historian/status"

test_json_route \
  "Digital twin" \
  "/geocooling/digital-twin"

test_json_route \
  "Hardware readiness" \
  "/geocooling/industrial-platform/hardware-readiness"

echo
echo "============================================================"
echo "5. MATÉRIEL — LECTURE SEULE"
echo "============================================================"

test_json_route \
  "Relay status" \
  "/geocooling/relay/status"

test_json_route \
  "Hardware status" \
  "/geocooling/manual/hardware/status"

test_json_route \
  "Hardware certification" \
  "/geocooling/hardware-certification"

test_json_route \
  "MQTT preflight" \
  "/geocooling/mqtt-preflight"

echo
echo "============================================================"
echo "6. FRONTEND"
echo "============================================================"

if curl -fsS \
  --connect-timeout 5 \
  --max-time 60 \
  "$FRONTEND_URL/" \
  > "$REPORT_DIR/frontend-home-$STAMP.html"
then
  pass "Frontend /"
else
  fail "Frontend /"
fi

for page in \
  brain \
  runtime \
  historian \
  forecast \
  hardware \
  digital-twin
do
  if curl -fsS \
    --connect-timeout 5 \
    --max-time 60 \
    "$FRONTEND_URL/$page" \
    > "$REPORT_DIR/frontend-$page-$STAMP.html"
  then
    pass "Frontend /$page"
  else
    fail "Frontend /$page"
  fi
done

echo
echo "============================================================"
echo "7. LOGS"
echo "============================================================"

BACKEND_ERRORS="$(
  docker logs "$BACKEND_CONTAINER" --since 10m 2>&1 \
    | grep -Eic 'traceback|exception|critical|fatal' \
    || true
)"

if [ "$BACKEND_ERRORS" -eq 0 ]; then
  pass "Aucune erreur critique backend sur 10 minutes"
else
  warn "$BACKEND_ERRORS ligne(s) critique(s) dans les logs backend"
  docker logs "$BACKEND_CONTAINER" --since 10m 2>&1 \
    | grep -Ei 'traceback|exception|critical|fatal' \
    | tail -80 \
    || true
fi

FRONTEND_ERRORS="$(
  docker logs "$FRONTEND_CONTAINER" --since 10m 2>&1 \
    | grep -Eic 'error|exception|fatal' \
    || true
)"

if [ "$FRONTEND_ERRORS" -eq 0 ]; then
  pass "Aucune erreur frontend sur 10 minutes"
else
  warn "$FRONTEND_ERRORS ligne(s) d’erreur dans les logs frontend"
fi

echo
echo "============================================================"
echo "8. SYNTHÈSE"
echo "============================================================"

echo "PASS : $PASS"
echo "WARN : $WARN"
echo "FAIL : $FAIL"

ln -sfn "$(basename "$REPORT")" "$LATEST"

SUMMARY="$REPORT_DIR/summary-$STAMP.json"

python3 - "$SUMMARY" "$PASS" "$WARN" "$FAIL" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

output = Path(sys.argv[1])
passed = int(sys.argv[2])
warnings = int(sys.argv[3])
failed = int(sys.argv[4])

status = (
    "READY"
    if failed == 0
    else "NOT_READY"
)

payload = {
    "schema": "geocooling.rc1.runtime-validation.v1",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "status": status,
    "pass": passed,
    "warnings": warnings,
    "failures": failed,
    "hardware_commands_sent": False,
    "read_only": True,
}

output.write_text(
    json.dumps(payload, indent=2),
    encoding="utf-8",
)

print(json.dumps(payload, indent=2))
PY

echo
echo "Rapport : $REPORT"
echo "Résumé  : $SUMMARY"

if [ "$FAIL" -gt 0 ]; then
  echo
  echo "❌ GEOCOOLING RC1 NON PRÊT"
  exit 2
fi

echo
echo "============================================================"
echo " ✅ GEOCOOLING RC1 PRÊT POUR LES TESTS TERRAIN"
echo "============================================================"
