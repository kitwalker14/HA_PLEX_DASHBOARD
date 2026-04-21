"""Config flow for Plex Dashboard."""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CREATE_HELPERS,
    CONF_DASHBOARD_URL_PATH,
    CONF_INSTALL_PACKAGE,
    CONF_INSTALL_THEME,
    CONF_PLEX_SLUG,
    CONF_REGISTER_DASHBOARD,
    DEFAULT_DASHBOARD_URL_PATH,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLEX_SENSOR_RE = re.compile(r"^sensor\.plex_(?!library_|recently_added_)([a-z0-9_]+)$")


def _detect_plex_slugs(hass) -> list[str]:
    """Return candidate Plex server slugs from existing sensors."""
    slugs: set[str] = set()
    for state in hass.states.async_all("sensor"):
        m = PLEX_SENSOR_RE.match(state.entity_id)
        if m:
            slugs.add(m.group(1))
    return sorted(slugs)


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
            slug = (user_input.get(CONF_PLEX_SLUG) or "").strip().lower()
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


class PlexDashboardOptionsFlow(config_entries.OptionsFlow):
    """Allow re-running file install / dashboard registration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

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
                    CONF_CREATE_HELPERS,
                    default=current.get(CONF_CREATE_HELPERS, True),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
