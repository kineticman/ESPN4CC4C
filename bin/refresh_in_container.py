#!/usr/bin/env python3
# refresh_in_container.py
# First-run safe refresher for ESPN4CC4C container
# - Runs DB migration (idempotent)
# - Ingests ESPN Watch Graph
# - Builds plan
# - Generates XMLTV + M3U
# - Prints a concise summary with basic validation

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

# -----------------------------
# Helpers
# -----------------------------


def env(name: str, default: str = "") -> str:
    v = os.environ.get(name, default)
    # Trim surrounding quotes users might add in compose
    if isinstance(v, str) and len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
        v = v[1:-1]
    return v


def run(cmd, check=True):
    """
    Run a command (list or string). Streams output to our stdout/stderr.
    Returns (rc, stdout_str) when check=False, otherwise raises on non-zero.
    """
    if isinstance(cmd, str):
        cmd_list = shlex.split(cmd)
    else:
        cmd_list = cmd
    print(f"→ {shlex.join(cmd_list)}", flush=True)
    proc = subprocess.Popen(
        cmd_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    out_lines = []
    for line in proc.stdout:
        print(line, end="")
        out_lines.append(line)
    proc.wait()
    out = "".join(out_lines)
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd_list, output=out)
    return proc.returncode, out


def abort(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


# -----------------------------
# Configuration
# -----------------------------

DB = env("DB", "/app/data/eplus_vc.sqlite3")
OUT = env("OUT", "/app/out")
TZ = env("TZ", "America/New_York")
VALID_HOURS = int(env("VALID_HOURS", "72") or "72")
LANES = int(env("LANES", "40") or "40")
ALIGN = int(env("ALIGN", "30") or "30")
MIN_GAP_MINS = int(env("MIN_GAP_MINS", "30") or "30")
PORT = int(env("PORT", "8094") or "8094")
CC_HOST = env("CC_HOST", "")
CC_PORT = env("CC_PORT", "")
VC_BASE = env("VC_RESOLVER_BASE_URL", "")

BIN = Path("/app/bin")

print("=== ESPN4CC4C Container Refresh Started ===")
print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime())}")
print("Configuration:")
print(f"  DB: {DB}")
print(f"  OUT: {OUT}")
print(f"  TZ: {TZ}")
print(f"  VALID_HOURS: {VALID_HOURS}")
print(f"  LANES: {LANES}")
print(f"  ALIGN: {ALIGN}")
print(f"  MIN_GAP_MINS: {MIN_GAP_MINS}")
print(f"  VC_RESOLVER_BASE_URL: {VC_BASE}")

# Ensure dirs
Path(OUT).mkdir(parents=True, exist_ok=True)
Path(DB).parent.mkdir(parents=True, exist_ok=True)
Path("/app/logs").mkdir(parents=True, exist_ok=True)

# Determine first run (before migration)
first_run = not Path(DB).exists()

# -----------------------------
# Step 0: DB migration (idempotent)
# -----------------------------
print("Step 0/4: Migrating database schema (idempotent)...")
migrator = BIN / "db_migrate.py"
if not migrator.exists():
    abort(f"Missing migrator: {migrator}")
run(["python3", str(migrator), "--db", DB, "--lanes", str(LANES)])

# First-run vs refresh: if DB file still didn't exist before, consider it first run
days = 3 if first_run else 1
print(
    "=== First Run: Initializing Database ==="
    if first_run
    else "=== Refreshing Existing Database ==="
)


# -----------------------------
# Step 1: Ingest
# -----------------------------
print(f"Step 1/4: Ingesting ESPN Watch Graph ({days} days)...")
ingest = BIN / "ingest_watch_graph_all_to_db.py"
run(["python3", str(ingest), "--db", DB, "--days", str(days)])

# -----------------------------
# Step 2: Build plan
# -----------------------------
print(f"Step 2/4: Building plan ({VALID_HOURS}h validity)...")
build_plan = BIN / "build_plan.py"
run(
    [
        "python3",
        str(build_plan),
        "--db",
        DB,
        "--valid-hours",
        str(VALID_HOURS),
        "--align",
        str(ALIGN),
        "--min-gap-mins",
        str(MIN_GAP_MINS),
        "--lanes",
        str(LANES),
    ]
)

# -----------------------------
# Step 3: XMLTV
# -----------------------------
print("Step 3/4: Generating XMLTV EPG...")
xmltv = BIN / "xmltv_from_plan.py"
epg_path = str(Path(OUT) / "epg.xml")
run(["python3", str(xmltv), "--db", DB, "--out", epg_path])

# -----------------------------
# Step 4: M3U
# -----------------------------
print("Step 4/4: Generating M3U playlist...")
m3u = BIN / "m3u_from_plan.py"
m3u_path = str(Path(OUT) / "playlist.m3u")
cmd = ["python3", str(m3u), "--db", DB, "--out", m3u_path]
if CC_HOST:
    cmd += ["--cc-host", CC_HOST]
if CC_PORT:
    cmd += ["--cc-port", CC_PORT]
run(cmd)


# -----------------------------
# Basic validation + summary
# -----------------------------
def file_ok(p: Path) -> bool:
    try:
        return p.exists() and p.stat().st_size > 0
    except Exception:
        return False


def count_programmes(epg_file: Path) -> int:
    # lightweight count without importing lxml
    try:
        n = 0
        with epg_file.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                # Cheap count of '<programme ' open tags
                if "<programme" in line:
                    n += line.count("<programme")
        return n
    except Exception:
        return -1


epg_ok = file_ok(Path(epg_path))
m3u_ok = file_ok(Path(m3u_path))
prog_ct = count_programmes(Path(epg_path)) if epg_ok else -1

print("=== Refresh Complete ===")
print(f"Database: {DB}")
print(f"EPG file: {epg_path} {'✓' if epg_ok else '✗'}")
print(f"M3U file: {m3u_path} {'✓' if m3u_ok else '✗'}")
if prog_ct >= 0:
    print(f"EPG programmes: {prog_ct}")

# Helpful URLs if VC_BASE is present
if VC_BASE:
    epg_url = f"{VC_BASE.rstrip('/')}/out/epg.xml"
    m3u_url = f"{VC_BASE.rstrip('/')}/playlist.m3u"
    print("Resolver endpoints:")
    print(f"  Health: {VC_BASE.rstrip('/')}/health")
    print(f"  EPG:    {epg_url}")
    print(f"  M3U:    {m3u_url}")
    print(f"  WhatsOn (all): {VC_BASE.rstrip('/')}/whatson_all")

# Exit non-zero if critical artifacts missing (so orchestrators can alert)
if not (epg_ok and m3u_ok):
    abort("Artifacts missing or empty. See logs above.", code=2)
