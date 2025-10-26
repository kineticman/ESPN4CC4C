# Systemd templates (resolver + plan)

Templates for ESPN4CC4C:

- `vc-resolver-v2.service` — FastAPI resolver (uvicorn).
- `vc-plan.service` — one-shot plan builder (writes XMLTV).
- `vc-plan.timer` — runs the plan job every 30 minutes.

They read host-specific settings from `.env.plan` (gitignored). Example:

```ini
DB=/home/brad/Projects/ESPN4CC/data/eplus_vc.sqlite3
OUT=/home/brad/Projects/ESPN4CC/out/epg.xml
RESOLVER_BASE=http://127.0.0.1:8094
TZ=America/New_York
VALID_HOURS=72
LANES=40
ALIGN=30
MIN_GAP_MINS=30
PORT=8094
```

## Install on a host (as user `brad`)

```bash
PROJECT_DIR=/home/brad/Projects/ESPN4CC
sudo install -Dm0644 contrib/systemd/vc-resolver-v2.service /etc/systemd/system/vc-resolver-v2@.service
sudo install -Dm0644 contrib/systemd/vc-plan.service       /etc/systemd/system/vc-plan@.service
sudo install -Dm0644 contrib/systemd/vc-plan.timer         /etc/systemd/system/vc-plan@.timer

sudo sed -i "s|\${PROJECT_DIR}|$PROJECT_DIR|g" /etc/systemd/system/vc-resolver-v2@.service
sudo sed -i "s|\${PROJECT_DIR}|$PROJECT_DIR|g" /etc/systemd/system/vc-plan@.service

sudo systemctl daemon-reload
sudo systemctl enable --now vc-resolver-v2@brad.service
sudo systemctl enable --now vc-plan@brad.timer
```

## Troubleshooting

- **NAMESPACE / ReadWritePaths**: ensure `ReadWritePaths=${PROJECT_DIR}` matches your folder.
- **venv path**: ExecStart uses `${PROJECT_DIR}/.venv/bin/python`.
- **ports**: tweak `PORT` in `.env.plan` if 8094 is taken.
- **logs**: `journalctl -u vc-resolver-v2@brad -o cat | tail -n 200`
