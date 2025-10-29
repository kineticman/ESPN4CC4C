<#  bootstrap1.ps1 – Windows PowerShell 5.x friendly
    Usage:
      PS> Set-ExecutionPolicy Bypass -Scope Process -Force
      PS> .\bootstrap1.ps1 -LanIp 192.168.86.80 [-Port 8094] [-CCPort 5589]

    What it does:
      1) Ensures ./data ./logs ./out
      2) Writes .env with LF and no BOM (preserves existing WATCH_API_KEY if present)
      3) docker compose up -d
      4) Waits for /health
      5) Runs db_migrate (idempotent)
      6) Ingests 3 days of events with TZ=America/New_York
      7) Builds plan + writes /out/epg.xml and /out/playlist.m3u
      8) Runs two verification tests (EPG programme count and M3U preview)
#>

param(
  [Parameter(Mandatory=$true)][string]$LanIp,
  [int]$Port   = 8094,
  [int]$CCPort = 5589
)

function Write-Info($m){ Write-Host "[INFO]" $m -ForegroundColor Cyan }
function Write-Ok($m){ Write-Host "[ OK ]" $m -ForegroundColor Green }
function Write-Err($m){ Write-Host "[ERR ]" $m -ForegroundColor Red }

# --- 0) Preconditions ---------------------------------------------------------
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Err "Docker not found in PATH"; exit 1
}

# Suppress Docker Compose symlink warnings
$env:COMPOSE_PROJECT_NAME = "espn4cc"

# --- 1) Folders ---------------------------------------------------------------
$dirs = @(".\data",".\logs",".\out")
foreach($d in $dirs){ if (-not (Test-Path $d)) { New-Item -ItemType Directory -Force -Path $d | Out-Null } }
Write-Ok "Ensured ./data ./logs ./out"

# --- 2) Build .env (LF, no BOM). Preserve existing WATCH_API_KEY if present ---
$envPath = ".env"
$existingKey = ""
if (Test-Path $envPath) {
  $raw = Get-Content $envPath -Raw
  $m = [regex]::Match($raw, "(?m)^WATCH_API_KEY=(.*)$")
  if ($m.Success) { $existingKey = $m.Groups[1].Value.Trim() }
}

$EnvLines = @(
  "# --- Service ---",
  "PORT=$Port",
  "TZ=America/New_York",
  "",
  "# --- Container paths (match bind mounts) ---",
  "DB=/app/data/eplus_vc.sqlite3",
  "OUT=/app/out",
  "LOGS=/app/logs",
  "VC_M3U_PATH=/app/out/playlist.m3u",
  "",
  "# --- Planner tunables ---",
  "VALID_HOURS=72",
  "LANES=40",
  "ALIGN=30",
  "MIN_GAP_MINS=30",
  "",
  "# --- Resolver base URL (LAN-reachable) ---",
  ("VC_RESOLVER_BASE_URL=http://{0}:{1}" -f $LanIp,$Port),
  "",
  "# --- Chrome Capture (optional but recommended) ---",
  ("CC_HOST={0}" -f $LanIp),
  ("CC_PORT={0}" -f $CCPort),
  "M3U_GROUP_TITLE='ESPN+ VC'",
  "",
  "# Optional ESPN Watch API key",
  ("WATCH_API_KEY={0}" -f ($existingKey))
)

# Normalize to LF and write UTF-8 (no BOM)
$txt = ($EnvLines -join "`n") -replace "`r`n","`n" -replace "`r","`n"
[IO.File]::WriteAllText($envPath, $txt, [Text.UTF8Encoding]::new($false))
Write-Ok "Updated .env"

# --- 3) Start container -------------------------------------------------------
Write-Info "Starting container..."
$output = & docker compose up -d --force-recreate 2>&1
if ($LASTEXITCODE -ne 0) { 
  Write-Err "Failed to start container: $output"
  exit 2
}
Write-Ok "Container started"

# --- 4) Wait for /health ------------------------------------------------------
$healthUrl = "http://{0}:{1}/health" -f $LanIp,$Port
$ok = $false
Write-Info "Waiting for service to become healthy..."
for ($i=1; $i -le 60; $i++){
  try {
    $r = Invoke-WebRequest $healthUrl -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -eq 200 -and ($r.Content -like '*"ok":true*')) { $ok = $true; break }
  } catch { Start-Sleep -Milliseconds 500 }
  Start-Sleep -Seconds 1
}
if (-not $ok) { Write-Err "Resolver did not become healthy at $healthUrl"; exit 3 }
Write-Ok "Resolver healthy at $healthUrl"

# --- 5) DB migrate (idempotent) ----------------------------------------------
Write-Info "Running database migration..."
Start-Sleep -Seconds 2  # Brief pause to ensure container is stable
$cmdMigrate = @'
: "${DB:=/app/data/eplus_vc.sqlite3}";
python3 /app/bin/db_migrate.py --db "$DB";
sqlite3 "$DB" ".tables"
'@
$migOutput = & docker compose exec -T espn4cc sh -lc $cmdMigrate 2>&1
if ($LASTEXITCODE -ne 0) { 
  Write-Err "DB migration failed: $migOutput"
  exit 4 
}
Write-Ok "Database migrated"

# --- 6) Ingest 3 days with TZ -------------------------------------------------
Write-Info "Ingesting 3 days of events..."
$cmdIngest = @'
: "${DB:=/app/data/eplus_vc.sqlite3}";
: "${TZ:=America/New_York}";
python3 /app/bin/ingest_watch_graph_all_to_db.py --db "$DB" --days 3 --tz "$TZ";
sqlite3 "$DB" "select count(*) from events;"
'@
$ingestOutput = & docker compose exec -T espn4cc sh -lc $cmdIngest 2>&1 | Out-String
# Check if we got some events (partial success is OK for ESPN API flakiness)
if ($ingestOutput -match "Ingested (\d+) airings") {
  $count = $matches[1]
  if ([int]$count -gt 0) {
    Write-Ok "Events ingested (got $count airings)"
    if ($ingestOutput -match "503|Backend fetch failed") {
      Write-Host "  Warning: ESPN API had intermittent errors, but got partial data" -ForegroundColor Yellow
    }
  } else {
    Write-Err "Event ingestion failed: $ingestOutput"
    exit 5
  }
} elseif ($LASTEXITCODE -ne 0) { 
  Write-Err "Event ingestion failed: $ingestOutput"
  exit 5 
} else {
  Write-Ok "Events ingested"
}

# --- 7) Build plan + write XMLTV + M3U ---------------------------------------
Write-Info "Building schedule plan and generating EPG/M3U..."
$cmdPlan = @'
: "${DB:=/app/data/eplus_vc.sqlite3}";
: "${TZ:=America/New_York}";
: "${VALID_HOURS:=72}"; : "${LANES:=40}"; : "${ALIGN:=30}"; : "${MIN_GAP_MINS:=30}";
python3 /app/bin/build_plan.py --db "$DB" --valid-hours "$VALID_HOURS" --min-gap-mins "$MIN_GAP_MINS" --align "$ALIGN" --lanes "$LANES" --tz "$TZ";
python3 /app/bin/xmltv_from_plan.py --db "$DB" --out /app/out/epg.xml;
: "${VC_RESOLVER_BASE_URL:=http://192.168.86.80:8094}";
: "${CC_HOST:=192.168.86.80}"; : "${CC_PORT:=5589}";
python3 /app/bin/m3u_from_plan.py --db "$DB" --out /app/out/playlist.m3u --resolver-base "$VC_RESOLVER_BASE_URL" --cc-host "$CC_HOST" --cc-port "$CC_PORT"
'@
$planOutput = & docker compose exec -T espn4cc sh -lc $cmdPlan 2>&1
if ($LASTEXITCODE -ne 0) { 
  Write-Err "Plan build failed: $planOutput"
  exit 6 
}
Write-Ok "Plan built and files generated"

# --- 8) Show essentials -------------------------------------------------------
try {
  $healthResponse = Invoke-WebRequest $healthUrl -UseBasicParsing -TimeoutSec 5
  Write-Ok "Health: $($healthResponse.Content)"
} catch {
  Write-Err "Health check failed: $_"
}

# --- 9) Verification tests ---------------------------------------------------
Write-Info "Verifying XMLTV EPG..."
try {
  $xmlResponse = Invoke-WebRequest ("http://{0}:{1}/out/epg.xml" -f $LanIp,$Port) -UseBasicParsing -TimeoutSec 15
  $xmlContent = [System.Text.Encoding]::UTF8.GetString($xmlResponse.Content)
  $progCount = ([regex]::Matches($xmlContent,'<programme')).Count
  Write-Ok "EPG: $progCount programmes found (expect thousands after full build)"
} catch {
  Write-Err "Failed to verify EPG: $_"
}

Write-Info "Verifying M3U playlist..."
try {
  $m3uResponse = Invoke-WebRequest ("http://{0}:{1}/playlist.m3u" -f $LanIp,$Port) -UseBasicParsing -TimeoutSec 15
  $m3uContent = [System.Text.Encoding]::UTF8.GetString($m3uResponse.Content)
  Write-Host ($m3uContent.Substring(0, [Math]::Min(600, $m3uContent.Length)))
  Write-Ok "M3U playlist verified"
} catch {
  Write-Err "Failed to verify M3U: $_"
}

# --- Final summary -----------------------------------------------------------
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Ok "Bootstrap complete!"
Write-Host ""
Write-Host "  EPG URL:      http://$LanIp`:$Port/out/epg.xml" -ForegroundColor Cyan
Write-Host "  Playlist URL: http://$LanIp`:$Port/playlist.m3u" -ForegroundColor Cyan
Write-Host "  Health URL:   http://$LanIp`:$Port/health" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Local files:  .\out\epg.xml and .\out\playlist.m3u" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Ok "bootstrap1.ps1 finished successfully."