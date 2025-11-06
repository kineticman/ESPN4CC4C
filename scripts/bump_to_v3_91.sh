#!/usr/bin/env bash
set -Eeuo pipefail
NEW="v3.91"

git rev-parse --is-inside-work-tree >/dev/null || { echo "Not a git repo"; exit 1; }
echo "[bump] repo: $(pwd)  branch: $(git rev-parse --abbrev-ref HEAD)"

write_version () {
  local f="$1"; [ -f "$f" ] || { echo "[skip] $f not found"; return 0; }
  cp -a "$f" "$f.bak.$(date +%Y%m%d-%H%M%S)"
  python3 - "$f" "$NEW" <<'PY'
import re, sys
p, new = sys.argv[1], sys.argv[2]
s = open(p,'r',encoding='utf-8').read()
# allow tags vX.Y or vX.Y.Z
s = re.sub(r'(ESPN4CC_TAG_MATCH",\s*)r"v\[0-9\]\*\\.\[0-9\]\*\\.\[0-9\]\*"\)',
           r'\1r"v[0-9]+\.[0-9]+(\.[0-9]+)?" )', s)
# set VERSION if present
s = re.sub(r'^(VERSION\s*=\s*")[^"]+(")', rf'\1{new}\2', s, flags=re.M)
open(p,'w',encoding='utf-8').write(s)
print(f"[ok] version -> {new} in {p}")
PY
}

# 1) version.py (root + bin/)
write_version version.py
write_version bin/version.py

# 2) README pin (if exists)
if [ -f README.md ]; then
  sed -i 's/--branch v3\.[0-9]\+/--branch v3.91/g' README.md || true
  sed -i 's/\bv3\.[0-9]\+\b/v3.91/g' README.md || true
  echo "[ok] README pinned to v3.91"
fi

# 3) env defaults
grep -q '^VC_M3U_PATH=' .env         || echo 'VC_M3U_PATH=/app/out/playlist.m3u' >> .env
[ -f env.example ] && grep -q '^VC_M3U_PATH=' env.example || { [ -f env.example ] && echo 'VC_M3U_PATH=/app/out/playlist.m3u' >> env.example; }

# 4) bootstrap default ref (if present)
if [ -f bootstrap.sh ]; then
  if grep -q '^GIT_REF=' bootstrap.sh; then
    sed -i 's/^GIT_REF=.*/GIT_REF="${GIT_REF:-v3.91}"/' bootstrap.sh || true
  else
    awk 'NR==1{print; print "GIT_REF=\"${GIT_REF:-v3.91}\""; next}1' bootstrap.sh > .b.tmp && mv .b.tmp bootstrap.sh
    chmod +x bootstrap.sh
  fi
  echo "[ok] bootstrap default set to v3.91"
fi

# 5) commit + tag + push
git add -A
git commit -m "release: v3.91 (version bump; docs/env/bootstrap pin)" || echo "[info] nothing to commit"
git fetch --tags -q
git tag -a v3.91 -m "v3.91" || echo "[info] tag v3.91 already exists"
git push origin HEAD
git push origin v3.91 || echo "[info] tag push skipped (exists)"

# 6) restart resolver to pick up env (optional)
if grep -q 'services:.*espn4cc' docker-compose.yml 2>/dev/null; then
  docker compose restart espn4cc || true
fi

echo "[done] v3.91 ready"
