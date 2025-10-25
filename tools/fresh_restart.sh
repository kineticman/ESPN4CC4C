#!/usr/bin/env bash
# Fresh restart + sanity checks for ESPN_clean_v2
# Usage: VC_RESOLVER_ORIGIN=http://HOST:8094 tools/fresh_restart.sh
set -euo pipefail

PROJ=${PROJ:-"$HOME/Projects/ESPN_clean_v2"}
DB="${DB:-"$PROJ/data/eplus_vc.sqlite3"}"
LOGDIR="${LOGDIR:-/var/log/espnvc-v2}"

# Use env if set; else fall back to localhost
RESOLVER_BASE="${VC_RESOLVER_ORIGIN:-http://127.0.0.1:8094}"
LANE="${LANE:-eplus11}"

echo "== reload & restart resolver =="
sudo systemctl daemon-reload
sudo systemctl restart vc-resolver-v2.service
sleep 1
systemctl --no-pager -l status vc-resolver-v2.service | sed -n '1,15p' || true

echo "== clear logs =="
sudo mkdir -p "$LOGDIR"
sudo truncate -s 0 "$LOGDIR/resolver.log" || true
sudo truncate -s 0 "$LOGDIR/pipeline.log" || true

echo "== run one-shot pipeline =="
sudo systemctl start vc-pipeline-v2.service
sleep 1

echo "== pipeline log tail =="
tail -n 150 "$LOGDIR/pipeline.log" || true
if grep -Eiq 'unrecognized arguments|traceback|plan_build_failed|error:' "$LOGDIR/pipeline.log"; then
  echo "!! Found issues in pipeline.log"
else
  echo "✅ pipeline log shows no CLI/traceback errors"
fi

echo "== artifacts =="
ls -lh "$PROJ/out/virtual_channels.xml" "$PROJ/out/virtual_channels.m3u" || true

echo "== plan sanity: off-minute placeholders =="
sqlite3 -csv "$DB" "SELECT MAX(plan_id) FROM plan_slot;" | awk '{print \"Active plan_id:\",$0}'
sqlite3 -csv "$DB" "
WITH pid AS (SELECT MAX(plan_id) id FROM plan_slot)
SELECT COUNT(*) FROM plan_slot
WHERE plan_id=(SELECT id FROM pid) AND kind='placeholder'
  AND CAST(strftime('%M', replace(substr(start_utc,1,19),'T',' ')) AS INT) NOT IN (0,30);
" | awk '{print \"Off-minute placeholders:\",$0}'

echo "== resolver probes =="
curl -s "$RESOLVER_BASE/health" && echo
curl -sI "$RESOLVER_BASE/epg.xml"      | sed -n '1p;/Content-Type/p'
curl -sI "$RESOLVER_BASE/playlist.m3u" | sed -n '1p;/Content-Type/p'

echo "--- /vc/${LANE}/debug ---"
curl -s "$RESOLVER_BASE/vc/$LANE/debug" | jq . || true
echo "--- /vc/${LANE} (expect 302 when live) ---"
curl -i "$RESOLVER_BASE/vc/$LANE?only_live=0" | sed -n '1,12p'
