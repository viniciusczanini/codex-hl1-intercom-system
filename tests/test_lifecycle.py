import json
import tempfile
import unittest
from pathlib import Path

from codex_intercom.lifecycle import TranscriptLifecycle


def lifecycle(name, turn_id):
    return {
        "type": "event_msg",
        "payload": {"type": name, "turn_id": turn_id},
    }


class TranscriptLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.sessions = self.root / "sessions"
        self.sessions.mkdir()
        self.reader = TranscriptLifecycle(self.sessions, max_tail_bytes=512)

    def write_events(self, *events, path=None):
        path = path or self.root / "rollout.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(event) + "\n" for event in events),
            encoding="utf-8",
        )
        return path

    def test_latest_started_turn_is_active(self):
        path = self.write_events(lifecycle("task_started", "turn-1"))

        result = self.reader.inspect("session-1", path, "turn-1")

        self.assertEqual(result.status, "active")
        self.assertEqual(result.path, path)

    def test_latest_completed_turn_is_complete(self):
        path = self.write_events(
            lifecycle("task_started", "turn-1"),
            lifecycle("task_complete", "turn-1"),
        )

        result = self.reader.inspect("session-1", path, "turn-1")

        self.assertEqual(result.status, "complete")

    def test_newer_turn_does_not_change_recorded_turn_status(self):
        path = self.write_events(
            lifecycle("task_started", "turn-1"),
            lifecycle("task_complete", "turn-1"),
            lifecycle("task_started", "turn-2"),
        )

        result = self.reader.inspect("session-1", path, "turn-1")

        self.assertEqual(result.status, "complete")

    def test_missing_transcript_is_missing(self):
        result = self.reader.inspect(
            "session-1",
            self.root / "gone.jsonl",
            "turn-1",
        )

        self.assertEqual(result.status, "missing")

    def test_malformed_existing_transcript_is_unreadable(self):
        path = self.root / "broken.jsonl"
        path.write_text("{not-json}\n", encoding="utf-8")

        result = self.reader.inspect("session-1", path)

        self.assertEqual(result.status, "unreadable")
        self.assertEqual(result.error_type, "JSONDecodeError")

    def test_existing_transcript_without_lifecycle_is_unreadable(self):
        path = self.write_events({"type": "event_msg", "payload": {"type": "token_count"}})

        result = self.reader.inspect("session-1", path)

        self.assertEqual(result.status, "unreadable")

    def test_legacy_session_discovers_rollout_by_id(self):
        path = self.sessions / "2026" / "07" / "13" / (
            "rollout-2026-07-13T00-00-00-session-1.jsonl"
        )
        self.write_events(
            lifecycle("task_started", "turn-1"),
            path=path,
        )

        result = self.reader.inspect("session-1")

        self.assertEqual(result.status, "active")
        self.assertEqual(result.path, path)

    def test_reader_uses_bounded_tail_and_finds_terminal_event(self):
        path = self.root / "large.jsonl"
        prefix = "".join(
            json.dumps({"type": "event_msg", "payload": {"type": "token_count"}})
            + "\n"
            for _ in range(50)
        )
        path.write_text(
            prefix + json.dumps(lifecycle("task_complete", "turn-1")) + "\n",
            encoding="utf-8",
        )

        result = self.reader.inspect("session-1", path, "turn-1")

        self.assertEqual(result.status, "complete")


if __name__ == "__main__":
    unittest.main()
