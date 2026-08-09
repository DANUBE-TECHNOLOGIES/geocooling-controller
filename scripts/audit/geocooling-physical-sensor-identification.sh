#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${GEOCOOLING_LOCAL_API_URL:-http://127.0.0.1:8000}"
ENDPOINT="${BASE_URL%/}/geocooling/brain-v2/integration/home-assistant/telemetry-health"

printf '%s\n' "============================================================"
printf '%s\n' " GEOCOOLING - MATRICE PASSIVE D'IDENTIFICATION DES SONDES"
printf '%s\n' " AUCUNE PUBLICATION MQTT / AUCUNE COMMANDE MODBUS"
printf '%s\n' "============================================================"

payload="$(curl -fsS --max-time 10 "$ENDPOINT")"

python3 - "$payload" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])

print()
print("===== GARDE-FOUS =====")
print(f"read_only                     : {payload.get('read_only')}")
print(f"hardware_touched              : {payload.get('hardware_touched')}")
print(f"mqtt_publish                  : {payload.get('mqtt_publish')}")
print(f"database_write                : {payload.get('database_write')}")
print(f"auto_assignment_allowed       : {payload.get('auto_assignment_allowed')}")
print(f"physical_confirmation_required: {payload.get('physical_confirmation_required')}")

print()
print("===== ETAT GLOBAL =====")
print(f"upstream_state         : {payload.get('upstream_state')}")
print(f"ready                  : {payload.get('ready')}")
print(f"fail_closed            : {payload.get('fail_closed')}")
print(f"configured_role_count  : {payload.get('configured_role_count')}")
print(f"candidate_sensor_count : {payload.get('hydraulic_candidate_count')}")
print(f"stale_seconds          : {payload.get('stale_seconds')}")

print()
print("===== ROLES / VARIABLES =====")
for role_name, role in (payload.get("roles") or {}).items():
    print(
        f"{role_name:16} "
        f"state={str(role.get('state')):14} "
        f"env={str(role.get('env_var')):38} "
        f"sensor={role.get('sensor_name') or '-'}"
    )

print()
print("===== CANDIDATS OBSERVES =====")
candidates = payload.get("candidate_sensors") or []
if not candidates:
    print("Aucun candidat hydraulique observe.")
else:
    for candidate in candidates:
        print(f"sensor_name : {candidate.get('sensor_name')}")
        print(f"metrics     : {', '.join(candidate.get('metrics') or []) or '-'}")
        print(f"mqtt_topics : {', '.join(candidate.get('mqtt_topics') or []) or '-'}")
        print("physical    : A CONFIRMER")
        print()

print("===== REGLE =====")
print("Ne jamais affecter automatiquement un candidat a un role.")
print("Confirmer physiquement la sonde avant toute modification de .env.")
PY
