# ESPN4CC4C Windows bootstrap (PowerShell)
# - Builds/starts container
# - Seeds DB, builds first plan
# - Installs in-container cron to auto-refresh every 3h
# Requires: Docker Desktop w/ Compose v2

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Need($cmd) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    throw "[FATAL] Missing command: $cmd"
  }
}

Need docker

# Always run from repo root
Set-Location -Path (Split-Path -Parent $MyInvocation.MyCommand.Path)

# Load .env into session (best-effort)
$envPath = Join-Path (Get-Location) '.env'
if (Test-Path $envPath) {
  Get-Content $envPath | ForEach-Object {
    if ($_ -match '^\s*#') { return }
    if ($_ -match '^\s*$') { return }
    $k,$v = $_ -split '=',2
    if ($k) { [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim()) }
  }
}

$PORT = $env:PORT; if (-not $PORT) { $PORT = '8094' }
$VC_BASE = $env:VC_RESOLVER_BASE_URL; if (-not $VC_BASE) { $VC_BASE = "http://127.0.0.1:$PORT" }

Write-Host "== docker compose: build =="
docker compose build --pull

Write-Host "== docker compose: up =="
docker compose up -d | Out-Null

Write-Host "== readiness wait on $VC_BASE/health =="
for ($i=0; $i -lt 90; $i++) {
  try {
    (Invoke-WebRequest -UseBasicParsing -Uri "$VC_BASE/health" -TimeoutSec 2) | Out-Null
    Write-Host "Resolver healthy."
    break
  } catch { Start-Sleep -Seconds 1 }
}

Write-Host "== first run: DB ensure + migrate (inside container) =="
docker exec -i espn4cc sh -lc 'set -e; : "${DB:=/app/data/eplus_vc.sqlite3}"; mkdir -p /app/data /app/out /app/logs; [ -f "$DB" ] || : > "$DB"; if [ -x /app/bin/db_migrate.py ]; then python3 /app/bin/db_migrate.py --db "$DB" || true; fi' | Out-Null

Write-Host "== first run: generate plan + epg/m3u =="
docker exec -i espn4cc sh -lc 'set -e; DB="${DB:-/app/data/eplus_vc.sqlite3}"; TZ="${TZ:-America/New_York}"; cnt=$(sqlite3 "$DB" "SELECT COUNT(*) FROM events;" 2>/dev/null || echo 0); if [ "$cnt" -eq 0 ]; then python3 /app/bin/ingest_watch_graph_all_to_db.py --db "$DB" --days 3 --tz "$TZ" || true; fi; python3 /app/bin/build_plan.py --db "$DB" --valid-hours "${VALID_HOURS:-72}" --min-gap-mins "${MIN_GAP_MINS:-30}" --align "${ALIGN:-30}" --lanes "${LANES:-40}" --tz "$TZ" || true; python3 /app/bin/xmltv_from_plan.py --db "$DB" --out /app/out/epg.xml || true; python3 /app/bin/m3u_from_plan.py --db "$DB" --out /app/out/playlist.m3u --resolver-base "${VC_RESOLVER_BASE_URL:-http://127.0.0.1:8094}" --cc-host "${CC_HOST:-127.0.0.1}" --cc-port "${CC_PORT:-5589}" || true' | Out-Null

Write-Host "== installing in-container auto-refresh (cron) =="
$cron = @"
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Every 3 hours between 09:00–23:00 (minute 7) with jitter & lock
7 9-23/3 * * * root bash -lc 'sleep $((RANDOM % 60)); flock -n /tmp/espn4cc.lock bash -lc "/app/bin/refresh_in_container.sh >> /app/logs/cron.log 2>&1"'

# Overnight catch-up once at 03:17
17 3 * * * root bash -lc 'flock -n /tmp/espn4cc.lock bash -lc "/app/bin/refresh_in_container.sh >> /app/logs/cron.log 2>&1"'
"@

# Write cron file inside container, reload cron, prep log
$bash = @"
set -e
mkdir -p /app/logs
cat >/etc/cron.d/espn4cc <<'CRON'
$cron
CRON
chmod 644 /etc/cron.d/espn4cc
pkill -HUP cron || true
: > /app/logs/cron.log
chmod 666 /app/logs/cron.log
"@

docker exec -i espn4cc sh -lc "$bash" | Out-Null
Write-Host "[ok] cron installed & reloaded."

# Summary
try {
  $prog = (Invoke-WebRequest -UseBasicParsing -Uri "$VC_BASE/out/epg.xml").Content | Select-String -Pattern '<programme' -AllMatches
  $count = $prog.Matches.Count
} catch { $count = 0 }
Write-Host ""
Write-Host "========================================"
Write-Host ("Health : {0}" -f "$VC_BASE/health")
Write-Host ("XMLTV  : {0}" -f "$VC_BASE/out/epg.xml")
Write-Host ("M3U    : {0}" -f "$VC_BASE/out/playlist.m3u")
Write-Host ("Programmes in XML: {0}" -f $count)
Write-Host "Cron log tail:"
docker exec -i espn4cc sh -lc "tail -n 60 /app/logs/cron.log || true"
Write-Host "========================================"
