# Codex Intercom Design

## Goal

Create a macOS notification layer for Codex that plays short Half-Life 1 intercom announcements when work starts, needs attention, completes, blocks, or drains a prompt queue. The project installs global user-level hooks without replacing the existing Codex `notify` command.

## Design principles

- Use short Black Mesa VOX phrases that communicate state without requiring the screen.
- Keep every announcement independently switchable with a boolean in one JSON file.
- Default every announcement to enabled.
- Preserve existing `~/.codex/config.toml`, especially the Computer Use `notify` command.
- Install hooks through a separate `~/.codex/hooks.json` entry and merge safely if that file already appears later.
- Treat queue completion as an explicit inference with a short idle window because Codex does not expose queue length in hook input.
- Keep the runtime local, dependency-light, and inspectable.

## User-facing announcements

| Config key | Trigger | Phrase assembled from HL1 clips |
| --- | --- | --- |
| `task_started` | `UserPromptSubmit` begins a new item | “Processing.” |
| `permission_required` | `PermissionRequest` | “Attention. Security clearance required. Please acknowledge.” |
| `response_required` | `Stop` is classified as waiting for the user | “Attention. Communication required. Please acknowledge.” |
| `queue_item_complete` | Another queued item begins before the idle window closes | “Secondary objective secured.” |
| `task_complete` | One completed item reaches the idle window with no successor | “Objective secured.” |
| `queue_complete` | A batch of two or more items reaches the idle window | “Final objective secured. All systems nominal.” |
| `subagent_complete` | `SubagentStop` | “Secondary objective secured.” |
| `blocked` | `Stop` is classified as blocked or failed | “Warning. Objective failed. User acknowledge.” |

The VOX word filenames are treated as authoritative even where the website's automatic transcription is inaccurate.

## Configuration

The repository contains `config.json`:

```json
{
  "announcements": {
    "task_started": true,
    "permission_required": true,
    "response_required": true,
    "queue_item_complete": true,
    "task_complete": true,
    "queue_complete": true,
    "subagent_complete": true,
    "blocked": true
  },
  "queue_idle_seconds": 4
}
```

Changing a boolean affects the next hook invocation; no rebuild is required. Unknown keys are ignored. Missing keys fall back to `true`, preserving the requested default. An invalid JSON file causes the runtime to fail silent and write a diagnostic log rather than interrupt Codex.

## Components

### `src/intercom.py`

The hook entry point. It reads one Codex hook event from `stdin`, loads `config.json`, classifies the event, updates per-session queue state, launches `/usr/bin/afplay` detached, and emits valid hook output where required. It never blocks Codex for the duration of a sound.

The module also exposes pure functions for configuration defaults, final-message classification, phrase selection, and queue transitions so tests do not need to play audio.

### `scripts/build_sounds.py`

Downloads only the required WAV fragments from `https://hl1sfx.com/download/<encoded-path>` and composes phrases into `sounds/generated/`. Composition uses the installed `/opt/homebrew/bin/ffmpeg`, falling back to the first `ffmpeg` on `PATH`. Every source URL and phrase word sequence is declared in a small manifest committed to the repository.

The generated phrases are local artifacts and are excluded from Git. The repository stores the manifest, not redistributed Half-Life audio.

### `scripts/install.py`

Performs an idempotent user-level installation:

1. Build or validate generated sounds.
2. Create `~/.codex/hooks.json` if absent.
3. Merge this project's handlers into `UserPromptSubmit`, `PermissionRequest`, `SubagentStop`, and `Stop` without deleting unrelated hooks.
4. Write an installation record under `~/.codex/codex-intercom/` so uninstall can remove only entries owned by this project.
5. Print the `/hooks` trust step required by Codex.

It does not modify the existing `notify` key in `~/.codex/config.toml`.

### `scripts/uninstall.py`

Removes only the hook handler commands installed by this project and its runtime state. It leaves downloaded/generated sounds in the repository unless explicitly asked to purge them.

### Runtime state

Per-session JSON state lives under `~/.codex/codex-intercom/state/`, keyed by `session_id`. Writes are atomic. Each state record tracks the active batch count, the last completed turn, and a generation token used to invalidate delayed queue-finalization processes.

## Event and queue flow

1. `UserPromptSubmit` starts or advances a batch and optionally plays “Processing.”
2. If the prior `Stop` still has a pending completion token, the new prompt proves that prior work was a queue item. The pending final announcement is invalidated and “Secondary objective secured” plays before the new processing announcement.
3. A normal `Stop` schedules a detached finalizer for `queue_idle_seconds` later.
4. If no next prompt invalidates the token:
   - batch count `1` plays `task_complete`;
   - batch count greater than `1` plays `queue_complete`.
5. A waiting-for-user or blocked `Stop` plays its immediate announcement, cancels normal completion, and closes the current batch.
6. `PermissionRequest` and `SubagentStop` play independently and do not change the main queue batch.

This design intentionally avoids announcing both “Objective secured” and “Final objective secured” for a single-item batch.

## Classification rules

`PermissionRequest`, `UserPromptSubmit`, and `SubagentStop` are exact event mappings.

`Stop` classification uses only the final portion of `last_assistant_message`:

- `response_required` wins when the message ends in a direct question or contains an explicit request for confirmation, selection, missing information, or user action.
- `blocked` wins over normal completion when the final status explicitly says work cannot continue, is blocked, or failed without recovery.
- Otherwise the result is a normal completion candidate and enters queue finalization.

The classifier is deliberately conservative: uncertain messages become normal completion rather than producing repeated attention alarms.

## Error handling

- Missing sound: log and continue without interrupting Codex.
- Invalid config: log and play nothing for that event.
- Network/build failure: installation fails before changing hooks.
- Invalid hook input: exit successfully with no sound; for `Stop` and `SubagentStop`, emit `{}` when the event name can be recovered.
- Concurrent hook events: serialize state updates with a per-session lock and atomic replace.
- Audio playback failure: record it in `~/.codex/codex-intercom/intercom.log`; never block the Codex event.

## Testing

Use Python's standard `unittest` so runtime tests require no package installation.

- Configuration defaults and per-announcement opt-out.
- Exact event-to-announcement mappings.
- English and Portuguese response-required examples.
- Blocked/failure examples and recovered-error counterexamples.
- Single-item completion versus multi-item queue completion.
- Cancellation of stale finalizer tokens.
- Valid JSON output for `Stop` and `SubagentStop`.
- Install merge and uninstall preservation using temporary Codex homes.
- Build manifest validation and HTTP/content-type checks without committing audio.

Verification includes unit tests, a dry-run install into a temporary `CODEX_HOME`, JSON validation, generated audio inspection with `ffprobe`, and manual `afplay` smoke tests for every enabled phrase.

## Acceptance criteria

- Every announcement is present in `config.json` with default `true`.
- Flipping any announcement to `false` suppresses only that announcement on the next event.
- Existing Codex `notify` configuration remains byte-for-byte unchanged.
- Hooks are installed without removing unrelated global hooks.
- A single completed task produces only the single-task completion phrase.
- Consecutive queued items produce item completion announcements and exactly one final queue announcement.
- Waiting-for-user and blocked states do not produce a false queue-complete announcement.
- All automated verification passes and each generated phrase is audibly checked on macOS.
