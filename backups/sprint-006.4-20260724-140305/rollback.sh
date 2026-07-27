#!/usr/bin/env bash
set -Eeuo pipefail
cd "/opt/stacks/smart-building-controller"
rm -rf backend/app
cp -a "/opt/stacks/smart-building-controller/backups/sprint-006.4-20260724-140305/app" backend/app
if [[ -d "/opt/stacks/smart-building-controller/backups/sprint-006.4-20260724-140305/tests" ]]; then
  rm -rf tests
  cp -a "/opt/stacks/smart-building-controller/backups/sprint-006.4-20260724-140305/tests" tests
fi
[[ -f "/opt/stacks/smart-building-controller/backups/sprint-006.4-20260724-140305/VERSION" ]] && cp -a "/opt/stacks/smart-building-controller/backups/sprint-006.4-20260724-140305/VERSION" VERSION || true
docker compose build backend
docker compose up -d --force-recreate backend
