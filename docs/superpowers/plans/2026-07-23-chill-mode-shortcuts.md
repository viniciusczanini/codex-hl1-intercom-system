# Chill Mode and Desktop Shortcuts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hot-switchable GTA Vice City chill notification mode plus safe normal/chill and LED Apple Shortcuts with Desktop launchers.

**Architecture:** Configuration validation owns the `normal`/`chill` contract. `RuntimeContext` passes the validated mode to `AudioPlayer`, which maps normal announcements to their existing WAVs and every chill announcement to one shared WAV. A separate atomic configuration command powers Apple Shortcuts without allowing them to rewrite unrelated settings.

**Tech Stack:** Python 3.9 standard library, `unittest`, macOS `afplay`, Apple Shortcuts, `shortcuts` CLI, AppleScript application launchers, PCM WAV audio.

## Global Constraints

- Normal mode must preserve the current Half-Life announcement WAVs.
- Chill mode must use only the user-confirmed 1.57-second GTA Vice City pop-up notification sound.
- Configuration changes must take effect on the next hook without restarting ChatGPT or the hook.
- Existing per-announcement booleans remain authoritative in both modes.
- `alokium_enabled` remains independent from audio mode.
- Preserve the user's current uncommitted runtime setting `alokium_enabled: false`; do not stage it as a repository default change.
- Unknown modes fail safely and are logged by the existing hook error path.
- Do not modify Alokium event classification, firmware, or RGB behavior.
- Shortcut names must be exactly `Intercom - normal`, `Intercom - chill`, `Intercom - LEDs on`, and `Intercom - LEDs off`.
- Credit Rockstar Games and Take-Two Interactive for the GTA Vice City sound asset.

---

## File Structure

- Modify `src/codex_intercom/config.py`: validate and expose the audio mode.
- Modify `src/codex_intercom/audio.py`: resolve normal and chill sound paths and launch playback.
- Modify `src/codex_intercom/runtime.py`: pass the validated mode to the audio player.
- Create `scripts/set_config.py`: lock and atomically change only `mode` or `alokium_enabled`.
- Modify `scripts/install.py`: require the shared chill WAV during installation validation.
- Add `assets/chill/notification.wav`: one normalized shared chill asset.
- Modify `config.json`: add repository/runtime mode while preserving the local LED-off choice.
- Modify `tests/test_config.py`: mode defaults and validation.
- Create `tests/test_audio.py`: mode-specific path selection and missing-file behavior.
- Modify `tests/test_runtime.py`: runtime mode forwarding and audio/LED independence.
- Create `tests/test_set_config.py`: safe field updates, invalid input, and concurrent writers.
- Modify `tests/test_install.py`: chill asset installation validation.
- Modify `README.md` and `INSTALLATION.md`: mode, commands, shortcuts, and credits.
- Create four Apple Shortcuts in the macOS Shortcuts database.
- Create four matching `.app` launchers under `/Users/tommy/Desktop`.

---

### Task 1: Validate and expose the audio mode

**Files:**
- Modify: `tests/test_config.py:28-59`
- Modify: `src/codex_intercom/config.py:19-55`
- Modify: `config.json:1-14`

**Interfaces:**
- Consumes: `load_config(path: pathlib.Path) -> dict`
- Produces: `config["mode"]` with exactly `"normal"` or `"chill"`

- [ ] **Step 1: Write failing mode configuration tests**

Add to `ConfigTests`:

```python
def test_missing_mode_defaults_to_normal(self):
    config = load_config(self.write_json({}))
    self.assertEqual(config["mode"], "normal")

def test_chill_mode_is_accepted(self):
    config = load_config(self.write_json({"mode": "chill"}))
    self.assertEqual(config["mode"], "chill")

def test_unknown_mode_raises_config_error(self):
    with self.assertRaisesRegex(ConfigError, "mode must be 'normal' or 'chill'"):
        load_config(self.write_json({"mode": "quiet"}))
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_config.ConfigTests.test_missing_mode_defaults_to_normal \
  tests.test_config.ConfigTests.test_chill_mode_is_accepted \
  tests.test_config.ConfigTests.test_unknown_mode_raises_config_error -v
```

Expected: failures because `load_config` does not return or validate `mode`.

- [ ] **Step 3: Implement minimal mode validation**

In `load_config`, before the returned dictionary:

```python
mode = raw.get("mode", "normal")
if mode not in ("normal", "chill"):
    raise ConfigError("mode must be 'normal' or 'chill'")
```

Add `"mode": mode` to the returned dictionary.

Add the root key to `config.json` without changing any existing toggles:

```json
"mode": "normal"
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_config -v
```

Expected: all configuration tests pass.

- [ ] **Step 5: Stage only the mode hunk and commit**

Use interactive staging for `config.json` so the existing `alokium_enabled: false` working-tree change is not included:

```bash
git add src/codex_intercom/config.py tests/test_config.py
git add -p config.json
git diff --cached
git commit -m "feat: add intercom audio mode"
```

Expected cached diff: `mode`, loader, and tests only; local LED-off state remains unstaged.

---

### Task 2: Route normal and chill playback through one shared asset

**Files:**
- Create: `tests/test_audio.py`
- Modify: `tests/test_runtime.py:24-30,68-89,188-199`
- Modify: `src/codex_intercom/audio.py:15-37`
- Modify: `src/codex_intercom/runtime.py:126-132`
- Add: `assets/chill/notification.wav`

**Interfaces:**
- Consumes: `config["mode"]`, announcement names, `AudioPlayer.sounds_dir`
- Produces: `AudioPlayer.sound_path(name: str, mode: str) -> pathlib.Path`
- Produces: `AudioPlayer.play(name: str, mode: str = "normal") -> bool`

- [ ] **Step 1: Write failing audio path tests**

Create `tests/test_audio.py`:

```python
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_intercom.audio import AudioPlayer


class AudioPlayerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.assets = Path(self.temp_dir.name) / "assets"
        self.assets.mkdir()
        self.player = AudioPlayer(self.assets, Path(self.temp_dir.name) / "log")

    def test_normal_mode_resolves_announcement_asset(self):
        self.assertEqual(
            self.player.sound_path("task_complete", "normal"),
            self.assets / "task_complete.wav",
        )

    def test_chill_mode_resolves_shared_notification_asset(self):
        self.assertEqual(
            self.player.sound_path("task_complete", "chill"),
            self.assets / "chill" / "notification.wav",
        )
        self.assertEqual(
            self.player.sound_path("response_required", "chill"),
            self.assets / "chill" / "notification.wav",
        )

    @patch("codex_intercom.audio.subprocess.Popen")
    def test_play_uses_resolved_chill_asset(self, popen):
        sound = self.assets / "chill" / "notification.wav"
        sound.parent.mkdir()
        sound.write_bytes(b"RIFF" + b"\0" * 64)

        self.assertTrue(self.player.play("blocked", "chill"))

        self.assertEqual(popen.call_args.args[0], ["/usr/bin/afplay", str(sound)])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the audio tests and verify RED**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_audio -v
```

Expected: `AttributeError` for missing `sound_path` and incorrect `play` signature.

- [ ] **Step 3: Implement minimal path selection**

Update `AudioPlayer`:

```python
def sound_path(self, name, mode):
    if mode == "chill":
        return self.sounds_dir / "chill" / "notification.wav"
    return self.sounds_dir / (name + ".wav")

def play(self, name, mode="normal"):
    sound_path = self.sound_path(name, mode)
    if not sound_path.exists():
        append_log(self.log_path, "missing sound: {0}".format(sound_path))
        return False
    try:
        subprocess.Popen(
            [self.executable, str(sound_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        append_log(self.log_path, "playback failed: {0}".format(exc))
        return False
    return True
```

Update `RuntimeContext.play`:

```python
started = self.player.play(name, self.config.get("mode", "normal"))
```

Update `FakePlayer` in `tests/test_runtime.py` without changing existing name assertions:

```python
class FakePlayer:
    def __init__(self):
        self.played = []
        self.modes = []

    def play(self, name, mode="normal"):
        self.played.append(name)
        self.modes.append(mode)
        return True
```

Add:

```python
def test_chill_mode_is_forwarded_only_to_audio(self):
    self.config["mode"] = "chill"

    handle_event(self.event("PermissionRequest"), self.context)

    self.assertEqual(self.player.played, ["permission_required"])
    self.assertEqual(self.player.modes, ["chill"])
    self.assertEqual(
        self.notifier.calls,
        [("permission_required", "session-1", None)],
    )
```

- [ ] **Step 4: Normalize and add the confirmed asset**

Convert the confirmed temporary source:

```bash
mkdir -p assets/chill
/opt/homebrew/bin/ffmpeg -y -hide_banner -loglevel error \
  -i /tmp/gta-vc-popup-notification.mp3 \
  -ac 1 -ar 22050 -c:a pcm_s16le \
  assets/chill/notification.wav
```

Probe it:

```bash
/opt/homebrew/bin/ffprobe -v error \
  -show_entries stream=codec_name,sample_rate,channels:format=duration \
  -of json assets/chill/notification.wav
```

Expected: PCM signed 16-bit little-endian, 22050 Hz, mono, duration approximately 1.57 seconds.

- [ ] **Step 5: Run focused runtime and audio tests and verify GREEN**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_audio tests.test_runtime -v
```

Expected: all audio and runtime tests pass.

- [ ] **Step 6: Commit playback and asset**

```bash
git add src/codex_intercom/audio.py src/codex_intercom/runtime.py \
  tests/test_audio.py tests/test_runtime.py assets/chill/notification.wav
git commit -m "feat: add GTA Vice City chill playback"
```

---

### Task 3: Add safe atomic configuration switching

**Files:**
- Create: `tests/test_set_config.py`
- Create: `scripts/set_config.py`

**Interfaces:**
- Produces: `update_config(path: pathlib.Path, setting: str, value: str) -> dict`
- Produces CLI: `python3 scripts/set_config.py {mode|alokium} VALUE`
- Valid CLI values: `mode normal`, `mode chill`, `alokium on`, `alokium off`

- [ ] **Step 1: Write failing safe-update tests**

Create `tests/test_set_config.py` with tests that call the real function:

```python
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.set_config import update_config


ROOT = Path(__file__).resolve().parents[1]


class SetConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "config.json"
        self.original = {
            "mode": "normal",
            "announcements": {"task_started": False, "blocked": True},
            "alokium_enabled": False,
            "queue_idle_seconds": 4,
        }
        self.path.write_text(json.dumps(self.original), encoding="utf-8")

    def test_mode_update_preserves_every_other_field(self):
        result = update_config(self.path, "mode", "chill")
        self.assertEqual(result["mode"], "chill")
        self.assertEqual(result["announcements"], self.original["announcements"])
        self.assertFalse(result["alokium_enabled"])
        self.assertEqual(result["queue_idle_seconds"], 4)

    def test_alokium_update_preserves_mode_and_announcements(self):
        result = update_config(self.path, "alokium", "on")
        self.assertTrue(result["alokium_enabled"])
        self.assertEqual(result["mode"], "normal")
        self.assertEqual(result["announcements"], self.original["announcements"])

    def test_invalid_setting_or_value_is_rejected_without_writing(self):
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            update_config(self.path, "mode", "quiet")
        self.assertEqual(self.path.read_bytes(), before)

    def test_concurrent_cli_writers_leave_valid_complete_json(self):
        commands = [
            [sys.executable, str(ROOT / "scripts" / "set_config.py"),
             "--config", str(self.path), "mode", "chill"],
            [sys.executable, str(ROOT / "scripts" / "set_config.py"),
             "--config", str(self.path), "alokium", "on"],
        ]
        processes = [subprocess.Popen(command) for command in commands]
        self.assertEqual([process.wait() for process in processes], [0, 0])
        result = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(result["mode"], "chill")
        self.assertTrue(result["alokium_enabled"])
        self.assertEqual(result["announcements"], self.original["announcements"])
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_set_config -v
```

Expected: import failure because `scripts.set_config` does not exist.

- [ ] **Step 3: Implement locked atomic updates**

Create `scripts/set_config.py` with:

```python
#!/usr/bin/env python3
import argparse
import fcntl
import json
import os
import sys
import tempfile
from pathlib import Path


def project_root():
    return Path(__file__).resolve().parents[1]


def _replacement(setting, value):
    if setting == "mode" and value in ("normal", "chill"):
        return "mode", value
    if setting == "alokium" and value in ("on", "off"):
        return "alokium_enabled", value == "on"
    raise ValueError("expected: mode {normal|chill} or alokium {on|off}")


def _atomic_json(path, value):
    descriptor, temp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent), text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def update_config(path, setting, value):
    path = Path(path)
    key, replacement = _replacement(setting, value)
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("config must be an object")
        document[key] = replacement
        _atomic_json(path, document)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(description="Switch Codex intercom settings")
    parser.add_argument("--config", type=Path, default=project_root() / "config.json")
    parser.add_argument("setting", choices=("mode", "alokium"))
    parser.add_argument("value")
    args = parser.parse_args(argv)
    try:
        result = update_config(args.config, args.setting, args.value)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("Intercom setting failed: {0}".format(exc), file=sys.stderr)
        return 1
    if args.setting == "mode":
        print("Intercom mode: {0}".format(result["mode"]))
    else:
        print("Intercom LEDs: {0}".format(
            "on" if result["alokium_enabled"] else "off"
        ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests and direct CLI checks and verify GREEN**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_set_config -v
/usr/bin/python3 scripts/set_config.py mode normal
/usr/bin/python3 scripts/set_config.py alokium off
```

Expected: all tests pass; CLI prints `Intercom mode: normal` and `Intercom LEDs: off`.

- [ ] **Step 5: Commit the configuration command**

```bash
git add scripts/set_config.py tests/test_set_config.py
git commit -m "feat: add safe intercom setting command"
```

---

### Task 4: Validate installation assets and document usage

**Files:**
- Modify: `tests/test_install.py:71-109`
- Modify: `scripts/install.py:83-105`
- Modify: `README.md`
- Modify: `INSTALLATION.md`

**Interfaces:**
- Consumes: `assets/chill/notification.wav`
- Produces: `expected_assets(root) -> list[pathlib.Path]` including the shared chill asset

- [ ] **Step 1: Write failing installer validation tests**

In the install fixture create:

```python
(self.project / "assets" / "chill").mkdir()
(self.project / "assets" / "chill" / "notification.wav").write_bytes(
    b"RIFF" + b"\0" * 64
)
```

Add:

```python
def test_validate_assets_rejects_missing_chill_notification(self):
    (self.project / "assets" / "chill" / "notification.wav").unlink()
    with self.assertRaisesRegex(ValueError, "chill/notification.wav"):
        validate_assets(self.project)
```

- [ ] **Step 2: Run the focused installer test and verify RED**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_install.InstallRoundTripTests.test_validate_assets_rejects_missing_chill_notification -v
```

Expected: failure because `validate_assets` does not require the chill asset.

- [ ] **Step 3: Require the shared chill asset**

Update `expected_assets`:

```python
assets = [root / "assets" / (name + ".wav") for name in sorted(phrases)]
assets.append(root / "assets" / "chill" / "notification.wav")
return assets
```

When reporting invalid files, use:

```python
invalid.append(str(path.relative_to(root / "assets")))
```

so the message includes `chill/notification.wav`.

- [ ] **Step 4: Update English documentation**

Update both guides with:

```json
{
  "mode": "normal",
  "announcements": {},
  "alokium_enabled": false
}
```

Document:

```bash
/usr/bin/python3 scripts/set_config.py mode normal
/usr/bin/python3 scripts/set_config.py mode chill
/usr/bin/python3 scripts/set_config.py alokium on
/usr/bin/python3 scripts/set_config.py alokium off
```

State that mode and LED changes apply on the next hook without restart. Add an Apple Shortcuts/Desktop section naming all four controls. Add a credit that the GTA Vice City sound is owned by Rockstar Games/Take-Two Interactive and that this unofficial project is not affiliated with them.

- [ ] **Step 5: Run documentation and installer checks**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_install tests.test_build_sounds -v
rg -n '"mode"|set_config.py|Intercom - chill|Rockstar|Take-Two' \
  README.md INSTALLATION.md
```

Expected: tests pass and every required concept appears in both documents.

- [ ] **Step 6: Commit installer and documentation**

```bash
git add scripts/install.py tests/test_install.py README.md INSTALLATION.md
git commit -m "docs: explain chill mode and desktop controls"
```

---

### Task 5: Create and validate Apple Shortcuts and Desktop launchers

**Files and state:**
- Create in Shortcuts app: `Intercom - normal`
- Create in Shortcuts app: `Intercom - chill`
- Create in Shortcuts app: `Intercom - LEDs on`
- Create in Shortcuts app: `Intercom - LEDs off`
- Create: `/Users/tommy/Desktop/Intercom - normal.app`
- Create: `/Users/tommy/Desktop/Intercom - chill.app`
- Create: `/Users/tommy/Desktop/Intercom - LEDs on.app`
- Create: `/Users/tommy/Desktop/Intercom - LEDs off.app`

**Interfaces:**
- Consumes CLI: `/usr/bin/python3 /Users/tommy/Offline/projects/codex-intercom/scripts/set_config.py SETTING VALUE`
- Produces shortcuts callable as: `/usr/bin/shortcuts run "SHORTCUT NAME"`

- [ ] **Step 1: Create the four real Apple Shortcuts**

Using macOS Shortcuts UI, create one `Run Shell Script` action in each:

```bash
/usr/bin/python3 /Users/tommy/Offline/projects/codex-intercom/scripts/set_config.py mode normal
```

```bash
/usr/bin/python3 /Users/tommy/Offline/projects/codex-intercom/scripts/set_config.py mode chill
```

```bash
/usr/bin/python3 /Users/tommy/Offline/projects/codex-intercom/scripts/set_config.py alokium on
```

```bash
/usr/bin/python3 /Users/tommy/Offline/projects/codex-intercom/scripts/set_config.py alokium off
```

Set shell to `/bin/zsh`, input to `stdin`, and use the exact names from the global constraints.

- [ ] **Step 2: Verify the shortcuts exist**

Run:

```bash
/usr/bin/shortcuts list | rg '^Intercom - (normal|chill|LEDs on|LEDs off)$'
```

Expected: exactly four matching lines.

- [ ] **Step 3: Create the four Desktop application launchers**

Generate each launcher with `osacompile`, changing only the shortcut name:

```bash
/usr/bin/osacompile -o "/Users/tommy/Desktop/Intercom - normal.app" \
  -e 'do shell script "/usr/bin/shortcuts run " & quoted form of "Intercom - normal"'
```

Repeat for `Intercom - chill`, `Intercom - LEDs on`, and `Intercom - LEDs off`.

- [ ] **Step 4: Verify all four controls change only their intended state**

Run each shortcut and read the resulting JSON:

```bash
/usr/bin/shortcuts run "Intercom - chill"
/usr/bin/python3 -c 'import json; print(json.load(open("config.json"))["mode"])'
/usr/bin/shortcuts run "Intercom - normal"
/usr/bin/shortcuts run "Intercom - LEDs on"
/usr/bin/shortcuts run "Intercom - LEDs off"
```

Expected:

- Chill prints/stores `chill`.
- Normal restores `normal`.
- LEDs on temporarily stores `true`.
- LEDs off restores the user's requested final state `false`.
- Announcement toggles and `queue_idle_seconds` remain unchanged.

Verify Desktop bundles:

```bash
find /Users/tommy/Desktop -maxdepth 1 -type d -name 'Intercom - *.app' -print | sort
```

Expected: all four `.app` bundles.

---

### Task 6: Full verification and runtime smoke test

**Files:**
- Verify all changed project files and local shortcut state

**Interfaces:**
- Consumes all prior task outputs
- Produces a verified normal/chill installation with LEDs left off

- [ ] **Step 1: Run the complete automated suite**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
```

Expected: zero failures and zero errors.

- [ ] **Step 2: Validate bundled assets and inspect the chill WAV**

Run:

```bash
/usr/bin/python3 scripts/install.py
/opt/homebrew/bin/ffprobe -v error \
  -show_entries stream=codec_name,sample_rate,channels:format=duration \
  -of json assets/chill/notification.wav
```

Expected: installer succeeds; chill asset is valid mono 22050 Hz PCM audio around 1.57 seconds.

- [ ] **Step 3: Smoke-test direct playback in both modes**

Run:

```bash
/usr/bin/python3 scripts/set_config.py mode chill
/usr/bin/afplay assets/chill/notification.wav
/usr/bin/python3 scripts/set_config.py mode normal
/usr/bin/afplay assets/task_complete.wav
/usr/bin/python3 scripts/set_config.py alokium off
```

Expected: confirmed GTA notification plays first, current Half-Life task completion plays second, and final local state is normal mode with LEDs off.

- [ ] **Step 4: Inspect repository scope and preserve local runtime state**

Run:

```bash
git status --short --branch
git diff --check
git diff
git log --oneline -8
```

Expected: only the intentional unstaged `config.json` LED-off difference may remain; no temporary downloads, lock files, Shortcuts databases, or Desktop launchers are staged. If any verification fails, return to the owning task, add a focused failing regression test, implement the smallest correction, rerun the complete suite, and commit only the exact files named by that task.
