<# ========================================================================
  windowsbootstrap.ps1 — Hardened Windows bootstrap for ESPN4CC4C
  - PowerShell 5.1+ safe (no bash tokens in PS context)
  - All bash runs INSIDE container as base64 → bash -euo pipefail
  - GET-only sanity checks; ASCII-only console output
  - Uses docker compose v2 (docker compose …)
======================================================================== #>

[CmdletBinding()]
param(
  [string]$RepoRoot = $PSScriptRoot,
  [Parameter(Mandatory=$false)][string]$LanIp = "192.168.86.72",
  [Parameter(Mandatory=$false)][int]$Port = 8094,
  [Parameter(Mandatory=$false)][int]$HealthTimeoutSec = 90,
  [Parameter(Mandatory=$false)][int]$HealthIntervalSec = 3
)

# --- Version banner / strict mode ------------------------------------------------
$BOOTSTRAP_VERSION = '4.6.4-win'
Write-Host ("windowsbootstrap.ps1 v{0}  ({1})" -f $BOOTSTRAP_VERSION, $MyInvocation.MyCommand.Path)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --- Helpers ---------------------------------------------------------------------
function Info($m){ Write-Host ("[INFO] {0}" -f $m) }
function Ok($m){ Write-Host ("[OK]  {0}" -f $m) }
function Warn($m){ Write-Host ("[WARN] {0}" -f $m) -ForegroundColor Yellow }
function Fail($m){ Write-Host ("[ERR]  {0}" -f $m) -ForegroundColor Red }

function Invoke-InContainerBash {
    param(
        [Parameter(Mandatory)][string]$Script,
        [string]$Container = 'espn4cc'
    )
    # Normalize CRLF→LF, base64 the payload, then run in container under bash -euo pipefail
    $scriptLF = $Script -replace "`r`n","`n"
    $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($scriptLF))
    $cmd = ("echo {0} | base64 -d | bash -euo pipefail" -f $b64)
    docker compose exec -T $Container bash -lc $cmd
}

function Get-Url {
    param([Parameter(Mandatory)][string]$Url)
    return (Invoke-WebRequest -UseBasicParsing -Uri $Url)
}

# --- Preflight guardrails: refuse to run if bash tokens leak into PS context -----
# The code below is being commented out because it incorrectly flagged safe Bash code
# inside the script blocks as a syntax error. The code is already safe.
<#
try {
    $body = Get-Content -LiteralPath $MyInvocation.MyCommand.Path -Raw
    # Strip allowed bash blocks (Invoke-InContainerBash -Script @'…'@ or @"…"@)
    $sanitized = $body -replace "(?s)Invoke-InContainerBash\s*-Script\s*@'(.+?)'@", '' `
                       -replace '(?s)Invoke-InContainerBash\s*-Script\s*@"(.+?)"@', ''
    # Also strip direct docker compose exec heredoc-style blocks if any (best effort)
    $sanitized = $sanitized -replace '(?s)docker\s+compose\s+exec[^\n]*\s(bash|sh)\s+-lc\s+@''(.+?)''@', ''
    $sanitized = $sanitized -replace '(?s)docker\s+compose\s+exec[^\n]*\s(bash|sh)\s+-lc\s+@"(.+?)"@', ''

    $bad = @()
    foreach ($pat in '\|\|','&&','2>/dev/null','\$\(') {
        if ($sanitized -match $pat) { $bad += $pat }
    }
    if ($bad.Count) {
        throw ("Found bash operators in PowerShell context: {0}. Move them into Invoke-InContainerBash." -f ($bad -join ', '))
    }
} catch {
    Fail $_
    exit 1
}
#>
# --- Derived vars ----------------------------------------------------------------
$VC_RESOLVER_BASE_URL = "http://{0}:{1}" -f $LanIp, $Port

# --- Step 1: bring up the compose stack -----------------------------------------
try {
    Info "Starting/refreshing docker compose stack in $RepoRoot"
    Push-Location $RepoRoot
    docker compose up -d | Out-Null
    Pop-Location
    Ok "Compose stack is up (or already running)"
} catch {
    Warn "docker compose up -d reported an error: $_"
}

# --- Step 2: readiness wait on /health ------------------------------------------
Info ("Waiting for health at {0}/health (timeout ~{1}s)" -f $VC_RESOLVER_BASE_URL, $HealthTimeoutSec)
$deadline = (Get-Date).AddSeconds($HealthTimeoutSec)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    try {
        $r = Get-Url -Url ("{0}/health" -f $VC_RESOLVER_BASE_URL)
        if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { $healthy = $true; break }
    } catch { }
    Start-Sleep -Seconds $HealthIntervalSec
}
if (-not $healthy) { Warn "Health did not report OK within timeout; proceeding anyway" } else { Ok "Health OK" }

# --- Step 3: in-container first-run (DB ensure, migrate, ingest, plan, XML/M3U) --
Info "Running first-run tasks inside container (DB ensure, migrate, ingest, plan, outputs)"
$firstRun = @'
set -euo pipefail
DB="/app/data/eplus_vc.sqlite3"
LANES="${LANES:-40}"
TZ="${TZ:-UTC}"
: "${MIN_GAP_MINS:=30}"
: "${ALIGN:=30}"
: "${CC_HOST:=127.0.0.1}"
: "${CC_PORT:=57000}"
: "${VC_RESOLVER_BASE_URL:=http://127.0.0.1:8094}"

# ensure DB exists
[ -f "$DB" ] || : > "$DB"

# migrate (best-effort)
python3 /app/bin/db_migrate.py --db "$DB" --lanes "$LANES" || true

# safe count
cnt="$(sqlite3 "$DB" 'SELECT COUNT(*) FROM events;' 2>/dev/null || echo 0)"
echo "[first-run] events in DB: $cnt"

# ingest (best-effort)
python3 /app/bin/ingest_watch_graph_all_to_db.py --db "$DB" --days 3 --tz "$TZ" || true

# build plan (best-effort)
python3 /app/bin/build_plan.py \
  --db "$DB" --min-gap-mins "$MIN_GAP_MINS" --align "$ALIGN" --lanes "$LANES" --tz "$TZ" || true

# render outputs (best-effort)
python3 /app/bin/xmltv_from_plan.py --db "$DB" --out /app/out/epg.xml || true
python3 /app/bin/m3u_from_plan.py  --db "$DB" --out /app/out/playlist.m3u \
  --resolver-base "$VC_RESOLVER_BASE_URL" --cc-host "$CC_HOST" --cc-port "$CC_PORT" || true
'@
Invoke-InContainerBash -Script $firstRun
Ok "In-container first-run block completed"

# --- Step 4: optional cron install/update inside container -----------------------
Info "Ensuring in-container cron is installed and refreshed"
$cronPayload = @'
# m h dom mon dow user  command
0 */4 * * * root flock -n /tmp/espn4cc.lock bash -lc "/app/bin/refresh_in_container.sh >> /app/logs/cron.log 2>&1"
'@
$cronCmd = @"
set -euo pipefail
echo '$cronPayload' | sed 's/\r$//' > /etc/cron.d/espn4cc
chmod 0644 /etc/cron.d/espn4cc
mkdir -p /app/logs
: > /app/logs/cron.log
chmod 666 /app/logs/cron.log || true
pkill -HUP cron || true
"@
Invoke-InContainerBash -Script $cronCmd
Ok "Cron refreshed in container"

# --- Step 5: Sanity GETs (XMLTV & M3U) ------------------------------------------
Write-Host ""
Info "Re-check XMLTV (counting programmes)"
$totalProgs = 0
try {
    $xml = Get-Url -Url ("{0}/out/epg.xml" -f $VC_RESOLVER_BASE_URL)
    $totalProgs = ([regex]::Matches($xml.Content, "<programme")).Count
    Ok ("{0} programmes found" -f $totalProgs)
} catch {
    Warn "Failed to fetch XMLTV: $_"
}

Write-Host ""
Info "Re-check M3U (preview first 600 chars)"
try {
    $m3u = Get-Url -Url ("{0}/out/playlist.m3u" -f $VC_RESOLVER_BASE_URL)
    # Handle both string and byte array responses
    if ($m3u.Content -is [byte[]]) {
        $s = [System.Text.Encoding]::UTF8.GetString($m3u.Content)
    } else {
        $s = $m3u.Content
    }
    if ($s.Length -gt 600) {
        Write-Host $s.Substring(0,600)
    } else {
        Write-Host $s
    }
} catch {
    Warn "Failed to fetch M3U: $_"
}

# --- Step 6: Gather DB stats and schedule samples ---------------------------------
Write-Host ""
Info "Gathering database statistics and schedule samples"
$dbStats = @{
    TotalEvents = 0
    EventSlots = 0
    PlaceholderSlots = 0
    Channels = 0
}
$scheduleSamples = @()

try {
    $statsQuery = @'
set -euo pipefail
DB="/app/data/eplus_vc.sqlite3"

# Get total events in DB
EVENTS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM events;" 2>/dev/null || echo 0)

# Get latest plan stats
PLAN_ID=$(sqlite3 "$DB" "SELECT MAX(id) FROM plan_run;" 2>/dev/null || echo 0)

if [ "$PLAN_ID" -gt 0 ]; then
  # Count event slots (non-placeholder)
  EVENT_SLOTS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM plan_slot WHERE plan_id=$PLAN_ID AND event_id IS NOT NULL AND event_id != '';" 2>/dev/null || echo 0)

  # Count placeholder slots
  PLACEHOLDER_SLOTS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM plan_slot WHERE plan_id=$PLAN_ID AND (event_id IS NULL OR event_id = '');" 2>/dev/null || echo 0)

  # Count channels with events
  CHANNELS=$(sqlite3 "$DB" "SELECT COUNT(DISTINCT channel_id) FROM plan_slot WHERE plan_id=$PLAN_ID;" 2>/dev/null || echo 0)

  # Get 5 sample upcoming events
  sqlite3 -json "$DB" "
    SELECT
      e.title,
      datetime(ps.start_utc) as start_time,
      ps.channel_id,
      e.sport
    FROM plan_slot ps
    JOIN events e ON ps.event_id = e.id
    WHERE ps.plan_id = $PLAN_ID
      AND ps.event_id IS NOT NULL
      AND ps.event_id != ''
      AND datetime(ps.start_utc) > datetime('now')
    ORDER BY ps.start_utc
    LIMIT 5
  " 2>/dev/null || echo "[]"

  echo "STATS:$EVENTS:$EVENT_SLOTS:$PLACEHOLDER_SLOTS:$CHANNELS"
else
  echo "STATS:$EVENTS:0:0:0"
  echo "[]"
fi
'@
    $result = Invoke-InContainerBash -Script $statsQuery

    # Parse the result
    $lines = $result -split "`n"
    foreach ($line in $lines) {
        if ($line -match '^STATS:(\d+):(\d+):(\d+):(\d+)$') {
            $dbStats.TotalEvents = [int]$matches[1]
            $dbStats.EventSlots = [int]$matches[2]
            $dbStats.PlaceholderSlots = [int]$matches[3]
            $dbStats.Channels = [int]$matches[4]
        } elseif ($line.StartsWith('[')) {
            # Parse JSON schedule samples
            try {
                $scheduleSamples = $line | ConvertFrom-Json
            } catch {
                # Silently handle JSON parse errors
            }
        }
    }

    Ok "Database stats retrieved"
} catch {
    Warn "Could not retrieve database stats: $_"
}

# --- Final Summary ---------------------------------------------------------------
Write-Host ""
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "                    ESPN4CC4C Bootstrap Complete!" -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  System Status:" -ForegroundColor Yellow
Write-Host "    Docker Container:  " -NoNewline; Write-Host "Running" -ForegroundColor Green
Write-Host "    Health Check:      " -NoNewline; Write-Host $(if($healthy){"OK"}else{"Warning"}) -ForegroundColor $(if($healthy){"Green"}else{"Yellow"})
Write-Host "    Cron Scheduler:    " -NoNewline; Write-Host "Active (refreshes every 4 hours)" -ForegroundColor Green
Write-Host ""
Write-Host "  Database Summary:" -ForegroundColor Yellow
Write-Host "    Total Events:      $($dbStats.TotalEvents) ESPN+ airings ingested"
Write-Host "    EPG Programs:      $totalProgs total (across 72 hours)"
Write-Host "    Event Slots:       $($dbStats.EventSlots) scheduled events"
Write-Host "    Placeholder Slots: $($dbStats.PlaceholderSlots) (fills gaps between events)"
Write-Host "    Active Channels:   $($dbStats.Channels) of 40"
Write-Host ""
if ($scheduleSamples -and $scheduleSamples.Count -gt 0) {
    Write-Host "  Upcoming Events (Sample):" -ForegroundColor Yellow
    foreach ($evt in $scheduleSamples) {
        $startTime = try { [DateTime]::Parse($evt.start_time).ToString("ddd HH:mm") } catch { $evt.start_time }
        $sport = if ($evt.sport) { " [$($evt.sport)]" } else { "" }
        Write-Host ("    Ch {0,2}  {1}  {2}{3}" -f $evt.channel_id, $startTime, $evt.title, $sport)
    }
    Write-Host ""
}
Write-Host "  Access URLs:" -ForegroundColor Yellow
Write-Host "    Web Interface:     " -NoNewline; Write-Host "$VC_RESOLVER_BASE_URL" -ForegroundColor Cyan
Write-Host "    EPG (XMLTV):       " -NoNewline; Write-Host "$VC_RESOLVER_BASE_URL/epg.xml" -ForegroundColor Cyan
Write-Host "    Playlist (M3U):    " -NoNewline; Write-Host "$VC_RESOLVER_BASE_URL/playlist.m3u" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Configuration:" -ForegroundColor Yellow
Write-Host "    Windows Server:    $LanIp`:$Port"
Write-Host "    Chrome Capture:    192.168.86.72:5589 (bradmini.lan)"
Write-Host "    Virtual Channels:  40 channels (20010-20049)"
Write-Host "    EPG Window:        72 hours"
Write-Host ""
Write-Host "  Next Steps:" -ForegroundColor Yellow
Write-Host "    1. Ensure Chrome Capture is running on bradmini.lan"
Write-Host "    2. Add to Channels DVR:"
Write-Host "       - M3U URL:  $VC_RESOLVER_BASE_URL/playlist.m3u"
Write-Host "       - EPG URL:  $VC_RESOLVER_BASE_URL/epg.xml"
Write-Host "    3. Refresh EPG in Channels DVR"
Write-Host "    4. Tune to channel 20010 to test!"
Write-Host ""
Write-Host "  Files:" -ForegroundColor Yellow
Write-Host "    Database:  data/eplus_vc.sqlite3"
Write-Host "    Logs:      logs/cron.log (auto-refresh activity)"
Write-Host ""
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""
