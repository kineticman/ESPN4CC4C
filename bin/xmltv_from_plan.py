#!/usr/bin/env python3
# file: bin/xmltv_from_plan.py
# ESPN Clean v2.0 — render XMLTV from active plan

import argparse, os, json, sqlite3, html
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

VERSION="2.0.0"
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "xmltv_from_plan.jsonl")

def jlog(**kv):
    kv = {"ts": datetime.now(timezone.utc).isoformat(), "mod":"xmltv_from_plan", **kv}
    line = json.dumps(kv, ensure_ascii=False)
    print(line, flush=True)
    try:
        with open(LOG_PATH,"a",encoding="utf-8") as f: f.write(line+"\n")
    except Exception: pass

def connect_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def get_active_plan(conn):
    r = conn.execute("SELECT value FROM plan_meta WHERE key='active_plan_id'").fetchone()
    return int(r["value"]) if r else None

def load_channels(conn):
    return [dict(r) for r in conn.execute("SELECT id,chno,name,group_name FROM channel WHERE active=1 ORDER BY chno")]

def load_plan(conn, plan_id):
    q = """
    SELECT ps.*, e.*
    FROM plan_slot ps
    LEFT JOIN events e ON e.id = ps.event_id
    WHERE ps.plan_id=?
    ORDER BY ps.channel_id, ps.start_utc
    """
    return [dict(r) for r in conn.execute(q, (plan_id,)).fetchall()]

def fmt_xmltv_dt(iso_utc:str, tz:ZoneInfo):
    dt_utc = datetime.fromisoformat(iso_utc).replace(tzinfo=timezone.utc)
    dt_local = dt_utc.astimezone(tz)
    s = dt_local.strftime("%Y%m%d%H%M%S")
    off = dt_local.utcoffset().total_seconds()//60
    sign = "+" if off>=0 else "-"
    off = abs(int(off))
    return f"{s} {sign}{off//60:02d}{off%60:02d}"

def render_xml(channels, slots, tz:ZoneInfo, plan_id:int, meta):
    out=[]
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append(f'<!-- plan_id={plan_id} valid_from={meta.get("valid_from_utc","")} valid_to={meta.get("valid_to_utc","")} checksum={meta.get("checksum","")} -->')
    out.append('<tv generator-info-name="espn-clean-v2.0">')
    for c in channels:
        out.append(f'  <channel id="{html.escape(c["id"])}">')
        out.append(f'    <display-name>{html.escape(c["name"])}</display-name>')
        out.append(f'    <lcn>{c["chno"]}</lcn>')
        out.append('  </channel>')
    for s in slots:
        start = fmt_xmltv_dt(s["start_utc"], tz)
        stop  = fmt_xmltv_dt(s["end_utc"], tz)
        cid   = html.escape(s["channel_id"])
        title = s["title"] if s.get("title") else ("Stand By" if s["kind"]=="placeholder" else "TBD")
        title = html.escape(title)
        out.append(f'  <programme start="{start}" stop="{stop}" channel="{cid}">')
        out.append(f'    <title lang="en">{title}</title>')
        if s.get("subtitle"):
            out.append(f'    <sub-title lang="en">{html.escape(s["subtitle"])}</sub-title>')
        cat = s["sport"] if s.get("sport") else "Sports"
        out.append(f'    <category lang="en">{html.escape(cat)}</category>')
        if s["kind"]=="placeholder":
            out.append(f'    <desc lang="en">{html.escape("No live event scheduled")}</desc>')
        elif s.get("summary"):
            out.append(f'    <desc lang="en">{html.escape(s["summary"])}</desc>')
        if s.get("image"):
            out.append(f'    <icon src="{html.escape(s["image"])}"/>')
        out.append('  </programme>')
    out.append('</tv>')
    return "\n".join(out)

def load_plan_meta(conn, plan_id):
    r = conn.execute("SELECT * FROM plan_run WHERE id=?", (plan_id,)).fetchone()
    return dict(r) if r else {"valid_from_utc":"", "valid_to_utc":"", "checksum":""}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tz", default="America/New_York")
    args = ap.parse_args()

    conn = connect_db(args.db)
    plan_id = get_active_plan(conn)
    if not plan_id:
        jlog(level="error", event="no_active_plan"); raise SystemExit(2)

    channels = load_channels(conn)
    slots = load_plan(conn, plan_id)
    meta = load_plan_meta(conn, plan_id)
    tz = ZoneInfo(args.tz)

    xml = render_xml(channels, slots, tz, plan_id, meta)
    tmp = args.out + ".tmp"
    with open(tmp,"w",encoding="utf-8") as f: f.write(xml)
    os.replace(tmp, args.out)

    jlog(event="xmltv_written", plan_id=plan_id, out=args.out,
         channels=len(channels), programmes=len(slots))

if __name__=="__main__":
    try: main()
    except Exception as e:
        jlog(level="error", event="xmltv_failed", error=str(e))
        raise
