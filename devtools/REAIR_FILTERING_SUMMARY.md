# Re-Air Event Filtering - Implementation Summary

## Overview
Added Re-Air event filtering to ESPN4CC4C to address deeplink authentication issues on Android/Fire TV devices.

## What Changed

### 1. Database Schema (`ingest_watch_graph_all_to_db.py`)
- ✅ Added `is_reair` column to events table (INTEGER: 0 = regular, 1 = re-air)
- ✅ Updated GraphQL query to request `isReAir` field from ESPN API
- ✅ Auto-migration support for existing databases
- ✅ Captures ESPN's boolean flag and converts to SQLite integer

### 2. Event Filtering (`filter_events.py`)
- ✅ Added `exclude_reair` option to filters.ini
- ✅ Default: `exclude_reair = false` (backward compatible - includes re-airs)
- ✅ When enabled, filters out all events where `is_reair = 1`
- ✅ Shows exclusion status in filter summary output

### 3. XMLTV Generation (`xmltv_from_plan.py`)
- ✅ Fetches `is_reair` field from database
- ✅ Fixed `<live>` tag logic: Only adds tag when event is LIVE AND NOT a re-air
- ✅ Prevents misleading "live" indicators on replay content

### 4. Filter Options Generator (`generate_filter_options.py`)
- ✅ Shows Re-Air statistics in output
- ✅ Documents Re-Air filtering in generated filters.ini examples

## Usage

### Step 1: Re-ingest Data (One-Time)
Run the updated ingestion script to capture `isReAir` from ESPN:

```bash
python3 ingest_watch_graph_all_to_db.py --db /path/to/db.sqlite3 --days 3
```

The script will automatically add the `is_reair` column to existing databases.

### Step 2: Check Re-Air Statistics
See what's in your database:

```bash
python3 check_reair_events.py --db /path/to/db.sqlite3
```

Expected output:
```
Event Distribution:
============================================================
  Regular events:    1056 (92.3%)
  Re-Air events:       88 (7.7%)
  Total events:      1144
```

### Step 3: Enable Re-Air Filtering (Optional)
Edit your `filters.ini`:

```ini
[filters]
# ... other filters ...

# Exclude Re-Air events (recommended for Android/Fire TV users)
exclude_reair = true
```

### Step 4: Rebuild Plan
The filter will be applied during plan building:

```bash
python3 build_plan.py --db /path/to/db.sqlite3 --valid-hours 72
```

## Testing

Test the filter without modifying your database:

```bash
python3 test_reair_filter.py /path/to/db.sqlite3
```

This will show:
- How many events would be included/excluded
- Sample Re-Air events that would be filtered
- Verification that filtering logic works correctly

## Statistics from Your Database

Based on your current data (November 15, 2025):
- **Total Events**: 1,144
- **Re-Air Events**: 88 (7.7%)
- **Regular Events**: 1,056 (92.3%)

### Re-Air Distribution by Type:
- `OVER` (completed): 60 events
- `UPCOMING`: 25 events  
- `LIVE`: 3 events

### Networks with Most Re-Airs:
1. ESPNews: 26 events
2. ACCN: 16 events
3. ESPNU: 13 events
4. ESPN2: 13 events
5. SEC Network: 8 events

## Backward Compatibility

✅ **Fully backward compatible**
- Default behavior unchanged (includes re-airs)
- Auto-migration adds column to existing databases
- Existing filters.ini files work without modification
- Only affects behavior when explicitly enabled

## Docker/Container Usage

Add to your `.env` or docker-compose.yml environment:

```bash
# In filters.ini mounted to container
exclude_reair=true
```

The filter will be applied during the automatic refresh cycle.

## Troubleshooting

### Column doesn't exist error
Run migration or re-ingest:
```bash
python3 ingest_watch_graph_all_to_db.py --db /path/to/db.sqlite3 --days 1
```

### Re-Airs still appearing
1. Check your filters.ini has `exclude_reair = true`
2. Verify the filter is loaded: `python3 filter_events.py /path/to/db.sqlite3 filters.ini`
3. Rebuild the plan after changing filters

### Want to see only Re-Airs (for testing)
Not directly supported, but you can query:
```sql
SELECT * FROM events WHERE is_reair = 1;
```

## Files Modified

1. `ingest_watch_graph_all_to_db.py` - Captures isReAir from ESPN API
2. `filter_events.py` - Adds Re-Air filtering logic
3. `xmltv_from_plan.py` - Fixes live tag logic
4. `generate_filter_options.py` - Shows Re-Air stats
5. `filters.ini.example` - Documents new option

## Files Created

1. `check_reair_events.py` - Diagnostic tool for Re-Air events
2. `test_reair_filter.py` - Test suite for filter functionality
3. `filters.ini.example` - Updated example configuration

## Next Steps

1. ✅ Re-ingest data to capture isReAir field
2. ✅ Test filtering with `test_reair_filter.py`
3. ✅ Enable filtering if needed for Android/Fire TV users
4. 📝 Monitor authentication success rates on filtered channels
5. 📝 Consider per-network Re-Air filtering if needed

## API Field Reference

ESPN's `isReAir` field from Watch API:
```
isReAir: Boolean - Indicates whether Airing is a re-air or not
```

This is a dedicated field separate from `type` (LIVE/UPCOMING/OVER/REPLAY).
