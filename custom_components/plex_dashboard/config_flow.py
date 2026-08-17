"""Config flow for Plex Dashboard."""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_DASHBOARD_URL_PATH,
    CONF_INSTALL_PACKAGE,
    CONF_INSTALL_THEME,
    CONF_PLEX_SLUG,
    CONF_REGISTER_DASHBOARD,
    CONF_RESET_DASHBOARD,
    DEFAULT_DASHBOARD_URL_PATH,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLEX_SENSOR_RE = re.compile(r"^sensor\.plex_(?!library_|recently_added_)([a-z0-9_]+)$")

# Slugs that belong to this integration's own package sensors. Without this
# guard the dropdown fills up with our own template sensors as soon as the
# package is installed, and because the list is sorted, `active_client_ids`
# becomes the suggested default on any re-add.
PACKAGE_SENSOR_SLUGS = frozenset(
    {
        "active_client_ids",
        "active_streams",
        "anything_playing",
        "server_online",
        "total_bandwidth_mbps",
    }
)

# The slug is substituted into a YAML/Jinja file we write to /config, so it
# must be validated in EVERY code path that can set it -- not just the
# initial config step.
SLUG_RE = re.compile(r"^[a-z0-9_]+\Z")

# Lovelace url_path must be a single lowercase token; it is also rejected at
# registration time if it collides with a built-in panel, and that failure is
# swallowed by our caller, so catch it here where we can show the user an error.
URL_PATH_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*\Z")
RESERVED_URL_PATHS = frozenset(
    {
        "calendar",
        "config",
        "developer-tools",
        "energy",
        "history",
        "logbook",
        "lovelace",
        "map",
        "media-browser",
        "profile",
        "shopping-list",
        "todo",
    }
)


def _detect_plex_slugs(hass: HomeAssistant) -> list[str]:
    """Return candidate Plex server slugs from existing sensors."""
    slugs: set[str] = set()
    for state in hass.states.async_all("sensor"):
        m = PLEX_SENSOR_RE.match(state.entity_id)
        if not m:
            continue
        slug = m.group(1)
        if "_library_" in slug or slug in PACKAGE_SENSOR_SLUGS:
            continue
        slugs.add(slug)
    return sorted(slugs)


def _validate_input(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> tuple[str, str, dict[str, str]]:
    """Normalise and validate the slug and dashboard URL path.

    Returns ``(slug, url_path, errors)``. Shared by the config step and the
    options step so both enforce identical rules.
    """
    errors: dict[str, str] = {}

    raw_slug = (user_input.get(CONF_PLEX_SLUG) or "").strip().lower()
    slug = _normalize_slug(hass, raw_slug)
    if not slug:
        errors[CONF_PLEX_SLUG] = "slug_required"
    elif not SLUG_RE.match(slug):
        errors[CONF_PLEX_SLUG] = "slug_invalid"

    url_path = (
        (user_input.get(CONF_DASHBOARD_URL_PATH) or "").strip().lower()
        or DEFAULT_DASHBOARD_URL_PATH
    )
    if not URL_PATH_RE.match(url_path):
        errors[CONF_DASHBOARD_URL_PATH] = "url_path_invalid"
    elif url_path in RESERVED_URL_PATHS:
        errors[CONF_DASHBOARD_URL_PATH] = "url_path_reserved"

    return slug, url_path, errors


def _normalize_slug(hass: HomeAssistant, raw: str) -> str:
    """Smart slug normalization.

    Some users paste a full entity prefix (`sensor.plex_myserver`) into
    the slug field; others have a Plex server whose name legitimately
    starts with `plex` (e.g. `plex.lwk.space` slugifies to
    `plex_lwk_space`, producing `sensor.plex_plex_lwk_space`).

    We can't tell these apart syntactically, so we resolve against the
    state machine: only strip a `sensor.plex_` / `sensor.` / `plex_`
    prefix when the un-stripped slug does NOT match an existing
    `sensor.plex_<slug>` AND the stripped form does. Otherwise the user's
    input is returned untouched.
    """
    raw = raw.strip().lower()
    if not raw:
        return raw
    # If the input as-given resolves, trust it.
    if hass.states.get(f"sensor.plex_{raw}") is not None:
        return raw
    # Otherwise try progressively stripping known prefixes.
    for prefix in ("sensor.plex_", "sensor.", "plex_"):
        if raw.startswith(prefix):
            stripped = raw[len(prefix):]
            if stripped and hass.states.get(f"sensor.plex_{stripped}") is not None:
                return stripped
    # No resolution either way -- return as-given so the user sees the
    # exact value they typed in the deployment_health Repair message.
    return raw


class PlexDashboardConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance config flow for Plex Dashboard."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        slugs = _detect_plex_slugs(self.hass)
        suggested_slug = slugs[0] if slugs else ""

        errors: dict[str, str] = {}

        if user_input is not None:
            slug, url_path, errors = _validate_input(self.hass, user_input)
            if not errors:
                return self.async_create_entry(
                    title="Plex Dashboard",
                    data={
                        CONF_PLEX_SLUG: slug,
                        CONF_DASHBOARD_URL_PATH: url_path,
                        CONF_INSTALL_THEME: user_input.get(CONF_INSTALL_THEME, True),
                        CONF_INSTALL_PACKAGE: user_input.get(
                            CONF_INSTALL_PACKAGE, True
                        ),
                        CONF_REGISTER_DASHBOARD: user_input.get(
                            CONF_REGISTER_DASHBOARD, True
                        ),
                    },
                )

        # Build schema; if we found slugs, use a dropdown; otherwise a text box
        if slugs:
            slug_field = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=slugs,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            )
        else:
            slug_field = selector.TextSelector()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PLEX_SLUG, default=suggested_slug
                ): slug_field,
                vol.Optional(
                    CONF_DASHBOARD_URL_PATH, default=DEFAULT_DASHBOARD_URL_PATH
                ): str,
                vol.Optional(CONF_INSTALL_THEME, default=True): bool,
                vol.Optional(CONF_INSTALL_PACKAGE, default=True): bool,
                vol.Optional(CONF_REGISTER_DASHBOARD, default=True): bool,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=(
                self.add_suggested_values_to_schema(schema, user_input)
                if user_input is not None
                else schema
            ),
            errors=errors,
            description_placeholders={
                "detected": ", ".join(slugs) if slugs else "none yet",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "PlexDashboardOptionsFlow":
        return PlexDashboardOptionsFlow()


class PlexDashboardOptionsFlow(OptionsFlow):
    """Allow re-running file install / dashboard registration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            # The slug ends up inside a Jinja template in the package YAML we
            # write to /config, so it must be validated here too. Earlier
            # versions validated only in the config step, which meant the
            # options form could write arbitrary text into that file.
            slug, url_path, errors = _validate_input(self.hass, user_input)
            if not errors:
                return self.async_create_entry(
                    title="",
                    data={
                        **user_input,
                        CONF_PLEX_SLUG: slug,
                        CONF_DASHBOARD_URL_PATH: url_path,
                    },
                )

        # Read the entry live rather than from a snapshot taken in __init__,
        # so defaults reflect any update made while this flow was open.
        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PLEX_SLUG, default=current.get(CONF_PLEX_SLUG, "")
                ): str,
                vol.Optional(
                    CONF_DASHBOARD_URL_PATH,
                    default=current.get(
                        CONF_DASHBOARD_URL_PATH, DEFAULT_DASHBOARD_URL_PATH
                    ),
                ): str,
                vol.Optional(
                    CONF_INSTALL_THEME, default=current.get(CONF_INSTALL_THEME, True)
                ): bool,
                vol.Optional(
                    CONF_INSTALL_PACKAGE,
                    default=current.get(CONF_INSTALL_PACKAGE, True),
                ): bool,
                vol.Optional(
                    CONF_REGISTER_DASHBOARD,
                    default=current.get(CONF_REGISTER_DASHBOARD, True),
                ): bool,
                vol.Optional(
                    CONF_RESET_DASHBOARD, default=False
                ): bool,
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=(
                self.add_suggested_values_to_schema(schema, user_input)
                if user_input is not None
                else schema
            ),
            errors=errors,
        )
