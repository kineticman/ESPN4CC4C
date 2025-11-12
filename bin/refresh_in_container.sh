#!/bin/bash
#
# refresh_in_container.sh
# Runs on container startup to initialize/update database and generate EPG/M3U
#

set -e

echo "=== ESPN4CC4C Container Refresh Started ==="
echo "Timestamp: $(date)"

# Load environment variables with defaults
DB="${DB:-/app/data/eplus_vc.sqlite3}"
OUT="${OUT:-/app/out}"
TZ="${TZ:-America/New_York}"
VALID_HOURS="${VALID_HOURS:-72}"
LANES="${LANES:-40}"
ALIGN="${ALIGN:-30}"
MIN_GAP_MINS="${MIN_GAP_MINS:-30}"
PORT="${PORT:-8094}"

# Set VC_RESOLVER_BASE_URL in environment for scripts to use
export VC_RESOLVER_BASE_URL="${VC_RESOLVER_BASE_URL}"

echo "Configuration:"
echo "  DB: $DB"
echo "  OUT: $OUT"
echo "  TZ: $TZ"
echo "  VALID_HOURS: $VALID_HOURS"
echo "  VC_RESOLVER_BASE_URL: $VC_RESOLVER_BASE_URL"

# Ensure output directory exists
mkdir -p "$OUT"

# Check if database exists (first run vs. refresh)
if [ ! -f "$DB" ]; then
    echo "=== First Run: Initializing Database ==="
    DAYS=3
else
    echo "=== Refreshing Existing Database ==="
    DAYS=1
fi

# Step 1: Ingest events from ESPN Watch Graph
echo "Step 1/4: Ingesting ESPN Watch Graph (${DAYS} days)..."
python3 /app/bin/ingest_watch_graph_all_to_db.py \
    --db "$DB" \
    --days "$DAYS"

# Step 2: Build the plan
echo "Step 2/4: Building plan (${VALID_HOURS}h validity)..."
python3 /app/bin/build_plan.py \
    --db "$DB" \
    --valid-hours "$VALID_HOURS"

# Step 3: Generate XMLTV EPG
echo "Step 3/4: Generating XMLTV EPG..."
python3 /app/bin/xmltv_from_plan.py \
    --db "$DB" \
    --out "$OUT/epg.xml"

# Step 4: Generate M3U playlist
echo "Step 4/4: Generating M3U playlist..."
python3 /app/bin/m3u_from_plan.py \
    --db "$DB" \
    --out "$OUT/playlist.m3u" \
    ${CC_HOST:+--cc-host "$CC_HOST"} \
    ${CC_PORT:+--cc-port "$CC_PORT"}

echo "=== Refresh Complete ==="
echo "Database: $DB"
echo "EPG: $OUT/epg.xml"
echo "M3U: $OUT/playlist.m3u"
echo "Resolver: $VC_RESOLVER_BASE_URL"
echo "Starting API server..."
