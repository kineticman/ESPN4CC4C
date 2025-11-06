# app/api_now.py
from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timezone
import sqlite3, os, contextlib, time, re

router = APIRouter(tags=["now"])
DB_PATH = os.getenv("VC_DB_PATH", "data/eplus_vc.sqlite3")

UID_RE = re.compile(r"^espn-watch:([0-9a-fA-F-]{36}):")

def _derive_espn_uid(events_id: str | None) -> str | None:
    if not events_id:
        return None
    m = UID_RE.match(events_id)
    return m.group(1) if m else None

def _row_to_dict(cur, row):
    return {d[0]: row[i] for i, d in enumerate(cur.description)}

@contextlib.contextmanager
def _cx():
    cx = sqlite3.connect(DB_PATH)
    try:
        cx.row_factory = lambda cur, row: _row_to_dict(cur, row)
        yield cx
    finally:
        cx.close()

def _now_epoch():
    return int(time.time())

@router.get("/api/now")
def api_now(
    chan: int | None = Query(default=None, description="Virtual channel number (e.g., 2405)"),
    vc: int | None = Query(default=None, alias="lane", description="Lane number (e.g., 5)"),
    include_placeholders: bool = False,
):
    if not chan and vc is None:
        raise HTTPException(400, "Provide chan=<number> or lane=<int>")

    now = _now_epoch()

    sql = """
    SELECT
      ps.chno,
      ps.lane,
      ps.event_id,
      ps.title AS slot_title,
      ps.start_utc,
      ps.end_utc,
      ps.is_placeholder,
      ps.placeholder_reason,
      ps.preferred_feed_url,
      ps.feed_url,
      e.title AS event_title,
      e.id    AS event_pk
    FROM plan_slot ps
    JOIN events e ON e.id = ps.event_id
    WHERE (?1 IS NULL OR ps.chno = ?1)
      AND (?2 IS NULL OR ps.lane = ?2)
      AND ?3 BETWEEN ps.start_utc AND ps.end_utc
      AND (?4 = 1 OR ps.is_placeholder = 0)
    ORDER BY ps.start_utc DESC
    LIMIT 1;
    """

    with _cx() as cx:
        row = cx.execute(sql, (chan, vc, now, 1 if include_placeholders else 0)).fetchone()

    if not row:
        raise HTTPException(404, "No live slot for the requested channel")

    espn_uid = _derive_espn_uid(row["event_pk"])

    return {
      "channel": {"number": row["chno"], "lane": row["lane"]},
      "state": "live" if row["is_placeholder"] == 0 else "placeholder",
      "window": {"start_utc": row["start_utc"], "end_utc": row["end_utc"]},
      "title": row["event_title"] or row["slot_title"],
      "feeds": {
        "preferred": row["preferred_feed_url"],
        "fallback": row["feed_url"],
      },
      "espn": {
        "uid": espn_uid,           # <-- derived playable UID (UUID)
        "event_id": None,          # numeric ESPN event id not present in DB
        "web_url": None            # not present in DB
      }
    }

@router.get("/api/lookup")
def api_lookup(
    espn_uid: str = Query(..., description="Playable ESPN UID (UUID)"),
):
    # Find current slot where events.id contains that UID
    # events.id shape: espn-watch:<UUID>:<hash>
    now = _now_epoch()
    like_pat = f"espn-watch:{espn_uid}:%"

    sql = """
    SELECT
      ps.chno,
      ps.lane,
      ps.event_id,
      ps.title AS slot_title,
      ps.start_utc,
      ps.end_utc,
      ps.is_placeholder,
      e.title AS event_title,
      e.id    AS event_pk
    FROM plan_slot ps
    JOIN events e ON e.id = ps.event_id
    WHERE e.id LIKE ?1
      AND ?2 BETWEEN ps.start_utc AND ps.end_utc
    ORDER BY ps.start_utc DESC
    LIMIT 1;
    """

    with _cx() as cx:
        row = cx.execute(sql, (like_pat, now)).fetchone()

    if not row:
        raise HTTPException(404, "No live slot for the provided UID")

    return {
      "channel": {"number": row["chno"], "lane": row["lane"]},
      "state": "live" if row["is_placeholder"] == 0 else "placeholder",
      "window": {"start_utc": row["start_utc"], "end_utc": row["end_utc"]},
      "title": row["event_title"] or row["slot_title"],
      "espn": {
        "uid": espn_uid,
        "event_id": None,
        "web_url": None
      }
    }
