# ESPN4CC4C Event Padding Implementation

## Overview

This implementation adds configurable padding to live sports events to handle games that run long. Padding is applied during the planning phase (`build_plan.py`), which means:

- Raw ESPN event data in the database remains unchanged
- Filtering sees original event times
- Only the virtual channel schedule gets padded times
- Padding can break grid alignment (events can start at :03, :58, etc.)

## Environment Variables

### `PADDING_START_MINS` (default: 0)
Minutes of padding to add **before** event start time.
- Example: `PADDING_START_MINS=5` means a 7:00 PM game starts at 6:55 PM in your guide
- Useful for catching pre-game shows or early starts
- Most users set this to 0-5 minutes

### `PADDING_END_MINS` (default: 0)
Minutes of padding to add **after** event end time.
- Example: `PADDING_END_MINS=30` means a 3-hour game scheduled to end at 10:00 PM won't cut off until 10:30 PM
- This is the critical one - games often run long
- Recommended: 30-60 minutes for most sports

### `PADDING_LIVE_ONLY` (default: true)
Whether to only pad live sports events and skip studio shows.
- `true`: Only pad events where `event_type != "STUDIO"`
- `false`: Pad all events regardless of type
- Recommended: Keep this as `true` since studio shows have fixed durations

## How It Works

### 1. Event Type Detection
The system checks ESPN's `event_type` field for each event:
- `"LIVE"` → Live sports event, gets padded (if PADDING_LIVE_ONLY=true)
- `"STUDIO"` → Studio show, skipped (if PADDING_LIVE_ONLY=true)
- `"OVER"` → Completed event, gets padded
- Empty/unknown → Treated as live (safer to pad than not)

### 2. Padding Application
In `build_plan.py`, after loading events from DB but before lane assignment:
```python
original_start = 7:00 PM
original_end = 10:00 PM

# With PADDING_START_MINS=5, PADDING_END_MINS=30:
padded_start = 6:55 PM  (original - 5 mins)
padded_end = 10:30 PM   (original + 30 mins)
```

### 3. Conflict Resolution
Padded events follow these rules:
- **Padding wins over placeholders**: If padding causes an event to overlap a placeholder (gap filler), the placeholder is truncated or removed
- **Events don't overlap events**: If two events would overlap even with padding, the later event is dropped (normal behavior)
- **Sticky lanes preserved**: Events maintain their lane assignments across refreshes even with padding changes

### 4. Logging
The system logs padding activity in `/app/logs/plan_builder.jsonl`:

**Summary log** (one per build):
```json
{
  "event": "padding_summary",
  "padding_start_mins": 5,
  "padding_end_mins": 30,
  "padding_live_only": true,
  "events_padded": 127,
  "studio_events_skipped": 8,
  "total_events": 135
}
```

**Individual event logs** (one per padded event):
```json
{
  "event": "event_padded",
  "event_id": "401234567",
  "event_type": "LIVE",
  "original_start": "2024-11-25T19:00:00+00:00",
  "original_end": "2024-11-25T22:00:00+00:00",
  "padded_start": "2024-11-25T18:55:00+00:00",
  "padded_end": "2024-11-25T22:30:00+00:00",
  "channel_id": "eplus03"
}
```

## Configuration Examples

### Conservative (recommended for most users)
```yaml
environment:
  - PADDING_START_MINS=0
  - PADDING_END_MINS=30
  - PADDING_LIVE_ONLY=true
```
- No pre-padding
- 30 minutes of overrun protection
- Only live sports, skip studio shows

### Aggressive (for sports that often run very long)
```yaml
environment:
  - PADDING_START_MINS=5
  - PADDING_END_MINS=60
  - PADDING_LIVE_ONLY=true
```
- 5 minutes early start
- 60 minutes of overrun protection
- Great for football, baseball

### Pad Everything (including studio content)
```yaml
environment:
  - PADDING_START_MINS=5
  - PADDING_END_MINS=15
  - PADDING_LIVE_ONLY=false
```
- Pads all events regardless of type
- Not usually recommended

### Disabled (default)
```yaml
environment:
  - PADDING_START_MINS=0
  - PADDING_END_MINS=0
```
- No padding applied
- Events use ESPN's exact times

## Implementation Details

### Files Modified

**`bin/build_plan.py`**
- Added CLI arguments: `--padding-start-mins`, `--padding-end-mins`, `--padding-all`
- Modified `build_plan()` function to accept padding parameters
- Added padding logic in event normalization loop (before lane assignment)
- Added padding summary and per-event logging
- Version bumped to `2.1.7-padding`

**`bin/refresh_in_container.py`**
- Added environment variable reading: `PADDING_START_MINS`, `PADDING_END_MINS`, `PADDING_LIVE_ONLY`
- Modified Step 3 build command to pass padding parameters
- Added padding config to console output

### Design Decisions

1. **Padding happens at planning time, not ingest time**
   - Keeps raw ESPN data pristine in database
   - Allows changing padding without re-ingesting
   - Filters see original times (more accurate filtering)

2. **Padding can break grid alignment**
   - Events normally snap to :00/:30 boundaries
   - Padded events keep their exact offset times
   - This is intentional - better to catch all of a 7:03 PM start than miss the first 3 minutes

3. **Studio detection uses event_type field**
   - ESPN provides this in their API
   - Simple and reliable
   - Fallback: treat unknown types as live (safer)

4. **Padded events win over placeholders**
   - Placeholders are just gap fillers
   - Real content should take priority
   - User requested this behavior explicitly

5. **Comprehensive logging**
   - Summary stats for auditing
   - Per-event detail for troubleshooting
   - Both go to plan_builder.jsonl

## Testing & Validation

### Check if padding is working:

1. **Look at the logs**:
```bash
docker logs espn4cc4c | grep padding_summary
```

Expected output:
```
{"event":"padding_summary","padding_start_mins":5,"padding_end_mins":30,"padding_live_only":true,"events_padded":127,"studio_events_skipped":8,"total_events":135}
```

2. **Check the EPG times**:
Open `/out/epg.xml` and look at a `<programme>` tag:
```xml
<programme start="20241125185500 +0000" stop="20241125223000 +0000" channel="eplus03">
```
If ESPN says 7:00-10:00, you should see 6:55-10:30 (with 5min start + 30min end padding).

3. **Check the plan builder log**:
```bash
docker exec espn4cc4c tail -100 /app/logs/plan_builder.jsonl | grep event_padded
```

### Troubleshooting:

**"My events aren't getting padded"**
- Check that `PADDING_START_MINS` or `PADDING_END_MINS` > 0
- Verify the environment variables are set in docker-compose
- Check if events are being filtered out before planning
- Look for `padding_summary` in logs to see how many events were padded

**"Studio shows are getting padded when they shouldn't"**
- Verify `PADDING_LIVE_ONLY=true` is set
- Check the `event_type` field in your events table
- Some ESPN content might not have `event_type="STUDIO"` properly set

**"Events are overlapping after adding padding"**
- This is expected if padding causes conflicts
- The later event will be dropped (logged as `event_overlap_detected`)
- Consider reducing `PADDING_END_MINS` or adding more `LANES`

**"Padding broke my filter audit"**
- Filter audit sees events in the database (original times)
- Plan/guide uses padded times
- This is intentional and correct behavior

## Future Enhancements (not implemented)

Possible future additions:
- Per-sport padding (e.g., football gets 60min, basketball gets 30min)
- Dynamic padding based on league (NCAA vs NFL)
- Padding only for specific networks
- Smart padding based on historical overrun data
- Padding configuration via INI file

## Migration Notes

This is a **non-breaking change**:
- Default behavior: no padding (PADDING_START_MINS=0, PADDING_END_MINS=0)
- Existing deployments continue to work unchanged
- No database schema changes required
- No changes to filtering logic
- Opt-in by setting environment variables

Users can enable padding incrementally:
1. Start with just `PADDING_END_MINS=15` 
2. Monitor logs and EPG output
3. Gradually increase to desired levels
4. Add `PADDING_START_MINS` if needed
