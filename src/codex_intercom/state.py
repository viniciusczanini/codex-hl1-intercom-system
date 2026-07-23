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
    reconciled: tuple = ()


class StateStore:
    def __init__(self, root, lifecycle=None):
        self.root = root
        self.lifecycle = lifecycle
        self.root.mkdir(parents=True, exist_ok=True)

    def prompt_started(self, session_id, transcript_path=None, turn_id=None):
        with self._locked_global() as state:
            previous_pending = bool(state.get("pending_token"))
            active = self._active_records(state)
            if session_id not in active:
                state["batch_count"] = int(state.get("batch_count", 0)) + 1
            previous = active.get(session_id, {})
            active[session_id] = {
                "transcript_path": (
                    str(transcript_path)
                    if transcript_path
                    else previous.get("transcript_path")
                ),
                "turn_id": turn_id or previous.get("turn_id"),
            }
            count = int(state.get("batch_count", 0))
            state.update(
                active_sessions=active,
                pending_token=None,
                pending_turn=None,
                pending_session=None,
            )
            return PromptTransition(previous_pending, count)

    def session_started(self, session_id, transcript_path=None):
        with self._locked_global() as state:
            active = self._active_records(state)
            if session_id in active and transcript_path:
                active[session_id]["transcript_path"] = str(transcript_path)
            reconciled = self._reconcile(active)
            state["active_sessions"] = active
            return reconciled

    def completion_pending(self, session_id, turn_id, token):
        with self._locked_global() as state:
            active = self._active_records(state)
            active.pop(session_id, None)
            count = max(1, int(state.get("batch_count", 0)))
            state.update(
                active_sessions=active,
                batch_count=count,
                pending_token=token,
                pending_turn=turn_id,
                pending_session=session_id,
            )

    def close_attention(self, session_id):
        with self._locked_global() as state:
            active = self._active_records(state)
            participated = session_id in active or state.get("pending_session") == session_id
            active.pop(session_id, None)
            if participated:
                state["batch_count"] = max(0, int(state.get("batch_count", 0)) - 1)
            if state.get("pending_session") == session_id:
                state.update(
                    pending_token=None,
                    pending_turn=None,
                    pending_session=None,
                )
            state["active_sessions"] = active
            if int(state.get("batch_count", 0)) == 0 and not active:
                state.clear()
                state.update(self._empty_state())

    def finalize(self, session_id, token):
        del session_id
        with self._locked_global() as state:
            if state.get("pending_token") != token:
                return FinalizeTransition(None)
            active = self._active_records(state)
            reconciled = self._reconcile(active)
            state["active_sessions"] = active
            if active:
                state.update(
                    pending_token=None,
                    pending_turn=None,
                    pending_session=None,
                )
                return FinalizeTransition(
                    "queue_item_complete",
                    tuple(reconciled),
                )
            name = (
                "queue_complete"
                if int(state.get("batch_count", 0)) > 1
                else "task_complete"
            )
            state.clear()
            state.update(self._empty_state())
            return FinalizeTransition(name, tuple(reconciled))

    def _reconcile(self, active):
        reconciled = []
        if self.lifecycle is None:
            return tuple(reconciled)
        for active_session, metadata in list(active.items()):
            result = self.lifecycle.inspect(
                active_session,
                metadata.get("transcript_path"),
                metadata.get("turn_id"),
            )
            reconciled.append((
                active_session,
                result.status,
                result.error_type,
            ))
            if result.status in ("complete", "archived"):
                del active[active_session]
            elif result.path and not metadata.get("transcript_path"):
                metadata["transcript_path"] = str(result.path)
        return tuple(reconciled)

    @staticmethod
    def _active_records(state):
        loaded = state.get("active_sessions", {})
        if isinstance(loaded, dict):
            return {
                str(session_id): (
                    dict(metadata)
                    if isinstance(metadata, dict)
                    else {"transcript_path": None, "turn_id": None}
                )
                for session_id, metadata in loaded.items()
            }
        if isinstance(loaded, list):
            return {
                str(session_id): {
                    "transcript_path": None,
                    "turn_id": None,
                }
                for session_id in loaded
            }
        return {}

    @staticmethod
    def _empty_state():
        return {
            "batch_count": 0,
            "pending_token": None,
            "pending_turn": None,
            "pending_session": None,
            "active_sessions": {},
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
