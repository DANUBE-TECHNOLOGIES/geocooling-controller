#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/field-test-common.sh"

CAMPAIGN_DIR="$(active_campaign_dir)" || {
  echo "Aucune campagne active."
  exit 1
}

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
STATUS_FILE="$CAMPAIGN_DIR/collection-status.log"

mkdir -p "$CAMPAIGN_DIR/data"

{
  echo "============================================================"
  echo "COLLECTION $STAMP"
  echo "============================================================"

  safe_json_get \
    "rc1-readiness" \
    "/geocooling/rc1/readiness" \
    "$CAMPAIGN_DIR" \
    "$STAMP"

  safe_json_get \
    "dashboard" \
    "/geocooling/dashboard" \
    "$CAMPAIGN_DIR" \
    "$STAMP"

  safe_json_get \
    "thermal" \
    "/geocooling/thermal" \
    "$CAMPAIGN_DIR" \
    "$STAMP"

  safe_json_get \
    "brain" \
    "/geocooling/brain" \
    "$CAMPAIGN_DIR" \
    "$STAMP"

  safe_json_get \
    "prediction" \
    "/geocooling/prediction" \
    "$CAMPAIGN_DIR" \
    "$STAMP"

  safe_json_get \
    "safety" \
    "/geocooling/safety" \
    "$CAMPAIGN_DIR" \
    "$STAMP"

  safe_json_get \
    "runtime" \
    "/geocooling/runtime" \
    "$CAMPAIGN_DIR" \
    "$STAMP"

  safe_json_get \
    "relay-status" \
    "/geocooling/relay/status" \
    "$CAMPAIGN_DIR" \
    "$STAMP"

  safe_json_get \
    "hardware-status" \
    "/geocooling/manual/hardware/status" \
    "$CAMPAIGN_DIR" \
    "$STAMP"

  safe_json_get \
    "weather" \
    "/geocooling/weather" \
    "$CAMPAIGN_DIR" \
    "$STAMP"

  echo
} >> "$STATUS_FILE" 2>&1

python3 \
  "$SCRIPT_DIR/collector.py" \
  "$CAMPAIGN_DIR" \
  "$STAMP" \
  >> "$CAMPAIGN_DIR/collector.log" \
  2>&1
