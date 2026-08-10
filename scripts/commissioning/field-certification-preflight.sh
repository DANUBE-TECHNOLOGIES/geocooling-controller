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
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "============================================================"
echo " GEOCOOLING - PREFLIGHT CERTIFICATION TERRAIN"
echo " LECTURE SEULE - AUCUNE COMMANDE EV / M11 / M13"
echo "============================================================"

curl -fsS --max-time 5 "$BASE/health/live" >/dev/null
curl -fsS --max-time 5 "$BASE/geocooling/brain-v2/integration/home-assistant/commissioning-readiness" -o "$TMP/commissioning.json"
curl -fsS --max-time 5 "$BASE/geocooling/brain-v2/integration/home-assistant/release-readiness" -o "$TMP/release.json"
curl -fsS --max-time 5 "$BASE/geocooling/device" -o "$TMP/device.json"
curl -fsS --max-time 5 "$BASE/geocooling/commissioning/tests" -o "$TMP/tests.json"

python3 - "$TMP" <<'PY'
import json, sys
from pathlib import Path
root=Path(sys.argv[1])
commissioning=json.loads((root/'commissioning.json').read_text())
release=json.loads((root/'release.json').read_text())
device=json.loads((root/'device.json').read_text())
tests=json.loads((root/'tests.json').read_text())

telemetry=commissioning.get('telemetry_health') or {}
flags=release.get('runtime_flags') or {}
policy=release.get('activation_policy') or {}
active=tests.get('active_test') or tests.get('active')

print('commissioning_state=', commissioning.get('state'))
print('telemetry_ready=', commissioning.get('telemetry_ready'))
print('physical_identification_confirmed=', commissioning.get('physical_identification_confirmed'))
print('field_certification_confirmed=', commissioning.get('field_certification_confirmed'))
print('required_roles=', telemetry.get('required_role_count'))
print('configured_required_roles=', telemetry.get('configured_required_role_count'))
print('device_connected=', device.get('connected'))
print('device_ready=', device.get('ready'))
print('commissioning_tests_allowed_by_policy=', policy.get('commissioning_tests_allowed'))
print('active_test=', bool(active))
for key,value in flags.items():
    print(f'{key}={value}')

errors=[]
if commissioning.get('state') != 'FIELD_CERTIFICATION_REQUIRED':
    errors.append('commissioning state must be FIELD_CERTIFICATION_REQUIRED')
if commissioning.get('telemetry_ready') is not True:
    errors.append('telemetry must be ready')
if commissioning.get('physical_identification_confirmed') is not True:
    errors.append('sensor identification must be confirmed')
if commissioning.get('field_certification_confirmed') is True:
    errors.append('field certification is already confirmed')
if telemetry.get('required_role_count') != 5 or telemetry.get('configured_required_role_count') != 5:
    errors.append('installed telemetry profile must remain 5/5')
if policy.get('commissioning_tests_allowed') is not True:
    errors.append('activation policy does not allow commissioning tests')
if active:
    errors.append('a commissioning test is already active')
for key in ('hardware_armed','hardware_sequence_enabled','autopilot_enabled','autopilot_allow_real_driver'):
    if flags.get(key) is True:
        errors.append(f'{key} must be false during read-only preflight')

if errors:
    print('\nPREFLIGHT=BLOCKED')
    for error in errors:
        print('BLOCKER:', error)
    raise SystemExit(1)

print('\nPREFLIGHT=READY_FOR_PHYSICAL_WIRING_CHECK')
print('No actuator was commanded by this script.')
print('After EV/M11/M13 are physically connected, perform the timed commissioning tests separately.')
PY

echo "============================================================"
echo " FIN PREFLIGHT - AUCUN ACTIONNEUR COMMANDE"
echo "============================================================"
