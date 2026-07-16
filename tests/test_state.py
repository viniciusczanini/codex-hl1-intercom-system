import tempfile
import unittest
import json
from pathlib import Path

from codex_intercom.lifecycle import LifecycleResult
from codex_intercom.state import StateStore


class FakeLifecycle:
    def __init__(self, results=None):
        self.results = results or {}
        self.calls = []

    def inspect(self, session_id, transcript_path=None, turn_id=None):
        self.calls.append((session_id, transcript_path, turn_id))
        return self.results.get(session_id, LifecycleResult("active"))


class StateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.store = StateStore(Path(self.temp_dir.name))

    def test_single_item_finalizes_as_task_complete(self):
        first = self.store.prompt_started("s1")
        self.assertFalse(first.previous_pending)
        self.assertEqual(first.batch_count, 1)
        self.store.completion_pending("s1", "t1", "token-1")
        final = self.store.finalize("s1", "token-1")
        self.assertEqual(final.announcement, "task_complete")

    def test_next_prompt_converts_previous_completion_to_queue_item(self):
        self.store.prompt_started("s1")
        self.store.completion_pending("s1", "t1", "token-1")
        second = self.store.prompt_started("s1")
        self.assertTrue(second.previous_pending)
        self.assertEqual(second.batch_count, 2)
        self.store.completion_pending("s1", "t2", "token-2")
        final = self.store.finalize("s1", "token-2")
        self.assertEqual(final.announcement, "queue_complete")

    def test_stale_finalizer_is_cancelled(self):
        self.store.prompt_started("s1")
        self.store.completion_pending("s1", "t1", "old")
        self.store.prompt_started("s1")
        self.assertIsNone(self.store.finalize("s1", "old").announcement)

    def test_attention_closes_batch(self):
        self.store.prompt_started("s1")
        self.store.completion_pending("s1", "t1", "token-1")
        self.store.close_attention("s1")
        next_prompt = self.store.prompt_started("s1")
        self.assertFalse(next_prompt.previous_pending)
        self.assertEqual(next_prompt.batch_count, 1)

    def test_completion_waits_for_all_active_sessions(self):
        self.store.prompt_started("s1")
        self.store.prompt_started("s2")
        self.store.completion_pending("s1", "t1", "token-1")
        self.assertEqual(
            self.store.finalize("s1", "token-1").announcement,
            "queue_item_complete",
        )

        self.store.completion_pending("s2", "t2", "token-2")
        final = self.store.finalize("s2", "token-2")

        self.assertEqual(final.announcement, "queue_complete")

    def test_attention_does_not_close_an_unrelated_active_session(self):
        self.store.prompt_started("s1")
        self.store.prompt_started("s2")
        self.store.close_attention("s1")
        self.store.completion_pending("s2", "t2", "token-2")
        self.assertEqual(
            self.store.finalize("s2", "token-2").announcement,
            "task_complete",
        )

    def test_old_global_schema_loads_without_active_sessions(self):
        state_path, _ = self.store._global_paths()
        state_path.write_text(json.dumps({
            "batch_count": 1,
            "pending_token": "legacy-token",
            "pending_turn": "legacy-turn",
        }), encoding="utf-8")

        final = self.store.finalize("legacy-session", "legacy-token")

        self.assertEqual(final.announcement, "task_complete")

    def test_prompt_records_transcript_and_turn_metadata(self):
        self.store.prompt_started("s1", "/tmp/rollout-s1.jsonl", "turn-1")

        state_path, _ = self.store._global_paths()
        state = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(state["active_sessions"], {
            "s1": {
                "transcript_path": "/tmp/rollout-s1.jsonl",
                "turn_id": "turn-1",
            }
        })

    def test_fresh_active_transcript_still_blocks_completion(self):
        lifecycle = FakeLifecycle({"s2": LifecycleResult("active")})
        store = StateStore(Path(self.temp_dir.name) / "active", lifecycle=lifecycle)
        store.prompt_started("s1", "/tmp/s1.jsonl", "t1")
        store.prompt_started("s2", "/tmp/s2.jsonl", "t2")
        store.completion_pending("s1", "t1", "token-1")

        final = store.finalize("s1", "token-1")

        self.assertEqual(final.announcement, "queue_item_complete")
        self.assertEqual(final.reconciled, (("s2", "active", None),))

    def test_completed_transcript_no_longer_blocks_completion(self):
        lifecycle = FakeLifecycle({"s2": LifecycleResult("complete")})
        store = StateStore(Path(self.temp_dir.name) / "complete", lifecycle=lifecycle)
        store.prompt_started("s1", "/tmp/s1.jsonl", "t1")
        store.prompt_started("s2", "/tmp/s2.jsonl", "t2")
        store.completion_pending("s1", "t1", "token-1")

        final = store.finalize("s1", "token-1")

        self.assertEqual(final.announcement, "queue_complete")
        self.assertEqual(final.reconciled, (("s2", "complete", None),))

    def test_archived_transcript_no_longer_blocks_completion(self):
        lifecycle = FakeLifecycle({"s2": LifecycleResult("archived")})
        store = StateStore(Path(self.temp_dir.name) / "archived", lifecycle=lifecycle)
        store.prompt_started("s1", "/tmp/s1.jsonl", "t1")
        store.prompt_started("s2", "/tmp/s2.jsonl", "t2")
        store.completion_pending("s1", "t1", "token-1")

        final = store.finalize("s1", "token-1")

        self.assertEqual(final.announcement, "queue_complete")
        self.assertEqual(final.reconciled, (("s2", "archived", None),))

    def test_missing_transcript_remains_active_until_positive_completion(self):
        lifecycle = FakeLifecycle({"s2": LifecycleResult("missing")})
        store = StateStore(Path(self.temp_dir.name) / "missing", lifecycle=lifecycle)
        store.prompt_started("s1", "/tmp/s1.jsonl", "t1")
        store.prompt_started("s2")
        store.completion_pending("s1", "t1", "token-1")

        final = store.finalize("s1", "token-1")

        self.assertEqual(final.announcement, "queue_item_complete")
        self.assertEqual(final.reconciled, (("s2", "missing", None),))

    def test_unreadable_transcript_remains_conservatively_active(self):
        lifecycle = FakeLifecycle({
            "s2": LifecycleResult("unreadable", error_type="PermissionError")
        })
        store = StateStore(Path(self.temp_dir.name) / "unreadable", lifecycle=lifecycle)
        store.prompt_started("s1", "/tmp/s1.jsonl", "t1")
        store.prompt_started("s2", "/tmp/s2.jsonl", "t2")
        store.completion_pending("s1", "t1", "token-1")

        final = store.finalize("s1", "token-1")

        self.assertEqual(final.announcement, "queue_item_complete")
        self.assertEqual(
            final.reconciled,
            (("s2", "unreadable", "PermissionError"),),
        )

    def test_legacy_list_state_discovers_and_preserves_active_transcript(self):
        lifecycle = FakeLifecycle({"legacy-s2": LifecycleResult("active")})
        store = StateStore(Path(self.temp_dir.name) / "legacy", lifecycle=lifecycle)
        state_path, _ = store._global_paths()
        state_path.write_text(json.dumps({
            "active_sessions": ["legacy-s2"],
            "batch_count": 2,
            "pending_token": "token-1",
            "pending_turn": "t1",
            "pending_session": "s1",
        }), encoding="utf-8")

        final = store.finalize("s1", "token-1")

        self.assertEqual(final.announcement, "queue_item_complete")
        self.assertEqual(lifecycle.calls, [("legacy-s2", None, None)])

    def test_session_start_updates_metadata_without_creating_active_work(self):
        lifecycle = FakeLifecycle()
        store = StateStore(Path(self.temp_dir.name) / "session-start", lifecycle=lifecycle)

        store.session_started("s1", "/tmp/initial.jsonl")
        state_path, _ = store._global_paths()
        initial = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(initial["active_sessions"], {})

        store.prompt_started("s1", None, "turn-1")
        store.session_started("s1", "/tmp/resumed.jsonl")
        resumed = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(resumed["active_sessions"]["s1"], {
            "transcript_path": "/tmp/resumed.jsonl",
            "turn_id": "turn-1",
        })

    def test_session_start_silently_reconciles_legacy_state(self):
        lifecycle = FakeLifecycle({
            "active-s1": LifecycleResult("active"),
            "complete-s2": LifecycleResult("complete"),
            "missing-s3": LifecycleResult("missing"),
        })
        store = StateStore(
            Path(self.temp_dir.name) / "session-reconcile",
            lifecycle=lifecycle,
        )
        state_path, _ = store._global_paths()
        state_path.write_text(json.dumps({
            "active_sessions": ["active-s1", "complete-s2", "missing-s3"],
            "batch_count": 3,
            "pending_token": None,
            "pending_turn": None,
            "pending_session": None,
        }), encoding="utf-8")

        reconciled = store.session_started("new-session", "/tmp/new.jsonl")

        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(state["active_sessions"]),
            {"active-s1", "missing-s3"},
        )
        self.assertEqual(reconciled, (
            ("active-s1", "active", None),
            ("complete-s2", "complete", None),
            ("missing-s3", "missing", None),
        ))


if __name__ == "__main__":
    unittest.main()
