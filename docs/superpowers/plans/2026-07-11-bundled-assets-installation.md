# Bundled Audio Installation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship eight ready-to-play WAV assets and make a fresh clone installable with one local installer command, while adding a complete English installation and usage guide.

**Architecture:** Runtime playback and the optional sound builder converge on a committed top-level `assets/` directory. The installer validates those assets before touching Codex hooks and rebuilds them only when explicitly requested. Existing hook ownership, queue behavior, configuration, and uninstall behavior remain unchanged.

**Tech Stack:** Python 3.9 standard library, `unittest`, JSON, macOS `/usr/bin/afplay`, optional Homebrew `ffmpeg`/`ffprobe`, Markdown, GitHub.

## Global Constraints

- The default installation path is clone, `cd`, and `/usr/bin/python3 scripts/install.py`.
- Normal installation must not require `ffmpeg`, `ffprobe`, or additional network downloads.
- Commit only the eight final announcement WAVs under `assets/`.
- Keep `sounds/source/` and `sounds/normalized/` ignored.
- Preserve existing `~/.codex/hooks.json` handlers and `~/.codex/config.toml`.
- Preserve the accepted legacy `--skip-build` CLI option.
- Provide `--rebuild-assets` for maintainers.
- Credit HL1SFX, Valve Corporation, and `viniciusczanini`; state that the project is unofficial and unendorsed.
- Push the verified result directly to public `main` at `viniciusczanini/codex-hl1-intercom-system`.

---

## File structure

- `assets/*.wav`: committed final phrases used directly by the runtime.
- `scripts/build_sounds.py`: optional source downloader and asset rebuilder.
- `scripts/install.py`: default offline asset validation and hook installation.
- `src/codex_intercom/runtime.py`: points `AudioPlayer` at `assets/`.
- `tests/test_build_sounds.py`: verifies manifest-to-asset coverage.
- `tests/test_install.py`: verifies validation, no-build default, and explicit rebuild.
- `tests/test_runtime.py`: verifies the production context uses `assets/`.
- `INSTALLATION.md`: complete English install and usage guide.
- `README.md`: concise quick start linking to the complete guide.

### Task 1: Bundle final audio and switch runtime/build output

**Files:**
- Create: `assets/blocked.wav`
- Create: `assets/permission_required.wav`
- Create: `assets/queue_complete.wav`
- Create: `assets/queue_item_complete.wav`
- Create: `assets/response_required.wav`
- Create: `assets/subagent_complete.wav`
- Create: `assets/task_complete.wav`
- Create: `assets/task_started.wav`
- Modify: `scripts/build_sounds.py`
- Modify: `src/codex_intercom/runtime.py`
- Test: `tests/test_build_sounds.py`
- Test: `tests/test_runtime.py`

**Interfaces:**
- Consumes: phrase names from `sounds/manifest.json`.
- Produces: `assets/<phrase>.wav` and a production `AudioPlayer` whose `sounds_dir` is `<project>/assets`.

- [ ] **Step 1: Write failing asset-path tests**

Add to `tests/test_build_sounds.py`:

```python
    def test_every_phrase_has_a_bundled_asset(self):
        manifest = load_manifest(ROOT / "sounds" / "manifest.json")
        self.assertEqual(
            {path.stem for path in (ROOT / "assets").glob("*.wav")},
            set(manifest["phrases"]),
        )
```

Add `create_context` to the imports in `tests/test_runtime.py`, define `ROOT = Path(__file__).resolve().parents[1]`, and add:

```python
    def test_production_context_uses_bundled_assets(self):
        context = create_context(
            root=ROOT,
            codex_home=Path(self.temp_dir.name) / "codex",
        )
        self.assertEqual(context.player.sounds_dir, ROOT / "assets")
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_build_sounds.SoundBuilderTests.test_every_phrase_has_a_bundled_asset \
  tests.test_runtime.RuntimeTests.test_production_context_uses_bundled_assets -v
```

Expected: asset coverage is empty and the runtime reports `sounds/generated` instead of `assets`.

- [ ] **Step 3: Copy final WAVs and update both paths**

Copy the eight existing verified files from `sounds/generated/*.wav` to `assets/*.wav` without transcoding.

In `scripts/build_sounds.py`, replace the output directory with:

```python
generated_dir = root / "assets"
```

Change the success line to:

```python
print("Built Half-Life intercom phrases in assets")
```

In `src/codex_intercom/runtime.py`, construct the player with:

```python
player=AudioPlayer(root / "assets", log_path),
```

- [ ] **Step 4: Run focused and full tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_build_sounds.SoundBuilderTests.test_every_phrase_has_a_bundled_asset \
  tests.test_runtime.RuntimeTests.test_production_context_uses_bundled_assets -v
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
```

Expected: both focused tests and the full suite pass.

- [ ] **Step 5: Commit runtime and assets**

```bash
git add assets scripts/build_sounds.py src/codex_intercom/runtime.py \
  tests/test_build_sounds.py tests/test_runtime.py
git commit -m "feat: bundle intercom audio assets"
```

### Task 2: Make default installation offline and validate assets

**Files:**
- Modify: `scripts/install.py`
- Test: `tests/test_install.py`

**Interfaces:**
- Produces: `expected_assets(root: Path) -> list[Path]`.
- Produces: `validate_assets(root: Path) -> None`, raising `ValueError` with missing or invalid filenames.
- Produces: `install(codex_home, root, rebuild_assets=False, skip_build=None) -> Path`.
- Produces: CLI flag `--rebuild-assets`; retains accepted `--skip-build`.

- [ ] **Step 1: Write failing installer tests**

In the install fixture, create a valid one-phrase manifest and WAV:

```python
(self.project / "sounds").mkdir()
(self.project / "sounds" / "manifest.json").write_text(
    json.dumps({
        "fragments": {"objective": "vox/objective.wav"},
        "phrases": {"task_complete": ["objective"]},
    }),
    encoding="utf-8",
)
(self.project / "assets").mkdir()
(self.project / "assets" / "task_complete.wav").write_bytes(
    b"RIFF" + b"\0" * 64
)
```

Import `validate_assets` and `patch`, then add:

```python
    def test_validate_assets_rejects_missing_phrase(self):
        (self.project / "assets" / "task_complete.wav").unlink()
        with self.assertRaisesRegex(ValueError, "task_complete.wav"):
            validate_assets(self.project)

    @patch("scripts.install.build_all")
    def test_default_install_does_not_rebuild_assets(self, build_all):
        install(self.codex_home, self.project)
        build_all.assert_not_called()

    @patch("scripts.install.build_all")
    def test_explicit_rebuild_runs_builder(self, build_all):
        install(self.codex_home, self.project, rebuild_assets=True)
        build_all.assert_called_once_with(self.project)
```

- [ ] **Step 2: Run focused tests to verify RED**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_install.InstallRoundTripTests.test_validate_assets_rejects_missing_phrase \
  tests.test_install.InstallRoundTripTests.test_default_install_does_not_rebuild_assets \
  tests.test_install.InstallRoundTripTests.test_explicit_rebuild_runs_builder -v
```

Expected: import or signature failures because validation and `rebuild_assets` do not exist.

- [ ] **Step 3: Implement validation and opt-in rebuilding**

Read `sounds/manifest.json`, derive each expected `assets/<phrase>.wav`, and reject any file that is absent or 44 bytes or smaller. At the beginning of `install`:

```python
if skip_build is False:
    rebuild_assets = True
if rebuild_assets:
    build_all(root)
validate_assets(root)
```

Use this CLI definition:

```python
parser.add_argument("--rebuild-assets", action="store_true")
parser.add_argument("--skip-build", action="store_true", help=argparse.SUPPRESS)
```

Call:

```python
hooks_path = install(
    args.codex_home,
    project_root(),
    rebuild_assets=args.rebuild_assets,
)
```

This keeps `--skip-build` accepted as a compatibility no-op while making no-build the default.

- [ ] **Step 4: Run installer and full tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_install -v
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
```

Expected: all installer tests and the full suite pass.

- [ ] **Step 5: Commit installer behavior**

```bash
git add scripts/install.py tests/test_install.py
git commit -m "feat: install from bundled audio"
```

### Task 3: Write the complete English guide

**Files:**
- Create: `INSTALLATION.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: `scripts/install.py`, `scripts/uninstall.py`, `config.json`, and the two runtime log paths.
- Produces: a standalone English installation and usage guide with a three-command quick start.

- [ ] **Step 1: Create `INSTALLATION.md`**

Write complete sections for overview, requirements, quick start, hook trust, one-time restart, configuration, queue timing, test scenarios, troubleshooting, updating, uninstalling, optional asset rebuilding, additional sounds, and credits.

The credits must link to `https://hl1sfx.com/`, identify HL1SFX as the sound discovery/download source, credit Valve Corporation for Half-Life and its original audio, credit `viniciusczanini` for this integration and phrase arrangements, and state that the project is unofficial and unendorsed.

- [ ] **Step 2: Reduce README install friction**

Remove `ffmpeg` from normal requirements, remove the mandatory build command, link prominently to `INSTALLATION.md`, update playback examples to `assets/*.wav`, and explain that final assets are committed while raw/intermediate files remain ignored.

- [ ] **Step 3: Verify documentation consistency**

```bash
rg -n 'INSTALLATION.md|https://hl1sfx.com/|Valve Corporation|viniciusczanini|--rebuild-assets' \
  README.md INSTALLATION.md
if rg -n 'sounds/generated|/Users/|tommy' README.md INSTALLATION.md; then exit 1; fi
git diff --check
```

Expected: required documentation is present, obsolete paths are absent, and Markdown has no whitespace errors.

- [ ] **Step 4: Commit documentation**

```bash
git add README.md INSTALLATION.md
git commit -m "docs: add installation and usage guide"
```

### Task 4: End-to-end verification and publish to main

**Files:**
- Verify: all tracked project files.
- Update: GitHub `main`.

**Interfaces:**
- Consumes: complete local repository.
- Produces: a verified public `main` with matching local and remote commits.

- [ ] **Step 1: Run complete local verification**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 -m json.tool config.json >/dev/null
/usr/bin/python3 -m json.tool sounds/manifest.json >/dev/null
test "$(find assets -maxdepth 1 -name '*.wav' | wc -l | tr -d ' ')" = "8"
for wav in assets/*.wav; do test -s "$wav"; done
git diff --check
git status -sb
```

Expected: zero failures, eight non-empty WAVs, no diff errors, and only intentional commits ahead of `origin/main`.

- [ ] **Step 2: Dry-run a fresh-clone-style install**

```bash
tmp="$(mktemp -d)"
git archive HEAD | tar -x -C "$tmp"
/usr/bin/python3 "$tmp/scripts/install.py" --codex-home "$tmp/codex-home"
/usr/bin/python3 -m json.tool "$tmp/codex-home/hooks.json" >/dev/null
```

Expected: installation succeeds without `ffmpeg` and writes valid hook JSON.

- [ ] **Step 3: Smoke-test bundled playback lookup**

Send a `PermissionRequest` event through the archived entry point with a temporary `CODEX_HOME`, then verify `play_attempted` appears in a temporary trace. Do not require audible playback as the only evidence.

- [ ] **Step 4: Push directly and verify GitHub**

```bash
git push origin main
test "$(git rev-parse HEAD)" = "$(git ls-remote origin refs/heads/main | awk '{print $1}')"
gh repo view viniciusczanini/codex-hl1-intercom-system \
  --json nameWithOwner,owner,visibility,url,defaultBranchRef
```

Use the GitHub tree API to confirm exactly eight `assets/*.wav` entries and no `sounds/source/` or `sounds/normalized/` entries.

Expected: owner `viniciusczanini`, visibility `PUBLIC`, default branch `main`, and identical local/remote commit hashes.
