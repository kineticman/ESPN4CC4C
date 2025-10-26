#!/usr/bin/env bash
# ESPN4CC full integrity sweep: DB ↔ resolver ↔ XML/M3U
set -euo pipefail

RESOLVER="${RESOLVER:-http://127.0.0.1:8094}"
DB="${DB:-data/eplus_vc.sqlite3}"
XML_LOCAL="${XML_LOCAL:-out/epg.xml}"
M3U_LOCAL="${M3U_LOCAL:-out/playlist.m3u}"
XML_SRV=/tmp/epg.from.server.xml
M3U_SRV=/tmp/m3u.from.server.m3u

echo "[1/7] endpoints (expect 200s)"
/usr/bin/printf "health:      " ; curl -s -o /dev/null -w "%{http_code}\n" "$RESOLVER/health"
/usr/bin/printf "epg.xml:     " ; curl -s -o /dev/null -w "%{http_code}\n" "$RESOLVER/epg.xml"
/usr/bin/printf "playlist.m3u:" ; curl -s -o /dev/null -w "%{http_code}\n" "$RESOLVER/playlist.m3u"

echo; echo "[2/7] plan window covers now (expect OK)"
sqlite3 "$DB" <<'SQL'
.headers off
.mode column
SELECT
  'plan_id='||pr.id,
  'valid_from='||pr.valid_from_utc,
  'valid_to='||pr.valid_to_utc,
  'now='||datetime('now'),
  'covers_now='||
  CASE
    WHEN datetime(replace(substr(pr.valid_from_utc,1,19),'T',' ')) <= datetime('now')
     AND datetime(replace(substr(pr.valid_to_utc,  1,19),'T',' '))  > datetime('now')
    THEN 'OK' ELSE 'OUT_OF_WINDOW'
  END
FROM plan_run pr
ORDER BY pr.id DESC
LIMIT 1;
SQL

echo; echo "[3/7] counts: DB vs XML (expect equal programmes & channels)"
sqlite3 "$DB" <<'SQL'
.headers off
.mode list
SELECT 'db: plan_id='||(SELECT MAX(plan_id) FROM plan_slot);
SELECT 'db: programmes_total='||COUNT(*) FROM plan_slot WHERE plan_id=(SELECT MAX(plan_id) FROM plan_slot);
SELECT 'db: channels_active='||COUNT(*) FROM channel WHERE active=1;
SQL

curl -s "$RESOLVER/epg.xml" -o "$XML_SRV"
python3 - <<PY
import xml.etree.ElementTree as ET, sys
root = ET.parse("$XML_SRV").getroot()
print("xml: programmes_total =", len(root.findall('programme')))
print("xml: channels_total   =", len(root.findall('channel')))
PY

echo; echo "[4/7] resolver vs DB: event_id @ now per lane (expect all MATCH)"
if ! command -v jq >/dev/null 2>&1; then
  echo "jq not found – skipping this step"; 
else
  while read -r lane; do
    db_evt=$(sqlite3 "$DB" "
      WITH latest(pid) AS (SELECT MAX(plan_id) FROM plan_slot)
      SELECT COALESCE(event_id,'-') FROM plan_slot, latest
      WHERE plan_id=latest.pid
        AND channel_id='$lane'
        AND datetime(replace(substr(start_utc,1,19),'T',' '))<=datetime('now')
        AND datetime(replace(substr(end_utc,  1,19),'T',' ')) > datetime('now')
      LIMIT 1;")
    api_evt=$(curl -s "$RESOLVER/vc/$lane/debug" | jq -r '.slot.event_id // "-"')
    if [[ "$api_evt" == "$db_evt" ]]; then
      printf "%-8s  %-6s  DB:%s  API:%s\n" "$lane" "MATCH" "$db_evt" "$api_evt"
    else
      printf "%-8s  %-10s  DB:%s  API:%s\n" "$lane" "MISMATCH" "$db_evt" "$api_evt"
    fi
  done < <(sqlite3 "$DB" "SELECT id FROM channel WHERE active=1 ORDER BY chno;")
fi

echo; echo "[5/7] playlist wiring: sample first 5 entries (accept any scheme)"
curl -s "$RESOLVER/playlist.m3u" | awk 'BEGIN{c=0} /^#EXTINF/ || /^[a-zA-Z]+:\/\// {print; if ($0 ~ /^[a-zA-Z]+:\/\//) c++; if (c==5) exit}'

echo; echo "[6/7] MD5 equality: resolver-served vs local out/ (expect identical)"
curl -s "$RESOLVER/epg.xml" -o "$XML_SRV"
curl -s "$RESOLVER/playlist.m3u" -o "$M3U_SRV"
md5sum "$XML_SRV" "$XML_LOCAL" || true
md5sum "$M3U_SRV" "$M3U_LOCAL" || true

echo; echo "[7/7] spot-check: titles now for three LCNs (XML via resolver)"
python3 - <<'PY'
import urllib.request as u, xml.etree.ElementTree as ET, datetime as dt
xml=u.urlopen("http://127.0.0.1:8094/epg.xml",timeout=5).read()
root=ET.fromstring(xml)
def title_for_lcn(L):
    cid=None
    for ch in root.findall('channel'):
        if ch.findtext('lcn')==str(L):
            cid=ch.attrib.get('id'); break
    now=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    title="(none)"
    for p in root.findall('programme'):
        if p.attrib.get('channel')==cid and p.attrib['start']<=now and p.attrib['stop']>now:
            title=p.findtext('title') or "(untitled)"; break
    return cid,title
for L in (20010,20024,20040):
    cid,title = title_for_lcn(L)
    print(f"LCN {L}: channel_id={cid}  title_now={title}")
PY

echo; echo "=== DONE ==="
