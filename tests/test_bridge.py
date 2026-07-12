import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from codex_intercom.bridge import forward_to_alokium, main


class BridgeTests(unittest.TestCase):
    def test_forwarder_starts_adapter_with_payload_on_stdin(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = Path(directory) / "intercom.py"
            adapter.write_text("# adapter\n", encoding="utf-8")
            calls = []

            class InputPipe:
                def write(self, value):
                    calls.append(("write", value))

                def close(self):
                    calls.append(("close", None))

            class Process:
                stdin = InputPipe()

            def popen(*args, **kwargs):
                calls.append((args, kwargs))
                return Process()

            result = forward_to_alokium(
                '{"hook_event_name":"Stop"}',
                adapter_path=adapter,
                popen=popen,
            )

        self.assertTrue(result)
        args, kwargs = calls[0]
        self.assertEqual(args[0], ["/usr/bin/python3", str(adapter)])
        self.assertIs(kwargs["stdin"], subprocess.PIPE)
        self.assertIs(kwargs["stdout"], subprocess.DEVNULL)
        self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
        self.assertTrue(kwargs["start_new_session"])
        self.assertEqual(calls[1], ("write", b'{"hook_event_name":"Stop"}'))
        self.assertEqual(calls[2], ("close", None))

    def test_hook_event_is_forwarded_and_audio_receives_the_same_payload(self):
        event = {
            "hook_event_name": "Stop",
            "session_id": "session-1",
            "last_assistant_message": "Finished and verified.",
        }
        raw = json.dumps(event)
        forwarded = []
        audio_inputs = []
        stdout = io.StringIO()

        def forward(payload):
            forwarded.append(payload)
            return True

        def audio_main(argv, stdin, stdout):
            audio_inputs.append((argv, stdin.read()))
            stdout.write("{}\n")
            return 0

        code = main(
            argv=[],
            stdin=io.StringIO(raw),
            stdout=stdout,
            audio_main=audio_main,
            forward=forward,
        )

        self.assertEqual(code, 0)
        self.assertEqual(forwarded, [raw])
        self.assertEqual(audio_inputs, [([], raw)])
        self.assertEqual(stdout.getvalue(), "{}\n")

    def test_internal_finalizer_is_not_forwarded(self):
        forwarded = []
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
            forward=lambda payload: forwarded.append(payload),
        )

        self.assertEqual(code, 0)
        self.assertEqual(forwarded, [])

    def test_forward_failure_does_not_break_audio(self):
        calls = []

        def audio_main(argv, stdin, stdout):
            calls.append(json.load(stdin)["hook_event_name"])
            return 0

        code = main(
            argv=[],
            stdin=io.StringIO('{"hook_event_name":"PermissionRequest"}'),
            stdout=io.StringIO(),
            audio_main=audio_main,
            forward=lambda payload: (_ for _ in ()).throw(OSError("adapter unavailable")),
        )

        self.assertEqual(code, 0)
        self.assertEqual(calls, ["PermissionRequest"])


if __name__ == "__main__":
    unittest.main()
