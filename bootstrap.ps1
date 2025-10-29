<#  bootstrap.ps1 — ESPN4CC4C quick start (Windows / Docker Desktop)
    Usage:
      Set-ExecutionPolicy Bypass -Scope Process -Force
      .\bootstrap.ps1 -LanIp 192.168.86.80 [-Port 8094]
#>

param(
  [Parameter(Mandatory = $true)][string]$LanIp,
  [int]$Port = 8094
)

$ErrorActionPreference = 'Stop'

function Info($m){ Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Ok($m){ Write-Host "[ OK ] $m" -ForegroundColor Green }
function Warn($m){ Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Err($m){ Write-Host "[ERR ] $m" -ForegroundColor Red }

function Compose { param([string[]]$Args)
  if (Get-Command docker -ErrorAction SilentlyContinue) {
    try { $null = docker compose version 2>$null; docker compose @Args; return } catch {}
  }
  if (Get-Command docker-compose -ErrorAction SilentlyContinue) { docker-compose @Args; return }
  Err "Docker Compose not available. Install Docker Desktop."; exit 1
}

# Docker daemon up?
try { $null = docker info | Out-Null } catch { Err "Docker daemon not reachable. Start Docker Desktop."; exit 1 }

# Bind mounts
foreach($d in 'data','logs','out'){ if(-not (Test-Path $d)){ New-Item -ItemType Directory -Path $d | Out-Null } }
Ok "Ensured ./data ./logs ./out"

# docker-compose.yml (create minimal if missing) — use format placeholders (no $ interpolation)
if(-not (Test-Path 'docker-compose.yml')){
$compose = @"
version: "3.8"
services:
  espn4cc:
    image: ghcr.io/babsonnexus/espn4cc4c:v0.1.1-rc6
    container_name: espn4cc
    ports:
      - "{0}:{0}"
    env_file:
      - .env
    environment:
      - PORT={0}
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./out:/app/out
    restart: unless-stopped
"@ -f $Port
$compose | Set-Content -Path 'docker-compose.yml' -Encoding ascii
Ok "Wrote minimal docker-compose.yml (port $Port)"
}

# .env write/update
$envPath = ".env"
$vcUrl   = "http://{0}:{1}" -f $LanIp, $Port
$envBlock = @(
  "PORT=$Port",
  "TZ=America/New_York",
  "",
  "DB=/app/data/eplus_vc.sqlite3",
  "OUT=/app/out",
  "LOGS=/app/logs",
  "VC_M3U_PATH=/app/out/playlist.m3u",
  "",
  "VALID_HOURS=72",
  "LANES=40",
  "ALIGN=30",
  "MIN_GAP_MINS=30",
  "",
  "VC_RESOLVER_BASE_URL=$vcUrl",
  "CC_HOST=$LanIp",
  "CC_PORT=5589"
) -join "`r`n"

if(-not (Test-Path $envPath)){
  $envBlock | Set-Content -Path $envPath -Encoding ascii
  Ok "Wrote .env with VC_RESOLVER_BASE_URL=$vcUrl"
}else{
  $content = Get-Content $envPath -Raw
  foreach($kv in @("VC_RESOLVER_BASE_URL=$vcUrl","VC_M3U_PATH=/app/out/playlist.m3u","CC_HOST=$LanIp","CC_PORT=5589")){
    $k = $kv.Split('=')[0]
    if($content -match "(?m)^$([regex]::Escape($k))="){
      $content = [regex]::Replace($content,"(?m)^$([regex]::Escape($k))=.*$", [regex]::Escape($kv) -replace '\\=','=')
    } else {
      if($content.Length -gt 0 -and $content[-1] -ne "`n"){ $content += "`r`n" }
      $content += $kv
    }
  }
  $content | Set-Content -Path $envPath -Encoding ascii
  Ok "Updated .env (resolver base, M3U path, CC_HOST/PORT)"
}

# Start stack
Info "Starting container…"
Compose @('pull')
Compose @('up','-d')

# readiness: /health (GET only)
$health = "$vcUrl/health"
Info "Waiting for health: $health"
$ready = $false
for($i=1;$i -le 30;$i++){
  try{
    $r = Invoke-WebRequest -Uri $health -UseBasicParsing -TimeoutSec 3
    if($r.StatusCode -eq 200 -and $r.Content -match '"status"\s*:\s*"ok"'){ $ready=$true; break }
  }catch{}
  Start-Sleep -Seconds 2
}
if(-not $ready){
  Err "Resolver not healthy after wait. Check logs:"
  Write-Host "  docker compose logs --tail=200 espn4cc"
  exit 2
}
Ok "Health OK"

# Strip CRLF in-container; run the canonical pipeline once
Info "Forcing schedule refresh…"
Compose @('exec','espn4cc','sh','-lc', @"
: "\${DB:=/app/data/eplus_vc.sqlite3}"; : "\${TZ:=America/New_York}";
mkdir -p /app/data /app/out /app/logs; [ -f "\$DB" ] || : > "\$DB";
[ -x /app/bin/db_migrate.py ] && python3 /app/bin/db_migrate.py --db "\$DB" || true
cnt=\$(sqlite3 "\$DB" 'SELECT COUNT(*) FROM events;' 2>/dev/null || echo 0)
if [ "\$cnt" -eq 0 ]; then python3 /app/bin/ingest_watch_graph_all_to_db.py --db "\$DB" --days 3 --tz "\$TZ"; fi
: "\${VALID_HOURS:=72}"; : "\${LANES:=40}"; : "\${ALIGN:=30}"; : "\${MIN_GAP_MINS:=30}";
python3 /app/bin/build_plan.py --db "\$DB" --valid-hours "\$VALID_HOURS" --min-gap-mins "\$MIN_GAP_MINS" --align "\$ALIGN" --lanes "\$LANES" --tz "\$TZ"
python3 /app/bin/xmltv_from_plan.py --db "\$DB" --out /app/out/epg.xml
: "\${VC_RESOLVER_BASE_URL:=http://127.0.0.1:${Port}}"; : "\${CC_HOST:=${LanIp}}"; : "\${CC_PORT:=5589}";
python3 /app/bin/m3u_from_plan.py --db "\$DB" --out /app/out/playlist.m3u --resolver-base "\$VC_RESOLVER_BASE_URL" --cc-host "\$CC_HOST" --cc-port "\$CC_PORT"
"@)

# Sanity checks (byte-safe)
$epgUrl = "$vcUrl/out/epg.xml"
$m3uUrl = "$vcUrl/playlist.m3u"
$dbgUrl = "$vcUrl/vc/eplus1/debug"

Info "Fetching EPG: $epgUrl"
$xmlResp = Invoke-WebRequest -Uri $epgUrl -UseBasicParsing
$xmlText = ($xmlResp.Content -is [byte[]]) ? [Text.Encoding]::UTF8.GetString($xmlResp.Content) : $xmlResp.Content
$progCount = ([regex]::Matches($xmlText,'<programme')).Count
Ok "EPG programmes: $progCount"

Info "Checking M3U: $m3uUrl"
$m3uResp = Invoke-WebRequest -Uri $m3uUrl -UseBasicParsing
$m3uText = ($m3uResp.Content -is [byte[]]) ? [Text.Encoding]::UTF8.GetString($m3uResp.Content) : $m3uResp.Content
$m3uPreview = $m3uText.Substring(0, [Math]::Min(600, $m3uText.Length))
Write-Host $m3uPreview
if($m3uText -notmatch [regex]::Escape($LanIp)){ Warn "M3U does not reference $LanIp"; } else { Ok "M3U references $LanIp (good)" }

Info "Lane debug (eplus1): $dbgUrl"
try{
  $dbg = Invoke-WebRequest -Uri $dbgUrl -UseBasicParsing
  $dbgText = ($dbg.Content -is [byte[]]) ? [Text.Encoding]::UTF8.GetString($dbg.Content) : $dbg.Content
  Write-Host ($dbgText -split "`r?`n" | Select-Object -First 20 -Join "`n")
}catch{ Warn "Could not fetch lane debug (eplus1)." }

Ok ("Bootstrap complete.`n- XMLTV: {0}`n- M3U:   {1}`nAdd these in Channels DVR when ready." -f $epgUrl,$m3uUrl)
