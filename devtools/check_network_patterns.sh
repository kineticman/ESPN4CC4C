#!/bin/bash
# Check which networks work vs don't work with deeplinks

DB="${1:-data/eplus_vc.sqlite3}"

echo "=== Network Distribution ===="
echo ""
echo "Events by network:"
docker exec espn4cc4c sqlite3 /app/data/eplus_vc.sqlite3 -header -column "
SELECT 
    network,
    COUNT(*) as count,
    COUNT(DISTINCT packages) as package_variants
FROM events
WHERE network IS NOT NULL
GROUP BY network
ORDER BY count DESC
"

echo ""
echo "=== Package Analysis by Network ===="
echo ""
echo "Working networks (ESPN, ESPN Deportes, ESPNU):"
docker exec espn4cc4c sqlite3 /app/data/eplus_vc.sqlite3 -header -column "
SELECT network, packages, COUNT(*) as count
FROM events
WHERE network IN ('ESPN', 'ESPN Deportes', 'ESPNU')
GROUP BY network, packages
ORDER BY network, count DESC
"

echo ""
echo "Non-working networks (ESPN2, ESPNews, ACCN, etc.):"
docker exec espn4cc4c sqlite3 /app/data/eplus_vc.sqlite3 -header -column "
SELECT network, packages, COUNT(*) as count
FROM events
WHERE network IN ('ESPN2', 'ESPNews', 'ACCN', 'ACCNX', 'SEC Network')
GROUP BY network, packages
ORDER BY network, count DESC
"

echo ""
echo "=== Sample Events from Working vs Non-Working ===="
echo ""
echo "ESPN (working) sample:"
docker exec espn4cc4c sqlite3 /app/data/eplus_vc.sqlite3 -header -column "
SELECT id, title, network, packages, event_type
FROM events
WHERE network = 'ESPN'
LIMIT 3
"

echo ""
echo "ESPN2 (NOT working) sample:"
docker exec espn4cc4c sqlite3 /app/data/eplus_vc.sqlite3 -header -column "
SELECT id, title, network, packages, event_type
FROM events
WHERE network = 'ESPN2'
LIMIT 3
"

echo ""
echo "ACCN (NOT working) sample:"
docker exec espn4cc4c sqlite3 /app/data/eplus_vc.sqlite3 -header -column "
SELECT id, title, network, packages, event_type
FROM events
WHERE network = 'ACCN'
LIMIT 3
"

echo ""
echo "=== Check for Network IDs ===="
docker exec espn4cc4c sqlite3 /app/data/eplus_vc.sqlite3 -header -column "
SELECT DISTINCT network, network_id, network_short
FROM events
WHERE network IN ('ESPN', 'ESPN2', 'ACCN', 'ESPNews', 'ESPNU')
ORDER BY network
"
