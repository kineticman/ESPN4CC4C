#!/usr/bin/env python3
# file: bin/build_plan.py
# ESPN Clean v2.1 — canonical plan builder (events -> plan_run/plan_slot)
# Version with "sticky lanes" via event_lane table
# PATCHED: Fixed event duplication, grid alignment, and channel naming

import argparse, os, json, sqlite3, hashlib
try:
    from version import get_version, VERSION as BUILD_VERSION
    RUNTIME_VERSION = get_version()
except Exception:
    BUILD_VERSION = "unknown"
    RUNTIME_VERSION = "unknown"

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

try:
    from config import (
        BUILDER_DEFAULT_TZ as CFG_TZ,
        BUILDER_DEFAULT_VALID_HOURS as CFG_VALID_HOURS,
        BUILDER_DEFAULT_MIN_GAP_MINS as CFG_MIN_GAP_MINS,
        BUILDER_DEFAULT_LANES as CFG_LANES,
        CHANNEL_START_CHNO as CFG_CHANNEL_START_CHNO,
    )
except Exception:
    CFG_TZ = "America/New_York"
    CFG_VALID_HOURS = 72
    CFG_MIN_GAP_MINS = 5
    CFG_LANES = 40
    CFG_CHANNEL_START_CHNO = 20010

VERSION = "2.1.1-sticky-patched"
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "plan_builder.jsonl")
STICKY_GRACE = timedelta(seconds=0)  # lane must be free at event start

def jlog(**kv):
    kv = {"ts": datetime.now(timezone.utc).isoformat(), "mod":"build_plan", **kv}
    line = json.dumps(kv, ensure_ascii=False)
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line+"\n")
    except Exception:
        pass

def connect_db(path:str)->sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn

def make_default_lanes(n:int=40, start_chno:int=None):
    if start_chno is None:
        start_chno = CFG_CHANNEL_START_CHNO
    lanes = []
    for i in range(1, n+1):
        # PATCHED: Consistent naming format
        lanes.append((f"eplus{i:02d}", start_chno + (i-1), f"ESPN+ EPlus {i}", "ESPN+ VC"))
    return lanes

def seed_channels_if_empty(conn:sqlite3.Connection, nlanes:int=40):
    cur = conn.execute("SELECT COUNT(*) AS n FROM channel WHERE active=1")
    n = cur.fetchone()["n"]
    if n>0:
        return n
    lanes = make_default_lanes(nlanes)
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO channel(id,chno,name,group_name,active) VALUES(?,?,?,?,1)",
            lanes
        )
    jlog(event="seed_channels", count=len(lanes))
    return len(lanes)

def parse_args():
    ap = argparse.ArgumentParser(description="ESPN Clean v2.1 Plan Builder (Patched)")
    ap.add_argument("--db", required=True)
    ap.add_argument("--valid-hours", type=int, default=CFG_VALID_HOURS)
    ap.add_argument("--tz", default=CFG_TZ)
    ap.add_argument("--note", default="")
    ap.add_argument("--min-gap-mins", type=int, default=CFG_MIN_GAP_MINS, help="min placeholder gap granularity")
    ap.add_argument("--align", type=int, default=30, help="grid alignment in minutes (e.g., 30 for :00/:30)")
    ap.add_argument("--lanes", type=int, default=CFG_LANES, help="seed this many lanes if channel table empty")
    return ap.parse_args()

def load_channels(conn):
    rows = conn.execute(
        "SELECT id, chno, name, group_name FROM channel WHERE active=1 ORDER BY chno"
    ).fetchall()
    return [dict(r) for r in rows]

def load_events(conn, start_utc:str, end_utc:str):
    q = """
    SELECT e.*
    FROM events e
    WHERE e.start_utc < ? AND e.stop_utc > ?
    ORDER BY e.start_utc ASC
    """
    try:
        rows = conn.execute(q, (end_utc, start_utc)).fetchall()
    except Exception:
        return []
    return [dict(r) for r in rows]

def iso(dt:datetime)->str:
    return dt.replace(microsecond=0, tzinfo=timezone.utc).isoformat()

def checksum_rows(rows):
    m = hashlib.sha256()
    for r in rows:
        m.update(json.dumps(r, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        m.update(b"\n")
    return m.hexdigest()

def _now_iso_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def _ensure_event_lane_table(conn: sqlite3.Connection):
    with conn:
        conn.execute("""
          CREATE TABLE IF NOT EXISTS event_lane(
            event_id TEXT PRIMARY KEY,
            channel_id TEXT NOT NULL,
            pinned_at_utc TEXT NOT NULL,
            last_seen_utc TEXT NOT NULL
          )
        """)

def _load_event_lane_map(conn):
    _ensure_event_lane_table(conn)
    rows = conn.execute("SELECT event_id, channel_id FROM event_lane").fetchall()
    return {r["event_id"]: r["channel_id"] for r in rows}

def _upsert_event_lane(conn, event_id:str, channel_id:str):
    _ensure_event_lane_table(conn)
    now = _now_iso_utc()
    conn.execute("""
        INSERT INTO event_lane(event_id, channel_id, pinned_at_utc, last_seen_utc)
        VALUES(?,?,?,?)
        ON CONFLICT(event_id) DO UPDATE SET
          channel_id=excluded.channel_id,
          last_seen_utc=excluded.last_seen_utc
    """, (event_id, channel_id, now, now))

def _seed_event_lane_from_latest_plan(conn):
    """
    If event_lane is empty, seed it from the latest plan's event slots.
    """
    _ensure_event_lane_table(conn)
    have = conn.execute("SELECT COUNT(*) AS n FROM event_lane").fetchone()["n"]
    if have > 0:
        return 0
    row = conn.execute("SELECT MAX(plan_id) AS pid FROM plan_slot").fetchone()
    if not row or row["pid"] is None:
        return 0
    pid = int(row["pid"])
    events = conn.execute("""
      SELECT DISTINCT event_id, channel_id FROM plan_slot
       WHERE plan_id=? AND kind='event' AND event_id IS NOT NULL
    """,(pid,)).fetchall()
    with conn:
        for r in events:
            _upsert_event_lane(conn, r["event_id"], r["channel_id"])
    return len(events)

def _floor_to_step(dt_obj, minutes: int):
    """Floor datetime to the nearest step boundary."""
    m = (dt_obj.minute // minutes) * minutes
    return dt_obj.replace(minute=m, second=0, microsecond=0)

def _ceil_to_step(dt_obj, minutes: int):
    """Ceil datetime to the nearest step boundary."""
    base = _floor_to_step(dt_obj, minutes)
    if base < dt_obj:
        base = base + timedelta(minutes=minutes)
    return base

def _segmentize(start_dt, end_dt, step_mins: int):
    """Yield (seg_start, seg_end) covering [start_dt, end_dt) on a fixed grid."""
    if start_dt >= end_dt:
        return
    s = _floor_to_step(start_dt, step_mins)
    if s < start_dt:
        s = _ceil_to_step(start_dt, step_mins)
    t = s
    while t < end_dt:
        nxt = t + timedelta(minutes=step_mins)
        yield (t, min(nxt, end_dt))
        t = nxt

def build_plan(conn, channels, events, start_dt_utc:datetime, end_dt_utc:datetime,
               min_gap:timedelta, align_minutes:int, _sticky_map=None):
    # normalize events
    norm_events = []
    for e in events:
        try:
            s = datetime.fromisoformat(e["start_utc"]).astimezone(timezone.utc)
            t = datetime.fromisoformat(e["stop_utc"]).astimezone(timezone.utc)
        except Exception:
            continue
        if t <= start_dt_utc or s >= end_dt_utc:
            continue
        s = max(s, start_dt_utc)
        t = min(t, end_dt_utc)
        if t <= s:
            continue
        e2 = dict(e); e2["_s"]=s; e2["_t"]=t
        norm_events.append(e2)

    # timelines[channel_id] -> list of (start,end,event_id,kind)
    channels_sorted = [c["id"] for c in sorted(channels, key=lambda x: x["chno"])]
    timelines = {cid: [] for cid in channels_sorted}
    sticky_map = dict(_sticky_map or {})
    new_sticky = []  # (event_id, channel_id)

    # greedy in start order; prefer sticky lane if free
    norm_events.sort(key=lambda e: e["_s"])
    for e in norm_events:
        preferred = sticky_map.get(e["id"])
        chosen = None

        # 1) Sticky lane if free
        if preferred in timelines:
            tl = timelines[preferred]
            free_at = tl[-1][1] if tl else start_dt_utc
            if free_at <= e["_s"]:
                chosen = preferred

        # 2) Earliest-free lane (deterministic by chno)
        if chosen is None:
            best_free = None
            best_cid = None
            for cid in channels_sorted:
                tl = timelines[cid]
                free_at = tl[-1][1] if tl else start_dt_utc
                if free_at <= e["_s"] and (best_free is None or free_at < best_free):
                    best_free = free_at; best_cid = cid
            if best_cid is None:
                # no lane free yet: take the one that frees earliest, start when free
                cid = min(channels_sorted, key=lambda k: timelines[k][-1][1] if timelines[k] else start_dt_utc)
                free_t = timelines[cid][-1][1] if timelines[cid] else start_dt_utc
                if free_t < e["_t"]:
                    e_s = max(e["_s"], free_t)
                    timelines[cid].append((e_s, e["_t"], e["id"], "event"))
                    if preferred is None and sticky_map.get(e["id"]) != cid:
                        sticky_map[e["id"]] = cid
                        new_sticky.append((e["id"], cid))
                continue
            chosen = best_cid

        # 3) Place on chosen lane
        timelines[chosen].append((e["_s"], e["_t"], e["id"], "event"))
        if preferred is None and sticky_map.get(e["id"]) != chosen:
            sticky_map[e["id"]] = chosen
            new_sticky.append((e["id"], chosen))

    # fill gaps (raw, unsnapped)
    plan_slots = []
    for c in channels:
        cid = c["id"]
        cursor = start_dt_utc
        for (s, t, eid, kind) in timelines[cid]:
            if s - cursor >= min_gap:
                plan_slots.append({"channel_id": cid, "event_id": None, "start": cursor, "end": s,
                                   "kind": "placeholder", "placeholder_reason": "no_event"})
            plan_slots.append({"channel_id": cid, "event_id": eid, "start": s, "end": t,
                               "kind": "event", "placeholder_reason": None})
            cursor = t
        if end_dt_utc - cursor >= min_gap:
            plan_slots.append({"channel_id": cid, "event_id": None, "start": cursor, "end": end_dt_utc,
                               "kind": "placeholder", "placeholder_reason": "tail_gap"})
    plan_slots.sort(key=lambda r:(r["channel_id"], r["start"]))

    # PATCHED: Snap and segment differently for events vs placeholders
    snapped = []
    for s in plan_slots:
        if s["kind"] == "event":
            # Events: keep whole, just align start/end to grid boundaries
            aligned_start = _floor_to_step(s["start"], align_minutes)
            aligned_end = _ceil_to_step(s["end"], align_minutes)
            snapped.append({
                "channel_id": s["channel_id"],
                "event_id": s["event_id"],
                "start": aligned_start.replace(second=0, microsecond=0),
                "end": aligned_end.replace(second=0, microsecond=0),
                "kind": "event",
                "placeholder_reason": None,
            })
        else:
            # Placeholders: split across grid boundaries for better visual alignment
            for seg_s, seg_e in _segmentize(s["start"], s["end"], align_minutes):
                snapped.append({
                    "channel_id": s["channel_id"],
                    "event_id": None,
                    "start": seg_s.replace(second=0, microsecond=0),
                    "end": seg_e.replace(second=0, microsecond=0),
                    "kind": "placeholder",
                    "placeholder_reason": s["placeholder_reason"],
                })
    
    snapped.sort(key=lambda r:(r["channel_id"], r["start"]))
    
    # PATCHED: Remove overlapping placeholders that conflict with events
    # When events get floor-aligned, they can overlap with placeholder segments
    # that were created before alignment. Remove any placeholder that overlaps with an event.
    cleaned = []
    snapped_by_channel = {}
    for slot in snapped:
        cid = slot["channel_id"]
        if cid not in snapped_by_channel:
            snapped_by_channel[cid] = []
        snapped_by_channel[cid].append(slot)
    
    for cid in sorted(snapped_by_channel.keys()):
        slots = snapped_by_channel[cid]
        i = 0
        while i < len(slots):
            current = slots[i]
            
            # If this is a placeholder, check if it overlaps with next event
            if current["kind"] == "placeholder" and i + 1 < len(slots):
                next_slot = slots[i + 1]
                if next_slot["kind"] == "event" and current["end"] > next_slot["start"]:
                    # Overlap detected: truncate or skip placeholder
                    if current["start"] < next_slot["start"]:
                        # Truncate placeholder to end where event starts
                        current["end"] = next_slot["start"]
                        cleaned.append(current)
                    # else: placeholder completely overlapped, skip it
                    i += 1
                    continue
            
            cleaned.append(current)
            i += 1
    
    snapped = cleaned
    snapped.sort(key=lambda r:(r["channel_id"], r["start"]))

    # Persist new sticky choices
    if new_sticky:
        with conn:
            for eid, cid in new_sticky:
                _upsert_event_lane(conn, eid, cid)
        jlog(event="sticky_upserts", count=len(new_sticky))

    return snapped

def write_plan(conn, plan_slots, start_dt_utc, end_dt_utc, note:str):
    rows_for_ck = [{
        "channel_id": ps["channel_id"],
        "event_id": ps["event_id"],
        "start": iso(ps["start"]),
        "end":   iso(ps["end"]),
        "kind":  ps["kind"],
        "placeholder_reason": ps["placeholder_reason"],
    } for ps in plan_slots]
    ck = checksum_rows(rows_for_ck)
    with conn:
        cur = conn.execute(
            "INSERT INTO plan_run(generated_at_utc,valid_from_utc,valid_to_utc,source_version,note,checksum) VALUES(?,?,?,?,?,?)",
            (iso(datetime.now(timezone.utc)), iso(start_dt_utc), iso(end_dt_utc), f"builder:{VERSION}", note, ck)
        )
        plan_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO plan_slot(plan_id,channel_id,event_id,start_utc,end_utc,kind,placeholder_reason,preferred_feed_id) VALUES(?,?,?,?,?,?,?,NULL)",
            [(plan_id, s["channel_id"], s["event_id"], iso(s["start"]), iso(s["end"]), s["kind"], s["placeholder_reason"]) for s in plan_slots]
        )
        conn.execute("INSERT INTO plan_meta(key,value) VALUES('active_plan_id',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(plan_id),))
    return plan_id, ck

def main():
    args = parse_args()
    tz = ZoneInfo(args.tz)
    start_local = datetime.now(tz).replace(second=0, microsecond=0)
    start_utc = start_local.astimezone(timezone.utc)
    # Align the window start to the requested grid
    start_utc = _floor_to_step(start_utc, args.align)
    end_utc = start_utc + timedelta(hours=args.valid_hours)
    min_gap = timedelta(minutes=args.min_gap_mins)

    conn = connect_db(args.db)
    seeded = seed_channels_if_empty(conn, args.lanes)
    channels = load_channels(conn)
    events = load_events(conn, start_utc.replace(tzinfo=timezone.utc).isoformat(), end_utc.replace(tzinfo=timezone.utc).isoformat())

    # Sticky: seed from latest plan once, then load map
    seeded_sticky = _seed_event_lane_from_latest_plan(conn)
    sticky_map = _load_event_lane_map(conn)

    jlog(event="plan_build_start", version=VERSION, db=args.db, valid_hours=args.valid_hours,
         tz=args.tz, start_utc=start_utc.replace(tzinfo=timezone.utc).isoformat(),
         end_utc=end_utc.replace(tzinfo=timezone.utc).isoformat(),
         channels=len(channels), events=len(events),
         seeded_channels=seeded, seeded_sticky=seeded_sticky, sticky_entries=len(sticky_map))

    plan_slots = build_plan(conn, channels, events, start_utc, end_utc, min_gap, args.align, _sticky_map=sticky_map)
    by_ch = {}
    ev_count = ph_count = 0
    for s in plan_slots:
        d = by_ch.setdefault(s["channel_id"], {"events":0,"placeholders":0})
        if s["kind"]=="event":
            d["events"]+=1; ev_count+=1
        else:
            d["placeholders"]+=1; ph_count+=1

    plan_id, ck = write_plan(conn, plan_slots, start_utc, end_utc, args.note)
    jlog(event="plan_build_done", plan_id=plan_id, checksum=ck,
         total_slots=len(plan_slots), event_slots=ev_count, placeholder_slots=ph_count,
         by_channel=by_ch)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        jlog(level="error", event="plan_build_failed", error=str(e))
        raise
