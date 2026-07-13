# Active Session Timeout Design

## Problem

The global completion aggregator records each session after `UserPromptSubmit` and removes it after `Stop` or an attention state. If Codex interrupts or abandons a turn without emitting `Stop`, that session remains active forever. Every later finalizer then returns no announcement, so both Half-Life audio and Alokium notifications stop working.

The observed production state contains one such orphaned session. Hooks are still arriving, but all recent finalizers are suppressed by stale global state.

## Chosen Approach

Apply a simple inactivity timeout to active sessions. The default timeout is 1,800 seconds (30 minutes) and is configurable through `active_session_timeout_seconds` in `config.json`.

Each active session stores the UTC time of its most recent lifecycle hook. Before deciding whether completion is globally safe, the state store removes sessions whose last activity is older than the configured timeout. A new prompt refreshes that session's timestamp. `Stop` and attention classifications continue to remove the session immediately.

This intentionally favors recovery from missing hooks over indefinite suppression. A task that emits no lifecycle hook for more than 30 minutes can be considered inactive even if it is still executing; that is the accepted trade-off of the selected timeout-only approach.

## State Migration

The current `active_sessions` list has no timestamps. On first load after the update, existing list entries are treated as legacy stale entries and do not block finalization. New state uses an object mapping session IDs to last-activity timestamps.

This migration clears the already-orphaned production state automatically. No manual deletion or ChatGPT restart is required.

## Runtime Flow

1. `UserPromptSubmit` loads the configured timeout and records the session with the current time.
2. `Stop` preserves the existing classification behavior.
3. A completion finalizer prunes expired sessions under the existing global file lock.
4. If another non-expired session remains, completion stays silent.
5. If none remain, the existing `task_complete` versus `queue_complete` decision runs and dispatches one semantic notification to audio and Alokium.

## Configuration and Validation

`active_session_timeout_seconds` must be a positive number. Missing configuration defaults to 1,800 seconds. Invalid values follow the existing fail-silent hook behavior and are written to the runtime error log.

Tests must prove:

- a fresh concurrent session still blocks completion;
- an expired concurrent session no longer blocks completion;
- a repeated prompt refreshes the inactivity deadline;
- legacy list-based active state is pruned during migration;
- current single-task and multi-task announcement behavior remains unchanged;
- the full intercom suite passes;
- a real isolated hook replay dispatches audio and Alokium after stale state is present.

## Scope

Only `codex-intercom` changes. Audio phrases, WAV assets, Alokium firmware, RGB restoration behavior, and the separate notification repositories remain unchanged.
