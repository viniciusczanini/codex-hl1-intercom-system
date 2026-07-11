import tempfile
import unittest
from pathlib import Path

from codex_intercom.state import StateStore


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

    def test_sessions_do_not_share_state(self):
        self.store.prompt_started("s1")
        self.store.completion_pending("s1", "t1", "token-1")
        other = self.store.prompt_started("s2")
        self.assertFalse(other.previous_pending)
        self.assertEqual(other.batch_count, 1)


if __name__ == "__main__":
    unittest.main()
