#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/opt/stacks/smart-building-controller}"
ENV_FILE="$ROOT/.env"
API_BASE="${API_BASE:-http://127.0.0.1:8000}"

cd "$ROOT"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERREUR: .env introuvable: $ENV_FILE" >&2
  exit 1
fi

backup="$ENV_FILE.pre-sensor-identification-$(date +%Y%m%d-%H%M%S)"
cp -a "$ENV_FILE" "$backup"
chmod 600 "$backup" "$ENV_FILE" || true

health_tmp="$(mktemp)"
trap 'rm -f "$health_tmp"' EXIT

curl -fsS "$API_BASE/geocooling/brain-v2/integration/home-assistant/telemetry-health" -o "$health_tmp"

python3 - "$health_tmp" <<'PY'
import json, sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
required = report.get("required_roles") or []
roles = report.get("roles") or {}
if report.get("ready") is not True:
    raise SystemExit("ERREUR: télémétrie requise non prête; confirmation refusée")
if report.get("required_role_count") != 5:
    raise SystemExit(f"ERREUR: required_role_count inattendu: {report.get('required_role_count')}")
if report.get("surface_reference_mode") != "floor_loop_estimate":
    raise SystemExit("ERREUR: mode surface attendu floor_loop_estimate")
if report.get("flow_required") is not False:
    raise SystemExit("ERREUR: le débit doit rester optionnel")
expected = {"surface", "floor_supply", "floor_return", "source_inlet", "source_outlet"}
if set(required) != expected:
    raise SystemExit(f"ERREUR: rôles requis inattendus: {required}")
for role in expected:
    item = roles.get(role) or {}
    if item.get("ready") is not True:
        raise SystemExit(f"ERREUR: rôle requis non prêt: {role}")
print("Télémétrie 5/5 validée avant confirmation.")
PY

export ENV_FILE
python3 - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["ENV_FILE"])
key = "GEOCOOLING_SENSOR_IDENTIFICATION_CONFIRMED"
value = "true"
lines = path.read_text().splitlines()
out = []
seen = False
for line in lines:
    if "=" in line and not line.lstrip().startswith("#"):
        current = line.split("=", 1)[0].strip()
        if current == key:
            out.append(f"{key}={value}")
            seen = True
            continue
    out.append(line)
if not seen:
    if out and out[-1] != "":
        out.append("")
    out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n")
PY

echo "Confirmation d'identification enregistrée. Sauvegarde: $backup"

echo
echo "===== SAFE FLAGS ====="
grep -E '^(GEOCOOLING_HARDWARE_ARMED|GEOCOOLING_HARDWARE_SEQUENCE_ENABLED|GEOCOOLING_AUTOPILOT_ENABLED|GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER|GEOCOOLING_SENSOR_IDENTIFICATION_CONFIRMED|GEOCOOLING_FIELD_CERTIFICATION_CONFIRMED)=' "$ENV_FILE" || true

echo
echo "===== RECREATE BACKEND ONLY ====="
docker compose up -d --force-recreate backend

for i in $(seq 1 60); do
  if curl -fsS "$API_BASE/health/live" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo
echo "===== COMMISSIONING READINESS ====="
curl -fsS "$API_BASE/geocooling/brain-v2/integration/home-assistant/commissioning-readiness" | python3 -m json.tool

echo
echo "===== RELEASE READINESS ====="
curl -fsS "$API_BASE/geocooling/brain-v2/integration/home-assistant/release-readiness" | python3 -m json.tool

echo
echo "Identification confirmée sans armement matériel."
