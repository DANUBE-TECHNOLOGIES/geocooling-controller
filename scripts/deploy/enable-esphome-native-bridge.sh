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
echo "===== BACKEND READINESS ====="
SBC_PORT="$(sed -nE 's/^SBC_API_PORT=(.*)$/\1/p' "$ENV_FILE" | tail -n1)"
SBC_PORT="${SBC_PORT:-8000}"

BACKEND_READY=false
for attempt in $(seq 1 30); do
  if curl -fsS --max-time 3 "http://127.0.0.1:${SBC_PORT}/health/live" >/dev/null 2>&1; then
    BACKEND_READY=true
    echo "Backend READY après ${attempt} tentative(s)."
    break
  fi
  sleep 2
done

if [[ "$BACKEND_READY" != "true" ]]; then
  echo "ERREUR: backend non prêt après 60 secondes." >&2
  docker compose ps backend esphome-bridge || true
  docker compose logs --tail=120 backend esphome-bridge 2>&1 \
    | sed -E 's/(noise_psk|NOISE_PSK|api_key)[^ ]*/\1=***MASQUE***/Ig' || true
  exit 1
fi

echo
echo "===== BRIDGE LOGS (clé jamais affichée) ====="
docker compose logs --tail=80 esphome-bridge 2>&1 \
  | sed -E 's/(noise_psk|NOISE_PSK|api_key)[^ ]*/\1=***MASQUE***/Ig'

echo
echo "===== CANONICAL SENSOR VALUES ====="
SENSORS_OK=false
for attempt in $(seq 1 30); do
  TMP="$(mktemp)"
  if curl -fsS --max-time 5 "http://127.0.0.1:${SBC_PORT}/sensors/latest" -o "$TMP" 2>/dev/null; then
    COUNT="$(python3 - "$TMP" <<'PY'
import json
import sys
from pathlib import Path

rows = json.loads(Path(sys.argv[1]).read_text())
wanted = {
    "gc_source_inlet",
    "gc_source_outlet",
    "gc_floor_supply",
    "gc_floor_return",
}
seen = {
    row.get("sensor_name")
    for row in rows
    if isinstance(row, dict) and row.get("sensor_name") in wanted
}
print(len(seen))
PY
)"
    if [[ "$COUNT" == "4" ]]; then
      python3 - "$TMP" <<'PY'
import json
import sys
from pathlib import Path

rows = json.loads(Path(sys.argv[1]).read_text())
wanted = [
    "gc_source_inlet",
    "gc_source_outlet",
    "gc_floor_supply",
    "gc_floor_return",
]
by_name = {row.get("sensor_name"): row for row in rows if isinstance(row, dict)}
for name in wanted:
    row = by_name[name]
    print(f"{name}: {row.get('value')} {row.get('unit')}  {row.get('measured_at')}")
PY
      SENSORS_OK=true
      rm -f "$TMP"
      break
    fi
  fi
  rm -f "$TMP"
  sleep 2
done

if [[ "$SENSORS_OK" != "true" ]]; then
  echo "ERREUR: les 4 sondes hydrauliques canoniques ne sont pas visibles après 60 secondes." >&2
  echo "Derniers logs bridge:" >&2
  docker compose logs --tail=160 esphome-bridge 2>&1 \
    | sed -E 's/(noise_psk|NOISE_PSK|api_key)[^ ]*/\1=***MASQUE***/Ig' || true
  exit 1
fi

echo
echo "Bridge ESPHome déployé en lecture seule."
echo "4/4 températures hydrauliques visibles dans /sensors/latest."
echo "Aucun flag d'armement/certification n'a été activé."
