<#  bootstrap.ps1  — ESPN4CC4C (Windows + Docker Desktop friendly)
    Usage:
      Set-ExecutionPolicy Bypass -Scope Process -Force
      .\bootstrap.ps1 -LanIp 192.168.86.80 [-Port 8094]

    What it does:
      - Writes .env with LAN-aware settings (resolver & Chrome Capture)
      - Ensures ./data ./logs ./out exist (bind mounts)
      - Normalizes .env to LF (no BOM) to avoid CRLF issues inside container
      - docker compose up -d (or docker-compose up -d), readiness wait on /health
      - One-time inside-container run: migrate DB, optional ingest, build plan, write XMLTV/M3U
      - Prints sanity checks: health ok, EPG programme count, M3U preview, lane debug

    Notes:
      - Uses GET only for HTTP checks
      - Never uses proxies for ESPN endpoints
      - Compatible with Windows PowerShell 5.x and PowerShell 7+
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)]
  [string]$LanIp,

  [int]$Port = 8094
)

# --- Helpers ---------------------------------------------------------------

function Write-Ok    ([string]$msg) { Write-Host "[ OK ] $msg" -ForegroundColor Green }
function Write-Info  ([string]$msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Warn  ([string]$msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Error2([string]$msg) { Write-Host "[ERR ] $msg" -ForegroundColor Red }

function Compose {
  param([string[]]$Args)
  if (Get-Command docker -ErrorAction SilentlyContinue) {
    try {
      $null = docker compose version 2>$null
      return docker compose @Args
    } catch { }
  }
  return docker-compose @Args
}

function Ensure-Dirs {
  param([string[]]$Paths)
  foreach ($p in $Paths) {
    if (-not (Test-Path -LiteralPath $p)) {
      New-Item -ItemType Directory -Force -Path $p | Out-Null
    }
  }
}

# Normalize a text file to **LF** (no BOM). Important for .env in Linux container.
function Set-LFFile {
  param([Parameter(Mandatory)] [string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) { return }
  $raw = Get-Content -LiteralPath $Path -Raw
  # Replace CRLF/CR -> LF
  $lf  = $raw -replace "`r`n", "`n" -replace "`r","`n"
  [IO.File]::WriteAllText($Path, $lf, [Text.UTF8Encoding]::new($false))
}

# Quick GET with retries; returns $true on HTTP 200
function Wait-Healthy {
  param(
    [Parameter(Mandatory)][string]$Url,
    [int]$Retries = 30,
    [int]$DelaySec = 2
  )
  for ($i=1; $i -le $Retries; $i++) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -Method GET -TimeoutSec 5
      if ($r.StatusCode -eq 200) { return $true }
    } catch { }
    Start-Sleep -Seconds $DelaySec
  }
  return $false
}

# Inside-container one-shot runner (no WSL required)
function InContainer {
  param([Parameter(Mandatory)][string]$ShellScript)
  Compose @('exec','-T','espn4cc','sh','-lc', $ShellScript)
}

# --- 1) Ensure folders -----------------------------------------------------

Ensure-Dirs @('data','logs','out')
Write-Ok "Ensured ./data ./logs ./out"

# --- 2) Render .env --------------------------------------------------------

$envPath = ".env"
$envBody = @"
# --- Service ---
PORT=$Port
TZ=America/New_York

# --- Container paths (match bind mounts) ---
DB=/app/data/eplus_vc.sqlite3
OUT=/app/out
LOGS=/app/logs
VC_M3U_PATH=/app/out/playlist.m3u

# --- Planner tunables ---
VALID_HOURS=72
LANES=40
ALIGN=30
MIN_GAP_MINS=30

# --- Resolver base URL (LAN-reachable) ---
VC_RESOLVER_BASE_URL=http://$LanIp:$Port

# --- Chrome Capture (optional but recommended) ---
CC_HOST=$LanIp
CC_PORT=5589
M3U_GROUP_TITLE='ESPN+ VC'

# Optional ESPN Watch API key (public per project notes)
WATCH_API_KEY=0dbf88e8-cc6d-41da-aa83-18b5c630bc5c
"@

# Write .env (as-is), then normalize to LF
Set-Content -LiteralPath $envPath -Value $envBody -Encoding UTF8
Set-LFFile -Path $envPath
Write-Ok "Updated .env"

# --- 3) Bring up container -------------------------------------------------

Write-Info "Starting container…"
Compose @('up','-d') | Out-Null

# Readiness wait
$healthUrl = "http://{0}:{1}/health" -f $LanIp, $Port
if (-not (Wait-Healthy -Url $healthUrl -Retries 40 -DelaySec 2)) {
  Write-Error2 "Resolver did not become healthy at $healthUrl"
  exit 2
}
Write-Ok "Resolver healthy at $healthUrl"

# --- 4) First-run tasks inside container ----------------------------------

# Migrate DB, seed if empty, build plan, emit XML + M3U
$inside = @'
: "${DB:=/app/data/eplus_vc.sqlite3}"; : "${TZ:=America/New_York}";
mkdir -p /app/data /app/out /app/logs; [ -f "$DB" ] || : > "$DB";

# migrate (idempotent)
python3 /app/bin/db_migrate.py --db "$DB" || true

# seed only if empty
cnt=$(sqlite3 "$DB" "select count(*) from events;" 2>/dev/null || echo 0)
if [ "$cnt" -eq 0 ]; then
  python3 /app/bin/ingest_watch_graph_all_to_db.py --db "$DB" --days 3 --tz "$TZ" || true
fi

: "${VALID_HOURS:=72}"; : "${LANES:=40}"; : "${ALIGN:=30}"; : "${MIN_GAP_MINS:=30}";
python3 /app/bin/build_plan.py --db "$DB" --valid-hours "$VALID_HOURS" --min-gap-mins "$MIN_GAP_MINS" --align "$ALIGN" --lanes "$LANES" --tz "$TZ" || true

python3 /app/bin/xmltv_from_plan.py --db "$DB" --out /app/out/epg.xml || true

: "${VC_RESOLVER_BASE_URL:=http://127.0.0.1:@PORT@}"; : "${CC_HOST:=@LANIP@}"; : "${CC_PORT:=5589}";
python3 /app/bin/m3u_from_plan.py --db "$DB" --out /app/out/playlist.m3u \
  --resolver-base "$VC_RESOLVER_BASE_URL" --cc-host "$CC_HOST" --cc-port "$CC_PORT" || true
'@

$inside = $inside.Replace('@PORT@', "$Port").Replace('@LANIP@', $LanIp)
InContainer -ShellScript $inside | Out-Null
Write-Ok "Plan built and outputs written"

# --- 5) Smoke tests (PowerShell 5/7 safe) ---------------------------------

# Health JSON
try {
  $h = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -Method GET -TimeoutSec 6
  Write-Ok ("Health: " + $h.Content)
} catch {
  Write-Warn "Health fetch failed: $($_.Exception.Message)"
}

# EPG <programme> count
try {
  $epgUrl = "http://{0}:{1}/out/epg.xml" -f $LanIp, $Port
  $epg = Invoke-WebRequest -UseBasicParsing -Uri $epgUrl -Method GET -TimeoutSec 12
  $epgText = $epg.Content
  if ($epgText -is [byte[]]) { $epgText = [Text.Encoding]::UTF8.GetString($epgText) }
  $progCount = ([regex]::Matches($epgText, '<programme')).Count
  Write-Ok ("EPG programmes: {0}" -f $progCount)
} catch {
  Write-Warn "EPG fetch failed: $($_.Exception.Message)"
}

# M3U preview
try {
  $m3uUrl = "http://{0}:{1}/playlist.m3u" -f $LanIp, $Port
  $m3u = Invoke-WebRequest -UseBasicParsing -Uri $m3uUrl -Method GET -TimeoutSec 12
  $m3uText = $m3u.Content
  if ($m3uText -is [byte[]]) { $m3uText = [Text.Encoding]::UTF8.GetString($m3uText) }
  $preview = $m3uText.Substring(0, [Math]::Min(600, $m3uText.Length))
  Write-Ok "M3U preview:"
  $preview
} catch {
  Write-Warn "M3U fetch failed: $($_.Exception.Message)"
}

# Lane debug sampler (prints first active slot it finds)
try {
  for ($i=1; $i -le 40; $i++) {
    $lane = ("eplus{0:D1}" -f $i)
    $dbgUrl = "http://{0}:{1}/vc/{2}/debug" -f $LanIp, $Port, $lane
    try {
      $r = Invoke-WebRequest -UseBasicParsing -Uri $dbgUrl -Method GET -TimeoutSec 6
      $txt = $r.Content
      if ($txt -is [byte[]]) { $txt = [Text.Encoding]::UTF8.GetString($txt) }
      # Robust JSON parse if it's JSON; otherwise skip
      try {
        $obj = $txt | ConvertFrom-Json
        if ($obj.slot) {
          Write-Ok ("{0} => {1}  {2}" -f $lane, $obj.slot.start, $obj.slot.title)
          break
        }
      } catch { }
    } catch { }
  }
} catch {
  Write-Warn "Lane debug failed: $($_.Exception.Message)"
}

Write-Host ""
Write-Ok "Bootstrap complete!"
Write-Info ("XMLTV: http://{0}:{1}/out/epg.xml" -f $LanIp, $Port)
Write-Info ("M3U  : http://{0}:{1}/playlist.m3u" -f $LanIp, $Port)
