#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8000}"

printf '%s\n' "============================================================"
printf '%s\n' " GEOCOOLING - TELEMETRY MAPPING AUDIT"
printf '%s\n' " PASSIVE / READ-ONLY / NO RELAY COMMAND"
printf '%s\n' "============================================================"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

if ! curl -fsS --max-time 10 "$API_BASE/sensors/latest" -o "$TMP"; then
  echo "ERROR: cannot read $API_BASE/sensors/latest"
  exit 1
fi

python3 - "$TMP" <<'PY'
import json
import sys
from collections import defaultdict
from pathlib import Path

rows = json.loads(Path(sys.argv[1]).read_text())
if not isinstance(rows, list):
    raise SystemExit("Unexpected /sensors/latest payload")

by_sensor = defaultdict(dict)
for row in rows:
    if not isinstance(row, dict):
        continue
    sensor = str(row.get("sensor_name") or "").strip()
    metric = str(row.get("metric") or "").strip()
    if not sensor or not metric:
        continue
    by_sensor[sensor][metric] = {
        "value": row.get("value"),
        "unit": row.get("unit"),
        "measured_at": row.get("measured_at"),
        "mqtt_topic": row.get("mqtt_topic"),
    }

print("\n===== SENSORS OBSERVED =====")
for sensor in sorted(by_sensor):
    metrics = by_sensor[sensor]
    print(f"\n{sensor}")
    for metric in sorted(metrics):
        item = metrics[metric]
        print(
            f"  {metric:14} = {item['value']!s:10} "
            f"{item['unit'] or '':6} topic={item['mqtt_topic']}"
        )

print("\n===== CANDIDATES FOR GEOCOOLING =====")
temperature_sensors = [
    name for name, metrics in by_sensor.items()
    if "temperature" in metrics
]
flow_sensors = [
    name for name, metrics in by_sensor.items()
    if "flow" in metrics
]

roles = [
    ("GEOCOOLING_SURFACE_SENSOR", ("surface", "sol", "floor_surface", "plancher_surface")),
    ("GEOCOOLING_FLOOR_SUPPLY_SENSOR", ("depart", "supply", "aller", "plancher_depart", "floor_supply")),
    ("GEOCOOLING_FLOOR_RETURN_SENSOR", ("retour", "return", "plancher_retour", "floor_return")),
    ("GEOCOOLING_SOURCE_INLET_SENSOR", ("source_in", "inlet", "nappe_in", "source_entree", "source_entry")),
    ("GEOCOOLING_SOURCE_OUTLET_SENSOR", ("source_out", "outlet", "nappe_out", "source_sortie", "source_exit")),
]

for env_name, words in roles:
    matches = [
        sensor for sensor in temperature_sensors
        if any(word in sensor.lower() for word in words)
    ]
    print(f"{env_name}:")
    if matches:
        for sensor in sorted(matches):
            print(f"  candidate: {sensor}")
    else:
        print("  no unambiguous candidate by name")

print("GEOCOOLING_FLOW_SENSOR:")
if flow_sensors:
    for sensor in sorted(flow_sensors):
        print(f"  candidate: {sensor}")
else:
    print("  no flow metric observed")

print("\n===== SAFETY NOTE =====")
print("Do not auto-assign hydraulic roles only from temperature values.")
print("Confirm each physical sensor before setting the corresponding .env variable.")
PY

printf '\n%s\n' "============================================================"
printf '%s\n' " END - NO ACTUATOR COMMAND SENT"
printf '%s\n' "============================================================"
