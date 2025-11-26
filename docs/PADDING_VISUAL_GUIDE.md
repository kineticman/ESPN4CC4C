# Event Padding Visual Example

## Without Padding (Current Behavior)

```
Timeline:  6:45    7:00           10:00   10:15   10:30
           ├───────┼───────────────┼───────┼───────┤
           │       │  Game Runs    │       │       │
Lane 1:    [  Gap ][ ESPN Game    ][ Gap  ][ Next ]
                   ^               ^
                   ESPN Start      ESPN End
                   
Problem: Game goes into overtime until 10:20 PM
         → Recording stops at 10:00 PM
         → You miss the ending! 😢
```

## With Padding (New Feature)

```
Configuration: PADDING_START_MINS=5, PADDING_END_MINS=30

Timeline:  6:45   6:55  7:00           10:00  10:30   10:45
           ├──────┼─────┼───────────────┼──────┼───────┤
           │      │     │  Game Runs    │      │       │
Lane 1:    [ Gap  ][ ESPN Game (Padded) ][ Gap ][ Next ]
                  ^                      ^
                  Padded Start           Padded End
                  (6:55)                 (10:30)
                  
Result: Game goes into overtime until 10:20 PM
        → Recording continues until 10:30 PM
        → You catch the whole game! 🎉
```

## How Padding Affects Grid Alignment

### Normal Grid Alignment (Without Padding)
```
All events snap to :00 or :30 minute boundaries:

6:00 ────┬──── 6:30 ────┬──── 7:00 ────┬──── 7:30
         │              │              │
    [ Event snaps  ][ Event snaps  ][ Event snaps ]
      to 6:00          to 6:30          to 7:00
```

### With Padding (Grid Alignment Can Break)
```
Padded events keep their exact time offsets:

6:00 ────┬──── 6:30 ────┬──── 7:00 ────┬──── 7:30
         │              │   ^           │
         │              │   │           │
    [ Event starts ]    │   │       [ Event ]
      at 6:25           │   ESPN says 7:03
                        │   → Padded to 6:58
                        │      (exact -5 mins)
                        └── Padding preserves offset
```

**Why this matters:**
- ESPN often schedules games at odd times (7:03, 7:08, etc.)
- Without padding: Game gets clamped to 7:00, you miss first 3 minutes
- With padding: Game starts at 6:58 (7:03 - 5min), you catch everything

## Studio Show Handling

### With PADDING_LIVE_ONLY=true (Recommended)

```
Event Type Detection:

┌─────────────────────┐
│ ESPN Event Data     │
│ event_type="LIVE"   │  → PADDED
│ (Basketball Game)   │     6:55 ────────── 10:30
└─────────────────────┘     (Original: 7:00-10:00)

┌─────────────────────┐
│ ESPN Event Data     │
│ is_studio=1 │  → NOT PADDED
│ (SportsCenter)      │     8:00 ── 8:30
└─────────────────────┘     (Exact ESPN times)

Why? Studio shows have fixed durations.
     No need to pad a 30-minute show.
```

## Conflict Resolution

### Padding vs Placeholder (Padding Wins)
```
Before Padding:
Lane 1:  [ Game 1 ][ Placeholder ][ Game 2 ]
         7:00-9:00  9:00-9:30      9:30-11:00

After Padding (PADDING_END_MINS=45):
Lane 1:  [ Game 1 (Extended) ][ Game 2 ]
         7:00-9:45              9:45-11:00
                   ^
                   Placeholder removed
                   (padded event won)
```

### Event vs Event Overlap (Earlier Wins)
```
Before Padding:
Lane 1:  [ Game 1 ][ Game 2 ]
         7:00-9:00  9:00-11:00

After Padding (PADDING_END_MINS=30 on both):
Lane 1:  [ Game 1 (Extended) ]
         7:00-9:30
         
         Game 2 DROPPED (logged as event_overlap_detected)
         Reason: Can't fit both games with padding
         
Solution: Add more LANES or reduce PADDING_END_MINS
```

## Real-World Example

### College Football Saturday

```
Configuration:
  PADDING_START_MINS=5
  PADDING_END_MINS=60
  PADDING_LIVE_ONLY=true

ESPN Schedule:
  12:00 PM - GameDay (Studio)    is_studio=1
   1:00 PM - Ohio State vs Michigan (Live)  event_type="LIVE"
   4:30 PM - Alabama vs Auburn (Live)       event_type="LIVE"

Your Guide (After Padding):
  12:00 PM - 1:00 PM   GameDay (no padding - studio show)
  12:55 PM - 5:00 PM   Ohio State vs Michigan (5min early + 60min late)
   4:25 PM - 8:30 PM   Alabama vs Auburn (5min early + 60min late)

Result:
  ✅ GameDay records exactly 1 hour (studio show)
  ✅ Ohio State game catches pre-game + potential 4-hour marathon
  ✅ Alabama game catches pre-game + potential 4-hour marathon
  ✅ No cutoffs during exciting finishes!
```

## Logging Example

When you check the logs after a refresh:

```json
// Summary (one per build)
{
  "event": "padding_summary",
  "padding_start_mins": 5,
  "padding_end_mins": 30,
  "events_padded": 42,           ← Live sports that got padding
  "non_live_events_skipped": 3,    ← Studio shows skipped
  "total_events": 45
}

// Individual event (one per padded event)
{
  "event": "event_padded",
  "event_id": "401234567",
  "event_type": "LIVE",
  "original_start": "2024-11-25T19:00:00Z",  ← ESPN's time
  "original_end": "2024-11-25T22:00:00Z",
  "padded_start": "2024-11-25T18:55:00Z",    ← Your guide's time
  "padded_end": "2024-11-25T22:30:00Z",
  "channel_id": "eplus03"
}
```

## Settings Cheat Sheet

```
┌─────────────────────────────────────────────────────────┐
│ Use Case              │ START │  END  │ LIVE_ONLY       │
├───────────────────────┼───────┼───────┼─────────────────┤
│ Default (no padding)  │   0   │   0   │  true           │
│ Conservative          │   0   │  30   │  true           │
│ Recommended           │   5   │  30   │  true           │
│ Football/Baseball     │   5   │  60   │  true           │
│ Aggressive            │  10   │  90   │  true           │
│ Everything            │   5   │  30   │  false          │
└─────────────────────────────────────────────────────────┘

START: Minutes before ESPN start time
END:   Minutes after ESPN end time  
LIVE_ONLY: Skip studio shows?
```
