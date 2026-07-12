import io
import sys

from codex_intercom.runtime import main as audio_main_default


def main(
    argv=None,
    stdin=None,
    stdout=None,
    audio_main=audio_main_default,
):
    argv = list(sys.argv[1:] if argv is None else argv)
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout

    if argv and argv[0] == "--finalize":
        return audio_main(argv, stdin, stdout)

    raw_event = stdin.read()
    return audio_main(argv, io.StringIO(raw_event), stdout)
