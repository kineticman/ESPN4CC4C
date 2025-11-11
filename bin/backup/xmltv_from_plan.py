#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xmltv_from_plan.py — Build XMLTV from ESPN4CC4C DB plan.

- Channels are DB-authoritative from `channel` (id, name, chno, active).
- Programmes come from latest plan in `plan_slot`.
- Time format: XMLTV "YYYYMMDDHHMMSS +0000".
- Header: generator-info-name="espn-clean-v2.1".
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from xml.sax.saxutils import escape

GENERATOR = "espn-clean-v2.1"


def iso_to_xmltv(iso: str) -> str:
    """
    Convert ISO8601 like '2025-11-08T02:30:00+00:00' to '20251108023000 +0000'.
    Assumes UTC offset is present; if missing, treats as UTC.
    """
    if not iso:
        return ""
    s = iso.strip()
    # tolerate 'YYYY-MM-DDTHH:MM:SS' (naive) and '+00:00' variant
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    if "+" not in s[10:] and "-" not in s[10:]:
        s += "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y%m%d%H%M%S") + " +0000"
    except Exception:
        # last-ditch: strip offset manually
        try:
            base = (
                s.split("+", 1)[0].split("-", 1)[0] if "+" in s else s.split("-", 1)[0]
            )
            dt = datetime.fromisoformat(base)
            return dt.strftime("%Y%m%d%H%M%S") + " +0000"
        except Exception:
            return ""


def fetch_channels(conn: sqlite3.Connection):
    """
    Return list of dicts: {id(str), name(str), lcn(str)} for active channels.
    """
    rows = conn.execute(
        """
        SELECT id, name, chno, COALESCE(active,1) AS active
        FROM channel
        WHERE COALESCE(active,1)=1
        ORDER BY COALESCE(chno,id)
    """
    ).fetchall()

    out = []
    for r in rows:
        ch_id = int(r[0])
        name = (r[1] or f"ESPN+ EPlus {ch_id}").strip()
        chno = r[2]
        lcn = None
        try:
            lcn = int(chno) if chno is not None else None
        except Exception:
            lcn = None
        if lcn is None:
            lcn = 20009 + ch_id
        out.append({"id": str(ch_id), "name": name, "lcn": str(lcn)})
    return out


def fetch_rows_latest_plan(conn: sqlite3.Connection):
    """
    Returns list of rows for the latest plan_id in plan_slot.
    Each row should provide: channel_id, start_utc, end_utc, kind, title.
    """
    row = conn.execute("SELECT MAX(plan_id) AS pid FROM plan_slot").fetchone()
    if not row or row["pid"] is None:
        return None, []

    pid = int(row["pid"])
    rows = conn.execute(
        """
        SELECT channel_id, start_utc, end_utc, kind, title
        FROM plan_slot
        WHERE plan_id = ?
        ORDER BY channel_id, start_utc
    """,
        (pid,),
    ).fetchall()
    return pid, rows


def write_channels(f, channels):
    for ch in channels:
        cid = escape(ch["id"])
        name = escape(ch["name"])
        lcn = escape(ch["lcn"])
        f.write(f'  <channel id="{cid}">\n')
        f.write(f"    <display-name>{name}</display-name>\n")
        f.write(f"    <lcn>{lcn}</lcn>\n")
        f.write("  </channel>\n")


def write_programmes(f, rows):
    for r in rows:
        cid = str(r["channel_id"])
        start = iso_to_xmltv(r["start_utc"])
        stop = iso_to_xmltv(r["end_utc"])
        kind = (r["kind"] or "").strip()
        title = r["title"] or ("Sports" if kind == "event" else "Stand By")

        f.write(
            f'  <programme channel="{escape(cid)}" start="{escape(start)}" stop="{escape(stop)}">\n'
        )
        f.write(f"    <title>{escape(title)}</title>\n")
        # minimal, clean — add <desc/> here if you want later
        # tag live-ish events (optional): uncomment if you'd like a <live/> node for events
        # if kind == "event":
        #     f.write('    <live/>\n')
        f.write("  </programme>\n")


def main():
    ap = argparse.ArgumentParser(description="Generate XMLTV from latest plan.")
    ap.add_argument("--db", default="data/eplus_vc.sqlite3", help="SQLite DB path")
    ap.add_argument("--out", default="out/epg.xml", help="Output XMLTV path")
    args = ap.parse_args()

    db_path = args.db
    out_path = args.out

    print(f"[xmltv] db={db_path}")
    print(f"[xmltv] out={out_path}")

    if not os.path.isfile(db_path):
        print(f"FATAL: DB not found at {db_path}", file=sys.stderr)
        sys.exit(2)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    try:
        channels = fetch_channels(conn)
        pid, rows = fetch_rows_latest_plan(conn)
        if pid is None:
            print("FATAL: No plan rows in plan_slot", file=sys.stderr)
            sys.exit(3)

        print(f"[xmltv] fetched rows (latest plan only): {len(rows)}")

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n')
            f.write(f'<tv generator-info-name="{GENERATOR}">\n')

            # Channels first (authoritative)
            write_channels(f, channels)

            # Programmes
            write_programmes(f, rows)

            f.write("</tv>\n")

        print("[xmltv] wrote XML successfully")
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
