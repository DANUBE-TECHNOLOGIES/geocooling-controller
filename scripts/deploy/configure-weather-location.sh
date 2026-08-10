#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/opt/stacks/smart-building-controller}"
ENV_FILE="$ROOT/.env"
cd "$ROOT"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERREUR: .env introuvable: $ENV_FILE" >&2
  exit 1
fi

BACKUP="$ENV_FILE.pre-weather-location-$(date +%Y%m%d-%H%M%S)"
cp -a "$ENV_FILE" "$BACKUP"
chmod 600 "$BACKUP" "$ENV_FILE" || true

export ENV_FILE
python3 - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["ENV_FILE"])
values = {
    "GEOCOOLING_WEATHER_LOCATION": "Chevannes",
    "GEOCOOLING_WEATHER_POSTAL_CODE": "45210",
    "GEOCOOLING_WEATHER_COUNTRY_CODE": "FR",
    "GEOCOOLING_WEATHER_LATITUDE": "48.1348",
    "GEOCOOLING_WEATHER_LONGITUDE": "2.8606",
    "GEOCOOLING_WEATHER_TIMEZONE": "Europe/Paris",
    "GEOCOOLING_WEATHER_FORECAST_HOURS": "48",
    "GEOCOOLING_WEATHER_FORECAST_DAYS": "7",
    "GEOCOOLING_WEATHER_CACHE_SECONDS": "900",
    "GEOCOOLING_WEATHER_TIMEOUT_SECONDS": "12",
}

lines = path.read_text().splitlines()
seen = set()
out = []
for line in lines:
    if "=" in line and not line.lstrip().startswith("#"):
        key = line.split("=", 1)[0].strip()
        if key in values:
            out.append(f"{key}={values[key]}")
            seen.add(key)
            continue
    out.append(line)

if out and out[-1] != "":
    out.append("")
for key, value in values.items():
    if key not in seen:
        out.append(f"{key}={value}")

path.write_text("\n".join(out) + "\n")
PY

echo "Localisation météo GeoCooling configurée pour Chevannes 45210."
echo "Sauvegarde: $BACKUP"

echo
echo "===== WEATHER CONFIG ====="
grep -E '^GEOCOOLING_WEATHER_(LOCATION|POSTAL_CODE|COUNTRY_CODE|LATITUDE|LONGITUDE|TIMEZONE|FORECAST_HOURS|FORECAST_DAYS|CACHE_SECONDS|TIMEOUT_SECONDS)=' "$ENV_FILE" || true

echo
echo "===== SAFE FLAGS (lecture uniquement) ====="
grep -E '^(GEOCOOLING_HARDWARE_ARMED|GEOCOOLING_HARDWARE_SEQUENCE_ENABLED|GEOCOOLING_AUTOPILOT_ENABLED|GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER|GEOCOOLING_COMMISSIONING_TESTS_ENABLED)=' "$ENV_FILE" || true

echo
echo "===== RECREATE BACKEND ONLY ====="
docker compose up -d --no-deps --force-recreate backend

PORT="$(sed -nE 's/^SBC_API_PORT=(.*)$/\1/p' "$ENV_FILE" | tail -n1)"
PORT="${PORT:-8000}"
BASE="http://127.0.0.1:${PORT}"

for attempt in $(seq 1 60); do
  if curl -fsS --max-time 3 "$BASE/health/live" >/dev/null 2>&1; then
    echo "Backend READY après ${attempt}s."
    break
  fi
  if [[ "$attempt" == "60" ]]; then
    echo "ERREUR: backend non prêt après 60 secondes." >&2
    exit 1
  fi
  sleep 1
done

echo
echo "===== WEATHER LOCATION CHECK ====="
curl -fsS --max-time 20 "$BASE/geocooling/weather?refresh=true" | python3 -c '
import json,sys
p=json.load(sys.stdin)
loc=p.get("location") or {}
print("provider=", p.get("provider"))
print("location=", loc.get("name"), loc.get("postal_code"), loc.get("country"))
print("latitude=", loc.get("latitude"))
print("longitude=", loc.get("longitude"))
print("forecast_hours=", p.get("forecast_hours"))
print("forecast_days=", p.get("forecast_days"))
if abs(float(loc.get("latitude")) - 48.1348) > 0.01:
    raise SystemExit("ERREUR: latitude météo inattendue")
if abs(float(loc.get("longitude")) - 2.8606) > 0.01:
    raise SystemExit("ERREUR: longitude météo inattendue")
'

echo
echo "Météo Chevannes configurée sans actionnement matériel."
