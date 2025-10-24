#!/usr/bin/env python3
# file: bin/m3u_from_plan.py
# ESPN Clean v2.0 — render M3U from active plan (resolver-driven lanes)

import argparse, os, json, sqlite3, urllib.parse
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "m3u_from_plan.jsonl")

def jlog(**kv):
    kv = {"ts": datetime.now(timezone.utc).isoformat(), "mod":"m3u_from_plan", **kv}
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--resolver-base", required=True, help="http://LAN:8093")
    ap.add_argument("--cc-host", required=True)
    ap.add_argument("--cc-port", required=True)
    ap.add_argument("--only-live", action="store_true")
    args = ap.parse_args()

    conn = connect_db(args.db)
    pid = get_active_plan(conn)
    chans = load_channels(conn)

    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for c in chans:
            inner = f'{args.resolver_base.rstrip("/")}/vc/{c["id"]}'
            if args.only_live:
                inner += "?only_live=1"
            url = f"chrome://{args.cc_host}:{args.cc_port}/stream?url=" + urllib.parse.quote(inner, safe="")
            tvg_id = c["id"]
            tvg_name = c["name"]
            group = c["group_name"]
            f.write(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{tvg_name}" tvg-chno="{c["chno"]}" group-title="{group}",{tvg_name}\n')
            f.write(url + "\n")
    os.replace(tmp, args.out)
    jlog(event="m3u_written", plan_id=pid, out=args.out, channels=len(chans), only_live=args.only_live)

if __name__=="__main__":
    try: main()
    except Exception as e:
        jlog(level="error", event="m3u_failed", error=str(e))
        raise
