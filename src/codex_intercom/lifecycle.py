import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LifecycleResult:
    status: str
    path: object = None
    error_type: object = None


class TranscriptLifecycle:
    LIFECYCLE_EVENTS = frozenset(("task_started", "task_complete"))

    def __init__(
        self,
        sessions_root,
        max_tail_bytes=1024 * 1024,
        archived_root=None,
    ):
        self.sessions_root = Path(sessions_root)
        self.archived_root = Path(archived_root) if archived_root else None
        self.max_tail_bytes = int(max_tail_bytes)

    def inspect(self, session_id, transcript_path=None, turn_id=None):
        path, archived = self._resolve_path(session_id, transcript_path)
        if path is None:
            return LifecycleResult("missing")
        if archived:
            return LifecycleResult("archived", path=path)
        try:
            records = self._tail_records(path)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return LifecycleResult(
                "unreadable",
                path=path,
                error_type=type(exc).__name__,
            )

        latest = None
        for record in records:
            if record.get("type") != "event_msg":
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            name = payload.get("type")
            if name not in self.LIFECYCLE_EVENTS:
                continue
            if turn_id and payload.get("turn_id") != turn_id:
                continue
            latest = name

        if latest == "task_started":
            return LifecycleResult("active", path=path)
        if latest == "task_complete":
            return LifecycleResult("complete", path=path)
        return LifecycleResult("unreadable", path=path, error_type="LifecycleNotFound")

    def _resolve_path(self, session_id, transcript_path):
        if transcript_path:
            candidate = Path(transcript_path).expanduser()
            try:
                if candidate.is_file():
                    return candidate, self._is_archived(candidate)
            except OSError:
                return candidate, self._is_archived(candidate)

        pattern = "**/*{0}.jsonl".format(session_id)
        roots = [(self.sessions_root, False)]
        if self.archived_root is not None:
            roots.append((self.archived_root, True))
        try:
            candidates = [
                (path, archived)
                for root, archived in roots
                for path in root.glob(pattern)
                if path.is_file()
            ]
        except OSError:
            return None, False
        if not candidates:
            return None, False
        try:
            return max(candidates, key=lambda item: item[0].stat().st_mtime_ns)
        except OSError:
            return candidates[0]

    def _is_archived(self, path):
        if self.archived_root is None:
            return False
        try:
            path.resolve().relative_to(self.archived_root.resolve())
            return True
        except (OSError, ValueError):
            return False

    def _tail_records(self, path):
        with path.open("rb") as transcript:
            transcript.seek(0, 2)
            size = transcript.tell()
            offset = max(0, size - self.max_tail_bytes)
            transcript.seek(offset)
            data = transcript.read()
        if offset:
            newline = data.find(b"\n")
            data = b"" if newline < 0 else data[newline + 1:]
        text = data.decode("utf-8")
        return [
            json.loads(line)
            for line in text.splitlines()
            if line.strip()
        ]
