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

    def __init__(self, sessions_root, max_tail_bytes=1024 * 1024):
        self.sessions_root = Path(sessions_root)
        self.max_tail_bytes = int(max_tail_bytes)

    def inspect(self, session_id, transcript_path=None, turn_id=None):
        path = self._resolve_path(session_id, transcript_path)
        if path is None:
            return LifecycleResult("missing")
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
                    return candidate
            except OSError:
                return candidate

        pattern = "**/*{0}.jsonl".format(session_id)
        try:
            candidates = [
                path
                for path in self.sessions_root.glob(pattern)
                if path.is_file()
            ]
        except OSError:
            return None
        if not candidates:
            return None
        try:
            return max(candidates, key=lambda path: path.stat().st_mtime_ns)
        except OSError:
            return candidates[0]

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
