#!/usr/bin/env python3
import argparse, sqlite3, os, sys, json

DDL = {
"channel": """
CREATE TABLE IF NOT EXISTS channel(
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  chno       INTEGER NOT NULL UNIQUE,
  name       TEXT    NOT NULL,
  group_name TEXT,
  active     INTEGER NOT NULL DEFAULT 1
);
""",
"events": """
CREATE TABLE IF NOT EXISTS events(
  id        INTEGER PRIMARY KEY,
  start_utc TEXT NOT NULL,
  stop_utc  TEXT NOT NULL,
  title     TEXT,
  sport     TEXT,
  subtitle  TEXT,
  summary   TEXT,
  image     TEXT
);
""",
"feeds": """
CREATE TABLE IF NOT EXISTS feeds(
  id         INTEGER PRIMARY KEY,
  event_id   INTEGER NOT NULL,
  url        TEXT,
  is_primary INTEGER,
  FOREIGN KEY(event_id) REFERENCES events(id)
);
""",
"plan_run": """
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
""",
"plan_slot": """
CREATE TABLE IF NOT EXISTS plan_slot(
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id              INTEGER NOT NULL,
  lane                 INTEGER,
  chno                 INTEGER,
  channel_id           INTEGER,
  event_id             INTEGER,
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
""",
"plan_meta": """
CREATE TABLE IF NOT EXISTS plan_meta(
  key   TEXT PRIMARY KEY,
  value TEXT
);
""",
"event_lane": """
CREATE TABLE IF NOT EXISTS event_lane(
  event_id      INTEGER,
  channel_id    INTEGER,
  pinned_at_utc INTEGER,
  last_seen_utc INTEGER
);
"""
}

def cols(cur, t):
    return [r[1] for r in cur.execute(f"PRAGMA table_info({t})")]

def ensure_table(cur, name, ddl):
    cur.executescript(ddl)

def ensure_columns(cur, table, want_cols):
    have = set(cols(cur, table))
    for colname, colddl in want_cols:
        if colname not in have:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {colddl}")

def seed_channels(cur, lanes:int):
    c = cur.execute("SELECT COUNT(*) FROM channel").fetchone()[0]
    if c: return 0
    rows = [(i, f"eplus{i:02d}", "ESPN+ VC", 1) for i in range(1, lanes+1)]
    cur.executemany("INSERT INTO channel(chno,name,group_name,active) VALUES(?,?,?,?)", rows)
    return len(rows)

def drop_unique_index_on_checksum(cur):
    # Defensive: if any unique/partial index exists on plan_run.checksum, drop it
    for row in cur.execute("PRAGMA index_list('plan_run')").fetchall():
        # row = (seq, name, unique, origin, partial)
        name = row[1]; unique = row[2]
        if unique:
            # check indexed columns
            cols = [r[2] for r in cur.execute(f"PRAGMA index_info('{name}')")]
            if "checksum" in cols:
                cur.execute(f'DROP INDEX IF EXISTS "{name}"')

def ensure_created_at_default(cur):
    # Make sure plan_run.created_at has a default
    info = cur.execute("PRAGMA table_info(plan_run)").fetchall()
    dflt = None
    for cid, name, ctype, notnull, default, pk in info:
        if name == "created_at":
            dflt = default
            break
    if not dflt:
        # rebuild table minimally to set default (rare on fresh installs, but keep here)
        cur.executescript("""
        BEGIN;
        CREATE TABLE plan_run_new(
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
        INSERT INTO plan_run_new(id,checksum,starts_at,ends_at,note,created_at,generated_at_utc,valid_from_utc,valid_to_utc,source_version)
        SELECT id,checksum,starts_at,ends_at,note,
               COALESCE(created_at, strftime('%s','now')),
               generated_at_utc,valid_from_utc,valid_to_utc,source_version
        FROM plan_run;
        DROP TABLE plan_run;
        ALTER TABLE plan_run_new RENAME TO plan_run;
        COMMIT;
        """)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--lanes", type=int, default=int(os.getenv("LANES", "40")))
    ap.add_argument("--drop-unique-plan-run", action="store_true")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.db), exist_ok=True)
    con = sqlite3.connect(args.db)
    cur = con.cursor()

    # 1) core tables
    for t, ddl in DDL.items():
        ensure_table(cur, t, ddl)

    # 2) ensure plan_slot has all desired columns (safe if already present)
    want_cols = [
        ("lane",               "lane INTEGER"),
        ("chno",               "chno INTEGER"),
        ("channel_id",         "channel_id INTEGER"),
        ("event_id",           "event_id INTEGER"),
        ("title",              "title TEXT"),
        ("starts_at",          "starts_at INTEGER"),
        ("ends_at",            "ends_at INTEGER"),
        ("start_utc",          "start_utc TEXT"),
        ("end_utc",            "end_utc TEXT"),
        ("is_placeholder",     "is_placeholder INTEGER NOT NULL DEFAULT 0"),
        ("placeholder_reason", "placeholder_reason TEXT"),
        ("feed_url",           "feed_url TEXT"),
        ("preferred_feed_id",  "preferred_feed_id INTEGER"),
        ("preferred_feed_url", "preferred_feed_url TEXT"),
        ("kind",               "kind TEXT"),
        ("created_at",         "created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))"),
    ]
    ensure_columns(cur, "plan_slot", want_cols)

    # 3) plan_run guards
    if args.drop_unique_plan_run:
        drop_unique_index_on_checksum(cur)
    ensure_created_at_default(cur)

    # 4) seed channels if empty
    seeded = seed_channels(cur, args.lanes)

    # 5) ensure plan_meta exists
    ensure_table(cur, "plan_meta", DDL["plan_meta"])

    con.commit()
    out = {
        "db": args.db,
        "seeded_channels": seeded,
        "lanes": args.lanes,
        "tables": [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()],
    }
    print(json.dumps(out, indent=2))
    con.close()

if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as e:
        raise
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
