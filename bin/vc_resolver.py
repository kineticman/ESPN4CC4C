#!/usr/bin/env python3
from fastapi import FastAPI, Response, Request
from fastapi.responses import JSONResponse
import os, sqlite3, datetime as dt, traceback
from typing import Optional

try:
    from config import (
        RESOLVER_DB_DEFAULT as CFG_DB_DEFAULT,
        RESOLVER_SLATE_URL as CFG_SLATE_URL,
    )
except Exception:
    CFG_DB_DEFAULT = CFG_DB_DEFAULT
    CFG_SLATE_URL = ""
app = FastAPI()

DB_DEFAULT = "data/eplus_vc.sqlite3"

def db() -> sqlite3.Connection:
    db_path = os.getenv("VC_DB", CFG_DB_DEFAULT)
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=2.0)
    conn.row_factory = sqlite3.Row
    return conn

def now_utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()

def parse_at(value: Optional[str]) -> str:
    """Return an ISO UTC string. Accepts Z or offset or naive (assumed UTC)."""
    if not value:
        return now_utc_iso()
    v = value.strip()
    if v.endswith("Z"):
        return v.replace("Z","+00:00")
    try:
        # let fromisoformat parse offsets; treat naive as UTC
        t = dt.datetime.fromisoformat(v)
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        return t.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        # fallback: try space separated "YYYY-mm-dd HH:MM:SS"
        try:
            t = dt.datetime.strptime(v, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
            return t.isoformat()
        except Exception:
            return now_utc_iso()

def latest_plan_id(conn: sqlite3.Connection) -> Optional[int]:
    row = conn.execute("SELECT MAX(plan_id) AS pid FROM plan_slot").fetchone()
    return int(row["pid"]) if row and row["pid"] is not None else None

def current_slot(conn: sqlite3.Connection, lane: str, at_iso: str):
    q = """
      SELECT s.channel_id, s.start_utc, s.end_utc, s.event_id, s.kind, s.preferred_feed_id
        FROM plan_slot s
       WHERE s.plan_id=(SELECT MAX(plan_id) FROM plan_slot)
         AND s.channel_id = ?
         AND s.start_utc <= ? AND s.end_utc > ?
       ORDER BY s.start_utc DESC
       LIMIT 1
    """
    r = conn.execute(q, (lane, at_iso, at_iso)).fetchone()
    return dict(r) if r else None

def best_feed_for_event(conn: sqlite3.Connection, event_id: str, preferred_feed_id: Optional[str]) -> Optional[str]:
    # v2 feeds(event_id, url, is_primary)
    if preferred_feed_id:
        r = conn.execute(
            "SELECT url FROM feeds WHERE id=? AND event_id=? LIMIT 1",
            (preferred_feed_id, event_id)
        ).fetchone()
        if r and r["url"]:
            return r["url"]
    r = conn.execute(
        "SELECT url FROM feeds WHERE event_id=? AND url IS NOT NULL ORDER BY is_primary DESC, id DESC LIMIT 1",
        (event_id,)
    ).fetchone()
    if r and r["url"]:
        return r["url"]
    # no events.player_url in v2 schema, so no further fallback
    return None

@app.get("/health")
def health():
    return {"ok": True, "ts": now_utc_iso()}

@app.get("/channels")
def channels():
    try:
        with db() as conn:
            lanes = [
                dict(row) for row in conn.execute(
                    "SELECT id AS channel_id, chno, name FROM channel WHERE active=1 ORDER BY chno"
                ).fetchall()
            ]
            return {"ok": True, "count": len(lanes), "channels": lanes}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.get("/vc/{lane}")
def tune(lane: str, request: Request, only_live: int = 0, at: str | None = None):
    try:
        at_iso = parse_at(at)
        with db() as conn:
            slot = current_slot(conn, lane, at_iso)
            # no event or placeholder
            if not slot or slot.get("kind") != "event" or not slot.get("event_id"):
                slate = os.getenv("VC_SLATE_URL", CFG_SLATE_URL).strip()
                if not only_live and slate:
                    return Response(status_code=302, headers={"Location": slate})
                return Response(status_code=204 if only_live else 404)
            # we have an event -> try to get a feed
            target = best_feed_for_event(conn, slot["event_id"], slot.get("preferred_feed_id"))
            if target:
                return Response(status_code=302, headers={"Location": target})
            # event but no feed
            slate = os.getenv("VC_SLATE_URL", CFG_SLATE_URL).strip()
            if not only_live and slate:
                return Response(status_code=302, headers={"Location": slate})
            return Response(status_code=204 if only_live else 404)
    except Exception:
        return Response(content="Internal Server Error", status_code=500, media_type="text/plain")

@app.get("/vc/{lane}/debug")
def debug_lane(lane: str, at: Optional[str] = None):
    info = {"lane": lane}
    try:
        at_iso = parse_at(at)
        info["now"] = at_iso
        with db() as conn:
            try:
                slot = current_slot(conn, lane, at_iso)
                info["slot"] = slot
                if slot and slot.get("event_id"):
                    info["feed"] = best_feed_for_event(conn, slot["event_id"], slot.get("preferred_feed_id"))
                else:
                    info["feed"] = None
                info["slate"] = os.getenv("VC_SLATE_URL", CFG_SLATE_URL).strip()
            except Exception as inner:
                info["slot"] = None
                info["feed"] = None
                info["slate"] = os.getenv("VC_SLATE_URL", CFG_SLATE_URL).strip()
                info["exception"] = str(inner)
                info["trace"] = traceback.format_exc().splitlines()[-4:]
        return JSONResponse(info)
    except Exception as outer:
        info["error"] = str(outer)
        return JSONResponse(info, status_code=500)
