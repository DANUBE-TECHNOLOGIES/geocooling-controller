#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="/opt/stacks/smart-building-controller"
BACKUP_DIR="/opt/stacks/smart-building-controller/backups/release-0.6.6-20260724-144650"
rm -rf "$PROJECT_DIR/backend/app/building" "$PROJECT_DIR/backend/app/rules"
cp -a "$BACKUP_DIR/backend/app/building" "$PROJECT_DIR/backend/app/building"
cp -a "$BACKUP_DIR/backend/app/rules" "$PROJECT_DIR/backend/app/rules"
cp -a "$BACKUP_DIR/backend/app/main.py" "$PROJECT_DIR/backend/app/main.py"
cp -a "$BACKUP_DIR/VERSION" "$PROJECT_DIR/VERSION"
cd "$PROJECT_DIR"
docker compose build backend
docker compose up -d --force-recreate backend
