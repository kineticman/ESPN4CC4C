#!/usr/bin/env python3
import argparse, sqlite3
from urllib.parse import quote
from datetime import datetime, timezone

SERVER_IP     = "192.168.86.72"
RESOLVER_BASE = f"http://{SERVER_IP}:8094"
CC_HOST       = SERVER_IP
CC_PORT       = 5589

def open_db(p):
    c = sqlite3.connect(p); c.row_factory = sqlite3.Row; return c

def latest_plan_id(conn):
    r = conn.execute("SELECT MAX(plan_id) AS pid FROM plan_slot").fetchone()
    return int(r["pid"]) if r and r["pid"] is not None else None

def load_channels(conn):
    return conn.execute("SELECT id, chno, name FROM channel WHERE active=1 ORDER BY chno ASC").fetchall()

def m3u_entry(ch_id, chno, name, resolver_base, cc_host, cc_port, only_live):
    tail = f"/vc/{ch_id}" + ("?only_live=1" if only_live else "")
    inner = f"{resolver_base}{tail}"
    cc_url = f"chrome://{cc_host}:{cc_port}/stream?url=" + quote(inner, safe="")
    group = "ESPN+ VC"
    return f'#EXTINF:-1 tvg-id="{ch_id}" tvg-name="{name}" tvg-chno="{chno}" group-title="{group}",{name}\n{cc_url}'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--resolver-base", default=RESOLVER_BASE)
    ap.add_argument("--cc-host", default=CC_HOST)
    ap.add_argument("--cc-port", type=int, default=CC_PORT)
    ap.add_argument("--only-live", action="store_true", default=False)
    args = ap.parse_args()

    conn = open_db(args.db)
    pid = latest_plan_id(conn)
    chans = load_channels(conn) if pid is not None else []
    body = ["#EXTM3U"]
    for ch in chans:
        body.append(m3u_entry(ch["id"], ch["chno"], ch["name"], args.resolver_base, args.cc_host, args.cc_port, args.only_live))
    if not chans:
        # emit standard 40 as fallback
        for i in range(1,41):
            cid = f"eplus{i}"; name = f"ESPN+ EPlus {i}"; chno = 20010+(i-1)
            body.append(m3u_entry(cid, chno, name, args.resolver_base, args.cc_host, args.cc_port, args.only_live))
    with open(args.out,"w",encoding="utf-8") as f: f.write("\n".join(body) + "\n")
    print(f'{{"ts":"{datetime.now(timezone.utc).isoformat()}","mod":"m3u_from_plan","event":"m3u_written","plan_id":{pid if pid is not None else "null"},"out":"{args.out}","channels":{len(chans) if chans else 40}}}')

if __name__ == "__main__":
    main()
