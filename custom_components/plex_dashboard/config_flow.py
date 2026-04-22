"""Config flow for Plex Dashboard."""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CREATE_HELPERS,
    CONF_DASHBOARD_URL_PATH,
    CONF_INSTALL_PACKAGE,
    CONF_INSTALL_THEME,
    CONF_PLEX_SLUG,
    CONF_RECENTLY_ADDED_SENSOR,
    CONF_REGISTER_DASHBOARD,
    CONF_RESET_DASHBOARD,
    DEFAULT_DASHBOARD_URL_PATH,
    DEFAULT_RECENTLY_ADDED_SENSOR,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLEX_SENSOR_RE = re.compile(r"^sensor\.plex_(?!library_|recently_added_)([a-z0-9_]+)$")
RECENTLY_ADDED_RE = re.compile(r"^sensor\..*recently_added.*$")


def _detect_recently_added_sensors(hass) -> list[str]:
    """Return candidate `plex_recently_added` source sensors.

    The HACS `plex_recently_added` integration creates a single sensor
    whose exact entity_id depends on the `name:` option and the user's
    Plex server slug. Common variants: `sensor.plex_recently_added`,
    `sensor.plex_plex_recently_added`, `sensor.<name>_recently_added`.
    We surface anything matching `sensor.*recently_added*` that has a
    `data` attribute (which is how upcoming-media-card consumes them).
    """
    candidates: list[str] = []
    for state in hass.states.async_all("sensor"):
        if not RECENTLY_ADDED_RE.match(state.entity_id):
            continue
        # Must have the list-of-items `data` attribute that
        # upcoming-media-card reads. A bare sensor.*recently_added* without
        # `data` is not useful here.
        if isinstance(state.attributes.get("data"), list):
            candidates.append(state.entity_id)
    return sorted(candidates)


def _detect_plex_slugs(hass) -> list[str]:
    """Return candidate Plex server slugs from existing sensors."""
    slugs: set[str] = set()
    for state in hass.states.async_all("sensor"):
        m = PLEX_SENSOR_RE.match(state.entity_id)
        if m:
            slugs.add(m.group(1))
    return sorted(slugs)


def _normalize_slug(hass, raw: str) -> str:
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
            raw_slug = (user_input.get(CONF_PLEX_SLUG) or "").strip().lower()
            slug = _normalize_slug(self.hass, raw_slug)
            if not slug:
                errors[CONF_PLEX_SLUG] = "slug_required"
            elif not re.match(r"^[a-z0-9_]+$", slug):
                errors[CONF_PLEX_SLUG] = "slug_invalid"
            else:
                return self.async_create_entry(
                    title="Plex Dashboard",
                    data={
                        CONF_PLEX_SLUG: slug,
                        CONF_DASHBOARD_URL_PATH: user_input.get(
                            CONF_DASHBOARD_URL_PATH, DEFAULT_DASHBOARD_URL_PATH
                        ).strip()
                        or DEFAULT_DASHBOARD_URL_PATH,
                        CONF_RECENTLY_ADDED_SENSOR: (
                            user_input.get(CONF_RECENTLY_ADDED_SENSOR)
                            or DEFAULT_RECENTLY_ADDED_SENSOR
                        ).strip()
                        or DEFAULT_RECENTLY_ADDED_SENSOR,
                        CONF_INSTALL_THEME: user_input.get(CONF_INSTALL_THEME, True),
                        CONF_INSTALL_PACKAGE: user_input.get(
                            CONF_INSTALL_PACKAGE, True
                        ),
                        CONF_REGISTER_DASHBOARD: user_input.get(
                            CONF_REGISTER_DASHBOARD, True
                        ),
                        CONF_CREATE_HELPERS: user_input.get(
                            CONF_CREATE_HELPERS, True
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

        # Recently-added sensor field: dropdown of detected candidates with
        # free-text fallback, default to first candidate (or the canonical
        # default if no sensors were detected yet).
        ra_candidates = _detect_recently_added_sensors(self.hass)
        ra_default = ra_candidates[0] if ra_candidates else DEFAULT_RECENTLY_ADDED_SENSOR
        if ra_candidates:
            ra_field = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=ra_candidates,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            )
        else:
            ra_field = selector.TextSelector()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PLEX_SLUG, default=suggested_slug
                ): slug_field,
                vol.Optional(
                    CONF_DASHBOARD_URL_PATH, default=DEFAULT_DASHBOARD_URL_PATH
                ): str,
                vol.Optional(
                    CONF_RECENTLY_ADDED_SENSOR, default=ra_default
                ): ra_field,
                vol.Optional(CONF_INSTALL_THEME, default=True): bool,
                vol.Optional(CONF_INSTALL_PACKAGE, default=True): bool,
                vol.Optional(CONF_REGISTER_DASHBOARD, default=True): bool,
                vol.Optional(CONF_CREATE_HELPERS, default=True): bool,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
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
        return PlexDashboardOptionsFlow(config_entry)


class PlexDashboardOptionsFlow(OptionsFlow):
    """Allow re-running file install / dashboard registration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        # Do NOT assign self.config_entry — it is provided by the base class
        # in modern HA and assigning to it raises an error.
        self._entry_data = dict(config_entry.data)
        self._entry_options = dict(config_entry.options)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            # Smart slug normalization: only strip prefixes if doing so
            # actually resolves to a real sensor.plex_<slug> entity.
            raw_slug = (user_input.get(CONF_PLEX_SLUG) or "").strip().lower()
            user_input[CONF_PLEX_SLUG] = _normalize_slug(self.hass, raw_slug)
            return self.async_create_entry(title="", data=user_input)

        current = {**self._entry_data, **self._entry_options}
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
                    CONF_RECENTLY_ADDED_SENSOR,
                    default=current.get(
                        CONF_RECENTLY_ADDED_SENSOR,
                        DEFAULT_RECENTLY_ADDED_SENSOR,
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
                    CONF_CREATE_HELPERS,
                    default=current.get(CONF_CREATE_HELPERS, True),
                ): bool,
                vol.Optional(
                    CONF_RESET_DASHBOARD, default=False
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
