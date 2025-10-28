BEGIN;

-- events: TEXT PK + ISO8601 TEXT times
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
INSERT INTO _events_v3(id,start_utc,stop_utc,title,sport,subtitle,summary,image)
SELECT CAST(id AS TEXT), CAST(start_utc AS TEXT), CAST(stop_utc AS TEXT),
       title, sport, subtitle, summary, image
FROM events
ON CONFLICT(id) DO NOTHING;
DROP TABLE IF EXISTS events;
ALTER TABLE _events_v3 RENAME TO events;

-- event_lane: supports ON CONFLICT(event_id)
CREATE TABLE IF NOT EXISTS _event_lane_v3(
  event_id       TEXT PRIMARY KEY,
  channel_id     INTEGER NOT NULL,
  pinned_at_utc  INTEGER,
  last_seen_utc  INTEGER
);
INSERT INTO _event_lane_v3(event_id,channel_id,pinned_at_utc,last_seen_utc)
SELECT CAST(event_id AS TEXT),
       COALESCE(channel_id, lane),
       pinned_at_utc, last_seen_utc
FROM event_lane
ON CONFLICT(event_id) DO UPDATE SET
  channel_id    = excluded.channel_id,
  pinned_at_utc = COALESCE(excluded.pinned_at_utc, _event_lane_v3.pinned_at_utc),
  last_seen_utc = COALESCE(excluded.last_seen_utc, _event_lane_v3.last_seen_utc);
DROP TABLE IF EXISTS event_lane;
ALTER TABLE _event_lane_v3 RENAME TO event_lane;

COMMIT;

