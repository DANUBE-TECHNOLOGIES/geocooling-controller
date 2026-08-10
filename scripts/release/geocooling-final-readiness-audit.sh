#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${GEOCOOLING_INTERNAL_API_BASE_URL:-http://127.0.0.1:8000}"
REPO="${REPO:-/opt/stacks/smart-building-controller}"

json_get() {
  curl -fsS --max-time 15 "$BASE_URL$1"
}

json_field() {
  python3 -c "import json,sys; d=json.load(sys.stdin); v=$1; print(v if v is not None else '')"
}

fail=0

printf '%s\n' '============================================================'
printf '%s\n' ' GEOCOOLING - FINAL READINESS AUDIT'
printf '%s\n' ' LECTURE SEULE - AUCUN ACTIONNEMENT MATERIEL'
printf '%s\n' '============================================================'

echo
echo '===== BACKEND ====='
if json_get /health/live >/dev/null; then
  echo 'backend=READY'
else
  echo 'backend=FAILED'
  fail=1
fi

echo
echo '===== WEATHER ====='
WEATHER="$(json_get /geocooling/weather)"
echo "$WEATHER" | python3 -c '
import json,sys
d=json.load(sys.stdin)
loc=d.get("location") or {}
forecast=d.get("forecast") or []
print("provider=", d.get("provider"))
print("location=", loc.get("name"), loc.get("postal_code"), loc.get("country"))
print("forecast_points=", len(forecast) if isinstance(forecast,list) else "?")
' || fail=1

echo
echo '===== WEATHER / INERTIA ====='
PRED="$(json_get /geocooling/rc3/weather-inertia/live)"
echo "$PRED" | python3 -c '
import json,sys
d=json.load(sys.stdin)
w=d.get("weather_input") or {}
s=d.get("safety") or {}
print("weather_mode=", w.get("mode"))
print("weather_degraded=", w.get("degraded"))
print("forecast_points=", w.get("forecast_points"))
print("hardware_write=", s.get("hardware_write"))
if w.get("mode") != "HOURLY_FORECAST" or w.get("degraded") is not False or s.get("hardware_write") is not False:
    raise SystemExit(1)
' || fail=1

echo
echo '===== TELEMETRY ====='
TELEMETRY="$(json_get /geocooling/brain-v2/integration/home-assistant/telemetry-health)"
echo "$TELEMETRY" | python3 -c '
import json,sys
d=json.load(sys.stdin)
print("ready=", d.get("ready"))
print("required_role_count=", d.get("required_role_count"))
print("ready_required_role_count=", d.get("ready_required_role_count"))
print("surface_reference_mode=", d.get("surface_reference_mode"))
print("flow_required=", d.get("flow_required"))
if d.get("ready") is not True or d.get("required_role_count") != 5:
    raise SystemExit(1)
' || fail=1

echo
echo '===== DECISION CONTEXT ====='
CONTEXT="$(json_get /geocooling/decision-context/live)"
echo "$CONTEXT" | python3 -c '
import json,sys
d=json.load(sys.stdin)
m=d.get("measurements") or {}
q=d.get("quality") or {}
print("indoor_temperature_c=", m.get("indoor_temperature_c"))
print("indoor_humidity_pct=", m.get("indoor_humidity_pct"))
print("floor_surface_temperature_c=", m.get("floor_surface_temperature_c"))
print("floor_supply_temperature_c=", m.get("floor_supply_temperature_c"))
print("floor_return_temperature_c=", m.get("floor_return_temperature_c"))
print("source_in_temperature_c=", m.get("source_in_temperature_c"))
print("source_out_temperature_c=", m.get("source_out_temperature_c"))
print("sensor_quality=", q.get("sensors"))
print("blocking=", d.get("blocking"))
' || fail=1

echo
echo '===== PRECOOLING SHADOW ====='
ADVISORY="$(json_get /geocooling/rc3/weather-inertia/precooling-advisory)"
echo "$ADVISORY" | python3 -c '
import json,sys
d=json.load(sys.stdin)
s=d.get("safety") or {}
print("state=", d.get("state"))
print("advisory_only=", s.get("advisory_only"))
print("controller_authorized=", s.get("controller_authorized"))
print("hardware_write=", s.get("hardware_write"))
print("promotion_to_controller_allowed=", s.get("promotion_to_controller_allowed"))
if not (s.get("advisory_only") is True and s.get("controller_authorized") is False and s.get("hardware_write") is False and s.get("promotion_to_controller_allowed") is False):
    raise SystemExit(1)
' || fail=1

echo
echo '===== COMMISSIONING ====='
COMMISSIONING="$(json_get /geocooling/brain-v2/integration/home-assistant/commissioning-readiness)"
echo "$COMMISSIONING" | python3 -c '
import json,sys
d=json.load(sys.stdin)
print("state=", d.get("state"))
print("telemetry_ready=", d.get("telemetry_ready"))
print("physical_identification_confirmed=", d.get("physical_identification_confirmed"))
print("field_certification_confirmed=", d.get("field_certification_confirmed"))
' || fail=1

echo
echo '===== RELEASE ====='
RELEASE="$(json_get /geocooling/brain-v2/integration/home-assistant/release-readiness)"
echo "$RELEASE" | python3 -c '
import json,sys
d=json.load(sys.stdin)
print("state=", d.get("state"))
print("deployment_ready=", d.get("deployment_ready"))
print("runtime_safe_defaults=", d.get("runtime_safe_defaults"))
print("active_dangerous_flags=", d.get("active_dangerous_flags"))
print("blockers=", d.get("blockers"))
' || fail=1

echo
echo '===== SAFE FLAGS ====='
if [ -f "$REPO/.env" ]; then
  grep -E '^(GEOCOOLING_HARDWARE_ARMED|GEOCOOLING_HARDWARE_SEQUENCE_ENABLED|GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER|GEOCOOLING_AUTOPILOT_ENABLED)=' "$REPO/.env" || true
else
  echo '.env absent'
fi

COMMISSIONING_STATE="$(printf '%s' "$COMMISSIONING" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("state", "UNKNOWN"))')"
DEPLOYMENT_READY="$(printf '%s' "$RELEASE" | python3 -c 'import json,sys; print(str(json.load(sys.stdin).get("deployment_ready", False)).lower())')"

echo
echo '============================================================'
if [ "$fail" -ne 0 ]; then
  echo ' FINAL_STATE=SOFTWARE_CHECK_REQUIRED'
  echo ' Une ou plusieurs vérifications logicielles ont échoué.'
elif [ "$DEPLOYMENT_READY" = 'true' ]; then
  echo ' FINAL_STATE=READY_FOR_DEPLOYMENT'
  echo ' Commissioning et defaults sûrs validés.'
elif [ "$COMMISSIONING_STATE" = 'FIELD_CERTIFICATION_REQUIRED' ]; then
  echo ' FINAL_STATE=SOFTWARE_COMPLETE_FIELD_CERTIFICATION_REQUIRED'
  echo ' Logiciel prêt. Reste uniquement la certification terrain EV / M11 / M13.'
else
  echo " FINAL_STATE=$COMMISSIONING_STATE"
  echo ' Consulter les blocs COMMISSIONING et RELEASE.'
fi
echo ' AUCUN ACTIONNEUR N A ETE COMMANDE'
echo '============================================================'

exit "$fail"
