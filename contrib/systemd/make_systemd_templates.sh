#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="${HOME}/Projects/ESPN4CC"
TARGET_USER="$(id -un)"
DO_INSTALL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-dir) PROJECT_DIR="$2"; shift 2;;
    --user)        TARGET_USER="$2"; shift 2;;
    --install)     DO_INSTALL=1; shift;;
    -h|--help)     echo "Usage: $0 [--project-dir PATH] [--user USER] [--install]"; exit 0;;
    *) echo "Unknown arg: $1" >&2; exit 2;;
  esac
done
mkdir -p "${PROJECT_DIR}/contrib/systemd" "${PROJECT_DIR}/scripts"
# copy from repo into /etc with placeholder substitution
if [[ $DO_INSTALL -eq 1 ]]; then
  sudo install -Dm0644 "${PROJECT_DIR}/contrib/systemd/vc-resolver-v2.service" /etc/systemd/system/vc-resolver-v2@.service
  sudo install -Dm0644 "${PROJECT_DIR}/contrib/systemd/vc-plan.service"       /etc/systemd/system/vc-plan@.service
  sudo install -Dm0644 "${PROJECT_DIR}/contrib/systemd/vc-plan.timer"         /etc/systemd/system/vc-plan@.timer
  sudo sed -i "s|\${PROJECT_DIR}|${PROJECT_DIR}|g" /etc/systemd/system/vc-resolver-v2@.service
  sudo sed -i "s|\${PROJECT_DIR}|${PROJECT_DIR}|g" /etc/systemd/system/vc-plan@.service
  sudo systemctl daemon-reload
  sudo systemctl enable --now vc-resolver-v2@${TARGET_USER}.service
  sudo systemctl enable --now vc-plan@${TARGET_USER}.timer
  systemctl status vc-resolver-v2@${TARGET_USER}.service --no-pager || true
  systemctl list-timers --all | grep -E 'vc-plan@|NEXT' || true
else
  echo "Templates written. To install: bash scripts/make_systemd_templates.sh --install"
fi
