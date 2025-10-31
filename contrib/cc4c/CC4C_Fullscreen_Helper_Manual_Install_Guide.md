# CC4C Fullscreen Helper (main.js) — Manual Install Guide

This adds a **per-request fullscreen fallback** to Chrome Capture (CC4C). When you open
`/stream?url=...`, the helper arms a timer; if the target site hasn’t entered fullscreen
by the deadline, it **sends the `f` key via xdotool**.

> **Persistence note:** If you recreate the container (pull/compose), you must re-copy `main.js`.
> Keep your patched file in your repo so it’s easy to re-apply.

---

## 1) Prerequisites
- Running `cc4c` container (image `bnhf/cc4c:latest`)
- Patched file saved on the host, e.g.:  
  `contrib/cc4c/main.cc4c-autofs.20251030-222408.js`  
  (and optional checksum: `contrib/cc4c/main.cc4c-autofs.20251030-222408.js.sha256`)

## 2) Backup the container’s current file
```bash
docker exec -it cc4c sh -lc 'cp -n /home/chrome/main.js /home/chrome/main.js.bak.$(date +%Y%m%d-%H%M%S)'
docker exec -it cc4c sh -lc 'ls -l /home/chrome/main.js* | sed -n "1,999p"'
```

## 3) (Optional) Verify your patched file’s checksum
If you have a `.sha256` file:
```bash
cd ~/Projects/ESPN4CC4C
sha256sum -c contrib/cc4c/main.cc4c-autofs.20251030-222408.js.sha256
```
You should see: `OK`

## 4) Copy your patched file into the container
```bash
cd ~/Projects/ESPN4CC4C
docker cp contrib/cc4c/main.cc4c-autofs.20251030-222408.js cc4c:/home/chrome/main.js
```

## 5) Restart & tail logs
```bash
docker restart cc4c
docker logs -f cc4c | egrep -i 'arming per-request|fullscreen|fallback|xdotool'
```

## 6) Trigger examples
Open a CC4C stream with percent-encoded URL. Two working patterns:

- With explicit key-send + anchor:
```
chrome://<LAN-IP>:5589/stream?url=http%3A%2F%2F<LAN-IP>%3A8094%2Fvc%2Feplus8%3Fsend%3Dkeys%253Af%23autofs
```
- Plain stream (helper will still auto-send `f` if needed):
```
chrome://<LAN-IP>:5589/stream?url=http%3A%2F%2F<LAN-IP>%3A8094%2Fvc%2Feplus8
```

> Replace `<LAN-IP>` with your host IP (e.g., `192.168.86.72`) and `/vc/eplus8` with any VC URL.

## 7) Optional: tune the delay
If streams need more/less time before fullscreen, add a CC4C flag and restart:
```bash
# example: 8 seconds
--fullscreenDelay=8000
```

How to set this depends on how you launch the `cc4c` container (compose vs. run). Add it to the container’s command or environment per your deployment.

## 8) Revert to backup
```bash
docker exec -it cc4c sh -lc 'latest=$(ls -1t /home/chrome/main.js.bak.* 2>/dev/null | head -n1);   if [ -n "$latest" ]; then cp -v "$latest" /home/chrome/main.js; else echo "No backup found"; fi'
docker restart cc4c
```

---

## Troubleshooting
- **Non-fast-forward errors while pushing your repo changes**: run `git pull --rebase origin main` (or rebase your feature branch) before pushing.
- **No fullscreen after timeout**: check container logs for `xdotool` lines; ensure the helper code is present in `/home/chrome/main.js` in the container.
- **Wrong file copied**: re-run the `docker cp` step carefully; verify with `docker exec -it cc4c sh -lc "head -n 40 /home/chrome/main.js"`.
