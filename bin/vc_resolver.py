#!/usr/bin/env python3
import datetime as dt
import json
import os
import sqlite3
import traceback
import logging
import subprocess
from typing import Dict, Any, Optional
from urllib.parse import quote
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from pathlib import Path
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               PlainTextResponse, RedirectResponse, Response)
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Scheduler functions ---
def run_refresh(source: str = "auto"):
    """Run the database refresh script"""
    import time
    global last_refresh_info

    start_time = time.time()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    # record overall + per-source timestamps
    last_refresh_info["last_run"] = now_iso
    last_refresh_info["last_status"] = "running"
    last_refresh_info["last_duration"] = None
    last_refresh_info["last_error"] = None
    last_refresh_info["last_source"] = source

    if source == "manual":
        last_refresh_info["last_manual_run"] = now_iso
    else:
        last_refresh_info["last_auto_run"] = now_iso

    try:
        logger.info("Starting scheduled database refresh...")
        result = subprocess.run(
            ["python3", "/app/bin/refresh_in_container.py"],
            capture_output=True,
            text=True,
            timeout=3600,
        )

        duration = time.time() - start_time
        last_refresh_info["last_duration"] = f"{duration:.1f}s"

        if result.returncode == 0:
            logger.info("Database refresh completed successfully")
            last_refresh_info["last_status"] = "success"
        else:
            logger.error(f"Database refresh failed with code {result.returncode}")
            last_refresh_info["last_status"] = "failed"
            last_refresh_info["last_error"] = result.stderr[:500] if result.stderr else "Unknown error"
    except subprocess.TimeoutExpired:
        logger.error("Database refresh timed out after 1 hour")
        last_refresh_info["last_status"] = "timeout"
        last_refresh_info["last_error"] = "Refresh timed out after 1 hour"
    except Exception as e:
        logger.error(f"Error running database refresh: {e}")
        last_refresh_info["last_status"] = "error"
        last_refresh_info["last_error"] = str(e)

def run_vacuum(source: str = "auto"):
    """Run the weekly VACUUM operation"""
    import time
    global last_vacuum_info
    start_time = time.time()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    last_vacuum_info["last_run"] = now_iso
    last_vacuum_info["last_status"] = "running"
    last_vacuum_info["last_duration"] = None
    last_vacuum_info["last_error"] = None
    last_vacuum_info["last_source"] = source

    if source == "manual":
        last_vacuum_info["last_manual_run"] = now_iso
    else:
        last_vacuum_info["last_auto_run"] = now_iso

    try:
        logger.info("Starting scheduled VACUUM...")
        db_path = os.getenv("DB", "/app/data/eplus_vc.sqlite3")
        result = subprocess.run(
            ["sqlite3", db_path, "PRAGMA wal_checkpoint(TRUNCATE); VACUUM;"],
            capture_output=True,
            text=True,
            timeout=3600
        )

        duration = time.time() - start_time
        last_vacuum_info["last_duration"] = f"{duration:.1f}s"

        if result.returncode == 0:
            logger.info("VACUUM completed successfully")
            last_vacuum_info["last_status"] = "success"
            last_vacuum_info["last_error"] = None
        else:
            logger.error("VACUUM failed")
            last_vacuum_info["last_status"] = "failed"
            last_vacuum_info["last_error"] = result.stderr[:500] if result.stderr else "VACUUM failed"
    except subprocess.TimeoutExpired:
        logger.error("VACUUM timed out after 1 hour")
        last_vacuum_info["last_status"] = "timeout"
        last_vacuum_info["last_error"] = "VACUUM timed out after 1 hour"
    except Exception as e:
        logger.error(f"Error running VACUUM: {e}")
        last_vacuum_info["last_status"] = "error"
        last_vacuum_info["last_error"] = str(e)



def _get_db_stats():
    """Return (db_path, size_mb, freelist_count) for the main DB."""
    db_path = os.getenv("DB", "/app/data/eplus_vc.sqlite3")
    size_bytes = 0
    try:
        if os.path.exists(db_path):
            size_bytes = os.path.getsize(db_path)
    except OSError as exc:
        logger.warning("Unable to stat DB file %s: %s", db_path, exc)
    size_mb = size_bytes / (1024 * 1024) if size_bytes else 0.0

    freelist = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.execute("PRAGMA freelist_count;")
        row = cur.fetchone()
        if row is not None:
            freelist = row[0]
        conn.close()
    except Exception as exc:
        logger.warning("Unable to query freelist_count: %s", exc)
    return db_path, size_mb, freelist

def cleanup_old_logs(source: str = "auto"):
    """Clean up old log files, keeping only the 3 most recent of each type."""
    import glob
    import time
    
    global last_vacuum_info  # Reuse vacuum info dict for logging
    start_time = time.time()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    
    log_dir = Path("/app/logs")
    if not log_dir.exists():
        return
    
    removed_count = 0
    try:
        logger.info("Starting log cleanup...")
        
        # Patterns for main log files (including rotated versions)
        patterns = [
            "plan_builder.jsonl*",
            "refresh.log*",
            "cron_refresh.log*",
            "cron_vacuum.log*",
        ]
        
        for pattern in patterns:
            files = sorted(
                glob.glob(str(log_dir / pattern)),
                key=os.path.getmtime,
                reverse=True
            )
            # Keep newest 3, delete rest
            for old_file in files[3:]:
                try:
                    size = os.path.getsize(old_file)
                    os.remove(old_file)
                    removed_count += 1
                    logger.info(f"Cleaned up old log: {old_file} ({size / 1024 / 1024:.1f} MB)")
                except Exception as e:
                    logger.warning(f"Failed to clean up {old_file}: {e}")
        
        duration = time.time() - start_time
        logger.info(f"Log cleanup completed: removed {removed_count} old log files in {duration:.1f}s")
        
    except Exception as e:
        logger.error(f"Error during log cleanup: {e}")

def start_scheduler() -> BackgroundScheduler:
    """Initialize and start the background scheduler"""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_refresh,
        CronTrigger(hour=3, minute=0),
        id='refresh_job',
        kwargs={"source": "auto"},
    )
    scheduler.add_job(
        run_vacuum,
        CronTrigger(day_of_week='sun', hour=3, minute=10),
        id='vacuum_job',
        kwargs={"source": "auto"},
    )
    scheduler.add_job(
        cleanup_old_logs,
        CronTrigger(day_of_week='sun', hour=3, minute=30),
        id='log_cleanup_job',
        kwargs={"source": "auto"},
    )
    scheduler.start()
    logger.info("Scheduler started: refresh daily at 03:00, vacuum Sunday 03:10, log cleanup Sunday 03:30")
    return scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = start_scheduler()
    yield
    scheduler.shutdown()
    logger.info("Scheduler stopped")

# --- ChromeCapture config ---
CC_HOST = os.getenv("CC_HOST")  # defaults to resolver host if not set
CC_PORT = os.getenv("CC_PORT", "5589")
VC_RESOLVER_BASE_URL = os.getenv("VC_RESOLVER_BASE_URL", "")

# Global variable to track last refresh stats
last_refresh_info = {
    "last_run": None,
    "last_status": None,
    "last_duration": None,
    "last_error": None,
    "last_source": None,
    "last_manual_run": None,
    "last_auto_run": None,
}

# Global variable to track last VACUUM stats
last_vacuum_info = {
    "last_run": None,
    "last_status": None,
    "last_duration": None,
    "last_error": None,
    "last_source": None,
    "last_manual_run": None,
    "last_auto_run": None,
}

# Updated run_refresh function with stat tracking
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
    from config import RESOLVER_SLATE_URL as CFG_SLATE_URL
except Exception:
    CFG_SLATE_URL = ""


app = FastAPI(lifespan=lifespan)


# --- Admin hub page (static HTML) ---
RESOLVER_DIR = Path(__file__).resolve().parent
ADMIN_HTML_PATH = RESOLVER_DIR / "admin.html"


@app.get("/admin")
async def admin_index() -> HTMLResponse:
    """Simple admin hub page linking to all the useful endpoints."""
    try:
        html = ADMIN_HTML_PATH.read_text(encoding="utf-8")
    except Exception as e:
        logger.error("Error reading admin.html: %s", e)
        raise HTTPException(status_code=500, detail="Admin page template not found")
    return HTMLResponse(html)


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
            t = dt.datetime.strptime(v, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=dt.timezone.utc
            )
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


def best_feed_for_event(
    conn: sqlite3.Connection, event_id: str, preferred_feed_id: Optional[str]
) -> Optional[str]:
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





def _get_lane_event_ids(lane: str, at: Optional[str] = None):
    """Resolve the current event for a lane and break its event_id into
    play_id, airing_id, and network_id.

    We now:
      * Parse play_id and airing_id from the espn-watch payload.
      * Prefer network_id from the events table (events.network_id) using the
        full raw event_id as the key.
      * Fall back to a third colon-part in the payload if present.

    Returns a dict with keys:
      lane, at, slot, event_uid_raw, event_uid, play_id, airing_id, network_id.
    """
    at_iso = parse_at(at or None)

    lane_str = str(lane).strip()
    if lane_str.lower().startswith("eplus") and lane_str[5:].isdigit():
        num = int(lane_str[5:])
    elif lane_str.isdigit():
        num = int(lane_str)
    else:
        num = None

    normalized_lane = num if num is not None else lane_str
    candidates = [f"eplus{num}", str(num)] if num is not None else [lane_str]

    slot = None
    try:
        with db() as conn:
            for cand in candidates:
                slot = current_slot(conn, cand, at_iso)
                if slot:
                    break
    except Exception:
        slot = None

    result: Dict[str, Any] = {
        "lane": normalized_lane,
        "at": at_iso,
        "slot": slot,
        "event_uid_raw": None,
        "event_uid": None,
        "play_id": None,
        "airing_id": None,
        "network_id": None,
    }

    if not slot or slot.get("kind") != "event" or not slot.get("event_id"):
        return result

    eid_raw = slot.get("event_id") or ""
    eid = eid_raw
    if eid.startswith("espn-watch:"):
        # strip namespace prefix, keep payload after it
        eid = eid[len("espn-watch:") :]

    play_id: Optional[str] = None
    airing_id: Optional[str] = None
    network_id: Optional[str] = None

    # 1) Prefer network_id from the events table using the *raw* event_id
    if eid_raw:
        try:
            with db() as conn2:
                row = conn2.execute(
                    "SELECT network_id FROM events WHERE id = ?",
                    (eid_raw,),
                ).fetchone()
                if row is not None:
                    try:
                        nid = row["network_id"]
                    except Exception:
                        nid = row[0]
                    if nid:
                        network_id = str(nid)
        except Exception:
            # If anything goes wrong here, we just leave network_id as None
            pass

    # 2) Parse play_id / airing_id (and optionally network_id) from the payload
    if eid:
        parts = eid.split(":")
        if len(parts) >= 1 and parts[0]:
            play_id = parts[0]
        if len(parts) >= 2 and parts[1]:
            airing_id = parts[1]
        # If DB lookup failed to give us a network_id, fall back to third part
        if len(parts) >= 3 and parts[2] and not network_id:
            network_id = parts[2]

    result["event_uid_raw"] = eid_raw
    result["event_uid"] = eid
    result["play_id"] = play_id
    result["airing_id"] = airing_id
    result["network_id"] = network_id
    return result

def _build_showwatchstream_variant(ids: dict, variant: int) -> str:
    """Build one of the test showWatchStream URLs.

    Variants:
      1 -> playID only
      2 -> playID + networkId
      3 -> playID + airingId
      4 -> playID + airingId + networkId

    Raises ValueError if required IDs are missing.
    """
    play_id = ids.get("play_id")
    airing_id = ids.get("airing_id")
    network_id = ids.get("network_id")

    if not play_id:
        raise ValueError("play_id is required")

    base = "sportscenter://x-callback-url/showWatchStream"
    params = [f"playID={play_id}"]

    if variant == 1:
        # playID only
        pass
    elif variant == 2:
        # playID + networkId
        if not network_id:
            raise ValueError("network_id is required for variant 2")
        params.append(f"networkId={network_id}")
    elif variant == 3:
        # playID + airingId
        if not airing_id:
            raise ValueError("airing_id is required for variant 3")
        params.append(f"airingId={airing_id}")
    elif variant == 4:
        # playID + airingId + networkId
        if not airing_id or not network_id:
            raise ValueError("airing_id and network_id are required for variant 4")
        params.append(f"airingId={airing_id}")
        params.append(f"networkId={network_id}")
    else:
        raise ValueError(f"Unsupported variant: {variant}")

    return f"{base}?{'&'.join(params)}"
# --- Health ---
@app.get("/health")
def health():
    return {"ok": True, "ts": now_utc_iso()}


# --- Channels (DB-backed) ---
@app.get(
    "/channels_db",
    tags=["channels"],
    summary="DB-backed channel list",
    response_class=JSONResponse,
)
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
        return [
            {"id": c.get("id"), "name": (c.findtext("display-name") or "").strip()}
            for c in root.findall("channel")
        ]
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
        conn = sqlite3.connect(
            f"file:{dbp}?mode=ro", uri=True, check_same_thread=False, timeout=2.0
        )
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT CAST(id AS TEXT) AS id,
                   COALESCE(name, printf('ESPN+ EPlus %d', id)) AS name,
                   CAST(COALESCE(chno, 20009 + id) AS TEXT)     AS lcn
            FROM channel
            WHERE COALESCE(active,1)=1
            ORDER BY COALESCE(chno,id)
        """
        ).fetchall()
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
            target = best_feed_for_event(
                conn, slot["event_id"], slot.get("preferred_feed_id")
            )
            if target:
                return Response(status_code=302, headers={"Location": target})
            # event but no feed
            slate = os.getenv("VC_SLATE_URL", CFG_SLATE_URL).strip()
            if not only_live and slate:
                return Response(status_code=302, headers={"Location": slate})
            return Response(status_code=204 if only_live else 404)
    except Exception:
        return Response(
            content="Internal Server Error", status_code=500, media_type="text/plain"
        )


@app.get("/vc/{lane}/debug")
def debug_lane(lane: str, at: Optional[str] = None):
    """
    Debug view of the current slot/feed for a lane. Adds 'slate' URL in response.
    """
    info = {"lane": lane}
    try:
        at_iso = parse_at(at)
        info["now"] = at_iso
        with db() as conn:
            try:
                slot = current_slot(conn, lane, at_iso)
                info["slot"] = slot
                if slot and slot.get("event_id"):
                    info["feed"] = best_feed_for_event(
                        conn, slot["event_id"], slot.get("preferred_feed_id")
                    )
                else:
                    info["feed"] = None
            except Exception as inner:
                info["slot"] = None
                info["feed"] = None
                info["exception"] = str(inner)
                info["trace"] = traceback.format_exc().splitlines()[-4:]
        # Always include slate URL; don't let slate errors break debug
        try:
            info["slate"] = _slate_url(lane)
        except Exception:
            info["slate"] = os.getenv("VC_SLATE_URL", CFG_SLATE_URL).strip()
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
        return FileResponse(
            p, media_type="application/x-mpegURL", filename="playlist.m3u"
        )
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

            eid_short = str(eid).split(":", 1)[0] if eid else None
            deeplink_full = (
                f"sportscenter://x-callback-url/showWatchStream?playID={eid_short}"
                if eid_short
                else None
            )
            return PlainTextResponse(deeplink_full, status_code=200)
    except Exception:
        return PlainTextResponse("", status_code=204)


# --- whatson with deeplink support ---



@app.get(
    "/api/test/{lane}",
    response_class=JSONResponse,
    tags=["vc"],
    summary="Deeplink test variants for a lane",
)
def deeplink_test_all(
    lane: str,
    at: Optional[str] = None,
    format: Optional[str] = None,
):
    """Return showWatchStream deeplink variants for the current event on a lane.

    JSON (default):
      GET /api/test/4
        -> {
             "lane": 4,
             "ids": {"play_id": "...", "airing_id": "...", "network_id": "..."},
             "deeplinks": {
               "1": "sportscenter://...",
               "2": "sportscenter://...",
               "3": "...",
               "4": "..."
             }
           }

    TXT:
      GET /api/test/4?format=txt
        -> plain text list of variants, one per line:
           1: sportscenter://...
           2: sportscenter://...
           ...
    """
    info = _get_lane_event_ids(lane, at)
    ids = {
        "play_id": info.get("play_id"),
        "airing_id": info.get("airing_id"),
        "network_id": info.get("network_id"),
    }

    if not ids["play_id"]:
        return JSONResponse(
            {
                "ok": False,
                "lane": info.get("lane"),
                "at": info.get("at"),
                "error": "No event or play_id available for this lane at this time.",
            },
            status_code=404,
        )

    deeplinks: dict[str, str] = {}
    for variant in (1, 2, 3, 4):
        try:
            url = _build_showwatchstream_variant(ids, variant)
            deeplinks[str(variant)] = url
        except ValueError:
            # Skip variants we can't build due to missing IDs
            continue

    fmt = (format or "").lower()
    if fmt == "txt":
        # Return a simple text list, perfect for copy/paste into adb
        lines_out = [f"{k}: {v}" for k, v in sorted(deeplinks.items())]
        body = "\n".join(lines_out)
        return PlainTextResponse(body, status_code=200)

    return JSONResponse(
        {
            "ok": True,
            "lane": info.get("lane"),
            "at": info.get("at"),
            "slot": info.get("slot"),
            "ids": {
                "event_uid_raw": info.get("event_uid_raw"),
                "event_uid": info.get("event_uid"),
                **ids,
            },
            "deeplinks": deeplinks,
        },
        status_code=200,
    )


@app.get(
    "/api/test/{lane}/format/{variant}",
    response_class=PlainTextResponse,
    tags=["vc"],
    summary="Single deeplink test URL for a lane",
)
def deeplink_test_single(lane: str, variant: int, at: Optional[str] = None):
    """Return a single sportscenter:// showWatchStream URL as text/plain for adb testing.

    Examples:
      GET /api/test/4/format/1  -> playID only
      GET /api/test/4/format/2  -> playID + networkId
      GET /api/test/4/format/3  -> playID + airingId
      GET /api/test/4/format/4  -> playID + airingId + networkId
    """
    if variant not in (1, 2, 3, 4):
        return PlainTextResponse("", status_code=400)

    info = _get_lane_event_ids(lane, at)
    ids = {
        "play_id": info.get("play_id"),
        "airing_id": info.get("airing_id"),
        "network_id": info.get("network_id"),
    }

    if not ids["play_id"]:
        return PlainTextResponse("", status_code=204)

    try:
        url = _build_showwatchstream_variant(ids, variant)
    except ValueError:
        # Required IDs missing for this variant
        return PlainTextResponse("", status_code=204)

    return PlainTextResponse(url, status_code=200)
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
    Return current event for a lane at time 'at' (default now UTC).
    TXT modes:
      - format=txt&param=deeplink_url_full  => full playID deeplink
      - format=txt&param=deeplink_url       => short playID deeplink
      - format=txt                          => just short playID
    JSON:
      - include=deeplink (or include=1 / deeplink=1 / dynamic=1) adds "deeplink_url"
    """
    import datetime as _dt
    import os
    import sqlite3

    from fastapi.responses import JSONResponse, Response

    def _parse_at(val: str | None) -> _dt.datetime:
        if not val:
            return _dt.datetime.now(_dt.timezone.utc)
        v = val.strip().replace(" ", "T")
        try:
            if v.endswith("Z"):
                return _dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
            if "+" in v[10:] or "-" in v[10:]:
                return _dt.datetime.fromisoformat(v)
            return _dt.datetime.fromisoformat(v).replace(tzinfo=_dt.timezone.utc)
        except Exception:
            try:
                return _dt.datetime.fromisoformat(v).replace(tzinfo=_dt.timezone.utc)
            except Exception:
                return _dt.datetime.now(_dt.timezone.utc)

    when = _parse_at(at)
    when_iso = when.astimezone(_dt.timezone.utc).isoformat(timespec="seconds")

    lane_s = str(lane).strip()
    num = (
        int(lane_s[5:])
        if (lane_s.lower().startswith("eplus") and lane_s[5:].isdigit())
        else (int(lane_s) if lane_s.isdigit() else None)
    )
    normalized_lane = num if num is not None else lane_s
    candidates = [f"eplus{num}", str(num)] if num is not None else [lane_s]

    fmt = (format or "").lower()
    param_l = (param or "").lower() if isinstance(param, str) else ""
    want_txt_deeplink_full = fmt == "txt" and param_l in (
        "deeplink_url_full",
        "deeplink_full",
    )
    want_txt_deeplink_short = fmt == "txt" and param_l in (
        "deeplink_url",
        "deeplink_url_short",
    )
    want_txt_playid_short = fmt == "txt" and param_l == ""

    _want_deeplink_field = (
        (isinstance(include, str) and include.lower() in ("deeplink", "1", "true"))
        or (deeplink == 1)
        or (dynamic == 1)
    )

    db_path = os.getenv("VC_DB", "data/eplus_vc.sqlite3")
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception as e:
        if want_txt_deeplink_full or want_txt_deeplink_short or want_txt_playid_short:
            return Response(status_code=404)
        return JSONResponse(
            {"ok": False, "error": f"DB open failed: {e}"}, status_code=404
        )

    try:
        cur = conn.cursor()
        cur.execute("SELECT MAX(id) FROM plan_run")
        row = cur.fetchone()
        if not row or row[0] is None:
            if (
                want_txt_deeplink_full
                or want_txt_deeplink_short
                or want_txt_playid_short
            ):
                return Response(status_code=204)
            return JSONResponse(
                {"ok": False, "error": "No plan_run rows"}, status_code=404
            )
        plan_id = row[0]

        placeholders = ",".join("?" for _ in candidates)
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

        if not hit or not (hit[1] == "event" and hit[2]):
            if (
                want_txt_deeplink_full
                or want_txt_deeplink_short
                or want_txt_playid_short
            ):
                return Response(status_code=204)
            return JSONResponse(
                {
                    "ok": True,
                    "lane": normalized_lane,
                    "event_uid": None,
                    "at": when_iso,
                    "deeplink_url": None,
                },
                status_code=200,
            )

        _, _kind, eid = hit
        if eid.startswith("espn-watch:"):
            eid = eid[11:]

        play_short = eid.split(":", 1)[0] if eid else None
        deeplink_full = (
            f"sportscenter://x-callback-url/showWatchStream?playID={eid}"
            if eid
            else None
        )
        deeplink_short = (
            f"sportscenter://x-callback-url/showWatchStream?playID={play_short}"
            if play_short
            else None
        )

        if want_txt_deeplink_full:
            return Response(
                content=deeplink_full, media_type="text/plain", status_code=200
            )
        if want_txt_deeplink_short:
            return Response(
                content=deeplink_short, media_type="text/plain", status_code=200
            )
        if want_txt_playid_short:
            return Response(
                content=play_short, media_type="text/plain", status_code=200
            )

        return JSONResponse(
            {
                "ok": True,
                "lane": normalized_lane,
                "event_uid": eid,
                "at": when_iso,
                "deeplink_url": (deeplink_short if _want_deeplink_field else None),
            },
            status_code=200,
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


@app.get("/whatson_all", response_class=JSONResponse)
def whatson_all(
    at: Optional[str] = None,
    format: Optional[str] = None,
    include: Optional[str] = None,
    deeplink: Optional[int] = None,
    dynamic: Optional[int] = None,
):
    """
    Snapshot across all lanes. include=deeplink mirrors /whatson behavior.
    """
    import datetime as _dt
    import os
    import sqlite3

    from fastapi.responses import JSONResponse

    def _parse_at(val: str | None) -> _dt.datetime:
        if not val:
            return _dt.datetime.now(_dt.timezone.utc)
        v = val.strip().replace(" ", "T")
        try:
            if v.endswith("Z"):
                return _dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
            if "+" in v[10:] or "-" in v[10:]:
                return _dt.datetime.fromisoformat(v)
            return _dt.datetime.fromisoformat(v).replace(tzinfo=_dt.timezone.utc)
        except Exception:
            try:
                return _dt.datetime.fromisoformat(v).replace(tzinfo=_dt.timezone.utc)
            except Exception:
                return _dt.datetime.now(_dt.timezone.utc)

    when = _parse_at(at)
    when_iso = when.astimezone(_dt.timezone.utc).isoformat(timespec="seconds")

    _want_deeplink_field = (
        (isinstance(include, str) and include.lower() in ("deeplink", "1", "true"))
        or (deeplink == 1)
        or (dynamic == 1)
    )

    db_path = os.getenv("VC_DB", "data/eplus_vc.sqlite3")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = conn.cursor()
    cur.execute("SELECT MAX(id) FROM plan_run")
    row = cur.fetchone()
    if not row or row[0] is None:
        return JSONResponse({"ok": True, "items": [], "at": when_iso})

    plan_id = row[0]
    cur.execute(
        """
        SELECT lane, channel_id, kind, event_id, start_utc, end_utc
        FROM plan_slot
        WHERE plan_id = ?
          AND start_utc <= ?
          AND end_utc > ?
        ORDER BY lane ASC
        """,
        (plan_id, when_iso, when_iso),
    )
    items = []
    for lane_i, channel_id, kind, event_id, _s, _e in cur.fetchall():
        eid = event_id
        if eid and eid.startswith("espn-watch:"):
            eid = eid[11:]
        play_short = eid.split(":", 1)[0] if eid else None

        deeplink_short = (
            f"sportscenter://x-callback-url/showWatchStream?playID={play_short}"
            if play_short
            else None
        )
        items.append(
            {
                "lane": lane_i,
                "channel_id": channel_id,
                "kind": kind,
                "event_uid": eid,
                "deeplink_url": (deeplink_short if _want_deeplink_field else None),
            }
        )

    try:
        conn.close()
    except Exception:
        pass

    return JSONResponse({"ok": True, "at": when_iso, "items": items})


@app.get("/filters", tags=["admin"], summary="Show available filter options")
def get_filters_info():
    """
    Display available filter options from current database.
    Shows networks, sports, leagues, event types, and packages.
    Helps users configure their filters.ini file.
    """

    dbp = os.environ.get("VC_DB", "data/eplus_vc.sqlite3")

    try:
        conn = sqlite3.connect(
            f"file:{dbp}?mode=ro", uri=True, check_same_thread=False, timeout=2.0
        )
        cursor = conn.cursor()

        # Get all filter options
        options = {}

        # Networks
        cursor.execute(
            """
            SELECT network, COUNT(*) as cnt
            FROM events
            WHERE network IS NOT NULL AND network != ''
            GROUP BY network
            ORDER BY cnt DESC, network
        """
        )
        options["networks"] = cursor.fetchall()

        # Sports
        cursor.execute(
            """
            SELECT sport, COUNT(*) as cnt
            FROM events
            WHERE sport IS NOT NULL AND sport != ''
            GROUP BY sport
            ORDER BY cnt DESC, sport
        """
        )
        options["sports"] = cursor.fetchall()

        # Leagues
        cursor.execute(
            """
            SELECT league_name, COUNT(*) as cnt
            FROM events
            WHERE league_name IS NOT NULL AND league_name != ''
            GROUP BY league_name
            ORDER BY cnt DESC, league_name
        """
        )
        options["leagues"] = cursor.fetchall()

        # Event types
        cursor.execute(
            """
            SELECT event_type, COUNT(*) as cnt
            FROM events
            WHERE event_type IS NOT NULL AND event_type != ''
            GROUP BY event_type
            ORDER BY cnt DESC
        """
        )
        options["event_types"] = cursor.fetchall()

        # Packages
        cursor.execute(
            """
            SELECT packages, COUNT(*) as cnt
            FROM events
            WHERE packages IS NOT NULL AND packages != '' AND packages != '[]'
            GROUP BY packages
            ORDER BY cnt DESC
            LIMIT 20
        """
        )
        options["packages"] = cursor.fetchall()

        conn.close()

        # Format as HTML
        html = """
        <html>
        <head>
            <title>ESPN4CC4C - Available Filters</title>
            <meta charset="UTF-8">
            <style>
                body {
                    font-family: 'Consolas', 'Monaco', monospace;
                    background: #1e1e1e;
                    color: #d4d4d4;
                    padding: 20px;
                    max-width: 1200px;
                    margin: 0 auto;
                }
                h1 { color: #4fc3f7; border-bottom: 2px solid #4fc3f7; padding-bottom: 10px; }
                h2 { color: #81c784; margin-top: 30px; }
                .section {
                    background: #252526;
                    padding: 15px;
                    margin: 15px 0;
                    border-radius: 4px;
                }
                .item {
                    padding: 3px 0;
                    font-family: 'Courier New', monospace;
                    font-size: 14px;
                }
                .count { color: #ffb74d; font-weight: bold; }
                .tip {
                    background: #263238;
                    padding: 20px;
                    margin: 30px 0;
                    border-left: 4px solid #4fc3f7;
                    border-radius: 4px;
                }
                pre {
                    background: #1e1e1e;
                    padding: 15px;
                    overflow-x: auto;
                    border-radius: 4px;
                    border: 1px solid #333;
                }
                code { color: #ce9178; }
                .intro { background: #252526; padding: 15px; margin: 20px 0; border-radius: 4px; }
                a { color: #4fc3f7; text-decoration: none; }
                a:hover { text-decoration: underline; }
            </style>
        </head>
        <body>
            <h1>📺 ESPN4CC4C - Available Filter Options</h1>
            <div class='intro'>
                <p>These values are from your current database. Use them in your <code>filters.ini</code> file.</p>
                <p>JSON version: <a href="/filters/json">/filters/json</a></p>
            </div>
        """

        # Networks
        html += "<h2>📺 Networks</h2><div class='section'>"
        for network, count in options["networks"]:
            html += f"<div class='item'>{network:<40} <span class='count'>({count:>4} events)</span></div>"
        html += "</div>"

        # Sports
        html += "<h2>⚽ Sports</h2><div class='section'>"
        for sport, count in options["sports"]:
            html += f"<div class='item'>{sport:<40} <span class='count'>({count:>4} events)</span></div>"
        html += "</div>"

        # Leagues
        html += "<h2>🏆 Leagues</h2><div class='section'>"
        for league, count in options["leagues"]:
            html += f"<div class='item'>{league:<40} <span class='count'>({count:>4} events)</span></div>"
        html += "</div>"

        # Event Types
        html += "<h2>📡 Event Types</h2><div class='section'>"
        for etype, count in options["event_types"]:
            html += f"<div class='item'>{etype:<40} <span class='count'>({count:>4} events)</span></div>"
        html += "</div>"

        # Packages
        html += "<h2>💰 Packages</h2><div class='section'>"
        for pkg, count in options["packages"]:
            pkg_clean = pkg.replace('["', "").replace('"]', "").replace('", "', ", ")
            html += f"<div class='item'>{pkg_clean:<50} <span class='count'>({count:>4} events)</span></div>"
        html += "</div>"

        # Example usage
        html += """
        <div class='tip'>
            <h3>💡 Example filters.ini Configuration</h3>
            <pre>
[filters]
# Professional sports only
enabled_leagues = NFL,NBA,NHL

# No replays
exclude_event_types = OVER

# Cable TV only (no ESPN+)
exclude_networks = ESPN+
require_espn_plus = false

# Remove studio shows (no deeplinks)
exclude_no_sport = true

# Football and Basketball only
enabled_sports = Football,Basketball
            </pre>
            <p>Place <code>filters.ini</code> in your project root and run <code>update_schedule.sh</code></p>
        </div>
        """

        html += "</body></html>"

        return HTMLResponse(content=html)

    except Exception as e:
        return JSONResponse({"error": str(e), "traceback": traceback.format_exc()})


@app.get("/filters/json", tags=["admin"], summary="Get filter options as JSON")
def get_filters_json():
    """Return filter options as JSON for programmatic access"""

    dbp = os.environ.get("VC_DB", "data/eplus_vc.sqlite3")

    try:
        conn = sqlite3.connect(
            f"file:{dbp}?mode=ro", uri=True, check_same_thread=False, timeout=2.0
        )
        cursor = conn.cursor()

        # Get all filter options
        def get_counts(field):
            cursor.execute(
                f"""
                SELECT {field}, COUNT(*) as cnt
                FROM events
                WHERE {field} IS NOT NULL AND {field} != ''
                GROUP BY {field}
                ORDER BY cnt DESC
            """
            )
            return [{"name": row[0], "count": row[1]} for row in cursor.fetchall()]

        result = {
            "networks": get_counts("network"),
            "sports": get_counts("sport"),
            "leagues": get_counts("league_name"),
            "event_types": get_counts("event_type"),
        }

        # Packages (special handling for JSON field)
        cursor.execute(
            """
            SELECT packages, COUNT(*) as cnt
            FROM events
            WHERE packages IS NOT NULL AND packages != '' AND packages != '[]'
            GROUP BY packages
            ORDER BY cnt DESC
            LIMIT 20
        """
        )
        result["packages"] = [
            {
                "name": row[0]
                .replace('["', "")
                .replace('"]', "")
                .replace('", "', ", "),
                "count": row[1],
            }
            for row in cursor.fetchall()
        ]

        # Total events
        cursor.execute("SELECT COUNT(*) FROM events")
        result["total_events"] = cursor.fetchone()[0]

        conn.close()

        return JSONResponse(result)

    except Exception as e:
        return JSONResponse({"error": str(e), "traceback": traceback.format_exc()})


@app.get(
    "/channels", tags=["channels"], summary="DB-backed channel list (authoritative)"
)
def channels():
    """
    Authoritative channel list from the DB only.
    Uses table: channel(id, name, chno, active).
    If chno is null/invalid, synthesize LCN = 20009 + id.
    """
    import sqlite3 as _sqlite3  # local alias to avoid shadowing

    dbp = os.environ.get("VC_DB", "data/eplus_vc.sqlite3")
    con = _sqlite3.connect(
        f"file:{dbp}?mode=ro", uri=True, check_same_thread=False, timeout=2.0
    )
    con.row_factory = _sqlite3.Row
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
            name = (r["name"] or f"ESPN+ EPlus {ch_id}").strip()
            chno = r["chno"]
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
@app.get(
    "/setupfilters",
    response_class=HTMLResponse,
    tags=["admin"],
    summary="Interactive helper to build FILTER_* environment snippets",
)
def setup_filters_helper():
    """Interactive helper that uses /filters/json to build FILTER_* env snippets.

    This is a read-only guide: it does NOT change your running config. It just
    shows copy/paste examples for docker-compose or Portainer.
    """
    html = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>ESPN4CC4C - Filter Setup Helper</title>
  <style>
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #111827;
      color: #e5e7eb;
      padding: 24px;
      max-width: 960px;
      margin: 0 auto;
    }
    h1 {
      color: #38bdf8;
      border-bottom: 2px solid #1f2937;
      padding-bottom: 8px;
      margin-bottom: 16px;
    }
    h2 {
      color: #a5b4fc;
      margin-top: 24px;
      margin-bottom: 8px;
    }
    .card {
      background: #020617;
      border: 1px solid #1f2937;
      border-radius: 8px;
      padding: 16px 20px;
      margin-bottom: 16px;
    }
    .small {
      font-size: 12px;
      color: #9ca3af;
    }
    .section-title {
      font-weight: 600;
      margin-bottom: 8px;
    }
    .flex {
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
    }
    .flex-col {
      flex: 1 1 260px;
    }
    .option-list {
      max-height: 260px;
      overflow-y: auto;
      border: 1px solid #1f2937;
      border-radius: 6px;
      padding: 8px 10px;
      background: #020617;
      font-size: 13px;
    }
    .option-item {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 4px;
    }
    .option-item label {
      cursor: pointer;
    }
    a {
      color: #38bdf8;
      text-decoration: none;
    }
    a:hover {
      text-decoration: underline;
    }
    textarea {
      width: 100%;
      min-height: 220px;
      background: #020617;
      color: #e5e7eb;
      border-radius: 6px;
      border: 1px solid #374151;
      padding: 12px;
      font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      font-size: 13px;
      resize: vertical;
      box-sizing: border-box;
    }
    .actions {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 8px;
    }
    .copy-btn {
      background: #22c55e;
      border: none;
      color: #022c22;
      font-weight: 600;
      padding: 6px 12px;
      border-radius: 999px;
      cursor: pointer;
    }
    .copy-btn:hover {
      background: #16a34a;
    }
    .status {
      font-size: 12px;
      color: #a5b4fc;
    }
    .profile-buttons {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 8px;
    }
    .profile-buttons button {
      border-radius: 999px;
      border: 1px solid #4b5563;
      background: #020617;
      color: #e5e7eb;
      font-size: 12px;
      padding: 4px 10px;
      cursor: pointer;
    }
    .profile-buttons button:hover {
      background: #111827;
    }
    .toggle-row {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      font-size: 12px;
      margin-top: 6px;
    }
    .toggle-row label {
      cursor: pointer;
    }
  </style>
</head>
<body>
  <h1>ESPN4CC4C - Filter Setup Helper</h1>

  <div class="card">
    <p class="small">
      This page helps you generate <code>FILTER_*</code> environment variables for your
      <code>docker-compose.yml</code> or Portainer stack.
      <strong>Click the networks/leagues/sports you do NOT want in your guide</strong> and
      we will build the appropriate <code>FILTER_EXCLUDE_*</code> lines for you.
    </p>
    <p class="small">
      It does not change anything automatically. After you update your stack and restart
      the container, open <code>/out/filteraudit.html</code> to confirm the filters took effect.
    </p>
  </div>

  <div class="card">
    <div class="section-title">Quick profiles</div>
    <p class="small">
      These are common starting points. They simply toggle the checkboxes below:
      <br>- <strong>No filtering</strong>: show everything ESPN4CC4C finds.
      <br>- <strong>Clean but broad</strong>: hide NCAAW / women's college, Spanish feeds, and replays.
      <br>- <strong>ESPN+ + ESPN3 (no linear dupes)</strong>: keep ESPN+ and ESPN3 while excluding the main linear ESPN channels (ESPN, ESPN2, ESPNU, ESPN News, ESPN Deportes, SEC, ACC, etc.).
    </p>
    <div class="profile-buttons">
      <button type="button" onclick="applyProfile('none')">No filtering</button>
      <button type="button" onclick="applyProfile('clean')">Clean but broad</button>
      <button type="button" onclick="applyProfile('nodupes')">ESPN+ + ESPN3 (no linear dupes)</button>
    </div>
  </div>

  <h2>1. Choose what to exclude from your guide</h2>
  <div class="card">
    <p class="small">
      Check the items you <strong>do not want</strong>. They will be turned into
      <code>FILTER_EXCLUDE_*</code> values.
    </p>
    <div class="flex">
      <div class="flex-col">
        <div class="section-title">Networks</div>
        <div id="networksContainer" class="option-list small">
          <div class="small">Loading networks...</div>
        </div>
      </div>
      <div class="flex-col">
        <div class="section-title">Leagues</div>
        <div id="leaguesContainer" class="option-list small">
          <div class="small">Loading leagues...</div>
        </div>
      </div>
      <div class="flex-col">
        <div class="section-title">Sports</div>
        <div id="sportsContainer" class="option-list small">
          <div class="small">Loading sports...</div>
        </div>
      </div>
    </div>

    <div class="flex" style="margin-top: 16px;">
      <div class="flex-col">
        <div class="section-title">Event types (advanced)</div>
        <div id="eventTypesContainer" class="option-list small">
          <div class="small">Loading event types...</div>
        </div>
        <p class="small" style="margin-top:6px;">
          Most users can ignore event types. Replays are usually better controlled via
          <code>FILTER_EXCLUDE_REAIR=true</code> below.
        </p>
      </div>

      <div class="flex-col">
        <div class="section-title">Other options</div>
        <div class="toggle-row">
          <label><input type="checkbox" id="hideEs"> Hide Spanish (FILTER_EXCLUDE_LANGUAGES=es)</label>
          <label><input type="checkbox" id="hideReair" checked> Hide re-airs (FILTER_EXCLUDE_REAIR=true)</label>
          <label><input type="checkbox" id="caseInsensitive" checked> Case-insensitive matching</label>
          <label><input type="checkbox" id="partialLeagueMatch" checked> Partial league match (NCAAW / NCAA Women's)</label>
        </div>
      </div>
    </div>
  </div>

  <h2>2. Copy the suggested environment block</h2>
  <div class="card">
    <p class="small">
      <strong>For docker-compose.yml:</strong> Paste this under the <code>environment:</code> section for the <code>espn4cc4c</code> service.
    </p>
    <textarea id="configPreview" spellcheck="false"></textarea>
    <div class="actions">
      <button class="copy-btn" type="button" onclick="copySnippet()">Copy to clipboard</button>
      <span class="status" id="copyStatus"></span>
    </div>
  </div>

  <div class="card">
    <p class="small">
      <strong>For Portainer Stack Editor:</strong> Paste this in the <code>Environment variables</code> section (advanced mode).
    </p>
    <textarea id="portainerPreview" spellcheck="false"></textarea>
    <div class="actions">
      <button class="copy-btn" type="button" onclick="copyPortainerSnippet()">Copy to clipboard</button>
      <span class="status" id="portainerCopyStatus"></span>
    </div>
    <p class="small" style="margin-top:10px;">
      After updating your stack and restarting the container, open
      <code>/out/filteraudit.html</code> to verify the leagues, languages, and re-airs
      match your expectations.
    </p>
  </div>

  <h2>3. Helpful links</h2>
  <div class="card">
    <p class="small">
      • Filter options from your current DB: <a href="/filters" target="_blank">/filters</a><br>
      • JSON filter options: <a href="/filters/json" target="_blank">/filters/json</a><br>
      • Filter audit report: <a href="/out/filteraudit.html" target="_blank">/out/filteraudit.html</a><br>
    </p>
  </div>

  <script>
    var filterState = { data: null };

    function renderOptions(list, containerId, kind) {
      var container = document.getElementById(containerId);
      if (!container) return;
      container.innerHTML = "";
      if (!list || list.length === 0) {
        container.innerHTML = '<div class="small">No data found in current DB.</div>';
        return;
      }
      for (var i = 0; i < list.length; i++) {
        var item = list[i] || {};
        var name = item.name || "";
        var count = item.count || 0;
        // Only escape for display in HTML content, not for data-name attribute
        var escapedNameForDisplay = String(name).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        var escapedNameForAttr = String(name).replace(/"/g, '&quot;');

        var wrap = document.createElement("div");
        wrap.className = "option-item";
        var id = kind + "_" + i;

        var html = ''
          + '<label>'
          + '<input type="checkbox"'
          + ' class="filter-checkbox"'
          + ' data-kind="' + kind + '"'
          + ' data-name="' + escapedNameForAttr + '"'
          + ' id="' + id + '">'
          + escapedNameForDisplay + ' <span class="small">(' + count + ' events)</span>'
          + '</label>';

        wrap.innerHTML = html;
        container.appendChild(wrap);
      }
    }

    function buildSnippet() {
      var checked = Array.prototype.slice.call(
        document.querySelectorAll(".filter-checkbox:checked")
      );
      var byKind = {
        network: [],
        league: [],
        sport: [],
        event_type: []
      };
      checked.forEach(function(input) {
        var kind = input.getAttribute("data-kind");
        var name = input.getAttribute("data-name");
        // Unescape &quot; back to " for the actual environment variable value
        if (name) {
          name = name.replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
        }
        if (kind && name && byKind[kind]) {
          byKind[kind].push(name);
        }
      });

      var hideEs = document.getElementById("hideEs").checked;
      var hideReair = document.getElementById("hideReair").checked;
      var caseInsensitive = document.getElementById("caseInsensitive").checked;
      var partialLeagueMatch = document.getElementById("partialLeagueMatch").checked;

      // Docker-compose format
      var lines = [];
      lines.push("environment:");
      lines.push("  - FILTER_EXCLUDE_NETWORKS=" + (byKind.network.join(",") || ""));
      lines.push("  - FILTER_EXCLUDE_LEAGUES=" + (byKind.league.join(",") || ""));
      lines.push("  - FILTER_EXCLUDE_SPORTS=" + (byKind.sport.join(",") || ""));
      lines.push("  - FILTER_EXCLUDE_EVENT_TYPES=" + (byKind.event_type.join(",") || ""));
      lines.push("  - FILTER_EXCLUDE_LANGUAGES=" + (hideEs ? "es" : ""));
      lines.push("  - FILTER_EXCLUDE_REAIR=" + (hideReair ? "true" : "false"));
      lines.push("  - FILTER_CASE_INSENSITIVE=" + (caseInsensitive ? "true" : "false"));
      lines.push("  - FILTER_PARTIAL_LEAGUE_MATCH=" + (partialLeagueMatch ? "true" : "false"));
      lines.push("  - FILTER_REQUIRE_ESPN_PLUS=false");

      var area = document.getElementById("configPreview");
      if (area) {
        area.value = lines.join('\\n');
      }

      // Portainer format (no "environment:" header, no "  - " prefix)
      var portainerLines = [];
      portainerLines.push("FILTER_EXCLUDE_NETWORKS=" + (byKind.network.join(",") || ""));
      portainerLines.push("FILTER_EXCLUDE_LEAGUES=" + (byKind.league.join(",") || ""));
      portainerLines.push("FILTER_EXCLUDE_SPORTS=" + (byKind.sport.join(",") || ""));
      portainerLines.push("FILTER_EXCLUDE_EVENT_TYPES=" + (byKind.event_type.join(",") || ""));
      portainerLines.push("FILTER_EXCLUDE_LANGUAGES=" + (hideEs ? "es" : ""));
      portainerLines.push("FILTER_EXCLUDE_REAIR=" + (hideReair ? "true" : "false"));
      portainerLines.push("FILTER_CASE_INSENSITIVE=" + (caseInsensitive ? "true" : "false"));
      portainerLines.push("FILTER_PARTIAL_LEAGUE_MATCH=" + (partialLeagueMatch ? "true" : "false"));
      portainerLines.push("FILTER_REQUIRE_ESPN_PLUS=false");

      var portainerArea = document.getElementById("portainerPreview");
      if (portainerArea) {
        portainerArea.value = portainerLines.join('\\n');
      }
    }

    function copySnippet() {
      var area = document.getElementById("configPreview");
      if (!area) return;
      area.focus();
      area.select();
      try {
        var ok = document.execCommand("copy");
        var status = document.getElementById("copyStatus");
        if (status) {
          status.textContent = ok ? "Copied to clipboard" : "Unable to copy";
          setTimeout(function() { status.textContent = ""; }, 1500);
        }
      } catch (e) {
        console.error(e);
      }
    }

    function copyPortainerSnippet() {
      var area = document.getElementById("portainerPreview");
      if (!area) return;
      area.focus();
      area.select();
      try {
        var ok = document.execCommand("copy");
        var status = document.getElementById("portainerCopyStatus");
        if (status) {
          status.textContent = ok ? "Copied to clipboard" : "Unable to copy";
          setTimeout(function() { status.textContent = ""; }, 1500);
        }
      } catch (e) {
        console.error(e);
      }
    }

    function clearAllSelections() {
      var boxes = document.querySelectorAll(".filter-checkbox");
      Array.prototype.forEach.call(boxes, function(cb) {
        cb.checked = false;
      });
      document.getElementById("hideEs").checked = false;
      document.getElementById("hideReair").checked = true;
      document.getElementById("caseInsensitive").checked = true;
      document.getElementById("partialLeagueMatch").checked = true;
    }

    function setCheckedByKindAndNames(kind, names) {
      var set = {};
      for (var i = 0; i < names.length; i++) {
        set[names[i]] = true;
      }
      var boxes = document.querySelectorAll('.filter-checkbox[data-kind="' + kind + '"]');
      Array.prototype.forEach.call(boxes, function(cb) {
        var name = cb.getAttribute("data-name");
        cb.checked = !!set[name];
      });
    }

    function applyProfile(profile) {
      if (!filterState.data) {
        return;
      }
      clearAllSelections();

      if (profile === "none") {
        // Show everything, only keep matching helpers on
      } else if (profile === "clean") {
        // Hide NCAAW, NCAA Women's Volleyball, Spanish, and re-airs
        setCheckedByKindAndNames("league", ["NCAAW", "NCAA Women's Volleyball"]);
        document.getElementById("hideEs").checked = true;
        document.getElementById("hideReair").checked = true;
      } else if (profile === "nodupes") {
        // ESPN+ + ESPN3 (no linear dupes)
        setCheckedByKindAndNames("network", [
          "ESPN",
          "ESPN2",
          "ESPNU",
          "ESPNews",
          "ESPN Deportes",
          "SEC Network",
          "SEC Network +",
          "ACCN",
          "ACCNX",
          "@ESPN",
          "ESPN Unlimited"
        ]);
        // Optionally also filter women's / Spanish / re-airs
        setCheckedByKindAndNames("league", ["NCAAW", "NCAA Women's Volleyball"]);
        document.getElementById("hideEs").checked = true;
        document.getElementById("hideReair").checked = true;
      }

      buildSnippet();
    }

    function initializeFromJson(data) {
      filterState.data = data || {};
      renderOptions(data.networks || [], "networksContainer", "network");
      renderOptions(data.leagues || [], "leaguesContainer", "league");
      renderOptions(data.sports || [], "sportsContainer", "sport");
      renderOptions(data.event_types || [], "eventTypesContainer", "event_type");

      var boxes = document.querySelectorAll(".filter-checkbox");
      Array.prototype.forEach.call(boxes, function(cb) {
        cb.addEventListener("change", buildSnippet);
      });

      document.getElementById("hideEs").addEventListener("change", buildSnippet);
      document.getElementById("hideReair").addEventListener("change", buildSnippet);
      document.getElementById("caseInsensitive").addEventListener("change", buildSnippet);
      document.getElementById("partialLeagueMatch").addEventListener("change", buildSnippet);

      buildSnippet();
    }

    document.addEventListener("DOMContentLoaded", function () {
      fetch("/filters/json")
        .then(function(r) { return r.json(); })
        .then(function(data) {
          initializeFromJson(data);
        })
        .catch(function(err) {
          console.error("Failed to load /filters/json", err);
          var containers = ["networksContainer", "leaguesContainer", "sportsContainer", "eventTypesContainer"];
          for (var i = 0; i < containers.length; i++) {
            var el = document.getElementById(containers[i]);
            if (el) {
              el.innerHTML = '<div class="small">Error loading /filters/json - check logs.</div>';
            }
          }
          
          // Still set up event listeners for the checkboxes
          document.getElementById("hideEs").addEventListener("change", buildSnippet);
          document.getElementById("hideReair").addEventListener("change", buildSnippet);
          document.getElementById("caseInsensitive").addEventListener("change", buildSnippet);
          document.getElementById("partialLeagueMatch").addEventListener("change", buildSnippet);
          
          // Build boilerplate snippet so users at least see the FILTER_* keys
          buildSnippet();
        });
    });
  </script>
</body>
</html>"""
    return HTMLResponse(html)


# ============================================================================
# ADMIN DASHBOARD ROUTES
# ============================================================================


@app.get("/admin/refresh")
async def admin_dashboard():
    """Admin dashboard with refresh + vacuum stats and manual controls."""
    # Normalize refresh status
    status_raw = last_refresh_info.get("last_status") or "unknown"
    has_run = bool(last_refresh_info.get("last_run"))

    if not has_run:
        status_label = "NEVER RUN"
    else:
        status_label = status_raw.upper()

    if status_raw in {"success", "failed", "running", "timeout", "error"}:
        status_class = status_raw
    else:
        status_class = "unknown"

    raw_last_run = last_refresh_info.get("last_run")
    if raw_last_run:
        last_run_text = f"{raw_last_run} (UTC)"
    else:
        last_run_text = "Never"

    last_duration_text = last_refresh_info.get("last_duration") or "N/A"
    last_error = last_refresh_info.get("last_error")

    raw_manual = last_refresh_info.get("last_manual_run")
    if raw_manual:
        last_manual_text = f"{raw_manual} (UTC)"
    else:
        last_manual_text = "Never"

    raw_auto = last_refresh_info.get("last_auto_run")
    if raw_auto:
        last_auto_text = f"{raw_auto} (UTC)"
    else:
        last_auto_text = "Never"

    # VACUUM status
    vac_status_raw = last_vacuum_info.get("last_status") or "unknown"
    vac_has_run = bool(last_vacuum_info.get("last_run"))

    if not vac_has_run:
        vac_status_label = "NEVER RUN"
    else:
        vac_status_label = vac_status_raw.upper()

    if vac_status_raw in {"success", "failed", "running", "timeout", "error"}:
        vac_status_class = vac_status_raw
    else:
        vac_status_class = "unknown"

    raw_vac_last = last_vacuum_info.get("last_run")
    if raw_vac_last:
        vac_last_run_text = f"{raw_vac_last} (UTC)"
    else:
        vac_last_run_text = "Never"

    vac_last_duration_text = last_vacuum_info.get("last_duration") or "N/A"
    vac_last_error = last_vacuum_info.get("last_error")

    raw_vac_manual = last_vacuum_info.get("last_manual_run")
    if raw_vac_manual:
        vac_last_manual_text = f"{raw_vac_manual} (UTC)"
    else:
        vac_last_manual_text = "Never"

    raw_vac_auto = last_vacuum_info.get("last_auto_run")
    if raw_vac_auto:
        vac_last_auto_text = f"{raw_vac_auto} (UTC)"
    else:
        vac_last_auto_text = "Never"

    # DB stats
    db_path, db_size_mb, freelist = _get_db_stats()
    db_size_text = f"{db_size_mb:.2f} MiB"
    freelist_text = "Unknown" if freelist is None else str(freelist)

    last_error_html = ""
    if last_error:
        last_error_html = f'<div class="error-box">{last_error}</div>'

    vac_last_error_html = ""
    if vac_last_error:
        vac_last_error_html = f'<div class="error-box">{vac_last_error}</div>'

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>ESPN4CC4C Admin - Database Maintenance</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0f0f0f;
            color: #e0e0e0;
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        h1 {{
            color: #fff;
            margin-bottom: 10px;
        }}
        .subtitle {{
            color: #888;
            margin-bottom: 30px;
        }}
        .card {{
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
        }}
        .stat-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .stat {{
            background: #252525;
            padding: 15px;
            border-radius: 6px;
            border-left: 3px solid #666;
        }}
        .stat.success {{ border-left-color: #4caf50; }}
        .stat.failed {{ border-left-color: #f44336; }}
        .stat.running {{ border-left-color: #2196f3; }}
        .stat.timeout {{ border-left-color: #ff9800; }}
        .stat.error {{ border-left-color: #e91e63; }}
        .stat.unknown {{ border-left-color: #666; }}
        .stat-label {{
            font-size: 0.85em;
            color: #888;
            margin-bottom: 5px;
        }}
        .stat-value {{
            font-size: 1.3em;
            font-weight: 600;
            color: #fff;
        }}
        .status-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .status-success {{ background: #4caf50; color: #fff; }}
        .status-failed {{ background: #f44336; color: #fff; }}
        .status-running {{ background: #2196f3; color: #fff; }}
        .status-timeout {{ background: #ff9800; color: #000; }}
        .status-error {{ background: #e91e63; color: #fff; }}
        .status-unknown {{ background: #666; color: #fff; }}
        .refresh-btn {{
            background: #2196f3;
            color: white;
            border: none;
            padding: 12px 30px;
            font-size: 16px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
        }}
        .refresh-btn:hover {{
            background: #1976d2;
        }}
        .refresh-btn:disabled {{
            background: #555;
            cursor: not-allowed;
        }}
        .schedule-list {{
            list-style: none;
        }}
        .schedule-item {{
            padding: 10px;
            background: #252525;
            margin-bottom: 8px;
            border-radius: 4px;
            display: flex;
            justify-content: space-between;
        }}
        .error-box {{
            background: #2a1515;
            border: 1px solid #f44336;
            border-radius: 6px;
            padding: 15px;
            color: #ffcdd2;
            font-family: monospace;
            font-size: 0.9em;
            white-space: pre-wrap;
            word-break: break-word;
        }}
        #status-message {{
            padding: 12px;
            border-radius: 6px;
            margin-top: 15px;
            display: none;
        }}
        #status-message.success {{
            background: #1b5e20;
            border: 1px solid #4caf50;
            color: #c8e6c9;
        }}
        #status-message.error {{
            background: #b71c1c;
            border: 1px solid #f44336;
            color: #ffcdd2;
        }}
        .timestamp {{
            color: #888;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔄 Database Maintenance</h1>
        <p class="subtitle">Monitor and control ESPN4CC4C database refresh and VACUUM</p>

        <div class="card">
            <h2 style="margin-bottom: 15px;">Last Refresh Status</h2>
            <div class="stat-grid">
                <div class="stat {status_class}">
                    <div class="stat-label">Status</div>
                    <div class="stat-value">
                        <span class="status-badge status-{status_class}">
                            {status_label}
                        </span>
                    </div>
                </div>
                <div class="stat">
                    <div class="stat-label">Last Run</div>
                    <div class="stat-value timestamp">
                        {last_run_text}
                    </div>
                </div>
                <div class="stat">
                    <div class="stat-label">Duration</div>
                    <div class="stat-value">
                        {last_duration_text}
                    </div>
                </div>
            </div>

            <div class="stat-grid">
                <div class="stat">
                    <div class="stat-label">Last Manual Refresh</div>
                    <div class="stat-value timestamp">
                        {last_manual_text}
                    </div>
                </div>
                <div class="stat">
                    <div class="stat-label">Last Scheduled Refresh</div>
                    <div class="stat-value timestamp">
                        {last_auto_text}
                    </div>
                </div>
            </div>

            {last_error_html}
            <div style="margin-top: 20px; display: flex; flex-wrap: wrap; gap: 12px; align-items: center;">
                <button class="refresh-btn" onclick="triggerRefresh()" id="refresh-btn" style="max-width: 260px;">
                    🔄 Trigger Refresh Now
                </button>
                <p style="color: #888; font-size: 0.9em; margin: 0; max-width: 420px;">
                    Trigger a database refresh immediately. This will fetch the latest events from ESPN+ and update your channels.
                </p>
            </div>
            <div id="status-message"></div>
        </div>

        <div class="card">
            <h2 style="margin-bottom: 15px;">Scheduled Runs</h2>
            <ul class="schedule-list">
                <li class="schedule-item">
                    <span>📅 Database Refresh</span>
                    <span class="timestamp">03:00 daily</span>
                </li>
                <li class="schedule-item">
                    <span>🗄️ Database VACUUM</span>
                    <span class="timestamp">Sunday at 03:10</span>
                </li>
            </ul>
        </div>

        <div class="card">
            <h2 style="margin-bottom: 15px;">Database Health & VACUUM</h2>
            <div class="stat-grid">
                <div class="stat {vac_status_class}">
                    <div class="stat-label">Last VACUUM Status</div>
                    <div class="stat-value">
                        <span class="status-badge status-{vac_status_class}">
                            {vac_status_label}
                        </span>
                    </div>
                </div>
                <div class="stat">
                    <div class="stat-label">Last VACUUM Run</div>
                    <div class="stat-value timestamp">
                        {vac_last_run_text}
                    </div>
                </div>
                <div class="stat">
                    <div class="stat-label">VACUUM Duration</div>
                    <div class="stat-value">
                        {vac_last_duration_text}
                    </div>
                </div>
            </div>

            <div class="stat-grid">
                <div class="stat">
                    <div class="stat-label">Last Manual VACUUM</div>
                    <div class="stat-value timestamp">
                        {vac_last_manual_text}
                    </div>
                </div>
                <div class="stat">
                    <div class="stat-label">Last Scheduled VACUUM</div>
                    <div class="stat-value timestamp">
                        {vac_last_auto_text}
                    </div>
                </div>
            </div>

            <div class="stat-grid">
                <div class="stat">
                    <div class="stat-label">Database Path</div>
                    <div class="stat-value" style="font-size: 0.9em; word-break: break-all;">
                        {db_path}
                    </div>
                </div>
                <div class="stat">
                    <div class="stat-label">Database Size</div>
                    <div class="stat-value">
                        {db_size_text}
                    </div>
                </div>
                <div class="stat">
                    <div class="stat-label">Freelist Pages</div>
                    <div class="stat-value">
                        {freelist_text}
                    </div>
                </div>
            </div>

            {vac_last_error_html}

            <div style="margin-top: 20px;">
                <button class="refresh-btn" onclick="triggerVacuum()" id="vacuum-btn" style="width: 100%;">
                    🗄️ Run VACUUM Now
                </button>
            </div>
        </div>
    </div>

    <script>
        async function triggerRefresh() {{
            const btn = document.getElementById('refresh-btn');
            const status = document.getElementById('status-message');

            btn.disabled = true;
            btn.textContent = '⏳ Triggering refresh...';
            status.style.display = 'none';

            try {{
                const response = await fetch('/admin/refresh/trigger', {{
                    method: 'POST'
                }});

                const data = await response.json();

                if (response.ok) {{
                    status.className = 'success';
                    status.textContent = '✓ ' + data.message;
                    status.style.display = 'block';

                    setTimeout(() => {{
                        window.location.reload();
                    }}, 2000);
                }} else {{
                    throw new Error(data.message || 'Unknown error');
                }}
            }} catch (error) {{
                status.className = 'error';
                status.textContent = '✗ Error: ' + error.message;
                status.style.display = 'block';
                btn.disabled = false;
                btn.textContent = '🔄 Trigger Refresh Now';
            }}
        }}

        async function triggerVacuum() {{
            const btn = document.getElementById('vacuum-btn');
            const status = document.getElementById('status-message');

            btn.disabled = true;
            btn.textContent = '⏳ Running VACUUM...';
            status.style.display = 'none';

            try {{
                const response = await fetch('/admin/vacuum/trigger', {{
                    method: 'POST'
                }});

                const data = await response.json();

                if (response.ok) {{
                    status.className = 'success';
                    status.textContent = '✓ ' + data.message;
                    status.style.display = 'block';

                    setTimeout(() => {{
                        window.location.reload();
                    }}, 2000);
                }} else {{
                    throw new Error(data.message || 'Unknown error');
                }}
            }} catch (error) {{
                status.className = 'error';
                status.textContent = '✗ Error: ' + error.message;
                status.style.display = 'block';
                btn.disabled = false;
                btn.textContent = '🗄️ Run VACUUM Now';
            }}
        }}

        const lastRefreshStatus = '{status_class}';
        const lastVacuumStatus = '{vac_status_class}';
        if (lastRefreshStatus === 'running' || lastVacuumStatus === 'running') {{
            setTimeout(() => {{
                window.location.reload();
            }}, 30000);
        }}
    </script>
</body>
</html>
"""
    return HTMLResponse(html)

@app.post("/admin/vacuum/trigger")
async def trigger_vacuum():
    """Manually trigger a database VACUUM"""
    import threading

    if last_vacuum_info.get("last_status") == "running":
        return JSONResponse(
            status_code=409,
            content={
                "status": "error",
                "message": "VACUUM already in progress"
            }
        )

    threading.Thread(target=run_vacuum, kwargs={"source": "manual"}, daemon=True).start()
    return {
        "status": "success",
        "message": "VACUUM started in background. Check logs or refresh this page in a moment."
    }

@app.post("/admin/refresh/trigger")
async def trigger_refresh():
    """Manually trigger a database refresh"""
    import threading
    
    # Don't start if already running
    if last_refresh_info.get("last_status") == "running":
        return JSONResponse(
            status_code=409,
            content={
                "status": "error",
                "message": "Refresh already in progress"
            }
        )
    
    threading.Thread(target=run_refresh, kwargs={"source": "manual"}, daemon=True).start()
    return {
        "status": "success",
        "message": "Database refresh started in background. Check logs or refresh this page in a moment."
    }