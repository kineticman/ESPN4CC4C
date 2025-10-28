#!/usr/bin/env bash
# ESPN4CC4C - backup (safe Option A): brief downtime, reliable
set -Eeuo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${1:-$HOME/archive/backups}"
TS="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$DEST"

echo "== Stopping stack =="
cd "$PROJ"
docker compose down || true

# Clean SQLite backup while stopped (if present)
if command -v sqlite3 >/dev/null 2>&1 && [[ -f "$PROJ/data/eplus_vc.sqlite3" ]]; then
  echo "== SQLite .backup =="
  sqlite3 "$PROJ/data/eplus_vc.sqlite3" ".backup '$PROJ/data/eplus_vc_${TS}.sqlite3'"
fi

echo "== Archiving project folder =="
OUT="$DEST/ESPN4CC4C_${TS}.tar.gz"
tar --exclude-vcs -czf "$OUT" -C "$PROJ" .

echo "== Bringing stack back up =="
docker compose up -d

echo "== Backup complete =="
ls -lh "$OUT"
sha256sum "$OUT" || shasum -a 256 "$OUT" || true
