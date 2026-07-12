# Unified Semantic Announcements Design

## Goal

Make the Half-Life intercom and Alokium LEDs announce only meaningful Codex outcomes. Internal subagent completion must remain silent in both systems, and an intermediate raw `Stop` must never be treated as a completed task.

Every spoken Half-Life announcement must begin with the authentic Black Mesa announcement signal `vox/buzwarn.wav`.

## Root Cause

The intercom runtime delays ordinary `Stop` completion for four seconds so a following `UserPromptSubmit` can turn it into a queue-item transition. The Alokium bridge bypasses that decision and forwards the raw `Stop` immediately, so the LED can announce success before the queue state is known.

Separately, the audio runtime maps every `SubagentStop` directly to `subagent_complete`. Those events describe internal worker lifecycle, not a user-visible task outcome, so they produce announcements while the main task is still active.

## Considered Approaches

### 1. Filter only the known bad events

Ignore `SubagentStop` and delay raw `Stop` forwarding to Alokium. This is a small patch, but it duplicates the queue and classification rules across processes and can drift again.

### 2. Use one semantic decision source (selected)

The intercom runtime remains the sole owner of hook classification, queue state, and finalization. It emits a semantic announcement only after deciding what happened, and both audio and Alokium consume that same announcement. This removes the timing race and guarantees both outputs agree.

### 3. Build a separate event broker

Introduce a persistent daemon and event queue between Codex and all notification outputs. This would support future integrations, but it adds unnecessary lifecycle and recovery complexity for the current local system.

## Architecture

`RuntimeContext` will expose a single announcement dispatch operation. Dispatch first checks the existing per-announcement audio configuration, plays audio when enabled, and independently forwards the semantic announcement to the Alokium adapter. Alokium availability or failure must never block or fail the Codex hook.

The raw-event forwarding path in `bridge.py` will be removed. The bridge will invoke the runtime only; the runtime will dispatch finalized semantic events at the point where it currently calls `play`.

The allowed semantic announcements are:

- `permission_required`
- `response_required`
- `blocked`
- `queue_item_complete`
- `task_complete`
- `queue_complete`
- `task_started` when enabled for audio; it does not trigger an Alokium completion/attention alert

`SubagentStop` will be acknowledged with the required empty hook response but will produce no semantic announcement, audio, or LED activity. The obsolete `subagent_complete` phrase, config key, generated asset, and documentation references will be removed.

## Event Flow

### Permission and attention

`PermissionRequest` dispatches `permission_required` immediately. A `Stop` classified as `response_required` dispatches `response_required` immediately. Alokium maps both to blue.

### Blocked

A `Stop` classified as `blocked` dispatches `blocked` immediately. Alokium maps it to red.

### Completion and queue transitions

An ordinary completed `Stop` only schedules the existing four-second finalizer. It sends no audio or LED notification immediately.

If a new prompt arrives before finalization, the pending stop becomes `queue_item_complete`; that semantic announcement is dispatched once and Alokium maps it to green.

If the idle timer expires, the state store chooses `task_complete` or `queue_complete`; the finalizer dispatches that semantic announcement once and Alokium maps it to green.

### Subagents

`SubagentStop` is ignored by the semantic layer. It cannot change queue state or create an output in either destination.

## Alokium Adapter Contract

The Codex adapter will accept a small semantic JSON payload instead of raw Codex hooks:

```json
{"announcement":"task_complete","session_id":"...","turn_id":"..."}
```

Only the allowlisted semantic announcements above are accepted. Unknown or malformed payloads are logged and ignored. The generic `alokium_notifications` package remains independent of Codex and continues receiving only notification commands such as success, attention, and error.

## Half-Life Signal

The fragment manifest will include `buzwarn` from `vox/buzwarn.wav`. The sound builder will prepend it, followed by a short pause, to every enabled spoken phrase during asset generation. The prefix is part of each final WAV rather than a separate playback call, so `afplay` cannot overlap the signal and speech.

`buzwarn.wav` is an original Half-Life game asset listed at the same `valve/sound/vox/buzwarn.wav` path and size by SteamDB and HL1SFX. Documentation will credit Valve and HL1SFX consistently with the existing bundled-asset credits.

## Reliability and Logging

Semantic dispatch logs the announcement name and the result of each destination independently. Audio suppression does not suppress Alokium unless the Alokium integration is separately disabled. Adapter errors are caught and logged without changing the hook's successful empty response.

This change does not modify Alokium firmware. RGB restoration retries remain owned by the generic Alokium notification project and are outside this semantic-hook fix.

## Configuration

Existing per-audio announcement booleans remain easy to change in `config.json`. A separate Alokium integration flag controls semantic forwarding globally. `SubagentStop` has no toggle because it is deliberately unsupported as a user-visible notification.

## Tests

Automated tests will prove:

- `SubagentStop` produces no audio, semantic forwarding, scheduler call, or state transition.
- Raw completed `Stop` schedules finalization but sends no Alokium success.
- Permission, response-required, and blocked decisions reach audio and Alokium once.
- Queue-item, task, and queue completion reach audio and Alokium only after state resolution.
- A prompt arriving before the finalizer prevents a false task-complete alert.
- Adapter failure cannot break audio or the Codex hook response.
- Every generated spoken asset begins with the normalized `buzwarn` fragment.
- Removed `subagent_complete` configuration and assets are not required by installation validation.

End-to-end verification will replay representative JSON hook sequences into the installed bridge, inspect the structured hook log and Alokium adapter log, and confirm exactly one expected output per semantic transition.

## Success Criteria

- Internal subagent completion is silent in both systems.
- Neither system announces completion from an unresolved raw `Stop`.
- Audio and LED outcomes are derived from the same semantic decision.
- Every spoken phrase begins with the authentic Half-Life `buzwarn` signal.
- All automated tests pass and installed hooks continue returning valid empty responses.
