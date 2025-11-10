#!/usr/bin/env python3
# file: bin/db_migrate.py
# Purpose: make the DB safe for v3 builder/ingester
# - events.id -> TEXT PRIMARY KEY
# - feeds.event_id -> TEXT (FK -> events.id)
# - event_lane(event_id TEXT PRIMARY KEY, channel_id INTEGER, ...)
# - ensure plan_run + plan_slot shapes
# - seed channels if empty

import argparse
import contextlib
import json
import os
import sqlite3
import sys

# ---------- helpers ----------


def cols(cur, t):
    try:
        return [r[1] for r in cur.execute(f"PRAGMA table_info({t})")]
    except sqlite3.OperationalError:
        return []


def coltypes(cur, t):
    out = {}
    try:
        for cid, name, ctype, notnull, dflt, pk in cur.execute(
            f"PRAGMA table_info({t})"
        ):
            out[name] = (
                ctype.upper() if ctype else "",
                int(notnull or 0),
                dflt,
                int(pk or 0),
            )
    except sqlite3.OperationalError:
        pass
    return out


def has_unique_on(cur, table, column):
    try:
        for row in cur.execute(f"PRAGMA index_list('{table}')").fetchall():
            # row: (seq, name, unique, origin, partial)
            name = row[1]
            unique = int(row[2] or 0)
            if unique:
                icols = [r[2] for r in cur.execute(f"PRAGMA index_info('{name}')")]
                if column in icols:
                    return name
    except sqlite3.OperationalError:
        pass
    return None


def ensure_table(cur, ddl):
    cur.executescript(ddl)


def ensure_columns(cur, table, want_cols):
    have = set(cols(cur, table))
    for colname, colddl in want_cols:
        if colname not in have:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {colddl}")


def seed_channels(cur, lanes: int):
    """Seed channels if table empty (ESPN+ conventions).
    chno starts at 20010; names 'ESPN+ EPlus <n>'; group 'ESPN+ VC'."""
    try:
        c = cur.execute("SELECT COUNT(*) FROM channel").fetchone()[0]
    except Exception:
        c = 0
    if c:
        return 0
    start_chno = 20010
    rows = []
    for i in range(1, lanes + 1):
        chno = start_chno + (i - 1)
        name = f"ESPN+ EPlus {i}"
        rows.append((chno, name, "ESPN+ VC", 1))
    cur.executemany(
        "INSERT INTO channel(chno,name,group_name,active) VALUES(?,?,?,?)", rows
    )
    return len(rows)


def drop_unique_index_on_checksum(cur):
    name = has_unique_on(cur, "plan_run", "checksum")
    if name:
        cur.execute(f'DROP INDEX IF EXISTS "{name}"')


def ensure_created_at_default(cur):
    try:
        info = cur.execute("PRAGMA table_info(plan_run)").fetchall()
    except sqlite3.OperationalError:
        info = []
    dflt = None
    for cid, name, ctype, notnull, default, pk in info:
        if name == "created_at":
            dflt = default
            break
    if dflt:
        return
    # Rebuild to ensure default exists
    cur.executescript(
        """
    BEGIN;
    CREATE TABLE IF NOT EXISTS plan_run(
      id               INTEGER PRIMARY KEY AUTOINCREMENT,
      checksum         TEXT,
      starts_at        INTEGER,
      ends_at          INTEGER,
      note             TEXT,
      created_at       INTEGER NOT NULL DEFAULT (strftime('%s','now')),
      generated_at_utc INTEGER,
      valid_from_utc   INTEGER,
      valid_to_utc     INTEGER,
      source_version   TEXT
    );
    CREATE TABLE IF NOT EXISTS _plan_run_migrate AS SELECT * FROM plan_run WHERE 0;
    INSERT INTO _plan_run_migrate SELECT * FROM plan_run;
    DROP TABLE plan_run;
    CREATE TABLE plan_run(
      id               INTEGER PRIMARY KEY AUTOINCREMENT,
      checksum         TEXT,
      starts_at        INTEGER,
      ends_at          INTEGER,
      note             TEXT,
      created_at       INTEGER NOT NULL DEFAULT (strftime('%s','now')),
      generated_at_utc INTEGER,
      valid_from_utc   INTEGER,
      valid_to_utc     INTEGER,
      source_version   TEXT
    );
    INSERT INTO plan_run(id,checksum,starts_at,ends_at,note,created_at,generated_at_utc,valid_from_utc,valid_to_utc,source_version)  # noqa: E501
    SELECT id,checksum,starts_at,ends_at,note,COALESCE(created_at, strftime('%s','now')),generated_at_utc,valid_from_utc,valid_to_utc,source_version  # noqa: E501
    FROM _plan_run_migrate;
    DROP TABLE _plan_run_migrate;
    COMMIT;
    """
    )


# ---------- canonical DDL ----------

DDL_CHANNEL = """
CREATE TABLE IF NOT EXISTS channel(
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  chno       INTEGER NOT NULL UNIQUE,
  name       TEXT    NOT NULL,
  group_name TEXT,
  active     INTEGER NOT NULL DEFAULT 1
);
"""

# v3 events: TEXT PK + TEXT times
DDL_EVENTS_V3 = """
CREATE TABLE IF NOT EXISTS _events_v3(
  id        TEXT PRIMARY KEY,
  start_utc TEXT NOT NULL,
  stop_utc  TEXT NOT NULL,
  title     TEXT,
  sport     TEXT,
  subtitle  TEXT,
  summary   TEXT,
  image     TEXT
);
"""

DDL_FEEDS = """
CREATE TABLE IF NOT EXISTS feeds(
  id         INTEGER PRIMARY KEY,
  event_id   TEXT NOT NULL,
  url        TEXT,
  is_primary INTEGER,
  FOREIGN KEY(event_id) REFERENCES events(id)
);
"""

# feeds v3 temp (used by migration)
DDL_FEEDS_V3 = """
CREATE TABLE IF NOT EXISTS _feeds_v3(
  id         INTEGER PRIMARY KEY,
  event_id   TEXT NOT NULL,
  url        TEXT,
  is_primary INTEGER,
  FOREIGN KEY(event_id) REFERENCES events(id)
);
"""

DDL_PLAN_RUN = """
CREATE TABLE IF NOT EXISTS plan_run(
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  checksum         TEXT,
  starts_at        INTEGER,
  ends_at          INTEGER,
  note             TEXT,
  created_at       INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  generated_at_utc INTEGER,
  valid_from_utc   INTEGER,
  valid_to_utc     INTEGER,
  source_version   TEXT
);
"""

DDL_PLAN_SLOT = """
CREATE TABLE IF NOT EXISTS plan_slot(
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id              INTEGER NOT NULL,
  lane                 INTEGER,
  chno                 INTEGER,
  channel_id           INTEGER,
  event_id             TEXT,
  title                TEXT,
  starts_at            INTEGER,
  ends_at              INTEGER,
  start_utc            TEXT,
  end_utc              TEXT,
  is_placeholder       INTEGER NOT NULL DEFAULT 0,
  placeholder_reason   TEXT,
  feed_url             TEXT,
  preferred_feed_id    INTEGER,
  preferred_feed_url   TEXT,
  kind                 TEXT,
  created_at           INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

DDL_PLAN_META = """
CREATE TABLE IF NOT EXISTS plan_meta(
  key   TEXT PRIMARY KEY,
  value TEXT
);
"""

# v3 sticky map
DDL_EVENT_LANE_V3 = """
CREATE TABLE IF NOT EXISTS _event_lane_v3(
  event_id       TEXT PRIMARY KEY,
  channel_id     INTEGER,
  pinned_at_utc  INTEGER,
  last_seen_utc  INTEGER
);
"""

# ---------- migration routines ----------


def migrate_events_to_v3(cur):
    ct = coltypes(cur, "events")
    need = False
    if not ct:
        need = True
    else:
        id_ok = "id" in ct and ct["id"][0] == "TEXT" and ct["id"][3] == 1
        start_ok = "start_utc" in ct and ct["start_utc"][0] == "TEXT"
        stop_ok = "stop_utc" in ct and ct["stop_utc"][0] == "TEXT"
        need = not (id_ok and start_ok and stop_ok)
    if not need:
        return False

    ensure_table(cur, DDL_EVENTS_V3)
    if ct:
        # copy legacy -> v3, casting to TEXT; ignore dup ids
        cur.executescript(
            """
        INSERT OR IGNORE INTO _events_v3(id,start_utc,stop_utc,title,sport,subtitle,summary,image)
        SELECT CAST(id AS TEXT),
               CAST(start_utc AS TEXT),
               CAST(stop_utc  AS TEXT),
               title, sport, subtitle, summary, image
        FROM events;
        """
        )
        cur.execute("DROP TABLE IF EXISTS events")
    cur.execute("ALTER TABLE _events_v3 RENAME TO events")
    return True


def migrate_feeds_to_v3(cur):
    """
    Ensure feeds.event_id is TEXT (FK -> events.id TEXT).
    Rebuilds table if event_id type != TEXT.
    """
    ct = coltypes(cur, "feeds")
    if not ct:
        # table missing; base-table creator will make it; nothing to migrate
        return False

    eid_ok = "event_id" in ct and (ct["event_id"][0] in ("TEXT", ""))
    if eid_ok:
        return False

    # Rebuild feeds with TEXT event_id; copy/CAST existing rows
    ensure_table(cur, DDL_FEEDS_V3)
    cur.executescript(
        """
    INSERT OR IGNORE INTO _feeds_v3(id, event_id, url, is_primary)
      SELECT id, CAST(event_id AS TEXT), url, is_primary
      FROM feeds;
    DROP TABLE IF EXISTS feeds;
    ALTER TABLE _feeds_v3 RENAME TO feeds;
    """
    )
    return True


def migrate_event_lane_to_v3(cur):
    ct = coltypes(cur, "event_lane")
    need = False
    if not ct:
        need = True
    else:
        eid_ok = (
            "event_id" in ct
            and ct["event_id"][0] in ("TEXT", "")
            and ct["event_id"][3] == 1
        )
        ch_ok = "channel_id" in ct and ct["channel_id"][0] in ("INTEGER", "")
        need = not (eid_ok and ch_ok)
    if not need:
        return False

    ensure_table(cur, DDL_EVENT_LANE_V3)

    if ct:
        # 1) Insert rows that don't exist yet; prefer existing channel_id, else legacy lane, else 1
        have_lane = "lane" in ct
        cur.executescript(
            f"""
        INSERT OR IGNORE INTO _event_lane_v3(event_id,channel_id,pinned_at_utc,last_seen_utc)
        SELECT CAST(event_id AS TEXT),
               COALESCE(channel_id, {'lane' if have_lane else 'NULL'}, 1),
               pinned_at_utc, last_seen_utc
        FROM event_lane;
        """
        )
        # 2) For rows that already exist, update channel_id if source has a better value
        if have_lane:
            cur.executescript(
                """
            UPDATE _event_lane_v3
            SET channel_id = COALESCE(
                (SELECT channel_id FROM event_lane WHERE CAST(event_lane.event_id AS TEXT)=_event_lane_v3.event_id),
                (SELECT lane       FROM event_lane WHERE CAST(event_lane.event_id AS TEXT)=_event_lane_v3.event_id),
                _event_lane_v3.channel_id
            );
            UPDATE _event_lane_v3
            SET pinned_at_utc = COALESCE(
                (SELECT pinned_at_utc FROM event_lane WHERE CAST(event_lane.event_id AS TEXT)=_event_lane_v3.event_id),
                _event_lane_v3.pinned_at_utc
            ),
                last_seen_utc = COALESCE(
                (SELECT last_seen_utc FROM event_lane WHERE CAST(event_lane.event_id AS TEXT)=_event_lane_v3.event_id),
                _event_lane_v3.last_seen_utc
            );
            """
            )
    # swap tables
    cur.execute("DROP TABLE IF EXISTS event_lane")
    cur.execute("ALTER TABLE _event_lane_v3 RENAME TO event_lane")
    return True


def migrate_filter_columns(cur):
    """
    Add filtering columns introduced in v2.2.0 for content filtering.
    These columns store network, league, sport, and package metadata
    from the ESPN Watch API to enable user-configurable filtering.
    """
    ct = coltypes(cur, "events")
    if not ct:
        # events table doesn't exist yet; will be created by migrate_events_to_v3
        return False

    # Define new columns for filtering
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
    }

    # Check which columns are missing
    added = 0
    for col, col_type in new_cols.items():
        if col not in ct:
            print(f"[db_migrate] Adding column: events.{col} {col_type}")
            cur.execute(f"ALTER TABLE events ADD COLUMN {col} {col_type}")
            added += 1

    if added > 0:
        print(f"[db_migrate] Added {added} filtering column(s) to events table")

    return added > 0


def ensure_base_tables(cur):
    ensure_table(cur, DDL_CHANNEL)
    ensure_table(cur, DDL_FEEDS)
    ensure_table(cur, DDL_PLAN_RUN)
    ensure_table(cur, DDL_PLAN_SLOT)
    ensure_table(cur, DDL_PLAN_META)

    # ensure plan_slot has all desired columns
    want_cols = [
        ("lane", "lane INTEGER"),
        ("chno", "chno INTEGER"),
        ("channel_id", "channel_id INTEGER"),
        ("event_id", "event_id TEXT"),
        ("title", "title TEXT"),
        ("starts_at", "starts_at INTEGER"),
        ("ends_at", "ends_at INTEGER"),
        ("start_utc", "start_utc TEXT"),
        ("end_utc", "end_utc TEXT"),
        ("is_placeholder", "is_placeholder INTEGER NOT NULL DEFAULT 0"),
        ("placeholder_reason", "placeholder_reason TEXT"),
        ("feed_url", "feed_url TEXT"),
        ("preferred_feed_id", "preferred_feed_id INTEGER"),
        ("preferred_feed_url", "preferred_feed_url TEXT"),
        ("kind", "kind TEXT"),
        ("created_at", "created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))"),
    ]
    ensure_columns(cur, "plan_slot", want_cols)


# ---------- main ----------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--lanes", type=int, default=int(os.getenv("LANES", "40")))
    ap.add_argument("--drop-unique-plan-run", action="store_true")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.db), exist_ok=True)
    con = sqlite3.connect(args.db)
    cur = con.cursor()

    with contextlib.ExitStack():
        cur.execute("PRAGMA foreign_keys=OFF")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")

        # 1) ensure core tables
        ensure_base_tables(cur)

        # 2) canonicalize v3 tables (transaction)
        changed = {}
        cur.execute("BEGIN")
        try:
            changed["events_rebuilt"] = migrate_events_to_v3(cur)
            changed["feeds_rebuilt"] = migrate_feeds_to_v3(cur)
            changed["event_lane_rebuilt"] = migrate_event_lane_to_v3(cur)
            changed["filter_columns_added"] = migrate_filter_columns(cur)
            con.commit()
        except Exception:
            con.rollback()
            raise

        # 3) plan_run guards
        if args.drop_unique_plan_run:
            drop_unique_index_on_checksum(cur)
        ensure_created_at_default(cur)

        # 4) seed channels if empty
        seeded = seed_channels(cur, args.lanes)
        con.commit()

    out = {
        "db": args.db,
        "seeded_channels": seeded,
        "lanes": args.lanes,
        "tables": [
            r[0]
            for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ],
        "changed": changed,
        "events_schema": coltypes(cur, "events"),
        "feeds_schema": coltypes(cur, "feeds"),
        "event_lane_schema": coltypes(cur, "event_lane"),
    }
    print(json.dumps(out, indent=2))
    con.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
