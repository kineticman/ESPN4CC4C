#!/usr/bin/env python3
# file: bin/build_plan.py
# ESPN4CC4C — canonical plan builder (events -> plan_run/plan_slot)
# Version with "sticky lanes", grid alignment, overlap guards, and
# NEW: default --start behavior = previous plan's valid_from_utc (fallback to now)

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from typing import Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

# ---------- Config fallbacks ----------
try:
    from version import VERSION as BUILD_VERSION  # type: ignore
    from version import get_version

    RUNTIME_VERSION = get_version()
except Exception:
    BUILD_VERSION = "unknown"
    RUNTIME_VERSION = "unknown"

try:
    from config import BUILDER_DEFAULT_LANES as CFG_LANES
    from config import BUILDER_DEFAULT_MIN_GAP_MINS as CFG_MIN_GAP_MINS
    from config import BUILDER_DEFAULT_TZ as CFG_TZ  # type: ignore
    from config import BUILDER_DEFAULT_VALID_HOURS as CFG_VALID_HOURS
    from config import CHANNEL_START_CHNO as CFG_CHANNEL_START_CHNO
except Exception:
    CFG_TZ = "America/New_York"
    CFG_VALID_HOURS = 72
    CFG_MIN_GAP_MINS = 5
    CFG_LANES = 40
    CFG_CHANNEL_START_CHNO = 20010

VERSION = "2.1.7-padding-logrotate"
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "plan_builder.jsonl")

STICKY_GRACE = timedelta(seconds=0)  # lane must be free at event start


# ---------- Logging with rotation ----------
_log_handler = RotatingFileHandler(
    LOG_PATH,
    maxBytes=10 * 1024 * 1024,  # 10 MB per file
    backupCount=3,  # Keep 3 old files (30MB max total)
    encoding="utf-8",
)
_log_handler.setFormatter(logging.Formatter('%(message)s'))  # Raw JSONL format

_logger = logging.getLogger("plan_builder")
_logger.setLevel(logging.INFO)
_logger.addHandler(_log_handler)


def jlog(**kv):
    kv = {"ts": datetime.now(timezone.utc).isoformat(), "mod": "build_plan", **kv}
    line = json.dumps(kv, ensure_ascii=False)
    print(line, flush=True)
    try:
        _logger.info(line)
    except Exception:
        pass


# ---------- DB helpers ----------
def connect_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


# ---------- CLI ----------
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="ESPN4CC4C Plan Builder")
    ap.add_argument("--db", required=True)
    ap.add_argument("--valid-hours", type=int, default=CFG_VALID_HOURS)
    ap.add_argument(
        "--start",
        default=None,
        help="ISO (2025-11-09T18:00:00), local 'YYYY-MM-DD HH:MM:SS', or offset like -6h / -30m",
    )
    ap.add_argument("--tz", default=CFG_TZ)
    ap.add_argument("--note", default="")
    ap.add_argument(
        "--min-gap-mins",
        type=int,
        default=CFG_MIN_GAP_MINS,
        help="min placeholder gap granularity",
    )
    ap.add_argument(
        "--align", type=int, default=30, help=":00/:30 grid in minutes (e.g., 30)"
    )
    ap.add_argument(
        "--lanes",
        type=int,
        default=CFG_LANES,
        help="seed this many lanes if channel table empty",
    )
    ap.add_argument(
        "--force-replan",
        action="store_true",
        help="ignore sticky lanes and force fresh planning (use after filter changes)",
    )
    ap.add_argument(
        "--padding-start-mins",
        type=int,
        default=0,
        help="minutes of padding before event start (default: 0)",
    )
    ap.add_argument(
        "--padding-end-mins",
        type=int,
        default=0,
        help="minutes of padding after event end (default: 0)",
    )
    ap.add_argument(
        "--padding-all",
        action="store_true",
        help="apply padding to all events (default: live events only)",
    )
    return ap.parse_args()


# ---------- Channel seeding ----------
def make_default_lanes(
    n: int = 40, start_chno: Optional[int] = None
) -> List[Tuple[str, int, str, str]]:
    if start_chno is None:
        start_chno = CFG_CHANNEL_START_CHNO
    lanes: List[Tuple[str, int, str, str]] = []
    for i in range(1, n + 1):
        lanes.append(
            (f"eplus{i:02d}", start_chno + (i - 1), f"ESPN+ EPlus {i}", "ESPN+ VC")
        )
    return lanes


def seed_channels_if_empty(conn: sqlite3.Connection, nlanes: int = 40) -> int:
    cur = conn.execute("SELECT COUNT(*) AS n FROM channel WHERE COALESCE(active,1)=1")
    n = int(cur.fetchone()[0])
    if n > 0:
        return n
    lanes = make_default_lanes(nlanes)
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO channel(id,chno,name,group_name,active) VALUES(?,?,?,?,1)",
            lanes,
        )
    jlog(event="seed_channels", count=len(lanes))
    return len(lanes)


# ---------- Query helpers ----------
def load_channels(conn: sqlite3.Connection) -> List[dict]:
    rows = conn.execute(
        "SELECT id, chno, name, group_name FROM channel WHERE COALESCE(active,1)=1 ORDER BY COALESCE(chno,id)"
    ).fetchall()
    return [dict(r) for r in rows]


def load_events(
    conn: sqlite3.Connection,
    start_utc: str,
    end_utc: str,
    event_ids: Optional[List[str]] = None,
) -> List[dict]:
    """Load events within time window, optionally filtered by event IDs"""
    if event_ids is not None:
        # Filter by specific event IDs
        if not event_ids:
            return []  # No events passed filter
        placeholders = ",".join("?" * len(event_ids))
        q = (
            f"SELECT e.* FROM events e "
            f"WHERE e.id IN ({placeholders}) AND e.start_utc < ? AND e.stop_utc > ? "
            f"ORDER BY e.start_utc ASC"
        )
        try:
            rows = conn.execute(q, tuple(event_ids) + (end_utc, start_utc)).fetchall()
        except Exception:
            return []
    else:
        # No filtering - load all events in window
        q = (
            "SELECT e.* FROM events e "
            "WHERE e.start_utc < ? AND e.stop_utc > ? "
            "ORDER BY e.start_utc ASC"
        )
        try:
            rows = conn.execute(q, (end_utc, start_utc)).fetchall()
        except Exception:
            return []
    return [dict(r) for r in rows]


# ---------- Sticky lanes ----------
def _load_event_lane_map(conn: sqlite3.Connection) -> Dict[str, str]:
    try:
        rows = conn.execute("SELECT event_id, channel_id FROM event_lane").fetchall()
        return {str(r[0]): str(r[1]) for r in rows}
    except Exception:
        return {}


def _seed_event_lane_from_latest_plan(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT MAX(plan_id) AS pid FROM plan_slot").fetchone()
        if not row or row[0] is None:
            return 0
        pid = int(row[0])
        rows = conn.execute(
            "SELECT DISTINCT event_id, channel_id FROM plan_slot WHERE plan_id=? AND kind='event' AND event_id IS NOT NULL",
            (pid,),
        ).fetchall()
        count = 0
        with conn:
            for r in rows:
                eid, cid = r[0], r[1]
                if eid is None:
                    continue
                conn.execute(
                    "INSERT INTO event_lane(event_id,channel_id) VALUES(?,?) ON CONFLICT(event_id) DO UPDATE SET channel_id=excluded.channel_id",  # noqa: E501
                    (eid, cid),
                )
                count += 1
        return count
    except Exception:
        return 0


def _upsert_event_lane(
    conn: sqlite3.Connection, event_id: str, channel_id: str
) -> None:
    with conn:
        conn.execute(
            "INSERT INTO event_lane(event_id,channel_id) VALUES(?,?) ON CONFLICT(event_id) DO UPDATE SET channel_id=excluded.channel_id",  # noqa: E501
            (event_id, channel_id),
        )


# ---------- Time/grid helpers ----------
def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0, tzinfo=timezone.utc).isoformat()


def _floor_to_step(dt: datetime, step_mins: int) -> datetime:
    step = step_mins * 60
    s = int(dt.timestamp())
    return datetime.fromtimestamp((s // step) * step, tz=timezone.utc)


def _ceil_to_step(dt: datetime, step_mins: int) -> datetime:
    step = step_mins * 60
    s = int(dt.timestamp())
    if s % step == 0:
        return datetime.fromtimestamp(s, tz=timezone.utc)
    return datetime.fromtimestamp(((s // step) + 1) * step, tz=timezone.utc)


def _segmentize(
    start_dt: datetime, end_dt: datetime, step_mins: int
) -> Iterable[Tuple[datetime, datetime]]:
    if start_dt >= end_dt:
        return []
    s = _floor_to_step(start_dt, step_mins)
    if s < start_dt:
        s = _ceil_to_step(start_dt, step_mins)
    t = s
    while t < end_dt:
        nxt = t + timedelta(minutes=step_mins)
        yield (t, min(nxt, end_dt))
        t = nxt


# ---------- Core planning ----------
def build_plan(
    conn: sqlite3.Connection,
    channels: List[dict],
    events: List[dict],
    start_dt_utc: datetime,
    end_dt_utc: datetime,
    min_gap: timedelta,
    align_minutes: int,
    _sticky_map: Optional[Dict[str, str]] = None,
    padding_start_mins: int = 0,
    padding_end_mins: int = 0,
    padding_live_only: bool = True,
) -> List[dict]:
    # Normalize events into window and to UTC datetimes
    norm_events: List[dict] = []
    padding_applied_count = 0
    padding_skipped_reair_count = 0
    
    for e in events:
        try:
            s = datetime.fromisoformat(e["start_utc"]).astimezone(timezone.utc)
            t = datetime.fromisoformat(e["stop_utc"]).astimezone(timezone.utc)
        except Exception:
            continue
        
        # Store original times for logging
        original_start = s
        original_end = t
        
        # Apply padding if enabled
        padding_applied = False
        if padding_start_mins > 0 or padding_end_mins > 0:
            # Check both content flags to determine if this needs padding:
            # is_reair = 0 means original live broadcast (not a replay)
            # is_studio = 0 means actual game/competition (not a talk show)
            # Only truly live sports events (both = 0) should be padded
            is_reair = e.get("is_reair", 0)
            is_studio = e.get("is_studio", 0)
            
            # Apply padding to live sports content, or all content if padding_live_only=False
            if not padding_live_only or (is_reair == 0 and is_studio == 0):
                s = s - timedelta(minutes=padding_start_mins)
                t = t + timedelta(minutes=padding_end_mins)
                padding_applied = True
                padding_applied_count += 1
            else:
                padding_skipped_reair_count += 1
        
        # Clamp to window boundaries
        if t <= start_dt_utc or s >= end_dt_utc:
            continue
        s = max(s, start_dt_utc)
        t = min(t, end_dt_utc)
        if t <= s:
            continue
        
        e2 = dict(e)
        e2["_s"] = s
        e2["_t"] = t
        e2["_padding_applied"] = padding_applied
        e2["_original_start"] = original_start
        e2["_original_end"] = original_end
        norm_events.append(e2)
    
    # Log padding summary
    if padding_start_mins > 0 or padding_end_mins > 0:
        jlog(
            event="padding_summary",
            padding_start_mins=padding_start_mins,
            padding_end_mins=padding_end_mins,
            padding_live_only=padding_live_only,
            events_padded=padding_applied_count,
            non_live_events_skipped=padding_skipped_reair_count,
            total_events=len(events),
        )

    # Channel timelines
    channels_sorted = [
        str(c["id"]) if isinstance(c["id"], (int,)) else str(c["id"]) for c in channels
    ]
    timelines: Dict[str, List[dict]] = {cid: [] for cid in channels_sorted}

    sticky = _sticky_map or {}

    # Assign events to lanes
    for ev in norm_events:
        eid = str(ev.get("id") or ev.get("event_id") or "")
        preferred = sticky.get(eid)

        def lane_free(cid: str, s: datetime, t: datetime) -> bool:
            for slot in timelines[cid]:
                if not (t <= slot["start"] or s >= slot["end"]):
                    return False
            return True

        target_cid: Optional[str] = None
        if (
            preferred
            and preferred in timelines
            and lane_free(preferred, ev["_s"], ev["_t"])
        ):
            target_cid = preferred
        else:
            for cid in channels_sorted:
                if lane_free(cid, ev["_s"], ev["_t"]):
                    target_cid = cid
                    break

        if not target_cid:
            # No free lane; drop this event (logged)
            jlog(
                level="warning",
                event="no_free_lane",
                event_id=eid,
                start=iso(ev["_s"]),
                end=iso(ev["_t"]),
            )
            continue

        if preferred and preferred != target_cid:
            jlog(
                event="sticky_miss_reassigned",
                event_id=eid,
                sticky=preferred,
                assigned=target_cid,
            )
        
        # Log individual padding application for audit
        if ev.get("_padding_applied"):
            jlog(
                event="event_padded",
                event_id=eid,
                is_reair=ev.get("is_reair", 0),
                is_studio=ev.get("is_studio", 0),
                original_start=iso(ev["_original_start"]),
                original_end=iso(ev["_original_end"]),
                padded_start=iso(ev["_s"]),
                padded_end=iso(ev["_t"]),
                channel_id=target_cid,
            )

        timelines[target_cid].append(
            {
                "channel_id": target_cid,
                "event_id": eid or None,
                "start": ev["_s"],
                "end": ev["_t"],
                "kind": "event",
                "placeholder_reason": None,
            }
        )

    # Add placeholders to fill gaps on grid
    for cid in channels_sorted:
        slots = timelines[cid]
        slots.sort(key=lambda r: r["start"])  # by time
        filled: List[dict] = []

        # Start of window
        cursor = start_dt_utc
        for s in slots:
            if s["start"] > cursor:
                gap = s["start"] - cursor
                if gap >= min_gap:
                    # segmentize gap on the grid
                    for a, b in _segmentize(cursor, s["start"], align_minutes):
                        filled.append(
                            {
                                "channel_id": cid,
                                "event_id": None,
                                "start": a,
                                "end": b,
                                "kind": "placeholder",
                                "placeholder_reason": "gap",
                            }
                        )
            filled.append(s)
            cursor = max(cursor, s["end"])  # advance

        if cursor < end_dt_utc:
            gap = end_dt_utc - cursor
            if gap >= min_gap:
                for a, b in _segmentize(cursor, end_dt_utc, align_minutes):
                    filled.append(
                        {
                            "channel_id": cid,
                            "event_id": None,
                            "start": a,
                            "end": b,
                            "kind": "placeholder",
                            "placeholder_reason": "tail",
                        }
                    )

        timelines[cid] = filled

    # Safety clean-up: remove overlaps and drop placeholders overlapped by events
    # Padded events should "win" over placeholders
    cleaned: List[dict] = []
    new_sticky: List[Tuple[str, str]] = []
    for cid in channels_sorted:
        slots = sorted(
            timelines[cid], key=lambda r: (r["start"], 0 if r["kind"] == "event" else 1)
        )
        i = 0
        while i < len(slots):
            current = slots[i]
            # If event overlaps following placeholder, drop/truncate placeholder
            if current["kind"] == "event" and current.get("event_id"):
                new_sticky.append((current["event_id"], cid))
            if i + 1 < len(slots):
                nxt = slots[i + 1]
                if current["end"] > nxt["start"]:
                    # Overlap
                    if current["kind"] == "event" and nxt["kind"] == "placeholder":
                        # truncate/skip placeholder (padding wins)
                        if nxt["end"] <= current["end"]:
                            # placeholder fully covered — drop it
                            i += 1
                            continue
                        else:
                            # move its start forward
                            nxt["start"] = current["end"]
                    elif current["kind"] == "event" and nxt["kind"] == "event":
                        # event-to-event overlap -> keep earlier, drop later
                        jlog(
                            level="warning",
                            event="event_overlap_detected",
                            channel_id=cid,
                            event1_start=iso(current["start"]),
                            event1_end=iso(current["end"]),
                            event2_start=iso(nxt["start"]),
                            event2_end=iso(nxt["end"]),
                            action="drop_later",
                        )
                        cleaned.append(current)
                        i += 2
                        continue
            cleaned.append(current)
            i += 1

    snapped = sorted(cleaned, key=lambda r: (r["channel_id"], r["start"]))

    # Persist sticky hints from this build
    if new_sticky:
        with conn:
            for eid, cid in new_sticky:
                if eid:
                    _upsert_event_lane(conn, eid, cid)
        jlog(event="sticky_upserts", count=len(new_sticky))

    return snapped


# ---------- Persist plan ----------
def checksum_rows(rows: Iterable[dict]) -> str:
    m = hashlib.sha256()
    for r in rows:
        m.update(json.dumps(r, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        m.update(b"\n")
    return m.hexdigest()


def write_plan(
    conn: sqlite3.Connection,
    plan_slots: List[dict],
    start_dt_utc: datetime,
    end_dt_utc: datetime,
    note: str,
) -> Tuple[int, str]:
    rows_for_ck = [
        {
            "channel_id": ps["channel_id"],
            "event_id": ps["event_id"],
            "start": iso(ps["start"]),
            "end": iso(ps["end"]),
            "kind": ps["kind"],
            "placeholder_reason": ps["placeholder_reason"],
        }
        for ps in plan_slots
    ]
    ck = checksum_rows(rows_for_ck)
    with conn:
        cur = conn.execute(
            "INSERT INTO plan_run(generated_at_utc,valid_from_utc,valid_to_utc,source_version,note,checksum) VALUES(?,?,?,?,?,?)",
            (
                iso(datetime.now(timezone.utc)),
                iso(start_dt_utc),
                iso(end_dt_utc),
                f"builder:{VERSION}",
                note,
                ck,
            ),
        )
        plan_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO plan_slot(plan_id,channel_id,event_id,start_utc,end_utc,kind,placeholder_reason,preferred_feed_id) VALUES(?,?,?,?,?,?,?,NULL)",  # noqa: E501
            [
                (
                    plan_id,
                    s["channel_id"],
                    s["event_id"],
                    iso(s["start"]),
                    iso(s["end"]),
                    s["kind"],
                    s["placeholder_reason"],
                )
                for s in plan_slots
            ],
        )
        conn.execute(
            "INSERT INTO plan_meta(key,value) VALUES('active_plan_id',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(plan_id),),
        )
    return int(plan_id), ck


# ---------- Main ----------
def main() -> None:
    args = parse_args()
    tz = ZoneInfo(args.tz)

    conn = connect_db(args.db)  # we need this early to read plan_run

    # Resolve start_local according to precedence:
    # 1) --start provided -> parse (offset or ISO) and convert to local tz
    # 2) else last plan_run.valid_from_utc -> local tz
    # 3) else now (local tz)
    if args.start:
        start_str = str(args.start).strip()
        if start_str.startswith("-") or start_str.startswith("+"):
            # offset like -6h / +90m
            import re

            m = re.match(r"^([+-]?)(\d+)([hm])$", start_str)
            if m:
                sign, value, unit = m.groups()
                value_i = int(value)
                if sign == "-":
                    value_i = -value_i
                if unit == "h":
                    start_local = datetime.now(tz) + timedelta(hours=value_i)
                else:
                    start_local = datetime.now(tz) + timedelta(minutes=value_i)
                start_local = start_local.replace(second=0, microsecond=0)
            else:
                jlog(
                    event="plan_build_error",
                    error=f"Invalid offset format: {start_str}",
                )
                start_local = datetime.now(tz).replace(second=0, microsecond=0)
        else:
            # Absolute datetime
            try:
                dt = datetime.fromisoformat(start_str)
            except Exception:
                # allow space between date and time
                try:
                    parts = start_str.replace(" ", "T")
                    dt = datetime.fromisoformat(parts)
                except Exception:
                    jlog(
                        event="plan_build_error",
                        error=f"Invalid datetime format: {start_str}",
                    )
                    dt = datetime.now(tz)
            if dt.tzinfo is None:
                start_local = dt.replace(tzinfo=tz)
            else:
                start_local = dt.astimezone(tz)
            start_local = start_local.replace(second=0, microsecond=0)
    else:
        # NEW DEFAULT: use "now minus grace hours" to ensure in-progress events
        # keep their true start times instead of being clamped to the window edge.
        # Adjustable via env BUILDER_DEFAULT_START_GRACE_HOURS (default 2).
        try:
            grace_hours = int(os.environ.get("BUILDER_DEFAULT_START_GRACE_HOURS", "4"))
        except Exception:
            grace_hours = 2
        start_local = (datetime.now(tz) - timedelta(hours=grace_hours)).replace(
            second=0, microsecond=0
        )
        jlog(event="default_start_now_minus_grace", grace_hours=grace_hours)

    start_utc = start_local.astimezone(timezone.utc)
    start_utc = _floor_to_step(start_utc, args.align)
    end_utc = start_utc + timedelta(hours=args.valid_hours)
    min_gap = timedelta(minutes=args.min_gap_mins)

    # seed + load
    seeded = seed_channels_if_empty(conn, args.lanes)
    channels = load_channels(conn)

    # NOTE: Event filtering now happens in refresh_in_container.py (Step 2/5)
    # which physically deletes filtered-out events from the database.
    # build_plan.py simply loads whatever events remain in the DB.
    events = load_events(
        conn, start_utc.isoformat(), end_utc.isoformat(), event_ids=None
    )

    # Sticky lanes: seed from latest plan (one-time) and load map
    # UNLESS --force-replan is used (for filter changes)
    sticky_map: dict[str, str] = {}
    seeded_sticky = 0
    if args.force_replan:
        jlog(
            event="force_replan_enabled",
            message="Ignoring sticky lanes - forcing fresh plan",
        )
    else:
        seeded_sticky = _seed_event_lane_from_latest_plan(conn)
        sticky_map = _load_event_lane_map(conn)

    jlog(
        event="plan_build_start",
        version=VERSION,
        db=args.db,
        valid_hours=args.valid_hours,
        tz=args.tz,
        start_utc=start_utc.isoformat(),
        end_utc=end_utc.isoformat(),
        channels=len(channels),
        events=len(events),
        seeded_channels=seeded,
        seeded_sticky=seeded_sticky,
        sticky_entries=len(sticky_map),
        padding_start_mins=args.padding_start_mins,
        padding_end_mins=args.padding_end_mins,
        padding_live_only=not args.padding_all,
        runtime_version=RUNTIME_VERSION,
        build_version=BUILD_VERSION,
    )

    plan_slots = build_plan(
        conn,
        channels,
        events,
        start_utc,
        end_utc,
        min_gap,
        args.align,
        _sticky_map=sticky_map,
        padding_start_mins=args.padding_start_mins,
        padding_end_mins=args.padding_end_mins,
        padding_live_only=not args.padding_all,
    )

    by_ch: Dict[str, Dict[str, int]] = {}
    ev_count = ph_count = 0
    for s in plan_slots:
        d = by_ch.setdefault(str(s["channel_id"]), {"events": 0, "placeholders": 0})
        if s["kind"] == "event":
            d["events"] += 1
            ev_count += 1
        else:
            d["placeholders"] += 1
            ph_count += 1

    plan_id, ck = write_plan(conn, plan_slots, start_utc, end_utc, args.note)
    jlog(
        event="plan_build_done",
        plan_id=plan_id,
        checksum=ck,
        total_slots=len(plan_slots),
        event_slots=ev_count,
        placeholder_slots=ph_count,
        by_channel=by_ch,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        jlog(level="error", event="plan_build_failed", error=str(e))
        raise
