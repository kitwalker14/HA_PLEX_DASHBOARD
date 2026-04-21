# Contributing

Thanks for your interest in improving the Plex Dashboard!

## Dev workflow

1. Fork → branch → PR
2. Push triggers the **Validate** workflow (HACS Action + yamllint + shellcheck)
3. Test against a real HA install:
   - For the **theme**: symlink `themes/plex-dashboard.yaml` into
     `/config/themes/`
   - For **dashboard/package**: run `HA_CONFIG=/config ./scripts/install.sh`

## Releasing

Maintainers only.

1. Update `CHANGELOG.md`
2. Commit & push to `main`
3. Tag with semver:
   ```sh
   git tag v1.2.3
   git push --tags
   ```
4. The **Release** workflow builds `plex_dashboard_extras.zip`, creates a
   GitHub Release, and HACS will pick up the theme update automatically.

## Style

- 2-space YAML indent
- Mark user-replaceable values with `PLACEHOLDER_NAME` so find/replace works
- Keep card-mod / button-card JS short and inline-commented
- Shell scripts must pass `shellcheck`
