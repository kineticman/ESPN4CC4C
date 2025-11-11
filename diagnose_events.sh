#!/bin/bash
# Diagnostic script to figure out why event counts are low

DB="${1:-data/eplus_vc.sqlite3}"

echo "=== EVENT DATABASE DIAGNOSTIC ==="
echo ""

echo "Total events in events table:"
sqlite3 "$DB" "SELECT COUNT(*) FROM events"
echo ""

echo "Total plan_slot entries:"
sqlite3 "$DB" "SELECT COUNT(*) FROM plan_slot WHERE plan_id = (SELECT MAX(plan_id) FROM plan_slot)"
echo ""

echo "plan_slot breakdown by kind:"
sqlite3 "$DB" -header -column "
SELECT kind, COUNT(*) as count
FROM plan_slot
WHERE plan_id = (SELECT MAX(plan_id) FROM plan_slot)
GROUP BY kind
ORDER BY count DESC
"
echo ""

echo "plan_slot with event_id (should have full data):"
sqlite3 "$DB" "
SELECT COUNT(*)
FROM plan_slot
WHERE plan_id = (SELECT MAX(plan_id) FROM plan_slot)
AND event_id IS NOT NULL AND event_id != ''
"
echo ""

echo "plan_slot WITHOUT event_id (placeholders):"
sqlite3 "$DB" "
SELECT COUNT(*)
FROM plan_slot
WHERE plan_id = (SELECT MAX(plan_id) FROM plan_slot)
AND (event_id IS NULL OR event_id = '')
"
echo ""

echo "Sample plan_slot entries with event_id:"
sqlite3 "$DB" -header -column "
SELECT ps.channel_id, ps.kind, ps.title, ps.event_id, e.title as event_title
FROM plan_slot ps
LEFT JOIN events e ON ps.event_id = e.id
WHERE ps.plan_id = (SELECT MAX(plan_id) FROM plan_slot)
AND ps.event_id IS NOT NULL
LIMIT 10
"
echo ""

echo "Sample plan_slot entries WITHOUT event_id (placeholders):"
sqlite3 "$DB" -header -column "
SELECT channel_id, kind, title, is_placeholder, placeholder_reason
FROM plan_slot
WHERE plan_id = (SELECT MAX(plan_id) FROM plan_slot)
AND (event_id IS NULL OR event_id = '')
LIMIT 10
"
echo ""

echo "Check if events were lost in migration:"
sqlite3 "$DB" "SELECT COUNT(*) FROM events WHERE start_utc LIKE '2025-11%'"
echo "^ Events with November 2025 dates"
echo ""

echo "Most recent plan_run info:"
sqlite3 "$DB" -header -column "
SELECT id, starts_at, ends_at, note, datetime(created_at, 'unixepoch') as created
FROM plan_run
ORDER BY id DESC
LIMIT 3
"
