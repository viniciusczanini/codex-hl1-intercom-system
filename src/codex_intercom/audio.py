import subprocess
from datetime import datetime, timezone


def append_log(path, message):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat()
        with path.open("a", encoding="utf-8") as log_file:
            log_file.write("{0} {1}\n".format(timestamp, message))
    except OSError:
        pass


class AudioPlayer:
    def __init__(self, sounds_dir, log_path, executable="/usr/bin/afplay"):
        self.sounds_dir = sounds_dir
        self.log_path = log_path
        self.executable = executable

    def play(self, name):
        sound_path = self.sounds_dir / (name + ".wav")
        if not sound_path.exists():
            append_log(self.log_path, "missing sound: {0}".format(sound_path))
            return False
        try:
            subprocess.Popen(
                [self.executable, str(sound_path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            append_log(self.log_path, "playback failed: {0}".format(exc))
            return False
        return True
