#!/usr/bin/env python3
"""
xmltv_from_plan.py - Enhanced with fruitdeeplinks-style formatting

Generate an XMLTV EPG from the ESPN4CC4C virtual-channel plan.

Enhanced features:
- Title format: "Sport: League - Matchup" (e.g., "Women's College Basketball: Wake Forest vs Stanford")
- Description format: "Sport - (League) - Matchup - Available on Network"
  (e.g., "Basketball - (Women's College Basketball) - Wake Forest vs Stanford - Available on ACCNX")
"""

import argparse
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Any
import sys
import xml.etree.ElementTree as ET


@dataclass
class ChannelRow:
    id: int
    chno: int
    name: str
    group_name: Optional[str]


@dataclass
class ProgrammeRow:
    channel_id: int
    start_utc: str
    end_utc: str
    is_placeholder: int
    placeholder_reason: Optional[str]
    kind: str
    event_id: Optional[str]
    title: Optional[str]
    subtitle: Optional[str]
    sport: Optional[str]
    summary: Optional[str]
    image: Optional[str]
    network: Optional[str]
    network_short: Optional[str]
    league_name: Optional[str]
    league_abbr: Optional[str]
    packages: Optional[str]
    event_type: Optional[str]
    language: Optional[str]
    is_reair: Optional[int]
    content_kind: Optional[str]
    has_competition: Optional[int]
    feed_name: Optional[str]
    feed_type: Optional[str]


def get_latest_plan_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM plan_run ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        raise SystemExit("No rows in plan_run — did you run build_plan?")
    return int(row[0])


def fetch_channels_for_plan(conn: sqlite3.Connection, plan_id: int) -> List[ChannelRow]:
    sql = """
    SELECT DISTINCT
        c.id         AS id,
        c.chno       AS chno,
        c.name       AS name,
        c.group_name AS group_name
    FROM plan_slot ps
    JOIN channel c ON c.id = ps.channel_id
    WHERE ps.plan_id = ?
    ORDER BY c.chno, c.id
    """
    rows = conn.execute(sql, (plan_id,)).fetchall()
    return [
        ChannelRow(
            id=row["id"],
            chno=row["chno"],
            name=row["name"],
            group_name=row["group_name"],
        )
        for row in rows
    ]


def fetch_programmes_for_plan(conn: sqlite3.Connection, plan_id: int) -> List[ProgrammeRow]:
    sql = """
    SELECT
        ps.channel_id          AS channel_id,
        ps.start_utc           AS start_utc,
        ps.end_utc             AS end_utc,
        ps.is_placeholder      AS is_placeholder,
        ps.placeholder_reason  AS placeholder_reason,
        ps.kind                AS kind,
        e.id                   AS event_id,
        e.title                AS title,
        e.subtitle             AS subtitle,
        e.sport                AS sport,
        e.summary              AS summary,
        e.image                AS image,
        e.network              AS network,
        e.network_short        AS network_short,
        e.league_name          AS league_name,
        e.league_abbr          AS league_abbr,
        e.packages             AS packages,
        e.event_type           AS event_type,
        e.language             AS language,
        e.is_reair             AS is_reair,
        e.content_kind         AS content_kind,
        e.has_competition      AS has_competition,
        e.feed_name            AS feed_name,
        e.feed_type            AS feed_type
    FROM plan_slot ps
    LEFT JOIN events e ON e.id = ps.event_id
    WHERE ps.plan_id = ?
    ORDER BY ps.start_utc, ps.channel_id, ps.id
    """
    rows = conn.execute(sql, (plan_id,)).fetchall()
    programmes: List[ProgrammeRow] = []
    for r in rows:
        programmes.append(
            ProgrammeRow(
                channel_id=r["channel_id"],
                start_utc=r["start_utc"],
                end_utc=r["end_utc"],
                is_placeholder=r["is_placeholder"],
                placeholder_reason=r["placeholder_reason"],
                kind=r["kind"],
                event_id=r["event_id"],
                title=r["title"],
                subtitle=r["subtitle"],
                sport=r["sport"],
                summary=r["summary"],
                image=r["image"],
                network=r["network"],
                network_short=r["network_short"],
                league_name=r["league_name"],
                league_abbr=r["league_abbr"],
                packages=r["packages"],
                event_type=r["event_type"],
                language=r["language"],
                is_reair=r["is_reair"],
                content_kind=r["content_kind"],
                has_competition=r["has_competition"],
                feed_name=r["feed_name"],
                feed_type=r["feed_type"],
            )
        )
    return programmes


def parse_iso_utc(s: str) -> datetime:
    """Parse ISO8601 timestamps."""
    if not s:
        raise ValueError("Empty datetime string")
    s2 = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s2)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def xmltv_time(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M%S %z")


def coerce_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    if isinstance(val, int):
        return val
    try:
        return int(val)
    except Exception:
        return None


def is_live_event(p: ProgrammeRow) -> bool:
    flag = coerce_int(p.is_reair)
    if flag is None:
        if p.is_placeholder:
            return False
        return True
    return flag == 0


def uniq(seq: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in seq:
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def build_channel_elements(tv: ET.Element, channels: List[ChannelRow]) -> None:
    for ch in channels:
        ch_el = ET.SubElement(tv, "channel", id=str(ch.id))
        name_el = ET.SubElement(ch_el, "display-name")
        name_el.text = ch.name

        chno_el = ET.SubElement(ch_el, "display-name")
        chno_el.text = str(ch.chno)

        if ch.group_name:
            grp_el = ET.SubElement(ch_el, "display-name")
            grp_el.text = ch.group_name


def build_programme_elements(
    tv: ET.Element,
    programmes: List[ProgrammeRow],
) -> None:
    for p in programmes:
        try:
            start_dt = parse_iso_utc(p.start_utc)
            end_dt = parse_iso_utc(p.end_utc)
        except Exception as exc:
            print(f"[xmltv] WARNING: bad datetime for event {p.event_id}: {exc}", file=sys.stderr)
            continue

        attrs = {
            "start": xmltv_time(start_dt),
            "stop": xmltv_time(end_dt),
            "channel": str(p.channel_id),
        }
        prog_el = ET.SubElement(tv, "programme", **attrs)

        is_placeholder = bool(p.is_placeholder) or (p.kind and p.kind.lower() != "event")

        if is_placeholder or not p.event_id:
            # Placeholder
            title_el = ET.SubElement(prog_el, "title")
            title_el.text = "Standby"

            desc_el = ET.SubElement(prog_el, "desc")
            desc_el.text = "Standby — no live event"

            cats: List[str] = []

        else:
            # Real event - build fruitdeeplinks-style title and description
            raw_title = p.title or "Untitled Event"
            sport = p.sport or ""
            league = p.league_name or ""
            network = p.network or "ESPN+"
            
            # Build title in format: "Sport: League - Matchup"
            # Example: "Women's College Basketball: Wake Forest vs Stanford"
            title_parts = []
            if sport:
                title_parts.append(sport)
            if league and league != sport:
                # Don't duplicate if league name contains sport name
                if sport.lower() not in league.lower():
                    title_parts.append(league)
            
            if title_parts:
                title_text = f"{' - '.join(title_parts)}: {raw_title}"
            else:
                title_text = raw_title
            
            title_el = ET.SubElement(prog_el, "title")
            title_el.text = title_text

            # Add subtitle if present
            if p.subtitle:
                sub_el = ET.SubElement(prog_el, "sub-title")
                sub_el.text = p.subtitle

            # Build description in format: "Sport - (League) - Matchup - Available on Network"
            # Example: "Basketball - (Women's College Basketball) - Wake Forest vs Stanford - Available on ACCNX"
            desc_parts = []
            
            # First part: Sport
            if sport:
                desc_parts.append(sport)
            
            # Second part: (League) in parentheses if different from sport
            if league and league != sport:
                # Only add league in parens if it's substantively different from sport
                if sport.lower() not in league.lower() or len(league) > len(sport) + 5:
                    desc_parts.append(f"({league})")
            
            # Third part: The actual matchup/event
            desc_parts.append(raw_title)
            
            # Fourth part: Available on Network
            desc_parts.append(f"Available on {network}")
            
            desc_text = " - ".join(desc_parts)
            
            # Add feed name as additional context if present
            if p.feed_name and p.feed_name.strip():
                desc_text += f" • {p.feed_name}"
            
            # If ESPN provided a summary, append it on a new line
            if p.summary and p.summary.strip():
                desc_text += f"\n\n{p.summary.strip()}"
            
            desc_el = ET.SubElement(prog_el, "desc")
            desc_el.text = desc_text

            # Categories — comprehensive ESPN metadata tagging
            live = is_live_event(p)
            kind = (getattr(p, "content_kind", None) or "").strip().lower()

            if not kind:
                has_comp = coerce_int(getattr(p, "has_competition", None))
                
                if has_comp == 1:
                    kind = "sports_event"
                elif (p.sport or p.league_name):
                    title_lower = (p.title or "").lower()
                    sport_lower = (p.sport or "").lower()
                    
                    has_vs = " vs. " in title_lower or " vs " in title_lower
                    has_at = " @ " in title_lower
                    
                    sport_event_keywords = {
                        "tennis": ["court", "championship", "semifinal", "quarterfinal", "final", "round"],
                        "golf": ["round", "tournament", "championship"],
                        "racing": ["practice", "qualifying", "race", "grand prix"],
                        "motorsports": ["practice", "qualifying", "race", "grand prix"],
                    }
                    has_sport_pattern = False
                    if sport_lower in sport_event_keywords:
                        has_sport_pattern = any(keyword in title_lower for keyword in sport_event_keywords[sport_lower])
                    
                    show_keywords = [
                        "sportscenter", "postgame", "countdown", "tonight", "kickoff",
                        "pregame", "in 60", "read & react", "fantasy focus", "get up",
                        "first take", "pardon", "highly questionable", "around the horn"
                    ]
                    is_show = any(keyword in title_lower for keyword in show_keywords)
                    
                    if (has_vs or has_at or has_sport_pattern) and not is_show:
                        kind = "sports_event"
                    elif is_show:
                        kind = "sports_show"

            cats_raw: List[str] = []

            if kind in ("sports_event", "sports_show"):
                cats_raw.append("Sports")

            if p.sport:
                cats_raw.append(p.sport)

            if p.league_name:
                cats_raw.append(p.league_name)

            packages_set = set()
            if p.packages:
                import json
                try:
                    pkg_list = json.loads(p.packages)
                    for pkg in pkg_list:
                        if pkg:
                            normalized = pkg.replace("_", " ").replace(" PLUS", "+")
                            packages_set.add(normalized)
                            cats_raw.append(normalized)
                except:
                    pass

            if p.network and p.network not in packages_set:
                cats_raw.append(p.network)

            if kind == "sports_event":
                cats_raw.append("Sports Event")
            elif kind == "sports_show":
                cats_raw.append("Sports Talk")

            if p.event_type:
                et = p.event_type.strip().upper()
                if et and et not in ("UPCOMING", "LIVE"):
                    cats_raw.append(et)

            if p.language and p.language.lower() not in ("en", "eng", "english"):
                cats_raw.append(p.language.upper())

            cats_raw.append("ESPN4CC4C")

            cats = [c for c in uniq(cats_raw) if c]
            
            for cat in cats:
                cat_el = ET.SubElement(prog_el, "category")
                cat_el.text = cat
            
            if p.image:
                ET.SubElement(prog_el, "icon", src=p.image)

            if p.event_id:
                url_el = ET.SubElement(prog_el, "url")
                url_el.text = f"videos://espn-plus/event?eventID={p.event_id}"

            if live:
                live_el = ET.SubElement(prog_el, "live")
                live_el.text = "1"


def build_xmltv_tree(channels: List[ChannelRow], programmes: List[ProgrammeRow]) -> ET.ElementTree:
    tv = ET.Element("tv")
    tv.set("generator-info-name", "ESPN4CC4C")
    tv.set("source-info-name", "ESPN+ virtual channels")

    build_channel_elements(tv, channels)
    build_programme_elements(tv, programmes)

    return ET.ElementTree(tv)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate XMLTV EPG from virtual-channel plan.")
    parser.add_argument("--db", required=True, help="Path to eplus_vc.sqlite3")
    parser.add_argument("--out", required=False, help="Output XMLTV file (defaults to stdout)")
    args = parser.parse_args(argv)

    db_path = args.db
    out_path = args.out

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row

        plan_id = get_latest_plan_id(conn)
        print(f"[xmltv] Using plan_id={plan_id}", file=sys.stderr)

        channels = fetch_channels_for_plan(conn, plan_id)
        programmes = fetch_programmes_for_plan(conn, plan_id)

    tree = build_xmltv_tree(channels, programmes)

    if out_path:
        tree.write(out_path, encoding="utf-8", xml_declaration=True)
        print(f"[xmltv] out={out_path}", file=sys.stderr)
    else:
        tree.write(sys.stdout, encoding="unicode")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
