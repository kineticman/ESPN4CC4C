#!/usr/bin/env python3
import argparse, sqlite3, sys, json, os
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

# Placeholder wording (override via env if you like)
PH_TITLE    = os.getenv('VC_PLACEHOLDER_TITLE', 'Stand By')
PH_SUBTITLE = os.getenv('VC_PLACEHOLDER_SUBTITLE', '')
PH_SUMMARY  = os.getenv('VC_PLACEHOLDER_SUMMARY', 'No live event scheduled')

# Resolver origin (default to your LAN)
LAN_ORIGIN = os.getenv('VC_RESOLVER_ORIGIN', 'http://192.168.86.72:8094')

def iso_to_xmltv(ts: str) -> str:
    # supports "Z" or "+00:00"
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    return dt.strftime("%Y%m%d%H%M%S +0000")

def _row_get(r, k):
    try:
        return r[k]
    except Exception:
        return None

def conn_open(path):
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c

def have_table(conn, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone())

def latest_plan_id(conn):
    r = conn.execute("SELECT MAX(plan_id) AS pid FROM plan_slot").fetchone()
    return int(r["pid"]) if r and r["pid"] is not None else None

def compute_window(conn, pid: int):
    r = conn.execute(
        "SELECT MIN(start_utc) AS vfrom, MAX(end_utc) AS vto "
        "FROM plan_slot WHERE plan_id=?",
        (pid,)
    ).fetchone()
    return (r["vfrom"], r["vto"]) if r else (None, None)

def read_checksum(conn, pid: int):
    # prefer plan_run.checksum if present
    if have_table(conn, "plan_run"):
        try:
            r = conn.execute("SELECT checksum FROM plan_run WHERE id=?", (pid,)).fetchone()
            if r and r["checksum"]:
                return r["checksum"]
        except sqlite3.OperationalError:
            pass
    # else try plan_meta.checksum
    if have_table(conn, "plan_meta"):
        try:
            # support either id or plan_id keying
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(plan_meta)") }
            key = "plan_id" if "plan_id" in cols else ("id" if "id" in cols else None)
            if key and "checksum" in cols:
                r = conn.execute(f"SELECT checksum FROM plan_meta WHERE {key}=?", (pid,)).fetchone()
                if r and r["checksum"]:
                    return r["checksum"]
        except sqlite3.OperationalError:
            pass
    return None

def load_channels(conn):
    return conn.execute(
        "SELECT id, chno, name FROM channel WHERE active=1 ORDER BY chno ASC"
    ).fetchall()

def load_slots(conn, pid):
    q = """
    SELECT
      s.channel_id AS chan,
      s.kind       AS slot_kind,
      s.start_utc  AS slot_start,
      s.end_utc    AS slot_stop,
      s.event_id   AS event_id,
      e.title      AS event_title,
      e.subtitle   AS event_subtitle,
      e.summary    AS event_summary,
      e.sport      AS event_sport,
      e.image      AS event_image,
      e.start_utc  AS event_start
    FROM plan_slot s
    LEFT JOIN events e ON e.id = s.event_id
    WHERE s.plan_id = ?
    ORDER BY s.channel_id, s.start_utc
    """
    return conn.execute(q, (pid,)).fetchall()

def build_xml(ch_rows, slots, resolver_base, meta):
    tv = ET.Element("tv", {"generator-info-name": "espn-clean-v2.0"})
    tv.append(ET.Comment(
        f" plan_id={meta.get('id')} valid_from={meta.get('valid_from')} "
        f"valid_to={meta.get('valid_to')} checksum={meta.get('checksum')} "
    ))

    # channels
    for ch in ch_rows:
        c = ET.SubElement(tv, "channel", id=ch["id"])
        ET.SubElement(c, "display-name").text = ch["name"]
        ET.SubElement(c, "lcn").text = str(ch["chno"])

    # programmes
    programmes = 0
    for r in slots:
        chan  = r["chan"]
        start_str = r["slot_start"]
        # Backdate to true event start (if earlier) so EPG shows full progress
        if _row_get(r,"slot_kind") == "event" and _row_get(r,"event_start"):
            if r["event_start"] < start_str:
                start_str = r["event_start"]
        start = iso_to_xmltv(start_str)
        stop  = iso_to_xmltv(r["slot_stop"])

        p = ET.SubElement(tv, "programme", channel=chan, start=start, stop=stop)

        # Title: event title if present; placeholder uses PH_TITLE
        title_txt = (r["event_title"] or "").strip()
        if r["slot_kind"] != "event" or not title_txt:
            title_txt = PH_TITLE
        ET.SubElement(p, "title").text = title_txt

        # Optional metadata
        if r["event_subtitle"]:
            ET.SubElement(p, "sub-title").text = r["event_subtitle"]
        if r["event_summary"]:
            ET.SubElement(p, "desc").text = r["event_summary"]

        # Categories ONLY for real sports events
        sport = (r["event_sport"] or "").strip()
        if r["slot_kind"] == "event" and sport:
            ET.SubElement(p, "category").text = "Sports"
            ET.SubElement(p, "category").text = sport
            ET.SubElement(p, "category").text = "Sports Event"
            ET.SubElement(p, "category").text = "Live"

        if r["event_image"]:
            ET.SubElement(p, "icon", {"src": r["event_image"]})

        ET.SubElement(p, "url").text = f"{resolver_base}/vc/{chan}"

        programmes += 1

    # pretty print
    def indent(e, level=0):
        i = "\n" + level * "  "
        if len(e):
            if not e.text or not e.text.strip():
                e.text = i + "  "
            for child in e:
                indent(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = i
        if level and (not e.tail or not e.tail.strip()):
            e.tail = i

    indent(tv)
    return ET.ElementTree(tv), programmes

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--resolver-base", default=LAN_ORIGIN)
    args = ap.parse_args()

    conn = conn_open(args.db)
    pid = latest_plan_id(conn)
    if pid is None:
        print(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                          "mod": "xmltv_from_plan", "event": "no_active_plan"}))
        sys.exit(0)

    vfrom, vto = compute_window(conn, pid)
    checksum = read_checksum(conn, pid)
    meta = {"id": pid, "valid_from": vfrom, "valid_to": vto, "checksum": checksum}

    channels = load_channels(conn)
    slots    = load_slots(conn, pid)
    tree, n  = build_xml(channels, slots, args.resolver_base, meta)
    tree.write(args.out, encoding="utf-8", xml_declaration=True)
    print(json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "mod": "xmltv_from_plan", "event": "xmltv_written",
        "plan_id": pid, "out": args.out, "channels": len(channels), "programmes": n
    }))

if __name__ == "__main__":
    main()
