# v2.0.2 — 2025-10-24

**Fixes & polish**
- XMLTV: placeholder titles standardized to “Stand By”
- XMLTV: removed `only_live=1` from <url> entries; resolver decides live/slate
- XMLTV: category tagging:
  - Always adds `Sports`
  - Adds sport-specific category when present in DB
  - Adds `Live` + `Sports Event` only for real event slots (not placeholders or shows)
- Resolver: default behavior (no param) now 302s to live or slate; `?only_live=1` forces 204 when idle
- M3U: stable lane URLs (no only_live param), client never needs to change

**Ops**
- .gitignore hardened (out/, logs/, backups/, releases/, archives)
- Repo housekeeping (releases/ artifacts, backups/ DB snapshot)

