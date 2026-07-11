# Codex Intercom

Black Mesa-style voice notifications for Codex on macOS. The project builds short announcements from the Half-Life 1 VOX catalog and connects them to Codex lifecycle hooks.

## Announcements

| Setting | Phrase | When it plays |
| --- | --- | --- |
| `task_started` | “Processing.” | A task or queued prompt starts |
| `permission_required` | “Attention. Security clearance required. Please acknowledge.” | Codex requests permission |
| `response_required` | “Attention. User communication required. Please acknowledge.” | Codex stops with a direct question or request |
| `queue_item_complete` | “Secondary objective secured.” | Another queued item starts after the previous one completes |
| `task_complete` | “Objective secured.” | One task finishes and no queued prompt follows |
| `queue_complete` | “Final objective secured. All systems nominal.” | A sequence of two or more queued tasks finishes |
| `subagent_complete` | “Secondary objective secured.” | A Codex subagent stops |
| `blocked` | “Warning. Objective failed. User acknowledge.” | Codex reports that it cannot continue |

## Enable or disable an announcement

Edit [`config.json`](config.json). Changes apply on the next hook event; rebuilding and reinstalling are not required.

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

Set an announcement to `false` to mute only that announcement. Missing announcement keys default to `true`. Invalid JSON fails silent and is recorded in `~/.codex/codex-intercom/intercom.log` so it cannot interrupt Codex.

## Install

Requirements:

- macOS with `/usr/bin/afplay`
- `/usr/bin/python3` 3.9 or later
- `ffmpeg` and `ffprobe` in `/opt/homebrew/bin` or on `PATH`

Build the local WAV phrases and merge the hooks into `~/.codex/hooks.json`:

```bash
cd /Users/tommy/Offline/projects/codex-intercom
/usr/bin/python3 scripts/build_sounds.py
/usr/bin/python3 scripts/install.py
```

The installer preserves unrelated hooks and does not modify `~/.codex/config.toml` or its existing `notify` command. It is idempotent, so rerunning it does not create duplicate handlers.

After installation, open `/hooks` in Codex and trust the four entries labelled **Black Mesa intercom**. Codex hashes hook definitions; changed definitions must be reviewed again.

## Queue inference

Codex hooks do not expose queue length. Intercom therefore holds a normal completion for four seconds:

- If another prompt starts in that window, the previous task is announced as a queue item.
- If nothing follows, a one-item batch gets `task_complete`.
- A batch with two or more items gets exactly one `queue_complete` announcement.
- Questions and blocked states close the batch immediately and never produce a false queue-complete sound.

Adjust `queue_idle_seconds` in `config.json` if queued prompts on your machine take longer to start.

## Test and rebuild

```bash
cd /Users/tommy/Offline/projects/codex-intercom
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 scripts/build_sounds.py
```

Generated and downloaded Half-Life audio stays local under `sounds/` and is ignored by Git. The committed [`sounds/manifest.json`](sounds/manifest.json) records each source fragment and phrase sequence.

Play all generated phrases:

```bash
for wav in sounds/generated/*.wav; do
  echo "PLAYING $wav"
  /usr/bin/afplay "$wav"
done
```

## Uninstall

```bash
cd /Users/tommy/Offline/projects/codex-intercom
/usr/bin/python3 scripts/uninstall.py
```

Uninstall removes only handlers owned by this project. It preserves unrelated Codex hooks, `config.toml`, downloaded source clips, and generated phrases.
