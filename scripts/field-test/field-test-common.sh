#!/usr/bin/env bash

REPO="/opt/stacks/smart-building-controller"
DATA_ROOT="$REPO/field-tests"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-sbc-backend}"
FRONTEND_CONTAINER="${FRONTEND_CONTAINER:-geocooling-ui-dev}"

ACTIVE_FILE="$DATA_ROOT/.active-campaign"

active_campaign_dir() {
  if [ ! -f "$ACTIVE_FILE" ]; then
    return 1
  fi

  local directory
  directory="$(cat "$ACTIVE_FILE")"

  if [ ! -d "$directory" ]; then
    return 1
  fi

  printf '%s\n' "$directory"
}

json_get() {
  local route="$1"
  local output="$2"

  curl -fsS \
    --connect-timeout 4 \
    --max-time 20 \
    "$BACKEND_URL$route" \
    > "$output"
}

safe_json_get() {
  local name="$1"
  local route="$2"
  local directory="$3"
  local timestamp="$4"

  local filename
  filename="$directory/data/${timestamp}-${name}.json"

  if json_get "$route" "$filename"; then
    if python3 -m json.tool "$filename" >/dev/null 2>&1; then
      printf 'OK\t%s\t%s\n' "$name" "$route"
      return 0
    fi

    printf 'INVALID_JSON\t%s\t%s\n' "$name" "$route"
    return 1
  fi

  printf 'UNAVAILABLE\t%s\t%s\n' "$name" "$route"
  rm -f "$filename"
  return 1
}
