#!/usr/bin/env python3
import argparse
import os as _os
import sqlite3
from datetime import datetime, timezone
from urllib.parse import quote

# Resolver / CC defaults (env-first; fully overridable by args)
DEFAULT_RESOLVER = (
    _os.getenv("VC_RESOLVER_BASE_URL")
    or _os.getenv("VC_RESOLVER_ORIGIN")
    or "http://127.0.0.1:8094"
)
DEFAULT_CC_HOST = _os.getenv("CC_HOST", "127.0.0.1")
try:
    DEFAULT_CC_PORT = int(_os.getenv("CC_PORT", "5589"))
except Exception:
    DEFAULT_CC_PORT = 5589

# CH4C (Chrome HDMI for Channels) - optional, separate system
DEFAULT_CH4C_HOST = _os.getenv("CH4C_HOST", "127.0.0.1")
try:
    DEFAULT_CH4C_PORT = int(_os.getenv("CH4C_PORT", "2442"))
except Exception:
    DEFAULT_CH4C_PORT = 2442

# M3U cosmetics
M3U_GROUP_TITLE = _os.getenv("M3U_GROUP_TITLE", "ESPN+ VC")

# Fallback lane count ONLY when DB has no active channels (first-run)
# Single source of truth: LANES (default 40)
DEFAULT_LANES = int(_os.getenv("LANES", "40"))


def open_db(p):
    c = sqlite3.connect(p)
    c.row_factory = sqlite3.Row
    return c


def latest_plan_id(conn):
    r = conn.execute("SELECT MAX(plan_id) AS pid FROM plan_slot").fetchone()
    return int(r["pid"]) if r and r["pid"] is not None else None


def load_channels(conn):
    return conn.execute(
        "SELECT id, chno, name FROM channel WHERE active=1 ORDER BY chno ASC"
    ).fetchall()


def m3u_entry(ch_id, chno, name, resolver_base, cc_host, cc_port, only_live):
    tail = f"/vc/{ch_id}" + ("?only_live=1" if only_live else "")
    inner = f"{resolver_base}{tail}"
    cc_url = f"chrome://{cc_host}:{cc_port}/stream?url=" + quote(inner, safe="")
    return (
        f'#EXTINF:-1 tvg-id="{ch_id}" tvg-name="{name}" tvg-chno="{chno}" '
        f'group-title="{M3U_GROUP_TITLE}",{name}\n'
        f"{cc_url}"
    )


def m3u_entry_ch4c(ch_id, chno, name, resolver_base, ch4c_host, ch4c_port, only_live):
    """Generate CH4C (Chrome HDMI for Channels) style M3U entry with http:// URL"""
    tail = f"/vc/{ch_id}" + ("?only_live=1" if only_live else "")
    inner = f"{resolver_base}{tail}"
    ch4c_url = f"http://{ch4c_host}:{ch4c_port}/stream?url=" + quote(inner, safe="")
    return (
        f'#EXTINF:-1 tvg-id="{ch_id}" tvg-name="{name}" tvg-chno="{chno}" '
        f'group-title="{M3U_GROUP_TITLE}",{name}\n'
        f"{ch4c_url}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--resolver-base", default=DEFAULT_RESOLVER)
    ap.add_argument("--cc-host", default=DEFAULT_CC_HOST)
    ap.add_argument("--cc-port", type=int, default=DEFAULT_CC_PORT)
    ap.add_argument("--ch4c-host", default=DEFAULT_CH4C_HOST)
    ap.add_argument("--ch4c-port", type=int, default=DEFAULT_CH4C_PORT)
    ap.add_argument("--only-live", action="store_true", default=False)
    args = ap.parse_args()

    conn = open_db(args.db)
    pid = latest_plan_id(conn)
    chans = load_channels(conn) if pid is not None else []

    # Build both M3U variants
    body_cc = ["#EXTM3U"]
    body_ch4c = ["#EXTM3U"]
    
    if chans:
        for ch in chans:
            body_cc.append(
                m3u_entry(
                    ch["id"],
                    ch["chno"],
                    ch["name"],
                    args.resolver_base,
                    args.cc_host,
                    args.cc_port,
                    args.only_live,
                )
            )
            body_ch4c.append(
                m3u_entry_ch4c(
                    ch["id"],
                    ch["chno"],
                    ch["name"],
                    args.resolver_base,
                    args.ch4c_host,
                    args.ch4c_port,
                    args.only_live,
                )
            )
    else:
        # First-run / empty DB fallback: emit N lanes based on LANES
        LCN_BASE = int(_os.getenv("EPLUS_LCN_BASE", "20010"))
        for i in range(1, DEFAULT_LANES + 1):
            cid = f"eplus{i}"
            name = f"ESPN+ EPlus {i}"
            chno = LCN_BASE + (i - 1)
            body_cc.append(
                m3u_entry(
                    cid,
                    chno,
                    name,
                    args.resolver_base,
                    args.cc_host,
                    args.cc_port,
                    args.only_live,
                )
            )
            body_ch4c.append(
                m3u_entry_ch4c(
                    cid,
                    chno,
                    name,
                    args.resolver_base,
                    args.ch4c_host,
                    args.ch4c_port,
                    args.only_live,
                )
            )

    # Write standard CC version
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(body_cc) + "\n")

    # Write CH4C version (replace .m3u extension with .ch4c.m3u)
    ch4c_out = args.out.replace(".m3u", ".ch4c.m3u")
    with open(ch4c_out, "w", encoding="utf-8") as f:
        f.write("\n".join(body_ch4c) + "\n")

    print(
        f'{{"ts":"{datetime.now(timezone.utc).isoformat()}","mod":"m3u_from_plan",'
        f'"event":"m3u_written","plan_id":{pid if pid is not None else "null"},'
        f'"out":"{args.out}","ch4c_out":"{ch4c_out}","channels":{len(chans) if chans else DEFAULT_LANES}}}'
    )


if __name__ == "__main__":
    main()
