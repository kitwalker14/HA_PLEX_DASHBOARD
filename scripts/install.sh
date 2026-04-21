#!/usr/bin/env bash
# =============================================================================
#  Plex Dashboard for Home Assistant – installer
# =============================================================================
#  Installs:
#    - extras/packages/plex_dashboard.yaml -> $HA_CONFIG/packages/
#    - extras/dashboards/plex_dashboard.yaml -> $HA_CONFIG/dashboards/
#
#  The theme is delivered separately via HACS. Install it from HACS first:
#    HACS → Themes → search "Plex Dashboard"
#
#  Usage:
#    HA_CONFIG=/config ./scripts/install.sh
#  Or interactively:
#    ./scripts/install.sh /config
# =============================================================================
set -euo pipefail

HA_CONFIG="${1:-${HA_CONFIG:-}}"
if [[ -z "$HA_CONFIG" ]]; then
  read -rp "Path to your Home Assistant config dir [/config]: " HA_CONFIG
  HA_CONFIG="${HA_CONFIG:-/config}"
fi

if [[ ! -d "$HA_CONFIG" ]]; then
  echo "ERROR: $HA_CONFIG does not exist" >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
SRC="$(cd -- "$SCRIPT_DIR/.." &>/dev/null && pwd)"

echo "→ Installing into $HA_CONFIG"

mkdir -p "$HA_CONFIG/packages" "$HA_CONFIG/dashboards"
cp -v "$SRC/extras/packages/plex_dashboard.yaml"   "$HA_CONFIG/packages/"
cp -v "$SRC/extras/dashboards/plex_dashboard.yaml" "$HA_CONFIG/dashboards/"

cat <<'EOF'

✓ Files installed.

Next steps:

1. Install the Plex Dashboard THEME via HACS (HACS → Themes → "Plex Dashboard")
2. Install required HACS frontend cards:
     - mushroom, button-card, mini-media-player, bar-card,
       auto-entities, card-mod, upcoming-media-card
3. Add to configuration.yaml (if not already present):

     homeassistant:
       packages: !include_dir_named packages

     lovelace:
       mode: storage
       dashboards:
         plex-dashboard:
           mode: yaml
           title: Plex
           icon: mdi:plex
           show_in_sidebar: true
           filename: dashboards/plex_dashboard.yaml

4. Edit packages/plex_dashboard.yaml and replace PLEX_SERVER_NAME with your
   Plex server slug (see sensor.plex_<slug> in Developer Tools → States)

5. Restart Home Assistant
6. Profile → Theme → "Plex Dark"

Done.
EOF
