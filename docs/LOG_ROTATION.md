# Log Rotation Implementation

## Problem
Log files growing to 45-90MB each:
- `plan_builder.jsonl` - 45MB
- `refresh.log` - 47MB
- `cron_refresh.log` - 506KB

This is unsustainable and can fill up disk space over time.

## Solution
Two-pronged approach for comprehensive log management:

### 1. Rotating File Handler (Proactive)
Added Python's built-in `RotatingFileHandler` to `build_plan.py`.

**How it works:**
- Automatically rotates logs when they hit 10MB
- Keeps 3 backup files (plan_builder.jsonl, .1, .2, .3)
- Max total size: 40MB for plan_builder logs (10MB × 4 files)
- Happens automatically as logs are written

**Changes in build_plan.py:**
```python
# Added import
from logging.handlers import RotatingFileHandler

# Replaced simple file append with rotating handler
_log_handler = RotatingFileHandler(
    LOG_PATH,
    maxBytes=10 * 1024 * 1024,  # 10 MB per file
    backupCount=3,  # Keep 3 old files
    encoding="utf-8",
)
```

### 2. Weekly Cleanup Job (Defensive)
Added scheduled cleanup job to `vc_resolver_FINAL.py` that runs weekly.

**How it works:**
- Runs every Sunday at 03:30 (after refresh + vacuum)
- Scans `/app/logs` for old log files
- Keeps newest 3 of each type, deletes older ones
- Handles all log file patterns:
  - `plan_builder.jsonl*`
  - `refresh.log*`
  - `cron_refresh.log*`
  - `cron_vacuum.log*`

**Changes in vc_resolver_FINAL.py:**
```python
def cleanup_old_logs(source: str = "auto"):
    """Clean up old log files, keeping only the 3 most recent of each type."""
    # Scans log directory
    # Keeps newest 3 files per pattern
    # Deletes older files
    # Logs what was cleaned up

# Added to scheduler
scheduler.add_job(
    cleanup_old_logs,
    CronTrigger(day_of_week='sun', hour=3, minute=30),
    id='log_cleanup_job',
    kwargs={"source": "auto"},
)
```

## Expected Results

### Before
```
logs/
├── plan_builder.jsonl    (45 MB)
├── refresh.log           (47 MB)
├── cron_refresh.log      (506 KB)
└── cron_vacuum.log       (40 B)
Total: ~92 MB
```

### After (Steady State)
```
logs/
├── plan_builder.jsonl    (10 MB)
├── plan_builder.jsonl.1  (10 MB)
├── plan_builder.jsonl.2  (10 MB)
├── plan_builder.jsonl.3  (10 MB)
├── refresh.log           (varies, cleaned weekly)
├── refresh.log.1         (varies, cleaned weekly)
├── refresh.log.2         (varies, cleaned weekly)
├── cron_refresh.log      (<1 MB)
└── cron_vacuum.log       (<1 KB)
Total: ~40-50 MB max
```

## Weekly Schedule (Sunday 3:00 AM)
```
03:00 - Database Refresh (runs daily, but shown here in Sunday context)
03:10 - Database VACUUM (weekly)
03:30 - Log Cleanup (weekly) ← NEW
```

## Files Modified

1. **build_plan.py**
   - Added `RotatingFileHandler` import
   - Replaced simple file writing with rotating logger
   - Version bumped to `2.1.7-padding-logrotate`

2. **vc_resolver_FINAL.py**
   - Added `cleanup_old_logs()` function
   - Added log cleanup job to scheduler
   - Updated scheduler startup message

## Testing

### Verify Rotating Handler Works
```bash
# Watch plan_builder.jsonl size
watch -n 1 'ls -lh /app/logs/plan_builder.jsonl*'

# Should see:
# - plan_builder.jsonl grows to 10MB
# - Then rotates to .1
# - New plan_builder.jsonl starts fresh
```

### Verify Weekly Cleanup
```bash
# Check scheduler log
docker logs espn4cc4c | grep "log cleanup"

# Should see on Sundays:
# "Starting log cleanup..."
# "Cleaned up old log: /app/logs/xxx"
# "Log cleanup completed: removed N old log files"
```

### Manual Cleanup Test
```bash
# Trigger cleanup immediately (don't wait for Sunday)
docker exec espn4cc4c python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, '/app/bin')
from vc_resolver import cleanup_old_logs
cleanup_old_logs('manual')
"
```

## Benefits

✅ **Automatic rotation** - No manual intervention needed
✅ **Predictable disk usage** - Max ~50MB for all logs combined
✅ **Weekly cleanup** - Catches any logs that don't rotate automatically
✅ **Preserves history** - Keeps 3 rotations (recent enough for debugging)
✅ **Non-breaking** - Existing log patterns work the same

## Migration Notes

When you first deploy:
1. Existing large logs will remain until weekly cleanup
2. New logs will start rotating immediately
3. First Sunday cleanup will remove old files
4. After first week, logs stabilize at ~50MB total

## If You Need to Adjust

**Change rotation size:**
```python
maxBytes=20 * 1024 * 1024,  # 20 MB instead of 10 MB
```

**Change number of backups:**
```python
backupCount=5,  # Keep 5 old files instead of 3
```

**Change cleanup schedule:**
```python
CronTrigger(day='*', hour=3, minute=30),  # Daily instead of weekly
```

## Other Logs to Consider

If `refresh.log` is still large, you can add rotation there too:
- Likely written by `refresh_in_container.py`
- Would need similar `RotatingFileHandler` treatment
- Or just let weekly cleanup handle it

Currently focusing on `plan_builder.jsonl` since it's the biggest and most active.
