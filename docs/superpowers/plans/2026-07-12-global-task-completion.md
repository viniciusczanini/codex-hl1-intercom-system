# Global Task Completion Implementation Plan

**Goal:** Announce completion only after every active Codex session has stopped and the global four-second idle window expires.

**Architecture:** Replace independent per-session completion state with one atomically locked global state document containing active sessions, global batch count, and one finalizer token. Raw hooks keep their existing semantic classification; only completion aggregation changes.

## Task 1: Global state transitions

- Write failing state tests for two overlapping sessions, stale global tokens, isolated completion, attention isolation, and old-schema loading.
- Move `prompt_started`, `completion_pending`, `close_attention`, and `finalize` to the global lock.
- Ensure a finalizer returns no announcement while any session is active.
- Run `PYTHONPATH=src python3 -m unittest tests.test_state -v` and commit.

## Task 2: Runtime regression

- Write a failing runtime test reproducing session A stop followed by session B activity.
- Verify session A finalizer dispatches neither audio nor Alokium.
- Verify session B stop and finalizer dispatch exactly one `queue_complete`.
- Run the complete intercom suite and commit.

## Task 3: Documentation and live replay

- Document that `Stop` is aggregated globally and completion waits for every active session.
- Replay two distinct session IDs through the installed hook and inspect structured logs.
- Run all tests, reinstall hooks if needed, push personal `origin/main`, and report the exact commit.
