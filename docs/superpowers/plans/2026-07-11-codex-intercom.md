# Codex Intercom Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and install a macOS Codex hook package that plays configurable Half-Life 1 VOX announcements for task, attention, queue, subagent, and blocked states.

**Architecture:** A Python 3.9 runtime receives Codex hook JSON, classifies events, maintains atomic per-session queue state, and launches `afplay` without blocking Codex. A separate sound builder downloads named HL1 fragments and composes local WAV phrases with `ffmpeg`; an idempotent installer merges owned handlers into the user's global `hooks.json` while preserving existing configuration.

**Tech Stack:** Python 3.9 standard library, `unittest`, JSON, macOS `/usr/bin/afplay`, Homebrew `ffmpeg`, Codex user-level lifecycle hooks.

## Global Constraints

- Project root is `/Users/tommy/Offline/projects/codex-intercom`.
- Every announcement is independently controlled by a boolean in `config.json` and defaults to `true`.
- Existing `/Users/tommy/.codex/config.toml`, including its Computer Use `notify` command, must remain byte-for-byte unchanged.
- Generated Half-Life audio and downloaded fragments stay local and are not committed.
- Queue completion is inferred with a four-second idle window because Codex hook input does not expose queue length.
- Runtime failures must never block a Codex turn or approval request.
- Python code must run on the installed `/usr/bin/python3` version 3.9.6 without third-party packages.

---

## File structure

- `config.json`: user-editable booleans and queue idle duration.
- `.gitignore`: excludes Python caches, downloaded fragments, generated WAV files, and test artifacts.
- `src/codex_intercom/config.py`: configuration defaults and validation.
- `src/codex_intercom/classifier.py`: conservative `Stop` message classification.
- `src/codex_intercom/state.py`: atomic per-session queue state and token transitions.
- `src/codex_intercom/audio.py`: announcement lookup, detached playback, and logging.
- `src/codex_intercom/runtime.py`: event orchestration and hook-compatible output.
- `src/intercom.py`: minimal executable hook entry point.
- `sounds/manifest.json`: HL1 source fragments and generated phrase sequences.
- `scripts/build_sounds.py`: download, normalize, concatenate, and validate WAV assets.
- `scripts/install.py`: idempotent global hook merge and installation record.
- `scripts/uninstall.py`: ownership-aware hook removal.
- `tests/`: standard-library unit and integration tests for each component.
- `README.md`: install, toggle, test, rebuild, and uninstall instructions.

### Task 1: Configuration and final-message classifier

**Files:**
- Create: `.gitignore`
- Create: `config.json`
- Create: `src/codex_intercom/__init__.py`
- Create: `src/codex_intercom/config.py`
- Create: `src/codex_intercom/classifier.py`
- Create: `tests/test_config.py`
- Create: `tests/test_classifier.py`

**Interfaces:**
- Produces: `load_config(path: pathlib.Path) -> dict`
- Produces: `announcement_enabled(config: dict, name: str) -> bool`
- Produces: `classify_stop(message: str) -> str`, returning `response_required`, `blocked`, or `complete`

- [ ] **Step 1: Write failing configuration tests**

```python
class ConfigTests(unittest.TestCase):
    def test_missing_keys_default_to_enabled(self):
        path = self.write_json({"announcements": {"task_started": False}})
        config = load_config(path)
        self.assertFalse(announcement_enabled(config, "task_started"))
        self.assertTrue(announcement_enabled(config, "queue_complete"))

    def test_invalid_json_raises_config_error(self):
        path = self.write_text("{")
        with self.assertRaises(ConfigError):
            load_config(path)
```

- [ ] **Step 2: Run configuration tests and verify RED**

Run: `PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_config -v`

Expected: import failure because `codex_intercom.config` does not exist.

- [ ] **Step 3: Implement configuration defaults and validation**

```python
class ConfigError(ValueError):
    pass

ANNOUNCEMENTS = (
    "task_started", "permission_required", "response_required",
    "queue_item_complete", "task_complete", "queue_complete",
    "subagent_complete", "blocked",
)

def load_config(path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    announcements = raw.get("announcements", {})
    if not isinstance(announcements, dict):
        raise ConfigError("announcements must be an object")
    merged = {name: True for name in ANNOUNCEMENTS}
    for name in ANNOUNCEMENTS:
        value = announcements.get(name, True)
        if not isinstance(value, bool):
            raise ConfigError("announcement values must be boolean")
        merged[name] = value
    idle = raw.get("queue_idle_seconds", 4)
    if not isinstance(idle, (int, float)) or isinstance(idle, bool) or idle <= 0:
        raise ConfigError("queue_idle_seconds must be positive")
    return {"announcements": merged, "queue_idle_seconds": float(idle)}
```

- [ ] **Step 4: Run configuration tests and verify GREEN**

Run: `PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_config -v`

Expected: all configuration tests pass.

- [ ] **Step 5: Write failing classifier tests**

```python
CASES = (
    ("Qual opção você prefere?", "response_required"),
    ("Please confirm which environment I should use.", "response_required"),
    ("Estou bloqueado: preciso da credencial para continuar.", "blocked"),
    ("The failing test was fixed and all checks now pass.", "complete"),
    ("Implementação concluída e verificada.", "complete"),
)

def test_classification_cases(self):
    for message, expected in CASES:
        with self.subTest(message=message):
            self.assertEqual(classify_stop(message), expected)
```

- [ ] **Step 6: Run classifier tests and verify RED**

Run: `PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_classifier -v`

Expected: import failure because `codex_intercom.classifier` does not exist.

- [ ] **Step 7: Implement conservative classifier**

```python
RESPONSE_MARKERS = (
    "please confirm", "please choose", "which do you prefer",
    "preciso que você", "por favor confirme", "qual opção",
    "você prefere", "me diga", "responda",
)

BLOCKED_MARKERS = (
    "i am blocked", "cannot continue", "unable to continue",
    "estou bloqueado", "não consigo continuar", "impasse",
    "failed without recovery", "falhou sem recuperação",
)

def classify_stop(message):
    tail = (message or "").strip()[-1200:]
    lowered = tail.casefold()
    recovered = ("fixed" in lowered or "corrig" in lowered) and (
        "pass" in lowered or "verific" in lowered
    )
    if not recovered and any(marker in lowered for marker in BLOCKED_MARKERS):
        return "blocked"
    if tail.endswith("?") or any(marker in lowered for marker in RESPONSE_MARKERS):
        return "response_required"
    return "complete"
```

- [ ] **Step 8: Run Task 1 tests and commit**

Run: `PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_config tests.test_classifier -v`

Expected: all tests pass.

```bash
git add .gitignore config.json src/codex_intercom tests/test_config.py tests/test_classifier.py
git commit -m "feat: add intercom configuration and classifier"
```

### Task 2: Queue state machine and delayed finalization

**Files:**
- Create: `src/codex_intercom/state.py`
- Create: `tests/test_state.py`

**Interfaces:**
- Produces: `StateStore(root: pathlib.Path)` with `prompt_started(session_id)`, `completion_pending(session_id, turn_id, token)`, `close_attention(session_id)`, and `finalize(session_id, token)`
- Produces: `PromptTransition(previous_pending: bool, batch_count: int)`
- Produces: `FinalizeTransition(announcement: Optional[str])`

- [ ] **Step 1: Write failing single-task and queue tests**

```python
def test_single_item_finalizes_as_task_complete(self):
    first = self.store.prompt_started("s1")
    self.assertFalse(first.previous_pending)
    self.store.completion_pending("s1", "t1", "token-1")
    final = self.store.finalize("s1", "token-1")
    self.assertEqual(final.announcement, "task_complete")

def test_next_prompt_converts_previous_completion_to_queue_item(self):
    self.store.prompt_started("s1")
    self.store.completion_pending("s1", "t1", "token-1")
    second = self.store.prompt_started("s1")
    self.assertTrue(second.previous_pending)
    self.assertEqual(second.batch_count, 2)
    self.store.completion_pending("s1", "t2", "token-2")
    final = self.store.finalize("s1", "token-2")
    self.assertEqual(final.announcement, "queue_complete")
```

- [ ] **Step 2: Run state tests and verify RED**

Run: `PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_state -v`

Expected: import failure because `codex_intercom.state` does not exist.

- [ ] **Step 3: Implement atomic state transitions**

```python
class StateStore:
    def prompt_started(self, session_id):
        with self._locked(session_id) as state:
            pending = bool(state.get("pending_token"))
            count = int(state.get("batch_count", 0)) + 1
            state.update(batch_count=count, pending_token=None, pending_turn=None)
            return PromptTransition(pending, count)

    def finalize(self, session_id, token):
        with self._locked(session_id) as state:
            if state.get("pending_token") != token:
                return FinalizeTransition(None)
            name = "queue_complete" if state.get("batch_count", 0) > 1 else "task_complete"
            state.clear()
            state.update(batch_count=0, pending_token=None, pending_turn=None)
            return FinalizeTransition(name)
```

Use `fcntl.flock`, a temporary sibling file, `os.replace`, and sanitized SHA-256 session filenames so concurrent events cannot corrupt state.

- [ ] **Step 4: Add stale-token and attention-reset tests**

```python
def test_stale_finalizer_is_cancelled(self):
    self.store.prompt_started("s1")
    self.store.completion_pending("s1", "t1", "old")
    self.store.prompt_started("s1")
    self.assertIsNone(self.store.finalize("s1", "old").announcement)

def test_attention_closes_batch(self):
    self.store.prompt_started("s1")
    self.store.close_attention("s1")
    self.assertFalse(self.store.prompt_started("s1").previous_pending)
```

- [ ] **Step 5: Run state tests and commit**

Run: `PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_state -v`

Expected: all state tests pass.

```bash
git add src/codex_intercom/state.py tests/test_state.py
git commit -m "feat: track Codex queue completion state"
```

### Task 3: HL1 phrase manifest and audio builder

**Files:**
- Create: `sounds/manifest.json`
- Create: `scripts/build_sounds.py`
- Create: `tests/test_build_sounds.py`

**Interfaces:**
- Produces: `load_manifest(path: pathlib.Path) -> dict`
- Produces: `source_url(hl1_path: str) -> str`
- Produces: `build_all(project_root: pathlib.Path, runner=subprocess.run) -> None`
- Output: `sounds/generated/<announcement>.wav`

- [ ] **Step 1: Write failing manifest tests**

```python
def test_every_phrase_references_declared_fragments(self):
    manifest = load_manifest(ROOT / "sounds" / "manifest.json")
    fragments = set(manifest["fragments"])
    for sequence in manifest["phrases"].values():
        for token in sequence:
            if not token.startswith("pause_"):
                self.assertIn(token, fragments)

def test_download_url_encodes_slash(self):
    self.assertEqual(
        source_url("vox/attention.wav"),
        "https://hl1sfx.com/download/vox%2Fattention.wav",
    )
```

- [ ] **Step 2: Run builder tests and verify RED**

Run: `/usr/bin/python3 -m unittest tests.test_build_sounds -v`

Expected: import or file failure because the builder and manifest do not exist.

- [ ] **Step 3: Add exact fragment and phrase manifest**

```json
{
  "fragments": {
    "processing": "vox/processing.wav",
    "attention": "vox/attention.wav",
    "security": "vox/security.wav",
    "clearance": "vox/clearance.wav",
    "required": "vox/required.wav",
    "please": "vox/please.wav",
    "acknowledge": "vox/acknowledge.wav",
    "user": "vox/user.wav",
    "communication": "vox/communication.wav",
    "secondary": "vox/secondary.wav",
    "objective": "vox/objective.wav",
    "secured": "vox/secured.wav",
    "final": "vox/final.wav",
    "all": "vox/all.wav",
    "systems": "vox/systems.wav",
    "nominal": "vox/nominal.wav",
    "warning": "vox/warning.wav",
    "failed": "vox/failed.wav"
  },
  "phrases": {
    "task_started": ["processing"],
    "permission_required": ["attention", "pause_sentence", "security", "clearance", "required", "pause_sentence", "please", "acknowledge"],
    "response_required": ["attention", "pause_sentence", "user", "communication", "required", "pause_sentence", "please", "acknowledge"],
    "queue_item_complete": ["secondary", "objective", "secured"],
    "task_complete": ["objective", "secured"],
    "queue_complete": ["final", "objective", "secured", "pause_sentence", "all", "systems", "nominal"],
    "subagent_complete": ["secondary", "objective", "secured"],
    "blocked": ["warning", "pause_sentence", "objective", "failed", "pause_sentence", "user", "acknowledge"]
  }
}
```

- [ ] **Step 4: Implement download, normalization, and concatenation**

Implement `build_all` to:

1. Resolve `ffmpeg` with `/opt/homebrew/bin/ffmpeg` first, then `shutil.which`.
2. Download each fragment with `urllib.request.urlopen`, require HTTP 200 and an audio content type, and cache under `sounds/source/`.
3. Normalize every fragment to mono 22050 Hz PCM signed 16-bit WAV under `sounds/normalized/`.
4. Generate `pause_word.wav` at 0.07 seconds and `pause_sentence.wav` at 0.18 seconds with `anullsrc`.
5. Concatenate each manifest sequence with the ffmpeg concat demuxer and write atomically into `sounds/generated/`.
6. Probe every output with `ffprobe` and require one audio stream with positive duration.

- [ ] **Step 5: Run unit tests, build phrases, and inspect outputs**

Run:

```bash
/usr/bin/python3 -m unittest tests.test_build_sounds -v
/usr/bin/python3 scripts/build_sounds.py
for wav in sounds/generated/*.wav; do /opt/homebrew/bin/ffprobe -v error -show_entries stream=codec_name,sample_rate,channels -of compact "$wav"; done
```

Expected: tests pass; eight WAV files report `pcm_s16le`, `22050`, and one channel.

- [ ] **Step 6: Commit manifest and builder**

```bash
git add sounds/manifest.json scripts/build_sounds.py tests/test_build_sounds.py .gitignore
git commit -m "feat: build Half-Life intercom phrases"
```

### Task 4: Hook runtime and detached playback

**Files:**
- Create: `src/codex_intercom/audio.py`
- Create: `src/codex_intercom/runtime.py`
- Create: `src/intercom.py`
- Create: `tests/test_runtime.py`

**Interfaces:**
- Consumes: `load_config`, `announcement_enabled`, `classify_stop`, and `StateStore`
- Produces: `AudioPlayer(project_root, log_path).play(name) -> bool`
- Produces: `handle_event(event: dict, context: RuntimeContext) -> dict`
- CLI: `/usr/bin/python3 src/intercom.py [--finalize SESSION TOKEN]`

- [ ] **Step 1: Write failing exact-event runtime tests**

```python
def test_permission_request_plays_permission_phrase(self):
    output = handle_event({"hook_event_name": "PermissionRequest", "session_id": "s"}, self.context)
    self.assertEqual(self.player.played, ["permission_required"])
    self.assertEqual(output, {})

def test_disabled_announcement_is_suppressed(self):
    self.config["announcements"]["permission_required"] = False
    handle_event({"hook_event_name": "PermissionRequest", "session_id": "s"}, self.context)
    self.assertEqual(self.player.played, [])
```

- [ ] **Step 2: Run runtime tests and verify RED**

Run: `PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_runtime -v`

Expected: import failure because runtime modules do not exist.

- [ ] **Step 3: Implement audio playback and event orchestration**

```python
def handle_event(event, context):
    name = event.get("hook_event_name")
    session = event.get("session_id", "unknown")
    if name == "PermissionRequest":
        context.play("permission_required")
    elif name == "SubagentStop":
        context.play("subagent_complete")
    elif name == "UserPromptSubmit":
        transition = context.state.prompt_started(session)
        if transition.previous_pending:
            context.play("queue_item_complete")
        context.play("task_started")
    elif name == "Stop":
        kind = classify_stop(event.get("last_assistant_message", ""))
        if kind in ("response_required", "blocked"):
            context.state.close_attention(session)
            context.play(kind)
        else:
            context.schedule_finalize(session, event.get("turn_id", ""))
    return {}
```

`AudioPlayer.play` must use `subprocess.Popen` with `stdin`, `stdout`, and `stderr` set to `DEVNULL`, `start_new_session=True`, and `/usr/bin/afplay` as an absolute executable.

`src/intercom.py` must catch malformed input, configuration, state, scheduling, and playback exceptions, append a timestamped diagnostic to `~/.codex/codex-intercom/intercom.log`, and return exit code zero. When parsed input identifies `Stop` or `SubagentStop`, it must always serialize `{}` to `stdout`; other events emit no stdout.

- [ ] **Step 4: Add queue orchestration and hook-output tests**

```python
def test_stop_schedules_finalizer_without_immediate_completion_sound(self):
    handle_event(self.stop_event("Finished and verified."), self.context)
    self.assertEqual(self.player.played, [])
    self.assertEqual(len(self.scheduler.calls), 1)

def test_stop_waiting_for_user_closes_queue_and_returns_json_object(self):
    output = handle_event(self.stop_event("Qual opção você prefere?"), self.context)
    self.assertEqual(self.player.played, ["response_required"])
    self.assertEqual(output, {})

def test_invalid_config_logs_and_suppresses_audio(self):
    self.context.config_loader = lambda: (_ for _ in ()).throw(ConfigError("bad config"))
    output = run_hook(self.permission_event(), self.context)
    self.assertEqual(output, {})
    self.assertEqual(self.player.played, [])
    self.assertIn("bad config", self.log.read_text(encoding="utf-8"))

def test_stop_cli_always_emits_valid_json_on_runtime_failure(self):
    stdout = io.StringIO()
    exit_code = main(
        stdin=io.StringIO('{"hook_event_name":"Stop","session_id":"s"}'),
        stdout=stdout,
        context_factory=self.failing_context,
    )
    self.assertEqual(exit_code, 0)
    self.assertEqual(json.loads(stdout.getvalue()), {})
```

- [ ] **Step 5: Run runtime suite and commit**

Run: `PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_runtime tests.test_state tests.test_classifier tests.test_config -v`

Expected: all tests pass.

```bash
git add src/intercom.py src/codex_intercom/audio.py src/codex_intercom/runtime.py tests/test_runtime.py
git commit -m "feat: handle Codex lifecycle announcements"
```

### Task 5: Idempotent install and ownership-aware uninstall

**Files:**
- Create: `scripts/install.py`
- Create: `scripts/uninstall.py`
- Create: `tests/test_install.py`

**Interfaces:**
- Produces: `merge_hooks(existing: dict, command: str) -> dict`
- Produces: `remove_owned_hooks(existing: dict, command: str) -> dict`
- CLI: `/usr/bin/python3 scripts/install.py [--codex-home PATH] [--skip-build]`
- CLI: `/usr/bin/python3 scripts/uninstall.py [--codex-home PATH]`

- [ ] **Step 1: Write failing merge-preservation tests**

```python
def test_merge_preserves_unrelated_hooks_and_adds_owned_events(self):
    existing = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other"}]}]}}
    merged = merge_hooks(existing, INTERCOM_COMMAND)
    commands = extract_commands(merged)
    self.assertIn("other", commands)
    self.assertEqual(commands.count(INTERCOM_COMMAND), 4)

def test_repeated_merge_is_idempotent(self):
    once = merge_hooks({}, INTERCOM_COMMAND)
    twice = merge_hooks(once, INTERCOM_COMMAND)
    self.assertEqual(once, twice)
```

- [ ] **Step 2: Run install tests and verify RED**

Run: `/usr/bin/python3 -m unittest tests.test_install -v`

Expected: import failure because installer functions do not exist.

- [ ] **Step 3: Implement installer merge and atomic write**

For each event in `UserPromptSubmit`, `PermissionRequest`, `SubagentStop`, and `Stop`, append exactly one matcher group containing:

```json
{
  "hooks": [
    {
      "type": "command",
      "command": "/usr/bin/python3 /Users/tommy/Offline/projects/codex-intercom/src/intercom.py",
      "timeout": 5,
      "statusMessage": "Black Mesa intercom"
    }
  ]
}
```

Before writing, copy an existing `hooks.json` to `hooks.json.codex-intercom.bak`; write JSON through a sibling temporary file and `os.replace`. Record the exact command and installed events in `~/.codex/codex-intercom/install.json`.

- [ ] **Step 4: Implement uninstall preservation and tests**

```python
def test_uninstall_removes_only_owned_commands(self):
    installed = merge_hooks(self.existing, INTERCOM_COMMAND)
    cleaned = remove_owned_hooks(installed, INTERCOM_COMMAND)
    self.assertEqual(cleaned, self.existing)
```

Remove matcher groups that become empty, keep unrelated handlers in mixed groups, and keep unrelated events untouched.

- [ ] **Step 5: Dry-run installation in a temporary Codex home**

Run:

```bash
tmp_home="$(mktemp -d)"
/usr/bin/python3 scripts/install.py --codex-home "$tmp_home" --skip-build
/usr/bin/python3 -m json.tool "$tmp_home/hooks.json" >/dev/null
/usr/bin/python3 scripts/install.py --codex-home "$tmp_home" --skip-build
/usr/bin/python3 scripts/uninstall.py --codex-home "$tmp_home"
test ! -e "$tmp_home/hooks.json" || /usr/bin/python3 -m json.tool "$tmp_home/hooks.json" >/dev/null
```

Expected: every command exits zero; repeated install creates no duplicates; uninstall removes only owned entries.

- [ ] **Step 6: Run install tests and commit**

Run: `/usr/bin/python3 -m unittest tests.test_install -v`

Expected: all installer tests pass.

```bash
git add scripts/install.py scripts/uninstall.py tests/test_install.py
git commit -m "feat: install and remove Codex intercom hooks"
```

### Task 6: Documentation, global activation, and end-to-end verification

**Files:**
- Create: `README.md`
- Modify: `config.json`
- Modify: `/Users/tommy/.codex/hooks.json` through `scripts/install.py`

**Interfaces:**
- Consumes all previous task CLIs.
- Produces a working global user installation and documented toggle workflow.

- [ ] **Step 1: Write README with exact operations**

Document:

```bash
/usr/bin/python3 scripts/build_sounds.py
/usr/bin/python3 scripts/install.py
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 scripts/uninstall.py
```

Include the complete `config.json` schema, explain that changes apply on the next event, list every phrase, explain the four-second queue inference, and instruct the user to open `/hooks` to trust the installed definitions.

- [ ] **Step 2: Run full automated verification**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 -m json.tool config.json >/dev/null
/usr/bin/python3 -m json.tool sounds/manifest.json >/dev/null
/usr/bin/python3 scripts/build_sounds.py
for wav in sounds/generated/*.wav; do /opt/homebrew/bin/ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$wav"; done
```

Expected: zero test failures, valid JSON, eight positive audio durations.

- [ ] **Step 3: Audibly smoke-test every generated phrase**

Run:

```bash
for wav in sounds/generated/*.wav; do echo "PLAYING $wav"; /usr/bin/afplay "$wav"; done
```

Expected: each phrase is understandable, ordered correctly, and free of truncation or excessive silence. Adjust only manifest pause tokens if cadence needs correction, then rebuild and replay all phrases.

- [ ] **Step 4: Install globally while proving existing config preservation**

Run:

```bash
before="$(shasum -a 256 /Users/tommy/.codex/config.toml)"
/usr/bin/python3 scripts/install.py
after="$(shasum -a 256 /Users/tommy/.codex/config.toml)"
test "$before" = "$after"
/usr/bin/python3 -m json.tool /Users/tommy/.codex/hooks.json >/dev/null
```

Expected: install exits zero, `config.toml` hashes match exactly, and global hooks JSON is valid.

- [ ] **Step 5: Exercise hook payloads without waiting for a live task**

Run representative JSON payloads into `src/intercom.py` for `UserPromptSubmit`, `PermissionRequest`, `SubagentStop`, response-required `Stop`, blocked `Stop`, and completed `Stop`; wait five seconds for finalization and inspect `~/.codex/codex-intercom/intercom.log` for errors.

Expected: immediate events return zero, `Stop` and `SubagentStop` print `{}`, disabled announcements remain silent, and the log contains no playback or state errors.

- [ ] **Step 6: Review hook trust and commit documentation**

Open `/hooks` in Codex, review the four installed definitions, and trust them. Then run one real prompt and confirm the start and completion announcements.

```bash
git add README.md config.json
git commit -m "docs: add Codex intercom operations guide"
git status --short
```

Expected: commit succeeds and `git status --short` is empty except for intentionally ignored generated audio.

## Completion checklist

- [ ] All eight `config.json` toggles default to `true`.
- [ ] All unit and integration tests pass under `/usr/bin/python3` 3.9.6.
- [ ] All eight generated announcements have positive durations and pass audible review.
- [ ] Global hooks are installed once and trusted.
- [ ] Existing Codex `notify` configuration is unchanged.
- [ ] Live start and completion events play the intended phrases.
