#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-${VC_RESOLVER_BASE_URL:-http://127.0.0.1:8094}}"
LAN="${BASE#http://}"; LAN="${LAN#https://}"
XML_URL="http://${LAN}/out/epg.xml"
XML="$(curl -fsS "$XML_URL" 2>/dev/null || true)"

TOTAL=$(printf '%s' "$XML" | grep -c '<programme ' || true)
STBY=$(  printf '%s' "$XML" | grep -c '<title>Stand By</title>' || true)
REAL=$(( TOTAL - STBY ))

echo "== sanity summary =="
echo "host=$(hostname)  programmes=${TOTAL:-0}  placeholders=${STBY:-0}  real=${REAL:-0}"

echo "== first non-placeholder title =="
printf '%s' "$XML" | awk '
  /<programme / { inside=1; title=""; next }
  inside && /<title>/ { sub(/.*<title>/,""); sub(/<\/title>.*/,""); title=$0 }
  /<\/programme>/ { if (inside && title != "Stand By" && title != "") { print title; exit }; inside=0 }
' || true
