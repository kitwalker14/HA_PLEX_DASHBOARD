"""Plex Dashboard integration: zero-touch installer for HA Plex dashboard."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import yaml

from homeassistant.components.lovelace.const import (
    CONF_ALLOW_SINGLE_WORD,
    CONF_ICON,
    CONF_REQUIRE_ADMIN,
    CONF_SHOW_IN_SIDEBAR,
    CONF_TITLE,
    CONF_URL_PATH,
    DOMAIN as LOVELACE_DOMAIN,
    LOVELACE_DATA,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, issue_registry as ir

from .const import (
    CONF_CREATE_HELPERS,
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
    HELPERS_INPUT_BOOLEAN,
    HELPERS_INPUT_SELECT,
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
    """Write content to target. Returns True if file was created/updated."""
    if target.exists():
        try:
            existing = target.read_text(encoding="utf-8")
            if existing == content:
                return False
        except OSError:
            pass
    _ensure_dir(target.parent)
    target.write_text(content, encoding="utf-8")
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
    create_helpers: bool = data.get(CONF_CREATE_HELPERS, True)
    url_path: str = data.get(CONF_DASHBOARD_URL_PATH, DEFAULT_DASHBOARD_URL_PATH)

    config_dir = Path(hass.config.path())
    substitutions = {PLACEHOLDER_SLUG: slug}

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

    # ---- Create helpers ----------------------------------------------------
    if create_helpers:
        await _async_create_helpers(hass)

    # ---- Surface missing frontend cards as Repairs -------------------------
    await _async_check_frontend_cards(hass)

    # ---- Surface missing packages config as a Repair -----------------------
    if install_package and file_results.get("package"):
        await _async_check_packages_enabled(hass)

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


# ---------------------------------------------------------------------------
# Lovelace dashboard registration (storage mode, fully runtime)
# ---------------------------------------------------------------------------
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

    # Parse YAML off the loop
    def _parse() -> dict:
        return yaml.safe_load(dashboard_yaml_text) or {}

    try:
        dashboard_config = await hass.async_add_executor_job(_parse)
    except yaml.YAMLError as err:
        _LOGGER.error("Plex Dashboard: bundled dashboard YAML is invalid: %s", err)
        return

    new_hash = _hash_dashboard(dashboard_config)

    # Find / construct the dashboards collection. It shares the same on-disk
    # storage as the singleton lovelace created at startup, so loading a fresh
    # instance is safe.
    from homeassistant.components.lovelace.dashboard import (
        DashboardsCollection,
        LovelaceStorage,
    )

    dashboards_collection = DashboardsCollection(hass)
    await dashboards_collection.async_load()

    existing = next(
        (
            item
            for item in dashboards_collection.async_items()
            if item.get(CONF_URL_PATH) == url_path
        ),
        None,
    )

    if existing is None:
        try:
            existing = await dashboards_collection.async_create_item(
                {
                    CONF_URL_PATH: url_path,
                    CONF_TITLE: DEFAULT_DASHBOARD_TITLE,
                    CONF_ICON: DEFAULT_DASHBOARD_ICON,
                    CONF_SHOW_IN_SIDEBAR: True,
                    CONF_REQUIRE_ADMIN: False,
                    CONF_ALLOW_SINGLE_WORD: True,
                }
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Plex Dashboard: could not create dashboard entry %s: %s",
                url_path,
                err,
            )
            return

    storage = LovelaceStorage(hass, existing)
    try:
        existing_config = await storage.async_load(force=True)
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

    await storage.async_save(dashboard_config)
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
# Helper creation via the input_boolean / input_select services
# ---------------------------------------------------------------------------
async def _async_create_helpers(hass: HomeAssistant) -> None:
    """Create input_boolean/input_select helpers if missing.

    We use the runtime services rather than the storage collection directly so
    the helpers are reload-safe and visible under Settings -> Helpers.
    """
    from homeassistant.components.input_boolean import (
        DOMAIN as IB_DOMAIN,
    )
    from homeassistant.components.input_select import (
        DOMAIN as IS_DOMAIN,
    )

    # input_boolean
    ib_component = hass.data.get(IB_DOMAIN)
    if ib_component is not None:
        for object_id, cfg in HELPERS_INPUT_BOOLEAN.items():
            entity_id = f"{IB_DOMAIN}.{object_id}"
            if hass.states.get(entity_id) is not None:
                continue
            try:
                await ib_component.async_create_item(
                    {"id": object_id, "name": cfg["name"], "icon": cfg.get("icon")}
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Could not create %s: %s", entity_id, err)

    # input_select
    is_component = hass.data.get(IS_DOMAIN)
    if is_component is not None:
        for object_id, cfg in HELPERS_INPUT_SELECT.items():
            entity_id = f"{IS_DOMAIN}.{object_id}"
            if hass.states.get(entity_id) is not None:
                continue
            try:
                await is_component.async_create_item(
                    {
                        "id": object_id,
                        "name": cfg["name"],
                        "icon": cfg.get("icon"),
                        "options": cfg["options"],
                        "initial": cfg.get("initial"),
                    }
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Could not create %s: %s", entity_id, err)


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
