#!/usr/bin/env python3
import argparse
import copy
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

try:
    from scripts.build_sounds import build_all
    from scripts.uninstall import remove_owned_hooks
except ModuleNotFoundError:
    from build_sounds import build_all
    from uninstall import remove_owned_hooks


EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "PermissionRequest",
    "Stop",
)


def project_root():
    return Path(__file__).resolve().parents[1]


def intercom_command(root):
    return "/usr/bin/python3 {0}".format(root / "src" / "intercom.py")


def _handler_group(command):
    return {
        "hooks": [
            {
                "type": "command",
                "command": command,
                "timeout": 5,
                "statusMessage": "Black Mesa intercom",
            }
        ]
    }


def _event_has_command(groups, command):
    for group in groups:
        for handler in group.get("hooks", []):
            if handler.get("command") == command:
                return True
    return False


def merge_hooks(existing, command):
    if not isinstance(existing, dict):
        raise ValueError("hooks document must be an object")
    merged = copy.deepcopy(existing)
    hooks = merged.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks must be an object")
    for event in EVENTS:
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise ValueError("hook event must be a list: {0}".format(event))
        if not _event_has_command(groups, command):
            groups.append(_handler_group(command))
    return merged


def _read_json(path, default):
    if not path.exists():
        return copy.deepcopy(default)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read {0}: {1}".format(path, exc)) from exc
    if not isinstance(value, dict):
        raise ValueError("{0} must contain a JSON object".format(path))
    return value


def expected_assets(root):
    root = Path(root)
    manifest = _read_json(root / "sounds" / "manifest.json", {})
    phrases = manifest.get("phrases")
    if not isinstance(phrases, dict) or not phrases:
        raise ValueError("sound manifest must contain phrase definitions")
    return [root / "assets" / (name + ".wav") for name in sorted(phrases)]


def validate_assets(root):
    invalid = []
    for path in expected_assets(root):
        try:
            valid = path.is_file() and path.stat().st_size > 44
        except OSError:
            valid = False
        if not valid:
            invalid.append(path.name)
    if invalid:
        raise ValueError(
            "missing or invalid bundled assets: {0}".format(", ".join(invalid))
        )


def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temp_file:
            json.dump(value, temp_file, indent=2, sort_keys=True)
            temp_file.write("\n")
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def install(codex_home, root, rebuild_assets=False, skip_build=None):
    codex_home = Path(codex_home).expanduser().absolute()
    root = Path(root).expanduser().absolute()
    entrypoint = root / "src" / "intercom.py"
    if not entrypoint.exists():
        raise ValueError("hook entrypoint not found: {0}".format(entrypoint))
    if skip_build is False:
        rebuild_assets = True
    if rebuild_assets:
        build_all(root)
    validate_assets(root)

    hooks_path = codex_home / "hooks.json"
    runtime_root = codex_home / "codex-intercom"
    record_path = runtime_root / "install.json"
    existing_record = _read_json(record_path, {})
    first_install = not bool(existing_record)
    hooks_file_existed = (
        hooks_path.exists()
        if first_install
        else bool(existing_record.get("hooks_file_existed"))
    )

    command = intercom_command(root)
    existing = _read_json(hooks_path, {})
    previous_command = existing_record.get("command")
    if previous_command and previous_command != command:
        existing = remove_owned_hooks(existing, previous_command)
    existing = remove_owned_hooks(existing, command)
    merged = merge_hooks(existing, command)

    if first_install and hooks_path.exists():
        backup_path = codex_home / "hooks.json.codex-intercom.bak"
        shutil.copy2(hooks_path, backup_path)

    _atomic_json(hooks_path, merged)
    _atomic_json(
        record_path,
        {
            "command": command,
            "events": list(EVENTS),
            "hooks_file_existed": hooks_file_existed,
            "project_root": str(root),
        },
    )
    return hooks_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install Codex Half-Life intercom hooks")
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    build_group = parser.add_mutually_exclusive_group()
    build_group.add_argument("--rebuild-assets", action="store_true")
    build_group.add_argument("--skip-build", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        hooks_path = install(
            args.codex_home,
            project_root(),
            rebuild_assets=args.rebuild_assets,
        )
    except Exception as exc:
        print("install failed: {0}".format(exc), file=sys.stderr)
        return 1
    print("Installed Codex intercom hooks in {0}".format(hooks_path))
    print("Open /hooks in Codex and trust the four Black Mesa intercom definitions.")
    print("If the ChatGPT desktop app is open, quit and reopen it once to load the hooks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
