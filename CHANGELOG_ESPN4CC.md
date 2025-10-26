# Changelog
All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project (informally) uses [Semantic Versioning](https://semver.org/)—or a date-based tag when that’s more convenient.

## [Unreleased]
- TBD

## [v2025.10.25] — 2025-10-25
### Added
- `tools/vc_diag.py`: programme & channel counts (DB vs XML), `.env.plan` autodetect, route discovery via `/openapi.json`, quiet error mode, tidy summary.
- `contrib/systemd/`: templated `vc-resolver-v2@.service`, `vc-plan@.service`, `vc-plan@.timer`.
- `scripts/make_systemd_templates.sh`: scaffold + optional install to `/etc/systemd/system` with placeholder substitution.
- `Makefile`: `systemd-install`, `systemd-status`, `plan-run`, `resolver-restart`, `diag`, etc.

### Changed
- `README.md`: modernized layout (project overview, Makefile and systemd quickstart, diagnostics).

### Notes
- Services sandboxed with `ProtectSystem=full`, `PrivateTmp=true`, and `ReadWritePaths=${PROJECT_DIR}`.
- Resolver endpoints available at: `/health`, `/epg.xml`, `/playlist.m3u`, `/vc/<lane>`, `/vc/<lane>/debug`.

[Unreleased]: https://github.com/kineticman/ESPN4CC4C/compare/v2025.10.25...HEAD
[v2025.10.25]: https://github.com/kineticman/ESPN4CC4C/releases/tag/v2025.10.25
