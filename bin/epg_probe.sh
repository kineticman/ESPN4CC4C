#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://127.0.0.1:8094}"
LAN="${BASE#http://}"; LAN="${LAN#https://}"
XML="$(mktemp)"
trap 'rm -f "$XML"' EXIT
curl -fsS "$BASE/out/epg.xml" -o "$XML" 2>/dev/null || true
TOTAL=$(grep -c '<programme ' "$XML" 2>/dev/null || echo 0)
STBY=$(grep -c '<title>Stand By</title>' "$XML" 2>/dev/null || echo 0)
REAL=$(( TOTAL - STBY ))
echo "== sanity summary =="
echo "host=$(hostname)  programmes=${TOTAL}  placeholders=${STBY}  real=${REAL}"
echo "== first non-placeholder title =="
awk '
  /<programme / { inside=1; title=""; next }
  inside && /<title>/ { gsub(/.*<title>|<\/title>.*/,""); title=$0 }
  /<\/programme>/ { if (title != "Stand By" && title != "") { print title; exit }; inside=0 }
' "$XML" || true
