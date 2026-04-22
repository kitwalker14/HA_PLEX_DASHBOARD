# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.3.2] - 2026-04-22

### Fixed
- **Hassfest CI validation now passes.** The Repair issue description
  for `lovelace_internals_unavailable` contained a literal GitHub URL,
  which Hassfest rejects ("the string should not contain URLs, please
  use description placeholders instead"). The URL is now passed via a
  new `{issue_url}` translation placeholder; user-visible text is
  unchanged.

## [2.3.1] - 2026-04-22

### Fixed
- **Recently Added cards now auto-configure on first run / upgrade.**
  v2.3.0 introduced three typed sensor fields with sensible defaults
  (`sensor.plex_recently_added_movie` / `_show` / `_artist`), but
  installs whose Plex server name slugifies to a doubled-prefix
  (e.g. `sensor.plex_plex_recently_added_movie`) or any other
  non-default form would render the dashboard's `else:` markdown
  fallback for every card after upgrading from v2.2.x.
- `async_setup_entry` now sniffs the state machine during setup: for
  any of the three typed keys whose configured value doesn't resolve
  to a sensor exposing a `data` list attribute, it picks the first
  `sensor.*recently_added*_{movie,show,artist}` that does, persists
  the resolved value back into `entry.data`, and logs the substitution
  at INFO level. The Configure dialog continues to reflect (and let
  the user override) whatever is in use.

## [2.3.0] - 2026-04-22

### Fixed
- **Recently Added cards (New Movies / New Episodes / New Music) no
  longer render as empty boxes.** The previous implementation relied
  on three template sensors that filtered the legacy unified
  `plex_recently_added` sensor by inspecting `runtime` / `tmdb_id` /
  `genres` attributes. The current `plex_recently_added` HACS
  integration (v0.6+) ships separate per-type sensors out of the box
  (`*_recently_added_movie`, `_show`, `_artist`) and no longer exposes
  those classification attributes, so the heuristic always produced
  empty results.

### Changed
- **Three new typed config-flow fields** replace the single
  `recently_added_sensor` field: **Movies sensor**, **TV / Shows
  sensor**, **Music / Artist sensor**. The integration auto-detects
  candidates by entity-id suffix (`_movie` / `_show` / `_artist`) and
  presents them as dropdowns in the config and options flows. Free-text
  fallback is preserved for non-standard naming.
- **Dashboard YAML** now points each `upcoming-media-card` directly at
  the user-selected typed sensor via placeholder substitution
  (`PLEX_RECENTLY_ADDED_{MOVIES,TV,MUSIC}_SENSOR`). Each card is
  wrapped in `auto-entities` with an `else:` markdown fallback so a
  missing sensor (e.g. a music-only Plex server with no movies sensor)
  collapses to a setup hint instead of an empty progress bar.
- **Bundled package YAML** drops the three heuristic template sensors
  (`sensor.plex_recently_added_movies` / `_tv` / `_music`). They were
  ineffective on plex_recently_added v0.6+ and are no longer needed
  now that the dashboard reads the typed source sensors directly.
- **Deployment-health Repair** now validates each of the three typed
  sensors independently and lists which specific cards will be empty,
  with a per-bucket suggestion of detected candidate entity-ids.

### Backward compatibility
- Existing config entries that still carry the legacy
  `recently_added_sensor` field continue to load without error -- the
  field is silently ignored. The constants `CONF_RECENTLY_ADDED_SENSOR`
  and `DEFAULT_RECENTLY_ADDED_SENSOR` remain in `const.py` for the same
  reason (no migration required). Re-open **Settings → Devices &
  Services → Plex Dashboard → Configure** to pick the per-type sensors
  from the auto-detected dropdowns; then toggle **Reset dashboard to
  bundled version** to pick up the new dashboard YAML on the next reload.

## [2.2.5] - 2026-04-22

### Changed
- **Manifest dependencies trimmed** to just `lovelace`. Previous list
  included `frontend`, `input_boolean`, `input_select`, and `repairs`,
  which are not integration-level dependencies (the helpers are loaded
  on demand from the bundled package YAML; `repairs` is a core helper,
  not a domain). Reduces spurious "dependency not found" errors on
  minimal HA configs.
- **`create_helpers` toggle removed from the config & options flows.**
  It has been a no-op since 2.1.5 (helpers ship as YAML in the package
  file). The constant is retained in `const.py` so existing config
  entries that still carry the key continue to load without migration.

### Fixed
- **Atomic file writes.** Theme/package/dashboard YAML files are now
  written via `<file>.tmp` + `os.replace`, guaranteeing the target
  is never left half-written if HA is killed mid-install (power loss,
  OOM, container kill). Previously a truncated YAML could surface as
  a hard-to-diagnose startup error.
- **Defensive Lovelace internals import.** The integration uses
  `homeassistant.components.lovelace.dashboard.{DashboardsCollection,
  LovelaceStorage}` to register the dashboard in storage mode -- these
  are private APIs that have moved before. The import is now wrapped
  in `try/except ImportError`; if a future HA release refactors them,
  setup no longer fails silently. Instead a new Repair issue
  (`lovelace_internals_unavailable`) tells the user exactly how to
  register the dashboard manually from the YAML file already on disk.
- **Defensive `CONF_ALLOW_SINGLE_WORD` import.** Same rationale --
  the constant is conditionally included in the dashboard create
  payload only when present in the running HA version.

## [2.2.4] - 2026-04-22

### Added
- **Recently Added cards now display actual media.** Previously the
  dashboard pointed at `sensor.plex_recently_added_movies` / `_tv` /
  `_music` -- entities the HACS `plex_recently_added` integration does
  not create. That integration publishes a single unified sensor whose
  `data` attribute contains all media types mixed together. The
  package YAML now ships three template sensors
  (`sensor.plex_recently_added_movies`, `_tv`, `_music`) that filter
  the unified source by heuristic:
  - **TV** = item has a non-empty `episode` field
  - **Movies** = no episode, has `tmdb_id`, non-empty `genres`, runtime ≥ 40 min
  - **Music** = everything else (music videos, concerts, short clips,
    demos, YT rips)
  Each filtered sensor exposes the same `data` attribute schema
  `upcoming-media-card` reads, so the three cards now render poster
  grids with titles, dates, and summaries.
- **Configurable Recently Added source sensor.** The
  `plex_recently_added` integration produces different entity_ids
  depending on the Plex server name (e.g. `sensor.plex_recently_added`
  for a default name, `sensor.plex_plex_recently_added` for a server
  named `plex.example.com`). Config flow now includes a "Recently
  added source sensor" field with auto-detection: any sensor matching
  `sensor.*recently_added*` with a `data` list attribute is offered in
  a dropdown. Default: `sensor.plex_recently_added`.
- **Deployment-health Repair detects missing source sensor.** If the
  configured source sensor is absent or has no `data` attribute, a new
  informational finding points the user at the HACS install link and
  the Configure dialog, and lists any auto-detected candidates.

### Changed
- Dashboard Recently Added card titled "New Albums" renamed to "New
  Music" to match the new filter sensor's broader scope (music videos,
  concerts, YT clips, etc. -- not strictly albums).

## [2.2.3] - 2026-04-22

### Changed
- **Libraries section now hides orphaned Plex library sensors.** When a
  Plex Media Server integration is removed and re-added, HA's entity
  registry can leave behind stale rows that produce two patterns of
  duplicate entity_ids: doubled-prefix
  (`sensor.plex_<slug>_plex_<slug>_library_*`) and numeric-suffix
  (`sensor.plex_<slug>_library_<lib>_2` ... `_99`). The dashboard's
  Libraries `auto-entities` filter now excludes both patterns so users
  see one clean row per library out of the box, regardless of how many
  orphans linger in the entity registry.

### Added
- **Deployment-health Repair surfaces orphan library sensors.** A new
  finding reports the orphan count and tells the user how to clean
  them via Settings → Devices & Services → Entities. The dashboard
  works fine without cleanup, but the orphans clutter the entity
  registry so they're worth removing.

## [2.2.2] - 2026-04-22

### Fixed
- **Slug auto-stripping no longer breaks legitimately `plex_`-prefixed
  slugs.** v2.2.1 unconditionally stripped a leading `plex_` from the
  slug input -- but Plex servers whose name starts with `plex` (e.g.
  `plex.lwk.space`) legitimately slugify to `plex_lwk_space`, producing
  `sensor.plex_plex_lwk_space`. The new normalization checks the state
  machine: only strip a prefix if (a) the un-stripped slug does NOT
  resolve to an existing `sensor.plex_<slug>` entity, AND (b) the
  stripped form DOES. Otherwise the user's input is left alone.
- **Deployment-health Repair uses the same logic.** The "extra `plex_`
  prefix" finding now only fires when the stripped form actually
  resolves and the original doesn't, instead of misdiagnosing every
  `plex_*` slug as wrong.

## [2.2.1] - 2026-04-22

### Fixed
- **Slug field accepts `plex_<name>` and `sensor.plex_<name>` forms.**
  Both the initial config flow and the options-flow re-configure dialog
  now strip a leading `sensor.plex_` / `sensor.` / `plex_` prefix from
  the user-entered slug. Previously, pasting `plex_lwk_space` (an easy
  mistake — the field hint says "e.g. 'myplex' from sensor.plex_myplex"
  but it's tempting to paste the full prefix) caused the integration to
  look for `sensor.plex_plex_lwk_space` and fail every entity-existence
  check, including the `sensor.plex_<slug>` -> server-online template
  sensor. The new sanitization makes the field robust to all three
  common pasting patterns.

### Changed
- **Deployment health Repair detects the extra-`plex_`-prefix case
  specifically.** When the configured slug is `plex_<X>` and
  `sensor.plex_<X>` actually exists, the Repair message now calls out
  the exact fix ("change `plex_lwk_space` to `lwk_space`") instead of
  the generic "slug mismatch" message.

## [2.2.0] - 2026-04-22

### Added
- **New "Deployment health" Repair.** Detects and surfaces in one
  consolidated Repair entry: (a) Plex server slug mismatch (configured
  slug doesn't resolve to any `sensor.plex_<slug>`, with detected
  candidates listed), (b) no Plex library sensors enabled, (c) Tautulli
  not detected (bandwidth gauge will read 0), (d) neither Sonarr nor
  Radarr detected (Coming Soon view will show install hints). Each
  finding includes an actionable fix link. Repair clears automatically
  when issues are resolved.

### Changed
- **Full deployment-agnostic rewrite.** The dashboard now makes zero
  assumptions about the user's Plex server slug, optional integrations,
  or whether the package YAML helpers were installed. Every block uses
  one of: `custom:auto-entities` with `show_empty: false` + an `else:`
  fallback, glob entity filters, or defensive Jinja with `has_value()`
  guards. Missing pieces collapse cleanly instead of erroring.
- **Libraries section: glob filter (`sensor.plex_*_library_*`)** matches
  any Plex server slug, not just a hardcoded one. Previously the filter
  was `sensor.plex_library_*`, which never matched any real Plex
  integration entity (Plex creates them as
  `sensor.plex_<server_slug>_library_<library_name>`). The filter also
  now excludes the bundled package's `sensor.plex_*` template sensors so
  they don't accidentally appear in the Libraries list.
- **Plex Server tile, Bandwidth gauge, and server-action buttons** are
  now wrapped in `custom:auto-entities` so a missing
  `sensor.plex_server_online`, `sensor.plex_total_bandwidth_mbps`, or
  bundled scripts collapse cleanly instead of rendering red error tiles.
- **Quick stats markdown** uses `has_value()` guards on every state
  read, so missing template sensors render as `0` / `--` instead of
  `unknown`.
- **Coming Soon view (Radarr/Sonarr cards) wrapped in `auto-entities`
  with `else:` fallback markdown** — a missing
  `sensor.radarr_upcoming_media` / `sensor.sonarr_upcoming_media` now
  shows an "install the integration" hint instead of an empty card.
- **Settings entities card wrapped in auto-entities** — missing helpers
  collapse instead of rendering "Entity not found" rows.

### Fixed
- **`script.plex_pause_all` no longer errors when no streams are
  active.** Added a guard condition so the script only invokes
  `media_player.media_pause` when at least one Plex client is streaming
  (previously, tapping the button with nothing playing passed `None` as
  `entity_id` and raised in HA's service handler).

## [2.1.7] - 2026-04-22

### Fixed
- **Recently Added "Configuration error" tiles (real fix).** v2.1.6
  attempted to fix this by wrapping the conditionals in a
  `vertical-stack` -- that was the wrong diagnosis and the red tiles
  persisted. Live debugging on a user dashboard proved
  (a) `upcoming-media-card` works fine when used directly in a
  Sections-view grid (the Coming Soon view renders Radarr/Sonarr cards
  correctly even with missing sensors -- they just show empty progress
  bars), and (b) the same helper entities render fine in a plain
  `entities` card. The bug was specifically the
  `condition: template` blocks: in HA Sections-view layouts, conditional
  cards using template conditions render as red tiles regardless of
  whether they're nested in a vertical-stack.

### Changed
- **Recently Added section rewritten without conditionals.** The filter
  pill now uses `custom:auto-entities` with `show_empty: false` (handles
  missing helper gracefully). The 3 `upcoming-media-card` blocks are
  rendered directly with no wrapper -- if `sensor.plex_recently_added_*`
  doesn't exist, the card shows an empty progress bar (same behavior as
  the Coming Soon view). The "install plex_recently_added" markdown
  fallback was removed (it was tied to the conditional logic); see
  README for setup instructions instead.

## [2.1.6] - 2026-04-22

### Fixed
- **Recently Added section "Configuration error" tiles.** All five
  conditional cards in the Recently Added column (filter pill, Movies,
  TV, Music, fallback markdown) were rendering as "Configuration error"
  red tiles. Root cause: Home Assistant Sections-view grids
  (`type: grid`) do **not** support `type: conditional` as a direct
  child -- each grid child must be a layout-aware card, and conditional
  is not. The five conditionals are now wrapped in a single
  `vertical-stack` so the grid sees one card and lets the stack manage
  its conditional children. No user action required beyond reloading
  the dashboard YAML (Settings -> Devices & services -> Plex Dashboard
  -> Configure -> enable "Reset dashboard YAML on next reload").

## [2.1.5] - 2026-04-21

### Changed
- **Helpers are now defined in the package YAML** instead of being
  created programmatically at integration setup. Home Assistant core
  does not expose the `input_boolean` / `input_select` storage
  collections via `hass.data`, so programmatic creation was unreliable
  and could silently fail. The helpers now appear under
  Settings -> Devices & services -> Helpers as read-only YAML entries
  (reload-safe, never silently disappear).
- **Helpers renamed** to avoid colliding with any helpers a previous
  version may have created in `.storage`:
  - `input_boolean.plex_show_paused` ->
    `input_boolean.plex_dashboard_show_paused`
  - `input_boolean.plex_show_offline_clients` ->
    `input_boolean.plex_dashboard_show_offline_clients`
  - `input_select.plex_recently_added_filter` ->
    `input_select.plex_dashboard_recently_added_filter`
  If you have the old helpers from a prior version they will simply
  remain as orphaned entities -- delete them from
  Settings -> Devices & services -> Helpers if desired.
- **Now Playing card config simplified** to the bare minimum
  (`type`, `entity`, `artwork: cover`). Some `mini-media-player`
  sub-keys (`hide:`, `info: scroll`, `icon:`) appear to misbehave
  when passed through auto-entities' `this.entity_id` substitution.

## [2.1.4] - 2026-04-21

### Fixed
- **Now Playing "Configuration error" cards (root cause)**: per
  auto-entities documentation, the `options:` block (which receives the
  `this.entity_id` substitution) MUST live inside each
  `filter.include[]` entry. Previous versions had `options:` at the top
  level of `auto-entities`, which is silently ignored -- the card got a
  list of bare entities with no `type:` and rendered as "Configuration
  error" tiles. Now Playing now correctly emits one
  `mini-media-player` per active stream.
- **Libraries "Configuration error"** when no Plex library sensors
  exist: switched from `show_empty:false` + separate conditional hint
  to auto-entities' built-in `else:` fallback card. Some HA versions
  rendered the zero-entity entities-card as a config-error tile.
- **Recently Added "Configuration error" 2x2 grid**: the conditionals
  now also require the sensor to expose the `data` attribute (a
  non-empty list) that `upcoming-media-card` requires. A same-named
  sensor without that attribute would let the conditional pass but the
  card would error. Fallback markdown now also triggers on
  `data`-less sensors, not just missing entities.

### Notes
- v2.1.2's hash tracking will auto-update existing dashboards on the
  next reload after upgrade. No need to manually toggle Reset.

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
