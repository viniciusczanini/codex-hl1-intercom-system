# Global Task Completion Design

## Goal

Prevent `Objective secured` and green Alokium alerts while any Codex task is still active, including tasks running in different sessions.

## Root Cause

The installed `Stop` hook reports that one Codex turn stopped. It does not report that the desktop-wide task queue is empty. The current state store and four-second finalizer are keyed by `session_id`, so a finalizer for session A cannot see a newer active prompt in session B.

Observed evidence on 2026-07-12:

- session A received `Stop` at 16:30:47 and scheduled completion;
- session B received `UserPromptSubmit` at 16:30:50;
- session A emitted `task_complete` at 16:30:51 while session B remained active.

## Design

The state store will maintain one global batch alongside per-session state. `UserPromptSubmit` marks its session active, increments the global batch only for a newly active turn, and invalidates any pending global completion token. `Stop` closes that session for completion purposes and records its completed turn.

An ordinary complete `Stop` schedules a global finalizer. The finalizer may announce only when:

1. its token is still current;
2. no session is active;
3. no newer prompt arrived during the four-second idle window.

If another session remains active, the stop is recorded but no completion finalizer is allowed to announce. When the last active session later stops, its finalizer covers the entire global batch.

The final announcement is:

- `task_complete` when the global batch contains one completed task;
- `queue_complete` when it contains two or more completed tasks, whether sequential or concurrent.

`queue_item_complete` remains available for a new prompt that follows a pending completed stop, but it must not also cause a later duplicate completion for that same item.

## Immediate Outcomes

`PermissionRequest`, `response_required`, and `blocked` remain immediate. Attention or blocked stops close their own session and invalidate any completion pending for that session, but they do not falsely close other active sessions.

`SubagentStop` remains fully silent and does not affect global activity.

## Persistence and Compatibility

Global state is stored under the existing private runtime state directory using the same file-locking and atomic-write conventions. Existing per-session files are migrated lazily: missing global fields start empty, so upgrading does not require deleting local state.

Audio and Alokium continue to receive one semantic decision from `RuntimeContext.dispatch`. No Alokium or firmware changes are required.

## Tests

Automated tests must prove:

- session A cannot announce completion while session B is active;
- the last stopping session announces one `queue_complete` for two sessions;
- a newer prompt invalidates an older global finalizer token;
- one isolated session still announces `task_complete` after four idle seconds;
- response-required and blocked events do not close unrelated sessions;
- `SubagentStop` remains silent and does not alter global state;
- stale state files from the previous schema load safely.

An end-to-end replay will submit two session IDs, stop the first, run its finalizer, and verify no audio/Alokium dispatch; after stopping the second, exactly one finalized semantic announcement must appear.
