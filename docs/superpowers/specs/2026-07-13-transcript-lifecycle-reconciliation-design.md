# Transcript Lifecycle Reconciliation Design

## Problem

The global completion aggregator records each session after `UserPromptSubmit` and removes it after `Stop` or an attention state. If Codex interrupts or abandons a turn without emitting `Stop`, that session remains active forever. Every later finalizer then returns no announcement, so both Half-Life audio and Alokium notifications stop working.

The production trace confirms this failure mode: hooks continue arriving, but one orphaned session remains in `active_sessions`, causing every later finalizer to produce `announcement: null` before either notification destination is called.

## Source of Truth

Use Codex's own transcript lifecycle as the authoritative task state. Hook payloads expose `transcript_path`, `session_id`, and `turn_id`; the transcript records `event_msg` lifecycle entries such as `task_started` and `task_complete`.

There is no inactivity timeout. A legitimate task remains active for any duration while its latest lifecycle entry is `task_started`.

## Stored State

Each active session stores:

- `transcript_path` received by the hook;
- `turn_id` for the active turn.

The global state continues to store batch count and pending-finalizer data under the existing file lock. The `active_sessions` field changes from a list of IDs to an object keyed by session ID.

## Reconciliation

Before a finalizer decides whether the global queue is complete, it reconciles every other active session:

1. Resolve the stored transcript path. Legacy entries without one may be recovered by finding a Codex rollout filename containing the session ID.
2. Read only a bounded tail of the JSON Lines file, expanding the tail only when needed to locate the latest lifecycle entry for the recorded turn.
3. Keep the session active when its latest relevant lifecycle entry is `task_started` and no terminal entry follows it.
4. Remove the session when `task_complete` follows the relevant start. This is the terminal lifecycle event present in the installed Codex transcripts, including turns that finish without a usable `Stop` hook.
5. Remove a session when Codex has moved its transcript into `archived_sessions`; archiving is a positive terminal state even if an interrupted turn never wrote `task_complete`.
6. If a transcript is missing, temporarily unreadable, or malformed, retain the session. The completed item may announce, but final queue completion remains suppressed. This is the conservative failure mode.

The session that emitted the current `Stop` is still removed immediately by the existing completion-pending transition. Reconciliation is for the remaining sessions that could otherwise block the global decision.

## SessionStart Recovery

Install the same intercom entrypoint for `SessionStart`. This event never announces audio or LEDs. It only records or refreshes the session's transcript metadata and reconciles legacy state after startup, resume, clear, or compaction.

`SessionStart` must not clear unrelated active sessions and must not treat compaction as completion.

## Migration

Existing list-based `active_sessions` entries are loaded as legacy records without transcript metadata. Reconciliation attempts to discover their rollout files by session ID. Persisted active tasks remain protected; missing orphaned sessions are removed automatically.

No ChatGPT restart is required for state migration after the runtime code changes, but adding the new `SessionStart` hook definition requires the normal hook reload and trust flow. The existing three hooks continue working before that reload, and finalizer reconciliation alone repairs the current failure.

## Notification Flow

1. `UserPromptSubmit` records the active session's transcript and turn.
2. `Stop` retains the existing response-required, blocked, and delayed-completion classification behavior.
3. The delayed finalizer reconciles all remaining active sessions from transcripts.
4. A transcript moved to Codex's `archived_sessions` directory is terminal even when an interrupted turn has no `task_complete` record.
5. If any session is still active or conservatively unreadable, the completed item dispatches `queue_item_complete` while final queue completion remains pending.
6. Otherwise, the existing `task_complete` versus `queue_complete` decision dispatches one semantic notification to both audio and Alokium.

## Error Handling and Privacy

- Transcript contents are never copied to the intercom trace.
- Diagnostic events contain only session ID, lifecycle classification, and error type.
- Missing files are classified separately from unreadable files.
- Malformed tail records do not crash Codex or remove a possibly active session.
- Hook execution retains the existing fail-silent contract.

## Validation

Tests must prove:

- a concurrent transcript ending in `task_started` blocks completion, regardless of age;
- a concurrent transcript ending in `task_complete` no longer blocks completion;
- a persisted turn that reaches `task_complete` without a usable `Stop` hook no longer blocks completion;
- a missing transcript keeps final queue completion blocked but does not silence completed queue items;
- an unreadable or malformed existing transcript remains conservatively active;
- compaction and `SessionStart` do not produce announcements or clear real active work;
- legacy list-based state migrates and discovers persisted active transcripts;
- current single-task and multi-task announcement behavior remains unchanged;
- the installer adds `SessionStart` idempotently and uninstall removes only owned hooks;
- the full intercom suite passes;
- an isolated real-format hook replay repairs stale state and dispatches the expected semantic notification to audio and Alokium.

## Scope

Only `codex-intercom` changes. Audio phrases, WAV assets, Alokium firmware, RGB restoration behavior, and the separate notification repositories remain unchanged.
