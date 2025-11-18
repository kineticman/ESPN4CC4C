### v4.8.2

**Highlights**
- **Filtering focus:** API endpoints and docs updated so testers can verify event filtering quickly.
- **API tweaks:** `/whatson/{lane}`, `/whatson_all`, `/deeplink/{lane}` now include clearer fields; deeplink responses can include the full `sportscenter://` URL when available.
- **Config UX:** `.ini` editing guidance added; filters now honor language hints and smarter defaults.
- **Bootstrap (Windows):** fixes to stop PowerShell parsing errors, add M3U/XML post-checks, and improve error messages.
- **Pipeline:** ingest + XMLTV generator updated (image scraping hooks, language support, XML enrich options).
- **Stability:** misc logging & minor fixes based on community feedback.

**Testing pointers**
- Open `http://<host>:8094/whatson_all` to see everything currently in DB.
- Try `http://<host>:8094/whatson/9?format=json` for a lane snapshot (deeplink present if available).
- Edit `filters.ini` and rebuild; confirm the API reflects your changes.

**Upgrade**
```bash
git fetch --tags
git checkout v4.8.2
# or pull main if you track main
```
