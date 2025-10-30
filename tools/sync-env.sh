#!/usr/bin/env bash
set -euo pipefail
cp env.example .env.example
echo "Synced env.example -> .env.example"
git add env.example .env.example
