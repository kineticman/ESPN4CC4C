# Padding Logic Update - Both Flags Check

## Change Summary
Updated padding logic to check **BOTH** `is_reair` and `is_studio` flags to ensure only truly live sports events get padded.

## Previous Logic (Using Only `is_reair`)
```python
is_reair = e.get("is_reair", 0)
if not padding_live_only or is_reair == 0:
    apply_padding()
```

**Problem:**
- Padded live studio shows unnecessarily (harmless but wasteful)
- Correctly skipped replays

## New Logic (Using Both Flags)
```python
is_reair = e.get("is_reair", 0)
is_studio = e.get("is_studio", 0)

if not padding_live_only or (is_reair == 0 and is_studio == 0):
    apply_padding()
```

**Better:**
- Only pads truly live sports events
- Skips both studio shows AND replays

## Event Types and Padding Behavior

With `PADDING_LIVE_ONLY=true`:

| Event Type | is_reair | is_studio | Padded? | Why |
|------------|----------|-----------|---------|-----|
| Live game | 0 | 0 | ✅ Yes | Might have overtime |
| Live studio show | 0 | 1 | ❌ No | Fixed duration |
| Replay of game | 1 | 0 | ❌ No | ESPN knows actual length |
| Replay of studio | 1 | 1 | ❌ No | Doubly unnecessary |

With `PADDING_LIVE_ONLY=false`:
- All events get padded regardless of flags

## Rationale

**Why skip studio shows?**
- Studio shows (SportsCenter, ESPN FC, etc.) have fixed durations
- Padding them is unnecessary

**Why skip replays?**
- ESPN schedules replays based on actual recorded length
- They already know how long the event ran
- Padding serves no purpose

**Why only pad live sports?**
- Live games can run long (overtime, delays, etc.)
- This is the only scenario where padding adds value

## Files Updated

### 1. build_plan.py
**Lines 320-336:** Updated padding check logic
```python
# Now checks both flags
if not padding_live_only or (is_reair == 0 and is_studio == 0):
    apply_padding()
```

**Line 355:** Updated log field name
```python
non_live_events_skipped=padding_skipped_reair_count  # Was: reair_events_skipped
```

**Line 421:** Added is_studio to individual event logs
```python
is_studio=ev.get("is_studio", 0)  # Added this field
```

### 2. README.md
Updated multiple sections:
- What's New bullet point
- PADDING_LIVE_ONLY description in table
- Content detection explanation
- Log example output

### 3. Documentation Files
Updated all padding documentation:
- PADDING_IMPLEMENTATION.md
- PADDING_VISUAL_GUIDE.md
- QUICK_START.md

Changed references from:
- "skip studio shows" → "skip studio shows and replays"
- "studio_events_skipped" → "non_live_events_skipped"

## Log Output Changes

**Before:**
```json
{
  "event": "padding_summary",
  "events_padded": 127,
  "reair_events_skipped": 8
}
```

**After:**
```json
{
  "event": "padding_summary",
  "events_padded": 127,
  "non_live_events_skipped": 15
}
```

Note: `non_live_events_skipped` now includes BOTH replays AND studio shows.

**Individual event logs now include both flags:**
```json
{
  "event": "event_padded",
  "event_id": "401234567",
  "is_reair": 0,
  "is_studio": 0,
  "original_start": "2024-11-25T19:00:00Z",
  "padded_start": "2024-11-25T18:55:00Z",
  ...
}
```

## Testing

### Verify Correct Behavior
```bash
# After refresh, check logs
docker logs espn4cc4c | grep padding_summary

# Should show:
# - events_padded: N (only live sports)
# - non_live_events_skipped: M (studio + replays)
```

### Check Individual Events
```bash
docker exec espn4cc4c tail -50 /app/logs/plan_builder.jsonl | grep event_padded | jq

# Verify all padded events have:
# "is_reair": 0
# "is_studio": 0
```

### Database Query
```sql
-- Count what's in the database
SELECT 
  is_reair,
  is_studio,
  COUNT(*) as count
FROM events
GROUP BY is_reair, is_studio;

-- Should see all four combinations:
-- 0, 0 = Live sports (these get padded)
-- 0, 1 = Live studio (skipped)
-- 1, 0 = Game replays (skipped)
-- 1, 1 = Studio replays (skipped)
```

## Migration Notes

**Non-breaking change:**
- Existing configs work as-is
- Default behavior (`PADDING_LIVE_ONLY=true`) is now more precise
- No configuration changes needed

**Effect on existing deployments:**
- Will now skip studio shows that were previously being padded
- This is an improvement (less unnecessary padding)
- No negative impact

## Summary

This update makes padding more intelligent and efficient by checking both content type flags. Only truly live sports events (games, matches, competitions broadcast live) get padding. Studio shows and replays are correctly excluded since they don't run long.
