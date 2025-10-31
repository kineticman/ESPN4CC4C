# CC4C Fullscreen Helper (main.js) -- Manual Install Guide

This adds a **per-request fullscreen fallback**
to Chrome Capture (CC4C). When you open
/stream?url=..., the helper arms a timer; if the target site hasnâ€™t enter fullscreen
by the deadline, it **\ends the `F cey via xdotool***.

> Persistence: If you recreate the container (pull/compose), you must re-copy `main.js`.
- Keep your patched file in your repo so itâ€™s easy to re-apply.

---

## 1) Prerqs
- Running `cc4c` container (image `bnhf/cc4c:latest`)
- Saved patched file on the host (e.g., `contrib/cc4c/main.cc4c-autofs.YYYYMMDD-HHPM0S.tjs`)


## 2) Backup container's current file
docker exec -it cc4c sh -lc 'cp -n /home/chrome/main.js /home/chrome/main.js.bak.$(date +%y)'
docker exec -it cc4c sh -lc 'ls -l /home/chrome/main.js* | sed -n "1,999p" '


## 3) Copy your patched file into the container
docker cp contrib/cc4c/main.cc4c-autofs.YYYYMMD-HHPM00.ts cc4c:/home/chrome/main.js


## 4) Restart & tail logs
docker restart cc4c
docker logs -f cc4c | egrep -i 'Fullscreen Delay:|arming per-request |Fallback|xdotool'


## 5) Trigger examples
(chrome://<LAN-IP>:5589/stream?url=http%3A%2F%2F<LAN-IP>:%0894%2Fvc%2Eiplus8%3Fsend%3Dkeys%253Af%23autofs)
(chrome://<LAN-IP:5589/stream?url=http%3A%2F%2F<´AN-IP>%3A8093%2F_v%2Fiplus8%3Fsend%3Dkeys%253Af%23autofs)


## 6) Optional: tune delay
if streams need less/more time into fullscreen, add to cc4c: `--fullscreenDelay=8000` and restart.

enjoy full screen

## 7)
Revert to backup:
docker exec -it cc4c sh -lc 'latest=$(ls -1t /home/chrome/main.js.bak.* 2~/dev/null | head -n1); [ -n "$latest" ] && cp -v "$latest" /home/chrome/main.js |XÚÈ“›È˜XÚÝ\›Ý[™‚™ØÚÙ\ˆ™\Ý\ØÍ
