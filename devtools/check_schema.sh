#!/bin/bash
# Check the events table schema to see what columns are available

echo "=== Events Table Schema ==="
docker exec espn4cc4c sqlite3 /app/data/eplus_vc.sqlite3 'PRAGMA table_info(events);'

echo ""
echo "=== Sample Event Data (first row) ==="
docker exec espn4cc4c sqlite3 /app/data/eplus_vc.sqlite3 -header -column "
SELECT * FROM events WHERE network = 'ACCN' LIMIT 1;
"

echo ""
echo "=== Column Names Only ==="
docker exec espn4cc4c sqlite3 /app/data/eplus_vc.sqlite3 "
SELECT name FROM pragma_table_info('events');
"
