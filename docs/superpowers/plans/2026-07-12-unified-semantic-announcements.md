# Unified Semantic Announcements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make audio and Alokium consume the same finalized Codex announcements, silence `SubagentStop`, and prefix spoken WAVs with the authentic `vox/buzwarn.wav` signal.

**Architecture:** `codex-intercom` owns raw-hook classification, queue state, and finalization. Its runtime dispatches each resolved announcement independently to audio and a semantic Alokium adapter; the adapter no longer classifies raw Codex hooks.

**Tech Stack:** Python 3 standard library, `unittest`, JSON hook payloads, WAV/AIFF tooling already used by the project, macOS `afplay`.

## Global Constraints

- Do not modify Alokium firmware.
- `SubagentStop` must be silent in both systems.
- A raw completed `Stop` must not send success before the four-second queue finalizer resolves it.
- Every spoken asset must start with original Half-Life `vox/buzwarn.wav` audio.
- Output failures must never break Codex hook responses.

---

### Task 1: Semantic Alokium adapter

**Files:**
- Modify: `/Users/tommy/Offline/projects/codex_alokium_intercom/src/codex_alokium_intercom/runtime.py`
- Delete: `/Users/tommy/Offline/projects/codex_alokium_intercom/src/codex_alokium_intercom/classifier.py`
- Modify: `/Users/tommy/Offline/projects/codex_alokium_intercom/tests/test_runtime.py`
- Delete: `/Users/tommy/Offline/projects/codex_alokium_intercom/tests/test_classifier.py`

**Interfaces:**
- Consumes: `{"announcement": str, "session_id": str?, "turn_id": str?}` on stdin.
- Produces: `map_announcement(name: str) -> str | None`, mapping permission/response to `attention`, blocked to `error`, and finalized completion announcements to `success`.

- [ ] **Step 1: Replace raw-hook mapping tests with failing semantic mapping tests**

Test all allowlisted names, ensure `task_started`, `subagent_complete`, `SubagentStop`, and raw `Stop` payloads map to no notification, and assert the CLI remains fail-open.

- [ ] **Step 2: Run the adapter tests and verify RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_runtime -v`

Expected: FAIL because `map_announcement` does not exist and raw `Stop` still maps to success.

- [ ] **Step 3: Implement the semantic mapping and remove raw classification**

Use an immutable mapping:

```python
ANNOUNCEMENT_KINDS = {
    "permission_required": "attention",
    "response_required": "attention",
    "blocked": "error",
    "queue_item_complete": "success",
    "task_complete": "success",
    "queue_complete": "success",
}
```

Trace the `announcement` field, ignore unknown payloads, and always return success without printing hook JSON because this adapter is no longer installed as a Codex hook.

- [ ] **Step 4: Run all adapter tests and verify GREEN**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 5: Commit the adapter change**

```bash
git add -A
git commit -m "fix: consume finalized Codex announcements"
```

### Task 2: Unified runtime dispatch and silent subagents

**Files:**
- Modify: `/Users/tommy/Offline/projects/codex-intercom/src/codex_intercom/runtime.py`
- Modify: `/Users/tommy/Offline/projects/codex-intercom/src/codex_intercom/bridge.py`
- Modify: `/Users/tommy/Offline/projects/codex-intercom/tests/test_runtime.py`
- Modify: `/Users/tommy/Offline/projects/codex-intercom/tests/test_bridge.py`
- Modify: `/Users/tommy/Offline/projects/codex-intercom/config.json`
- Modify: `/Users/tommy/Offline/projects/codex-intercom/src/codex_intercom/config.py`

**Interfaces:**
- Produces: `SemanticNotifier.notify(announcement, session_id=None, turn_id=None) -> bool`.
- `RuntimeContext.dispatch(name, session_id=None, turn_id=None)` independently attempts audio and semantic forwarding.

- [ ] **Step 1: Write failing tests for silent `SubagentStop` and resolved-only forwarding**

Assert no output destinations are called for `SubagentStop`; raw completed `Stop` only schedules; permission/response/blocked dispatch immediately; finalizer and queue transition dispatch their resolved names once; adapter failure does not suppress audio.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_runtime tests.test_bridge -v`

Expected: FAIL because the bridge forwards raw events and `SubagentStop` plays audio.

- [ ] **Step 3: Implement semantic dispatch**

Move adapter process launching behind `SemanticNotifier`, pass compact JSON on stdin, inject it into `RuntimeContext`, and replace `play(...)` calls with `dispatch(...)`. Remove raw forwarding from `bridge.main`; internal finalizers use the same context and therefore forward resolved completion.

- [ ] **Step 4: Remove obsolete subagent announcement configuration**

Delete `subagent_complete` from config validation and defaults. Preserve the required `{}` output for `SubagentStop` without side effects.

- [ ] **Step 5: Run the full intercom test suite and verify GREEN**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 6: Commit unified dispatch**

```bash
git add -A
git commit -m "fix: unify finalized audio and LED announcements"
```

### Task 3: Authentic `buzwarn` prefix and bundled assets

**Files:**
- Modify: `/Users/tommy/Offline/projects/codex-intercom/sounds/manifest.json`
- Modify: `/Users/tommy/Offline/projects/codex-intercom/scripts/build_sounds.py`
- Modify: `/Users/tommy/Offline/projects/codex-intercom/tests/test_build_sounds.py`
- Modify: `/Users/tommy/Offline/projects/codex-intercom/assets/*.wav`
- Delete: `/Users/tommy/Offline/projects/codex-intercom/assets/subagent_complete.wav`

**Interfaces:**
- Consumes: `fragments.buzwarn = "vox/buzwarn.wav"`.
- Produces: every generated phrase WAV beginning with the normalized `buzwarn` samples and a short pause.

- [ ] **Step 1: Write a failing generated-audio prefix test**

Build into a temporary directory and compare each phrase's initial PCM frames with the independently normalized `buzwarn` fragment. Also assert `subagent_complete` is absent.

- [ ] **Step 2: Run the sound tests and verify RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_build_sounds -v`

Expected: FAIL because the manifest has no `buzwarn` fragment and existing assets begin directly with speech.

- [ ] **Step 3: Add the fragment and builder-level prefix**

Download `https://hl1sfx.com/download/vox%2Fbuzwarn.wav` through the existing builder path, normalize once, and prepend it plus `pause_sentence` to every manifest phrase without duplicating tokens in each phrase declaration.

- [ ] **Step 4: Rebuild bundled assets and verify GREEN**

Run: `python3 scripts/build_sounds.py`

Then: `PYTHONPATH=src python3 -m unittest discover -s tests -v`

Expected: assets rebuilt and all tests pass.

- [ ] **Step 5: Commit assets**

```bash
git add sounds/manifest.json scripts/build_sounds.py tests/test_build_sounds.py assets
git commit -m "feat: prefix announcements with Half-Life buzwarn"
```

### Task 4: Installation, documentation, and end-to-end verification

**Files:**
- Modify: `/Users/tommy/Offline/projects/codex-intercom/INSTALLATION.md`
- Modify: `/Users/tommy/Offline/projects/codex-intercom/README.md`
- Modify: `/Users/tommy/Offline/projects/codex_alokium_intercom/README.md`
- Modify: installer tests/files only where required to remove obsolete direct Alokium hooks.

**Interfaces:**
- Installed Codex hooks invoke only `/Users/tommy/Offline/projects/codex-intercom/src/intercom.py`.
- That bridge sends semantic payloads to `/Users/tommy/Offline/projects/codex_alokium_intercom/src/intercom.py`.

- [ ] **Step 1: Write failing installation tests for a single hook owner**

Assert the Alokium adapter installer removes its owned direct hooks and the Half-Life installer remains the active hook command.

- [ ] **Step 2: Run installer tests and verify RED**

Run both projects' installation test modules and confirm the old direct-hook expectation fails.

- [ ] **Step 3: Update installers and English documentation**

Document semantic behavior, silent subagents, `buzwarn`, the HL1SFX URL, Valve/HL1SFX credits, toggles, logs, and reinstallation commands.

- [ ] **Step 4: Run both complete test suites**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v` in each repository.

Expected: all tests pass with no warnings or errors.

- [ ] **Step 5: Install and replay representative hooks**

Reinstall the Half-Life hook, ensure direct Alokium hooks are absent, then replay permission, subagent, completed stop plus prompt, and finalized completion sequences. Inspect `/tmp/codex-intercom-hooks.log` and the Alokium hook log to verify exact dispatch counts.

- [ ] **Step 6: Verify runtime health and commit**

Confirm the local notification service is running, working trees contain only intended changes, and no firmware files changed.

```bash
git add -A
git commit -m "docs: explain unified Codex notifications"
```

### Task 5: Final verification and publication

**Files:** No new implementation files.

- [ ] **Step 1: Run clean final verification**

Run both full suites again, validate generated WAV headers/durations, inspect installed hook configuration, and run `git diff --check` in both repositories.

- [ ] **Step 2: Push the public intercom repository**

Push `/Users/tommy/Offline/projects/codex-intercom` `main` to its configured personal `origin`. Do not create or use an institutional remote.

- [ ] **Step 3: Record exact final state**

Report commit IDs, test counts, installed hook command, service health, and whether the two Alokium repositories have remotes.
