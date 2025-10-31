#!/usr/bin/env bash
set -Eeuo pipefail

NEW="v3.8"

# Ensure we are in a git repo
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "[bump] ERROR: not in a git repo"; exit 1; }

echo "[bump] repo: $(pwd)"
echo "[bump] branch: $(git rev-parse --abbrev-ref HEAD)"

# Helper: add file only if it exists
add_if_exists() { [ -f "$1" ] && git add "$1" || true; }

# version.py (always write)
echo "[bump] write version.py -> ${NEW}"
cat > version.py <<EOF
# auto-generated
VERSION = "${NEW}"
def get_version() -> str:
    return VERSION
EOF

# README.md (only if present)
if [ -f README.md ]; then
  echo "[bump] update README.md pin to ${NEW}"
  sed -i 's/--branch v3\.[0-9]\+/--branch v3.8/g' README.md || true
  sed -i 's/\bv3\.[0-9]\+\b/v3.8/g' README.md || true
else
  echo "[bump] README.md not found (skipping)"
fi

# .env.example (only if present; create if you want)
if [ -f .env.example ]; then
  echo "[bump] ensure VC_M3U_PATH in .env.example"
  grep -q '^VC_M3U_PATH=' .env.example || printf '\nVC_M3U_PATH=/app/out/playlist.m3u\n' >> .env.example
else
  echo "[bump] .env.example not found (skipping)"
fi

# bootstrap.sh (only if present)
if [ -f bootstrap.sh ]; then
  echo "[bump] set bootstrap default GIT_REF=${NEW}"
  if grep -q '^GIT_REF=' bootstrap.sh; then
    sed -i 's/^GIT_REF=.*/GIT_REF="${GIT_REF:-v3.8}"/' bootstrap.sh || true
  else
    awk 'NR==1{print; print "GIT_REF=\"${GIT_REF:-v3.8}\""; next}1' bootstrap.sh > .b.tmp && mv .b.tmp bootstrap.sh
    chmod +x bootstrap.sh
  fi
else
  echo "[bump] bootstrap.sh not found (skipping)"
fi

# Commit whatever exists
add_if_exists version.py
add_if_exists README.md
add_if_exists .env.example
add_if_exists bootstrap.sh

if git diff --cached --quiet; then
  echo "[bump] nothing to commit"
else
  git commit -m "release: v3.8 (version.py; docs/env/bootstrap pin)"
fi

# Tag and push
git fetch --tags -q
if git rev-parse -q --verify "${NEW}" >/dev/null; then
  echo "[bump] tag ${NEW} already exists locally (skipping create)"
else
  git tag -a "${NEW}" -m "${NEW}"
fi

echo "[bump] push branch + tag"
git push origin HEAD
git push origin "${NEW}"

echo "[bump] done: ${NEW}"
