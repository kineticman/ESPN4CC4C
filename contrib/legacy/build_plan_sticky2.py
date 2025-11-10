#!/usr/bin/env python3
# file: bin/build_plan_sticky2.py
# Sticky plan builder: reuses lanes from the previous plan, with lane-affinity and freeze window.

import argparse
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

VERSION = "2.1.0-sticky2"
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "plan_builder.jsonl")


def jlog(**kv):
    kv = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mod": "build_plan_sticky2",
        **kv,
    }
    line = json.dumps(kv, ensure_ascii=False)
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def connect_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0, tzinfo=timezone.utc).isoformat()


def checksum_rows(rows):
    m = hashlib.sha256()
    for r in rows:
        m.update(json.dumps(r, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        m.update(b"\n")
    return m.hexdigest()


def _floor_to_half_hour(dt_obj: datetime) -> datetime:
    minute = dt_obj.minute
    floormin = 0 if minute < 30 else 30
    return dt_obj.replace(minute=floormin, second=0, microsecond=0)


def make_default_lanes(n: int = 40, start_chno: int = 20010):
    lanes = []
    for i in range(1, n + 1):
        lanes.append(
            (f"eplus{i}", start_chno + (i - 1), f"ESPN+ EPlus {i}", "ESPN+ VC")
        )
    return lanes


def seed_channels_if_empty(conn: sqlite3.Connection, nlanes: int = 40):
    cur = conn.execute("SELECT COUNT(*) AS n FROM channel WHERE active=1")
    n = cur.fetchone()["n"]
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


def read_prev_event_lanes(conn) -> Dict[str, str]:
    """
    Map event_id -> lane from the previous plan (MAX(plan_id)-1),
    considering only event slots.
    """
    pid_row = conn.execute("SELECT MAX(plan_id) AS pid FROM plan_slot").fetchone()
    if not pid_row or pid_row["pid"] is None:
        return {}
    prev_id = int(pid_row["pid"]) - 1
    if prev_id <= 0:
        return {}
    rows = conn.execute(
        """
      SELECT channel_id AS lane, event_id
      FROM plan_slot
      WHERE plan_id=? AND kind='event' AND event_id IS NOT NULL
    """,
        (prev_id,),
    ).fetchall()
    out = {}
    for r in rows:
        eid = r["event_id"]
        lane = r["lane"]
        if eid and lane:
            out[eid] = lane
    return out


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


# ----------------- Sticky packer -----------------


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def build_plan_sticky(
    channels: List[dict],
    events: List[dict],
    start_dt_utc: datetime,
    end_dt_utc: datetime,
    min_gap: timedelta,
    prev_event_lane: Dict[str, str],
    now_utc: datetime,
    stick_window: timedelta,
    freeze_window: timedelta,
    lane_affinity: int,
):
    """
    Strategy:
      1) Normalize / clip events to [start, end]
      2) For each event (sorted by start):
         - If within freeze_window of 'now', strongly prefer previous lane; if busy, try neighbor lanes within ±lane_affinity.
         - Else if within stick_window, prefer previous lane/affinity but can fall back freely.
         - Else place greedily (earliest free lane).
      3) Fill gaps with placeholders honoring min_gap.
    """
    # normalize
    norm: List[dict] = []
    for e in events:
        try:
            s = _parse_ts(e["start_utc"])
            t = _parse_ts(e["stop_utc"])
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
        norm.append(e2)

    # lanes state
    lane_ids = [c["id"] for c in channels]  # ordered by chno already
    lane_index = {lane_ids[i]: i for i in range(len(lane_ids))}
    free_at: Dict[str, datetime] = {lid: start_dt_utc for lid in lane_ids}
    timelines: Dict[str, List[Tuple[datetime, datetime, Optional[str], str]]] = {
        lid: [] for lid in lane_ids
    }

    # helpers
    def try_place_on(lid: str, ev: dict) -> bool:
        fa = free_at[lid]
        if fa <= ev["_s"]:
            timelines[lid].append((ev["_s"], ev["_t"], ev.get("id"), "event"))
            free_at[lid] = ev["_t"]
            return True
        return False

    def affinity_order(center: str) -> List[str]:
        if center not in lane_index:
            return []
        ci = lane_index[center]
        order = [center]
        for d in range(1, lane_affinity + 1):
            left = ci - d
            right = ci + d
            if left >= 0:
                order.append(lane_ids[left])
            if right < len(lane_ids):
                order.append(lane_ids[right])
        return order

    def greedy_place(ev: dict) -> str:
        # choose lane with smallest free_at that can start by ev["_s"]
        candidate = None
        best_time = None
        for lid in lane_ids:
            fa = free_at[lid]
            if fa <= ev["_s"] and (best_time is None or fa < best_time):
                best_time = fa
                candidate = lid
        if candidate is None:
            # spill: pick earliest finishing lane and start when it's free, clipped to ev end
            cid = min(lane_ids, key=lambda k: free_at[k])
            fa = free_at[cid]
            if fa < ev["_t"]:
                s2 = max(ev["_s"], fa)
                timelines[cid].append((s2, ev["_t"], ev.get("id"), "event"))
                free_at[cid] = ev["_t"]
                return cid
            return cid
        else:
            timelines[candidate].append((ev["_s"], ev["_t"], ev.get("id"), "event"))
            free_at[candidate] = ev["_t"]
            return candidate

    # pack
    norm.sort(key=lambda e: e["_s"])
    for ev in norm:
        eid = ev.get("id")
        s = ev["_s"]

        in_freeze = s <= now_utc + freeze_window
        in_stick = s <= now_utc + stick_window

        preferred_lane = prev_event_lane.get(eid) if eid else None
        placed = False

        if preferred_lane and (in_freeze or in_stick):
            # try preferred lane first
            if preferred_lane in lane_index and try_place_on(preferred_lane, ev):
                placed = True
            else:
                # try neighbors within affinity
                for lid in affinity_order(preferred_lane):
                    if lid == preferred_lane:
                        continue
                    if try_place_on(lid, ev):
                        placed = True
                        break

            # If still not placed:
            if not placed:
                # freeze window: do NOT spill; keep greedy within lanes that can start now (no truncation)
                if in_freeze:
                    candidate = None
                    best_time = None
                    for lid in lane_ids:
                        fa = free_at[lid]
                        if fa <= ev["_s"] and (best_time is None or fa < best_time):
                            best_time = fa
                            candidate = lid
                    if candidate:
                        timelines[candidate].append((ev["_s"], ev["_t"], eid, "event"))
                        free_at[candidate] = ev["_t"]
                        placed = True

        if not placed:
            greedy_place(ev)

    # fill placeholders
    plan_slots = []
    for lid in lane_ids:
        cursor = start_dt_utc
        for s, t, eid, kind in timelines[lid]:
            if s - cursor >= min_gap:
                plan_slots.append(
                    {
                        "channel_id": lid,
                        "event_id": None,
                        "start": cursor,
                        "end": s,
                        "kind": "placeholder",
                        "placeholder_reason": "no_event",
                    }
                )
            plan_slots.append(
                {
                    "channel_id": lid,
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
                    "channel_id": lid,
                    "event_id": None,
                    "start": cursor,
                    "end": end_dt_utc,
                    "kind": "placeholder",
                    "placeholder_reason": "tail_gap",
                }
            )

    plan_slots.sort(key=lambda r: (r["channel_id"], r["start"]))
    return plan_slots


# ----------------- CLI -----------------


def parse_args():
    ap = argparse.ArgumentParser(description="Sticky ESPN Clean v2 Plan Builder")
    ap.add_argument("--db", required=True)
    ap.add_argument("--valid-hours", type=int, default=72)
    ap.add_argument("--tz", default="America/New_York")
    ap.add_argument("--note", default="")
    ap.add_argument(
        "--min-gap-mins", type=int, default=5, help="min placeholder gap granularity"
    )
    ap.add_argument(
        "--lanes",
        type=int,
        default=40,
        help="seed this many lanes if channel table empty",
    )
    ap.add_argument(
        "--stick-window-hours",
        type=int,
        default=24,
        help="prefer previous lane within this horizon",
    )
    ap.add_argument(
        "--freeze-hours",
        type=int,
        default=3,
        help="never spill (no truncation) within this horizon",
    )
    ap.add_argument(
        "--lane-affinity",
        type=int,
        default=2,
        help="try ±N neighbor lanes around previous lane",
    )
    return ap.parse_args()


def main():
    args = parse_args()
    tz = ZoneInfo(args.tz)
    start_local = datetime.now(tz).replace(second=0, microsecond=0)
    start_utc = _floor_to_half_hour(start_local.astimezone(timezone.utc))
    end_utc = start_utc + timedelta(hours=args.valid_hours)
    min_gap = timedelta(minutes=args.min_gap_mins)

    conn = connect_db(args.db)
    seeded = seed_channels_if_empty(conn, args.lanes)
    channels = load_channels(conn)
    events = load_events(conn, start_utc.isoformat(), end_utc.isoformat())
    prev_map = read_prev_event_lanes(conn)
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)

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
        stick_window_h=args.stick_window_hours,
        freeze_h=args.freeze_hours,
        lane_affinity=args.lane_affinity,
        prev_event_map=len(prev_map),
    )

    plan_slots = build_plan_sticky(
        channels,
        events,
        start_utc,
        end_utc,
        min_gap,
        prev_event_lane=prev_map,
        now_utc=now_utc,
        stick_window=timedelta(hours=args.stick_window_hours),
        freeze_window=timedelta(hours=args.freeze_hours),
        lane_affinity=int(max(0, args.lane_affinity)),
    )

    # stats
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
