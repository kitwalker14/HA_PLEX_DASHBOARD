"""Plex Dashboard integration: zero-touch installer for HA Plex dashboard."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import yaml

from homeassistant.components.lovelace.const import (
    CONF_ICON,
    CONF_REQUIRE_ADMIN,
    CONF_SHOW_IN_SIDEBAR,
    CONF_TITLE,
    CONF_URL_PATH,
    LOVELACE_DATA,
)

# CONF_ALLOW_SINGLE_WORD has come and gone in HA's lovelace const module across
# versions. Import defensively so an upgrade that drops the constant doesn't
# break setup -- we only pass it when it exists.
try:
    from homeassistant.components.lovelace.const import (  # type: ignore[attr-defined]
        CONF_ALLOW_SINGLE_WORD,
    )
    _HAS_ALLOW_SINGLE_WORD = True
except ImportError:  # pragma: no cover - depends on HA version
    CONF_ALLOW_SINGLE_WORD = "allow_single_word"
    _HAS_ALLOW_SINGLE_WORD = False
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, issue_registry as ir

from .const import (
    CONF_DASHBOARD_URL_PATH,
    CONF_INSTALL_PACKAGE,
    CONF_INSTALL_THEME,
    CONF_PLEX_SLUG,
    CONF_REGISTER_DASHBOARD,
    CONF_RESET_DASHBOARD,
    DASHBOARD_FILENAME,
    DASHBOARD_OUTPUT_NAME,
    DASHBOARDS_OUTPUT_DIR,
    DATA_DIR,
    DATA_INSTALLED_DASHBOARD_HASH,
    DEFAULT_DASHBOARD_ICON,
    DEFAULT_DASHBOARD_TITLE,
    DEFAULT_DASHBOARD_URL_PATH,
    DOMAIN,
    HACS_DEEP_LINK,
    PACKAGE_FILENAME,
    PACKAGE_OUTPUT_NAME,
    PACKAGES_OUTPUT_DIR,
    PLACEHOLDER_SLUG,
    REQUIRED_FRONTEND_CARDS,
    THEME_FILENAME,
    THEME_OUTPUT_NAME,
    THEMES_OUTPUT_DIR,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = []


def _bundled_data_path(filename: str) -> Path:
    """Return absolute path to a file shipped in custom_components/.../data/."""
    return Path(__file__).parent / DATA_DIR / filename


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_file(target: Path, content: str) -> bool:
    """Write content to target atomically. Returns True if file was created/updated.

    Writes to a sibling ``<target>.tmp`` first then atomically renames it
    into place via ``os.replace``. This guarantees the destination is
    either the old content or the new content -- never a half-written
    truncated file -- even if the process is killed mid-write (power
    loss, OOM, container kill, etc).
    """
    if target.exists():
        try:
            existing = target.read_text(encoding="utf-8")
            if existing == content:
                return False
        except OSError:
            pass
    _ensure_dir(target.parent)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, target)
    except OSError:
        # Best-effort cleanup of partial tmp file before re-raising.
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return True


def _copy_with_substitution(
    src: Path, dest: Path, substitutions: dict[str, str]
) -> bool:
    """Copy src -> dest, replacing placeholder tokens. Returns True if changed."""
    text = src.read_text(encoding="utf-8")
    for token, value in substitutions.items():
        text = text.replace(token, value)
    return _write_file(dest, text)


def _hash_dashboard(config: dict | None) -> str:
    """Return a deterministic sha256 of a dashboard config dict.

    Uses canonical JSON (sorted keys, no whitespace) so cosmetic YAML/storage
    differences (key order, whitespace, anchors) don't affect the hash.
    """
    if not config:
        return ""
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """No YAML configuration; setup via config entry."""
    return True


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Plex Dashboard from a config entry."""
    data: dict[str, Any] = {**entry.data, **entry.options}
    slug: str = data[CONF_PLEX_SLUG]
    install_theme: bool = data.get(CONF_INSTALL_THEME, True)
    install_package: bool = data.get(CONF_INSTALL_PACKAGE, True)
    register_dashboard: bool = data.get(CONF_REGISTER_DASHBOARD, True)
    url_path: str = data.get(CONF_DASHBOARD_URL_PATH, DEFAULT_DASHBOARD_URL_PATH)

    config_dir = Path(hass.config.path())
    substitutions = {
        PLACEHOLDER_SLUG: slug,
    }

    # ---- Install YAML files (off-loop because of disk I/O) -----------------
    def _do_file_install() -> dict[str, bool]:
        results: dict[str, bool] = {}
        if install_theme:
            results["theme"] = _copy_with_substitution(
                _bundled_data_path(THEME_FILENAME),
                config_dir / THEMES_OUTPUT_DIR / THEME_OUTPUT_NAME,
                substitutions,
            )
        if install_package:
            results["package"] = _copy_with_substitution(
                _bundled_data_path(PACKAGE_FILENAME),
                config_dir / PACKAGES_OUTPUT_DIR / PACKAGE_OUTPUT_NAME,
                substitutions,
            )
        # The dashboard YAML is always written if we register the dashboard,
        # since the dashboard registration points to it.
        if register_dashboard:
            results["dashboard"] = _copy_with_substitution(
                _bundled_data_path(DASHBOARD_FILENAME),
                config_dir / DASHBOARDS_OUTPUT_DIR / DASHBOARD_OUTPUT_NAME,
                substitutions,
            )
        return results

    try:
        file_results = await hass.async_add_executor_job(_do_file_install)
    except OSError as err:
        _LOGGER.error("Plex Dashboard: failed writing files: %s", err)
        raise HomeAssistantError(f"Failed writing dashboard files: {err}") from err

    for kind, changed in file_results.items():
        _LOGGER.info(
            "Plex Dashboard: %s %s",
            kind,
            "installed/updated" if changed else "already up to date",
        )

    # ---- Register Lovelace dashboard ---------------------------------------
    if register_dashboard:
        dashboard_path = config_dir / DASHBOARDS_OUTPUT_DIR / DASHBOARD_OUTPUT_NAME
        try:
            dashboard_yaml_text = await hass.async_add_executor_job(
                dashboard_path.read_text, "utf-8"
            )
            await _async_register_dashboard(
                hass, entry, url_path, dashboard_yaml_text
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Plex Dashboard: could not auto-register dashboard (%s). "
                "Add manually under Settings -> Dashboards.",
                err,
            )

    # ---- Helpers --------------------------------------------------------
    # Helpers (input_boolean.plex_dashboard_show_paused,
    # input_select.plex_dashboard_recently_added_filter, etc.) are bundled
    # directly into plex_dashboard_package.yaml as YAML helpers. They appear
    # under Settings -> Helpers as read-only YAML entries. The legacy
    # CONF_CREATE_HELPERS flag is no longer exposed in the config flow but
    # is still accepted from existing config entries (silently ignored).

    # ---- Surface missing frontend cards as Repairs -------------------------
    await _async_check_frontend_cards(hass)

    # ---- Surface missing packages config as a Repair -----------------------
    if install_package and file_results.get("package"):
        await _async_check_packages_enabled(hass)

    # ---- Surface deployment-health gaps as a Repair ------------------------
    # (missing libraries, slug mismatch, optional integrations not detected)
    await _async_check_deployment_health(hass, entry)

    # Surface a one-time persistent notification with restart hint if any file
    # was newly installed (packages/themes only take effect after restart).
    if any(file_results.values()):
        await _async_notify_restart(hass, file_results)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry. Files are left in place intentionally."""
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the Lovelace dashboard we registered when the user deletes us.

    Without this, deleting the integration leaves a "Plex" entry in the
    sidebar forever, with nothing tying it back to this integration -- the
    user has to know to remove it by hand under Settings -> Dashboards.

    The YAML files written to /config are deliberately left in place: they
    are inert once the integration is gone, and the user may have edited
    them or be depending on the package's helpers.
    """
    if not entry.data.get(CONF_REGISTER_DASHBOARD, True):
        return

    url_path = entry.data.get(CONF_DASHBOARD_URL_PATH, DEFAULT_DASHBOARD_URL_PATH)

    # Must be HA's own collection: its change listener is what removes the
    # sidebar panel and deletes the dashboard's config store. Deleting from a
    # private instance would leave the panel up and, worse, HA's stale
    # in-memory copy would resurrect the entry on its next write.
    collection = _async_get_dashboards_collection(hass)
    if collection is None:
        _LOGGER.warning(
            "Plex Dashboard: could not reach the lovelace dashboards "
            "collection to remove dashboard '%s'. Remove it manually "
            "under Settings -> Dashboards.",
            url_path,
        )
        return

    item = next(
        (
            item
            for item in collection.async_items()
            if item.get(CONF_URL_PATH) == url_path
        ),
        None,
    )
    if item is None:
        _LOGGER.debug("Plex Dashboard: no dashboard '%s' to remove", url_path)
        return

    try:
        # The collection's listener handles frontend.async_remove_panel and
        # the config-store deletion, so we must not do either ourselves.
        await collection.async_delete_item(item["id"])
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Plex Dashboard: could not remove dashboard '%s' (%s). "
            "Remove it manually under Settings -> Dashboards.",
            url_path,
            err,
        )
        return

    _LOGGER.info("Plex Dashboard: removed dashboard '%s'", url_path)


# ---------------------------------------------------------------------------
# Lovelace dashboard registration (storage mode, fully runtime)
# ---------------------------------------------------------------------------
def _async_get_dashboards_collection(hass: HomeAssistant):
    """Return HA's authoritative storage DashboardsCollection, or None.

    HA's lovelace component keeps its DashboardsCollection as a local in
    ``async_setup`` and never publishes it on ``hass.data``. The only stable
    handle is the websocket command it registers, whose bound handler carries
    the collection. We must use *that* instance: it is the one carrying the
    ``storage_dashboard_changed`` listener that inserts the dashboard into
    ``hass.data[LOVELACE_DATA].dashboards`` and registers the sidebar panel,
    and it is the one whose in-memory view gets serialised on every save.
    Creating our own instance would both skip the panel registration and let
    HA's stale copy overwrite our entry on its next write.
    """
    try:
        handler, _schema = hass.data["websocket_api"]["lovelace/dashboards/list"]
        return handler.__self__.storage_collection
    except (KeyError, AttributeError, TypeError) as err:
        _LOGGER.debug("Could not resolve lovelace dashboards collection: %s", err)
        return None


async def _async_register_dashboard(
    hass: HomeAssistant,
    entry: ConfigEntry,
    url_path: str,
    dashboard_yaml_text: str,
) -> None:
    """Create or update a storage-mode Lovelace dashboard from YAML text.

    Behaviour on existing dashboards:

    * If the storage payload's hash matches the hash we recorded after our
      last write (stored in ``entry.data[DATA_INSTALLED_DASHBOARD_HASH]``),
      the user has not edited it -> we safely overwrite it with the new
      bundled YAML on integration upgrades.
    * If the user has set ``CONF_RESET_DASHBOARD`` in the options flow we
      force an overwrite regardless and then auto-clear the flag.
    * Otherwise we leave the dashboard alone to preserve user edits.
    """
    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        _LOGGER.debug("Plex Dashboard: lovelace not initialised yet, skipping register")
        return

    # Note: there is deliberately no import-availability probe here. Our only
    # real dependency is HA's dashboards collection, and that is checked by
    # the `collection is None` branch further down. Probing for the internal
    # lovelace.dashboard module would raise a false-positive Repair (and skip
    # registration) on any HA release that merely renames or moves that
    # module while leaving the websocket command we actually use intact.
    #
    # Clear a stale Repair if an older version of this integration raised it.
    ir.async_delete_issue(hass, DOMAIN, "lovelace_internals_unavailable")

    # Parse YAML off the loop
    def _parse() -> dict:
        return yaml.safe_load(dashboard_yaml_text) or {}

    try:
        dashboard_config = await hass.async_add_executor_job(_parse)
    except yaml.YAMLError as err:
        _LOGGER.error("Plex Dashboard: bundled dashboard YAML is invalid: %s", err)
        return

    new_hash = _hash_dashboard(dashboard_config)

    # Everything below must go through HA's own DashboardsCollection, never a
    # private instance of our own. Two independent reasons:
    #
    # 1) Panel registration. HA attaches a ``storage_dashboard_changed``
    #    listener to its collection; that listener is what builds the
    #    LovelaceStorage, files it under hass.data[LOVELACE_DATA].dashboards
    #    and calls frontend.async_register_built_in_panel. Drive a detached
    #    collection and none of that fires -- the dashboard stays invisible
    #    in the sidebar until HA is restarted.
    #
    # 2) Data loss. StorageCollection serialises its in-memory self.data.
    #    HA's collection never learns about an item created behind its back,
    #    so the next time the user adds/renames/deletes any dashboard in the
    #    UI, HA writes its stale view and our entry is dropped from
    #    .storage/lovelace_dashboards.
    collection = _async_get_dashboards_collection(hass)
    if collection is None:
        # Same Repair as a failed internals import: from the user's point of
        # view the outcome is identical (we cannot register the dashboard,
        # the YAML on disk still lets them add it by hand).
        ir.async_create_issue(
            hass,
            DOMAIN,
            "lovelace_internals_unavailable",
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="lovelace_internals_unavailable",
            translation_placeholders={
                "error": "dashboards collection unavailable",
                "url_path": url_path,
                "issue_url": "https://github.com/kitwalker14/HA_PLEX_DASHBOARD/issues",
            },
        )
        _LOGGER.error(
            "Plex Dashboard: cannot reach Home Assistant's lovelace "
            "dashboards collection. The dashboard YAML was still written "
            "to disk; add it manually under Settings -> Dashboards using "
            "URL path '%s'.",
            url_path,
        )
        return

    # hass.data[LOVELACE_DATA].dashboards is keyed by url_path and holds the
    # LovelaceStorage HA built for us. Its config store file key derives from
    # the collection-assigned id, not the url_path, so we must reuse this
    # object rather than construct our own.
    existing_storage = lovelace_data.dashboards.get(url_path)
    created = False

    if existing_storage is None:
        create_payload: dict[str, Any] = {
            CONF_URL_PATH: url_path,
            CONF_TITLE: DEFAULT_DASHBOARD_TITLE,
            CONF_ICON: DEFAULT_DASHBOARD_ICON,
            CONF_SHOW_IN_SIDEBAR: True,
            CONF_REQUIRE_ADMIN: False,
        }
        # Only include CONF_ALLOW_SINGLE_WORD on HA versions that ship it;
        # passing an unknown key trips lovelace's voluptuous schema on
        # versions that have removed it.
        if _HAS_ALLOW_SINGLE_WORD:
            create_payload[CONF_ALLOW_SINGLE_WORD] = True
        try:
            # async_create_item persists *and* awaits the change listener, so
            # by the time this returns the panel is registered and the
            # LovelaceStorage is in lovelace_data.dashboards.
            await collection.async_create_item(create_payload)
        except Exception as err:  # noqa: BLE001
            # Covers HomeAssistantError (e.g. url_already_exists when some
            # other panel squats our url_path) as well as schema errors.
            _LOGGER.warning(
                "Plex Dashboard: could not create dashboard entry %s: %s",
                url_path,
                err,
            )
            return

        created = True
        existing_storage = lovelace_data.dashboards.get(url_path)
        if existing_storage is None:
            _LOGGER.warning(
                "Plex Dashboard: dashboard entry %s was created but no "
                "storage was registered for it; skipping write.",
                url_path,
            )
            return

    if created:
        # A dashboard we just created has no config yet; async_load would
        # only raise. Treat it as empty so the write below is a plain
        # first-time registration.
        existing_config = None
    else:
        try:
            existing_config = await existing_storage.async_load(force=True)
        except Exception:  # noqa: BLE001
            existing_config = None

    force_reset = bool(entry.options.get(CONF_RESET_DASHBOARD, False))
    last_hash = entry.data.get(DATA_INSTALLED_DASHBOARD_HASH, "")
    existing_hash = _hash_dashboard(existing_config) if existing_config else ""

    if existing_config and not force_reset:
        if last_hash and existing_hash == last_hash:
            _LOGGER.info(
                "Plex Dashboard: dashboard %s is unedited (hash matches "
                "last installed) -- updating to new bundled version",
                url_path,
            )
        else:
            _LOGGER.info(
                "Plex Dashboard: dashboard %s appears to have user edits "
                "(stored hash %s, current hash %s); leaving in place. "
                "Toggle 'Reset dashboard to bundled version' in the "
                "integration options to force-overwrite.",
                url_path,
                last_hash[:8] or "<none>",
                existing_hash[:8],
            )
            return

    await existing_storage.async_save(dashboard_config)
    _LOGGER.info(
        "Plex Dashboard: %s storage dashboard '%s'",
        "force-reset" if force_reset else ("updated" if existing_config else "registered"),
        url_path,
    )

    # Persist the new hash so we can detect user edits next upgrade.
    new_data = {**entry.data, DATA_INSTALLED_DASHBOARD_HASH: new_hash}

    # Clear the one-shot reset flag if it was set.
    if force_reset:
        new_options = {k: v for k, v in entry.options.items() if k != CONF_RESET_DASHBOARD}
        hass.config_entries.async_update_entry(
            entry, data=new_data, options=new_options
        )
    else:
        hass.config_entries.async_update_entry(entry, data=new_data)


# ---------------------------------------------------------------------------
# Repairs: detect missing HACS frontend cards
# ---------------------------------------------------------------------------
async def _async_check_frontend_cards(hass: HomeAssistant) -> None:
    """Inspect the lovelace_resources collection for missing JS modules.

    We can't reliably tell which custom: element each resource registers, so we
    use a filename-substring heuristic. Any required card whose substring is
    absent from every registered resource URL gets a Repair issue raised.
    """
    lovelace_data = hass.data.get(LOVELACE_DATA)
    resources_collection = getattr(lovelace_data, "resources", None) if lovelace_data else None
    resource_urls: list[str] = []
    if resources_collection is not None:
        try:
            await resources_collection.async_get_info()
        except Exception:  # noqa: BLE001
            pass
        try:
            for item in resources_collection.async_items():
                url = (item.get("url") if isinstance(item, dict) else getattr(item, "url", "")) or ""
                resource_urls.append(url.lower())
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Could not enumerate lovelace resources: %s", err)

    blob = " ".join(resource_urls)

    missing: list[tuple[str, dict[str, str]]] = []
    for card_element, info in REQUIRED_FRONTEND_CARDS.items():
        # Heuristic substring: card name or repo name
        needle = card_element.replace("-card", "").split("-")[0]
        present = needle in blob or info["repo"].split("/")[-1].lower() in blob
        if not present:
            missing.append((card_element, info))
        # Clean up any per-card issues from previous versions
        ir.async_delete_issue(hass, DOMAIN, f"missing_card_{card_element}")

    consolidated_id = "missing_frontend_cards"
    if not missing:
        ir.async_delete_issue(hass, DOMAIN, consolidated_id)
        return

    # Build a markdown bullet list of one-click HACS install deep links
    lines: list[str] = []
    for _card, info in missing:
        owner, repo = info["repo"].split("/", 1)
        link = HACS_DEEP_LINK.format(owner=owner, repo=repo)
        lines.append(f"- [{info['name']}]({link}) — `{info['repo']}`")
    cards_md = "\n".join(lines)

    ir.async_create_issue(
        hass,
        DOMAIN,
        consolidated_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="missing_frontend_cards",
        translation_placeholders={
            "count": str(len(missing)),
            "cards": cards_md,
        },
        learn_more_url="https://hacs.xyz/docs/use/repositories/dashboard/",
    )


# ---------------------------------------------------------------------------
# Repairs: detect missing packages: config in configuration.yaml
# ---------------------------------------------------------------------------
async def _async_check_packages_enabled(hass: HomeAssistant) -> None:
    """Raise a Repair if `homeassistant.packages` doesn't include our package."""
    # We can't reliably re-parse configuration.yaml from here, but if our
    # template sensors aren't loaded after a restart, the user hasn't enabled
    # packages. The cheapest signal: check if sensor.plex_active_streams is
    # known to the entity registry / state machine.
    if hass.states.get("sensor.plex_active_streams") is not None:
        ir.async_delete_issue(hass, DOMAIN, "packages_not_loaded")
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        "packages_not_loaded",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="packages_not_loaded",
        learn_more_url="https://www.home-assistant.io/docs/configuration/packages/",
    )


# ---------------------------------------------------------------------------
# Restart notification
# ---------------------------------------------------------------------------
async def _async_notify_restart(
    hass: HomeAssistant, file_results: dict[str, bool]
) -> None:
    """Tell the user a restart is required if package/theme were just written."""
    needs_restart = file_results.get("package") or file_results.get("theme")
    if not needs_restart:
        return
    try:
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "Plex Dashboard installed",
                "notification_id": "plex_dashboard_restart",
                "message": (
                    "Plex Dashboard files were written to /config.\n\n"
                    "**Restart Home Assistant** to load the new package and theme.\n\n"
                    "After restart:\n"
                    "1. Profile -> Theme -> 'Plex Dark'\n"
                    "2. Open the new **Plex** dashboard from the sidebar\n"
                    "3. Resolve any missing-card Repairs in Settings -> Repairs"
                ),
            },
            blocking=False,
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Could not post restart notification: %s", err)


# ---------------------------------------------------------------------------
# Repairs: detect deployment-health gaps (slug mismatch, missing libraries,
# optional integrations not detected). Purely informational -- the dashboard
# itself collapses missing pieces gracefully via auto-entities, but a single
# Repair entry helps users find the gaps.
# ---------------------------------------------------------------------------
async def _async_check_deployment_health(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Detect common gaps and surface them as one consolidated Repair.

    Each finding is a markdown bullet pointing the user at the fix. We
    intentionally bundle these into a single Repair so the user sees one
    actionable summary rather than five low-priority notices.
    """
    issue_id = "deployment_health"
    findings: list[str] = []

    slug = entry.data.get(CONF_PLEX_SLUG, "")

    # 1) Plex server slug actually resolves to a sensor.
    if slug and hass.states.get(f"sensor.plex_{slug}") is None:
        # Look for any sensor.plex_* that could be the real slug
        candidates = sorted(
            s.entity_id.removeprefix("sensor.plex_")
            for s in hass.states.async_all("sensor")
            if s.entity_id.startswith("sensor.plex_")
            and "_library_" not in s.entity_id
            and s.entity_id
            not in {
                "sensor.plex_active_streams",
                "sensor.plex_active_client_ids",
                # Removed from the package in v2.4.1, but pre-2.4.1 installs
                # keep a restored registry entry, so still exclude it here.
                "sensor.plex_total_bandwidth_mbps",
                "sensor.plex_server_online",
            }
        )
        # Common footgun #1: user pasted the entity prefix into the slug
        # field (slug=`plex_<X>`, sensor.plex_<X> exists, sensor.plex_plex_<X>
        # does NOT). Only suggest stripping if both conditions hold --
        # otherwise users with legitimately `plex_`-prefixed slugs (e.g.
        # server named `plex.lwk.space` -> slug `plex_lwk_space`) get bad
        # advice telling them to remove a prefix they actually need.
        stripped = slug
        for prefix in ("sensor.plex_", "sensor.", "plex_"):
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix):]
                break
        if (
            stripped != slug
            and hass.states.get(f"sensor.plex_{stripped}") is not None
        ):
            findings.append(
                f"- **Plex slug has an extra `plex_` prefix.** Configured "
                f"slug is `{slug}`, but `sensor.plex_{stripped}` exists "
                f"and `sensor.plex_{slug}` does not. Open **Settings → "
                f"Devices & Services → Plex Dashboard → Configure** and "
                f"change the slug to `{stripped}`."
            )
        else:
            hint = (
                f" Detected candidates: `{', '.join(candidates[:5])}`."
                if candidates
                else ""
            )
            findings.append(
                f"- **Plex server slug mismatch** — configured slug `{slug}` "
                f"doesn't match any `sensor.plex_<slug>` entity.{hint} "
                "Update the slug in **Settings → Devices & Services → "
                "Plex Dashboard → Configure**."
            )

    # 2) At least one Plex library sensor is exposed.
    library_sensors = [
        s.entity_id
        for s in hass.states.async_all("sensor")
        if s.entity_id.startswith("sensor.plex_") and "_library_" in s.entity_id
    ]
    if not library_sensors:
        findings.append(
            "- **No Plex library sensors found.** Open **Settings → "
            "Devices & Services → Plex → Configure** and tick the libraries "
            "you want exposed as sensors. The Libraries section will stay "
            "empty until at least one is enabled."
        )

    # 2b) Orphan library sensors from re-added Plex integrations.
    # The dashboard now filters these out client-side (doubled-prefix +
    # numeric-suffix excludes), but they still clutter Developer Tools
    # and the entity registry. Surface a finding so the user knows.
    import re as _re
    orphan_double = [
        e for e in library_sensors
        if _re.match(r"^sensor\.plex_[^_]+(?:_[^_]+)*_plex_", e)
    ]
    orphan_numeric = [
        e for e in library_sensors
        if _re.match(r"^sensor\.plex_.+_library_.+_\d+$", e)
    ]
    orphans = set(orphan_double) | set(orphan_numeric)
    if orphans:
        findings.append(
            f"- **{len(orphans)} orphaned Plex library sensor(s) detected** "
            "(left over from a re-added Plex integration -- entities "
            "like `sensor.plex_<slug>_plex_<slug>_library_*` or with "
            "numeric suffixes `_2`/`_3`/...). The dashboard hides them "
            "automatically, but to clean them up: **Settings → Devices "
            "& Services → ⋮ → Entities**, filter `library`, select the "
            "duplicates, and Delete."
        )

    # 3) Optional integrations (informational only)
    #
    # Recently Added: as of v2.3.3 the dashboard discovers per-type
    # plex_recently_added sensors via auto-entities regex at render time
    # (no setup-time substitution), so a missing card just collapses to
    # the bundled `else:` markdown. We surface a single informational
    # finding when none of the three suffixes resolve at all -- that
    # usually means the integration isn't installed.
    typed_ra_eids = sorted(
        s.entity_id
        for s in hass.states.async_all("sensor")
        if "recently_added" in s.entity_id
        and isinstance(s.attributes.get("data"), list)
        and (
            s.entity_id.endswith("_movie")
            or s.entity_id.endswith("_show")
            or s.entity_id.endswith("_artist")
            or s.entity_id.endswith("_music")
        )
    )
    if not typed_ra_eids:
        findings.append(
            "- _Optional:_ no `plex_recently_added` typed sensors detected — "
            "the New Movies / New Episodes / New Music cards will show a "
            "setup hint instead of content. Install the [plex_recently_added]"
            "(https://github.com/custom-components/sensor.plex_recently_added) "
            "HACS integration (v0.6+ ships per-type sensors named "
            "`*_recently_added_movie` / `_show` / `_artist`); the dashboard "
            "will pick them up automatically on next reload."
        )

    if (
        hass.states.get("sensor.radarr_upcoming_media") is None
        and hass.states.get("sensor.sonarr_upcoming_media") is None
    ):
        findings.append(
            "- _Optional:_ neither **Radarr** nor **Sonarr** detected — "
            "the Coming Soon view will show install hints. "
            "[Radarr](https://www.home-assistant.io/integrations/radarr/) · "
            "[Sonarr](https://www.home-assistant.io/integrations/sonarr/)."
        )

    if not findings:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return

    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="deployment_health",
        translation_placeholders={
            "count": str(len(findings)),
            "findings": "\n".join(findings),
        },
    )
