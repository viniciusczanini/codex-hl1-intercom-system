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
from codex_intercom.lifecycle import LifecycleResult
from codex_intercom.state import StateStore


ROOT = Path(__file__).resolve().parents[1]


class FakePlayer:
    def __init__(self):
        self.played = []
        self.modes = []

    def play(self, name, mode="normal"):
        self.played.append(name)
        self.modes.append(mode)
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


class FakeLifecycle:
    def __init__(self, results):
        self.results = results

    def inspect(self, session_id, transcript_path=None, turn_id=None):
        return self.results[session_id]


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.state = StateStore(Path(self.temp_dir.name) / "state")
        self.player = FakePlayer()
        self.scheduler = FakeScheduler()
        self.notifier = FakeNotifier()
        self.traces = []
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
            trace=lambda stage, **fields: self.traces.append((stage, fields)),
        )

    def event(self, name, **values):
        event = {"hook_event_name": name, "session_id": "session-1"}
        event.update(values)
        return event

    def test_permission_request_plays_permission_phrase(self):
        output = handle_event(self.event("PermissionRequest"), self.context)
        self.assertEqual(self.player.played, ["permission_required"])
        self.assertEqual(output, {})

    def test_prompt_records_transcript_and_turn_metadata(self):
        handle_event(
            self.event(
                "UserPromptSubmit",
                transcript_path="/tmp/rollout-session-1.jsonl",
                turn_id="turn-1",
            ),
            self.context,
        )

        state_path, _ = self.state._global_paths()
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["active_sessions"]["session-1"], {
            "transcript_path": "/tmp/rollout-session-1.jsonl",
            "turn_id": "turn-1",
        })

    def test_session_start_is_silent_and_only_refreshes_existing_metadata(self):
        handle_event(
            self.event(
                "SessionStart",
                transcript_path="/tmp/initial.jsonl",
                source="startup",
            ),
            self.context,
        )
        state_path, _ = self.state._global_paths()
        initial = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(initial["active_sessions"], {})

        handle_event(
            self.event("UserPromptSubmit", turn_id="turn-1"),
            self.context,
        )
        self.player.played.clear()
        self.notifier.calls.clear()
        self.scheduler.calls.clear()

        output = handle_event(
            self.event(
                "SessionStart",
                transcript_path="/tmp/resumed.jsonl",
                source="compact",
            ),
            self.context,
        )

        resumed = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(output, {})
        self.assertEqual(resumed["active_sessions"]["session-1"], {
            "transcript_path": "/tmp/resumed.jsonl",
            "turn_id": "turn-1",
        })
        self.assertEqual(self.player.played, [])
        self.assertEqual(self.notifier.calls, [])
        self.assertEqual(self.scheduler.calls, [])

    def test_session_start_traces_silent_reconciliation(self):
        lifecycle = FakeLifecycle({"legacy-session": LifecycleResult("complete")})
        state = StateStore(
            Path(self.temp_dir.name) / "session-start-reconcile",
            lifecycle=lifecycle,
        )
        state.prompt_started("legacy-session", "/tmp/legacy.jsonl", "turn-1")
        context = RuntimeContext(
            config=self.config,
            state=state,
            player=self.player,
            scheduler=self.scheduler,
            notifier=self.notifier,
            trace=lambda stage, **fields: self.traces.append((stage, fields)),
        )

        handle_event(
            self.event("SessionStart", transcript_path="/tmp/new.jsonl"),
            context,
        )

        records = [fields for stage, fields in self.traces if stage == "session_reconciled"]
        self.assertEqual(records, [{
            "session_id": "legacy-session",
            "status": "complete",
            "error_type": None,
        }])
        self.assertEqual(self.player.played, [])
        self.assertEqual(self.notifier.calls, [])

    def test_production_context_uses_bundled_assets(self):
        context = create_context(
            root=ROOT,
            codex_home=Path(self.temp_dir.name) / "codex",
        )
        self.assertEqual(context.player.sounds_dir, ROOT / "assets")

    def test_disabled_announcement_is_suppressed(self):
        self.config["announcements"]["permission_required"] = False
        self.config["mode"] = "chill"
        handle_event(self.event("PermissionRequest"), self.context)
        self.assertEqual(self.player.played, [])
        self.assertEqual(self.player.modes, [])

    def test_chill_mode_is_forwarded_only_to_audio(self):
        self.config["mode"] = "chill"

        handle_event(self.event("PermissionRequest"), self.context)

        self.assertEqual(self.player.played, ["permission_required"])
        self.assertEqual(self.player.modes, ["chill"])
        self.assertEqual(
            self.notifier.calls,
            [("permission_required", "session-1", None)],
        )

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

    def test_finalizer_traces_reconciliation_without_transcript_content(self):
        lifecycle = FakeLifecycle({"session-2": LifecycleResult("complete")})
        state = StateStore(
            Path(self.temp_dir.name) / "reconciled-state",
            lifecycle=lifecycle,
        )
        state.prompt_started("session-1", "/tmp/s1.jsonl", "turn-1")
        state.prompt_started("session-2", "/private/secret/s2.jsonl", "turn-2")
        state.completion_pending("session-1", "turn-1", "token-1")
        context = RuntimeContext(
            config=self.config,
            state=state,
            player=self.player,
            scheduler=self.scheduler,
            notifier=self.notifier,
            trace=lambda stage, **fields: self.traces.append((stage, fields)),
        )

        finalize_event("session-1", "token-1", context)

        records = [fields for stage, fields in self.traces if stage == "session_reconciled"]
        self.assertEqual(records, [{
            "session_id": "session-2",
            "status": "complete",
            "error_type": None,
        }])
        self.assertNotIn("transcript_path", records[0])

    def test_completion_waits_for_other_active_session(self):
        handle_event(self.event("UserPromptSubmit"), self.context)
        handle_event(
            self.event("UserPromptSubmit", session_id="session-2"),
            self.context,
        )
        handle_event(
            self.event("Stop", turn_id="turn-1", last_assistant_message="Done."),
            self.context,
        )
        self.player.played.clear()
        self.notifier.calls.clear()

        finalize_event("session-1", "token-1", self.context)

        self.assertEqual(self.player.played, ["queue_item_complete"])
        self.assertEqual(
            self.notifier.calls,
            [("queue_item_complete", "session-1", None)],
        )

        handle_event(
            self.event(
                "Stop",
                session_id="session-2",
                turn_id="turn-2",
                last_assistant_message="Done.",
            ),
            self.context,
        )
        finalize_event("session-2", "token-1", self.context)

        self.assertEqual(
            self.player.played,
            ["queue_item_complete", "queue_complete"],
        )
        self.assertEqual(
            self.notifier.calls,
            [
                ("queue_item_complete", "session-1", None),
                ("queue_complete", "session-2", None),
            ],
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
