#!/usr/bin/env python3
# file: rebuildDB.py
# Purpose: Ensure/repair ESPN4CC DB schema + seed base data safely.

import argparse
import json
import sqlite3
import sys
from pathlib import Path

SCHEMA = {
    "events": """
    CREATE TABLE IF NOT EXISTS events (
        id         INTEGER PRIMARY KEY,
        start_utc  TEXT    NOT NULL,
        stop_utc   TEXT    NOT NULL,
        title      TEXT,
        sport      TEXT,
        subtitle   TEXT,
        summary    TEXT,
        image      TEXT
    );
    """,
    "feeds": """
    CREATE TABLE IF NOT EXISTS feeds (
        id         INTEGER PRIMARY KEY,
        event_id   INTEGER NOT NULL,
        url        TEXT,
        is_primary INTEGER,
        FOREIGN KEY(event_id) REFERENCES events(id)
    );
    """,
    "channel": """
    CREATE TABLE IF NOT EXISTS channel (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        chno       INTEGER NOT NULL UNIQUE,
        name       TEXT    NOT NULL,
        group_name TEXT,
        active     INTEGER NOT NULL DEFAULT 1
    );
    """,
    # NOTE: We intentionally do NOT make checksum UNIQUE here to avoid
    # repeat-build crashes when nothing changed.
    "plan_run": """
    CREATE TABLE IF NOT EXISTS plan_run (
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
    """,
    # plan_slot includes both *_utc (TEXT window strings) and *_at (INTEGER unix)
    "plan_slot": """
    CREATE TABLE IF NOT EXISTS plan_slot (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        plan_id             INTEGER NOT NULL,
        lane                INTEGER,
        chno                INTEGER,
        channel_id          INTEGER,
        event_id            INTEGER,
        title               TEXT,
        starts_at           INTEGER,
        ends_at             INTEGER,
        start_utc           TEXT,
        end_utc             TEXT,
        is_placeholder      INTEGER NOT NULL DEFAULT 0,
        placeholder_reason  TEXT,
        feed_url            TEXT,
        preferred_feed_id   INTEGER,
        preferred_feed_url  TEXT,
        kind                TEXT,
        created_at          INTEGER DEFAULT (strftime('%s','now')),
        FOREIGN KEY(plan_id)    REFERENCES plan_run(id),
        FOREIGN KEY(channel_id) REFERENCES channel(id),
        FOREIGN KEY(event_id)   REFERENCES events(id)
    );
    """,
    # Optional helper table used by sticky lanes
    "event_lane": """
    CREATE TABLE IF NOT EXISTS event_lane (
        event_id INTEGER PRIMARY KEY,
        lane     INTEGER
    );
    """,
    # Pointer to active plan id (text for flexibility)
    "plan_meta": """
    CREATE TABLE IF NOT EXISTS plan_meta (
        key   TEXT PRIMARY KEY,
        value TEXT
    );
    """,
    # Historical convenience (rarely used directly, safe to keep)
    "plan": """
    CREATE TABLE IF NOT EXISTS plan (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        starts_at INTEGER NOT NULL,
        ends_at   INTEGER NOT NULL,
        note      TEXT
    );
    """,
}

# Columns we want to guarantee exist (used for ALTER TABLE adds)
WANT_COLS = {
    "plan_run": {
        "checksum": "TEXT",
        "starts_at": "INTEGER",
        "ends_at": "INTEGER",
        "note": "TEXT",
        "created_at": "INTEGER",
        "generated_at_utc": "INTEGER",
        "valid_from_utc": "INTEGER",
        "valid_to_utc": "INTEGER",
        "source_version": "TEXT",
    },
    "plan_slot": {
        "plan_id": "INTEGER",
        "lane": "INTEGER",
        "chno": "INTEGER",
        "channel_id": "INTEGER",
        "event_id": "INTEGER",
        "title": "TEXT",
        "starts_at": "INTEGER",
        "ends_at": "INTEGER",
        "start_utc": "TEXT",
        "end_utc": "TEXT",
        "is_placeholder": "INTEGER",
        "placeholder_reason": "TEXT",
        "feed_url": "TEXT",
        "preferred_feed_id": "INTEGER",
        "preferred_feed_url": "TEXT",
        "kind": "TEXT",
        "created_at": "INTEGER",
    },
    "channel": {
        "chno": "INTEGER",
        "name": "TEXT",
        "group_name": "TEXT",
        "active": "INTEGER",
    },
}

INDEXES = [
    # Events time range
    "CREATE INDEX IF NOT EXISTS ix_events_time ON events(start_utc, stop_utc)",
    # Plan slot lookup helpers
    "CREATE INDEX IF NOT EXISTS ix_plan_slot_plan ON plan_slot(plan_id)",
    "CREATE INDEX IF NOT EXISTS ix_plan_slot_chno_time ON plan_slot(chno, starts_at, ends_at)",
]


def ensure_dir(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)


def table_exists(cur: sqlite3.Cursor, name: str) -> bool:
    try:
        cur.execute(f"SELECT 1 FROM {name} LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


def columns(cur: sqlite3.Cursor, name: str):
    return [r[1] for r in cur.execute(f"PRAGMA table_info({name})")]


def ensure_tables(cur: sqlite3.Cursor):
    # Enable WAL (safe in executescript)
    cur.executescript("PRAGMA journal_mode=WAL;")
    # Create base tables if missing
    for ddl in SCHEMA.values():
        cur.executescript(ddl)


def add_missing_columns(cur: sqlite3.Cursor, tbl: str, want: dict):
    if not want:
        return []
    existing = set(columns(cur, tbl))
    added = []
    for col, decl in want.items():
        if col not in existing:
            # SQLite allows ALTER TABLE ... ADD COLUMN <name> <type> [DEFAULT const]
            # but NOT expressions in DEFAULT. We keep it simple.
            cur.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {decl}")
            added.append(col)
    return added


def drop_unique_indexes_on_plan_run(con: sqlite3.Connection):
    cur = con.cursor()
    # PRAGMA index_list returns: seq, name, unique, origin, partial
    try:
        rows = list(cur.execute("PRAGMA index_list('plan_run')"))
    except sqlite3.OperationalError:
        return []

    dropped = []
    for row in rows:
        # row[2] is 'unique' flag in modern SQLite
        try:
            unique_flag = row[2]
            idx_name = row[1]
        except Exception:
            continue
        if unique_flag == 1:
            cur.execute(f'DROP INDEX IF EXISTS "{idx_name}"')
            dropped.append(idx_name)
    return dropped


def seed_channels(cur: sqlite3.Cursor, lanes: int = 40):
    n = cur.execute("SELECT COUNT(*) FROM channel WHERE active=1").fetchone()[0]
    if n > 0:
        return 0
    rows = [(i, f"ESPN+ {i:02d}", "ESPN+ VC", 1) for i in range(1, lanes + 1)]
    cur.executemany(
        "INSERT INTO channel (chno, name, group_name, active) VALUES (?,?,?,?)",
        rows,
    )
    return len(rows)


def ensure_plan_meta(cur: sqlite3.Cursor):
    # ensure key row exists (no value yet)
    cur.execute(
        "INSERT OR IGNORE INTO plan_meta(key, value) VALUES('active_plan_id', NULL)"
    )


def main():
    ap = argparse.ArgumentParser(description="Rebuild/repair ESPN4CC SQLite DB schema.")
    ap.add_argument(
        "--db",
        default="./data/eplus_vc.sqlite3",
        help="Path to SQLite DB (default: ./data/eplus_vc.sqlite3)",
    )
    ap.add_argument(
        "--lanes",
        type=int,
        default=40,
        help="How many ESPN+ channels to seed if empty (default: 40)",
    )
    ap.add_argument(
        "--wipe-plans",
        action="store_true",
        help="Delete all rows from plan_run/plan_slot/plan_meta before finishing (safe reset).",
    )
    ap.add_argument(
        "--drop-unique-plan-run",
        action="store_true",
        help="Drop any UNIQUE indexes on plan_run (prevents checksum duplicate errors).",
    )
    args = ap.parse_args()

    db_path = Path(args.db)
    ensure_dir(db_path)

    con = sqlite3.connect(str(db_path))
    cur = con.cursor()

    # 1) Create base tables
    ensure_tables(cur)

    # 2) Ensure required columns exist (ALTER add missing)
    added_cols = {}
    for tbl, want in WANT_COLS.items():
        if table_exists(cur, tbl):
            added = add_missing_columns(cur, tbl, want)
            if added:
                added_cols[tbl] = added

    # 3) Create helpful indexes
    for idx_sql in INDEXES:
        cur.execute(idx_sql)

    # 4) Seed channels if empty
    seeded = seed_channels(cur, args.lanes)

    # 5) Ensure plan_meta pointer exists
    ensure_plan_meta(cur)

    # 6) Optional: drop UNIQUE indexes on plan_run
    dropped_idx = []
    if args.drop_unique_plan_run:
        dropped_idx = drop_unique_indexes_on_plan_run(con)

    # 7) Optional: wipe plan data (clean slate for next build)
    wiped = False
    if args.wipe_plans:
        cur.execute("DELETE FROM plan_slot")
        cur.execute("DELETE FROM plan_run")
        cur.execute("DELETE FROM plan_meta")
        # re-create the active_plan_id key as null
        ensure_plan_meta(cur)
        wiped = True

    con.commit()

    # 8) Report
    report = {
        "db": str(db_path),
        "tables": sorted(
            [
                r[0]
                for r in cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            ]
        ),
        "channel_cols": columns(cur, "channel"),
        "plan_run_cols": columns(cur, "plan_run"),
        "plan_slot_cols": columns(cur, "plan_slot"),
        "events_cols": columns(cur, "events"),
        "feeds_cols": columns(cur, "feeds"),
        "plan_meta_cols": columns(cur, "plan_meta"),
        "event_lane_cols": columns(cur, "event_lane"),
        "added_columns": added_cols,
        "seeded_channels": seeded,
        "dropped_unique_indexes_on_plan_run": dropped_idx,
        "wiped_plans": wiped,
        "counts": {
            "channel_active": cur.execute(
                "SELECT COUNT(*) FROM channel WHERE active=1"
            ).fetchone()[0],
            "plan_run": cur.execute("SELECT COUNT(*) FROM plan_run").fetchone()[0],
            "plan_slot": cur.execute("SELECT COUNT(*) FROM plan_slot").fetchone()[0],
            "events": cur.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "feeds": cur.execute("SELECT COUNT(*) FROM feeds").fetchone()[0],
        },
    }
    print(json.dumps(report, indent=2))

    con.close()


if __name__ == "__main__":
    sys.exit(main())
