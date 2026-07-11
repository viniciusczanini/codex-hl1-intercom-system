import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from codex_intercom.audio import AudioPlayer, append_log
from codex_intercom.classifier import classify_stop
from codex_intercom.config import announcement_enabled, load_config
from codex_intercom.state import StateStore


class FinalizerScheduler:
    def __init__(self, entrypoint, python_executable="/usr/bin/python3"):
        self.entrypoint = entrypoint
        self.python_executable = python_executable

    def schedule(self, session_id, token, delay):
        subprocess.Popen(
            [
                self.python_executable,
                str(self.entrypoint),
                "--finalize",
                session_id,
                token,
                str(delay),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


class RuntimeContext:
    def __init__(self, config, state, player, scheduler, token_factory=None):
        self.config = config
        self.state = state
        self.player = player
        self.scheduler = scheduler
        self.token_factory = token_factory or (lambda: uuid.uuid4().hex)

    def play(self, name):
        if not announcement_enabled(self.config, name):
            return False
        return self.player.play(name)

    def schedule_finalize(self, session_id, turn_id):
        token = self.token_factory()
        self.state.completion_pending(session_id, turn_id, token)
        self.scheduler.schedule(
            session_id,
            token,
            self.config["queue_idle_seconds"],
        )


def handle_event(event, context):
    event_name = event.get("hook_event_name")
    session_id = event.get("session_id", "unknown")

    if event_name == "PermissionRequest":
        context.play("permission_required")
    elif event_name == "SubagentStop":
        context.play("subagent_complete")
    elif event_name == "UserPromptSubmit":
        transition = context.state.prompt_started(session_id)
        if transition.previous_pending:
            context.play("queue_item_complete")
        context.play("task_started")
    elif event_name == "Stop":
        classification = classify_stop(event.get("last_assistant_message", ""))
        if classification in ("response_required", "blocked"):
            context.state.close_attention(session_id)
            context.play(classification)
        else:
            context.schedule_finalize(session_id, event.get("turn_id", ""))
    return {}


def finalize_event(session_id, token, context):
    transition = context.state.finalize(session_id, token)
    if transition.announcement:
        context.play(transition.announcement)
    return {}


def default_project_root():
    return Path(__file__).resolve().parents[2]


def default_codex_home():
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def create_context(root=None, codex_home=None):
    root = root or default_project_root()
    codex_home = codex_home or default_codex_home()
    runtime_root = codex_home / "codex-intercom"
    log_path = runtime_root / "intercom.log"
    return RuntimeContext(
        config=load_config(root / "config.json"),
        state=StateStore(runtime_root / "state"),
        player=AudioPlayer(root / "sounds" / "generated", log_path),
        scheduler=FinalizerScheduler(root / "src" / "intercom.py"),
    )


def main(argv=None, stdin=None, stdout=None, context_factory=create_context):
    argv = list(sys.argv[1:] if argv is None else argv)
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    event_name = None
    log_path = default_codex_home() / "codex-intercom" / "intercom.log"

    try:
        if argv and argv[0] == "--finalize":
            if len(argv) != 4:
                raise ValueError("--finalize requires SESSION TOKEN DELAY")
            session_id, token, delay = argv[1], argv[2], float(argv[3])
            time.sleep(delay)
            finalize_event(session_id, token, context_factory())
            return 0

        event = json.load(stdin)
        if not isinstance(event, dict):
            raise ValueError("hook input must be an object")
        event_name = event.get("hook_event_name")
        output = handle_event(event, context_factory())
        if event_name in ("Stop", "SubagentStop"):
            json.dump(output, stdout)
            stdout.write("\n")
        return 0
    except Exception as exc:
        append_log(log_path, "hook failed: {0}".format(exc))
        if event_name in ("Stop", "SubagentStop"):
            json.dump({}, stdout)
            stdout.write("\n")
        return 0
