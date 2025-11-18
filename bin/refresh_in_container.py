#!/usr/bin/env python3
# refresh_in_container.py
# First-run safe refresher for ESPN4CC4C container
# - Runs DB migration (idempotent)
# - Optionally resets DB/plan tables when filters change
# - Ingests ESPN Watch Graph
# - Applies event filters (deletes non-matching events from DB)
# - Builds plan (with optional --force-replan on filter change)
# - Generates XMLTV + M3U
# - Prints a concise summary with basic validation

import os
import shlex
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from filter_events import EventFilter, filter_events_from_db


def env(name: str, default: str = "") -> str:
    v = os.environ.get(name, default)
    # Trim surrounding quotes some UIs add
    if isinstance(v, str) and len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
        v = v[1:-1]
    return v


def run(cmd, check: bool = True):
    """Run a command (list or string). Stream output. Return (rc, stdout_str)."""
    if isinstance(cmd, str):
        cmd_list = shlex.split(cmd)
    else:
        cmd_list = cmd

    print(f"→ {shlex.join(cmd_list)}", flush=True)
    proc = subprocess.Popen(
        cmd_list,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    out_lines = []
    assert proc.stdout is not None
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

AUTO_FORCE_REPLAN_ON_FILTER_CHANGE = env("AUTO_FORCE_REPLAN_ON_FILTER_CHANGE", "true").lower() in (
    "1",
    "true",
    "yes",
)
AUTO_RESET_DB_ON_FILTER_CHANGE = env("AUTO_RESET_DB_ON_FILTER_CHANGE", "false").lower() in (
    "1",
    "true",
    "yes",
)

BIN = Path("/app/bin")
FILTERS_INI = "/app/filters.ini"
FILTER_SIG_PATH = Path(DB).parent / "filter_signature.txt"

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
print(f"  AUTO_FORCE_REPLAN_ON_FILTER_CHANGE: {AUTO_FORCE_REPLAN_ON_FILTER_CHANGE}")
print(f"  AUTO_RESET_DB_ON_FILTER_CHANGE: {AUTO_RESET_DB_ON_FILTER_CHANGE}")

# Ensure dirs
Path(OUT).mkdir(parents=True, exist_ok=True)
Path(DB).parent.mkdir(parents=True, exist_ok=True)
Path("/app/logs").mkdir(parents=True, exist_ok=True)

# -----------------------------
# Filter configuration & change detection
# -----------------------------

try:
    event_filter = EventFilter(FILTERS_INI, use_env=True)
except Exception as e:
    print(f"[filter] ERROR: Failed to load filters: {e}", flush=True)
    # Fallback to a no-op filter to avoid blocking refresh
    event_filter = EventFilter(FILTERS_INI, use_env=False)

filter_summary = event_filter.get_filter_summary()
print(filter_summary)
print()

current_sig = event_filter.config_signature()
previous_sig: str | None = None
if FILTER_SIG_PATH.exists():
    try:
        previous_sig = FILTER_SIG_PATH.read_text(encoding="utf-8").strip() or None
    except Exception:
        previous_sig = None

filters_changed = previous_sig is not None and previous_sig != current_sig
if filters_changed:
    print("[filter] Detected filter configuration change since last run", flush=True)
else:
    print("[filter] No filter change detected compared to last run", flush=True)

# Determine first-run (before migration)
first_run = not Path(DB).exists()

# -----------------------------
# Step 0: DB migration (idempotent)
# -----------------------------
print("Step 0/5: Migrating database schema (idempotent)...")
migrator = BIN / "db_migrate.py"
if not migrator.exists():
    abort(f"Missing migrator: {migrator}")
run(["python3", str(migrator), "--db", DB, "--lanes", str(LANES)])

# Optional DB reset when filters change (for existing DBs only)
filter_reset_run = filters_changed and AUTO_RESET_DB_ON_FILTER_CHANGE and not first_run
if filter_reset_run:
    print("[filter] AUTO_RESET_DB_ON_FILTER_CHANGE is enabled - clearing event/plan tables", flush=True)
    try:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.executescript(
            """
            DELETE FROM plan_slot;
            DELETE FROM plan;
            DELETE FROM plan_meta;
            DELETE FROM plan_run;
            DELETE FROM event_lane;
            DELETE FROM feeds;
            DELETE FROM events;
            """
        )
        conn.commit()
        conn.close()
        print("[filter] Cleared events/plan tables due to filter configuration change", flush=True)
    except Exception as e:
        print(f"[filter] WARNING: Failed to clear tables on filter change: {e}", flush=True)

# Decide ingest horizon
initial_ingest_run = first_run or filter_reset_run
days = 3 if initial_ingest_run else 1

if first_run:
    banner = "=== First Run: Initializing Database ==="
elif filter_reset_run:
    banner = "=== Filter change detected: Rebuilding DB view ==="
else:
    banner = "=== Refreshing Existing Database ==="
print(banner)

# -----------------------------
# Step 1: Ingest
# -----------------------------
print(f"Step 1/5: Ingesting ESPN Watch Graph ({days} days)...")
ingest = BIN / "ingest_watch_graph_all_to_db.py"
run(["python3", str(ingest), "--db", DB, "--days", str(days)])

# -----------------------------
# Step 2: Apply Filters
# -----------------------------
print("Step 2/5: Applying event filters...")
try:
    # Print filter summary again for clarity (already printed once above)
    print(event_filter.get_filter_summary())
    print()

    conn = sqlite3.connect(DB)
    included_event_ids = filter_events_from_db(conn, event_filter)

    if included_event_ids:
        cursor = conn.cursor()
        placeholders = ",".join("?" * len(included_event_ids))
        delete_query = f"DELETE FROM events WHERE id NOT IN ({placeholders})"
        cursor.execute(delete_query, included_event_ids)
        deleted_count = cursor.rowcount
        conn.commit()
        print(f"[filter] Removed {deleted_count} events that didn't pass filters", flush=True)
    else:
        print("[filter] WARNING: No events passed filters! All events excluded.", flush=True)

    conn.close()
except Exception as e:
    print(f"[filter] WARNING: Error applying filters: {e}", flush=True)
    print("[filter] Continuing without filtering (all events included)", flush=True)

# Persist the new filter signature for next run
try:
    FILTER_SIG_PATH.write_text(current_sig + "\n", encoding="utf-8")
except Exception as e:
    print(f"[filter] WARNING: Failed to write filter signature file: {e}", flush=True)

# -----------------------------
# Step 3: Build plan
# -----------------------------
print(f"Step 3/5: Building plan ({VALID_HOURS}h validity)...")
build_plan = BIN / "build_plan.py"
build_cmd = [
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

force_replan = filters_changed and AUTO_FORCE_REPLAN_ON_FILTER_CHANGE
if force_replan:
    print("[filter] AUTO_FORCE_REPLAN_ON_FILTER_CHANGE is enabled - forcing fresh plan (ignore sticky lanes)", flush=True)
    build_cmd.append("--force-replan")


run(build_cmd)

# -----------------------------
# Step 4: XMLTV
# -----------------------------
print("Step 4/5: Generating XMLTV EPG...")
xmltv = BIN / "xmltv_from_plan.py"
epg_path = str(Path(OUT) / "epg.xml")
run(["python3", str(xmltv), "--db", DB, "--out", epg_path])

# -----------------------------
# Step 5: M3U
# -----------------------------
print("Step 5/5: Generating M3U playlist...")
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
    """Lightweight XMLTV <programme> count without pulling in lxml."""
    try:
        with epg_file.open("r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for line in f if "</programme>" in line or "<programme " in line)
    except Exception:
        return 0


epg_file = Path(epg_path)
m3u_file = Path(m3u_path)
epg_ok = file_ok(epg_file)
m3u_ok = file_ok(m3u_file)
programme_count = count_programmes(epg_file) if epg_ok else 0

print("\n=== Refresh Complete ===")
print(f"Database: {DB}")
print(f"EPG file: {epg_file} {'✓' if epg_ok else '✗'}")
print(f"M3U file: {m3u_file} {'✓' if m3u_ok else '✗'}")
print(f"EPG programmes: {programme_count}")

if VC_BASE:
    base = VC_BASE.rstrip("/")
    epg_url = f"{base}/out/epg.xml"
    m3u_url = f"{base}/out/playlist.m3u"
    audit_url = f"{base}/out/filteraudit.html"
    print("Resolver endpoints:")
    print(f"  Health: {base}/health")
    print(f"  EPG:    {epg_url}")
    print(f"  M3U:    {m3u_url}")
    print(f"  Filter Audit: {audit_url}")
    print(f"  WhatsOn (all): {base}/whatson_all")

# -----------------------------
# Filter audit HTML report
# -----------------------------

def write_filter_audit_html(
    db_path: str,
    out_dir: str,
    filter_summary_text: str,
) -> None:
    """Write a simple human-readable filter audit report to /out/filteraudit.html."""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Basic metrics
        cur.execute("SELECT COUNT(*) FROM events")
        events_total = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM plan_slot")
        plan_slots = cur.fetchone()[0] or 0

        # Leagues snapshot
        cur.execute(
            """
            SELECT lower(league_name) AS league, COUNT(*) AS cnt
            FROM events
            GROUP BY league
            ORDER BY cnt DESC
            LIMIT 20
            """
        )
        leagues = cur.fetchall()

        # Languages
        cur.execute(
            """
            SELECT language, COUNT(*) AS cnt
            FROM events
            GROUP BY language
            ORDER BY cnt DESC
            """
        )
        languages = cur.fetchall()

        # Re-airs left in events
        cur.execute("SELECT COUNT(*) FROM events WHERE is_reair = 1")
        reairs_left = cur.fetchone()[0] or 0

        # Plan violations (hard-coded for now to match audit script)
        cur.execute(
            """
            SELECT 'bad_slots_league' AS metric, COUNT(*) AS cnt
            FROM plan_slot ps
            JOIN events e ON ps.event_id = e.id
            WHERE lower(e.league_name) LIKE '%ncaaw%'
               OR lower(e.league_name) LIKE '%women%'
            UNION ALL
            SELECT 'bad_slots_language_es', COUNT(*)
            FROM plan_slot ps
            JOIN events e ON ps.event_id = e.id
            WHERE lower(e.language) = 'es'
            UNION ALL
            SELECT 'bad_slots_reair', COUNT(*)
            FROM plan_slot ps
            JOIN events e ON ps.event_id = e.id
            WHERE e.is_reair = 1
            """
        )
        violations = cur.fetchall()

        conn.close()
    except Exception as e:
        print(f"[audit] WARNING: Failed to build filter audit HTML: {e}", flush=True)
        return

    out_path = Path(out_dir) / "filteraudit.html"

    try:
        with out_path.open("w", encoding="utf-8") as f:
            f.write("<!DOCTYPE html>\n<html><head><meta charset='utf-8'>\n")
            f.write("<title>ESPN4CC4C Filter Audit</title>\n")
            f.write(
                "<style>body{font-family:system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
                "margin:1.5rem;background:#0b1120;color:#e5e7eb;}"
                "h1,h2,h3{color:#facc15;}"
                "pre{background:#020617;border-radius:0.5rem;padding:1rem;white-space:pre-wrap;}"
                "table{border-collapse:collapse;margin-top:0.5rem;margin-bottom:1rem;}"
                "th,td{border:1px solid #1f2937;padding:0.25rem 0.5rem;font-size:0.875rem;}"
                "th{background:#111827;}"
                ".ok{color:#22c55e;}.warn{color:#f97316;}.bad{color:#ef4444;}"
                "</style>\n"
            )
            f.write("</head><body>\n")
            f.write("<h1>ESPN4CC4C Filter Audit</h1>\n")

            # Step 1
            f.write("<h2>Step 1: What filters are turned on?</h2>\n")
            f.write(
                "<p>This is the output of <code>EventFilter.get_filter_summary()</code>, "
                "based on your <code>FILTER_*</code> environment variables and "
                "<code>/app/filters.ini</code>.</p>\n"
            )
            f.write("<pre>\n")
            f.write(filter_summary_text.strip())
            f.write("\n</pre>\n")
            f.write(
                "<p style='font-size:0.85rem;color:#9ca3af;'>Note: during a normal refresh, "
                "events that do <em>not</em> match your filters are deleted from the "
                "<code>events</code> table. If you re-run the filters afterwards "
                "(like this audit does), all remaining events should pass.</p>\n"
            )

            # Step 2
            f.write("<h2>Step 2: What does the database look like after filtering?</h2>\n")
            f.write(
                "<p>These numbers show how many events survived filtering and how many "
                "plan slots are using them.</p>\n"
            )
            f.write("<table><tr><th>Metric</th><th>Value</th></tr>\n")
            f.write(f"<tr><td>events_total</td><td>{events_total}</td></tr>\n")
            f.write(f"<tr><td>plan_slots</td><td>{plan_slots}</td></tr>\n")
            f.write("</table>\n")
            f.write(
                "<p style='font-size:0.9rem;color:#9ca3af;'>"
                "<strong>events_total</strong> = how many events survived your filters.<br>"
                "<strong>plan_slots</strong> = how many schedule slots are using those events."
                "</p>\n"
            )

            # Leagues
            f.write("<h3>Leagues still present in events (top 20)</h3>\n")
            f.write("<table><tr><th>League</th><th>Count</th></tr>\n")
            for league, cnt in leagues:
                league_display = league if league else "&nbsp;"
                f.write(f"<tr><td>{league_display}</td><td>{cnt}</td></tr>\n")
            f.write("</table>\n")

            # Languages
            f.write("<h3>Languages still present in events</h3>\n")
            f.write("<table><tr><th>Language</th><th>Count</th></tr>\n")
            for lang, cnt in languages:
                lang_display = lang if lang else "&nbsp;"
                f.write(f"<tr><td>{lang_display}</td><td>{cnt}</td></tr>\n")
            f.write("</table>\n")

            # Re-airs left
            f.write(
                "Re-airs still present in events "
                "(should be <code>0</code> if <code>exclude_reair</code> is true): "
                f"<strong>{reairs_left}</strong><br>\n"
            )

            # Step 3
            f.write("<h2>Step 3: Prove that blocked stuff is not in the guide</h2>\n")
            f.write(
                "<p>Now we look at the actual plan (what shows up in the guide). "
                "If your filters are working correctly, the checks below should all be "
                "<span class='ok'>0</span>.</p>\n"
            )
            f.write("<table><tr><th>Check</th><th>Count</th></tr>\n")
            for metric, cnt in violations:
                cls = "ok" if cnt == 0 else "bad"
                f.write(f"<tr><td>{metric}</td><td class='{cls}'>{cnt}</td></tr>\n")
            f.write("</table>\n")

            f.write(
                "<p>If all the numbers above are <strong>0</strong>, then:<br>"
                "&#x2705; Your filters are ON (Step 1)<br>"
                "&#x2705; The database only contains allowed events (Step 2)<br>"
                "&#x2705; The guide/plan is not using any blocked content (Step 3)</p>\n"
            )

            f.write("</body></html>\n")

        print(f"[audit] Wrote filter audit report to {out_path}", flush=True)
    except Exception as e:
        print(f"[audit] WARNING: Failed to write filter audit HTML: {e}", flush=True)
        return

# After generating the EPG/M3U and summary, write the audit HTML too.
write_filter_audit_html(DB, OUT, filter_summary)



# Exit non-zero if critical artifacts missing (so orchestrators can alert)
if not (epg_ok and m3u_ok):
    abort("Artifacts missing or empty. See logs above.", code=2)
