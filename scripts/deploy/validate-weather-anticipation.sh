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
TMP_WEATHER="$(mktemp)"
TMP_PREDICTION="$(mktemp)"
trap 'rm -f "$TMP_WEATHER" "$TMP_PREDICTION"' EXIT

echo "============================================================"
echo " GEOCOOLING - VALIDATION METEO / ANTICIPATION"
echo " LECTURE SEULE - AUCUN ACTIONNEMENT MATERIEL"
echo "============================================================"

echo
echo "===== BACKEND ====="
curl -fsS --max-time 5 "$BASE/health/live"
echo

echo
echo "===== WEATHER SERVICE ====="
curl -fsS --max-time 20 "$BASE/geocooling/weather?refresh=true" -o "$TMP_WEATHER"
python3 - "$TMP_WEATHER" <<'PY'
import json, sys
from pathlib import Path
p=json.loads(Path(sys.argv[1]).read_text())
print("provider=", p.get("provider"))
loc=p.get("location") or {}
print("location=", loc.get("name"), loc.get("postal_code"), loc.get("country"))
print("forecast_hours=", p.get("forecast_hours"))
print("forecast_days=", p.get("forecast_days"))
cur=p.get("current") or {}
print("current_temperature_c=", cur.get("temperature_2m"))
print("current_humidity_pct=", cur.get("relative_humidity_2m"))
print("current_dew_point_c=", cur.get("dew_point_2m"))
summary=p.get("summary") or {}
print("temperature_min_24h=", summary.get("temperature_min_24h"))
print("temperature_max_24h=", summary.get("temperature_max_24h"))
print("solar_radiation_peak_24h=", summary.get("solar_radiation_peak_24h"))
rows=p.get("hourly") or []
if not isinstance(rows, list) or len(rows) < 24:
    raise SystemExit("ERREUR: prévision horaire Open-Meteo insuffisante")
PY

echo
echo "===== WEATHER HEALTH ====="
curl -fsS --max-time 5 "$BASE/geocooling/weather/health" | python3 -m json.tool

echo
echo "===== WEATHER / INERTIA LIVE ====="
curl -fsS --max-time 15 "$BASE/geocooling/rc3/weather-inertia/live" -o "$TMP_PREDICTION"
python3 - "$TMP_PREDICTION" <<'PY'
import json, sys
from pathlib import Path
p=json.loads(Path(sys.argv[1]).read_text())
w=p.get("weather_input") or {}
s=p.get("safety") or {}
sources=p.get("sources") or {}
print("weather_source=", sources.get("weather"))
print("weather_mode=", w.get("mode"))
print("weather_degraded=", w.get("degraded"))
print("source_shape=", w.get("source_shape"))
print("forecast_points=", w.get("forecast_points"))
print("forecast_horizon_hours=", w.get("forecast_horizon_hours"))
print("controller_authorized=", s.get("controller_authorized"))
print("hardware_write=", s.get("hardware_write"))
print("mqtt_publish=", s.get("mqtt_publish"))
print("database_write=", s.get("database_write"))

if w.get("mode") != "HOURLY_FORECAST" or w.get("degraded") is not False:
    raise SystemExit("ERREUR: anticipation météo en mode dégradé")
if int(w.get("forecast_horizon_hours") or 0) < 24:
    raise SystemExit("ERREUR: horizon météo inférieur à 24 h")
if sources.get("weather") != "/geocooling/weather":
    raise SystemExit("ERREUR: le prédicteur n'utilise pas /geocooling/weather")
if any(bool(s.get(key)) for key in ("controller_authorized", "controller_called", "hardware_write", "mqtt_publish", "database_write")):
    raise SystemExit("ERREUR: invariant read-only météo violé")

trajectories=p.get("trajectories") or []
for item in trajectories:
    pts=item.get("points") or []
    last=pts[-1] if pts else {}
    print(
        "trajectory=", item.get("scenario"),
        "t48h=", last.get("predicted_indoor_temperature_c"),
        "outside48h=", last.get("outdoor_temperature_c"),
        "confidence=", last.get("confidence"),
        "uncertainty_c=", last.get("uncertainty_c"),
    )
PY

echo
echo "============================================================"
echo " METEO / ANTICIPATION VALIDEE EN LECTURE SEULE"
echo "============================================================"
