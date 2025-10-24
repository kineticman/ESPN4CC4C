PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS channel(
  id TEXT PRIMARY KEY,
  chno INTEGER NOT NULL,
  name TEXT NOT NULL,
  group_name TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS plan_run(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  generated_at_utc TEXT NOT NULL,
  valid_from_utc   TEXT NOT NULL,
  valid_to_utc     TEXT NOT NULL,
  source_version   TEXT,
  note             TEXT,
  checksum         TEXT
);

CREATE TABLE IF NOT EXISTS plan_slot(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id INTEGER NOT NULL REFERENCES plan_run(id) ON DELETE CASCADE,
  channel_id TEXT NOT NULL REFERENCES channel(id),
  event_id TEXT REFERENCES events(id),
  start_utc TEXT NOT NULL,
  end_utc   TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('event','placeholder')),
  placeholder_reason TEXT,
  preferred_feed_id TEXT,
  UNIQUE(plan_id, channel_id, start_utc)
);

CREATE TABLE IF NOT EXISTS plan_meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_plan_slot_lookup
  ON plan_slot(plan_id, channel_id, start_utc, end_utc);
