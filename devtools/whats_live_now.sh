#!/bin/bash
# Quick check: What ESPN events are LIVE RIGHT NOW?

DB="/app/data/eplus_vc.sqlite3"

echo "=== Events LIVE RIGHT NOW ==="
echo "Current time: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

docker exec espn4cc4c sqlite3 "$DB" -header -column "
SELECT 
    network,
    title,
    sport,
    substr(start_utc, 12, 5) as start_time_utc,
    substr(stop_utc, 12, 5) as end_time_utc,
    event_type,
    simulcast_airing_id
FROM events
WHERE network IN ('ESPN', 'ESPN2', 'ACCN', 'ESPNews', 'ESPNU', 'SEC Network')
  AND datetime('now') BETWEEN datetime(start_utc) AND datetime(stop_utc)
  AND (airing_id IS NOT NULL OR simulcast_airing_id IS NOT NULL)
ORDER BY network, start_utc
"

echo ""
echo "Total live events:"
docker exec espn4cc4c sqlite3 "$DB" "
SELECT COUNT(*) as live_count
FROM events
WHERE network IN ('ESPN', 'ESPN2', 'ACCN', 'ESPNews', 'ESPNU', 'SEC Network')
  AND datetime('now') BETWEEN datetime(start_utc) AND datetime(stop_utc)
  AND (airing_id IS NOT NULL OR simulcast_airing_id IS NOT NULL)
"
