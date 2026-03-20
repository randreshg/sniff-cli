# Changelog

All notable changes to `dekk` will be documented in this file.

## 1.0.1 - 2026-03-19

- Added project-local install and uninstall APIs for generated launchers.
- Centralized shell PATH updates in `dekk` for wrapper and shim installs.
- Added OS-aware shell config handling through the shared installer layer.
- Refreshed CI workflows and fixed repo lint, typing, and test drift.

## 1.0.0 - 2026-03-19

First public `dekk` release.

- Renamed the published distribution to `dekk`.
- Renamed the Python import package to `dekk`.
- Renamed the default config file to `.dekk.toml`.
- Standardized the console entrypoint as `dekk`.
- Cleaned up repository metadata, developer docs, and packaging surfaces for reuse.
- Added CI coverage for linting, typing, tests, and package builds.
