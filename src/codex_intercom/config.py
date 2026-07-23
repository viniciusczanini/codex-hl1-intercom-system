import json


ANNOUNCEMENTS = (
    "task_started",
    "permission_required",
    "response_required",
    "queue_item_complete",
    "task_complete",
    "queue_complete",
    "blocked",
)


class ConfigError(ValueError):
    """Raised when the user-editable intercom configuration is invalid."""


def load_config(path):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError("cannot read config: {0}".format(exc)) from exc

    if not isinstance(raw, dict):
        raise ConfigError("config must be an object")

    announcements = raw.get("announcements", {})
    if not isinstance(announcements, dict):
        raise ConfigError("announcements must be an object")

    merged = {}
    for name in ANNOUNCEMENTS:
        value = announcements.get(name, True)
        if not isinstance(value, bool):
            raise ConfigError("announcement '{0}' must be boolean".format(name))
        merged[name] = value

    idle = raw.get("queue_idle_seconds", 4)
    if (
        not isinstance(idle, (int, float))
        or isinstance(idle, bool)
        or idle <= 0
    ):
        raise ConfigError("queue_idle_seconds must be positive")

    alokium_enabled = raw.get("alokium_enabled", True)
    if not isinstance(alokium_enabled, bool):
        raise ConfigError("alokium_enabled must be boolean")

    mode = raw.get("mode", "normal")
    if mode not in ("normal", "chill"):
        raise ConfigError("mode must be 'normal' or 'chill'")

    return {
        "announcements": merged,
        "queue_idle_seconds": float(idle),
        "alokium_enabled": alokium_enabled,
        "mode": mode,
    }


def announcement_enabled(config, name):
    return bool(config.get("announcements", {}).get(name, True))
