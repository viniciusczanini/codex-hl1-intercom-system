#!/usr/bin/env python3
import argparse
import fcntl
import json
import os
import sys
import tempfile
from pathlib import Path


def project_root():
    return Path(__file__).resolve().parents[1]


def _replacement(setting, value):
    if setting == "mode" and value in ("normal", "chill"):
        return "mode", value
    if setting == "alokium" and value in ("on", "off"):
        return "alokium_enabled", value == "on"
    raise ValueError("expected: mode {normal|chill} or alokium {on|off}")


def _atomic_json(path, value):
    descriptor, temp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def update_config(path, setting, value):
    path = Path(path)
    key, replacement = _replacement(setting, value)
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("config must be an object")
        document[key] = replacement
        _atomic_json(path, document)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Switch Codex intercom settings",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=project_root() / "config.json",
    )
    parser.add_argument("setting", choices=("mode", "alokium"))
    parser.add_argument("value")
    args = parser.parse_args(argv)
    try:
        result = update_config(args.config, args.setting, args.value)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            "Intercom setting failed: {0}".format(exc),
            file=sys.stderr,
        )
        return 1
    if args.setting == "mode":
        print("Intercom mode: {0}".format(result["mode"]))
    else:
        print(
            "Intercom LEDs: {0}".format(
                "on" if result["alokium_enabled"] else "off"
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
