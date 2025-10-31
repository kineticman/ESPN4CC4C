#!/usr/bin/env bash
# espn4cc4c_mustdo_patch.sh
# Apply ONLY the must-do patches with backups.
# Usage: bash espn4cc4c_mustdo_patch.sh   (run from repo root)

set -Eeuo pipefail

timestamp() { date +"%Y%m%d-%H%M%S"; }
TS="$(timestamp)"
BACKUP_DIR="./_mustdo_backups_${TS}"
mkdir -p "$BACKUP_DIR"

log()  { printf "[mustdo] %s\n" "$*"; }
warn() { printf "[mustdo:warn] %s\n" "$*" >&2; }

_find_one() {
  # $1 = filename
  if [ -f "./bin/$1" ]; then printf "./bin/%s" "$1"; return 0; fi
  if [ -f "./$1" ]; then printf "./%s" "$1"; return 0; fi
  local found; found="$(find . -maxdepth 4 -type f -name "$1" | head -n1 || true)"
  [ -n "$found" ] && printf "%s" "$found" || return 1
}

_backup_file() {
  local p="$1"
  if [ ! -f "$p" ]; then warn "skip backup (not found): $p"; return 0; fi
  local rel="${p#./}"; local d="${BACKUP_DIR}/$(dirname "$rel")"
  mkdir -p "$d"; cp -a "$p" "$d/"; log "backed up: $p -> $d/"
}

# 1) db_migrate.py — seed 20010+, ESPN+ EPlus n, group ESPN+ VC
patch_db_migrate() {
  local f; f="$(_find_one db_migrate.py)" || { warn "db_migrate.py not found"; return 0; }
  _backup_file "$f"
  python3 - "$f" <<'PY'
import re, sys
path = sys.argv[1]
src = open(path, 'r', encoding='utf-8').read()

if "ESPN+ EPlus" in src and "start_chno = 20010" in src:
    print("[py] db_migrate.py: seed_channels already updated")
    sys.exit(0)

m = re.search(r'^(def\s+seed_channels\s*\([^)]*\)\s*:\s*\n)', src, flags=re.M)
if not m:
    print("[py] db_migrate.py: seed_channels() not found; no change")
    sys.exit(0)

lines = src.splitlines(True)
start_pos = m.start(1); pos = 0; def_idx = None
for i, L in enumerate(lines):
    if pos == start_pos:
        def_idx = i; break
    pos += len(L)

indent = len(lines[def_idx]) - len(lines[def_idx].lstrip(' '))
base = ' ' * indent
def lead(s): return len(s) - len(s.lstrip(' '))

end_idx = len(lines)
for j in range(def_idx+1, len(lines)):
    L = lines[j]
    if not L.strip(): continue
    if lead(L) <= indent and (L.lstrip().startswith('def ') or L.lstrip().startswith('class ')):
        end_idx = j; break

new_block = f"""{base}def seed_channels(cur, lanes: int):
{base}    \"\"\"Seed channels if table empty (ESPN+ conventions).
{base}    chno starts at 20010; names 'ESPN+ EPlus <n>'; group 'ESPN+ VC'.\"\"\"
{base}    try:
{base}        c = cur.execute("SELECT COUNT(*) FROM channel").fetchone()[0]
{base}    except Exception:
{base}        c = 0
{base}    if c:
{base}        return 0
{base}    start_chno = 20010
{base}    rows = []
{base}    for i in range(1, lanes + 1):
{base}        chno = start_chno + (i - 1)
{base}        name = f"ESPN+ EPlus {{i}}"
{base}        rows.append((chno, name, "ESPN+ VC", 1))
{base}    cur.executemany(
{base}        "INSERT INTO channel(chno,name,group_name,active) VALUES(?,?,?,?)",
{base}        rows
{base}    )
{base}    return len(rows)
"""
patched = "".join(lines[:def_idx]) + new_block + "".join(lines[end_idx:])
open(path, 'w', encoding='utf-8').write(patched)
print("[py] db_migrate.py: seed_channels updated")
PY
}

# 2) build_plan.py — guard version import
patch_build_plan() {
  local f; f="$(_find_one build_plan.py)" || { warn "build_plan.py not found"; return 0; }
  _backup_file "$f"
  python3 - "$f" <<'PY'
import re, sys
path = sys.argv[1]
src = open(path, 'r', encoding='utf-8').read()

if "RUNTIME_VERSION" in src and "BUILD_VERSION" in src and "from version import" not in src:
    print("[py] build_plan.py: version import already guarded")
    sys.exit(0)

# Remove direct import if present
src = re.sub(r'^[ \t]*from[ \t]+version[ \t]+import[^\n]*\n', '', src, flags=re.M)

# Insert guard after import block
lines = src.splitlines(True); ins = 0
for i, L in enumerate(lines):
    s = L.strip()
    if s.startswith('#!') or 'coding' in s: continue
    if s.startswith('import ') or s.startswith('from ') or s == '' or s.startswith('#'):
        ins = i + 1; continue
    break

guard = (
    "try:\n"
    "    from version import get_version, VERSION as BUILD_VERSION\n"
    "    RUNTIME_VERSION = get_version()\n"
    "except Exception:\n"
    "    BUILD_VERSION = \"unknown\"\n"
    "    RUNTIME_VERSION = \"unknown\"\n"
)
patched = "".join(lines[:ins]) + guard + "".join(lines[ins:])
open(path, 'w', encoding='utf-8').write(patched)
print("[py] build_plan.py: guarded version import inserted")
PY
}

# 3) m3u_from_plan.py — env defaults + post-parse env overrides
patch_m3u_from_plan() {
  local f; f="$(_find_one m3u_from_plan.py)" || { warn "m3u_from_plan.py not found"; return 0; }
  _backup_file "$f"
  python3 - "$f" <<'PY'
import re, sys
p = sys.argv[1]
src = open(p, 'r', encoding='utf-8').read()

# Add env-driven defaults header once
if "DEFAULT_RESOLVER" not in src:
    lines = src.splitlines(True); ins = 0
    for i, L in enumerate(lines):
        s = L.strip()
        if s.startswith('import ') or s.startswith('from ') or s == '' or s.startswith('#!') or 'coding' in s or s.startswith('#'):
            ins = i + 1; continue
        break
    header = (
        "import os as _os\n"
        "DEFAULT_RESOLVER = _os.getenv('VC_RESOLVER_BASE_URL') or _os.getenv('VC_RESOLVER_ORIGIN') or 'http://127.0.0.1:8094'\n"
        "DEFAULT_CC_HOST  = _os.getenv('CC_HOST', '127.0.0.1')\n"
        "try:\n"
        "    DEFAULT_CC_PORT  = int(_os.getenv('CC_PORT','5589'))\n"
        "except Exception:\n"
        "    DEFAULT_CC_PORT = 5589\n"
        "M3U_GROUP_TITLE = _os.getenv('M3U_GROUP_TITLE','ESPN+ VC')\n"
    )
    src = "".join(lines[:ins]) + header + "".join(lines[ins:])

# Replace argparse defaults (best-effort patterns)
src = re.sub(r"(add_argument\(\s*['\"]--resolver-base['\"][^)]*?default\s*=\s*)(['\"][^'\")]+['\"]|\d+)",
             r"\1DEFAULT_RESOLVER", src, flags=re.S)
src = re.sub(r"(add_argument\(\s*['\"]--cc-host['\"][^)]*?default\s*=\s*)(['\"][^'\")]+['\"]|\d+)",
             r"\1DEFAULT_CC_HOST", src, flags=re.S)
src = re.sub(r"(add_argument\(\s*['\"]--cc-port['\"][^)]*?default\s*=\s*)(['\"][^'\")]+['\"]|\d+)",
             r"\1DEFAULT_CC_PORT", src, flags=re.S)
src = re.sub(r"(add_argument\(\s*['\"][^-]*group[^'\"]*['\"][^)]*?default\s*=\s*)(['\"][^'\")]+['\"]|\d+)",
             r"\1M3U_GROUP_TITLE", src, flags=re.S|re.I)

# Post-parse env overrides once
if "##__POST_PARSE_ENV_OVERRIDE__" not in src:
    src = re.sub(
        r"(\bargs\s*=\s*parser\.parse_args\([^)]*\)\s*\n)",
        r"\1##__POST_PARSE_ENV_OVERRIDE__\n"
        r"try:\n"
        r"    _env = __import__('os').environ\n"
        r"    _rb = _env.get('VC_RESOLVER_BASE_URL') or _env.get('VC_RESOLVER_ORIGIN')\n"
        r"    if _rb and hasattr(args, 'resolver_base'):\n"
        r"        args.resolver_base = _rb\n"
        r"    if _env.get('CC_HOST') and hasattr(args, 'cc_host'):\n"
        r"        args.cc_host = _env['CC_HOST']\n"
        r"    if _env.get('CC_PORT') and hasattr(args, 'cc_port'):\n"
        r"        try: args.cc_port = int(_env['CC_PORT'])\n"
        r"        except Exception: pass\n"
        r"    _gt = _env.get('M3U_GROUP_TITLE')\n"
        r"    for cand in ('group', 'group_title', 'm3u_group', 'm3u_group_title'):\n"
        r"        if _gt and hasattr(args, cand): setattr(args, cand, _gt)\n"
        r"except Exception:\n"
        r"    pass\n",
        src, count=1
    )

open(p, 'w', encoding='utf-8').write(src)
print("[py] m3u_from_plan.py: env defaults + overrides applied")
PY
}

log "Backup dir: $BACKUP_DIR"
patch_db_migrate
patch_build_plan
patch_m3u_from_plan
log "Done. Review changes with: git --no-pager diff -- . || true"
