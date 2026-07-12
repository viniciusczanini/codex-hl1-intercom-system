import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass

import fcntl


@dataclass(frozen=True)
class PromptTransition:
    previous_pending: bool
    batch_count: int


@dataclass(frozen=True)
class FinalizeTransition:
    announcement: object


class StateStore:
    def __init__(self, root):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def prompt_started(self, session_id):
        with self._locked_global() as state:
            previous_pending = bool(state.get("pending_token"))
            active = set(state.get("active_sessions", []))
            if session_id not in active:
                active.add(session_id)
                state["batch_count"] = int(state.get("batch_count", 0)) + 1
            count = int(state.get("batch_count", 0))
            state.update(
                active_sessions=sorted(active),
                pending_token=None,
                pending_turn=None,
                pending_session=None,
            )
            return PromptTransition(previous_pending, count)

    def completion_pending(self, session_id, turn_id, token):
        with self._locked_global() as state:
            active = set(state.get("active_sessions", []))
            active.discard(session_id)
            count = max(1, int(state.get("batch_count", 0)))
            state.update(
                active_sessions=sorted(active),
                batch_count=count,
                pending_token=token,
                pending_turn=turn_id,
                pending_session=session_id,
            )

    def close_attention(self, session_id):
        with self._locked_global() as state:
            active = set(state.get("active_sessions", []))
            participated = session_id in active or state.get("pending_session") == session_id
            active.discard(session_id)
            if participated:
                state["batch_count"] = max(0, int(state.get("batch_count", 0)) - 1)
            if state.get("pending_session") == session_id:
                state.update(
                    pending_token=None,
                    pending_turn=None,
                    pending_session=None,
                )
            state["active_sessions"] = sorted(active)
            if int(state.get("batch_count", 0)) == 0 and not active:
                state.clear()
                state.update(self._empty_state())

    def finalize(self, session_id, token):
        del session_id
        with self._locked_global() as state:
            if state.get("pending_token") != token:
                return FinalizeTransition(None)
            if state.get("active_sessions"):
                state.update(
                    pending_token=None,
                    pending_turn=None,
                    pending_session=None,
                )
                return FinalizeTransition(None)
            name = (
                "queue_complete"
                if int(state.get("batch_count", 0)) > 1
                else "task_complete"
            )
            state.clear()
            state.update(self._empty_state())
            return FinalizeTransition(name)

    @staticmethod
    def _empty_state():
        return {
            "batch_count": 0,
            "pending_token": None,
            "pending_turn": None,
            "pending_session": None,
            "active_sessions": [],
        }

    def _global_paths(self):
        return self.root / "global.json", self.root / "global.lock"

    @contextmanager
    def _locked_global(self):
        state_path, lock_path = self._global_paths()
        with self._locked_paths(state_path, lock_path) as state:
            yield state

    @contextmanager
    def _locked_paths(self, state_path, lock_path):
        lock_path.touch(exist_ok=True)
        with lock_path.open("r+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            state = self._read_state(state_path)
            try:
                yield state
            finally:
                self._write_state(state_path, state)
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_state(self, path):
        if not path.exists():
            return self._empty_state()
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._empty_state()
        if not isinstance(loaded, dict):
            return self._empty_state()
        state = self._empty_state()
        state.update(loaded)
        return state

    def _write_state(self, path, state):
        descriptor, temp_name = tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=str(self.root),
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temp_file:
                json.dump(state, temp_file, sort_keys=True)
                temp_file.write("\n")
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
