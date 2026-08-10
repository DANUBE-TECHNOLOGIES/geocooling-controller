#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/opt/stacks/smart-building-controller}"
cd "$ROOT"

PORT="${SBC_API_PORT:-}"
if [[ -z "$PORT" && -f .env ]]; then
  PORT="$(sed -nE 's/^SBC_API_PORT=(.*)$/\1/p' .env | tail -n1)"
fi
PORT="${PORT:-8000}"
BASE="http://127.0.0.1:${PORT}"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

echo "============================================================"
echo " GEOCOOLING - PRECOOLING ADVISORY SHADOW"
echo " LECTURE SEULE - AUCUN ACTIONNEMENT MATERIEL"
echo "============================================================"

echo
echo "===== BACKEND ====="
curl -fsS --max-time 5 "$BASE/health/live"
echo

echo
echo "===== ADVISORY ====="
curl -fsS --max-time 20 \
  "$BASE/geocooling/rc3/weather-inertia/precooling-advisory" \
  -o "$TMP"

python3 - "$TMP" <<'PY'
import json, sys
from pathlib import Path

p=json.loads(Path(sys.argv[1]).read_text())
f=p.get("forecast") or {}
r=p.get("recommendation") or {}
s=p.get("safety") or {}
c=p.get("comfort") or {}

print("state=", p.get("state"))
print("reason=", p.get("reason"))
print("comfort_target_c=", c.get("target_temperature_c"))
print("comfort_max_c=", c.get("maximum_temperature_c"))
print("first_crossing_minutes=", f.get("first_limit_crossing_horizon_minutes"))
print("first_crossing_at=", f.get("first_limit_crossing_at"))
print("first_crossing_temperature_c=", f.get("first_limit_crossing_temperature_c"))
print("confidence_at_crossing=", f.get("confidence_at_crossing"))
print("minimum_confidence=", f.get("minimum_confidence"))
print("baseline_peak_temperature_c=", f.get("baseline_peak_temperature_c"))
print("recommended_scenario=", r.get("scenario"))
print("recommended_lead_minutes=", r.get("lead_minutes"))
print("recommended_start_minutes=", r.get("start_horizon_minutes"))
print("recommended_start_at=", r.get("start_at"))
print("predicted_temperature_with_cooling_c=", r.get("predicted_temperature_with_cooling_c"))
print("predicted_avoided_temperature_c=", r.get("predicted_avoided_temperature_c"))
print("advisory_only=", s.get("advisory_only"))
print("controller_authorized=", s.get("controller_authorized"))
print("controller_called=", s.get("controller_called"))
print("hardware_write=", s.get("hardware_write"))
print("mqtt_publish=", s.get("mqtt_publish"))
print("database_write=", s.get("database_write"))
print("promotion_to_controller_allowed=", s.get("promotion_to_controller_allowed"))

if s.get("advisory_only") is not True:
    raise SystemExit("ERREUR: advisory_only doit rester true")
for key in (
    "controller_authorized",
    "controller_called",
    "hardware_write",
    "mqtt_publish",
    "database_write",
    "promotion_to_controller_allowed",
):
    if bool(s.get(key)):
        raise SystemExit(f"ERREUR: invariant Shadow violé: {key}")
PY

echo
echo "============================================================"
echo " PRECOOLING ADVISORY VALIDE EN MODE SHADOW"
echo "============================================================"
