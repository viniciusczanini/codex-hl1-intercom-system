import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.install import EVENTS, install, merge_hooks, validate_assets
from scripts.uninstall import remove_owned_hooks, uninstall


INTERCOM_COMMAND = "/usr/bin/python3 /project/src/intercom.py"


def extract_commands(document):
    commands = []
    for groups in document.get("hooks", {}).values():
        for group in groups:
            for handler in group.get("hooks", []):
                command = handler.get("command")
                if command:
                    commands.append(command)
    return commands


class HookMergeTests(unittest.TestCase):
    def setUp(self):
        self.existing = {
            "hooks": {
                "Stop": [
                    {
                        "matcher": "",
                        "hooks": [{"type": "command", "command": "other"}],
                    }
                ]
            }
        }

    def test_merge_preserves_unrelated_hooks_and_adds_owned_events(self):
        merged = merge_hooks(self.existing, INTERCOM_COMMAND)
        commands = extract_commands(merged)
        self.assertIn("other", commands)
        self.assertEqual(commands.count(INTERCOM_COMMAND), len(EVENTS))

    def test_repeated_merge_is_idempotent(self):
        once = merge_hooks({}, INTERCOM_COMMAND)
        twice = merge_hooks(once, INTERCOM_COMMAND)
        self.assertEqual(once, twice)

    def test_uninstall_removes_only_owned_commands(self):
        installed = merge_hooks(self.existing, INTERCOM_COMMAND)
        cleaned = remove_owned_hooks(installed, INTERCOM_COMMAND)
        self.assertEqual(cleaned, self.existing)


class InstallRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.codex_home = self.root / "codex-home"
        self.codex_home.mkdir()
        self.project = self.root / "project"
        (self.project / "src").mkdir(parents=True)
        (self.project / "src" / "intercom.py").write_text("# hook\n", encoding="utf-8")
        (self.project / "sounds").mkdir()
        (self.project / "sounds" / "manifest.json").write_text(
            json.dumps(
                {
                    "fragments": {"objective": "vox/objective.wav"},
                    "phrases": {"task_complete": ["objective"]},
                }
            ),
            encoding="utf-8",
        )
        (self.project / "assets").mkdir()
        (self.project / "assets" / "task_complete.wav").write_bytes(
            b"RIFF" + b"\0" * 64
        )

    def test_validate_assets_rejects_missing_phrase(self):
        (self.project / "assets" / "task_complete.wav").unlink()
        with self.assertRaisesRegex(ValueError, "task_complete.wav"):
            validate_assets(self.project)

    @patch("scripts.install.build_all")
    def test_default_install_does_not_rebuild_assets(self, build_all):
        install(self.codex_home, self.project)
        build_all.assert_not_called()

    @patch("scripts.install.build_all")
    def test_explicit_rebuild_runs_builder(self, build_all):
        install(self.codex_home, self.project, rebuild_assets=True)
        build_all.assert_called_once_with(self.project)

    def test_install_does_not_change_config_toml(self):
        config_path = self.codex_home / "config.toml"
        original = 'notify = ["existing", "turn-ended"]\n'
        config_path.write_text(original, encoding="utf-8")
        install(self.codex_home, self.project, skip_build=True)
        self.assertEqual(config_path.read_text(encoding="utf-8"), original)

    def test_install_and_uninstall_round_trip_without_preexisting_hooks(self):
        install(self.codex_home, self.project, skip_build=True)
        installed = json.loads((self.codex_home / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(
            extract_commands(installed).count(
                "/usr/bin/python3 {0}".format(self.project / "src" / "intercom.py")
            ),
            len(EVENTS),
        )
        uninstall(self.codex_home, self.project)
        self.assertFalse((self.codex_home / "hooks.json").exists())

    def test_install_and_uninstall_preserve_preexisting_hooks(self):
        hooks_path = self.codex_home / "hooks.json"
        existing = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other"}]}]}}
        hooks_path.write_text(json.dumps(existing), encoding="utf-8")
        install(self.codex_home, self.project, skip_build=True)
        install(self.codex_home, self.project, skip_build=True)
        uninstall(self.codex_home, self.project)
        self.assertEqual(
            json.loads(hooks_path.read_text(encoding="utf-8")),
            existing,
        )

    def test_reinstall_after_project_move_replaces_old_owned_command(self):
        install(self.codex_home, self.project, skip_build=True)
        moved_project = self.root / "moved-project"
        (moved_project / "src").mkdir(parents=True)
        (moved_project / "src" / "intercom.py").write_text("# moved hook\n", encoding="utf-8")
        shutil.copytree(self.project / "sounds", moved_project / "sounds")
        shutil.copytree(self.project / "assets", moved_project / "assets")

        install(self.codex_home, moved_project, skip_build=True)

        installed = json.loads(
            (self.codex_home / "hooks.json").read_text(encoding="utf-8")
        )
        commands = extract_commands(installed)
        old_command = "/usr/bin/python3 {0}".format(self.project / "src" / "intercom.py")
        new_command = "/usr/bin/python3 {0}".format(moved_project / "src" / "intercom.py")
        self.assertNotIn(old_command, commands)
        self.assertEqual(commands.count(new_command), len(EVENTS))

    def test_reinstall_removes_obsolete_subagent_hook(self):
        command = "/usr/bin/python3 {0}".format(self.project / "src" / "intercom.py")
        hooks_path = self.codex_home / "hooks.json"
        hooks_path.write_text(json.dumps({
            "hooks": {
                "SubagentStop": [{"hooks": [{"type": "command", "command": command}]}]
            }
        }), encoding="utf-8")
        runtime = self.codex_home / "codex-intercom"
        runtime.mkdir()
        (runtime / "install.json").write_text(json.dumps({
            "command": command,
            "hooks_file_existed": True,
        }), encoding="utf-8")

        install(self.codex_home, self.project, skip_build=True)

        installed = json.loads(hooks_path.read_text(encoding="utf-8"))
        self.assertNotIn("SubagentStop", installed.get("hooks", {}))


if __name__ == "__main__":
    unittest.main()
