#!/usr/bin/env python3
import argparse
import copy
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


def project_root():
    return Path(__file__).resolve().parents[1]


def intercom_command(root):
    return "/usr/bin/python3 {0}".format(root / "src" / "intercom.py")


def remove_owned_hooks(existing, command):
    if not isinstance(existing, dict):
        raise ValueError("hooks document must be an object")
    cleaned = copy.deepcopy(existing)
    hooks = cleaned.get("hooks")
    if not isinstance(hooks, dict):
        return cleaned

    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept_groups = []
        for group in groups:
            if not isinstance(group, dict):
                kept_groups.append(group)
                continue
            new_group = copy.deepcopy(group)
            handlers = new_group.get("hooks")
            if not isinstance(handlers, list):
                kept_groups.append(new_group)
                continue
            new_handlers = [
                handler
                for handler in handlers
                if not isinstance(handler, dict) or handler.get("command") != command
            ]
            if new_handlers:
                new_group["hooks"] = new_handlers
                kept_groups.append(new_group)
        if kept_groups:
            hooks[event] = kept_groups
        else:
            del hooks[event]

    if not hooks:
        cleaned.pop("hooks", None)
    return cleaned


def _read_json(path, default):
    if not path.exists():
        return copy.deepcopy(default)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("{0} must contain a JSON object".format(path))
    return value


def _atomic_json(path, value):
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


def uninstall(codex_home, root):
    codex_home = Path(codex_home).expanduser().absolute()
    root = Path(root).expanduser().absolute()
    hooks_path = codex_home / "hooks.json"
    runtime_root = codex_home / "codex-intercom"
    record_path = runtime_root / "install.json"
    record = _read_json(record_path, {})
    command = record.get("command") or intercom_command(root)
    hooks_file_existed = bool(record.get("hooks_file_existed"))

    if hooks_path.exists():
        existing = _read_json(hooks_path, {})
        cleaned = remove_owned_hooks(existing, command)
        if not hooks_file_existed and not cleaned:
            hooks_path.unlink()
        else:
            _atomic_json(hooks_path, cleaned)

    state_path = runtime_root / "state"
    if state_path.exists():
        shutil.rmtree(state_path)
    if record_path.exists():
        record_path.unlink()
    return hooks_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Remove Codex Half-Life intercom hooks")
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    args = parser.parse_args(argv)
    try:
        uninstall(args.codex_home, project_root())
    except Exception as exc:
        print("uninstall failed: {0}".format(exc), file=sys.stderr)
        return 1
    print("Removed Codex intercom hook definitions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
