#!/bin/bash
# ESPN4CC4C Deeplink Format Testing Script - OPTIMIZED VERSION
# Uses actual database schema: airing_id + simulcast_airing_id

# Parse command-line arguments
NETWORK_FILTER=""
LIMIT=20
EVENT_TYPE_FILTER="('LIVE', 'UPCOMING')"
LIVE_NOW_FILTER=""

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
        --live-now)
            LIVE_NOW_FILTER="AND datetime('now') BETWEEN datetime(e.start_utc) AND datetime(e.stop_utc)"
            EVENT_TYPE_FILTER="('LIVE')"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --network=NAME    Filter by network (ESPN, ESPN2, ACCN, ESPNews, ESPNU, SEC Network)"
            echo "  --limit=N         Number of events to test (default: 20)"
            echo "  --type=TYPE       Filter by event type (LIVE, UPCOMING, or both)"
            echo "  --live-now        Only show events that are live RIGHT NOW"
            echo ""
            echo "Examples:"
            echo "  $0 --network=ESPN2"
            echo "  $0 --network=ACCN --limit=5"
            echo "  $0 --limit=10 --type=LIVE"
            echo "  $0 --live-now --network=ESPN2"
            echo "  $0 --live-now"
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
if [[ -n "$LIVE_NOW_FILTER" ]]; then
    echo "Filter: LIVE NOW ONLY" >> "$OUTPUT_FILE"
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
if [[ -n "$LIVE_NOW_FILTER" ]]; then
    echo "Additional: Live events only (happening RIGHT NOW)" | tee -a "$OUTPUT_FILE"
fi
echo "" >> "$OUTPUT_FILE"

docker exec espn4cc4c sqlite3 "$DB" -separator "|" "
SELECT 
    e.network,
    e.network_id,
    e.title,
    substr(e.id, 12, 36) as play_id,
    e.airing_id,
    e.simulcast_airing_id,
    e.event_type
FROM events e
WHERE $WHERE_CLAUSE
  AND (e.airing_id IS NOT NULL OR e.simulcast_airing_id IS NOT NULL)
  AND e.event_type IN $EVENT_TYPE_FILTER
  $LIVE_NOW_FILTER
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
" | while IFS='|' read -r network network_id title play_id airing_id simulcast_id event_type; do

    echo "" >> "$OUTPUT_FILE"
    echo "========================================" >> "$OUTPUT_FILE"
    echo "Event: $title" >> "$OUTPUT_FILE"
    echo "Network: $network (ID: $network_id)" >> "$OUTPUT_FILE"
    echo "Status: $event_type" >> "$OUTPUT_FILE"
    echo "PlayID: $play_id" >> "$OUTPUT_FILE"
    echo "AiringID: $airing_id" >> "$OUTPUT_FILE"
    echo "SimulcastAiringID: $simulcast_id" >> "$OUTPUT_FILE"
    echo "========================================" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Determine which airing ID to use (prefer simulcast if available)
    PRIMARY_AIRING="${simulcast_id:-$airing_id}"
    
    # Format 1: Current format (baseline - what we know works for ESPN)
    echo "# Format 1: Current (playID only)" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showWatchStream?playID=$play_id\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 2: With networkId
    echo "# Format 2: playID + networkId" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showWatchStream?playID=$play_id&networkId=$network_id\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 3: airingId only (using primary airing ID)
    echo "# Format 3: airingId only (simulcast preferred)" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showWatchStream?airingId=$PRIMARY_AIRING\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 4: airingId + networkId
    echo "# Format 4: airingId + networkId" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showWatchStream?airingId=$PRIMARY_AIRING&networkId=$network_id\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 5: Both playID and airingId
    echo "# Format 5: playID + airingId" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showWatchStream?playID=$play_id&airingId=$PRIMARY_AIRING\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 6: All three parameters
    echo "# Format 6: playID + airingId + networkId (nuclear option)" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showWatchStream?playID=$play_id&airingId=$PRIMARY_AIRING&networkId=$network_id\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 7: Linear channel approach
    echo "# Format 7: Linear channel (airingId + networkId)" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showLinearChannel?airingId=$PRIMARY_AIRING&networkId=$network_id\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 8: ShowVideo endpoint
    echo "# Format 8: showVideo endpoint (playID)" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showVideo?playID=$play_id\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 9: ShowVideo with airingId
    echo "# Format 9: showVideo + airingId" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showVideo?playID=$play_id&airingId=$PRIMARY_AIRING\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # Format 10: ESPN scheme (different protocol)
    echo "# Format 10: ESPN scheme (not sportscenter)" >> "$OUTPUT_FILE"
    echo "adb shell am start -a android.intent.action.VIEW -d \"espn://x-callback-url/showWatchStream?playID=$play_id\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    # ===== EVENT-BASED FORMATS (May bypass MVPD auth) =====
    
    # Format 11: showEvent with simulcast airing ID as eventId ⭐⭐⭐
    if [[ -n "$simulcast_id" ]]; then
        echo "# Format 11: showEvent (simulcast as eventId) ⭐⭐⭐ HIGHEST PRIORITY" >> "$OUTPUT_FILE"
        echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showEvent?eventId=$simulcast_id\"" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
    fi
    
    # Format 12: showEvent with regular airing_id as eventId
    if [[ -n "$airing_id" ]]; then
        echo "# Format 12: showEvent (airing_id as eventId) ⭐⭐" >> "$OUTPUT_FILE"
        echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showEvent?eventId=$airing_id\"" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
    fi
    
    # Format 13: playEvent with simulcast ID
    if [[ -n "$simulcast_id" ]]; then
        echo "# Format 13: playEvent (simulcast) ⭐" >> "$OUTPUT_FILE"
        echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/playEvent?eventId=$simulcast_id\"" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
    fi
    
    # Format 14: showEvent with both IDs (hybrid approach)
    if [[ -n "$simulcast_id" ]]; then
        echo "# Format 14: showEvent + playID (hybrid)" >> "$OUTPUT_FILE"
        echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showEvent?eventId=$simulcast_id&playID=$play_id\"" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
    fi
    
    # Format 15: showAiring endpoint (dedicated airing route)
    if [[ -n "$simulcast_id" ]]; then
        echo "# Format 15: showAiring (simulcast) ⭐" >> "$OUTPUT_FILE"
        echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showAiring?airingId=$simulcast_id\"" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
    fi
    
    # Format 16: showAiring with regular airing_id
    if [[ -n "$airing_id" ]]; then
        echo "# Format 16: showAiring (airing_id)" >> "$OUTPUT_FILE"
        echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showAiring?airingId=$airing_id\"" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
    fi
    
    # Format 17: Test if both airing IDs together helps
    if [[ -n "$airing_id" && -n "$simulcast_id" ]]; then
        echo "# Format 17: Both airing IDs (experimental)" >> "$OUTPUT_FILE"
        echo "adb shell am start -a android.intent.action.VIEW -d \"sportscenter://x-callback-url/showWatchStream?airingId=$airing_id&simulcastAiringId=$simulcast_id\"" >> "$OUTPUT_FILE"
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

2. Test HIGH PRIORITY formats first (marked with ⭐):
   - Format 11: showEvent with simulcast_airing_id ⭐⭐⭐
   - Format 15: showAiring with simulcast_airing_id ⭐
   - Format 12: showEvent with airing_id ⭐⭐
   - Format 13: playEvent ⭐

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
   Format: 11 (showEvent with simulcast)
   Result: SUCCESS - video played WITHOUT asking for cable login
   
5. Testing sequence (recommended):
   Step 1: Test Format 1 on ESPN (baseline - should work)
   Step 2: Test Format 1 on ESPN2 (should fail or ask for auth)
   Step 3: Test Format 11 on ESPN2 (hypothesis: should work!)
   Step 4: Test Format 11 on ACCN and ESPNews

========================================
MOST LIKELY TO WORK (PREDICTIONS)
========================================

⭐⭐⭐ Format 11: showEvent with simulcast_airing_id
  → HIGHEST PROBABILITY - bypasses channel MVPD auth
  → Uses simulcast airing as event identifier
  → Targets specific game, not linear channel feed
  → Should work for ESPN2, ACCN, ESPNews WITHOUT cable login

⭐⭐ Format 12: showEvent with airing_id
  → Second choice if simulcast version doesn't work
  → Same theory, different ID

⭐ Format 15: showAiring with simulcast_airing_id
  → Dedicated endpoint for airings
  → Alternative route to same content

Format 2: playID + networkId
  → Traditional fallback with network context
  
Format 4: airingId + networkId  
  → Channel-based approach with explicit network

========================================
KEY INSIGHT: MVPD Authentication
========================================

🔑 All networks have MVPD requirement in API:
   authTypes: ['MVPD'] = requires cable/satellite

Why ESPN "works" but ESPN2 doesn't:
  ✅ ESPN app pre-authenticated with provider
  ✅ ESPN has looser enforcement
  ❌ ESPN2/ACCN/ESPNews strictly enforce auth
  ❌ Without cable login, channel streams blocked

Event-based hypothesis:
  → showEvent/showAiring may bypass channel auth
  → Targets specific airing, not continuous channel
  → Could work with just ESPN+ (no cable needed)

Database insights:
  • airing_id = Basic airing identifier
  • simulcast_airing_id = Cross-network airing ID
  • simulcast_id preferred (handles multi-network events)

========================================
EXPECTED RESULTS BY NETWORK
========================================

ESPN (espn1):
  - Format 1 should work (your baseline)
  - Format 11 should also work
  - Use this as your control group

ESPN2 (espn2):
  - Format 1 probably fails or asks for cable login
  - Format 11 (showEvent) should bypass auth ✨
  
ACCN (acc):
  - Format 1 probably fails or asks for cable login
  - Format 11, 12, or 15 might work
  
ESPNews (espnews):
  - Same as ESPN2
  - Format 11 is best bet

ESPNU (espnu):
  - You reported this works
  - Format 1 should succeed
  - Good for comparison testing

========================================
QUICK TEST SCRIPT
========================================

To rapidly test the most promising formats:

#!/bin/bash
# Quick test of priority formats for ESPN2

FIRE_TV="192.168.x.x"
adb connect $FIRE_TV

echo "Testing ESPN2 event..."

# Baseline (should fail)
echo "Format 1: playID only"
adb shell am start -a android.intent.action.VIEW -d "sportscenter://x-callback-url/showWatchStream?playID=PLAY_ID_HERE"
sleep 5

# Magic bullet (should work!)
echo "Format 11: showEvent with simulcast"
adb shell am start -a android.intent.action.VIEW -d "sportscenter://x-callback-url/showEvent?eventId=SIMULCAST_ID_HERE"
sleep 5

# Alternative
echo "Format 15: showAiring"
adb shell am start -a android.intent.action.VIEW -d "sportscenter://x-callback-url/showAiring?airingId=SIMULCAST_ID_HERE"

========================================
WHAT TO REPORT BACK
========================================

Please test and share:

1. ✅/❌ Does Format 11 work for ESPN2?
2. ✅/❌ Does Format 11 work for ACCN?
3. ✅/❌ Does Format 11 work for ESPNews?
4. ⚠️  Does it ask for cable provider login?
5. 📝 Any error messages from ESPN app?
6. 🔍 Differences between airing_id vs simulcast_airing_id?

Critical findings we need:
❓ Can showEvent bypass MVPD authentication?
❓ Does simulcast_airing_id work as eventId?
❓ Is there a pattern to what works vs. fails?

If Format 11 works, we've SOLVED the ESPN2/ACCN/ESPNews problem! 🎉

========================================
DEBUGGING TIPS
========================================

If nothing works:
1. Check ESPN app authentication status
2. Try clearing ESPN app data and re-testing
3. Compare logcat output between ESPN vs ESPN2
4. Test both LIVE and UPCOMING events

To check authentication:
adb shell am start -n com.espn.score_center/com.espn.sportscenter.ui.settings.SettingsActivity

To see app logs:
adb logcat -s ESPN:* SportsCenterApp:*

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
      AND (airing_id IS NOT NULL OR simulcast_airing_id IS NOT NULL)
      AND event_type IN $EVENT_TYPE_FILTER
      $LIVE_NOW_FILTER
    ORDER BY network
    LIMIT $LIMIT
)
GROUP BY network
ORDER BY network
" | tee -a "$OUTPUT_FILE"

echo "" | tee -a "$OUTPUT_FILE"
echo "📋 Review $OUTPUT_FILE and start testing!" | tee -a "$OUTPUT_FILE"
echo "💡 Priority: Test Format 11 (showEvent) on ESPN2/ACCN first!" | tee -a "$OUTPUT_FILE"
echo "🎯 This is our best chance to bypass MVPD authentication!" | tee -a "$OUTPUT_FILE"
