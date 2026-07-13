# Transcript Lifecycle Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent interrupted or abandoned Codex sessions from permanently suppressing Half-Life audio and Alokium completion notifications, without expiring legitimate long-running tasks.

**Architecture:** Add a focused transcript lifecycle reader that classifies persisted Codex turns from bounded JSONL tails. Store transcript metadata per active session, reconcile remaining sessions under the existing global lock before final completion, and add a silent `SessionStart` hook for restart/resume metadata recovery.

**Tech Stack:** Python 3 standard library, JSON Lines Codex transcripts, `fcntl` file locking, `unittest`, existing Codex hook installer.

## Global Constraints

- There is no inactivity timeout.
- Transcript contents must never be copied into diagnostic logs.
- Existing announcement phrases and WAV assets must remain unchanged.
- Alokium firmware and the separate Alokium repositories must remain unchanged.
- An unreadable existing transcript must suppress completion conservatively.
- A missing transcript must not block completion indefinitely.

---

### Task 1: Transcript lifecycle reader and state reconciliation

**Files:**
- Create: `src/codex_intercom/lifecycle.py`
- Create: `tests/test_lifecycle.py`
- Modify: `src/codex_intercom/state.py`
- Modify: `tests/test_state.py`

**Interfaces:**
- Produces: `TranscriptLifecycle.inspect(session_id, transcript_path=None, turn_id=None) -> LifecycleResult`
- Produces: `LifecycleResult.status` with `active`, `complete`, `missing`, or `unreadable`
- Produces: `StateStore.prompt_started(session_id, transcript_path=None, turn_id=None)`
- Produces: `StateStore.session_started(session_id, transcript_path=None)`
- Extends: `FinalizeTransition.reconciled` with metadata-only `(session_id, status)` entries

- [ ] **Step 1: Write failing lifecycle tests**

Add tests using temporary JSONL transcripts for:

```python
def test_latest_started_turn_is_active(self):
    path = self.write_events(
        lifecycle("task_started", "turn-1"),
    )
    self.assertEqual(
        self.reader.inspect("session-1", path, "turn-1").status,
        "active",
    )

def test_latest_completed_turn_is_complete(self):
    path = self.write_events(
        lifecycle("task_started", "turn-1"),
        lifecycle("task_complete", "turn-1"),
    )
    self.assertEqual(
        self.reader.inspect("session-1", path, "turn-1").status,
        "complete",
    )

def test_missing_transcript_is_missing(self):
    result = self.reader.inspect("session-1", self.root / "gone.jsonl", "turn-1")
    self.assertEqual(result.status, "missing")

def test_malformed_existing_transcript_is_unreadable(self):
    path = self.root / "broken.jsonl"
    path.write_text("{not-json}\n", encoding="utf-8")
    self.assertEqual(self.reader.inspect("session-1", path).status, "unreadable")

def test_legacy_session_discovers_rollout_by_id(self):
    path = self.sessions / "2026" / "07" / "13" / (
        "rollout-2026-07-13T00-00-00-session-1.jsonl"
    )
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(lifecycle("task_started", "turn-1")) + "\n")
    self.assertEqual(self.reader.inspect("session-1").status, "active")
```

- [ ] **Step 2: Run lifecycle tests and verify RED**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_lifecycle -v
```

Expected: FAIL because `codex_intercom.lifecycle` does not exist.

- [ ] **Step 3: Implement the bounded transcript reader**

Create immutable result metadata and a reader that:

```python
@dataclass(frozen=True)
class LifecycleResult:
    status: str
    path: object = None
    error_type: object = None

class TranscriptLifecycle:
    TERMINAL = frozenset(("task_complete",))

    def __init__(self, sessions_root, max_tail_bytes=1024 * 1024): ...
    def inspect(self, session_id, transcript_path=None, turn_id=None): ...
```

Resolve an explicit path first, then use `sessions_root.glob("**/*{session_id}.jsonl")` for legacy discovery. Seek from the end and read no more than `max_tail_bytes`; discard only the first partial line when the seek offset is nonzero. Parse `event_msg` records whose payload type is `task_started` or `task_complete`, filter by `turn_id` when supplied, and classify the last relevant lifecycle event. Any malformed record in the inspected tail or read error returns `unreadable`; no path returns `missing`.

- [ ] **Step 4: Run lifecycle tests and verify GREEN**

Run the same focused command. Expected: all lifecycle tests pass.

- [ ] **Step 5: Write failing state reconciliation tests**

Add a fake lifecycle inspector with deterministic per-session results and tests proving:

```python
def test_fresh_active_transcript_still_blocks_completion(self): ...
def test_completed_transcript_no_longer_blocks_completion(self): ...
def test_missing_ephemeral_transcript_no_longer_blocks_completion(self): ...
def test_unreadable_transcript_remains_conservatively_active(self): ...
def test_legacy_list_state_discovers_and_preserves_active_transcript(self): ...
def test_session_start_updates_metadata_without_creating_active_work(self): ...
```

Assert the new serialized schema is:

```json
{
  "active_sessions": {
    "session-1": {
      "transcript_path": "/tmp/rollout-session-1.jsonl",
      "turn_id": "turn-1"
    }
  }
}
```

- [ ] **Step 6: Run state tests and verify RED**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_state -v
```

Expected: FAIL because state still stores a list and never invokes lifecycle reconciliation.

- [ ] **Step 7: Implement state migration and reconciliation**

Update `StateStore` to accept a lifecycle inspector, normalize list-based legacy entries into metadata records, and reconcile only during `finalize`. Remove `complete` and `missing` sessions, retain `active` and `unreadable`, preserve batch count semantics, and return metadata-only reconciliation outcomes for tracing. `session_started` may update an existing record but must never add a new active session.

- [ ] **Step 8: Run focused state and lifecycle tests**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_lifecycle tests.test_state -v
```

Expected: all tests pass.

- [ ] **Step 9: Commit Task 1**

```bash
git add src/codex_intercom/lifecycle.py src/codex_intercom/state.py tests/test_lifecycle.py tests/test_state.py
git commit -m "fix: reconcile active sessions from Codex transcripts"
```

---

### Task 2: Runtime and silent SessionStart hook

**Files:**
- Modify: `src/codex_intercom/runtime.py`
- Modify: `tests/test_runtime.py`
- Modify: `scripts/install.py`
- Modify: `tests/test_install.py`

**Interfaces:**
- Consumes: `StateStore.prompt_started(..., transcript_path, turn_id)`
- Consumes: `StateStore.session_started(..., transcript_path)`
- Consumes: `FinalizeTransition.reconciled`
- Produces: installed hook events `SessionStart`, `UserPromptSubmit`, `PermissionRequest`, and `Stop`

- [ ] **Step 1: Write failing runtime tests**

Add tests proving:

```python
def test_prompt_records_transcript_and_turn_metadata(self): ...
def test_session_start_is_silent_and_does_not_create_active_work(self): ...
def test_finalizer_traces_reconciliation_without_transcript_content(self): ...
```

The `SessionStart` test must assert no audio, no Alokium call, and no scheduler call.

- [ ] **Step 2: Run runtime tests and verify RED**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_runtime -v
```

Expected: FAIL because runtime does not pass transcript metadata or handle `SessionStart`.

- [ ] **Step 3: Wire lifecycle state into runtime**

In `create_context`, construct:

```python
lifecycle = TranscriptLifecycle(codex_home / "sessions")
state = StateStore(runtime_root / "state", lifecycle=lifecycle)
```

Pass `event.get("transcript_path")` and `turn_id` on `UserPromptSubmit`. Handle `SessionStart` only through `state.session_started`. Trace one metadata-only `session_reconciled` record per reconciliation result and never include assistant messages or transcript lines.

- [ ] **Step 4: Run runtime tests and verify GREEN**

Run the focused runtime tests. Expected: all pass.

- [ ] **Step 5: Write failing installer tests**

Change the expected event set to include `SessionStart` and add an explicit assertion that reinstall remains idempotent and uninstall preserves unrelated `SessionStart` handlers.

- [ ] **Step 6: Run installer tests and verify RED**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_install -v
```

Expected: FAIL because `EVENTS` lacks `SessionStart`.

- [ ] **Step 7: Add SessionStart to installation**

Set:

```python
EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "PermissionRequest",
    "Stop",
)
```

Update installer output from “three” to “four” definitions. Do not change the command string, timeout, or hook trust model.

- [ ] **Step 8: Run Task 2 focused tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_runtime tests.test_install -v
```

Expected: all tests pass.

- [ ] **Step 9: Commit Task 2**

```bash
git add src/codex_intercom/runtime.py tests/test_runtime.py scripts/install.py tests/test_install.py
git commit -m "feat: recover intercom state on session lifecycle"
```

---

### Task 3: Documentation, installation, and end-to-end repair

**Files:**
- Modify: `README.md`
- Modify: `INSTALLATION.md`
- Runtime state: `~/.codex/codex-intercom/state/global.json`
- Hook config: `~/.codex/hooks.json`

**Interfaces:**
- Consumes: the existing `scripts/install.py` CLI
- Validates: real hook entrypoint, audio dispatch, and semantic Alokium adapter dispatch

- [ ] **Step 1: Update documentation**

Document four installed hooks, explain that transcript lifecycle prevents orphaned sessions from blocking completion, state explicitly that there is no task timeout, and add troubleshooting guidance for `session_reconciled` trace records.

- [ ] **Step 2: Run the full automated suite**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
```

Expected: zero failures and zero errors.

- [ ] **Step 3: Run static repository checks**

```bash
git diff --check
/usr/bin/python3 -m compileall -q src scripts tests
```

Expected: both commands exit 0.

- [ ] **Step 4: Install the updated hooks idempotently**

```bash
/usr/bin/python3 scripts/install.py
```

Verify `~/.codex/hooks.json` contains exactly one owned command under each of the four events and preserves unrelated hooks. Do not quit or restart ChatGPT automatically.

- [ ] **Step 5: Replay the stale-state regression in isolation**

Use a temporary `CODEX_HOME` containing:

- one legacy active session with no transcript;
- one real-format completed transcript;
- a final `Stop` event for the current session.

Invoke the real entrypoint and finalizer with a temporary trace path. Assert the decision emits exactly one completion announcement and that the trace contains reconciliation metadata but no transcript content.

- [ ] **Step 6: Verify both notification destinations**

Run one controlled real semantic completion dispatch. Confirm `/tmp/codex-intercom-hooks.log` reports `audio_started: true` and `alokium_started: true`; confirm the Alokium adapter log records the same announcement. Do not alter firmware or baseline RGB state manually.

- [ ] **Step 7: Confirm the production state repairs automatically**

Run a production-context finalization/reconciliation check under the normal state lock. Verify the missing orphan is removed while transcripts whose latest lifecycle is `task_started` remain active. Do not delete `global.json` manually.

- [ ] **Step 8: Re-run the full suite after installation**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
git diff --check
git status --short --branch
```

Expected: all tests pass; diff check is clean; only intentional documentation changes remain before the final commit.

- [ ] **Step 9: Commit documentation and verification-facing changes**

```bash
git add README.md INSTALLATION.md
git commit -m "docs: explain transcript lifecycle recovery"
```

- [ ] **Step 10: Verify final repository and installed state**

Confirm the checkout is clean except for its intentional commits, list the new commits, confirm `~/.codex/hooks.json` references the current checkout, and report that `SessionStart` becomes active after the user's next normal app reload while the current three hooks already use the corrected runtime immediately.
