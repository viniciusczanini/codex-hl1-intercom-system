import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.set_config import update_config


ROOT = Path(__file__).resolve().parents[1]


class SetConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "config.json"
        self.original = {
            "mode": "normal",
            "announcements": {
                "task_started": False,
                "blocked": True,
            },
            "alokium_enabled": False,
            "queue_idle_seconds": 4,
        }
        self.path.write_text(json.dumps(self.original), encoding="utf-8")

    def test_mode_update_preserves_every_other_field(self):
        result = update_config(self.path, "mode", "chill")

        self.assertEqual(result["mode"], "chill")
        self.assertEqual(
            result["announcements"],
            self.original["announcements"],
        )
        self.assertFalse(result["alokium_enabled"])
        self.assertEqual(result["queue_idle_seconds"], 4)

    def test_alokium_update_preserves_mode_and_announcements(self):
        result = update_config(self.path, "alokium", "on")

        self.assertTrue(result["alokium_enabled"])
        self.assertEqual(result["mode"], "normal")
        self.assertEqual(
            result["announcements"],
            self.original["announcements"],
        )

    def test_invalid_setting_or_value_is_rejected_without_writing(self):
        before = self.path.read_bytes()

        with self.assertRaises(ValueError):
            update_config(self.path, "mode", "quiet")

        self.assertEqual(self.path.read_bytes(), before)

    def test_concurrent_cli_writers_leave_valid_complete_json(self):
        commands = [
            [
                sys.executable,
                str(ROOT / "scripts" / "set_config.py"),
                "--config",
                str(self.path),
                "mode",
                "chill",
            ],
            [
                sys.executable,
                str(ROOT / "scripts" / "set_config.py"),
                "--config",
                str(self.path),
                "alokium",
                "on",
            ],
        ]
        processes = [
            subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for command in commands
        ]

        results = [process.communicate() for process in processes]

        self.assertEqual([process.returncode for process in processes], [0, 0])
        self.assertEqual([stderr for _, stderr in results], [b"", b""])
        result = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(result["mode"], "chill")
        self.assertTrue(result["alokium_enabled"])
        self.assertEqual(
            result["announcements"],
            self.original["announcements"],
        )


if __name__ == "__main__":
    unittest.main()
