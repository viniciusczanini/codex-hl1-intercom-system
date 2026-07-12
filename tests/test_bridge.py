import io
import json
import unittest

from codex_intercom.bridge import main


class BridgeTests(unittest.TestCase):
    def test_hook_event_is_consumed_only_by_semantic_runtime(self):
        event = {
            "hook_event_name": "Stop",
            "session_id": "session-1",
            "last_assistant_message": "Finished and verified.",
        }
        raw = json.dumps(event)
        audio_inputs = []
        stdout = io.StringIO()

        def audio_main(argv, stdin, stdout):
            audio_inputs.append((argv, stdin.read()))
            stdout.write("{}\n")
            return 0

        code = main(
            argv=[],
            stdin=io.StringIO(raw),
            stdout=stdout,
            audio_main=audio_main,
        )

        self.assertEqual(code, 0)
        self.assertEqual(audio_inputs, [([], raw)])
        self.assertEqual(stdout.getvalue(), "{}\n")

    def test_internal_finalizer_is_not_forwarded(self):
        original_stdin = io.StringIO("")

        def audio_main(argv, stdin, stdout):
            self.assertIs(stdin, original_stdin)
            self.assertEqual(argv, ["--finalize", "session", "token", "4"])
            return 0

        code = main(
            argv=["--finalize", "session", "token", "4"],
            stdin=original_stdin,
            stdout=io.StringIO(),
            audio_main=audio_main,
        )

        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
