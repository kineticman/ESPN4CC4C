#!/usr/bin/env python3
import json
import os
import sqlite3
import datetime as dt
import traceback
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import (
    FileResponse,
    RedirectResponse,
    Response,
    JSONResponse,
    HTMLResponse,
    PlainTextResponse,
)

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
SLATE_TMPL = os.getenv("VC_SLATE_URL_TEMPLATE", "/slate?lane={lane}")

def _slate_url(lane: str) -> str:
    tmpl = SLATE_TMPL
    try:
        return tmpl.format(lane=lane) if tmpl else ""
    except Exception:
        return ""

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

# === Middlewares to fill in slate on /vc/*/debug and redirect /vc/<lane> 404 to slate ===
@app.middleware("http")
async def _debug_slate_mid(request: Request, call_next):
    resp = await call_next(request)
    p = request.url.path
    if resp.status_code == 200 and p.startswith("/vc/") and p.endswith("/debug"):
        try:
            lane = p.split("/")[2]
            # Capture body bytes
            body = b""
            if hasattr(resp, "body_iterator") and resp.body_iterator is not None:
                async for chunk in resp.body_iterator:
                    body += chunk
            elif hasattr(resp, "body") and isinstance(resp.body, (bytes, bytearray)):
                body = bytes(resp.body)
            if body:
                data = json.loads(body.decode("utf-8"))
                if isinstance(data, dict) and not data.get("slate"):
                    data["slate"] = _slate_url(lane)
                    new = JSONResponse(content=data, status_code=resp.status_code)
                    for k, v in resp.headers.items():
                        if k.lower() != "content-length":
                            new.headers[k] = v
                    return new
        except Exception:
            pass
    return resp

@app.middleware("http")
async def _slate_mid(request: Request, call_next):
    resp = await call_next(request)
    p = request.url.path
    if resp.status_code == 404 and p.startswith("/vc/") and p.count("/") == 2:
        lane = p.split("/")[2]
        url = _slate_url(lane)
        if url:
            return RedirectResponse(url, status_code=302)
    return resp

# --- Paths / directories ---
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

# --- DB helpers ---
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
        return v.replace("Z", "+00:00")
    try:
        t = dt.datetime.fromisoformat(v)
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        return t.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
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
       WHERE s.plan_id = (SELECT MAX(plan_id) FROM plan_slot)
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
            (preferred_feed_id, event_id),
        ).fetchone()
        if r and r["url"]:
            return r["url"]
    r = conn.execute(
        "SELECT url FROM feeds WHERE event_id=? AND url IS NOT NULL ORDER BY is_primary DESC, id DESC LIMIT 1",
        (event_id,),
    ).fetchone()
    if r and r["url"]:
        return r["url"]
    return None

# --- Health ---
@app.get("/health")
def health():
    return {"ok": True, "ts": now_utc_iso()}

# --- Channels (DB-backed) ---
@app.get("/channels_db", tags=["channels"], summary="DB-backed channel list", response_class=JSONResponse)
def channels_db():
    try:
        with db() as conn:
            lanes = [
                dict(row)
                for row in conn.execute(
                    "SELECT id AS channel_id, chno, name FROM channel WHERE active=1 ORDER BY chno"
                ).fetchall()
            ]
            return {"ok": True, "count": len(lanes), "channels": lanes}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# --- XML helpers & channels (XMLTV-backed) ---
def _load_channels_from_xmltv(xml_path):
    try:
        import xml.etree.ElementTree as ET
        root = ET.parse(xml_path).getroot()
        return [{"id": c.get("id"), "name": (c.findtext("display-name") or "").strip()} for c in root.findall("channel")]
    except Exception:
        return []

# --- NEW helpers: file & DB fallbacks for /channels ---
def _load_channels_from_file(json_path: str):
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            return data
    except Exception:
        pass
    return []

def _channels_from_db_path(dbp: str):
    conn = None
    try:
        conn = sqlite3.connect(f"file:{dbp}?mode=ro", uri=True, check_same_thread=False, timeout=2.0)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT CAST(id AS TEXT) AS id,
                   COALESCE(name, printf('ESPN+ EPlus %d', id)) AS name,
                   CAST(COALESCE(chno, 20009 + id) AS TEXT)     AS lcn
            FROM channel
            WHERE COALESCE(active,1)=1
            ORDER BY COALESCE(chno,id)
        """).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

# --- Preferred /channels (File → DB → XMLTV) ---
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

# --- Standby / Slate ---
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

# --- Artifacts: epg.xml / playlist.m3u ---
try:
    OUT_DIR
except NameError:
    OUT_DIR = os.getenv("OUT", "./out")

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


# --- simple deeplink endpoint (text/plain) ---
@app.get("/deeplink/{lane}", response_class=PlainTextResponse, tags=["vc"])
def deeplink_lane(lane: str, at: Optional[str] = None):
    # 200 with body = deeplink string
    # 204 if no deeplink available (no current event)
    try:
        at_iso = parse_at(at or "")
        lane_str = str(lane).strip()
        if lane_str.lower().startswith("eplus") and lane_str[5:].isdigit():
            num = int(lane_str[5:])
        elif lane_str.isdigit():
            num = int(lane_str)
        else:
            num = None
        candidates = [f"eplus{num}", str(num)] if num is not None else [lane_str]

        with db() as conn:
            slot = None
            for cand in candidates:
                slot = current_slot(conn, cand, at_iso)
                if slot:
                    break

            if not slot or slot.get("kind") != "event" or not slot.get("event_id"):
                return PlainTextResponse("", status_code=204)

            eid = slot.get("event_id") or ""
            if eid.startswith("espn-watch:"):
                eid = eid[11:]  # strip prefix, keep full playID suffix

            eid_short = (str(eid).split(':', 1)[0] if eid else None)
            deeplink_full = (f"sportscenter://x-callback-url/showWatchStream?playID={eid_short}" if eid_short else None)
            return PlainTextResponse(deeplink_full, status_code=200)
    except Exception:
        return PlainTextResponse("", status_code=204)

# --- whatson with deeplink support ---
@app.get("/whatson/{lane}", response_class=JSONResponse)
def whatson(
    lane: str,
    at: Optional[str] = None,
    format: Optional[str] = None,
    include: Optional[str] = None,
    deeplink: Optional[int] = None,
    dynamic: Optional[int] = None,
    param: Optional[str] = None,
):
    """
    Returns the current ESPN event UID for a lane at time 'at' (default: now UTC).
    New:
      - include=deeplink (or include=1 / deeplink=1 / dynamic=1) => adds "deeplink_url" to JSON.
      - param=deeplink_url&format=txt => returns just the deeplink URL (text/plain).
      - format=txt (without param) => legacy short playId (before ':').
    """
    # Normalize time
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

    # Accept "6" or "eplus6"
    lane_str = str(lane).strip()
    num = int(lane_str[5:]) if (lane_str.lower().startswith("eplus") and lane_str[5:].isdigit()) else (int(lane_str) if lane_str.isdigit() else None)
    normalized_lane = num if num is not None else lane_str
    candidates = [f"eplus{num}", str(num)] if num is not None else [lane_str]

    # Flags for deeplink outputs
    fmt = (format or "").lower()
    param_l = (param or "").lower() if isinstance(param, str) else ""

    # JSON controls
    want_deeplink_full_json = False
    want_deeplink_field = (isinstance(include, str) and include.lower() in ("deeplink", "1", "true")) or (deeplink == 1) or (dynamic == 1)

    # TXT output modes:
    # - format=txt&param=deeplink_url_full        -> full deeplink (playID with suffix)
    # - format=txt&param=deeplink_url[_short]     -> short deeplink (playID before ':')
    # - format=txt                                -> short playID only (legacy)
    want_txt_deeplink_full  = (param_l == "deeplink_url" and fmt == "txt")
    want_txt_deeplink_short = (param_l in ("deeplink_url","deeplink_url_short","deeplink_url") and fmt == "txt")
    want_txt_playid_short   = (param_l == "" and fmt == "txt")

    db_path_env = os.getenv("VC_DB", "data/eplus_vc.sqlite3")
    try:
        conn = sqlite3.connect(f"file:{db_path_env}?mode=ro", uri=True)
    except Exception as e:
        if want_txt_deeplink_short or want_txt_playid_short:
            return Response(status_code=404)
        return JSONResponse({"ok": False, "error": f"DB open failed: {e}"}, status_code=404)

    try:
        cur = conn.cursor()
        cur.execute("SELECT MAX(id) FROM plan_run")
        row = cur.fetchone()
        if not row or row[0] is None:
            if want_txt_deeplink_short or want_txt_playid_short:
                return Response(status_code=204)
            return JSONResponse({"ok": False, "error": "No plan_run rows"}, status_code=404)
        plan_id = row[0]

        # Try exact IN first
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

        # Fallback: try numeric/CAST if needed
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

        # No current slot or placeholder
        if not hit:
            if want_txt_deeplink_short or want_txt_playid_short:
                return Response(status_code=204)
            body = {"ok": True, "lane": normalized_lane, "event_uid": None, "at": when_iso, "deeplink_url": None}
            return JSONResponse(body, status_code=200)

        _, kind, eid = hit
        if not (kind == "event" and eid):
            if want_txt_deeplink_short or want_txt_playid_short:
                return Response(status_code=204)
            body = {"ok": True, "lane": normalized_lane, "event_uid": None, "at": when_iso, "deeplink_url": None}
            return JSONResponse(body, status_code=200)

        # Strip espn-watch: prefix only; KEEP any :suffix
        if eid.startswith("espn-watch:"):
            eid = eid[11:]

        # Build deeplinks with proper None handling
        play_id_short = eid.split(':', 1)[0] if eid else None
        deeplink_full = f"sportscenter://x-callback-url/showWatchStream?playID={eid}" if eid else None
        deeplink_short = f"sportscenter://x-callback-url/showWatchStream?playID={play_id_short}" if play_id_short else None
        
        # TXT modes
        if want_txt_deeplink_full:
            return Response(content=deeplink_full, media_type="text/plain", status_code=200)
        if want_txt_deeplink_short:
            return Response(content=deeplink_short, media_type="text/plain", status_code=200)
        if want_txt_playid_short:
            return Response(content=play_id_short, media_type="text/plain", status_code=200)

        # JSON body
        body = {"ok": True, "lane": normalized_lane, "event_uid": eid, "at": when_iso, "deeplink_url": deeplink_short}
        return JSONResponse(body, status_code=200)
    finally:
        try:
            conn.close()
        except Exception:
            pass

# --- whatson_all (+ optional deeplinks) ---
@app.get("/whatson_all", response_class=JSONResponse)
def whatson_all(at: Optional[str] = None, include: Optional[str] = None, deeplink: Optional[int] = None, dynamic: Optional[int] = None):
    want_deeplink_field = (isinstance(include, str) and include.lower() in ("deeplink", "1", "true")) or (deeplink == 1) or (dynamic == 1)
    want_deeplink_full_json = False

    def _to_lane_label(chid: str):
        s = str(chid)
        if s.lower().startswith("eplus") and s[5:].isdigit():
            return int(s[5:])
        if s.isdigit():
            return int(s)
        return s

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

    db_path_env = os.getenv("VC_DB", "data/eplus_vc.sqlite3")
    try:
        conn = sqlite3.connect(f"file:{db_path_env}?mode=ro", uri=True)
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
            short = (str(uid).split(':', 1)[0] if uid else None)
            item = {"lane": _to_lane_label(lane), "event_uid": uid, "deeplink_url": (f"sportscenter://x-callback-url/showWatchStream?playID={short}" if short else None)}
            items.append(item)

        return JSONResponse({"ok": True, "at": when_iso, "items": items}, status_code=200)
    finally:
        conn.close()
@app.get("/channels", tags=["channels"], summary="DB-backed channel list (authoritative)")
def channels():
    """
    Authoritative channel list from the DB only.
    Uses table: channel(id, name, chno, active).
    If chno is null/invalid, synthesize LCN = 20009 + id.
    """
    import os
    import sqlite3

    dbp = os.environ.get("VC_DB", "data/eplus_vc.sqlite3")
    con = sqlite3.connect(f"file:{dbp}?mode=ro", uri=True, check_same_thread=False, timeout=2.0)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT id, name, chno, COALESCE(active,1) AS active
            FROM channel
            WHERE COALESCE(active,1)=1
            ORDER BY COALESCE(chno,id)
            """
        ).fetchall()

        out = []
        for r in rows:
            ch_id = int(r["id"])
            name  = (r["name"] or f"ESPN+ EPlus {ch_id}").strip()
            chno  = r["chno"]
            try:
                lcn = int(chno) if chno is not None else None
            except Exception:
                lcn = None
            if lcn is None:
                lcn = 20009 + ch_id
            out.append({"id": str(ch_id), "name": name, "lcn": str(lcn)})
        return out
    finally:
        try:
            con.close()
        except Exception:
            pass
