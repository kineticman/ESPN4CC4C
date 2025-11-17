# Sticky Lane Management - Implementation Summary

## Overview

Added two solutions to handle filter changes with ESPN4CC4C's sticky lane system:

1. **`--force-replan` flag** - Quick, one-time override of sticky lanes
2. **`clear_sticky.py` script** - Nuclear option to completely reset sticky assignments

## Problem Statement

The sticky lane system maintains event-to-channel assignments across refreshes for consistency. However, when users change filters:

- Filtered-out events remain on channels (from previous assignments)
- New filters don't appear to work immediately
- Users are confused why their filter changes aren't applying

**Root cause:** The `event_lane` table preserves old assignments, and `build_plan.py` respects them even when events are now filtered.

## Solution 1: --force-replan Flag

### Implementation

**File:** `build_plan.py`

Added command-line argument:
```python
ap.add_argument(
    "--force-replan",
    action="store_true",
    help="ignore sticky lanes and force fresh planning (use after filter changes)",
)
```

Modified sticky map loading:
```python
if args.force_replan:
    jlog(
        event="force_replan_enabled",
        message="Ignoring sticky lanes - forcing fresh plan",
    )
    sticky_map = {}
else:
    seeded_sticky = _seed_event_lane_from_latest_plan(conn)
    sticky_map = _load_event_lane_map(conn)
```

### Usage

```bash
# After changing filters
python3 bin/build_plan.py --db data/db.sqlite3 --valid-hours 72 --force-replan
```

### Behavior

- Skips loading the event_lane table for this run
- All events get fresh channel assignments
- Filters apply immediately
- Next refresh without flag returns to normal sticky behavior
- Event_lane table is updated with new assignments

### When to Use

- ✅ After changing 1-2 filter settings
- ✅ Quick filter testing
- ✅ Want immediate filter application
- ✅ Temporary override needed

## Solution 2: clear_sticky.py Script

### Implementation

**File:** `clear_sticky.py` (new)

Main function:
```python
def clear_sticky_lanes(db_path: str, dry_run: bool = False):
    """Clear the event_lane table to reset sticky lane assignments"""
    # Count current assignments
    # Optionally preview (dry-run)
    # DELETE FROM event_lane
    # Return results
```

Features:
- Dry-run mode to preview changes
- JSON output option
- Shows sample assignments before clearing
- Counts and reports clearing results

### Usage

```bash
# Preview what will be cleared
python3 bin/clear_sticky.py --db data/db.sqlite3 --dry-run

# Actually clear
python3 bin/clear_sticky.py --db data/db.sqlite3

# Then rebuild
python3 bin/build_plan.py --db data/db.sqlite3 --valid-hours 72
```

### Behavior

- Deletes all rows from event_lane table
- Forces next build_plan to start completely fresh
- All events get new channel assignments
- Sticky system starts learning from scratch
- Permanent until new sticky assignments build up

### When to Use

- ✅ Major filter overhaul (many changes)
- ✅ Complete channel reorganization
- ✅ Troubleshooting assignment issues
- ✅ Starting fresh after extensive testing

## Files Modified/Created

### Modified Files

1. **build_plan.py**
   - Added `--force-replan` argument
   - Modified sticky map loading logic
   - Added logging for force-replan mode

### New Files

1. **clear_sticky.py**
   - Script to clear event_lane table
   - Dry-run mode
   - JSON output support
   - User-friendly output

2. **FILTER_CHANGES_GUIDE.md**
   - Comprehensive guide to filter changes
   - When to use each solution
   - Examples and scenarios
   - Troubleshooting tips

3. **STICKY_LANES_QUICK_REF.txt**
   - Quick reference card
   - Decision tree
   - Common scenarios
   - Command examples

## Comparison Matrix

| Aspect | --force-replan | clear_sticky.py |
|--------|---------------|-----------------|
| **Commands** | 1 (integrated) | 2 (clear + rebuild) |
| **Speed** | Instant | ~2 seconds |
| **Scope** | Single run | Permanent reset |
| **Safety** | Very safe | Safe (just cache) |
| **Persistence** | Temporary | Until rebuilt |
| **Sticky returns** | Next refresh | Immediately rebuilds |
| **Use case** | Quick fixes | Major changes |
| **Reversible** | Auto (next run) | Manual (rebuild) |

## User Workflows

### Workflow 1: Quick Filter Change

```bash
# 1. Edit filter
nano filters.ini

# 2. Apply immediately
python3 bin/build_plan.py --db data/db.sqlite3 --valid-hours 72 --force-replan

# 3. Done! Next refresh runs normally
```

### Workflow 2: Major Filter Overhaul

```bash
# 1. Edit filters
nano filters.ini

# 2. Preview sticky state
python3 bin/clear_sticky.py --db data/db.sqlite3 --dry-run

# 3. Clear sticky assignments
python3 bin/clear_sticky.py --db data/db.sqlite3

# 4. Rebuild from scratch
python3 bin/build_plan.py --db data/db.sqlite3 --valid-hours 72

# 5. Verify results
```

### Workflow 3: Filter Testing

```bash
# Test different filter configurations
for config in filter_*.ini; do
    cp $config filters.ini
    python3 bin/build_plan.py --db data/db.sqlite3 --force-replan
    # Review and compare...
done

# Once satisfied, do final refresh
python3 bin/build_plan.py --db data/db.sqlite3 --valid-hours 72
```

## Docker/Container Integration

### Environment Variable (Future Enhancement)

Could add:
```bash
FORCE_REPLAN=true  # Auto-applies --force-replan flag
```

### Automated Workflow

```bash
#!/bin/bash
# refresh_with_filters.sh

# If filters changed, force replan
if [ "$FILTERS_CHANGED" = "true" ]; then
    python3 /app/bin/build_plan.py \
        --db /app/data/db.sqlite3 \
        --valid-hours 72 \
        --force-replan
else
    python3 /app/bin/build_plan.py \
        --db /app/data/db.sqlite3 \
        --valid-hours 72
fi
```

## Technical Details

### Event Lane Table

```sql
CREATE TABLE event_lane(
  event_id       TEXT PRIMARY KEY,
  channel_id     INTEGER,
  pinned_at_utc  INTEGER,
  last_seen_utc  INTEGER
);
```

### Normal Sticky Behavior

```python
sticky_map = load_event_lane_map(conn)  # {"event123": "5", ...}

for event in events:
    preferred_channel = sticky_map.get(event.id)
    if preferred_channel and is_free(preferred_channel):
        assign_to(preferred_channel)  # Use sticky
    else:
        assign_to(find_first_free())  # Find new channel
```

### With --force-replan

```python
sticky_map = {}  # Empty map, no preferences

for event in events:
    assign_to(find_first_free())  # All fresh assignments
```

### With clear_sticky.py

```python
# Simply wipes the table
conn.execute("DELETE FROM event_lane")
conn.commit()
```

## Testing

### Test Case 1: --force-replan

```bash
# Setup: Have existing plan with events
sqlite3 data/db.sqlite3 "SELECT COUNT(*) FROM event_lane"  # Should have rows

# Action: Run with --force-replan
python3 bin/build_plan.py --db data/db.sqlite3 --force-replan

# Verify: Events reassigned, filters applied
# event_lane table still has rows (updated with new assignments)
```

### Test Case 2: clear_sticky.py

```bash
# Setup: Have existing sticky assignments
sqlite3 data/db.sqlite3 "SELECT COUNT(*) FROM event_lane"  # e.g., 150 rows

# Action: Dry run
python3 bin/clear_sticky.py --db data/db.sqlite3 --dry-run
# Should show: "Would clear 150 sticky lane assignments"

# Action: Actual clear
python3 bin/clear_sticky.py --db data/db.sqlite3
# Should show: "Cleared 150 sticky lane assignments"

# Verify: Table empty
sqlite3 data/db.sqlite3 "SELECT COUNT(*) FROM event_lane"  # 0 rows

# Rebuild
python3 bin/build_plan.py --db data/db.sqlite3

# Verify: New assignments created
sqlite3 data/db.sqlite3 "SELECT COUNT(*) FROM event_lane"  # New rows
```

## Known Limitations

### --force-replan

- Must be used manually each time filters change
- No automatic detection of filter changes
- Users might forget to use it

### clear_sticky.py

- Requires two commands (clear + rebuild)
- More disruptive than --force-replan
- Overkill for small filter changes

## Future Enhancements

### Automatic Filter Change Detection

```python
# Store filter hash in plan_meta
filter_hash = hashlib.sha256(filter_config_text.encode()).hexdigest()

# Compare on next run
last_hash = load_filter_hash_from_db()
if filter_hash != last_hash:
    # Automatically force replan
    sticky_map = {}
```

### Sticky TTL

```python
# Add expiry to event_lane
# Auto-ignore entries older than X hours
```

### Per-Network Sticky Reset

```bash
# Clear sticky for specific networks only
python3 bin/clear_sticky.py --db db.sqlite3 --networks ESPNews,ACCN
```

## Documentation

All documentation provided in:

1. **FILTER_CHANGES_GUIDE.md** - Complete guide with examples
2. **STICKY_LANES_QUICK_REF.txt** - Quick reference card
3. **This file** - Technical implementation details

## Migration Path

No migration needed! Both features are:
- ✅ Backward compatible
- ✅ Optional (opt-in)
- ✅ Non-breaking
- ✅ Safe to deploy immediately

## Success Criteria

✅ Users can apply filter changes immediately
✅ Two clear options for different scenarios
✅ Comprehensive documentation
✅ Safe, reversible operations
✅ Minimal code changes
✅ Easy to understand and use

## Deployment

1. Copy updated `build_plan.py` to `bin/`
2. Copy new `clear_sticky.py` to `bin/`
3. Copy documentation to `docs/`
4. Update main README to reference filter change guide
5. Announce to users with examples

Done! 🎯
