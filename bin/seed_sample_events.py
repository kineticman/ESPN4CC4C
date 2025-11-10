#!/usr/bin/env python3
import argparse
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/eplus_vc.sqlite3")
    ap.add_argument(
        "--channels",
        type=int,
        default=4,
        help="how many lanes to seed starting from eplus1",
    )
    ap.add_argument(
        "--start-offset", type=int, default=5, help="minutes from now to start"
    )
    ap.add_argument("--duration", type=int, default=45, help="minutes per event")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")

    # Ensure minimal schema exists
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
      image     TEXT
    );
    CREATE TABLE IF NOT EXISTS feeds(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      url TEXT,
      is_primary INTEGER NOT NULL DEFAULT 1
    );
    """
    )

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = now + timedelta(minutes=args.start_offset)
    stop = start + timedelta(minutes=args.duration)

    rows = []
    with conn:
        for i in range(1, args.channels + 1):
            eid = str(uuid.uuid4())
            title = f"EPlus Demo {i}"
            sport = "Demo"
            conn.execute(
                "INSERT OR IGNORE INTO events(id,start_utc,stop_utc,title,sport,subtitle,summary,image) VALUES(?,?,?,?,?,?,?,?)",
                (
                    eid,
                    start.isoformat(),
                    stop.isoformat(),
                    title,
                    sport,
                    "Seeded",
                    "Sample seeded event",
                    None,
                ),
            )
            # dummy feed per lane (replace with real later)
            feed = f"http://example.com/stream/eplus{i}.m3u8"
            conn.execute(
                "INSERT INTO feeds(event_id,url,is_primary) VALUES(?,?,1)", (eid, feed)
            )
            rows.append((i, eid, feed))

    print(f"Seeded {len(rows)} events {start.isoformat()} → {stop.isoformat()}")
    for i, eid, feed in rows:
        print(f"  eplus{i}: {eid} -> {feed}")


if __name__ == "__main__":
    main()
