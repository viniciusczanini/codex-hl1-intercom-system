import io
import os
import subprocess
import sys
from pathlib import Path

from codex_intercom.runtime import main as audio_main_default
from codex_intercom.runtime import trace_event


def default_adapter_path():
    configured = os.environ.get("CODEX_ALOKIUM_ADAPTER")
    if configured:
        return Path(configured).expanduser()
    projects_root = Path(__file__).resolve().parents[3]
    return projects_root / "codex_alokium_intercom" / "src" / "intercom.py"


def forward_to_alokium(raw_event, adapter_path=None, popen=subprocess.Popen):
    adapter = Path(adapter_path) if adapter_path else default_adapter_path()
    if not adapter.is_file():
        trace_event("alokium_bridge_skipped", reason="adapter_missing")
        return False
    try:
        process = popen(
            ["/usr/bin/python3", str(adapter)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        process.stdin.write(raw_event.encode("utf-8"))
        process.stdin.close()
        trace_event("alokium_bridge_forwarded")
        return True
    except (OSError, BrokenPipeError, AttributeError) as error:
        trace_event("alokium_bridge_failed", error_type=type(error).__name__)
        return False


def main(
    argv=None,
    stdin=None,
    stdout=None,
    audio_main=audio_main_default,
    forward=forward_to_alokium,
):
    argv = list(sys.argv[1:] if argv is None else argv)
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout

    if argv and argv[0] == "--finalize":
        return audio_main(argv, stdin, stdout)

    raw_event = stdin.read()
    try:
        forward(raw_event)
    except Exception as error:
        trace_event("alokium_bridge_failed", error_type=type(error).__name__)
    return audio_main(argv, io.StringIO(raw_event), stdout)
