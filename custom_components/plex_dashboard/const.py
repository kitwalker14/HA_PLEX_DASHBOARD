"""Constants for the Plex Dashboard integration."""
from __future__ import annotations

DOMAIN = "plex_dashboard"

# Config entry data keys
CONF_PLEX_SLUG = "plex_slug"
CONF_DASHBOARD_URL_PATH = "dashboard_url_path"
CONF_INSTALL_THEME = "install_theme"
CONF_INSTALL_PACKAGE = "install_package"
CONF_REGISTER_DASHBOARD = "register_dashboard"
CONF_CREATE_HELPERS = "create_helpers"

DEFAULT_DASHBOARD_URL_PATH = "plex-dashboard"
DEFAULT_DASHBOARD_TITLE = "Plex"
DEFAULT_DASHBOARD_ICON = "mdi:plex"

# File names bundled in /data
DATA_DIR = "data"
THEME_FILENAME = "plex-dashboard.yaml"
DASHBOARD_FILENAME = "plex_dashboard_dashboard.yaml"
PACKAGE_FILENAME = "plex_dashboard_package.yaml"

# Output paths (relative to /config)
THEMES_OUTPUT_DIR = "themes"
DASHBOARDS_OUTPUT_DIR = "dashboards"
PACKAGES_OUTPUT_DIR = "packages"

THEME_OUTPUT_NAME = "plex-dashboard.yaml"
DASHBOARD_OUTPUT_NAME = "plex_dashboard.yaml"
PACKAGE_OUTPUT_NAME = "plex_dashboard.yaml"

PLACEHOLDER_SLUG = "PLEX_SERVER_NAME"

# Required HACS frontend cards (custom: element name -> friendly name + repo)
REQUIRED_FRONTEND_CARDS: dict[str, dict[str, str]] = {
    "mushroom-template-card": {
        "name": "Mushroom",
        "repo": "piitaya/lovelace-mushroom",
    },
    "button-card": {
        "name": "Button card",
        "repo": "custom-cards/button-card",
    },
    "mini-media-player": {
        "name": "Mini media player",
        "repo": "kalkih/mini-media-player",
    },
    "bar-card": {
        "name": "Bar card",
        "repo": "custom-cards/bar-card",
    },
    "auto-entities": {
        "name": "Auto-entities",
        "repo": "thomasloven/lovelace-auto-entities",
    },
    "upcoming-media-card": {
        "name": "Upcoming media card",
        "repo": "custom-cards/upcoming-media-card",
    },
}

# Helpers we create on setup
HELPERS_INPUT_BOOLEAN: dict[str, dict[str, str]] = {
    "plex_show_paused": {
        "name": "Show paused streams",
        "icon": "mdi:pause-circle-outline",
    },
    "plex_show_offline_clients": {
        "name": "Show idle clients",
        "icon": "mdi:monitor-off",
    },
}

HELPERS_INPUT_SELECT: dict[str, dict] = {
    "plex_recently_added_filter": {
        "name": "Recently added filter",
        "icon": "mdi:filter-variant",
        "options": ["All", "Movies", "TV", "Music"],
        "initial": "All",
    },
}
