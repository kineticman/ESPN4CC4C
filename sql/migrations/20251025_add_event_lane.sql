PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS event_lane(
  event_id       TEXT PRIMARY KEY,
  channel_id     TEXT NOT NULL,
  pinned_at_utc  TEXT NOT NULL,
  last_seen_utc  TEXT NOT NULL
);
