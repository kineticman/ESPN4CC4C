#!/usr/bin/env bash
set -euo pipefail

# ESPN4CC4C Filter Audit (ELI5-style)
#
# What this script does, in human terms:
#   1) Shows you WHICH FILTERS are currently turned on.
#   2) Shows how many events are left in the database AFTER filtering.
#   3) Proves that nothing you tried to block (like NCAAW, Spanish, re-airs)
#      is sneaking into the guide/plan.

DB="${1:-/app/data/eplus_vc.sqlite3}"
CONTAINER="${CONTAINER_NAME:-espn4cc4c}"

echo "=== ESPN4CC4C Filter Audit ==="
echo "Container: ${CONTAINER}"
echo "DB: ${DB}"
echo

echo "STEP 1: What filters are turned on right now?"
echo "--------------------------------------------"
echo "Below is the filter summary from EventFilter.get_filter_summary()."
echo "This is based on your FILTER_* environment variables and /app/filters.ini."
echo

docker exec "${CONTAINER}" python3 /app/bin/filter_events.py "${DB}" /app/filters.ini || {
  echo "WARNING: Failed to run filter_events.py inside container" >&2
}
echo
echo "NOTE:"
echo "  The line like \"[filter] Total events: X, Included: X, Filtered out: 0\""
echo "  is re-checking ONLY the events that are already in the database now."
echo "  The REAL pruning happened during the last refresh, when bad events"
echo "  were physically deleted from the events table."
echo

echo "STEP 2: What does the database look like AFTER filtering?"
echo "---------------------------------------------------------"
docker exec "${CONTAINER}" sqlite3 "${DB}" "
SELECT 'events_total' AS metric, COUNT(*) FROM events
UNION ALL
SELECT 'plan_slots', COUNT(*) FROM plan_slot;
"
echo
echo "Think of this as:"
echo "  - events_total = how many events SURVIVED your filters"
echo "  - plan_slots   = how many schedule slots are using those events"
echo

echo "Leagues still present in events (top 20):"
docker exec "${CONTAINER}" sqlite3 "${DB}" "
SELECT lower(league_name) AS league, COUNT(*) AS cnt
FROM events
GROUP BY league
ORDER BY cnt DESC
LIMIT 20;
"
echo

echo "Languages still present in events:"
docker exec "${CONTAINER}" sqlite3 "${DB}" "
SELECT language, COUNT(*) AS cnt
FROM events
GROUP BY language
ORDER BY cnt DESC;
"
echo

echo "Re-airs still present in events (should be 0 if exclude_reair is true):"
docker exec "${CONTAINER}" sqlite3 "${DB}" "
SELECT COUNT(*) AS reairs_left
FROM events
WHERE is_reair = 1;
"
echo

echo "STEP 3: Prove that blocked stuff is NOT in the guide"
echo "----------------------------------------------------"
echo "Now we look at the actual plan (what shows up in the guide)."
echo "If your filters are working correctly, these should all be ZERO:"
echo

docker exec "${CONTAINER}" sqlite3 "${DB}" "
SELECT 'bad_slots_league' AS metric, COUNT(*) AS cnt
FROM plan_slot ps
JOIN events e ON ps.event_id = e.id
WHERE lower(e.league_name) LIKE '%ncaaw%'
   OR lower(e.league_name) LIKE '%women%'
UNION ALL
SELECT 'bad_slots_language_es', COUNT(*)
FROM plan_slot ps
JOIN events e ON ps.event_id = e.id
WHERE lower(e.language) = 'es'
UNION ALL
SELECT 'bad_slots_reair', COUNT(*)
FROM plan_slot ps
JOIN events e ON ps.event_id = e.id
WHERE e.is_reair = 1;
"
echo
echo "If all the numbers above are 0, then:"
echo "  ✅ Your filters are ON (Step 1)"
echo "  ✅ The database only contains allowed events (Step 2)"
echo "  ✅ The guide/plan is not using any blocked content (Step 3)"
echo
