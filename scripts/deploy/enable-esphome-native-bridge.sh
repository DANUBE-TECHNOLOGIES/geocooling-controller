#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/opt/stacks/smart-building-controller}"
ESPHOME_SECRETS="${ESPHOME_SECRETS:-/opt/GeoCooling-Controller/esphome/secrets.yaml}"
ENV_FILE="$ROOT/.env"

cd "$ROOT"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERREUR: .env introuvable: $ENV_FILE" >&2
  exit 1
fi

if [[ ! -f "$ESPHOME_SECRETS" ]]; then
  echo "ERREUR: secrets ESPHome introuvables: $ESPHOME_SECRETS" >&2
  exit 1
fi

API_KEY="$({
  sed -nE 's/^[[:space:]]*sbc_api_key:[[:space:]]*(.*)$/\1/p' "$ESPHOME_SECRETS" | head -n1
} || true)"
API_KEY="${API_KEY%\"}"
API_KEY="${API_KEY#\"}"
API_KEY="${API_KEY%\'}"
API_KEY="${API_KEY#\'}"

if [[ -z "$API_KEY" ]]; then
  echo "ERREUR: sbc_api_key absent de $ESPHOME_SECRETS" >&2
  exit 1
fi

BACKUP="$ENV_FILE.pre-esphome-bridge-$(date +%Y%m%d-%H%M%S)"
cp -a "$ENV_FILE" "$BACKUP"
chmod 600 "$BACKUP" "$ENV_FILE" || true

export API_KEY ENV_FILE
python3 - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["ENV_FILE"])
values = {
    "ESPHOME_BRIDGE_HOST": "192.168.10.105",
    "ESPHOME_BRIDGE_PORT": "6053",
    "ESPHOME_BRIDGE_NOISE_PSK": os.environ["API_KEY"],
    "ESPHOME_BRIDGE_RECONNECT_SECONDS": "5",
    "GEOCOOLING_SOURCE_INLET_SENSOR": "gc_source_inlet",
    "GEOCOOLING_SOURCE_OUTLET_SENSOR": "gc_source_outlet",
    "GEOCOOLING_FLOOR_SUPPLY_SENSOR": "gc_floor_supply",
    "GEOCOOLING_FLOOR_RETURN_SENSOR": "gc_floor_return",
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

unset API_KEY

echo "Configuration locale mise à jour (clé masquée)."
echo "Sauvegarde: $BACKUP"

echo
echo "===== SAFE FLAGS (doivent rester false) ====="
grep -E '^(GEOCOOLING_HARDWARE_ARMED|GEOCOOLING_HARDWARE_SEQUENCE_ENABLED|GEOCOOLING_AUTOPILOT_ENABLED|GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER|GEOCOOLING_SENSOR_IDENTIFICATION_CONFIRMED|GEOCOOLING_FIELD_CERTIFICATION_CONFIRMED)=' "$ENV_FILE" || true

echo
echo "===== BUILD / START ====="
docker compose build backend esphome-bridge
docker compose up -d backend esphome-bridge

echo
echo "===== SERVICES ====="
docker compose ps backend esphome-bridge

echo
echo "===== BRIDGE LOGS (clé jamais affichée) ====="
docker compose logs --tail=60 esphome-bridge 2>&1 | sed -E 's/(noise_psk|NOISE_PSK|api_key)[^ ]*/\1=***MASQUE***/Ig'

echo
echo "===== CANONICAL SENSOR VALUES ====="
sleep 12
curl -fsS http://127.0.0.1:${SBC_API_PORT:-8000}/sensors/latest \
  | python3 -c '
import json,sys
rows=json.load(sys.stdin)
wanted={"gc_source_inlet","gc_source_outlet","gc_floor_supply","gc_floor_return"}
for row in rows:
    if row.get("sensor_name") in wanted:
        print(f"{row.get(chr(115)+chr(101)+chr(110)+chr(115)+chr(111)+chr(114)+chr(95)+chr(110)+chr(97)+chr(109)+chr(101))}: {row.get(chr(118)+chr(97)+chr(108)+chr(117)+chr(101))} {row.get(chr(117)+chr(110)+chr(105)+chr(116))}  {row.get(chr(109)+chr(101)+chr(97)+chr(115)+chr(117)+chr(114)+chr(101)+chr(100)+chr(95)+chr(97)+chr(116))}")
'

echo
echo "Bridge ESPHome déployé en lecture seule."
echo "Aucun flag d'armement/certification n'a été activé."
