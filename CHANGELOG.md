# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- README: added one-click My Home Assistant install link
- README: documented HACS default index pending status
- README: clarified that custom-repository install is a temporary fallback

## [1.0.0] - 2026-04-21

Initial public HACS-installable release.

### Added

#### Dashboard (`extras/dashboards/plex_dashboard.yaml`)
- 4-column responsive `sections` view layout
- Server overview card: status indicator, active/paused/buffering stream
  chips, total bandwidth bar, action buttons (scan all, pause all)
- Auto-discovered library counts list driven by `sensor.plex_library_*`
- Auto Now Playing column: one rich card per active stream via
  `auto-entities` + `mini-media-player` + custom `button-card`
  (poster, title, S/E or artist/album, user, state, progress bar)
- Client list: every Plex client (active + idle), sorted by activity,
  with toggles for paused / offline visibility
- Recently Added section: Movies / TV / Music with filter pill driven by
  `input_select.plex_recently_added_filter`
- Second view "Coming Soon": Radarr + Sonarr upcoming releases via
  `upcoming-media-card`

#### Package (`extras/packages/plex_dashboard.yaml`)
- `sensor.plex_active_streams` with `playing/paused/buffering` attrs
- `sensor.plex_active_client_ids` (active `media_player.plex_*` ids)
- `sensor.plex_total_bandwidth_mbps` (Tautulli, falls back to 0)
- `sensor.plex_server_online`
- `binary_sensor.plex_anything_playing`
- `script.plex_scan_all_libraries`
- `script.plex_pause_all`
- `input_boolean.plex_show_paused`
- `input_boolean.plex_show_offline_clients`
- `input_select.plex_recently_added_filter` (All / Movies / TV / Music)

#### Theme (`themes/plex-dashboard.yaml`)
- HACS-installable Plex amber dark theme matched to the dashboard

#### Tooling
- `scripts/install.sh` one-line installer for the release zip
- `.github/workflows/validate.yml`: HACS Action (theme) + yamllint + shellcheck
- `.github/workflows/release.yml`: builds `plex_dashboard_extras.zip` on `v*` tag push
- `hacs.json` manifest, MIT `LICENSE`, `CONTRIBUTING.md`, `.gitignore`
