\
    Param(
      [string]$Port = $env:PORT
    )

    $ErrorActionPreference = "Stop"

    function Need($cmd) {
      if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "[FATAL] Missing command: $cmd"
      }
    }

    Need "docker"
    # Compose v2 check (best-effort)
    try { docker compose version | Out-Null } catch { throw "[FATAL] Docker Compose v2 not available." }

    # Always run from script folder
    $SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location $SCRIPT_DIR

    if (-not (Test-Path "./Dockerfile")) { throw "[FATAL] Dockerfile not found in $PWD" }
    if (-not (Test-Path "./docker-compose.yml")) { throw "[FATAL] docker-compose.yml not found in $PWD" }

    # Load .env into process env (shallow)
    if (Test-Path ".env") {
      Get-Content .env | ForEach-Object {
        if ($_ -match '^\s*#') { return }
        if ($_ -match '^\s*$') { return }
        $kv = $_ -split '=',2
        if ($kv.Length -eq 2) { [Environment]::SetEnvironmentVariable($kv[0], $kv[1]) }
      }
    }

    $PORT = if ($env:PORT) { $env:PORT } else { "8094" }
    $TZ   = if ($env:TZ)   { $env:TZ } else { "America/New_York" }
    $VC_BASE = if ($env:VC_RESOLVER_BASE_URL) { $env:VC_RESOLVER_BASE_URL } else { "http://127.0.0.1:$PORT" }

    Write-Host "== docker compose: build =="
    docker compose build --pull | Out-Null

    Write-Host "== docker compose: up =="
    docker compose up -d | Out-Null

    Write-Host "== readiness wait on $VC_BASE/health =="
    $ok = $false
    foreach ($i in 1..90) {
      try {
        Invoke-WebRequest -UseBasicParsing -Uri "$VC_BASE/health" -TimeoutSec 2 | Out-Null
        $ok = $true
        break
      } catch {
        Start-Sleep -Seconds 1
      }
    }
    if (-not $ok) { Write-Warning "Resolver health not confirmed yet; continuing." }

    Write-Host "== first run: DB ensure + migrate (inside container) =="
    docker compose exec -T espn4cc bash -lc @'
      set -e
      : "${DB:=/app/data/eplus_vc.sqlite3}"
      : "${TZ:=America/New_York}"
      mkdir -p /app/data /app/out /app/logs
      [ -f "$DB" ] || : > "$DB"
      if [ -x /app/bin/db_migrate.py ]; then
        python3 /app/bin/db_migrate.py --db "$DB" || true
      fi
'@

    Write-Host "== first run: generate plan + epg/m3u (inline) =="
    docker compose exec -T espn4cc bash -lc @'
      set -e
      DB="${DB:-/app/data/eplus_vc.sqlite3}"
      TZ="${TZ:-America/New_York}"
      VALID_HOURS="${VALID_HOURS:-72}"
      MIN_GAP_MINS="${MIN_GAP_MINS:-30}"
      ALIGN="${ALIGN:-30}"
      LANES="${LANES:-40}"
      VC_RESOLVER_BASE_URL="${VC_RESOLVER_BASE_URL:-http://127.0.0.1:8094}"
      CC_HOST="${CC_HOST:-127.0.0.1}"
      CC_PORT="${CC_PORT:-5589}"
      cnt=$(sqlite3 "$DB" "SELECT COUNT(*) FROM events;" 2>/dev/null || echo 0)
      if [ "$cnt" -eq 0 ]; then
        python3 /app/bin/ingest_watch_graph_all_to_db.py --db "$DB" --days 3 --tz "$TZ" || true
      fi
      python3 /app/bin/build_plan.py --db "$DB" --valid-hours "$VALID_HOURS" --min-gap-mins "$MIN_GAP_MINS" --align "$ALIGN" --lanes "$LANES" --tz "$TZ" || true
      python3 /app/bin/xmltv_from_plan.py --db "$DB" --out /app/out/epg.xml || true
      python3 /app/bin/m3u_from_plan.py   --db "$DB" --out /app/out/playlist.m3u --resolver-base "$VC_RESOLVER_BASE_URL" --cc-host "$CC_HOST" --cc-port "$CC_PORT" || true
'@

    # --- Install in-container auto-refresh via cron.d ---
    Write-Host "== installing in-container auto-refresh (cron) =="
    $cron = @'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Every 3 hours between 09:00–23:00 (minute 7) with jitter & lock
7 9-23/3 * * * root bash -lc '"'"'sleep $((RANDOM % 60)); flock -n /tmp/espn4cc.lock bash -lc "/app/bin/refresh_in_container.sh >> /app/logs/cron.log 2>&1"'"'"'

# Overnight catch-up once at 03:17
17 3 * * * root bash -lc '"'"'flock -n /tmp/espn4cc.lock bash -lc "/app/bin/refresh_in_container.sh >> /app/logs/cron.log 2>&1"'"'"'
'@

    $cronB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($cron))
    docker compose exec -T espn4cc sh -lc "echo $cronB64 | base64 -d > /etc/cron.d/espn4cc && chmod 644 /etc/cron.d/espn4cc && pkill -HUP cron || true && mkdir -p /app/logs && : > /app/logs/cron.log && chmod 666 /app/logs/cron.log"

    Write-Host "== summary =="
    try {
      $epgCount = (Invoke-WebRequest -UseBasicParsing -Uri "$VC_BASE/out/epg.xml").Content.Split([Environment]::NewLine) | Where-Object { $_ -like '*<programme*' } | Measure-Object | Select-Object -ExpandProperty Count
    } catch { $epgCount = 0 }
    Write-Host ("XMLTV programmes: {0}" -f $epgCount)
    Write-Host "Health : $VC_BASE/health"
    Write-Host "XMLTV  : $VC_BASE/out/epg.xml"
    Write-Host "M3U    : $VC_BASE/out/playlist.m3u"
    Write-Host "Cron   : docker exec -it espn4cc sh -lc 'tail -f /app/logs/cron.log'"
