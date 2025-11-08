<#  
  windowsbootstrap_complete.ps1 - Complete Windows setup for ESPN4CC4C
  
  What it does:
    * Creates data/logs/out directories
    * Writes clean .env (UTF-8 no BOM, LF)
    * Starts container and waits for /health
    * Migrates DB schema
    * Ingests 72h of ESPN events
    * Builds virtual channel plan
    * Generates EPG (XMLTV) and M3U playlist
    * Validates and previews outputs
#>

param(
  [Parameter(Mandatory=$true)][string]$LanIp,
  [int]$Port   = 8094,
  [int]$CCPort = 5589
)

# === Pin working directory to this script's folder ===
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ScriptDir) { $ScriptDir = $PSScriptRoot }
Set-Location $ScriptDir
$RepoDir = $ScriptDir

# === Helpers ===
function Write-Info ($msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Ok   ($msg) { Write-Host "[ OK ] $msg" -ForegroundColor Green }
function Write-Warn ($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err  ($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red }

# === 0) Sanity check ===
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Err "Docker Desktop / docker CLI not found in PATH"
    exit 1
}
$env:COMPOSE_PROJECT_NAME = "espn4cc"

# === 1) Ensure project directories ===
New-Item -ItemType Directory -Path (Join-Path $RepoDir 'data') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $RepoDir 'logs') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $RepoDir 'out')  -Force | Out-Null
Write-Ok "Ensured ./data ./logs ./out"

# === 2) .env (UTF-8 no BOM, LF) ===
$envPath = Join-Path $RepoDir ".env"

# Keep existing WATCH_API_KEY if present
$existingKey = ""
if (Test-Path $envPath) {
    $raw = Get-Content $envPath -Raw
    if ($raw -match "(?m)^WATCH_API_KEY=(.*)$") { 
        $existingKey = $Matches[1].Trim() 
    }
}
if ([string]::IsNullOrWhiteSpace($existingKey)) {
    $existingKey = "0dbf88e8-cc6d-41da-aa83-18b5c630bc5c"
    Write-Info "Using default WATCH_API_KEY"
}

$envContent = @"
# --- Service ---
PORT=$Port
TZ=America/New_York

# --- Container paths (bind mounts map host -> /app/*) ---
DB=/app/data/eplus_vc.sqlite3
OUT=/app/out
LOGS=/app/logs
VC_M3U_PATH=/app/out/playlist.m3u

# --- Planner tunables ---
VALID_HOURS=72
LANES=40
ALIGN=30
MIN_GAP_MINS=30

# --- Resolver base URL (LAN reachable; do NOT use 127.0.0.1) ---
VC_RESOLVER_BASE_URL=http://${LanIp}:${Port}

# --- Chrome Capture integration ---
CC_HOST=$LanIp
CC_PORT=$CCPort
M3U_GROUP_TITLE=ESPN+ VC

# --- ESPN Watch API (public per project notes) ---
WATCH_API_KEY=$existingKey
"@

# Normalize newlines and save as UTF-8 no BOM
$envContent = $envContent -replace "`r`n", "`n" -replace "`r","`n"
[IO.File]::WriteAllText($envPath, $envContent, [Text.UTF8Encoding]::new($false))
Write-Ok ".env written (LF, no BOM)"

# === 3) Start container ===
Write-Info "Starting container..."
docker compose up -d --force-recreate | Out-Null
if ($LASTEXITCODE -ne 0) { 
    Write-Err "docker compose up failed"
    exit 2 
}

# === 4) Health wait ===
$healthUrl = "http://${LanIp}:${Port}/health"
Write-Info "Waiting for health at $healthUrl"
$healthy = $false
for ($i=0; $i -lt 60; $i++) {
    try {
        $r = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200 -and $r.Content -like '*"ok":true*') { 
            $healthy = $true
            break 
        }
    } catch { 
        Start-Sleep -Milliseconds 500 
    }
    Start-Sleep -Seconds 1
}
if (-not $healthy) { 
    Write-Err "Resolver did not become healthy at $healthUrl"
    exit 3 
}
Write-Ok "Resolver healthy"

# === 5) DB migrate (idempotent) ===
Write-Info "Migrating DB schema..."
docker compose exec -T espn4cc sh -lc 'python3 /app/bin/db_migrate.py --db /app/data/eplus_vc.sqlite3' | Out-Null
if ($LASTEXITCODE -ne 0) { 
    Write-Err "db_migrate.py failed"
    exit 4 
}
$tables = (docker compose exec -T espn4cc sh -lc 'sqlite3 /app/data/eplus_vc.sqlite3 ".tables"')
Write-Ok ("Tables: {0}" -f $tables)

# === 6) Ingest 72h (GET-only) ===
Write-Info "Ingesting 72h from ESPN Watch Graph..."
$ingOut = docker compose exec -T espn4cc sh -lc 'python3 /app/bin/ingest_watch_graph_all_to_db.py --db /app/data/eplus_vc.sqlite3 --days 3 --tz America/New_York' 2>&1
$ingOut | Write-Host
if ($ingOut -notmatch 'Ingested \d+ airings') {
    Write-Warn "Ingest did not report counts - check WATCH_API_KEY and network"
}

# === 7) Build plan + write outputs ===
Write-Info "Building plan + writing XMLTV/M3U..."
docker compose exec -T espn4cc sh -lc 'python3 /app/bin/build_plan.py --db /app/data/eplus_vc.sqlite3 --valid-hours 72 --min-gap-mins 30 --align 30 --lanes 40 --tz America/New_York' | Write-Host
docker compose exec -T espn4cc sh -lc 'python3 /app/bin/xmltv_from_plan.py --db /app/data/eplus_vc.sqlite3 --out /app/out/epg.xml' | Write-Host
docker compose exec -T espn4cc sh -lc "python3 /app/bin/m3u_from_plan.py --db /app/data/eplus_vc.sqlite3 --out /app/out/playlist.m3u --resolver-base http://${LanIp}:${Port} --cc-host ${LanIp} --cc-port ${CCPort}" | Write-Host
Write-Ok "EPG/M3U written"

# === 8) Final tests ===
# EPG: download -> count <programme>
Write-Info "Re-check XMLTV (fresh read)"
$xmlPath = Join-Path $RepoDir "epg.xml"
try {
    Invoke-WebRequest "http://${LanIp}:${Port}/out/epg.xml" -UseBasicParsing -OutFile $xmlPath
    $xml = Get-Content $xmlPath -Raw
    $progCount = ([regex]::Matches($xml,'<programme')).Count
    Write-Host ("{0} programmes found" -f $progCount) -ForegroundColor Green
} catch {
    Write-Warn "Could not fetch EPG: $($_.Exception.Message)"
}

# M3U: download -> preview
Write-Info "Re-check M3U (preview first ~600 chars)"
$m3uPath   = Join-Path $RepoDir 'playlist.m3u'
$baseUrl   = "http://${LanIp}:${Port}"
$m3uUrls   = @("$baseUrl/out/playlist.m3u", "$baseUrl/playlist.m3u")
$downloaded = $false

foreach ($u in $m3uUrls) {
    Write-Host "GET $u" -ForegroundColor DarkCyan
    try {
        $resp = Invoke-WebRequest -Uri $u -UseBasicParsing -ErrorAction Stop
        # Decode content as string
        $content = [System.Text.Encoding]::UTF8.GetString($resp.Content)
        
        if ($resp.StatusCode -eq 200 -and $content -match '^\#EXTM3U') {
            $content | Set-Content -Path $m3uPath -NoNewline
            Write-Ok "Saved M3U -> $m3uPath"
            $downloaded = $true
            break
        } else {
            Write-Warn "Unexpected response (Status=$($resp.StatusCode)). First 60 chars:"
            $head = $content.Substring(0, [Math]::Min(60, $content.Length))
            Write-Host $head -ForegroundColor DarkYellow
        }
    } catch {
        Write-Warn "Request failed: $($_.Exception.Message)"
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            Write-Warn "HTTP status: $([int]$_.Exception.Response.StatusCode)"
        }
    }
}

if (-not $downloaded) {
    Write-Err "Could not fetch a valid M3U from any known path. Tried: $($m3uUrls -join ', ')"
    Write-Host "Tip: check resolver health: $healthUrl" -ForegroundColor Yellow
    exit 5
}

# Safe preview (first 600 chars)
$m3u = Get-Content $m3uPath -Raw
$preview = $m3u.Substring(0, [Math]::Min(600, $m3u.Length))
Write-Host $preview -ForegroundColor Gray

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Ok "DONE"
Write-Host "Health   : $healthUrl" -ForegroundColor Cyan
Write-Host "XMLTV    : http://${LanIp}:${Port}/out/epg.xml" -ForegroundColor Cyan
Write-Host "M3U      : http://${LanIp}:${Port}/out/playlist.m3u" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Green
