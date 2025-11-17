# Filter Changes & Sticky Lanes Guide

## The Problem

ESPN4CC4C uses "sticky lanes" to maintain consistency when refreshing the schedule. This means:
- Events stay on the same channel across refreshes (good for continuity)
- But when you change filters, previously-planned events remain until they expire (confusing!)

**Example:**
```
1. You have Re-Air events on channels
2. You add exclude_reair=true to filters.ini
3. You run build_plan.py
4. Re-Air events are STILL there! 😕
```

**Why?** The sticky lane system keeps events that are already planned (typically for ~6 hours) to avoid disrupting active viewing.

## Solutions

You have TWO options when changing filters:

### Option 1: Quick Replan (Recommended)

Use the `--force-replan` flag to ignore sticky assignments:

```bash
python3 bin/build_plan.py --db data/db.sqlite3 --valid-hours 72 --force-replan
```

**When to use:**
- ✅ After changing filters.ini
- ✅ Quick and easy
- ✅ Safe - just ignores sticky for one run
- ✅ Default behavior returns on next refresh

**What it does:**
- Ignores the event_lane table for this run
- Assigns events to channels fresh
- Applies current filters immediately
- Sticky behavior returns on next normal run

### Option 2: Nuclear Clear (Thorough)

Use the `clear_sticky.py` script to completely wipe sticky assignments:

```bash
# Preview what would be cleared
python3 bin/clear_sticky.py --db data/db.sqlite3 --dry-run

# Actually clear it
python3 bin/clear_sticky.py --db data/db.sqlite3

# Then rebuild plan
python3 bin/build_plan.py --db data/db.sqlite3 --valid-hours 72
```

**When to use:**
- ✅ Want a complete fresh start
- ✅ Changing multiple filter settings at once
- ✅ Troubleshooting weird channel assignments
- ✅ Major filter restructuring

**What it does:**
- Deletes ALL entries from event_lane table
- Forces next build_plan to start completely fresh
- All events get new channel assignments
- Sticky system starts learning from scratch

## Comparison

| Feature | --force-replan | clear_sticky.py |
|---------|---------------|-----------------|
| Speed | Instant (one command) | Two commands |
| Scope | Single plan run | Permanent until new stickiness builds |
| Safety | Very safe (temporary) | Safe (just clears cache) |
| Use case | Filter changes | Complete reset |
| Sticky returns | Next refresh | Starts rebuilding immediately |

## Typical Workflow

### Scenario 1: Changed One Filter

```bash
# Edit filters.ini
nano filters.ini

# Quick replan
python3 bin/build_plan.py --db data/db.sqlite3 --valid-hours 72 --force-replan
```

### Scenario 2: Major Filter Overhaul

```bash
# Edit filters.ini with many changes
nano filters.ini

# See what sticky assignments exist
python3 bin/clear_sticky.py --db data/db.sqlite3 --dry-run

# Clear them all
python3 bin/clear_sticky.py --db data/db.sqlite3

# Rebuild from scratch
python3 bin/build_plan.py --db data/db.sqlite3 --valid-hours 72
```

### Scenario 3: Docker/Automated Refreshes

In your refresh script or cron job, use `--force-replan` after filter changes:

```bash
#!/bin/bash
# After updating filters.ini in your deployment

# Force fresh planning
python3 /app/bin/build_plan.py \
  --db /app/data/db.sqlite3 \
  --valid-hours 72 \
  --force-replan

# Generate outputs
python3 /app/bin/xmltv_from_plan.py --db /app/data/db.sqlite3 --out /app/out/epg.xml
python3 /app/bin/m3u_from_plan.py --db /app/data/db.sqlite3 --out /app/out/playlist.m3u
```

## Understanding Sticky Behavior

### What is "Stickiness"?

The `event_lane` table tracks which events were assigned to which channels. On refresh:
1. Build_plan checks event_lane table
2. If an event was on channel 5 before → tries to keep it on channel 5
3. This prevents channels from "shuffling" during refreshes
4. Provides consistency for viewers

### Why Filters Don't Apply Immediately

When you change filters:
1. Build_plan loads events passing new filters ✅
2. Build_plan sees these events were on channels before (in event_lane) ✅
3. Build_plan keeps them on same channels (sticky) ❌
4. Filtered-out events stay until they expire naturally ❌

### How --force-replan Fixes This

```python
if args.force_replan:
    # Skip loading sticky map
    sticky_map = {}
else:
    # Normal: load and use sticky assignments
    sticky_map = load_event_lane_map(conn)
```

With `--force-replan`:
- Sticky map is empty
- All events get fresh channel assignments
- Current filters fully applied
- Next refresh without flag → sticky returns

## Frequently Asked Questions

### Q: Do I need to use --force-replan every time I change filters?

**A:** Only the first time after the change. Once events are planned with new filters, sticky will maintain them correctly.

### Q: Will --force-replan disrupt viewers?

**A:** Possibly. Events may move to different channels. Use during low-traffic times or use clear_sticky.py + plan for scheduled changes.

### Q: How often should I clear sticky assignments?

**A:** Rarely. Only when:
- Major filter changes
- Troubleshooting channel assignment issues
- Want to completely reorganize channels

### Q: Can I automate --force-replan after filter changes?

**A:** Yes! You could:
1. Watch filters.ini for changes (inotify/watchdog)
2. Auto-run with --force-replan when changed
3. Or just use it in your manual update workflow

### Q: What happens to event_lane after --force-replan?

**A:** The table stays intact. The flag just ignores it for that one run. On next normal refresh, new assignments will be saved to event_lane.

### Q: What happens to event_lane after clear_sticky.py?

**A:** Table is emptied. Build_plan will populate it again with new assignments as it runs.

## Examples

### Example 1: Exclude Re-Air Events

```bash
# Add to filters.ini
exclude_reair = true

# Apply immediately
python3 bin/build_plan.py --db data/db.sqlite3 --valid-hours 72 --force-replan

# Verify
python3 bin/check_reair_events.py --db data/db.sqlite3
```

### Example 2: Change Network Filters

```bash
# Edit filters.ini
enabled_networks = ESPN,ESPN2,ESPN+

# Clear and rebuild
python3 bin/clear_sticky.py --db data/db.sqlite3
python3 bin/build_plan.py --db data/db.sqlite3 --valid-hours 72
```

### Example 3: Testing Different Filter Combinations

```bash
# Test filter #1
nano filters.ini  # Edit
python3 bin/build_plan.py --db data/db.sqlite3 --force-replan
# Review results...

# Test filter #2
nano filters.ini  # Edit again
python3 bin/build_plan.py --db data/db.sqlite3 --force-replan
# Review results...

# Once happy, do a normal refresh
python3 bin/build_plan.py --db data/db.sqlite3 --valid-hours 72
```

## Technical Details

### Sticky Lane Table Schema

```sql
CREATE TABLE event_lane(
  event_id       TEXT PRIMARY KEY,
  channel_id     INTEGER,
  pinned_at_utc  INTEGER,
  last_seen_utc  INTEGER
);
```

### How Stickiness Works in Code

```python
# Load sticky map from event_lane
sticky_map = {"event123": "5", "event456": "12", ...}

# When assigning event
preferred_channel = sticky_map.get(event_id)
if preferred_channel and is_free(preferred_channel):
    assign_to(preferred_channel)  # Use sticky
else:
    assign_to(find_first_free())  # Find new channel
```

### Clear Sticky Implementation

```python
# clear_sticky.py simply does:
conn.execute("DELETE FROM event_lane")
conn.commit()
```

Simple but effective!

## Best Practices

1. **Always preview with --dry-run** before using clear_sticky.py
2. **Use --force-replan for quick filter tweaks** 
3. **Use clear_sticky.py for major reorganizations**
4. **Document your filter changes** so team knows why assignments changed
5. **Schedule major changes during low-traffic periods**
6. **Test filter changes in dev environment first** if possible

## Troubleshooting

### Problem: Filters still not applying after --force-replan

**Check:**
```bash
# Verify filters.ini is being read
python3 bin/filter_events.py data/db.sqlite3 filters.ini

# Check if filtered events exist at all
python3 bin/generate_filter_options.py data/db.sqlite3
```

### Problem: Channels keep shuffling on every refresh

**Solution:** Stop using --force-replan! It's meant for one-time use after filter changes.

### Problem: Want to see what's in event_lane

**Query:**
```bash
sqlite3 data/db.sqlite3 "SELECT * FROM event_lane LIMIT 20"
```

## Summary

**Quick checklist when changing filters:**

- [ ] Edit filters.ini with your changes
- [ ] Run: `python3 bin/build_plan.py --db db.sqlite3 --force-replan`
- [ ] Verify events are filtered correctly
- [ ] Next refresh runs normally (no flag needed)

**For complete reset:**

- [ ] Run: `python3 bin/clear_sticky.py --db db.sqlite3 --dry-run` (preview)
- [ ] Run: `python3 bin/clear_sticky.py --db db.sqlite3` (actually clear)
- [ ] Run: `python3 bin/build_plan.py --db db.sqlite3` (rebuild)
- [ ] Sticky system starts fresh

That's it! 🎯
