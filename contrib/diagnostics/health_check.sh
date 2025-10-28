#!/usr/bin/env bash
set -euo pipefail
curl -fsS http://127.0.0.1:8094/health >/dev/null || exit 1
curl -fsS http://127.0.0.1:8094/status | jq -e '.active_plan.plan_id' >/dev/null
echo "ok"
