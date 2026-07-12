import json
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_intercom.runtime import (
    RuntimeContext,
    create_context,
    finalize_event,
    handle_event,
    main,
    trace_event,
)
from codex_intercom.state import StateStore


ROOT = Path(__file__).resolve().parents[1]


class FakePlayer:
    def __init__(self):
        self.played = []

    def play(self, name):
        self.played.append(name)
        return True


class FakeScheduler:
    def __init__(self):
        self.calls = []

    def schedule(self, session_id, token, delay):
        self.calls.append((session_id, token, delay))


class FakeNotifier:
    def __init__(self, result=True):
        self.calls = []
        self.result = result

    def notify(self, announcement, session_id=None, turn_id=None):
        self.calls.append((announcement, session_id, turn_id))
        return self.result


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.state = StateStore(Path(self.temp_dir.name) / "state")
        self.player = FakePlayer()
        self.scheduler = FakeScheduler()
        self.notifier = FakeNotifier()
        self.config = {
            "announcements": {
                "task_started": True,
                "permission_required": True,
                "response_required": True,
                "queue_item_complete": True,
                "task_complete": True,
                "queue_complete": True,
                "subagent_complete": True,
                "blocked": True,
            },
            "queue_idle_seconds": 4.0,
        }
        self.context = RuntimeContext(
            config=self.config,
            state=self.state,
            player=self.player,
            scheduler=self.scheduler,
            notifier=self.notifier,
            token_factory=lambda: "token-1",
        )

    def event(self, name, **values):
        event = {"hook_event_name": name, "session_id": "session-1"}
        event.update(values)
        return event

    def test_permission_request_plays_permission_phrase(self):
        output = handle_event(self.event("PermissionRequest"), self.context)
        self.assertEqual(self.player.played, ["permission_required"])
        self.assertEqual(output, {})

    def test_production_context_uses_bundled_assets(self):
        context = create_context(
            root=ROOT,
            codex_home=Path(self.temp_dir.name) / "codex",
        )
        self.assertEqual(context.player.sounds_dir, ROOT / "assets")

    def test_disabled_announcement_is_suppressed(self):
        self.config["announcements"]["permission_required"] = False
        handle_event(self.event("PermissionRequest"), self.context)
        self.assertEqual(self.player.played, [])

    def test_subagent_stop_is_silent_in_both_destinations(self):
        output = handle_event(self.event("SubagentStop"), self.context)
        self.assertEqual(self.player.played, [])
        self.assertEqual(self.notifier.calls, [])
        self.assertEqual(self.scheduler.calls, [])
        self.assertEqual(output, {})

    def test_prompt_after_pending_stop_marks_previous_queue_item(self):
        handle_event(self.event("UserPromptSubmit"), self.context)
        handle_event(
            self.event("Stop", turn_id="turn-1", last_assistant_message="Done."),
            self.context,
        )
        handle_event(self.event("UserPromptSubmit"), self.context)
        self.assertEqual(
            self.player.played,
            ["task_started", "queue_item_complete", "task_started"],
        )

    def test_stop_schedules_finalizer_without_completion_sound(self):
        handle_event(self.event("UserPromptSubmit"), self.context)
        self.player.played.clear()
        output = handle_event(
            self.event("Stop", turn_id="turn-1", last_assistant_message="Finished."),
            self.context,
        )
        self.assertEqual(output, {})
        self.assertEqual(self.player.played, [])
        self.assertEqual(self.scheduler.calls, [("session-1", "token-1", 4.0)])
        self.assertEqual(self.notifier.calls, [])

    def test_waiting_for_user_plays_immediately_and_closes_batch(self):
        handle_event(self.event("UserPromptSubmit"), self.context)
        self.player.played.clear()
        output = handle_event(
            self.event("Stop", last_assistant_message="Qual opção você prefere?"),
            self.context,
        )
        self.assertEqual(output, {})
        self.assertEqual(self.player.played, ["response_required"])
        self.assertEqual(
            self.notifier.calls[-1],
            ("response_required", "session-1", None),
        )
        self.assertFalse(self.state.prompt_started("session-1").previous_pending)

    def test_blocked_stop_plays_blocked_phrase(self):
        handle_event(
            self.event("Stop", last_assistant_message="I cannot continue without access."),
            self.context,
        )
        self.assertEqual(self.player.played, ["blocked"])
        self.assertEqual(
            self.notifier.calls,
            [("blocked", "session-1", None)],
        )

    def test_finalizer_plays_state_selected_announcement(self):
        handle_event(self.event("UserPromptSubmit"), self.context)
        handle_event(
            self.event("Stop", turn_id="turn-1", last_assistant_message="Done."),
            self.context,
        )
        self.player.played.clear()
        output = finalize_event("session-1", "token-1", self.context)
        self.assertEqual(output, {})
        self.assertEqual(self.player.played, ["task_complete"])
        self.assertEqual(
            self.notifier.calls[-1],
            ("task_complete", "session-1", None),
        )

    def test_disabled_audio_does_not_disable_alokium(self):
        self.config["announcements"]["permission_required"] = False
        handle_event(self.event("PermissionRequest"), self.context)
        self.assertEqual(self.player.played, [])
        self.assertEqual(
            self.notifier.calls,
            [("permission_required", "session-1", None)],
        )

    def test_stop_cli_emits_json_when_context_creation_fails(self):
        stdout = io.StringIO()
        log_path = Path(self.temp_dir.name) / "codex" / "codex-intercom" / "intercom.log"

        def failing_context():
            raise RuntimeError("bad config")

        payload = json.dumps(self.event("Stop", last_assistant_message="Done."))
        with patch("codex_intercom.runtime.default_codex_home", return_value=log_path.parents[1]):
            exit_code = main(
                argv=[],
                stdin=io.StringIO(payload),
                stdout=stdout,
                context_factory=failing_context,
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), {})
        self.assertIn("bad config", log_path.read_text(encoding="utf-8"))

    def test_trace_event_writes_structured_jsonl_without_message_content(self):
        trace_path = Path(self.temp_dir.name) / "hook-trace.jsonl"
        with patch.dict(
            os.environ,
            {"CODEX_INTERCOM_TRACE_PATH": str(trace_path)},
        ):
            trace_event(
                "hook_received",
                event="Stop",
                session_id="session-1",
                turn_id="turn-1",
            )

        record = json.loads(trace_path.read_text(encoding="utf-8"))
        self.assertEqual(record["stage"], "hook_received")
        self.assertEqual(record["event"], "Stop")
        self.assertEqual(record["session_id"], "session-1")
        self.assertEqual(record["turn_id"], "turn-1")
        self.assertIn("timestamp", record)
        self.assertNotIn("last_assistant_message", record)


if __name__ == "__main__":
    unittest.main()
