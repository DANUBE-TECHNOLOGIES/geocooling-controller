#!/usr/bin/env bash
set -euo pipefail

LISTEN_SECONDS="${LISTEN_SECONDS:-15}"

printf '%s\n' "============================================================"
printf '%s\n' " GEOCOOLING - PASSIVE ESPHOME / MQTT DIAGNOSTIC"
printf '%s\n' " READ-ONLY / NO MODBUS / NO ACTUATOR COMMAND"
printf '%s\n' "============================================================"

printf '\n===== CONTAINERS =====\n'
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'

ESPHOME_CONTAINER="$(docker ps --format '{{.Names}} {{.Image}}' | awk 'tolower($0) ~ /esphome/ {print $1; exit}')"
MQTT_CONTAINER="$(docker ps --format '{{.Names}} {{.Image}}' | awk 'tolower($0) ~ /mosquitto/ {print $1; exit}')"

printf '\n===== COMPONENTS =====\n'
printf 'ESPHome: %s\n' "${ESPHOME_CONTAINER:-NOT_DETECTED}"
printf 'Mosquitto: %s\n' "${MQTT_CONTAINER:-NOT_DETECTED}"

printf '\n===== ESPHOME CONFIG CANDIDATES =====\n'
find /opt -maxdepth 5 -type f \( -name '*.yaml' -o -name '*.yml' \) 2>/dev/null \
  | grep -Ei 'esphome|wt32|geocooling|sbc-core' \
  | grep -Ev '/\.esphome/(platformio|\.espressif)/' \
  | head -100 || true

printf '\n===== ESPHOME SENSOR LOGS =====\n'
if [ -n "$ESPHOME_CONTAINER" ]; then
  docker logs --tail 300 "$ESPHOME_CONTAINER" 2>&1 \
    | grep -Ei 'ds18|dallas|one.?wire|sensor|temperature|error|warn' || true
else
  echo 'ESPHome container not detected.'
fi

printf '\n===== PASSIVE MQTT OBSERVATION (%ss) =====\n' "$LISTEN_SECONDS"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

if [ -n "$MQTT_CONTAINER" ]; then
  timeout "$LISTEN_SECONDS" docker exec "$MQTT_CONTAINER" \
    mosquitto_sub -h 127.0.0.1 -t '#' -v >"$TMP" 2>&1 || true
else
  echo 'Mosquitto container not detected.'
  : >"$TMP"
fi

MATCHES="$(grep -Ei 'temp|thermal|ds18|dallas|one.?wire|wt32|geocool|source|floor|plancher|depart|retour|surface|flow' "$TMP" || true)"

if [ -n "$MATCHES" ]; then
  printf '%s\n' "$MATCHES" | head -300
  printf '\nUPSTREAM_STATE=OBSERVED\n'
else
  echo 'No hydraulic/DS18B20/WT32 telemetry observed during passive window.'
  printf '\nUPSTREAM_STATE=UPSTREAM_EMPTY\n'
fi

printf '\n===== INTERPRETATION =====\n'
if [ -z "$ESPHOME_CONTAINER" ]; then
  echo 'BLOCKER: ESPHome runtime is absent.'
elif [ -z "$MQTT_CONTAINER" ]; then
  echo 'BLOCKER: MQTT broker is absent.'
elif [ -z "$MATCHES" ]; then
  echo 'BLOCKER: fix WT32/ESPHome -> MQTT publication before GeoCooling role mapping.'
else
  echo 'MQTT telemetry exists; continue with geocooling-telemetry-mapping.sh.'
fi

echo 'No MQTT publication, Modbus write or relay command was issued.'
printf '%s\n' "============================================================"
