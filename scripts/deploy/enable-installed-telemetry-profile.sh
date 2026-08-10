#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/opt/stacks/smart-building-controller}"
ENV_FILE="$ROOT/.env"

cd "$ROOT"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERREUR: .env introuvable: $ENV_FILE" >&2
  exit 1
fi

BACKUP="$ENV_FILE.pre-installed-telemetry-profile-$(date +%Y%m%d-%H%M%S)"
cp -a "$ENV_FILE" "$BACKUP"
chmod 600 "$BACKUP" "$ENV_FILE" || true

export ENV_FILE
python3 - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["ENV_FILE"])
values = {
    "GEOCOOLING_SURFACE_REFERENCE_MODE": "floor_loop_estimate",
    "GEOCOOLING_SURFACE_ESTIMATION_BIAS_C": "-0.5",
    "GEOCOOLING_FLOW_REQUIRED": "false",
    "GEOCOOLING_FLOOR_SUPPLY_SENSOR": "gc_floor_supply",
    "GEOCOOLING_FLOOR_RETURN_SENSOR": "gc_floor_return",
    "GEOCOOLING_SOURCE_INLET_SENSOR": "gc_source_inlet",
    "GEOCOOLING_SOURCE_OUTLET_SENSOR": "gc_source_outlet",
    "GEOCOOLING_FLOW_SENSOR": "",
    "GEOCOOLING_SURFACE_SENSOR": "",
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

echo "Profil télémétrique installé activé."
echo "Sauvegarde: $BACKUP"

echo
echo "===== PROFIL ====="
grep -E '^(GEOCOOLING_SURFACE_REFERENCE_MODE|GEOCOOLING_SURFACE_ESTIMATION_BIAS_C|GEOCOOLING_FLOW_REQUIRED|GEOCOOLING_(FLOOR_SUPPLY|FLOOR_RETURN|SOURCE_INLET|SOURCE_OUTLET|SURFACE|FLOW)_SENSOR)=' "$ENV_FILE" || true

echo
echo "===== SAFE FLAGS (aucune modification par ce script) ====="
grep -E '^(GEOCOOLING_HARDWARE_ARMED|GEOCOOLING_HARDWARE_SEQUENCE_ENABLED|GEOCOOLING_AUTOPILOT_ENABLED|GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER|GEOCOOLING_SENSOR_IDENTIFICATION_CONFIRMED|GEOCOOLING_FIELD_CERTIFICATION_CONFIRMED)=' "$ENV_FILE" || true

echo
echo "===== RESTART BACKEND ONLY ====="
docker compose up -d --no-deps --force-recreate backend

SBC_PORT="$(sed -nE 's/^SBC_API_PORT=(.*)$/\1/p' "$ENV_FILE" | tail -n1)"
SBC_PORT="${SBC_PORT:-8000}"

READY=false
for attempt in $(seq 1 30); do
  if curl -fsS --max-time 3 "http://127.0.0.1:${SBC_PORT}/health/live" >/dev/null 2>&1; then
    READY=true
    echo "Backend READY après ${attempt} tentative(s)."
    break
  fi
  sleep 2
done

if [[ "$READY" != "true" ]]; then
  echo "ERREUR: backend non prêt après 60 secondes." >&2
  docker compose logs --tail=120 backend >&2 || true
  exit 1
fi

echo
echo "===== 4 SONDES PHYSIQUES ====="
curl -fsS "http://127.0.0.1:${SBC_PORT}/sensors/latest" | python3 -c '
import json,sys
rows=json.load(sys.stdin)
wanted=["gc_source_inlet","gc_source_outlet","gc_floor_supply","gc_floor_return"]
by={r.get("sensor_name"):r for r in rows if isinstance(r,dict)}
missing=[name for name in wanted if name not in by]
for name in wanted:
    r=by.get(name)
    if r:
        print(f"{name}: {r.get(chr(118)+chr(97)+chr(108)+chr(117)+chr(101))} {r.get(chr(117)+chr(110)+chr(105)+chr(116))}  {r.get(chr(109)+chr(101)+chr(97)+chr(115)+chr(117)+chr(114)+chr(101)+chr(100)+chr(95)+chr(97)+chr(116))}")
if missing:
    print("MANQUANTES:", ", ".join(missing), file=sys.stderr)
    raise SystemExit(2)
'

echo
echo "===== TELEMETRY HEALTH ====="
curl -fsS "http://127.0.0.1:${SBC_PORT}/geocooling/brain-v2/integration/home-assistant/telemetry-health" | python3 -m json.tool

echo
echo "===== COMMISSIONING READINESS ====="
curl -fsS "http://127.0.0.1:${SBC_PORT}/geocooling/brain-v2/integration/home-assistant/commissioning-readiness" | python3 -m json.tool

echo
echo "===== RELEASE READINESS ====="
curl -fsS "http://127.0.0.1:${SBC_PORT}/geocooling/brain-v2/integration/home-assistant/release-readiness" | python3 -m json.tool

echo
echo "Profil appliqué sans armement matériel."
echo "Le débit reste optionnel et aucune valeur n'est inventée."
echo "La surface de sécurité est dérivée de départ+retour avec biais conservateur -0.5 °C."
