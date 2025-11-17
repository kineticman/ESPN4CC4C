#!/usr/bin/env python3
"""
ESPN Watch Graph -> v2 DB (events + feeds), matching your PowerShell/v1 request shape.

- URL: https://watch.graph.api.espn.com/api?apiKey=...&features=pbov7
- POST JSON: { query, variables, operationName:"Airings" }
- Vars: countryCode=US, deviceType=DESKTOP, tz=America/New_York, day=YYYY-MM-DD, limit=2000
- Headers: Accept/Origin/Referer/User-Agent like a browser
- Primary feed = ESPN player page https://www.espn.com/watch/player/_/id/<id|airingId|simulcastAiringId>

Env toggles:
  WATCH_API_VERIFY_SSL=0          # skip SSL verify (like v1 option)
  WATCH_API_DEVICE=desktop|mobile|tv (maps to DESKTOP|MOBILE|CONNECTED_TV)
  WATCH_API_TZ=America/New_York
  WATCH_API_REGION=US
"""
import argparse
import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
import urllib3

from config import WATCH_API_BASE as CFG_WATCH_API_BASE
from config import WATCH_API_KEY as CFG_WATCH_API_KEY
from config import WATCH_DEFAULT_DEVICE as CFG_WATCH_DEFAULT_DEVICE
from config import WATCH_DEFAULT_REGION as CFG_WATCH_DEFAULT_REGION
from config import WATCH_DEFAULT_TZ as CFG_WATCH_DEFAULT_TZ
from config import WATCH_FEATURES as CFG_WATCH_FEATURES
from config import WATCH_VERIFY_SSL as CFG_WATCH_VERIFY_SSL

API_BASE = CFG_WATCH_API_BASE
API_KEY = CFG_WATCH_API_KEY
FEATURES = CFG_WATCH_FEATURES
REGION = os.getenv("WATCH_API_REGION", CFG_WATCH_DEFAULT_REGION).upper()
TZ_DEFAULT = os.getenv("WATCH_API_TZ", CFG_WATCH_DEFAULT_TZ)
DEVICE_S = os.getenv("WATCH_API_DEVICE", CFG_WATCH_DEFAULT_DEVICE).lower()
VERIFY_SSL = str(
    os.getenv("WATCH_API_VERIFY_SSL", str(CFG_WATCH_VERIFY_SSL))
).strip().lower() not in ("0", "false", "no", "off")

if not VERIFY_SSL:
    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass

DEVICE_MAP = {
    "desktop": "DESKTOP",
    "web": "DESKTOP",
    "mobile": "MOBILE",
    "tv": "CONNECTED_TV",
    "ctv": "CONNECTED_TV",
}
DEVICE = DEVICE_MAP.get(DEVICE_S, "DESKTOP")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Origin": "https://www.espn.com",
    "Referer": "https://www.espn.com/",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

GQL_QUERY = """
query Airings(
  $countryCode: String!, $deviceType: DeviceType!, $tz: String!,
  $day: String!, $limit: Int
) {
  airings(
    countryCode: $countryCode, deviceType: $deviceType, tz: $tz,
    day: $day, limit: $limit
  ) {
    id airingId simulcastAiringId name shortName type
    startDateTime endDateTime
    network { id name shortName }
    league  { id name abbreviation }
    sport   { id name abbreviation }
    packages { name }
    image { url }
    language
    isReAir
  }
}
""".strip()


def stable_event_id(source: str, external_id: str) -> str:
    return f"{source}:{external_id}:{hashlib.sha256(f'{source}:{external_id}'.encode()).hexdigest()[:32]}"


def espn_player_url(row: Dict[str, Any]) -> Optional[str]:
    pid = row.get("id") or row.get("airingId") or row.get("simulcastAiringId")
    return f"https://www.espn.com/watch/player/_/id/{pid}" if pid else None


def connect(dbpath: str) -> sqlite3.Connection:
    conn = sqlite3.connect(dbpath)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def ensure_schema(conn: sqlite3.Connection):
    conn.executescript(
        """
    CREATE TABLE IF NOT EXISTS events(
      id TEXT PRIMARY KEY,
      start_utc TEXT NOT NULL,
      stop_utc  TEXT NOT NULL,
      title     TEXT,
      sport     TEXT,
      subtitle  TEXT,
      summary   TEXT,
      image     TEXT,
      network TEXT,
      network_id TEXT,
      network_short TEXT,
      league_name TEXT,
      league_id TEXT,
      league_abbr TEXT,
      sport_id TEXT,
      sport_abbr TEXT,
      packages TEXT,
      event_type TEXT,
      airing_id TEXT,
      simulcast_airing_id TEXT,
      language TEXT,
      is_reair INTEGER
    );
    CREATE TABLE IF NOT EXISTS feeds(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      url TEXT,
      is_primary INTEGER NOT NULL DEFAULT 1
    );
    """
    )


def migrate_schema(conn: sqlite3.Connection):
    """Add new columns to existing databases"""
    cursor = conn.cursor()

    # Get existing columns from events table
    cursor.execute("PRAGMA table_info(events)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    # Define new columns that should exist
    new_cols = {
        "network": "TEXT",
        "network_id": "TEXT",
        "network_short": "TEXT",
        "league_name": "TEXT",
        "league_id": "TEXT",
        "league_abbr": "TEXT",
        "sport_id": "TEXT",
        "sport_abbr": "TEXT",
        "packages": "TEXT",
        "event_type": "TEXT",
        "airing_id": "TEXT",
        "simulcast_airing_id": "TEXT",
        "language": "TEXT",
        "is_reair": "INTEGER",
    }

    # Add missing columns
    added = 0
    for col, col_type in new_cols.items():
        if col not in existing_cols:
            print(f"[migration] Adding column: {col} {col_type}")
            conn.execute(f"ALTER TABLE events ADD COLUMN {col} {col_type}")
            added += 1

    if added > 0:
        print(f"[migration] Added {added} new column(s) to events table")
        conn.commit()


def upsert_event(conn: sqlite3.Connection, row: Dict[str, Any]):
    cols = (
        "id",
        "start_utc",
        "stop_utc",
        "title",
        "sport",
        "subtitle",
        "summary",
        "image",
        "network",
        "network_id",
        "network_short",
        "league_name",
        "league_id",
        "league_abbr",
        "sport_id",
        "sport_abbr",
        "packages",
        "event_type",
        "airing_id",
        "simulcast_airing_id",
        "language",
        "is_reair",
    )
    vals = [row.get(k) for k in cols]
    placeholders = ",".join(["?"] * len(cols))
    updates = ",".join(
        [f"{c}=COALESCE(excluded.{c},events.{c})" for c in cols[1:]]
    )  # skip id
    conn.execute(
        f"""
    INSERT INTO events({",".join(cols)}) VALUES({placeholders})
    ON CONFLICT(id) DO UPDATE SET {updates}
    """,
        vals,
    )


def replace_feeds(conn: sqlite3.Connection, event_id: str, urls: List[str]):
    conn.execute("DELETE FROM feeds WHERE event_id=?", (event_id,))
    for i, u in enumerate(urls):
        if not u:
            continue
        conn.execute(
            "INSERT INTO feeds(event_id,url,is_primary) VALUES(?,?,?)",
            (event_id, u, 1 if i == 0 else 0),
        )


def post_airings(day_iso: str, tz_str: str, limit: int = 2000) -> List[Dict[str, Any]]:
    s = requests.Session()
    s.verify = VERIFY_SSL
    params = {"apiKey": API_KEY, "features": FEATURES}
    payload = {
        "query": GQL_QUERY,
        "variables": {
            "countryCode": REGION,
            "deviceType": DEVICE,
            "tz": tz_str,
            "day": day_iso,
            "limit": limit,
        },
        "operationName": "Airings",
    }
    for attempt in range(1, 5):
        try:
            r = s.post(
                API_BASE, params=params, headers=HEADERS, json=payload, timeout=20
            )
            if r.status_code >= 400:
                snippet = (r.text or "")[:800].replace("\n", " ")
                print(f"[watch-graph] HTTP {r.status_code} body={snippet}")
                r.raise_for_status()
            data = r.json()
            air = (data.get("data") or {}).get("airings") or []
            if not isinstance(air, list):
                raise RuntimeError("unexpected JSON: airings not list")
            return air
        except Exception:
            if attempt >= 4:
                raise
            time.sleep(0.5 * (2 ** (attempt - 1)))
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--tz", default=TZ_DEFAULT)
    args = ap.parse_args()

    tz = ZoneInfo(args.tz)
    start_day = datetime.now(tz).date()
    conn = connect(args.db)
    ensure_schema(conn)
    migrate_schema(conn)  # Auto-upgrade existing databases

    total = 0
    with conn:
        for d in range(args.days):
            day_iso = (start_day + timedelta(days=d)).strftime("%Y-%m-%d")
            airings = post_airings(day_iso, args.tz)
            for a in airings:
                # Basic event info
                title = a.get("shortName") or a.get("name")
                start = a.get("startDateTime")
                stop = a.get("endDateTime")
                base_id = str(
                    a.get("id")
                    or a.get("airingId")
                    or a.get("simulcastAiringId")
                    or title
                    or "evt"
                )
                if not start or not stop:
                    continue

                # Extract nested objects
                sport_obj = a.get("sport") or {}
                league_obj = a.get("league") or {}
                network_obj = a.get("network") or {}
                packages_list = a.get("packages") or []

                # Convert packages to JSON string
                packages_str = (
                    json.dumps([p.get("name") for p in packages_list if p.get("name")])
                    if packages_list
                    else None
                )

                # Extract image URL from nested image object
                image_obj = a.get("image") or {}
                image_url = (
                    image_obj.get("url") if isinstance(image_obj, dict) else None
                )

                # Get language (e.g., "en", "es", etc.)
                language = a.get("language")

                # Get Re-Air flag - convert boolean to integer for SQLite
                is_reair = 1 if a.get("isReAir") else 0

                eid = stable_event_id("espn-watch", base_id)
                upsert_event(
                    conn,
                    {
                        "id": eid,
                        "start_utc": start,
                        "stop_utc": stop,
                        "title": title,
                        "sport": sport_obj.get("name"),
                        "subtitle": None,
                        "summary": None,  # Don't use league name as summary - it's redundant
                        "image": image_url,
                        "network": network_obj.get("name"),
                        "network_id": network_obj.get("id"),
                        "network_short": network_obj.get("shortName"),
                        "league_name": league_obj.get("name"),
                        "league_id": league_obj.get("id"),
                        "league_abbr": league_obj.get("abbreviation"),
                        "sport_id": sport_obj.get("id"),
                        "sport_abbr": sport_obj.get("abbreviation"),
                        "packages": packages_str,
                        "event_type": a.get("type"),
                        "airing_id": a.get("airingId"),
                        "simulcast_airing_id": a.get("simulcastAiringId"),
                        "language": language,
                        "is_reair": is_reair,
                    },
                )
                replace_feeds(conn, eid, [espn_player_url(a)])
                total += 1
    print(f"Ingested {total} airings into {args.db}")


if __name__ == "__main__":
    main()
