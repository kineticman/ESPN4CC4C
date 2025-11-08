# ESPN4CC4C Windows bootstrap: build, run, first plan, and install in-container auto-refresh
# Requires Docker Desktop (Linux engine). Runs entirely from repo root.
$ErrorActionPreference = "Stop"

function Need($cmd) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    throw "[FATAL] Missing command: $cmd"
  }
}

Need docker
# Check Docker Compose v2 (docker compose ...)
try { docker compose version | Out-Null } catch { throw "[FATAL] Docker Compose v2 not available." }

# --- Repo root ---
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

if (-not (Test-Path ".\Dockerfile"))        { throw "[FATAL] Dockerfile not found in $PWD" }
if (-not (Test-Path ".\docker-compose.yml")){ throw "[FATAL] docker-compose.yml not found in $PWD" }

# --- Read .env for a few values (best-effort) ---
$EnvPath = ".\.env"
$envMap = @{}
if (Test-Path $EnvPath) {
  Get-Content $EnvPath | ForEach-Object {
    if ($_ -match '^\s*#') { return }
    if ($_ -match '^\s*$') { return }
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
      $k = $Matches[1]; $v = $Matches[2]
      if ($v -match '^\s*["''](.*)["'']\s*$') { $v = $Matches[1] }
      $envMap[$k] = $v
    }
  }
}

function GetOrDefault($k, $def) {
  if ($envMap.ContainsKey($k) -and $envMap[$k]) { return $envMap[$k] }
  return $def
}

$PORT = GetOrDefault "PORT" "8094"
$TZ   = GetOrDefault "TZ"   "America/New_York"
$VC_RESOLVER_BASE_URL = GetOrDefault "VC_RESOLVER_BASE_URL" ("http://127.0.0.1:{0}" -f $PORT)
$CC_HOST = GetOrDefault "CC_HOST" "127.0.0.1"
$CC_PORT = GetOrDefault "CC_PORT" "5589"

# --- Build & up ---
Write-Host "== docker compose: build =="
docker compose build --pull

Write-Host "== docker compose: up =="
docker compose up -d

# --- Readiness wait ---
Write-Host ("== readiness wait on {0}/health ==" -f $VC_RESOLVER_BASE_URL)
for ($i=0; $i -lt 90; $i++) {
  try {
    Invoke-WebRequest -UseBasicParsing -Uri ("{0}/health" -f $VC_RESOLVER_BASE_URL) -TimeoutSec 5 | Out-Null
    Write-Host "Resolver healthy."
    break
  } catch {
    Start-Sleep -Seconds 1
  }
}

# --- First run: DB ensure + migrate ---
Write-Host "== first run: DB ensure + migrate (inside container) =="
docker compose exec -T espn4cc bash -lc @'
  set -e
  : "${DB:=/app/data/eplus_vc.sqlite3}"
  : "${TZ:=America/New_York}"
  mkdir -p /app/data /app/out /app/logs
  [ -f "$DB" ] || : > "$DB"
  if [ -x /app/bin/db_migrate.py ]; then
    python3 /app/bin/db_migrate.py --db "$DB" --lanes "${LANES:-40}" || true
  fi
'@

# --- First run: generate plan + epg/m3u ---
Write-Host "== first run: generate plan + epg/m3u (inline) =="
docker compose exec -T espn4cc bash -lc @"
  set -e
  DB="\${DB:-/app/data/eplus_vc.sqlite3}"
  TZ="\${TZ:-America/New_York}"
  VALID_HOURS="\${VALID_HOURS:-72}"
  MIN_GAP_MINS="\${MIN_GAP_MINS:-30}"
  ALIGN="\${ALIGN:-30}"
  LANES="\${LANES:-40}"
  VC_RESOLVER_BASE_URL="\${VC_RESOLVER_BASE_URL:-http://127.0.0.1:8094}"
  CC_HOST="\${CC_HOST:-127.0.0.1}"
  CC_PORT="\${CC_PORT:-5589}"

  cnt=\$(sqlite3 "\$DB" "SELECT COUNT(*) FROM events;" 2>/dev/null || echo 0)
  if [ "\$cnt" -eq 0 ]; then
    python3 /app/bin/ingest_watch_graph_all_to_db.py --db "\$DB" --days 3 --tz "\$TZ" || true
  fi

  python3 /app/bin/build_plan.py --db "\$DB" --valid-hours "\$VALID_HOURS" \
    --min-gap-mins "\$MIN_GAP_MINS" --align "\$ALIGN" --lanes "\$LANES" --tz "\$TZ" || true

  python3 /app/bin/xmltv_from_plan.py --db "\$DB" --out /app/out/epg.xml || true
  python3 /app/bin/m3u_from_plan.py   --db "\$DB" --out /app/out/playlist.m3u \
    --resolver-base "\$VC_RESOLVER_BASE_URL" --cc-host "\$CC_HOST" --cc-port "\$CC_PORT" || true
"@

# --- Install in-container auto-refresh (cron.d) ---
Write-Host "== installing in-container auto-refresh (cron) =="

$cron = @'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Every 3 hours between 09:00–23:00 (minute 7) with jitter & lock
7 9-23/3 * * * root bash -lc "sleep $((RANDOM % 60)); flock -n /tmp/espn4cc.lock bash -lc \"/app/bin/refresh_in_container.sh >> /app/logs/cron.log 2>&1\""

# Overnight catch-up once at 03:17
17 3 * * * root bash -lc "flock -n /tmp/espn4cc.lock bash -lc \"/app/bin/refresh_in_container.sh >> /app/logs/cron.log 2>&1\""
'@

# Base64 (UTF8), one line
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($cron))

docker compose exec -T espn4cc sh -lc "echo $b64 | base64 -d > /etc/cron.d/espn4cc && chmod 644 /etc/cron.d/espn4cc && mkdir -p /app/logs && : > /app/logs/cron.log && chmod 666 /app/logs/cron.log && pkill -HUP cron || true"

# --- Final tests & summary ---
Write-Host ""
Write-Host "== Re-check XMLTV (counting programmes) =="
try {
  $xml = Invoke-WebRequest -UseBasicParsing -Uri ("{0}/out/epg.xml" -f $VC_RESOLVER_BASE_URL)
  $count = ([regex]::Matches($xml.Content, "<programme")).Count
  Write-Host ("✓ {0} programmes found" -f $count)
} catch {
  Write-Host "0"
}

Write-Host ""
Write-Host "== Re-check M3U (preview first 600 chars) =="
try {
  $m3u = Invoke-WebRequest -UseBasicParsing -Uri ("{0}/out/playlist.m3u" -f $VC_RESOLVER_BASE_URL)
  $s = $m3u.Content
  if ($s.Length -gt 600) { $s.Substring(0,600) } else { $s }
} catch {
  Write-Host "[warn] Could not fetch M3U"
}

Write-Host ""
Write-Host "========================================"
Write-Host ("✓ DONE")
Write-Host ("Health : {0}/health" -f $VC_RESOLVER_BASE_URL)
Write-Host ("XMLTV  : {0}/out/epg.xml" -f $VC_RESOLVER_BASE_URL)
Write-Host ("M3U    : {0}/out/playlist.m3u" -f $VC_RESOLVER_BASE_URL)
Write-Host ("Cron   : docker exec -it espn4cc sh -lc 'tail -f /app/logs/cron.log'")
Write-Host "========================================"
