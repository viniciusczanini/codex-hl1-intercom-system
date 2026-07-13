# Installation and Usage

Codex HL1 Intercom System plays Half-Life 1 VOX-style announcements for Codex lifecycle events on macOS. Every spoken announcement starts with the original `vox/buzwarn.wav` signal. The repository includes seven final WAV phrases, so normal installation does not require downloading or building audio.

## Requirements

- macOS with `/usr/bin/afplay`
- Codex in the ChatGPT desktop app or Codex CLI with lifecycle hooks support
- `/usr/bin/python3` 3.9 or later
- Git

`ffmpeg` and `ffprobe` are not required for normal installation. They are only needed if you choose to rebuild the bundled audio assets.

## Quick start

```bash
git clone https://github.com/viniciusczanini/codex-hl1-intercom-system.git
cd codex-hl1-intercom-system
/usr/bin/python3 scripts/install.py
```

The installer:

1. Validates every bundled WAV in `assets/`.
2. Preserves unrelated handlers already present in `~/.codex/hooks.json`.
3. Adds four intercom handlers for `SessionStart`, `UserPromptSubmit`, `PermissionRequest`, and `Stop`.
4. Leaves `~/.codex/config.toml` and its existing `notify` command unchanged.
5. Records installation ownership in `~/.codex/codex-intercom/install.json` so uninstalling removes only this project.

Running the installer again is safe and does not duplicate hooks.

## Activate the hooks

After installation:

1. Open `/hooks` in Codex.
2. Review and trust the four entries labelled **Black Mesa intercom**.
3. If the ChatGPT desktop app was already open during installation, quit it normally and reopen it once.

The desktop app loads hook definitions when its embedded Codex process starts. This restart is only needed after installing or changing hook definitions. Editing announcement toggles in `config.json` takes effect on the next event without another restart.

If the separate `codex_alokium_intercom` repository exists beside this checkout, this runtime sends it the same finalized semantic announcement used for audio. It never forwards raw `Stop` or `SubagentStop` events. No second hook definition is required for the LED bridge.

## Announcements

| Setting | Phrase | Trigger |
| --- | --- | --- |
| `task_started` | “Processing.” | A prompt or queued task starts |
| `permission_required` | “Attention. Security clearance required. Please acknowledge.” | Codex requests permission |
| `response_required` | “Attention. Communication required. Please acknowledge.” | Codex finishes with a direct question or request |
| `queue_item_complete` | “Secondary objective secured.” | A new queued prompt follows a completed item |
| `task_complete` | “Final objective reached.” | One task finishes with no queued successor |
| `queue_complete` | “Final objective secured. All systems nominal.” | A batch of two or more queued tasks finishes |
| `blocked` | “Warning. Objective failed. User acknowledge.” | Codex reports that it cannot continue |

Internal subagent completion is intentionally silent in both audio and Alokium.

## Configure announcements

Edit `config.json` in the cloned repository:

```json
{
  "announcements": {
    "task_started": false,
    "permission_required": true,
    "response_required": true,
    "queue_item_complete": true,
    "task_complete": true,
    "queue_complete": true,
    "blocked": true
  },
  "alokium_enabled": true,
  "queue_idle_seconds": 4
}
```

Set any announcement to `false` to mute only that event. Missing announcement keys default to `true`. The shipped configuration keeps `task_started` disabled to avoid playing “Processing” for every submitted prompt.

`queue_idle_seconds` controls how long the intercom waits for another prompt before announcing that a task or queue has finished. Increase it if queued prompts on your machine routinely take more than four seconds to begin.

Completion is aggregated across Codex sessions. A `Stop` from one task cannot play “Final objective reached” while another observed session remains active. Before the final decision, Intercom checks the bounded tail of each Codex transcript for its real `task_started` or `task_complete` lifecycle. This repairs sessions left behind when an interrupted task never emits `Stop`.

There is no task timeout. A persisted task ending in `task_started` remains active no matter how long it runs. `SessionStart` is silent and only refreshes lifecycle metadata after startup, resume, clear, or compaction.

Set `alokium_enabled` to `false` to disable LED notifications while keeping audio active.

Invalid configuration does not interrupt Codex. The event is skipped and the error is written to `~/.codex/codex-intercom/intercom.log`.

## Test the installation

Use these simple checks after trusting the hooks:

### Response required

Ask Codex to ask you a question before doing any work. When it stops on the question, the intercom should play the communication-required announcement.

### Single task

Send one small task and wait longer than `queue_idle_seconds`. The intercom should play “Final objective reached.”

### Queued tasks

Submit two or more small tasks in quick succession. It should play “Secondary objective secured.” between queue items and “Final objective secured. All systems nominal.” once after the entire queue drains.

### Play the bundled files directly

```bash
for wav in assets/*.wav; do
  echo "PLAYING $wav"
  /usr/bin/afplay "$wav"
done
```

## Troubleshooting

### Follow hook execution

The temporary JSON Lines trace records hook metadata, classification, scheduling, and playback status:

```bash
tail -f /tmp/codex-intercom-hooks.log
```

It does not store prompt or assistant-message content. macOS may remove this file after a reboot.

Useful trace stages include:

- `hook_received`: Codex invoked the hook.
- `stop_classified`: the final response was classified as complete, blocked, or waiting for the user.
- `finalizer_scheduled`: completion is waiting for the queue idle window.
- `play_attempted`: audio playback was started.
- `play_suppressed`: the announcement is disabled in `config.json`.
- `hook_failed`: the hook raised an error.
- `announcement_dispatched`: audio and semantic Alokium results for one finalized announcement.
- `session_state_refreshed`: a silent `SessionStart` refreshed persisted metadata.
- `session_reconciled`: another session was classified as `active`, `complete`, `missing`, or conservatively `unreadable` from its transcript.
- `subagent_stop_ignored`: an internal subagent event was intentionally silenced.

### Check runtime errors

```bash
tail -n 100 ~/.codex/codex-intercom/intercom.log
```

This log reports invalid configuration, missing sound files, and playback-launch failures.

### No hook events appear

1. Confirm the four entries exist and are trusted in `/hooks`.
2. Confirm `~/.codex/hooks.json` points to the current clone.
3. Quit and reopen the ChatGPT desktop app once.
4. Rerun `/usr/bin/python3 scripts/install.py` if the repository was moved.

The installer automatically removes its stale command when reinstalling from a new project path.

### Hooks run but no sound plays

1. Check that the event is enabled in `config.json`.
2. Play one file directly with `/usr/bin/afplay assets/task_complete.wav`.
3. Inspect both logs above for `play_suppressed`, `missing sound`, or `playback failed`.
4. Inspect `session_reconciled` records. `active` means another transcript still has running work; `unreadable` fails conservatively and should be checked for file access or malformed JSONL.

## Update

Pull the latest version and rerun the installer so moved or changed hook definitions are refreshed:

```bash
cd codex-hl1-intercom-system
git pull --ff-only
/usr/bin/python3 scripts/install.py
```

Review `/hooks` again if Codex asks you to trust a changed definition. Restart the desktop app once if the hook command itself changed.

## Rebuild the audio assets

This is optional. The repository already contains ready-to-play WAVs.

To rebuild them, install `ffmpeg` and `ffprobe`, ensure `hl1sfx.com` is reachable, and run:

```bash
/usr/bin/python3 scripts/install.py --rebuild-assets
```

The builder downloads the VOX fragments declared in `sounds/manifest.json`, normalizes them locally, prefixes each phrase with `vox/buzwarn.wav`, and overwrites the seven final files in `assets/`. Source fragments and normalized intermediate files stay ignored under `sounds/source/` and `sounds/normalized/`.

To explore other Half-Life sounds and create different phrases, browse [HL1SFX](https://hl1sfx.com/) and update `sounds/manifest.json` before rebuilding.

## Uninstall

From the cloned repository, run:

```bash
/usr/bin/python3 scripts/uninstall.py
```

Uninstall removes only hook commands owned by this project. It preserves unrelated hooks, `~/.codex/config.toml`, local configuration, and audio assets.

If the desktop app is open, quit and reopen it once so its embedded Codex process reloads the updated hook definitions.

## Additional sounds and credits

- Original sound fragments, including `vox/buzwarn.wav`, were located and downloaded through [HL1SFX](https://hl1sfx.com/), which is also the recommended catalog for finding additional Half-Life sounds.
- Half-Life, its names, and its original audio assets were created by and belong to Valve Corporation.
- The Codex hook integration and phrase arrangements in this repository were created by [viniciusczanini](https://github.com/viniciusczanini).

This is an unofficial fan project. It is not affiliated with, endorsed by, or sponsored by Valve Corporation or HL1SFX.
