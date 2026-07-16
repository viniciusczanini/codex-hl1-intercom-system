import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import fcntl

from codex_intercom.audio import AudioPlayer, append_log
from codex_intercom.classifier import classify_stop
from codex_intercom.config import announcement_enabled, load_config
from codex_intercom.lifecycle import TranscriptLifecycle
from codex_intercom.state import StateStore


def trace_event(stage, **fields):
    configured = os.environ.get("CODEX_INTERCOM_TRACE_PATH")
    path = Path(configured) if configured else Path("/tmp/codex-intercom-hooks.log")
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "stage": stage,
    }
    record.update(fields)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as trace_file:
            fcntl.flock(trace_file.fileno(), fcntl.LOCK_EX)
            json.dump(record, trace_file, sort_keys=True, separators=(",", ":"))
            trace_file.write("\n")
            trace_file.flush()
            fcntl.flock(trace_file.fileno(), fcntl.LOCK_UN)
    except (OSError, TypeError, ValueError):
        pass


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


class SemanticNotifier:
    ANNOUNCEMENTS = frozenset((
        "permission_required",
        "response_required",
        "blocked",
        "queue_item_complete",
        "task_complete",
        "queue_complete",
    ))

    def __init__(self, adapter=None, runner=subprocess.run):
        self.adapter = adapter or self.default_adapter_path()
        self.runner = runner

    @staticmethod
    def default_adapter_path():
        configured = os.environ.get("CODEX_ALOKIUM_ADAPTER")
        if configured:
            return Path(configured).expanduser()
        projects_root = Path(__file__).resolve().parents[3]
        return projects_root / "codex_alokium_intercom" / "src" / "intercom.py"

    def notify(self, announcement, session_id=None, turn_id=None):
        if announcement not in self.ANNOUNCEMENTS or not self.adapter.is_file():
            return False
        payload = {
            "announcement": announcement,
            "session_id": session_id,
            "turn_id": turn_id,
        }
        try:
            self.runner(
                ["/usr/bin/python3", str(self.adapter)],
                input=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
                start_new_session=True,
            )
            return True
        except (OSError, subprocess.SubprocessError):
            return False


class RuntimeContext:
    def __init__(
        self,
        config,
        state,
        player,
        scheduler,
        notifier=None,
        token_factory=None,
        trace=None,
    ):
        self.config = config
        self.state = state
        self.player = player
        self.scheduler = scheduler
        self.notifier = notifier
        self.token_factory = token_factory or (lambda: uuid.uuid4().hex)
        self.trace = trace or (lambda stage, **fields: None)

    def play(self, name):
        if not announcement_enabled(self.config, name):
            self.trace("play_suppressed", announcement=name)
            return False
        started = self.player.play(name)
        self.trace("play_attempted", announcement=name, started=bool(started))
        return started

    def dispatch(self, name, session_id=None, turn_id=None):
        audio_started = self.play(name)
        notified = False
        if (
            self.notifier is not None
            and self.config.get("alokium_enabled", True)
            and name in SemanticNotifier.ANNOUNCEMENTS
        ):
            notified = self.notifier.notify(name, session_id, turn_id)
        self.trace(
            "announcement_dispatched",
            announcement=name,
            session_id=session_id,
            turn_id=turn_id,
            audio_started=bool(audio_started),
            alokium_started=bool(notified),
        )
        return audio_started or notified

    def schedule_finalize(self, session_id, turn_id):
        token = self.token_factory()
        self.state.completion_pending(session_id, turn_id, token)
        self.scheduler.schedule(
            session_id,
            token,
            self.config["queue_idle_seconds"],
        )
        self.trace(
            "finalizer_scheduled",
            session_id=session_id,
            turn_id=turn_id,
            token=token,
            delay=self.config["queue_idle_seconds"],
        )


def handle_event(event, context):
    event_name = event.get("hook_event_name")
    session_id = event.get("session_id", "unknown")

    if event_name == "PermissionRequest":
        context.dispatch(
            "permission_required",
            session_id,
            event.get("turn_id"),
        )
    elif event_name == "SubagentStop":
        context.trace("subagent_stop_ignored", session_id=session_id)
    elif event_name == "SessionStart":
        reconciled = context.state.session_started(
            session_id,
            event.get("transcript_path"),
        )
        for reconciled_session, status, error_type in reconciled:
            context.trace(
                "session_reconciled",
                session_id=reconciled_session,
                status=status,
                error_type=error_type,
            )
        context.trace(
            "session_state_refreshed",
            session_id=session_id,
            source=event.get("source"),
        )
    elif event_name == "UserPromptSubmit":
        transition = context.state.prompt_started(
            session_id,
            event.get("transcript_path"),
            event.get("turn_id"),
        )
        context.trace(
            "prompt_state_updated",
            session_id=session_id,
            batch_count=transition.batch_count,
            previous_pending=transition.previous_pending,
        )
        if transition.previous_pending:
            context.dispatch("queue_item_complete", session_id)
        context.dispatch("task_started", session_id)
    elif event_name == "Stop":
        classification = classify_stop(event.get("last_assistant_message", ""))
        context.trace(
            "stop_classified",
            session_id=session_id,
            turn_id=event.get("turn_id", ""),
            classification=classification,
        )
        if classification in ("response_required", "blocked"):
            context.state.close_attention(session_id)
            context.dispatch(classification, session_id, event.get("turn_id"))
        else:
            context.schedule_finalize(session_id, event.get("turn_id", ""))
    return {}


def finalize_event(session_id, token, context):
    transition = context.state.finalize(session_id, token)
    for reconciled_session, status, error_type in transition.reconciled:
        context.trace(
            "session_reconciled",
            session_id=reconciled_session,
            status=status,
            error_type=error_type,
        )
    context.trace(
        "finalizer_decision",
        session_id=session_id,
        token=token,
        announcement=transition.announcement,
    )
    if transition.announcement:
        context.dispatch(transition.announcement, session_id)
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
    lifecycle = TranscriptLifecycle(
        codex_home / "sessions",
        archived_root=codex_home / "archived_sessions",
    )
    return RuntimeContext(
        config=load_config(root / "config.json"),
        state=StateStore(runtime_root / "state", lifecycle=lifecycle),
        player=AudioPlayer(root / "assets", log_path),
        scheduler=FinalizerScheduler(root / "src" / "intercom.py"),
        notifier=SemanticNotifier(),
        trace=trace_event,
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
            trace_event(
                "finalizer_worker_started",
                session_id=session_id,
                token=token,
                delay=delay,
            )
            time.sleep(delay)
            finalize_event(session_id, token, context_factory())
            trace_event(
                "finalizer_worker_finished",
                session_id=session_id,
                token=token,
            )
            return 0

        event = json.load(stdin)
        if not isinstance(event, dict):
            raise ValueError("hook input must be an object")
        event_name = event.get("hook_event_name")
        trace_event(
            "hook_received",
            event=event_name,
            session_id=event.get("session_id"),
            turn_id=event.get("turn_id"),
        )
        output = handle_event(event, context_factory())
        trace_event(
            "hook_handled",
            event=event_name,
            session_id=event.get("session_id"),
            turn_id=event.get("turn_id"),
        )
        if event_name in ("Stop", "SubagentStop"):
            json.dump(output, stdout)
            stdout.write("\n")
        return 0
    except Exception as exc:
        trace_event(
            "hook_failed",
            event=event_name,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        append_log(log_path, "hook failed: {0}".format(exc))
        if event_name in ("Stop", "SubagentStop"):
            json.dump({}, stdout)
            stdout.write("\n")
        return 0
