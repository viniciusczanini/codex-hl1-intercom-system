# Chill Mode and Desktop Shortcuts Design

## Goal

Add a quieter intercom mode that uses the short GTA Vice City pop-up notification sound for every enabled Codex announcement, while preserving the existing Half-Life VOX phrases as the normal mode.

Make normal/chill audio selection and Alokium LED forwarding easy to change through four Apple Shortcuts and matching double-click launchers on the macOS Desktop.

## Selected Sound

The chill sound is the 1.57-second GTA Vice City pop-up notification effect confirmed by the user. It is not the mission-complete jingle.

The normalized project asset will be stored once as:

```text
assets/chill/notification.wav
```

The project documentation will identify the source and credit Rockstar Games and Take-Two Interactive. The asset must not be presented as an original work of this project.

## Considered Approaches

### 1. Duplicate the chill sound for every announcement

Store seven identical WAV files under a chill asset directory. This would preserve the current one-filename-per-announcement lookup but wastes space and creates unnecessary files that could drift.

### 2. Select one shared chill asset at playback time (selected)

Keep the existing Half-Life announcement assets unchanged. The audio player chooses either the announcement-specific Half-Life WAV or the single shared chill WAV based on the current configuration. This keeps the mode distinction explicit and avoids duplicate audio.

### 3. Have shortcuts replace audio files

Swap or overwrite files whenever a shortcut runs. This would make mode switching destructive, complicate recovery, and make concurrent hook playback unsafe.

## Configuration

The root configuration gains a required audio mode:

```json
{
  "mode": "normal"
}
```

Accepted values are:

- `normal`: play the current Half-Life VOX WAV for the selected announcement.
- `chill`: play `assets/chill/notification.wav` for every selected announcement.

The mode is read from `config.json` for every incoming hook, so changing it does not require restarting the hook process or ChatGPT.

Existing per-announcement booleans remain authoritative in both modes. For example, `task_started: false` stays silent even in chill mode.

`alokium_enabled` remains independent of audio mode. Changing between normal and chill must not enable or disable LEDs. The user's current runtime choice of `alokium_enabled: false` is preserved.

An unknown mode is an invalid configuration. The hook logs a clear configuration error and returns safely without playing an unintended fallback sound.

## Playback Flow

For each finalized semantic announcement:

1. Load and validate the current configuration.
2. Check the announcement's existing enabled flag.
3. Resolve the asset from the current mode.
4. Play the resolved WAV through the existing serialized audio player.
5. Dispatch Alokium independently when `alokium_enabled` is true.

The event classifier, queue finalization, deduplication, and Alokium semantic mappings do not change.

## Safe Configuration Command

A small project command will expose only the supported runtime changes:

```text
set-config mode normal
set-config mode chill
set-config alokium on
set-config alokium off
```

The command validates its inputs, obtains an exclusive lock, reads the latest JSON, changes only the requested field, writes a temporary file, and atomically replaces `config.json`. It preserves announcement toggles and all unrelated configuration.

The command prints the resulting human-readable state and returns a nonzero status on failure. Tests cover field preservation, invalid input, and valid JSON output.

## Apple Shortcuts and Desktop Launchers

Four Apple Shortcuts will be created with these exact names:

- `Intercom - normal`
- `Intercom - chill`
- `Intercom - LEDs on`
- `Intercom - LEDs off`

Each shortcut runs the corresponding safe configuration command with the project's absolute local path. It must not prompt for values during normal use.

Because exported `.shortcut` files are primarily import packages rather than direct controls, the Desktop will also receive four small double-clickable launchers with the same names. Each launcher invokes its matching Apple Shortcut through the macOS `shortcuts` command. The Apple Shortcuts remain the source of truth; the launchers only provide the requested Desktop access.

No shortcut or launcher restarts ChatGPT, the Codex hook, or the Alokium service.

## Installation and Documentation

The installer will ensure the chill WAV and configuration command are available with the existing project files. Fresh installations default to:

```json
"mode": "normal"
```

Existing installations without `mode` will be migrated to `normal` so the upgrade does not silently change their sound.

The English installation documentation will describe:

- normal and chill behavior;
- direct JSON configuration;
- command-line switching;
- Apple Shortcuts and Desktop launchers;
- independent LED control;
- the GTA Vice City audio credit and ownership notice.

## Tests

Automated tests will prove:

- normal mode resolves each existing Half-Life announcement asset;
- chill mode resolves the one shared chill asset for every enabled announcement;
- disabled announcements remain silent in both modes;
- mode changes are observed by the next hook without a restart;
- invalid modes fail safely and are logged;
- the configuration command changes only its requested field;
- concurrent configuration updates cannot produce truncated or invalid JSON;
- installations without `mode` migrate to `normal`;
- Alokium forwarding is unchanged and remains independent of audio mode.

End-to-end verification will switch modes with both the command and the created Apple Shortcuts, replay representative hook events, confirm the expected sound, and verify all four Desktop launchers.

## Success Criteria

- Normal mode preserves the current Half-Life experience.
- Chill mode uses only the confirmed GTA Vice City pop-up notification sound.
- Mode changes take effect on the next hook without restarting anything.
- Existing announcement toggles continue to work.
- LEDs can be enabled or disabled independently.
- Four Apple Shortcuts exist and four matching Desktop launchers work by double-click.
- All automated and end-to-end checks pass.
