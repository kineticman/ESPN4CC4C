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
import argparse, os, sqlite3, time, json, hashlib
from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional
import requests, urllib3
from config import (
    WATCH_API_BASE as CFG_WATCH_API_BASE,
    WATCH_API_KEY as CFG_WATCH_API_KEY,
    WATCH_FEATURES as CFG_WATCH_FEATURES,
    WATCH_DEFAULT_REGION as CFG_WATCH_DEFAULT_REGION,
    WATCH_DEFAULT_TZ as CFG_WATCH_DEFAULT_TZ,
    WATCH_DEFAULT_DEVICE as CFG_WATCH_DEFAULT_DEVICE,
    WATCH_VERIFY_SSL as CFG_WATCH_VERIFY_SSL,
)


API_BASE   = CFG_WATCH_API_BASE
API_KEY    = CFG_WATCH_API_KEY
FEATURES   = CFG_WATCH_FEATURES
REGION     = os.getenv('WATCH_API_REGION', CFG_WATCH_DEFAULT_REGION).upper()
TZ_DEFAULT = os.getenv('WATCH_API_TZ', CFG_WATCH_DEFAULT_TZ)
DEVICE_S   = os.getenv('WATCH_API_DEVICE', CFG_WATCH_DEFAULT_DEVICE).lower()
VERIFY_SSL = os.getenv('WATCH_API_VERIFY_SSL', CFG_WATCH_VERIFY_SSL).strip().lower() not in ('0','false','no','off')

if not VERIFY_SSL:
    try: urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception: pass

DEVICE_MAP = {"desktop":"DESKTOP","web":"DESKTOP","mobile":"MOBILE","tv":"CONNECTED_TV","ctv":"CONNECTED_TV"}
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
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS events(
      id TEXT PRIMARY KEY,
      start_utc TEXT NOT NULL,
      stop_utc  TEXT NOT NULL,
      title     TEXT,
      sport     TEXT,
      subtitle  TEXT,
      summary   TEXT,
      image     TEXT
    );
    CREATE TABLE IF NOT EXISTS feeds(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      url TEXT,
      is_primary INTEGER NOT NULL DEFAULT 1
    );
    """)

def upsert_event(conn: sqlite3.Connection, row: Dict[str, Any]):
    cols = ("id","start_utc","stop_utc","title","sport","subtitle","summary","image")
    vals = [row.get(k) for k in cols]
    conn.execute(f"""
    INSERT INTO events({",".join(cols)}) VALUES(?,?,?,?,?,?,?,?)
    ON CONFLICT(id) DO UPDATE SET
      start_utc=excluded.start_utc,
      stop_utc=excluded.stop_utc,
      title=COALESCE(excluded.title,events.title),
      sport=COALESCE(excluded.sport,events.sport),
      subtitle=COALESCE(excluded.subtitle,events.subtitle),
      summary=COALESCE(excluded.summary,events.summary),
      image=COALESCE(excluded.image,events.image)
    """, vals)

def replace_feeds(conn: sqlite3.Connection, event_id: str, urls: List[str]):
    conn.execute("DELETE FROM feeds WHERE event_id=?", (event_id,))
    for i, u in enumerate(urls):
        if not u: continue
        conn.execute("INSERT INTO feeds(event_id,url,is_primary) VALUES(?,?,?)",
                     (event_id, u, 1 if i == 0 else 0))

def post_airings(day_iso: str, tz_str: str, limit: int = 2000) -> List[Dict[str, Any]]:
    s = requests.Session(); s.verify = VERIFY_SSL
    params = {"apiKey": API_KEY, "features": FEATURES}
    payload = {
        "query": GQL_QUERY,
        "variables": {"countryCode":REGION, "deviceType":DEVICE, "tz":tz_str, "day":day_iso, "limit":limit},
        "operationName": "Airings",
    }
    for attempt in range(1, 5):
        try:
            r = s.post(API_BASE, params=params, headers=HEADERS, json=payload, timeout=20)
            if r.status_code >= 400:
                snippet = (r.text or "")[:800].replace("\n"," ")
                print(f"[watch-graph] HTTP {r.status_code} body={snippet}")
                r.raise_for_status()
            data = r.json()
            air = (data.get("data") or {}).get("airings") or []
            if not isinstance(air, list):
                raise RuntimeError("unexpected JSON: airings not list")
            return air
        except Exception:
            if attempt >= 4: raise
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
    conn = connect(args.db); ensure_schema(conn)

    total = 0
    with conn:
        for d in range(args.days):
            day_iso = (start_day + timedelta(days=d)).strftime("%Y-%m-%d")
            airings = post_airings(day_iso, args.tz)
            for a in airings:
                title = a.get("shortName") or a.get("name")
                sport = (a.get("sport") or {}).get("name")
                start = a.get("startDateTime"); stop = a.get("endDateTime")
                base_id = str(a.get("id") or a.get("airingId") or a.get("simulcastAiringId") or title or "evt")
                if not start or not stop: continue
                eid = stable_event_id("espn-watch", base_id)
                upsert_event(conn, {
                    "id": eid, "start_utc": start, "stop_utc": stop,
                    "title": title, "sport": sport, "subtitle": None,
                    "summary": (a.get("league") or {}).get("name"), "image": None
                })
                replace_feeds(conn, eid, [espn_player_url(a)])
                total += 1
    print(f"Ingested {total} airings into {args.db}")

if __name__ == "__main__":
    main()
