#!/usr/bin/env bash
set -Eeuo pipefail
NEW="v3.9"

git rev-parse --is-inside-work-tree >/dev/null || { echo "Not in a git repo"; exit 1; }
echo "[bump] repo: $(pwd)  branch: $(git rev-parse --abbrev-ref HEAD)"

write_version () {
  local f="$1"; [ -f "$f" ] || { echo "[skip] $f not found"; return 0; }
  cp -a "$f" "$f.bak.$(date +%Y%m%d-%H%M%S)"
  python3 - "$f" "$NEW" <<'PY'
import re, sys
p, new = sys.argv[1], sys.argv[2]
s = open(p,'r',encoding='utf-8').read()
# widen strict vX.Y.Z tag match to vX.Y or vX.Y.Z if present
s = re.sub(r'(ESPN4CC_TAG_MATCH",\s*)r"v\[0-9\]\*\\.\[0-9\]\*\\.\[0-9\]\*"\)',
           r'\1r"v[0-9]+\.[0-9]+(\.[0-9]+)?" )', s)
# set VERSION line if present
s = re.sub(r'^(VERSION\s*=\s*")[^"]+(")', rf'\1{new}\2', s, flags=re.M)
open(p,'w',encoding='utf-8').write(s)
print(f"[ok] version set in {p} -> {new}")
PY
}

# 1) version.py (root + bin/)
write_version version.py
write_version bin/version.py

# 2) README pin (if present)
if [ -f README.md ]; then
  sed -i 's/--branch v3\.[0-9]\+/--branch v3.9/g' README.md || true
  sed -i 's/\bv3\.[0-9]\+\b/v3.9/g' README.md || true
  echo "[ok] README.md pinned to v3.9"
else
  echo "[skip] README.md not found"
fi

# 3) env defaults
grep -q '^VC_M3U_PATH=' .env         || echo 'VC_M3U_PATH=/app/out/playlist.m3u' >> .env
[ -f env.example ] && grep -q '^VC_M3U_PATH=' env.example || { [ -f env.example ] && echo 'VC_M3U_PATH=/app/out/playlist.m3u' >> env.example; }

# 4) bootstrap default ref (if present)
if [ -f bootstrap.sh ]; then
  if grep -q '^GIT_REF=' bootstrap.sh; then
    sed -i 's/^GIT_REF=.*/GIT_REF="${GIT_REF:-v3.9}"/' bootstrap.sh || true
  else
    awk 'NR==1{print; print "GIT_REF=\"${GIT_REF:-v3.9}\""; next}1' bootstrap.sh > .b.tmp && mv .b.tmp bootstrap.sh
    chmod +x bootstrap.sh
  fi
  echo "[ok] bootstrap default set to v3.9"
else
  echo "[skip] bootstrap.sh not found"
fi

# 5) commit + tag + push
git add -A
git commit -m "release: v3.9 (version bump; docs/env/bootstrap pin)" || echo "[info] nothing to commit"
git fetch --tags -q
git tag -a v3.9 -m "v3.9" || echo "[info] tag v3.9 already exists"
git push origin HEAD
git push origin v3.9 || echo "[info] tag push skipped (exists)"

# 6) restart resolver to pick up env (optional)
if grep -q 'services:.*espn4cc' docker-compose.yml 2>/dev/null; then
  docker compose restart espn4cc || true
fi

echo "[done] v3.9 ready"
