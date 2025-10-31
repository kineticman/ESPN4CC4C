#!/usr/bin/env python3
"""
vc_diag.py — ESPN4CC4C status+debug helper (no external deps)

Checks:
  • systemd env & liveness for vc-resolver-v2.service
  • resolver endpoints: /health, /epg.xml, /playlist.m3u, /channels, /vc/<lane>/debug
  • discovers available routes via /openapi.json (if exposed)
  • reads .env.plan to auto-configure DB (DB) and XML path (OUT)
  • DB: current slot/feeds, latest plan window, off-minute placeholders
  • Counts: DB programmes (total/events/placeholders) and XML <programme> count
  • Counts: unique channel count in DB vs XML
  • Optional fleet sweep: breakdown across channels
  • Recent resolver errors from journal (quiet mode supported)
  • Final SUMMARY with ✅/⚠️/❌/ℹ️ and exit code (0 good, 1 issues)
"""

import argparse, os, sys, json, sqlite3, subprocess, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Tuple, List, Dict, Optional

# ---------- util ----------
def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def sh(cmd: List[str]) -> Tuple[int, str]:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        return 0, out
    except subprocess.CalledProcessError as e:
        return e.returncode, e.output
    except FileNotFoundError:
        return 127, "command not found"

def http_get(url: str, timeout: float = 4.0) -> Tuple[int, str, dict]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"vc-diag/1.5"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.getcode(), body.decode("utf-8","replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8","replace")
        except Exception:
            body = ""
        return e.code, body, dict(e.headers or {})
    except Exception as e:
        return 0, str(e), {}

def p(title: str, body: str = ""):
    print(f"\n=== {title} ===")
    if body:
        print(body.rstrip())

def j(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))

def db_conn(path: str) -> sqlite3.Connection:
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c

def slot_val(row, key, default=None):
    try:
        return default if row is None else row[key]
    except Exception:
        return default

def load_env_file(path: str) -> Dict[str,str]:
    out: Dict[str,str] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln or ln.startswith("#") or "=" not in ln:
                    continue
                k, v = ln.split("=", 1)
                out[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return out

# ---------- checks ----------
def check_systemd_env() -> str:
    rc, out = sh(["systemctl","show","vc-resolver-v2.service","-p","Environment"])
    if rc != 0:
        return "(systemctl unavailable or permission denied)"
    return out.strip().removeprefix("Environment=")

def check_systemd_status() -> str:
    rc, out = sh(["systemctl","status","vc-resolver-v2.service","--no-pager","-l"])
    return out if rc == 0 else "(unable to read status)"

def check_timers() -> str:
    rc, out = sh(["systemctl","list-timers","--all"])
    if rc != 0:
        return "(unable to list timers)"
    lines = [ln for ln in out.splitlines() if "vc-" in ln]
    return "\n".join(lines) if lines else "(no vc-* timers found)"

def recent_resolver_errors(since_mins: int, quiet: bool=False) -> str:
    since = f"{since_mins} min ago"
    rc, out = sh(["journalctl","-u","vc-resolver-v2.service","--since", since, "-o","cat"])
    if rc != 0:
        return "(journalctl not available or permission denied)"
    errs = []
    for ln in out.splitlines():
        if any(tok in ln for tok in ("ERROR","Traceback","ImportError","NameError","Exception")):
            errs.append(ln)
    if not errs:
        return "(no recent errors)"
    if quiet:
        return f"({len(errs)} error lines in last {since_mins} minutes)"
    # cap + dedupe
    capped, prev = [], None
    for ln in errs[-40:]:
        if ln != prev:
            capped.append(ln)
        prev = ln
    return "\n".join(capped)

def probe_resolver(base: str, lane: str) -> Dict[str,object]:
    r: Dict[str,object] = {
        "base": base, "health": None, "epg": None, "m3u": None,
        "channels_len": None, "channels_code": None, "lane_debug_ok": None, "routes": []
    }
    code, body, _ = http_get(f"{base}/health"); r["health"] = code
    code_open, open_body, _ = http_get(f"{base}/openapi.json")
    if code_open == 200:
        try:
            r["routes"] = sorted(json.loads(open_body).get("paths", {}).keys())
        except Exception:
            r["routes"] = []
    for path, key in (("/epg.xml","epg"), ("/playlist.m3u","m3u"), ("/channels","channels_len")):
        code, body, hdr = http_get(f"{base}{path}")
        if key == "channels_len":
            r["channels_code"] = code
            try:
                arr = json.loads(body)
                r[key] = len(arr) if isinstance(arr, list) else None
            except Exception:
                r[key] = None
        else:
            r[key] = code
    code, body, _ = http_get(f"{base}/vc/{lane}/debug")
    if code and body:
        try:
            dbg = json.loads(body)
            r["lane_debug_ok"] = bool(dbg)
        except Exception:
            r["lane_debug_ok"] = False
    else:
        r["lane_debug_ok"] = False
    return r

def db_slot_and_feeds(conn: sqlite3.Connection, lane: str, ts_iso: str):
    slot = conn.execute("""
      SELECT channel_id,start_utc,end_utc,kind,event_id,preferred_feed_id
        FROM plan_slot
       WHERE plan_id=(SELECT MAX(plan_id) FROM plan_slot)
         AND channel_id=? AND start_utc<=? AND end_utc>?
       ORDER BY start_utc DESC LIMIT 1
    """,(lane, ts_iso, ts_iso)).fetchone()
    feeds = []
    if slot and slot_val(slot,"event_id") is not None:
        feeds = conn.execute("""
          SELECT id,url,is_primary FROM feeds
           WHERE event_id=? AND url IS NOT NULL
           ORDER BY is_primary DESC, id DESC LIMIT 5
        """,(slot["event_id"],)).fetchall()
    return slot, feeds

def db_plan_window(conn: sqlite3.Connection):
    row = conn.execute("SELECT MAX(plan_id) AS pid FROM plan_slot").fetchone()
    if not row or row["pid"] is None:
        return None, None, None
    pid = int(row["pid"])
    w = conn.execute("""
      SELECT MIN(start_utc) AS vfrom, MAX(end_utc) AS vto
        FROM plan_slot WHERE plan_id=?
    """,(pid,)).fetchone()
    return pid, (w["vfrom"] if w else None), (w["vto"] if w else None)

def db_offminute_placeholders(conn: sqlite3.Connection) -> Tuple[int,List[sqlite3.Row]]:
    rows = conn.execute("""
    WITH pid AS (SELECT MAX(plan_id) id FROM plan_slot)
    SELECT channel_id,start_utc,end_utc,placeholder_reason
      FROM plan_slot
     WHERE plan_id=(SELECT id FROM pid) AND kind='placeholder'
       AND CAST(strftime('%M', replace(substr(start_utc,1,19),'T',' ')) AS INT) NOT IN (0,30)
     ORDER BY channel_id,start_utc
    """).fetchall()
    return len(rows), rows

def fleet_sweep(conn: sqlite3.Connection, ts_iso: str) -> Tuple[int,int,int]:
    ch = conn.execute("SELECT id FROM channel WHERE active=1 ORDER BY chno").fetchall()
    ok_event_feed = event_no_feed = placeholder = 0
    for r in ch:
        lane = r["id"]
        slot = conn.execute("""
          SELECT kind,event_id FROM plan_slot
           WHERE plan_id=(SELECT MAX(plan_id) FROM plan_slot)
             AND channel_id=? AND start_utc<=? AND end_utc>?
           ORDER BY start_utc DESC LIMIT 1
        """,(lane, ts_iso, ts_iso)).fetchone()
        if not slot or slot_val(slot,"kind")!="event":
            placeholder += 1
            continue
        feed = conn.execute("SELECT 1 FROM feeds WHERE event_id=? AND url IS NOT NULL LIMIT 1",
                            (slot["event_id"],)).fetchone()
        if feed: ok_event_feed += 1
        else:    event_no_feed += 1
    return ok_event_feed, event_no_feed, placeholder

def db_programme_counts(conn: sqlite3.Connection) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    row = conn.execute("SELECT MAX(plan_id) AS pid FROM plan_slot").fetchone()
    if not row or row["pid"] is None:
        return None, None, None, None
    pid = int(row["pid"])
    total = conn.execute("SELECT COUNT(*) FROM plan_slot WHERE plan_id=?", (pid,)).fetchone()[0]
    ev    = conn.execute("SELECT COUNT(*) FROM plan_slot WHERE plan_id=? AND kind='event'", (pid,)).fetchone()[0]
    ph    = conn.execute("SELECT COUNT(*) FROM plan_slot WHERE plan_id=? AND kind='placeholder'", (pid,)).fetchone()[0]
    return pid, total, ev, ph

def db_channel_count(conn: sqlite3.Connection) -> Optional[int]:
    try:
        return conn.execute("SELECT COUNT(DISTINCT id) FROM channel WHERE active=1").fetchone()[0]
    except Exception:
        return None

def xml_programme_count(xml_path: str) -> Optional[int]:
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        return sum(1 for _ in root.iter("programme"))
    except FileNotFoundError:
        return None
    except Exception:
        try:
            text = open(xml_path, "r", encoding="utf-8", errors="ignore").read()
            return text.count("<programme ")
        except Exception:
            return None

def xml_channel_count(xml_path: str) -> Optional[int]:
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        return sum(1 for _ in root.iter("channel"))
    except FileNotFoundError:
        return None
    except Exception:
        try:
            text = open(xml_path, "r", encoding="utf-8", errors="ignore").read()
            return text.count("<channel ")
        except Exception:
            return None

# ---------- main ----------
def main():
    default_proj = "/home/brad/Projects/ESPN4CC4C"
    default_env  = os.path.join(default_proj, ".env.plan")
    env = load_env_file(default_env)

    ap = argparse.ArgumentParser(description="ESPN4CC4C diag")
    ap.add_argument("--lane", default=os.getenv("VC_DIAG_LANE","eplus11"))
    ap.add_argument("--db", default=os.getenv("VC_DB", env.get("DB", f"{default_proj}/data/eplus_vc.sqlite3")))
    ap.add_argument("--resolver", default=os.getenv("VC_RESOLVER_ORIGIN", env.get("RESOLVER_BASE","http://127.0.0.1:8094")))
    ap.add_argument("--xml", default=env.get("OUT", f"{default_proj}/out/epg.xml"), help="path to epg.xml (defaults to OUT in .env.plan)")
    ap.add_argument("--since-mins", type=int, default=30)
    ap.add_argument("--quiet-errors", action="store_true", help="only show a count of recent resolver errors")
    ap.add_argument("--no-fleet", action="store_true", help="skip sweeping all channels")
    ap.add_argument("--env-file", default=default_env, help="path to .env.plan (auto-loaded)")
    args = ap.parse_args()

    # prefer .env.plan values if defaults don't exist
    if not os.path.isfile(args.db) and os.path.isfile(args.env_file):
        env2 = load_env_file(args.env_file)
        if env2.get("DB") and os.path.isfile(env2["DB"]):
            args.db = env2["DB"]
        if env2.get("OUT") and (args.xml == f"{default_proj}/out/epg.xml"):
            args.xml = env2["OUT"]

    p("when/where", f"now(utc)={now_utc_iso()}\nresolver={args.resolver}\ndb={args.db}\nxml={args.xml}\nlane={args.lane}\nenv_file={args.env_file if os.path.isfile(args.env_file) else '(none)'}")

    # systemd info
    p("systemd env", check_systemd_env())
    p("resolver status (short)", "\n".join(check_systemd_status().splitlines()[:15]))
    p("timers", check_timers())

    # resolver probes
    rp = probe_resolver(args.resolver, args.lane)
    p("resolver probes", f"/health={rp['health']}  /epg.xml={rp['epg']}  /playlist.m3u={rp['m3u']}  /channels={rp['channels_code']}/{rp['channels_len']}  lane_debug_ok={rp['lane_debug_ok']}")
    if rp["routes"]:
        p("resolver routes (from openapi.json)", "\n".join(rp["routes"]))

    # DB checks
    db_ok = True
    try:
        conn = db_conn(args.db)
    except Exception as e:
        db_ok = False
        p("db error", f"failed to open DB at {args.db}\n{e}\n- Tip: check .env.plan DB, or run the vc-plan service to populate.")

    slot = feeds = None
    pid = vfrom = vto = None
    n_off = 0
    fleet = (0,0,0)
    db_counts = (None, None, None, None)
    db_chan = None
    if db_ok:
        ts = now_utc_iso()
        slot, feeds = db_slot_and_feeds(conn, args.lane, ts)
        p(f"db: current slot for {args.lane}", json.dumps(dict(slot) if slot else {}, indent=2))
        if slot_val(slot,"event_id") is not None:
            p("db: feeds for current event", json.dumps([dict(x) for x in feeds], indent=2) if feeds else "(none)")

        pid, vfrom, vto = db_plan_window(conn)
        p("db: plan window/id", f"plan_id={pid}  valid_from={vfrom}  valid_to={vto}")

        n_off, rows = db_offminute_placeholders(conn)
        preview = "\n".join(f"- {r['channel_id']} {r['start_utc']}→{r['end_utc']} {r['placeholder_reason']}" for r in rows[:12])
        p("db: off-minute placeholders (should be 0)", f"count={n_off}\n{preview}")

        if not args.no_fleet:
            fleet = fleet_sweep(conn, ts)
            ok, missing, ph = fleet
            p("fleet sweep @ now", f"event+feed={ok}  event(no feed)={missing}  placeholder={ph}")

        db_counts = db_programme_counts(conn)
        _, total_slots, ev, ph = db_counts
        p("db: programme counts (latest plan_id)", f"total={total_slots}  events={ev}  placeholders={ph}")

        db_chan = db_channel_count(conn)

    # XML counts
    xml_prog = xml_programme_count(args.xml)
    xml_chan = xml_channel_count(args.xml)
    p("xml: programme count", f"{xml_prog if xml_prog is not None else '(missing or unreadable)'}")
    p("xml: channel count", f"{xml_chan if xml_chan is not None else '(missing or unreadable)'}")
    if db_ok:
        p("channel counts (DB vs XML)", f"db={db_chan}  xml={xml_chan}")

    # recent errors
    p("recent resolver errors", recent_resolver_errors(args.since_mins, quiet=args.quiet_errors))

    # --------- SUMMARY ---------
    ok_items: List[str] = []
    warn_items: List[str] = []
    bad_items: List[str] = []
    info_items: List[str] = []

    # resolver health
    if rp["health"] == 200: ok_items.append("Resolver /health 200")
    elif rp["health"] in (0, None): bad_items.append("Resolver not reachable")
    else: warn_items.append(f"Resolver /health HTTP {rp['health']}")

    # critical endpoints
    ok_items.append("/epg.xml 200" if rp["epg"] == 200 else "/epg.xml not OK")
    if rp["m3u"] == 200: ok_items.append("/playlist.m3u 200")
    else: warn_items.append("/playlist.m3u not OK")

    # channels endpoint
    if rp.get("channels_code") == 200:
        if isinstance(rp["channels_len"], int):
            if rp["channels_len"] > 0: ok_items.append(f"/channels 200 ({rp['channels_len']} entries)")
            else: warn_items.append("/channels 200 but empty array")
        else:
            # treat non-JSON as informational, not a failure
            info_items.append("/channels 200 but non-JSON")
    elif rp.get("channels_code") is None:
        info_items.append("/channels not checked")
    else:
        info_items.append(f"/channels HTTP {rp['channels_code']}")

    # lane debug
    if rp["lane_debug_ok"]: ok_items.append(f"/vc/{args.lane}/debug OK")
    else: warn_items.append(f"/vc/{args.lane}/debug unavailable")

    # DB + plan + count comparisons
    if db_ok:
        total_slots = db_counts[1]
        if pid is not None: ok_items.append(f"plan_id={pid}")
        else: bad_items.append("No plan_id in plan_slot")

        if n_off == 0: ok_items.append("no off-minute placeholders")
        else: warn_items.append(f"{n_off} off-minute placeholders")

        # programmes: DB vs XML
        if total_slots is not None and xml_prog is not None:
            if total_slots == xml_prog:
                ok_items.append(f"programmes match (DB={total_slots} XML={xml_prog})")
            else:
                warn_items.append(f"programmes mismatch (DB={total_slots} XML={xml_prog})")
        elif xml_prog is None:
            warn_items.append("xml programme count unavailable")

        # channels: DB vs XML
        if isinstance(db_chan, int) and isinstance(xml_chan, int):
            if db_chan == xml_chan:
                ok_items.append(f"channels match (DB={db_chan} XML={xml_chan})")
            else:
                warn_items.append(f"channels mismatch (DB={db_chan} XML={xml_chan})")

        # fleet info
        if not args.no_fleet:
            ok, missing, ph = fleet
            info_items.append(f"fleet: ok={ok} missing_feed={missing} placeholders={ph}")
    else:
        bad_items.append("DB not openable (check .env.plan DB path and vc-plan)")

    # Suggested actions
    suggestions: List[str] = []
    if rp["epg"] != 200: suggestions.append("Resolver /epg.xml failing → check vc-resolver-v2 logs & app module path.")
    if db_ok and pid is None: suggestions.append("No plan rows → run vc-plan.service to build plan.")
    if db_ok and n_off > 0: suggestions.append("Off-minute placeholders detected → rebuild with ALIGN=30 and clamp enabled.")
    if db_ok and slot_val(slot,"kind") == "event" and (feeds is not None and len(feeds) == 0):
        suggestions.append("Event has no feed → re-run ingest or verify ESPN watch IDs.")
    if rp["health"] in (0, None): suggestions.append("Resolver unreachable → verify service is active and bound to :8094.")
    if isinstance(rp.get("channels_len"), int) and rp["channels_len"] == 0:
        suggestions.append("/channels empty → confirm channel seeding/lanes in DB.")

    print("\n===== SUMMARY =====")
    for s in ok_items:  print(f"✅ {s}")
    for s in warn_items:print(f"⚠️  {s}")
    for s in bad_items: print(f"❌ {s}")
    for s in info_items:print(f"ℹ️  {s}")

    if slot is not None:
        print(f"\nCurrent slot: {slot['channel_id']} {slot['start_utc']}→{slot['end_utc']} {slot['kind']} (event_id={slot_val(slot,'event_id','-')})")

    if suggestions:
        print("\nSuggested actions:")
        for s in suggestions:
            print(f" • {s}")

    sys.exit(0 if not bad_items else 1)

if __name__ == "__main__":
    main()
