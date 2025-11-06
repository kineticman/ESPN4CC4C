cd ~/Projects/ESPN4CC4C

# 0) See where you are
git status -sb

# 1) Switch to the existing cleanup branch (your staged renames come with you)
git switch chore/repo-clean-2025-11-06 || git checkout chore/repo-clean-2025-11-06

# 2) Ensure target dirs exist (idempotent)
mkdir -p docs/api scripts contrib/legacy data dist logs out
touch data/.gitkeep dist/.gitkeep logs/.gitkeep out/.gitkeep

# 3) Remove the stray "=" file (it's untracked per your output)
rm -f "="

# 4) Write/update .gitignore (safe to overwrite; this is what the script intended)
cat > .gitignore <<'GIT'
# Python
__pycache__/
*.pyc
*.pyo

# venvs
.venv/
venv/

# OS
.DS_Store

# Build / dist
dist/
*.zip
*.tgz
*.sha256
SHA256SUMS.txt

# Runtime outputs
data/
logs/
out/

# Local overrides
docker-compose.override.yml
GIT

# 5) Link docs from README if not already present (idempotent)
grep -q "docs/api/endpoints.md" README.md || awk '
  BEGIN{added=0}
  /^# / && added==0 {print; print ""; print "## API Endpoints"; print ""; print "- See [docs/api/endpoints.md](docs/api/endpoints.md) for `/whatson` and `/whatson_all`."; added=1; next}
  {print}
' README.md > README.md.tmp && mv README.md.tmp README.md

# 6) Stage everything and commit
git add -A
git commit -m "Chore: repo cleanup (docs/api/endpoints.md, scripts/, ignore runtime outputs, remove stray '=')"

# 7) Push branch
git push -u origin chore/repo-clean-2025-11-06
