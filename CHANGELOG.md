# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.1.3] - 2026-04-21

### Fixed
- **Bandwidth gauge "Configuration error"**: removed `device_class:
  data_rate` from the bandwidth template sensor. HA's `data_rate` device
  class only accepts canonical units (`bit/s`, `Mbit/s`, `MB/s`, etc.);
  the sensor's `Mbps` unit isn't in that allow-list and made the gauge
  card refuse to render.
- **Now Playing "Configuration error" cards (4×)**: removed the
  duplicate per-stream `button-card` metadata block. Each stream now
  renders as a single `mini-media-player` (`full-cover-fanart` artwork,
  scrolling info, progress bar built in), eliminating the brittle
  `auto-entities` → nested-options → `this.entity_id` substitution chain
  that was failing in the secondary card. Cleaner, fewer dependencies.
- **Recently Added "Entity not found"**: the `input_boolean` /
  `input_select` integrations are loaded lazily by HA, so on a fresh
  install where the user has no helpers our `async_create_item` calls
  silently no-op'd. We now force-load both integrations via
  `async_setup_component` before adding our items, and surface failures
  as warnings instead of debug logs.
- **Empty `New Movies` / `New Episodes` / `New Albums` cards**: the
  per-section conditionals now also require the sensor's state to be
  non-zero / non-unknown, and the filter `entities` row only renders
  when the helper actually exists.

### Changed
- **Frontend dependencies down to 3** (was 4): `button-card` is no
  longer required. Required cards are now `auto-entities`,
  `mini-media-player`, `upcoming-media-card`. README quick-install
  table and Repairs check updated accordingly.

### Notes
- Existing installs with v2.1.2's hash tracking will auto-update the
  dashboard on first reload after upgrade. Older installs (≤ v2.1.1)
  still need the one-shot **Reset dashboard to bundled version** toggle
  in the integration's Configure page to pick up these fixes.

## [2.1.2] - 2026-04-21

### Added
- **Smart dashboard upgrade**: the integration now records a SHA-256 hash
  of the dashboard config it last wrote into Lovelace storage. On the next
  setup it compares this hash to the current storage payload:
  - If they match (user hasn't edited the dashboard) the new bundled YAML
    is written automatically, so dashboard fixes ship with each release.
  - If they differ (user has edited) the dashboard is left in place and a
    log message explains how to opt back in.
- **`Reset dashboard to bundled version` option** (Settings → Devices &
  Services → Plex Dashboard → Configure). When ticked, the next reload
  force-overwrites the Lovelace storage payload with the bundled YAML and
  then auto-clears the toggle.

### Notes
- Existing v2.0.x / v2.1.0 / v2.1.1 installs have no recorded hash, so the
  dashboard appears as "edited" to the new logic. Use the new "Reset
  dashboard" toggle once to pick up the v2.1.1 fixes (broken gauge, broken
  Now Playing cards, graceful empty states), after which subsequent
  upgrades flow through automatically.

## [2.1.1] - 2026-04-21

### Fixed
- **Bandwidth gauge "Configuration error":** the
  `sensor.plex_total_bandwidth_mbps` template returned a whitespace-padded
  string from its `{% else %}` branch, which the `gauge` card couldn't
  parse as numeric. Tightened Jinja whitespace and added
  `device_class: data_rate` + `state_class: measurement` so the value is
  always a clean float.
- **Now Playing "Configuration error" (×2):** removed
  `shortcuts.buttons[].data.entity_id: this.entity_id` from the
  mini-media-player options block. Auto-entities does not substitute
  `this.entity_id` inside nested `data:` keys, so the resulting card
  config was invalid. The shortcut services already target the card's
  own entity by default.

### Changed
- **Libraries section** is now graceful when the Plex integration hasn't
  exposed library sensors: `auto-entities` uses `show_empty: false`, and
  a hint card explains how to enable them under Plex → Configure.
- **Recently Added section** is now graceful when the optional
  `sensor.plex_recently_added_*` entities (from the
  `plex_recently_added` custom integration) don't exist. Each
  upcoming-media-card is wrapped in a template-condition for entity
  existence, and a fallback markdown card points to the optional HACS
  integration.

## [2.1.0] - 2026-04-21

### Changed
- **Reduced required HACS frontend cards from 6 to 4.** Removed
  dependencies on `mushroom-template-card`, `mushroom-chips-card`, and
  `bar-card`. The bundled dashboard now uses built-in `gauge`, `tile`,
  `markdown`, and `entities` cards instead.
- Required cards are now: `auto-entities`, `button-card`,
  `mini-media-player`, `upcoming-media-card`.

### Added
- README "Quick install" table with one-click My-Home-Assistant deep
  links for each of the four remaining required cards.
- Consolidated Repair: a single `missing_frontend_cards` issue lists
  every missing card with a clickable HACS deep link, instead of one
  Repair per card.

### Removed
- Per-card `missing_card_<element>` Repairs (cleaned up automatically
  on first run after upgrade).

## [2.0.1] - 2026-04-21

### Fixed
- `_async_check_frontend_cards`: use `LOVELACE_DATA` HassKey and access
  `.resources` as an attribute. `LovelaceData` is a dataclass, not a
  dict, so `.get("resources")` raised `AttributeError` and broke
  `async_setup_entry` on the second restart.
- `_async_register_dashboard` was called without its required
  `dashboard_yaml_text` argument; now reads the just-written dashboard
  YAML from disk and passes its contents.
- `OptionsFlow`: stop assigning `self.config_entry` (forbidden in
  modern HA); copy data/options into private fields instead. Also
  import `OptionsFlow` directly from `config_entries`.

## [2.0.0] - 2026-04-21

### Changed
- **BREAKING:** Repo is now a HACS **Integration** (`plex_dashboard`)
  instead of a HACS Theme. The theme, dashboard YAML, and package YAML
  are bundled inside the integration and installed automatically.
- Install flow is now: HACS → Integration → Add Integration →
  pick Plex slug → restart. No more `install.sh` step.

### Added
- `custom_components/plex_dashboard/` integration with config flow
- Auto-detection of Plex server slug from existing `sensor.plex_*` entities
- Auto-substitution of `PLEX_SERVER_NAME` placeholder in bundled YAML
- Runtime registration of the Lovelace dashboard (storage mode)
- Auto-creation of `input_boolean` and `input_select` helpers via the
  helper components (visible under Settings → Helpers)
- Repairs entries for missing HACS frontend cards
  (`mini-media-player`, `button-card`, `auto-entities`, `bar-card`,
  `upcoming-media-card`, `card-mod`)
- Repair entry when `homeassistant.packages:` is not enabled
- Options flow to re-run the install steps (e.g. after switching servers)
- Hassfest workflow added to validation

### Removed
- `themes/` directory (theme is now bundled in the integration)
- `extras/` directory (dashboard + package are now bundled)
- `scripts/install.sh` (no longer needed)
- HACS Theme submission to `hacs/default` is obsolete

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
