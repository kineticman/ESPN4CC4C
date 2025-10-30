#!/usr/bin/env bash
set -Eeuo pipefail

# Default: DRY RUN (prints what would happen). Pass --apply to actually delete.
APPLY=0
if [[ "${1:-}" == "--apply" ]]; then
  APPLY=1
fi

shopt -s nullglob

must_be_repo_root() {
  [[ -f "README.md" && -f "docker-compose.yml" && -d "bin" && -d "out" ]] || {
    echo "Error: run from ESPN4CC4C repo root." >&2
    exit 1
  }
}

do_rm() {
  local paths=("$@")
  ((${#paths[@]}==0)) && return 0
  if ((APPLY)); then
    printf 'DELETE %s\n' "${paths[@]}"
    rm -rf -- "${paths[@]}"
  else
    printf 'WOULD DELETE %s\n' "${paths[@]}"
  fi
}

do_truncate_logs() {
  local files=(logs/*.log)
  ((${#files[@]}==0)) && return 0
  if ((APPLY)); then
    for f in "${files[@]}"; do
      : > "$f"
      echo "TRUNCATE $f"
    done
  else
    printf 'WOULD TRUNCATE %s\n' "${files[@]}"
  fi
}

must_be_repo_root

echo "== Cleanup (dry-run by default). Use '--apply' to actually delete =="

# 1) Generic backup droppings
bak_files=( ./*.bak.* ./*/*.bak.* )
do_rm "${bak_files[@]}"

# 2) Python caches
pycache_dirs=( $(find . -type d -name "__pycache__") )
do_rm "${pycache_dirs[@]}"

# 3) Ephemeral DB inspection bundles & dirs
do_rm out/db_inspect.tgz
inspect_dirs=( out/db_inspect_* )
do_rm "${inspect_dirs[@]}"

# 4) Trim EPG backups: keep newest 2, delete older
epg_backups=( $(ls -1t out/backups/epg_*.xml 2>/dev/null || true) )
if ((${#epg_backups[@]} > 2)); then
  # everything from the 3rd onward
  to_delete=( "${epg_backups[@]:2}" )
  do_rm "${to_delete[@]}"
else
  echo "Nothing to trim in out/backups (<=2 files present)."
fi

# 5) Old zip checksums or tgz in dist/out (keep as-is if current looks fine)
# (No action needed if you want to retain release artifacts; comment next two lines to skip entirely)
# dist_old=( $(ls -1t dist/*.zip 2>/dev/null | tail -n +2 || true) )
# do_rm "${dist_old[@]}"

# 6) Zero out logs but keep files
do_truncate_logs

# 7) Optional: remove sqlite journal files only if resolver is not running
# (Skipping destructive DB journal removal by default to be safe.)
echo "Skipped deleting data/*.sqlite3-(shm|wal) for safety."

echo "== Done. Re-run with '--apply' to execute deletions =="
