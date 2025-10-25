#!/usr/bin/env python3
"""
vc_diag.py — ESPN Clean v2 status+debug helper (no external deps)

What it checks:
  • systemd env & liveness for vc-resolver-v2.service
  • resolver endpoints: /health, /epg.xml, /playlist.m3u, /vc/<lane>/debug
  • DB: current slot for lane, feeds, latest plan window, off-minute placeholders
  • Optional fleet sweep: all active channels -> event/feed/placeholder breakdown
  • Recent resolver errors from journal (if available without sudo)

Examples:
  python3 vc_diag.py
  python3 vc_diag.py --lane eplus11
  python3 vc_diag.py --resolver http://192.168.86.72:8094 --db ~/Projects/ESPN_clean_v2/data/eplus_vc.sqlite3
"""

import argparse, os, sys, json, sqlite3, subprocess, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List

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

def http_get(url: str, timeout: float = 3.0) -> Tuple[int, str, dict]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"vc-diag/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.getcode(), body.decode("utf-8","replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        try: body = e.read().decode("utf-8","replace")
        except Exception: body = ""
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

# ---------- checks ----------
def check_systemd_env() -> str:
    rc, out = sh(["systemctl","show","vc-resolver-v2.service","-p","Environment"])
    if rc != 0: return "(systemctl unavailable or permission denied)"
    return out.strip().removeprefix("Environment=")

def check_systemd_status() -> str:
    rc, out = sh(["systemctl","status","vc-resolver-v2.service","--no-pager","-l"])
    return out if rc == 0 else "(unable to read status)"

def check_timers() -> str:
    rc, out = sh(["systemctl","list-timers","--all"])
    if rc != 0: return "(unable to list timers)"
    lines = [ln for ln in out.splitlines() if "vc-" in ln]
    return "\n".join(lines) if lines else "(no vc-* timers found)"

def recent_resolver_errors(since_mins: int) -> str:
    since = f"{since_mins} min ago"
    rc, out = sh(["journalctl","-u","vc-resolver-v2.service","--since", since, "-o","cat"])
    if rc != 0: return "(journalctl not available or permission denied)"
    lines = []
    for ln in out.splitlines():
        if any(tok in ln for tok in ("ERROR","Traceback","ImportError","NameError","Exception")):
            lines.append(ln)
    return "\n".join(lines) if lines else "(no recent errors)"

def resolver_probes(base: str, lane: str):
    code, body, _ = http_get(f"{base}/health")
    p("resolver /health", f"HTTP {code}\n{body if len(body)<400 else body[:400]+'…'}")

    for path in ("/epg.xml","/playlist.m3u"):
        code, _, hdr = http_get(f"{base}{path}")
        p(f"resolver {path}", f"HTTP {code}  Content-Type: {hdr.get('Content-Type','-')}")

    code, body, _ = http_get(f"{base}/vc/{lane}/debug")
    p(f"resolver /vc/{lane}/debug", f"HTTP {code}")
    try:
        dbg = json.loads(body) if code and body else {}
        j(dbg)
    except Exception:
        print(body[:1000])

def db_slot_and_feeds(conn: sqlite3.Connection, lane: str, ts_iso: str):
    slot = conn.execute("""
      SELECT channel_id,start_utc,end_utc,kind,event_id,preferred_feed_id
        FROM plan_slot
       WHERE plan_id=(SELECT MAX(plan_id) FROM plan_slot)
         AND channel_id=? AND start_utc<=? AND end_utc>?
       ORDER BY start_utc DESC LIMIT 1
    """,(lane, ts_iso, ts_iso)).fetchone()

    feeds = []
    if slot and slot["event_id"]:
        feeds = conn.execute("""
          SELECT id,url,is_primary FROM feeds
           WHERE event_id=? AND url IS NOT NULL
           ORDER BY is_primary DESC, id DESC LIMIT 5
        """,(slot["event_id"],)).fetchall()
    return slot, feeds

def db_plan_window(conn: sqlite3.Connection):
    row = conn.execute("SELECT MAX(plan_id) AS pid FROM plan_slot").fetchone()
    if not row or row["pid"] is None: return None, None, None
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
        if not slot or slot["kind"]!="event":
            placeholder += 1
            continue
        feed = conn.execute("SELECT 1 FROM feeds WHERE event_id=? AND url IS NOT NULL LIMIT 1",
                            (slot["event_id"],)).fetchone()
        if feed: ok_event_feed += 1
        else:    event_no_feed += 1
    return ok_event_feed, event_no_feed, placeholder

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser(description="ESPN Clean v2 diag")
    ap.add_argument("--lane", default=os.getenv("VC_DIAG_LANE","eplus11"))
    ap.add_argument("--db", default=os.getenv("VC_DB","/home/brad/Projects/ESPN_clean_v2/data/eplus_vc.sqlite3"))
    ap.add_argument("--resolver", default=os.getenv("VC_RESOLVER_ORIGIN","http://127.0.0.1:8094"))
    ap.add_argument("--since-mins", type=int, default=30)
    ap.add_argument("--no-fleet", action="store_true", help="skip sweeping all channels")
    args = ap.parse_args()

    p("when/where", f"now(utc)={now_utc_iso()}\nresolver={args.resolver}\ndb={args.db}\nlane={args.lane}")

    # systemd info
    p("systemd env", check_systemd_env())
    p("resolver status (short)", "\n".join(check_systemd_status().splitlines()[:15]))
    p("timers", check_timers())

    # resolver probes
    resolver_probes(args.resolver, args.lane)

    # DB checks
    try:
        conn = db_conn(args.db)
    except Exception as e:
        p("db error", f"failed to open DB: {e}")
        sys.exit(2)

    ts = now_utc_iso()
    slot, feeds = db_slot_and_feeds(conn, args.lane, ts)
    p(f"db: current slot for {args.lane}", json.dumps(dict(slot) if slot else {}, indent=2))
    if slot and slot["event_id"]:
        p("db: feeds for current event",
          json.dumps([dict(x) for x in feeds], indent=2) if feeds else "(none)")

    pid, vfrom, vto = db_plan_window(conn)
    p("db: plan window/id", f"plan_id={pid}  valid_from={vfrom}  valid_to={vto}")

    n_off, rows = db_offminute_placeholders(conn)
    p("db: off-minute placeholders (should be 0)",
      f"count={n_off}\n" + ("\n".join(f"- {r['channel_id']} {r['start_utc']}→{r['end_utc']} {r['placeholder_reason']}" for r in rows[:12])))

    if not args.no_fleet:
        ok, missing, ph = fleet_sweep(conn, ts)
        p("fleet sweep @ now",
          f"event+feed={ok}  event(no feed)={missing}  placeholder={ph}")

    # recent errors
    p("recent resolver errors", recent_resolver_errors(args.since_mins))

    # quick hints
    hints = []
    if slot and slot["kind"]=="event" and not feeds:
        hints.append("Current slot is an EVENT but has no feed → check ingest or ESPN watch IDs for this event.")
    if pid is None:
        hints.append("No plan_id in plan_slot → run the pipeline service manually to build a plan.")
    if n_off > 0:
        hints.append("Found off-minute placeholders → rebuild with fixed build_plan (half-hour alignment).")
    if hints:
        p("suggested actions", "\n".join(f"- {h}" for h in hints))
    else:
        p("suggested actions", "(none)")

if __name__ == "__main__":
    main()
