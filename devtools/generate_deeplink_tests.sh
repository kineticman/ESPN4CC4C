#!/bin/bash
# ESPN4CC4C Deeplink Format Testing Script
# Generates multiple deeplink format variations for testing on Fire TV

# Parse command-line arguments
NETWORK_FILTER=""
LIMIT=20
EVENT_TYPE_FILTER="('LIVE', 'UPCOMING')"

while [[ $# -gt 0 ]]; do
    case $1 in
        -network=*|--network=*)
            NETWORK_FILTER="${1#*=}"
            shift
            ;;
        -limit=*|--limit=*)
            LIMIT="${1#*=}"
            shift
            ;;
        -type=*|--type=*)
            TYPE="${1#*=}"
            if [[ "$TYPE" == "LIVE" ]]; then
                EVENT_TYPE_FILTER="('LIVE')"
            elif [[ "$TYPE" == "UPCOMING" ]]; then
                EVENT_TYPE_FILTER="('UPCOMING')"
            fi
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --network=NAME    Filter by network (ESPN, ESPN2, ACCN, ESPNews, ESPNU, SEC Network)"
            echo "  --limit=N         Number of events to test (default: 20)"
            echo "  --type=TYPE       Filter by event type (LIVE, UPCOMING, or both)"
            echo ""
            echo "Examples:"
            echo "  $0 --network=ESPN2"
            echo "  $0 --network=ACCN --limit=5"
            echo "  $0 --limit=10 --type=LIVE"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

DB="/app/data/eplus_vc.sqlite3"
OUTPUT_FILE="deeplink_test_cases.txt"

echo "=== ESPN4CC4C Deeplink Testing Script ===" > "$OUTPUT_FILE"
echo "Generated: $(date)" >> "$OUTPUT_FILE"
if [[ -n "$NETWORK_FILTER" ]]; then
    echo "Filter: Network = $NETWORK_FILTER" >> "$OUTPUT_FILE"
fi
echo "Limit: $LIMIT events" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Build WHERE clause
WHERE_CLAUSE="e.network IN ('ESPN', 'ESPN2', 'ACCN', 'ESPNews', 'ESPNU', 'SEC Network')"
if [[ -n "$NETWORK_FILTER" ]]; then
    WHERE_CLAUSE="e.network = '$NETWORK_FILTER'"
fi

# Get sample events from different networks
echo "Fetching sample events from database..." | tee -a "$OUTPUT_FILE"
echo "Filter: $WHERE_CLAUSE" | tee -a "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

docker exec espn4cc4c sqlite3 "$DB" -separator "|" "
SELECT 
    e.network,
    e.network_id,
    e.title,
    substr(e.id, 12, 36) as play_id,
    e.simulcast_airing_id,
    e.event_id,
    e.event_type
FROM events e
WHERE $WHERE_CLAUSE
  AND e.simulcast_airing_id IS NOT NULL
  AND e.event_type IN $EVENT_TYPE_FILTER
ORDER BY 
    CASE e.network
        WHEN 'ESPN' THEN 1
        WHEN 'ESPNU' THEN 2
        WHEN 'ESPN2' THEN 3
        WHEN 'ESPNews' THEN 4
        WHEN 'ACCN' THEN 5
        WHEN 'SEC Network' THEN 6
        ELSE 7
    END,
    e.start_utc
LIMIT $LIMIT
" | while IFS='|' read -r network network_id title play_id simulcast_id event_id event_type; do

    echo "" >> "$OUTPUT_FILE"
    echo "========================================" >> "$OUTPUT_FILE"
    echo "Event: $title" >> "$OUTPUT_FILE"
    echo "Network: $network (ID: $network_id)" >> "$OUTPUT_FILE"
    echo "Status: $event_type" >> "$OUTPUT_FILE"
    echo "PlayID: $play_id" >> "$OUTPUT_FILE"
    echo "SimulcastAiringID: $simulcast_id" >> "$OUTPUT_FILE"
    echo "EventID: $event_id" >> "$OUTPUT_FILE"
    echo "========================================" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 1: Current format (baseline - what we know works for ESPN)
    echo "# Format 1: Current (playID only)" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showWatchStream?playID=$play_id\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 2: With networkId
    echo "# Format 2: playID + networkId" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showWatchStream?playID=$play_id&networkId=$network_id\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 3: airingId only (using simulcast_airing_id)
    echo "# Format 3: airingId only" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showWatchStream?airingId=$simulcast_id\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 4: airingId + networkId
    echo "# Format 4: airingId + networkId" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showWatchStream?airingId=$simulcast_id&networkId=$network_id\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 5: Both playID and airingId
    echo "# Format 5: playID + airingId" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showWatchStream?playID=$play_id&airingId=$simulcast_id\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 6: All three parameters
    echo "# Format 6: playID + airingId + networkId" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showWatchStream?playID=$play_id&airingId=$simulcast_id&networkId=$network_id\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 7: Linear channel approach
    echo "# Format 7: Linear channel (airingId + networkId)" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showLinearChannel?airingId=$simulcast_id&networkId=$network_id\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 8: ShowVideo endpoint
    echo "# Format 8: showVideo endpoint (playID)" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showVideo?playID=$play_id\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 9: ShowVideo with airingId
    echo "# Format 9: showVideo + airingId" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showVideo?playID=$play_id&airingId=$simulcast_id\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 10: ESPN scheme (different protocol)
    echo "# Format 10: ESPN scheme (not sportscenter)" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"espn://x-callback-url/showWatchStream?playID=$play_id\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 11: Event-based (bypasses MVPD channel auth)
    if [[ -n "$event_id" ]]; then
        echo "# Format 11: showEvent (event-based, may bypass MVPD auth) ⭐" >> "$OUTPUT_FILE"
        echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showEvent?eventId=$event_id\"" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
    fi
    
    # Format 12: Event with playID fallback
    if [[ -n "$event_id" ]]; then
        echo "# Format 12: showEvent + playID fallback" >> "$OUTPUT_FILE"
        echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showEvent?eventId=$event_id&playID=$play_id\"" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
    fi
    
    # Format 13: Direct stream by event (alternative endpoint)
    if [[ -n "$event_id" ]]; then
        echo "# Format 13: playEvent endpoint" >> "$OUTPUT_FILE"
        echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/playEvent?eventId=$event_id\"" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
    fi
    
    # Format 14: Combined event + airing approach
    if [[ -n "$event_id" ]]; then
        echo "# Format 14: Event + airingId (hybrid)" >> "$OUTPUT_FILE"
        echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showEvent?eventId=$event_id&airingId=$simulcast_id\"" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
    fi
    
    echo "---" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"

done

# Summary and instructions
cat >> "$OUTPUT_FILE" << 'EOF'

========================================
TESTING INSTRUCTIONS
========================================

1. Connect to your Fire TV via ADB:
   adb connect 192.168.x.x

2. Test each format systematically:
   - START WITH FORMAT 11 (showEvent) - most likely to work!
   - Start with ESPN events (known working) as baseline
   - Then test ESPN2, ACCN, ESPNews (known NOT working)
   - Document which format makes them work

3. For each test:
   - Copy/paste the adb command
   - Observe what happens:
     ✅ Opens ESPN app and plays content = SUCCESS
     ❌ Opens app but shows error = Wrong format
     ❌ Doesn't open app = Invalid deeplink
     ⚠️  Opens app and asks for login = Needs MVPD authentication
     ⚠️  Opens app but shows "unavailable" = MVPD auth issue

4. Record your findings:
   Network: ESPN2
   Format: 4 (airingId + networkId)
   Result: SUCCESS - video played
   
5. Look for patterns:
   - Does adding networkId fix non-ESPN networks?
   - Does using airingId instead of playID help?
   - Do linear networks need different endpoint?

========================================
MOST LIKELY TO WORK (PREDICTIONS)
========================================

⭐ Format 11: showEvent (eventId only)
  → BEST GUESS - bypasses channel MVPD auth
  → Targets specific game, not linear channel
  → Should work for ESPN2, ACCN, ESPNews

Format 2: playID + networkId
  → Traditional approach with network context
  
Format 4: airingId + networkId  
  → Alternative if format 2 doesn't work
  
Format 14: Event + airingId
  → Hybrid approach with multiple identifiers
  
Format 6: All parameters
  → Nuclear option - might work if others fail

========================================
KEY INSIGHT: MVPD Authentication
========================================

🔑 All networks require MVPD (cable/satellite) auth:
   authTypes: ['MVPD'] in API response

Why ESPN "works" but ESPN2 doesn't:
  ✅ ESPN app already authenticated with provider
  ✅ ESPN may have looser enforcement
  ❌ ESPN2/ACCN/ESPNews enforce auth strictly

Event-based deeplinks (Format 11-14):
  → May bypass channel authentication
  → Target specific game, not channel feed
  → Could work without cable provider login

========================================
EXPECTED RESULTS BY NETWORK
========================================

ESPN (espn1):
  - Format 1 should work (baseline)
  - This is your control group

ESPN2 (espn2):
  - Format 1 probably fails
  - Format 2 or 4 likely fixes it
  
ACCN (acc):
  - Format 1 probably fails
  - Format 2, 4, or 7 might work
  
ESPNews (espnews):
  - Same as ESPN2

ESPNU (espnu):
  - User reported this works, so Format 1 should succeed

========================================
AUTOMATION TIPS
========================================

To test all formats for a single event quickly:

# Get event details
NETWORK="ESPN2"
PLAY_ID="d9e7769b-cf34-4152-82a3-6419bae9adbf"
NETWORK_ID="espn2"
AIRING_ID="1301152541"

# Test formats 1-6 in sequence
for i in {1..6}; do
    echo "Testing format $i..."
    # Run the corresponding adb command
    sleep 2  # Wait between tests
done

Or create a simple test harness:

#!/bin/bash
test_deeplink() {
    local format="$1"
    local url="$2"
    echo "Testing: $format"
    adb shell am start -a android.intent.action.VIEW -d "$url"
    echo "Did it work? (y/n)"
    read -t 10 response
    echo "$format: $response" >> test_results.txt
}

========================================
WHAT TO REPORT BACK
========================================

Please share:
1. Which format(s) work for ESPN2
2. Which format(s) work for ACCN  
3. Which format(s) work for ESPNews
4. Any error messages from ESPN app
5. Whether it asks for cable provider login
6. Whether Format 11 (showEvent) bypasses MVPD auth
7. Does your ESPN+ subscription include linear channels?

Critical questions:
❓ Do event-based deeplinks (Format 11-14) work?
❓ Do they bypass the MVPD authentication requirement?
❓ Is there a difference between live sports and replays?

This will tell us how to update the resolver!
EOF

echo "" | tee -a "$OUTPUT_FILE"
echo "✅ Test cases generated!" | tee -a "$OUTPUT_FILE"
echo "📄 Output saved to: $OUTPUT_FILE" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"
echo "Sample events by network:" | tee -a "$OUTPUT_FILE"

docker exec espn4cc4c sqlite3 "$DB" -header -column "
SELECT network, COUNT(*) as test_cases
FROM (
    SELECT network
    FROM events
    WHERE network IN ('ESPN', 'ESPN2', 'ACCN', 'ESPNews', 'ESPNU', 'SEC Network')
      AND simulcast_airing_id IS NOT NULL
      AND event_type IN ('LIVE', 'UPCOMING')
    ORDER BY network
    LIMIT 20
)
GROUP BY network
ORDER BY network
" | tee -a "$OUTPUT_FILE"

echo "" | tee -a "$OUTPUT_FILE"
echo "📋 Review $OUTPUT_FILE and start testing!" | tee -a "$OUTPUT_FILE"
echo "💡 Tip: Test ESPN (working) first to verify your ADB setup" | tee -a "$OUTPUT_FILE"
