#!/usr/bin/env python3
# file: bin/build_plan_sticky.py
# ESPN Clean v2.0 — plan builder with lane stickiness

import argparse
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

VERSION = "2.1.0-sticky"
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "plan_builder.jsonl")


def jlog(**kv):
    kv = {"ts": datetime.now(timezone.utc).isoformat(), "mod": "build_plan", **kv}
    line = json.dumps(kv, ensure_ascii=False)
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def parse_args():
    ap = argparse.ArgumentParser(
        description="ESPN Clean v2.0 Plan Builder (sticky lanes)"
    )
    ap.add_argument("--db", required=True)
    ap.add_argument("--valid-hours", type=int, default=72)
    ap.add_argument("--tz", default="America/New_York")
    ap.add_argument("--note", default="")
    ap.add_argument("--min-gap-mins", type=int, default=5)
    ap.add_argument("--lanes", type=int, default=40)
    ap.add_argument(
        "--stick-window-hours",
        type=int,
        default=12,
        help="Prefer prior lanes for events starting within this many hours from start (default 12)",
    )
    return ap.parse_args()


def connect_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def make_default_lanes(n: int = 40, start_chno: int = 20010):
    return [
        (f"eplus{i}", start_chno + (i - 1), f"ESPN+ EPlus {i}", "ESPN+ VC")
        for i in range(1, n + 1)
    ]


def seed_channels_if_empty(conn: sqlite3.Connection, nlanes: int = 40):
    n = conn.execute("SELECT COUNT(*) FROM channel WHERE active=1").fetchone()[0]
    if n > 0:
        return n
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO channel(id,chno,name,group_name,active) VALUES(?,?,?,?,1)",
            make_default_lanes(nlanes),
        )
    jlog(event="seed_channels", count=nlanes)
    return nlanes


def load_channels(conn):
    rows = conn.execute(
        "SELECT id, chno, name, group_name FROM channel WHERE active=1 ORDER BY chno"
    ).fetchall()
    return [dict(r) for r in rows]


def load_events(conn, start_utc: str, end_utc: str):
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


def latest_two_plan_ids(conn):
    rows = conn.execute(
        "SELECT DISTINCT plan_id FROM plan_slot ORDER BY plan_id DESC LIMIT 2"
    ).fetchall()
    return [r[0] for r in rows]


def prior_lane_map(conn, prior_plan_id: int):
    """event_id -> channel_id for prior plan (only real events)"""
    rows = conn.execute(
        """
        SELECT DISTINCT event_id, channel_id
        FROM plan_slot
        WHERE plan_id=? AND kind='event' AND event_id IS NOT NULL
    """,
        (prior_plan_id,),
    ).fetchall()
    return {r["event_id"]: r["channel_id"] for r in rows}


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0, tzinfo=timezone.utc).isoformat()


def checksum_rows(rows):
    m = hashlib.sha256()
    for r in rows:
        m.update(json.dumps(r, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        m.update(b"\n")
    return m.hexdigest()


def _floor_to_half_hour(dt_obj):
    minute = dt_obj.minute
    floormin = 0 if minute < 30 else 30
    return dt_obj.replace(minute=floormin, second=0, microsecond=0)


def build_plan_with_stickiness(
    conn,
    channels,
    events,
    start_dt_utc,
    end_dt_utc,
    min_gap,
    priormap: dict,
    stick_window: timedelta,
):
    # normalize events into window
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
        e2 = dict(e)
        e2["_s"] = s
        e2["_t"] = t
        norm_events.append(e2)

    # timelines per lane
    timelines = {c["id"]: [] for c in channels}
    # sort by start time
    norm_events.sort(key=lambda e: e["_s"])

    def lane_free_at(lane_id):
        tl = timelines[lane_id]
        return tl[-1][1] if tl else start_dt_utc

    # place with stickiness
    for e in norm_events:
        eid = e.get("id")
        s = e["_s"]
        t = e["_t"]
        chosen = None

        # inside stick window?
        if s <= start_dt_utc + stick_window and eid in priormap:
            preferred = priormap[eid]
            free_at = lane_free_at(preferred)
            if free_at <= s:  # preferred lane free at event start
                chosen = preferred

        if chosen is None:
            # fallback to earliest free lane
            chosen = min(timelines.keys(), key=lambda k: lane_free_at(k))

        # append if it actually adds play time
        free_t = lane_free_at(chosen)
        if free_t < t:
            e_s = max(s, free_t)
            timelines[chosen].append((e_s, t, eid, "event"))

    # fill gaps into plan_slots
    plan_slots = []
    for c in channels:
        cid = c["id"]
        cursor = start_dt_utc
        for s, t, eid, kind in timelines[cid]:
            if s - cursor >= min_gap:
                plan_slots.append(
                    {
                        "channel_id": cid,
                        "event_id": None,
                        "start": cursor,
                        "end": s,
                        "kind": "placeholder",
                        "placeholder_reason": "no_event",
                    }
                )
            plan_slots.append(
                {
                    "channel_id": cid,
                    "event_id": eid,
                    "start": s,
                    "end": t,
                    "kind": "event",
                    "placeholder_reason": None,
                }
            )
            cursor = t
        if end_dt_utc - cursor >= min_gap:
            plan_slots.append(
                {
                    "channel_id": cid,
                    "event_id": None,
                    "start": cursor,
                    "end": end_dt_utc,
                    "kind": "placeholder",
                    "placeholder_reason": "tail_gap",
                }
            )
    plan_slots.sort(key=lambda r: (r["channel_id"], r["start"]))
    return plan_slots


def write_plan(conn, plan_slots, start_dt_utc, end_dt_utc, note: str):
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
    return plan_id, ck


def main():
    args = parse_args()
    tz = ZoneInfo(args.tz)
    start_local = datetime.now(tz).replace(second=0, microsecond=0)
    start_utc = start_local.astimezone(timezone.utc)
    start_utc = _floor_to_half_hour(start_utc)
    end_utc = start_utc + timedelta(hours=args.valid_hours)
    min_gap = timedelta(minutes=args.min_gap_mins)
    stick_window = timedelta(hours=args.stick_window_hours)

    conn = connect_db(args.db)
    seeded = seed_channels_if_empty(conn, args.lanes)
    channels = load_channels(conn)
    events = load_events(
        conn,
        start_utc.replace(tzinfo=timezone.utc).isoformat(),
        end_utc.replace(tzinfo=timezone.utc).isoformat(),
    )

    # prior lane map (if any)
    pids = latest_two_plan_ids(conn)
    pmap = prior_lane_map(conn, pids[1]) if len(pids) >= 2 else {}

    jlog(
        event="plan_build_start",
        version=VERSION,
        db=args.db,
        valid_hours=args.valid_hours,
        tz=args.tz,
        start_utc=start_utc.replace(tzinfo=timezone.utc).isoformat(),
        end_utc=end_utc.replace(tzinfo=timezone.utc).isoformat(),
        channels=len(channels),
        events=len(events),
        seeded_channels=seeded,
        sticky_events=len(pmap),
        stick_window_hours=args.stick_window_hours,
    )

    plan_slots = build_plan_with_stickiness(
        conn, channels, events, start_utc, end_utc, min_gap, pmap, stick_window
    )

    by_ch = {}
    ev_count = ph_count = 0
    for s in plan_slots:
        d = by_ch.setdefault(s["channel_id"], {"events": 0, "placeholders": 0})
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
