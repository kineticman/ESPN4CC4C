#!/bin/bash
# Check why deeplinks are null

DB="${1:-data/eplus_vc.sqlite3}"

echo "=== Checking Event IDs and Feeds ==="
echo ""

# Get the event UIDs from your curl output
EVENT_UIDS=(
  "b452610f-6c7f-43be-a914-035cd03d5066:724cdbb5ef7bce7447de3804ec4852a3"
  "a1b122b2-7b62-4a1f-9dab-9e00fb603b63:f4c53e5d4bc16cb635695019496e062e"
  "b76b56ab-10ae-4f27-ad0b-2f0db8ec0ca3:2f8baf1128f8f20cdfd57cad248b7108"
)

for uid in "${EVENT_UIDS[@]}"; do
  echo "Event UID: $uid"
  
  # Check if event exists
  sqlite3 "$DB" -header -column "
  SELECT id, title, sport, league_name
  FROM events
  WHERE id LIKE '%${uid:0:36}%'
  LIMIT 1
  "
  
  # Check feeds for this event
  sqlite3 "$DB" -header -column "
  SELECT f.event_id, f.url, f.is_primary
  FROM feeds f
  JOIN events e ON f.event_id = e.id
  WHERE e.id LIKE '%${uid:0:36}%'
  LIMIT 3
  "
  
  echo "---"
done

echo ""
echo "=== Sample Events with Feeds ==="
sqlite3 "$DB" -header -column "
SELECT e.id, e.title, f.url
FROM events e
JOIN feeds f ON e.id = f.event_id
WHERE f.url IS NOT NULL
LIMIT 5
"

echo ""
echo "=== Events WITHOUT Feeds ==="
sqlite3 "$DB" "
SELECT COUNT(*)
FROM events e
LEFT JOIN feeds f ON e.id = f.event_id
WHERE f.url IS NULL OR f.url = ''
"
echo "^ Count of events with no feed URL"

echo ""
echo "=== Check Event ID Format ==="
echo "ESPN+ events should have ID format: espn-watch:UUID:hash"
sqlite3 "$DB" -header -column "
SELECT id, title, sport
FROM events
WHERE id NOT LIKE 'espn-watch:%'
LIMIT 10
"
echo "^ Events with non-ESPN format IDs"
