# Bundled Audio and Easy Installation Design

## Goal

Make Codex HL1 Intercom System usable by a new macOS user with the shortest reliable path: clone the repository, run one installer command, trust the hooks, and restart ChatGPT once if it was already open.

## User experience

The primary installation path will be:

```bash
git clone https://github.com/viniciusczanini/codex-hl1-intercom-system.git
cd codex-hl1-intercom-system
/usr/bin/python3 scripts/install.py
```

The normal path must not require `ffmpeg`, a network download beyond cloning the repository, or a separate sound-build command. The eight ready-to-play WAV announcements will be committed under `assets/`.

## Audio layout

- `assets/<announcement>.wav` contains the eight final phrases used at runtime.
- `sounds/manifest.json` remains the source-of-truth for phrase composition.
- `sounds/source/` and `sounds/normalized/` remain ignored local build directories.
- `scripts/build_sounds.py` becomes an optional maintainer tool that rebuilds the committed files in `assets/`.
- The runtime reads only from `assets/` so a fresh clone is immediately playable.

Only final phrases are published. Raw fragments and intermediate normalized clips are not added to Git.

## Installer behavior

The default installer validates that every phrase declared in `sounds/manifest.json` has a non-empty WAV in `assets/`, then merges the four owned hooks into `~/.codex/hooks.json` as before.

An explicit `--rebuild-assets` option rebuilds the WAVs before installation for maintainers. The existing `--skip-build` option remains accepted for compatibility, although skipping is now the default behavior. Rebuilding requires `ffmpeg`, `ffprobe`, and access to `hl1sfx.com`.

Missing or incomplete assets produce a clear installer error before hooks are modified. Existing hooks, `config.toml`, installation ownership, and uninstall behavior remain unchanged.

## Documentation

Create `INSTALLATION.md` in English with:

1. A three-command quick start.
2. Requirements and hook trust instructions.
3. Restart behavior for the desktop app.
4. Every configuration toggle and queue timing.
5. A practical test sequence.
6. Trace and runtime-log troubleshooting.
7. Updating and uninstalling.
8. An advanced asset-rebuild section.
9. Clear notice that this is an unofficial fan project and that Half-Life assets belong to their respective owners.

The README will link to the guide and keep only the concise installation path. All examples will use repository-relative paths.

## Compatibility and validation

- Existing user installations continue to use the same hook entry point.
- The runtime asset-path change takes effect without reinstalling hooks because the entry-point path does not change.
- Automated tests cover bundled-asset validation, the default no-build install path, the optional rebuild path, and the runtime asset directory.
- The full unit suite, JSON validation, WAV existence checks, installer dry run, and a live hook smoke test must pass before publishing.
- Post-push verification confirms that all eight assets exist on GitHub and that local `main` matches `origin/main`.

## Out of scope

- Publishing raw HL1 VOX fragments.
- Supporting non-macOS audio players.
- Changing announcement phrases, queue semantics, or default toggles.
