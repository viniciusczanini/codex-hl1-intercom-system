import hashlib
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
        with self._locked(session_id) as state:
            previous_pending = bool(state.get("pending_token"))
            count = int(state.get("batch_count", 0)) + 1
            state.update(
                batch_count=count,
                pending_token=None,
                pending_turn=None,
            )
            return PromptTransition(previous_pending, count)

    def completion_pending(self, session_id, turn_id, token):
        with self._locked(session_id) as state:
            count = max(1, int(state.get("batch_count", 0)))
            state.update(
                batch_count=count,
                pending_token=token,
                pending_turn=turn_id,
            )

    def close_attention(self, session_id):
        with self._locked(session_id) as state:
            state.clear()
            state.update(self._empty_state())

    def finalize(self, session_id, token):
        with self._locked(session_id) as state:
            if state.get("pending_token") != token:
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
        }

    def _paths(self, session_id):
        digest = hashlib.sha256((session_id or "unknown").encode("utf-8")).hexdigest()
        return self.root / (digest + ".json"), self.root / (digest + ".lock")

    @contextmanager
    def _locked(self, session_id):
        state_path, lock_path = self._paths(session_id)
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
