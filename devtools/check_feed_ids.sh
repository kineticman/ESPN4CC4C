#!/bin/bash
# Check feed data and airing IDs

DB="/app/data/eplus_vc.sqlite3"

echo "=== ESPN (working) - Full Event Data ==="
docker exec espn4cc4c sqlite3 "$DB" -header -column "
SELECT 
    e.id,
    e.title,
    e.network,
    e.network_id,
    e.airing_id,
    e.simulcast_airing_id,
    f.id as feed_id,
    f.url as feed_url
FROM events e
LEFT JOIN feeds f ON e.id = f.event_id
WHERE e.network = 'ESPN'
LIMIT 3
"

echo ""
echo "=== ESPN2 (NOT working) - Full Event Data ==="
docker exec espn4cc4c sqlite3 "$DB" -header -column "
SELECT 
    e.id,
    e.title,
    e.network,
    e.network_id,
    e.airing_id,
    e.simulcast_airing_id,
    f.id as feed_id,
    f.url as feed_url
FROM events e
LEFT JOIN feeds f ON e.id = f.event_id
WHERE e.network = 'ESPN2'
LIMIT 3
"

echo ""
echo "=== ACCN (NOT working) - Full Event Data ==="
docker exec espn4cc4c sqlite3 "$DB" -header -column "
SELECT 
    e.id,
    e.title,
    e.network,
    e.network_id,
    e.airing_id,
    e.simulcast_airing_id,
    f.id as feed_id,
    f.url as feed_url
FROM events e
LEFT JOIN feeds f ON e.id = f.event_id
WHERE e.network = 'ACCN'
LIMIT 3
"

echo ""
echo "=== Check if airingId vs simulcastAiringId matters ==="
docker exec espn4cc4c sqlite3 "$DB" -header -column "
SELECT 
    network,
    COUNT(*) as total,
    COUNT(airing_id) as has_airing_id,
    COUNT(simulcast_airing_id) as has_simulcast_id
FROM events
WHERE network IN ('ESPN', 'ESPN2', 'ACCN', 'ESPNU')
GROUP BY network
"
