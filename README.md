# ESPN4CC4C — ESPN+ Virtual Channels for Channels DVR (Docker Edition)

Turn ESPN+ events into **stable virtual channels** (eplus1–eplus40) your **Channels DVR** can ingest via **XMLTV** and **M3U** — all packaged in a single Docker service.

---

## Highlights (what you get)

- **40 managed virtual channels** by default (configurable).
- **FastAPI resolver** on `:8094` serving:
  - `GET /out/epg.xml` (XMLTV)
  - `GET /playlist.m3u` (M3U, Chrome Capture–ready URLs)
  - `GET /health` (simple JSON `"ok": true`)
- **Idempotent DB schema migration** + plan builder (“sticky lanes”).
- **Simple Windows + Linux onboarding** with ready-made bootstrap scripts.
- **No proxies** (by design). **GET-only** sanity checks (no `HEAD`).
- **Persistent bind mounts** for `data/`, `out/`, `logs/`.

---

## Requirements

- Docker Engine 20.10+
- Docker Compose v2
- A LAN‑reachable IP for the host (e.g., `192.168.86.80`)
- Channels DVR (configured to ingest external XMLTV/M3U)  
- (Optional) Chrome Capture at `http://<LAN-IP>:5589` for smoother playback
- Outbound HTTPS to ESPN (for the ingest job)

> **Ports exposed**: `8094/tcp`

---

## Quick Start — Windows (Docker Desktop)

> Tested on PowerShell 5+ (Windows 10/11). Uses a hardened bootstrap that fixes common Windows pitfalls (CRLF, BOM, env propagation, health gating).

1) **Clone or unzip** this repo on your Windows host, then open **PowerShell** in the project folder.

2) **Run the Windows bootstrap** (replace `192.168.86.80` with your LAN IP):
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
.ootstrap_windows_hardened.ps1 -LanIp 192.168.86.80
```

What it does:
- Creates `./data`, `./logs`, `./out` if missing.
- Writes/repairs `.env` (UTF‑8 **no BOM**, LF line endings).
- Starts the container and waits for `GET /health` to be ok.
- Seeds/migrates DB; builds plan; writes fresh `epg.xml` + `playlist.m3u`.

**Sanity checks (PowerShell)**

```powershell
# Health
Invoke-WebRequest http://192.168.86.80:8094/health -UseBasicParsing | % Content

# XMLTV count (save first, then read raw)
$xmlPath = "$PWD\epg.xml"
Invoke-WebRequest http://192.168.86.80:8094/out/epg.xml -UseBasicParsing -OutFile $xmlPath
$xml = Get-Content $xmlPath -Raw
([regex]::Matches($xml,'<programme')).Count    # expect a big number (~5749)

# M3U preview
$m3uPath = "$PWD\playlist.m3u"
Invoke-WebRequest http://192.168.86.80:8094/playlist.m3u -UseBasicParsing -OutFile $m3uPath
$m3u = Get-Content $m3uPath -Raw
$m3u.Substring(0, [Math]::Min(600, $m3u.Length))  # expect chrome://<IP>:5589/stream?.../vc/<lane>
```

> If your **container logs** ever show `/app/.env: line 1: ... command not found`, that usually means a **UTF‑8 BOM** or **CRLF** snuck in. The bootstrap script already fixes this, but you can re-run it safely.

---

## Quick Start — Linux (Compose)

```bash
# 1) Clone this repo
git clone https://github.com/<you>/ESPN4CC4C.git
cd ESPN4CC4C

# 2) Create .env from example (edit LAN IPs as needed)
cp .env.example .env
# then edit .env with your values (see “ENV reference” below)

# 3) Start
docker compose up -d

# 4) Wait for health OK (GET-only)
curl -s http://<LAN-IP>:8094/health

# 5) Sanity
curl -s http://<LAN-IP>:8094/out/epg.xml | grep -c '<programme'
curl -s http://<LAN-IP>:8094/playlist.m3u | head -n 6
```

> Linux notes: use `LF` line endings in `.env`. No `HEAD` checks; use `GET`. Do **not** configure proxies for ESPN endpoints.

---

## Channels DVR Setup

- **XMLTV URL**: `http://<LAN-IP>:8094/out/epg.xml`
- **M3U URL**: `http://<LAN-IP>:8094/playlist.m3u`

Group/title examples are included; Channels will map the lanes (`eplus1…eplus40`) into a lineup you can favorite/rename.

---

## ENV reference (.env)

Here is a **minimal, polished** set of keys you likely care about. Everything else has sane defaults.

```dotenv
# --- Service ---
PORT=8094
TZ=America/New_York   # use a canonical IANA TZ

# --- Container paths ---
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
VC_RESOLVER_BASE_URL=http://192.168.86.80:8094

# --- Chrome Capture (optional but recommended) ---
CC_HOST=192.168.86.80
CC_PORT=5589
M3U_GROUP_TITLE=ESPN+ VC

# --- ESPN Watch API key (project allows sharing; not secret) ---
WATCH_API_KEY=0dbf88e8-cc6d-41da-aa83-18b5c630bc5c
```

**Important:**  
- Keep `.env` **UTF‑8 (no BOM)** + **LF** line endings on Windows too (the Windows bootstrap takes care of this).  
- **Never** use HTTP proxies for ESPN endpoints.  
- Our health + sanity checks are **GET-only** (no `HEAD`).

---

## Common operations

**See logs**  
```powershell
# Windows
docker compose logs --tail=200 espn4cc
```
```bash
# Linux
docker compose logs --tail=200 espn4cc
```

**Rebuild plan & outputs manually (inside container)**  
```bash
docker compose exec -T espn4cc sh -c '
  : "${DB:=/app/data/eplus_vc.sqlite3}"; : "${TZ:=America/New_York}";
  : "${VALID_HOURS:=72}"; : "${LANES:=40}"; : "${ALIGN:=30}"; : "${MIN_GAP_MINS:=30}";
  python3 /app/bin/build_plan.py --db "$DB" --valid-hours "$VALID_HOURS" --min-gap-mins "$MIN_GAP_MINS" --align "$ALIGN" --lanes "$LANES" --tz "$TZ";
  python3 /app/bin/xmltv_from_plan.py --db "$DB" --out /app/out/epg.xml;
  : "${VC_RESOLVER_BASE_URL:=http://127.0.0.1:8094}"; : "${CC_HOST:=127.0.0.1}"; : "${CC_PORT:=5589}";
  python3 /app/bin/m3u_from_plan.py --db "$DB" --out /app/out/playlist.m3u --resolver-base "$VC_RESOLVER_BASE_URL" --cc-host "$CC_HOST" --cc-port "$CC_PORT"
'
```

**Force recreate container**  
```powershell
docker compose up -d --force-recreate
```

---

## Troubleshooting (battle‑tested)

- **`.env` BOM / CRLF**: If you see `/app/.env: line 1: ... command not found`, fix encoding/line endings. The Windows bootstrap script already does this.  
- **Health fails**: Ensure port `8094` isn’t blocked and the container is `Up (healthy)`.  
- **No events** after ingest: verify `WATCH_API_KEY` is present in the container `env`, and outbound HTTPS to ESPN works.  
- **TZ mistakes** cause ingest to fail: must be a valid IANA TZ (e.g., `America/New_York`).  
- **Symlink project name warning** from Compose is harmless.  
- **Chrome Capture integration**: If you don’t run CC, the M3U still works (URLs will still resolve through the resolver).

---

## File layout

```
ESPN4CC4C/
├─ bin/                      # planner & generators
├─ data/                     # SQLite (persisted)
├─ logs/                     # rotated logs
├─ out/                      # epg.xml + playlist.m3u
├─ docker-compose.yml
├─ .env                      # your environment (UTF-8 no BOM)
├─ bootstrap_windows_hardened.ps1
└─ README.md
```

---

## Notes & Policy

- **No proxies** will ever be used for ESPN endpoints (project policy).  
- All validation checks use **GET** (no `HEAD`).  
- Keep changes on a branch and PR into `main` when stable.

Enjoy! If something feels clunky, open an issue with your logs + what you expected to see.