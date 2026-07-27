#!/usr/bin/env bash
set -Eeuo pipefail
cd "/opt/stacks/smart-building-controller"
rm -rf backend/app
cp -a "/opt/stacks/smart-building-controller/backups/sprint-006-2C-20260724-122914/app" backend/app
[[ -f "/opt/stacks/smart-building-controller/backups/sprint-006-2C-20260724-122914/env" ]] && cp -a "/opt/stacks/smart-building-controller/backups/sprint-006-2C-20260724-122914/env" .env || true
[[ -f "/opt/stacks/smart-building-controller/backups/sprint-006-2C-20260724-122914/compose.yaml" ]] && cp -a "/opt/stacks/smart-building-controller/backups/sprint-006-2C-20260724-122914/compose.yaml" compose.yaml || true
docker compose up -d --build backend
