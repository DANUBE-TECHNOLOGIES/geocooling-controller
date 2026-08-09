#!/usr/bin/env bash
set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  SOURCE_DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
  SOURCE="$(readlink "$SOURCE")"

  if [[ "$SOURCE" != /* ]]; then
    SOURCE="$SOURCE_DIR/$SOURCE"
  fi
done

SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"

source "$SCRIPT_DIR/field-test-common.sh"

CAMPAIGN="$(active_campaign_dir)" || {
  echo "Aucune campagne active."
  exit 1
}

PID="$(
  cat "$CAMPAIGN/collector.pid" 2>/dev/null \
    || true
)"

rm -f "$ACTIVE_FILE"

if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  kill "$PID" 2>/dev/null || true

  for _ in $(seq 1 10); do
    if ! kill -0 "$PID" 2>/dev/null; then
      break
    fi

    sleep 1
  done

  if kill -0 "$PID" 2>/dev/null; then
    kill -9 "$PID" 2>/dev/null || true
  fi
fi

docker logs "$BACKEND_CONTAINER" \
  --since 6h \
  > "$CAMPAIGN/logs/backend-final.log" \
  2>&1 \
  || true

docker logs "$FRONTEND_CONTAINER" \
  --since 6h \
  > "$CAMPAIGN/logs/frontend-final.log" \
  2>&1 \
  || true

SAMPLES="$(
  wc -l < "$CAMPAIGN/samples.jsonl" 2>/dev/null \
    || echo 0
)"

python3 - "$CAMPAIGN" "$SAMPLES" <<'PY'
import json
import sys
from datetime import datetime
from pathlib import Path

directory = Path(sys.argv[1])
samples = int(sys.argv[2])

metadata_file = directory / "metadata.json"

try:
    metadata = json.loads(
        metadata_file.read_text(encoding="utf-8")
    )
except Exception:
    metadata = {}

metadata["stopped_at"] = datetime.now().astimezone().isoformat()
metadata["sample_count"] = samples
metadata["hardware_commands_sent"] = False
metadata["status"] = "completed"

metadata_file.write_text(
    json.dumps(metadata, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
PY

ARCHIVE="$CAMPAIGN.tar.gz"

tar -czf "$ARCHIVE" \
  -C "$(dirname "$CAMPAIGN")" \
  "$(basename "$CAMPAIGN")"

echo "============================================================"
echo " ✅ CAMPAGNE D’ESSAIS ARRÊTÉE"
echo "============================================================"
echo "Dossier      : $CAMPAIGN"
echo "Échantillons : $SAMPLES"
echo "Archive      : $ARCHIVE"
echo
echo "Aucune commande matérielle envoyée."
