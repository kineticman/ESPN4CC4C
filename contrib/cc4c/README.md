# CC4C Fullscreen Helper (contrib)

- **File:** `main.cc4c-autofs.20251030-222408.js`
- **Source:** extracted from running `cc4c` container
- **Note:** includes per-request fallback that sends `F` via `xdotool` after `fullscreenDelay` if site logic doesn't trigger.

## How to use
Replace the CC4C container's `/home/chrome/main.js` with this file, then restart the container:
```bash
docker cp contrib/cc4c/<filename>.js cc4c:/home/chrome/main.js
docker restart cc4c
```

## URL format (works with ESPN4CC4C resolver URLs)
Use ChromeCapture schema, pointing at your resolver URL. Examples:
```
chrome://<LAN-IP>:5589/stream?url=http%3A%2F%2F<LAN-IP>%3A8094%2Fvc%2Feplus8%3Fsend%3Dkeys%253Af%23autofs
chrome://<LAN-IP>:5589/stream?url=http%3A%2F%2F<LAN-IP>%3A8093%2Fvc%2Feplus8%3Fsend%3Dkeys%253Af%23autofs
```

## Default delay
- The container may log `Fullscreen Delay: 15000ms`; adjust if needed via yargs flag `--fullscreenDelay` in your runner.
