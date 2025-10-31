#!/usr/bin/env bash
set -Eeuo pipefail
echo "== file presence =="
req=(
  bin/build_plan.py
  bin/db_migrate.py
  bin/m3u_from_plan.py
  bin/xmltv_from_plan.py
  bin/vc_resolver.py
  bin/config.py
  bin/ingest_lib.py
  bin/ingest_watch_graph_all_to_db.py
)
missing=0
for f in "${req[@]}"; do
  if [ -f "$f" ]; then echo " ok  $f"; else echo " !!  MISSING: $f"; missing=1; fi
done
echo "== python import smoke =="
python3 - <<'PY'
import importlib.util, sys, os
# Make bin importable like in the container
sys.path.insert(0, os.path.abspath("bin"))

files = [
  "bin/build_plan.py","bin/db_migrate.py","bin/m3u_from_plan.py","bin/xmltv_from_plan.py",
  "bin/vc_resolver.py","bin/config.py","bin/ingest_lib.py","bin/ingest_watch_graph_all_to_db.py"
]
bad=0
for p in files:
    if not os.path.exists(p):
        print(f"[skip] {p} (missing)"); bad=1; continue
    try:
        spec = importlib.util.spec_from_file_location(os.path.basename(p).replace('.py',''), p)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)  # noqa
        print(f"[ok] import {p}")
    except Exception as e:
        bad=1; print(f"[err] import {p}: {e}")
sys.exit(bad)
PY
rc=$?
if [ $rc -ne 0 ]; then
  echo "== FAIL: fix missing/broken files above =="; exit $rc
fi
echo "== OK =="
