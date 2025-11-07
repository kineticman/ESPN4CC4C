#!/usr/bin/env python3
import json
from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.responses import JSONResponse, HTMLResponse
import os, sqlite3, datetime as dt, traceback
from typing import Optional

from urllib.parse import quote

# --- ChromeCapture config ---
CC_HOST = os.getenv("CC_HOST")          # defaults to resolver host if not set
CC_PORT = os.getenv("CC_PORT", "5589")  # default 5589
M3U_GROUP_TITLE = os.getenv("M3U_GROUP_TITLE", "ESPN+ VC")
VC_RESOLVER_BASE_URL = os.getenv("VC_RESOLVER_BASE_URL")  # optional, preferred if set

def _derive_host_from_base(vc_base: str) -> str:
    # vc_base like "http://192.168.86.72:8094"
    return vc_base.split("://", 1)[1].split("/", 1)[0].split(":")[0]

def _vc_base_from_request(request: Request) -> str:
    """
    Prefer VC_RESOLVER_BASE_URL (LAN IP guardrail).
    Fallback: request.base_url (handles reverse proxy/local testing).
    """
    if VC_RESOLVER_BASE_URL:
        return VC_RESOLVER_BASE_URL.rstrip("/")
    return str(request.base_url).rstrip("/")  # request.base_url has trailing slash

def _cc_base(vc_base: str) -> str:
    """
    chrome://<host>:<port>/stream?url=
    Host preference: CC_HOST (if set) else host from vc_base.
    """
    host = CC_HOST or _derive_host_from_base(vc_base)
    return f"chrome://{host}:{CC_PORT}/stream?url="

def _wrap_for_cc(vc_url: str, vc_base: str) -> str:
    return _cc_base(vc_base) + quote(vc_url, safe="")
# --- end ChromeCapture config ---


# --- slate support ---
SLATE_TMPL = os.getenv('VC_SLATE_URL_TEMPLATE', '/slate?lane={lane}')
def _slate_url(lane: str) -> str:
    tmpl = SLATE_TMPL
    try:
        return tmpl.format(lane=lane) if tmpl else ''
    except Exception:
        return ''
def slate_redirect(lane: str):
    url = _slate_url(lane)
    return RedirectResponse(url, status_code=302) if url else None
# --- end slate support ---

try:
    from config import (
        RESOLVER_SLATE_URL as CFG_SLATE_URL,
    )
except Exception:
    CFG_SLATE_URL = ""
app = FastAPI()




@app.middleware("http")
async def _debug_slate_mid(request: Request, call_next):
    resp = await call_next(request)
    p = request.url.path
    if resp.status_code == 200 and p.startswith('/vc/') and p.endswith('/debug'):
        try:
            lane = p.split('/')[2]
            # Capture body bytes from StreamingResponse/JSONResponse
            body = b''
            if hasattr(resp, 'body_iterator') and resp.body_iterator is not None:
                async for chunk in resp.body_iterator:
                    body += chunk
            elif hasattr(resp, 'body') and isinstance(resp.body, (bytes, bytearray)):
                body = bytes(resp.body)
            if body:
                data = json.loads(body.decode('utf-8'))
                if isinstance(data, dict) and not data.get('slate'):
                    data['slate'] = _slate_url(lane)
                    new = JSONResponse(content=data, status_code=resp.status_code)
                    # Preserve headers except length (will be recalculated)
                    for k, v in resp.headers.items():
                        if k.lower() != 'content-length':
                            new.headers[k] = v
                    return new
        except Exception:
            pass
    return resp
@app.middleware("http")
async def _slate_mid(request: Request, call_next):
    resp = await call_next(request)
    p = request.url.path
    if resp.status_code == 404 and p.startswith('/vc/') and p.count('/') == 2:
        lane = p.split('/')[2]
        url = _slate_url(lane)
        if url:
            return RedirectResponse(url, status_code=302)
    return resp
import os
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
OUT_DIR = os.path.join(BASE_DIR, "out")
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Serve /out/* (XML, M3U) and /static/* (slate page, etc.)
try:
    app.mount("/out", StaticFiles(directory=OUT_DIR), name="out")
    app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")
except Exception:
    # In case directories are missing in a fresh checkout; mounts are optional
    pass


DB_DEFAULT = "data/eplus_vc.sqlite3"
db_path = os.environ.get("VC_DB", DB_DEFAULT)  # global for debug/logs

def db() -> sqlite3.Connection:
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

@app.get("/channels_db")
def channels_db():
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
    _sl = _slate_url(lane)
    slate_url = _slate_url(lane)
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
        try:
            _resp
        except NameError:
            _resp = None
        try:
            (out if 'out' in locals() else _resp)['slate'] = _slate_url(lane)
        except Exception:
            pass
        return JSONResponse(info)
    except Exception as outer:
        info["error"] = str(outer)
        return JSONResponse(info, status_code=500)


@app.get("/standby")
def standby(lane: Optional[str] = None):
    """
    Back-compat convenience: redirect /standby?lane=... to the configured slate URL.
    Also catches any legacy links that referenced a static page.
    """
    q = f"{lane}" if lane else ""
    return slate_redirect(q) or HTMLResponse("<h1>Stand By</h1>", status_code=200)

@app.get("/slate")
def slate_page():
    """Serve the standby page from static/slate.html."""
    path = os.path.join(STATIC_DIR, "slate.html")
    if os.path.exists(path):
        return FileResponse(path, media_type="text/html")
    return HTMLResponse("<h1>Stand By</h1><p>No live event scheduled.</p>")

# Ensure OUT_DIR
try:
    OUT_DIR
except NameError:
    OUT_DIR = os.getenv("OUT","./out")

@app.get("/epg.xml")
def epg_xml():
    """Latest XMLTV from out/epg.xml"""
    path = os.getenv("VC_EPG_PATH", os.path.join(OUT_DIR, "epg.xml"))
    if os.path.exists(path):
        return FileResponse(path, media_type="application/xml")
    return Response("# not found\n", status_code=404, media_type="text/plain")

@app.get("/playlist.m3u")
def playlist_m3u():
    """Serve M3U: prefer VC_M3U_PATH; else /out/playlist.m3u."""
    p = os.getenv("VC_M3U_PATH") or os.path.join(OUT_DIR, "playlist.m3u")
    if os.path.exists(p):
        return FileResponse(p, media_type="application/x-mpegURL", filename="playlist.m3u")
    return Response("# not found\n", status_code=404, media_type="text/plain")


def _load_channels_from_xmltv(xml_path):
    try:
        import xml.etree.ElementTree as ET
        root = ET.parse(xml_path).getroot()
        return [{"id": c.get("id"), "name": (c.findtext("display-name") or "").strip()} for c in root.findall("channel")]
    except Exception:
        return []

@app.get("/channels")
def channels_json():
    xml = os.getenv("VC_EPG_PATH", os.path.join(OUT_DIR, "epg.xml"))
    if not os.path.exists(xml):
        return Response("[]\n", media_type="application/json")
    chans = _load_channels_from_xmltv(xml)
    # try to read <lcn> if present
    try:
        import xml.etree.ElementTree as ET
        root = ET.parse(xml).getroot()
        lcn_map = {}
        for c in root.findall("channel"):
            cid = c.get("id")
            lcn = c.findtext("lcn")
            if cid and lcn: lcn_map[cid] = lcn
        for c in chans:
            if c["id"] in lcn_map: c["lcn"] = lcn_map[c["id"]]
    except Exception:
        pass
    import json
    return Response(json.dumps(chans), media_type="application/json")


@app.get("/whatson/{lane}", response_class=JSONResponse)
def whatson(lane: str, at: Optional[str] = None, format: Optional[str] = None):
    # Normalize time like other endpoints
    def _parse_at(val: Optional[str]) -> dt.datetime:
        if not val:
            return dt.datetime.now(dt.timezone.utc)
        v = val.strip().replace(" ", "T")
        try:
            if v.endswith("Z"):
                return dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
            if "+" in v[10:] or "-" in v[10:]:
                return dt.datetime.fromisoformat(v)
            return dt.datetime.fromisoformat(v).replace(tzinfo=dt.timezone.utc)
        except Exception:
            try:
                return dt.datetime.fromisoformat(v).replace(tzinfo=dt.timezone.utc)
            except Exception:
                return dt.datetime.now(dt.timezone.utc)

    when = _parse_at(at)
    when_iso = when.astimezone(dt.timezone.utc).isoformat(timespec="seconds")

    # Normalize lane input; accept "10" or "eplus10"
    lane_str = str(lane).strip()
    num = None
    if lane_str.lower().startswith("eplus") and lane_str[5:].isdigit():
        num = int(lane_str[5:])
    elif lane_str.isdigit():
        num = int(lane_str)
    normalized_lane = num if num is not None else lane_str

    # Candidate channel_ids (supports DBs storing "eplus10" or "10")
    candidates = []
    if num is not None:
        candidates = [f"eplus{num}", str(num)]
    else:
        candidates = [lane_str]

    db_path = os.getenv("VC_DB", "data/eplus_vc.sqlite3")
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"DB open failed: {e}"}, status_code=404)

    try:
        cur = conn.cursor()
        # latest plan
        cur.execute("SELECT MAX(id) FROM plan_run")
        row = cur.fetchone()
        if not row or row[0] is None:
            return JSONResponse({"ok": False, "error": "No plan_run rows"}, status_code=404)
        plan_id = row[0]

        # First attempt: IN (candidates)
        placeholders = ",".join(["?"] * len(candidates))
        cur.execute(
            f"""
            SELECT channel_id, kind, event_id
            FROM plan_slot
            WHERE plan_id = ?
              AND channel_id IN ({placeholders})
              AND start_utc <= ?
              AND end_utc > ?
            ORDER BY start_utc DESC
            LIMIT 1
            """,
            (plan_id, *candidates, when_iso, when_iso),
        )
        hit = cur.fetchone()

        # If nothing matched (e.g., DB stores bare numbers or different casing), try a fallback:
        # derive a looser numeric from any candidate and try both text/int comparisons via CAST
        if not hit and num is not None:
            cur.execute(
                """
                SELECT channel_id, kind, event_id
                FROM plan_slot
                WHERE plan_id = ?
                  AND (channel_id = ? OR channel_id = ? OR CAST(channel_id AS TEXT) = ?)
                  AND start_utc <= ?
                  AND end_utc > ?
                ORDER BY start_utc DESC
                LIMIT 1
                """,
                (plan_id, f"eplus{num}", num, str(num), when_iso, when_iso),
            )
            hit = cur.fetchone()

        if not hit:
            # Always return JSON so jq never errors
            return JSONResponse({"ok": True, "lane": normalized_lane, "event_uid": None, "at": when_iso}, status_code=200)

        _, kind, eid = hit
        if kind == "event" and eid:
            # Strip espn-watch prefix if present
            if eid.startswith("espn-watch:"):
                eid = eid[11:]
            # format=txt -> return play_id only as text/plain
            if (format or "").lower() == "txt":
                play_id = eid.split(":", 1)[0]
                return Response(content=play_id, media_type="text/plain", status_code=200)
            return JSONResponse({"ok": True, "lane": normalized_lane, "event_uid": eid, "at": when_iso}, status_code=200)
        else:
            # No event -> 204 for txt (empty), JSON otherwise
            if (format or "").lower() == "txt":
                return Response(status_code=204)
            return JSONResponse({"ok": True, "lane": normalized_lane, "event_uid": None, "at": when_iso}, status_code=200)
    finally:
        conn.close()
@app.get("/whatson_all", response_class=JSONResponse)
def whatson_all(at: Optional[str] = None):
    def _to_lane_label(chid: str):
        s = str(chid)
        if s.lower().startswith("eplus") and s[5:].isdigit():
            return int(s[5:])
        if s.isdigit():
            return int(s)
        return s
    # Return the ESPN UID for every lane at the requested time (default: now UTC).
    # Response:
    # { "ok": true, "at": "<utc-iso>", "items": [ {"lane": "eplus1", "event_uid": "..." | null}, ... ] }
    def _parse_at(val: Optional[str]) -> dt.datetime:
        if not val:
            return dt.datetime.now(dt.timezone.utc)
        v = val.strip().replace(" ", "T")
        try:
            if v.endswith("Z"):
                return dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
            if "+" in v[10:] or "-" in v[10:]:
                return dt.datetime.fromisoformat(v)
            return dt.datetime.fromisoformat(v).replace(tzinfo=dt.timezone.utc)
        except Exception:
            try:
                return dt.datetime.fromisoformat(v).replace(tzinfo=dt.timezone.utc)
            except Exception:
                return dt.datetime.now(dt.timezone.utc)

    when = _parse_at(at)
    when_iso = when.astimezone(dt.timezone.utc).isoformat(timespec="seconds")

    db_path = os.getenv("VC_DB", "data/eplus_vc.sqlite3")
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"DB open failed: {e}"}, status_code=404)

    try:
        cur = conn.cursor()
        cur.execute("SELECT MAX(id) FROM plan_run")
        row = cur.fetchone()
        if not row or row[0] is None:
            return JSONResponse({"ok": False, "error": "No plan_run rows"}, status_code=404)
        plan_id = row[0]

        # Get all lanes that exist in this plan
        cur.execute("SELECT DISTINCT channel_id FROM plan_slot WHERE plan_id = ?", (plan_id,))
        lanes = [r[0] for r in cur.fetchall()]

        # Get current slot per lane at 'when'
        cur.execute(
            """
            SELECT channel_id, kind, event_id
            FROM plan_slot
            WHERE plan_id = ?
              AND start_utc <= ?
              AND end_utc   > ?
            """,
            (plan_id, when_iso, when_iso),
        )
        active = {row[0]: (row[1], row[2]) for row in cur.fetchall()}

        items = []
        def _sort_key(x):
            lbl = _to_lane_label(x)
            return (0, lbl) if isinstance(lbl, int) else (1, str(lbl).lower())
        for lane in sorted(lanes, key=_sort_key):
            kind, eid = active.get(lane, (None, None))
            uid = (eid[11:] if (kind == "event" and eid and eid.startswith("espn-watch:")) else (eid if kind == "event" else None))
            items.append({"lane": _to_lane_label(lane), "event_uid": uid})

        return JSONResponse({"ok": True, "at": when_iso, "items": items}, status_code=200)
    finally:
        conn.close()

