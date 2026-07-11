# Codex HL1 Intercom System

Black Mesa-style voice notifications for Codex on macOS. The project builds short announcements from the Half-Life 1 VOX catalog and connects them to Codex lifecycle hooks.

See the complete [installation and usage guide](INSTALLATION.md) for configuration, testing, troubleshooting, updating, and uninstalling.

## Announcements

| Setting | Phrase | When it plays |
| --- | --- | --- |
| `task_started` | “Processing.” | A task or queued prompt starts |
| `permission_required` | “Attention. Security clearance required. Please acknowledge.” | Codex requests permission |
| `response_required` | “Attention. Communication required. Please acknowledge.” | Codex stops with a direct question or request |
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
    "task_started": false,
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

The shipped configuration keeps `task_started` muted to avoid a sound on every submitted prompt. Set it to `true` if you want the “Processing” announcement.

## Install

Requirements:

- macOS with `/usr/bin/afplay`
- `/usr/bin/python3` 3.9 or later

Clone the repository and merge the hooks into `~/.codex/hooks.json`:

```bash
git clone https://github.com/viniciusczanini/codex-hl1-intercom-system.git
cd codex-hl1-intercom-system
/usr/bin/python3 scripts/install.py
```

The eight final WAV announcements are included in `assets/`, so normal installation does not require `ffmpeg`, audio downloads, or a separate build step.

The installer preserves unrelated hooks and does not modify `~/.codex/config.toml` or its existing `notify` command. It is idempotent, so rerunning it does not create duplicate handlers.

After installation, open `/hooks` in Codex and trust the four entries labelled **Black Mesa intercom**. Codex hashes hook definitions; changed definitions must be reviewed again.

If the ChatGPT desktop app was already running when the hooks were installed, quit and reopen it once. Its embedded `codex app-server` loads hook definitions when the process starts. Announcement booleans in `config.json` are read on every event and do not require another restart.

## Queue inference

Codex hooks do not expose queue length. Intercom therefore holds a normal completion for four seconds:

- If another prompt starts in that window, the previous task is announced as a queue item.
- If nothing follows, a one-item batch gets `task_complete`.
- A batch with two or more items gets exactly one `queue_complete` announcement.
- Questions and blocked states close the batch immediately and never produce a false queue-complete sound.

Adjust `queue_idle_seconds` in `config.json` if queued prompts on your machine take longer to start.

## Test

```bash
cd codex-hl1-intercom-system
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
```

The committed [`sounds/manifest.json`](sounds/manifest.json) records each source fragment and phrase sequence. Maintainers can rebuild the bundled assets with `/usr/bin/python3 scripts/install.py --rebuild-assets`; that optional path requires `ffmpeg`, `ffprobe`, and access to [HL1SFX](https://hl1sfx.com/).

Play all generated phrases:

```bash
for wav in assets/*.wav; do
  echo "PLAYING $wav"
  /usr/bin/afplay "$wav"
done
```

## Uninstall

```bash
cd codex-hl1-intercom-system
/usr/bin/python3 scripts/uninstall.py
```

Uninstall removes only handlers owned by this project. It preserves unrelated Codex hooks, `config.toml`, downloaded source clips, and generated phrases.

## Troubleshooting

Hook execution is recorded as metadata-only JSON Lines in `/tmp/codex-intercom-hooks.log`. Follow it live with:

```bash
tail -f /tmp/codex-intercom-hooks.log
```

The trace contains event, session, classification, scheduling, and playback status. It does not store prompt or assistant-message content, and macOS may remove it after a reboot.

## Sound assets

Final phrase assets are included for easy installation. Original fragments and normalized intermediate files remain local and are excluded from Git.

Original sound fragments were sourced through [HL1SFX](https://hl1sfx.com/). Half-Life and its original audio assets were created by and belong to Valve Corporation. This unofficial integration and its phrase arrangements were created by [viniciusczanini](https://github.com/viniciusczanini). The project is not affiliated with or endorsed by Valve Corporation or HL1SFX.
