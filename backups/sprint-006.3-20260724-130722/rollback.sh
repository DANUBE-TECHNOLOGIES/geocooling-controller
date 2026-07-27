#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="/opt/stacks/smart-building-controller"
BACKUP="/opt/stacks/smart-building-controller/backups/sprint-006.3-20260724-130722"
rm -rf "$ROOT/backend/app/automation"
if [[ -d "$BACKUP/backend/app/automation" ]]; then cp -a "$BACKUP/backend/app/automation" "$ROOT/backend/app/automation"; fi
cp -a "$BACKUP/backend/app/main.py" "$ROOT/backend/app/main.py"
cp -a "$BACKUP/VERSION" "$ROOT/VERSION"
if [[ -f "$BACKUP/tests/test_automation_service.py" ]]; then cp -a "$BACKUP/tests/test_automation_service.py" "$ROOT/tests/"; else rm -f "$ROOT/tests/test_automation_service.py"; fi
cd "$ROOT"
docker compose up -d --build backend
