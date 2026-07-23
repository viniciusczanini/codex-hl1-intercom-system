import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_intercom.audio import AudioPlayer


class AudioPlayerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.assets = Path(self.temp_dir.name) / "assets"
        self.assets.mkdir()
        self.player = AudioPlayer(
            self.assets,
            Path(self.temp_dir.name) / "log",
        )

    def test_normal_mode_resolves_announcement_asset(self):
        self.assertEqual(
            self.player.sound_path("task_complete", "normal"),
            self.assets / "task_complete.wav",
        )

    def test_chill_mode_resolves_shared_notification_asset(self):
        expected = self.assets / "chill" / "notification.wav"
        self.assertEqual(
            self.player.sound_path("task_complete", "chill"),
            expected,
        )
        self.assertEqual(
            self.player.sound_path("response_required", "chill"),
            expected,
        )

    @patch("codex_intercom.audio.subprocess.Popen")
    def test_play_uses_resolved_chill_asset(self, popen):
        sound = self.assets / "chill" / "notification.wav"
        sound.parent.mkdir()
        sound.write_bytes(b"RIFF" + b"\0" * 64)

        self.assertTrue(self.player.play("blocked", "chill"))

        self.assertEqual(
            popen.call_args.args[0],
            ["/usr/bin/afplay", str(sound)],
        )


if __name__ == "__main__":
    unittest.main()
