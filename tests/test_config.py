import json
import tempfile
import unittest
from pathlib import Path

from codex_intercom.config import (
    ANNOUNCEMENTS,
    ConfigError,
    announcement_enabled,
    load_config,
)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def write_text(self, value):
        path = self.root / "config.json"
        path.write_text(value, encoding="utf-8")
        return path

    def write_json(self, value):
        return self.write_text(json.dumps(value))

    def test_missing_keys_default_to_enabled(self):
        path = self.write_json({"announcements": {"task_started": False}})
        config = load_config(path)
        self.assertFalse(announcement_enabled(config, "task_started"))
        self.assertTrue(announcement_enabled(config, "queue_complete"))

    def test_all_expected_announcements_have_defaults(self):
        path = self.write_json({})
        config = load_config(path)
        self.assertEqual(set(config["announcements"]), set(ANNOUNCEMENTS))
        self.assertTrue(all(config["announcements"].values()))
        self.assertEqual(config["queue_idle_seconds"], 4.0)

    def test_invalid_json_raises_config_error(self):
        path = self.write_text("{")
        with self.assertRaises(ConfigError):
            load_config(path)

    def test_non_boolean_toggle_raises_config_error(self):
        path = self.write_json({"announcements": {"blocked": "yes"}})
        with self.assertRaises(ConfigError):
            load_config(path)

    def test_non_positive_queue_delay_raises_config_error(self):
        path = self.write_json({"queue_idle_seconds": 0})
        with self.assertRaises(ConfigError):
            load_config(path)

    def test_alokium_toggle_must_be_boolean(self):
        path = self.write_json({"alokium_enabled": "yes"})
        with self.assertRaises(ConfigError):
            load_config(path)


if __name__ == "__main__":
    unittest.main()
