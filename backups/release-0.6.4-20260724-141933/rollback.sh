#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="/opt/stacks/smart-building-controller"
BACKUP_DIR="/opt/stacks/smart-building-controller/backups/release-0.6.4-20260724-141933"

cp -a "$BACKUP_DIR/backend/app/main.py" "$PROJECT_DIR/backend/app/main.py"
rm -rf "$PROJECT_DIR/backend/app/rules"

if [[ -d "$BACKUP_DIR/backend/app/rules" ]]; then
    cp -a "$BACKUP_DIR/backend/app/rules" "$PROJECT_DIR/backend/app/rules"
fi

cp -a "$BACKUP_DIR/VERSION" "$PROJECT_DIR/VERSION"

cd "$PROJECT_DIR"
docker compose build backend
docker compose up -d --force-recreate backend
