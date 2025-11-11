#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xmltv_from_plan.py — Build XMLTV from ESPN4CC4C DB plan.
ENHANCED version with rich ESPN metadata, deduplication, and fixed LCN

Features:
- Channels are DB-authoritative from `channel` (id, name, chno, active)
- Programmes come from latest plan in `plan_slot`
- Rich metadata from ESPN: leagues, networks, packages, event types
- Enhanced categories, descriptions, icons, and sub-titles
- Deduplication of programme entries
- Time format: XMLTV "YYYYMMDDHHMMSS +0000"
- Header: generator-info-name="espn-clean-v2.1"

XMLTV Tags Generated:
- <title>, <sub-title>, <desc> with intelligent content hierarchy
- <category> tags: Sports, sport name, league, network, packages, event type
- <icon> tags with ESPN thumbnail URLs
- <url> tags pointing to virtual channel resolver
- <live> tag for live events
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from xml.sax.saxutils import escape

GENERATOR = "espn-clean-v2.1"


def safe_get(row, key: str, default=""):
    """
    Safely get a value from a sqlite3.Row, handling None and missing keys.
    """
    try:
        val = row[key]
        return val if val is not None else default
    except (KeyError, IndexError, TypeError):
        return default


# Resolver base (env-first; matches m3u_from_plan)
DEFAULT_RESOLVER = (
    os.getenv("VC_RESOLVER_BASE_URL")
    or os.getenv("VC_RESOLVER_ORIGIN")
    or "http://127.0.0.1:8094"
)

# Try to import channel start from config, fallback to default
try:
    from config import CHANNEL_START_CHNO as CFG_CHANNEL_START_CHNO
except Exception:
    CFG_CHANNEL_START_CHNO = 20010


def iso_to_xmltv(iso: str) -> str:
    """
    Convert ISO8601 like '2025-11-08T02:30:00+00:00' to '20251108023000 +0000'.
    Assumes UTC offset is present; if missing, treats as UTC.
    PATCHED: Improved error handling with logging.
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
    except Exception as e:
        # last-ditch: strip offset manually
        try:
            base = (
                s.split("+", 1)[0].split("-", 1)[0] if "+" in s else s.split("-", 1)[0]
            )
            dt = datetime.fromisoformat(base)
            return dt.strftime("%Y%m%d%H%M%S") + " +0000"
        except Exception:
            print(f"WARNING: Failed to parse timestamp '{iso}': {e}", file=sys.stderr)
            return ""


def fetch_channels(conn: sqlite3.Connection):
    """
    Return list of dicts: {id(str), name(str), lcn(str)} for active channels.
    PATCHED: Fixed LCN calculation to use config value properly.
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
        ch_id = str(r[0])
        name = (r[1] or f"ESPN+ EPlus {r[0]}").strip()
        chno = r[2]

        # PATCHED: Use actual chno from DB, fallback to calculated value
        if chno is not None:
            try:
                lcn = str(int(chno))
            except Exception:
                lcn = str(CFG_CHANNEL_START_CHNO + int(ch_id) - 1)
        else:
            lcn = str(CFG_CHANNEL_START_CHNO + int(ch_id) - 1)

        out.append({"id": ch_id, "name": name, "lcn": lcn})
    return out


def fetch_rows_latest_plan(conn: sqlite3.Connection):
    """
    Returns list of rows for the latest plan_id in plan_slot.
    Each row should provide: channel_id, start_utc, end_utc, kind, title, sport, subtitle, summary.
    PATCHED: JOINs with events table to get actual event titles and ALL metadata.
    """
    row = conn.execute("SELECT MAX(plan_id) AS pid FROM plan_slot").fetchone()
    if not row or row["pid"] is None:
        return None, []

    pid = int(row["pid"])
    rows = conn.execute(
        """
        SELECT
            ps.channel_id,
            ps.start_utc,
            ps.end_utc,
            ps.kind,
            COALESCE(e.title, ps.title) AS title,
            e.sport,
            e.subtitle,
            e.summary,
            e.image,
            e.network,
            e.network_short,
            e.league_name,
            e.league_abbr,
            e.sport_abbr,
            e.packages,
            e.event_type,
            e.language
        FROM plan_slot ps
        LEFT JOIN events e ON ps.event_id = e.id
        WHERE ps.plan_id = ?
        ORDER BY ps.channel_id, ps.start_utc
    """,
        (pid,),
    ).fetchall()
    return pid, rows


def write_channels(f, channels):
    """Write channel definitions to XMLTV."""
    for ch in channels:
        cid = escape(ch["id"])
        name = escape(ch["name"])
        lcn = escape(ch["lcn"])
        f.write(f'  <channel id="{cid}">\n')
        f.write(f"    <display-name>{name}</display-name>\n")
        f.write(f"    <lcn>{lcn}</lcn>\n")
        f.write("  </channel>\n")


def write_programmes(f, rows):
    """
    Write programme entries to XMLTV with ENHANCED metadata from ESPN.
    PATCHED: Added deduplication, rich categories, icons, better descriptions.
    """
    seen = set()  # Track (channel_id, start, stop, title) to detect duplicates
    duplicates_skipped = 0

    for r in rows:
        cid = str(r["channel_id"])
        start = iso_to_xmltv(r["start_utc"])
        stop = iso_to_xmltv(r["end_utc"])
        kind = (r["kind"] or "").strip()
        title = r["title"] or ("Sports" if kind == "event" else "Stand By")

        # Get all enhanced metadata from events table
        sport = safe_get(r, "sport", "").strip()
        sport_abbr = safe_get(r, "sport_abbr", "").strip()
        subtitle = safe_get(r, "subtitle", "").strip()
        summary = safe_get(r, "summary", "").strip()
        image = safe_get(r, "image", "").strip()
        network = safe_get(r, "network", "").strip()
        network_short = safe_get(r, "network_short", "").strip()
        league_name = safe_get(r, "league_name", "").strip()
        league_abbr = safe_get(r, "league_abbr", "").strip()
        packages = safe_get(r, "packages", "").strip()
        event_type = safe_get(r, "event_type", "").strip()
        language = safe_get(r, "language", "").strip()

        # Skip entries with invalid timestamps
        if not start or not stop:
            continue

        # PATCHED: Deduplication check
        key = (cid, start, stop, title)
        if key in seen:
            duplicates_skipped += 1
            continue
        seen.add(key)

        # Write programme tag
        f.write(
            f'  <programme channel="{escape(cid)}" start="{escape(start)}" stop="{escape(stop)}">\n'
        )
        f.write(f"    <title>{escape(title)}</title>\n")

        # Add enhanced metadata for events
        if kind == "event":
            # ENHANCED DESCRIPTION - Build engaging content from all available parts
            desc_parts = []

            # Start with league/competition for context (avoid duplication)
            if league_name and league_name != sport:
                desc_parts.append(league_name)
            elif league_abbr and league_abbr != sport:
                desc_parts.append(league_abbr)
            elif sport:
                # If we don't have league, use sport
                desc_parts.append(sport)

            # Build engaging matchup/event description - ALWAYS include title
            event_desc = None

            # Check if summary is actually useful or just a duplicate
            useful_summary = (
                summary
                and summary not in [league_name, league_abbr, sport, sport_abbr]
                and len(summary) > 20  # Real summaries are descriptive sentences
            )

            if useful_summary:
                # Use summary directly if it's actually descriptive
                event_desc = summary
            elif subtitle and subtitle != title:
                # Subtitle often has good context - combine with title
                event_desc = f"{title} - {subtitle}"
            else:
                # Always fall back to title (the matchup/event name)
                # BUT: if title is same as league or sport, skip it to avoid duplication
                if title and title not in [league_name, league_abbr, sport, sport_abbr]:
                    event_desc = title
                # If title is a duplicate of league/sport, we'll skip the desc entirely

            # Add network/broadcast info for extra context
            network_info = network or network_short

            # Assemble the final description with style
            if event_desc:
                if desc_parts and network_info:
                    # Full package: "NCAA Football: SMU vs. Boston College (ACCN)"
                    final_desc = (
                        f"{' • '.join(desc_parts)}: {event_desc} ({network_info})"
                    )
                elif desc_parts:
                    # League + event: "NCAA Football: SMU vs. Boston College"
                    final_desc = f"{' • '.join(desc_parts)}: {event_desc}"
                elif network_info:
                    # Just the event with network: "SMU vs. Boston College (ACCN)"
                    final_desc = f"{event_desc} ({network_info})"
                else:
                    # Bare minimum: just the title
                    final_desc = event_desc

                f.write(f"    <desc>{escape(final_desc)}</desc>\n")
            elif desc_parts:
                # Fallback: just show what we have
                f.write(f"    <desc>{escape(' • '.join(desc_parts))}</desc>\n")

            # SUB-TITLE (episode info like "Week 10", "Round 2", etc.)
            if subtitle and subtitle != title:
                f.write(f"    <sub-title>{escape(subtitle)}</sub-title>\n")

            # CATEGORIES - Build comprehensive category tree
            f.write("    <category>Sports</category>\n")

            # Sport category (use full name if available, otherwise abbreviation)
            if sport:
                f.write(f"    <category>{escape(sport)}</category>\n")
            elif sport_abbr:
                f.write(f"    <category>{escape(sport_abbr)}</category>\n")

            # League/Competition category
            if league_name:
                f.write(f"    <category>{escape(league_name)}</category>\n")
            elif league_abbr:
                f.write(f"    <category>{escape(league_abbr)}</category>\n")

            # Network category
            if network:
                f.write(f"    <category>{escape(network)}</category>\n")
            elif network_short:
                f.write(f"    <category>{escape(network_short)}</category>\n")

            # Generic event categories
            f.write("    <category>Sports Event</category>\n")
            f.write("    <category>Live</category>\n")

            # Package indicator (ESPN+, ESPN3, etc.)
            if packages:
                # Handle JSON array or comma-separated
                try:
                    import json

                    pkg_list = json.loads(packages)
                    for pkg in pkg_list:
                        f.write(f"    <category>{escape(pkg)}</category>\n")
                except Exception:
                    # Not JSON, treat as plain text
                    if packages not in ["null", "None", ""]:
                        f.write(f"    <category>{escape(packages)}</category>\n")

            # Event type (LIVE, REPLAY only - skip UPCOMING)
            if event_type and event_type.upper() in ["LIVE", "REPLAY"]:
                f.write(f"    <category>{escape(event_type)}</category>\n")

            f.write("    <category>ESPNCC4C</category>\n")

            # ICON/IMAGE - Thumbnail from ESPN
            if image and image.startswith("http"):
                f.write(f'    <icon src="{escape(image)}" />\n')

            # URL - Virtual channel resolver
            url = f"{DEFAULT_RESOLVER}/vc/{cid}"
            f.write(f"    <url>{escape(url)}</url>\n")

            # LIVE tag for live events
            if event_type and event_type.upper() == "LIVE":
                f.write("    <live>1</live>\n")

            # LANGUAGE tag (ISO 639 format)
            if language:
                f.write(f"    <language>{escape(language)}</language>\n")

        f.write("  </programme>\n")

    if duplicates_skipped > 0:
        print(
            f"[xmltv] Skipped {duplicates_skipped} duplicate programme entries",
            file=sys.stderr,
        )


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

        print(f"[xmltv] plan_id={pid}, fetched {len(rows)} raw rows")
        print(f"[xmltv] generating EPG for {len(channels)} channels")

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n')
            f.write(f'<tv generator-info-name="{GENERATOR}">\n')

            # Channels first (authoritative)
            write_channels(f, channels)

            # Programmes (with deduplication)
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
