#!/usr/bin/env bash
set -Eeuo pipefail
cd "/opt/stacks/smart-building-controller"
rm -rf backend/app
cp -a "/opt/stacks/smart-building-controller/backups/sprint-006-2B1-20260724-122244/app" backend/app
docker compose up -d --build backend
