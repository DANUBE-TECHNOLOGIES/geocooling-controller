#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/stacks/smart-building-controller}"
API_BASE_URL="${API_BASE_URL:-}"
API_FILE="${PROJECT_DIR}/backend/app/geocooling/api.py"
DIGITAL_TWIN_PATH="/geocooling/digital-twin/snapshot"

cd "$PROJECT_DIR"

discover_base_url() {
  local candidates=(
    "http://127.0.0.1:5001"
    "http://127.0.0.1:8000"
    "http://127.0.0.1:8001"
    "http://127.0.0.1:8080"
    "http://127.0.0.1:5000"
    "http://127.0.0.1:3001"
  )

  while IFS= read -r port; do
    [[ -n "$port" ]] && candidates+=("http://127.0.0.1:${port}")
  done < <(
    docker ps --format '{{.Ports}}' 2>/dev/null \
      | grep -oE '127\.0\.0\.1:[0-9]+|0\.0\.0\.0:[0-9]+|:::[0-9]+' \
      | grep -oE '[0-9]+$' \
      | sort -u || true
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if curl -fsS --connect-timeout 2 --max-time 5 \
      "${candidate}${DIGITAL_TWIN_PATH}" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

if [[ -z "$API_BASE_URL" ]]; then
  API_BASE_URL="$(discover_base_url || true)"
fi

if [[ -z "$API_BASE_URL" ]]; then
  echo "ERREUR : API GeoCooling introuvable."
  docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' || true
  exit 1
fi

echo "API détectée : $API_BASE_URL"

[[ -f "$API_FILE" ]] || {
  echo "ERREUR : fichier API absent : $API_FILE"
  exit 1
}

TMP_DIR="$(mktemp -d /tmp/c0201r5-routes.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

ROUTES_FILE="$TMP_DIR/routes.txt"

python3 - "$API_FILE" > "$ROUTES_FILE" <<'PY'
import ast
import re
import sys
from pathlib import Path

source_path = Path(sys.argv[1])
source = source_path.read_text(encoding="utf-8")
routes = set()

# 1. Toutes les chaînes Python contenant thermal ou snapshot.
try:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            low = value.lower()
            if value.startswith("/") and ("thermal" in low or "snapshot" in low):
                routes.add(value)
except SyntaxError:
    pass

# 2. Secours par expression régulière.
for match in re.findall(r"""["'](/[^"' \t\r\n]+)["']""", source):
    low = match.lower()
    if "thermal" in low or "snapshot" in low:
        routes.add(match)

# 3. Chemins historiques connus, uniquement comme derniers candidats.
routes.update({
    "/thermal-snapshot",
    "/thermal_snapshot",
    "/geocooling/thermal-snapshot",
    "/geocooling/thermal_snapshot",
    "/geocooling/thermal/snapshot",
    "/geocooling/snapshot/thermal",
})

for route in sorted(routes, key=lambda x: (0 if "snapshot" in x.lower() else 1, len(x), x)):
    print(route)
PY

echo "Routes candidates détectées :"
sed 's/^/ - /' "$ROUTES_FILE"

cat > "$TMP_DIR/snapshot.json" <<'JSON'
{
  "indoor": 26.1,
  "upstairs": 25.4,
  "outdoor": 31.8,
  "humidity": 54.0,
  "surface": 22.4,
  "supply": 18.0,
  "return": 20.5,
  "source_in": 12.3,
  "source_out": 15.0,
  "flow": 28.0,
  "pump": true,
  "valve": true
}
JSON

SUCCESS=0
SELECTED_METHOD=""
SELECTED_PATH=""

while IFS= read -r RAW_PATH; do
  [[ -n "$RAW_PATH" ]] || continue

  candidates=("$RAW_PATH")
  if [[ "$RAW_PATH" != /geocooling/* ]]; then
    candidates+=("/geocooling${RAW_PATH}")
  fi

  for SNAPSHOT_PATH in "${candidates[@]}"; do
    for METHOD in PUT POST; do
      RESPONSE="$TMP_DIR/response.json"
      HTTP_CODE="$(
        curl -sS --max-time 15 \
          -o "$RESPONSE" \
          -w '%{http_code}' \
          -X "$METHOD" \
          -H 'Content-Type: application/json' \
          --data-binary @"$TMP_DIR/snapshot.json" \
          "${API_BASE_URL}${SNAPSHOT_PATH}" || true
      )"

      echo "Essai : ${METHOD} ${SNAPSHOT_PATH} -> HTTP ${HTTP_CODE}"

      if [[ "$HTTP_CODE" =~ ^2[0-9][0-9]$ ]]; then
        SUCCESS=1
        SELECTED_METHOD="$METHOD"
        SELECTED_PATH="$SNAPSHOT_PATH"
        cp "$RESPONSE" "$TMP_DIR/put.json"
        break 3
      fi

      if [[ -s "$RESPONSE" && "$HTTP_CODE" != "404" && "$HTTP_CODE" != "405" ]]; then
        echo "Réponse : $(tr '\n' ' ' < "$RESPONSE" | head -c 500)"
        echo
      fi
    done
  done
done < "$ROUTES_FILE"

if [[ "$SUCCESS" -ne 1 ]]; then
  echo
  echo "ERREUR : aucune route candidate n'a accepté le snapshot."
  echo
  echo "Références à put_thermal_snapshot dans api.py :"
  grep -n -C 4 'put_thermal_snapshot' "$API_FILE" || true
  echo
  echo "Routes contenant thermal/snapshot dans api.py :"
  grep -nEi 'thermal|snapshot' "$API_FILE" | head -100 || true
  exit 1
fi

echo "Route snapshot validée : ${SELECTED_METHOD} ${SELECTED_PATH}"

curl -fsS --max-time 10 \
  "${API_BASE_URL}${DIGITAL_TWIN_PATH}" \
  -o "$TMP_DIR/after.json"

python3 - "$TMP_DIR/put.json" "$TMP_DIR/after.json" <<'PY'
import json
import sys
from pathlib import Path

put_response = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
after = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

def contains(value, expected):
    if value == expected:
        return True
    if isinstance(value, dict):
        return any(contains(item, expected) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains(item, expected) for item in value)
    return False

expected_values = [26.1, 25.4, 31.8, 54.0, 22.4, 18.0, 20.5, 12.3, 15.0, 28.0]
missing = [value for value in expected_values if not contains(after, value)]

if missing:
    print("ERREUR : valeurs absentes du Digital Twin :", missing)
    print(json.dumps(after, indent=2, ensure_ascii=False))
    raise SystemExit(1)

if not contains(after, True):
    print("ERREUR : états booléens absents du Digital Twin")
    print(json.dumps(after, indent=2, ensure_ascii=False))
    raise SystemExit(1)

print("Réponse injection :")
print(json.dumps(put_response, indent=2, ensure_ascii=False))
print()
print("Digital Twin après injection :")
print(json.dumps(after, indent=2, ensure_ascii=False))
PY

echo
echo "✅ C020.1R5 CERTIFIÉ EN CONDITIONS RÉELLES"
echo "Flux validé : ${SELECTED_METHOD} ${SELECTED_PATH} -> Digital Twin -> GET"
