#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import quote


BASE_URL = "https://hl1sfx.com/download/"
PAUSES = {
    "pause_word": 0.07,
    "pause_sentence": 0.18,
}


def project_root():
    return Path(__file__).resolve().parents[1]


def source_url(hl1_path):
    return BASE_URL + quote(hl1_path, safe="")


def load_manifest(path):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest):
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be an object")
    fragments = manifest.get("fragments")
    phrases = manifest.get("phrases")
    if not isinstance(fragments, dict) or not isinstance(phrases, dict):
        raise ValueError("manifest requires fragment and phrase objects")
    for name, hl1_path in fragments.items():
        if not isinstance(name, str) or not isinstance(hl1_path, str):
            raise ValueError("fragment names and paths must be strings")
        if not hl1_path.startswith("vox/") or not hl1_path.endswith(".wav"):
            raise ValueError("fragment path must be a VOX WAV: {0}".format(hl1_path))
    for name, sequence in phrases.items():
        if not isinstance(name, str) or not isinstance(sequence, list) or not sequence:
            raise ValueError("every phrase must contain a non-empty token list")
        for token in sequence:
            if token not in fragments and token not in PAUSES:
                raise ValueError("unknown phrase token: {0}".format(token))


def _tool(preferred, fallback):
    path = Path(preferred)
    if path.exists():
        return str(path)
    found = shutil.which(fallback)
    if not found:
        raise RuntimeError("required tool not found: {0}".format(fallback))
    return found


def _download(url, destination):
    if destination.exists() and destination.stat().st_size > 44:
        return
    request = urllib.request.Request(url, headers={"User-Agent": "codex-intercom/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        status = getattr(response, "status", 200)
        content_type = response.headers.get_content_type()
        if status != 200 or not content_type.startswith("audio/"):
            raise RuntimeError(
                "invalid audio response: status={0} type={1}".format(
                    status, content_type
                )
            )
        data = response.read()
    if len(data) <= 44:
        raise RuntimeError("downloaded audio is empty: {0}".format(url))
    _atomic_bytes(destination, data)


def _atomic_bytes(destination, data):
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=destination.name + ".",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    try:
        with os.fdopen(descriptor, "wb") as temp_file:
            temp_file.write(data)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_name, destination)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _run(command, runner):
    runner(command, check=True)


def _normalize(ffmpeg, source, destination, runner):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.stem + ".tmp.wav")
    _run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            "22050",
            "-c:a",
            "pcm_s16le",
            str(temp),
        ],
        runner,
    )
    os.replace(str(temp), str(destination))


def _make_pause(ffmpeg, duration, destination, runner):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.stem + ".tmp.wav")
    _run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=22050:cl=mono",
            "-t",
            str(duration),
            "-c:a",
            "pcm_s16le",
            str(temp),
        ],
        runner,
    )
    os.replace(str(temp), str(destination))


def _expanded_sequence(sequence):
    expanded = []
    for token in sequence:
        if expanded and not expanded[-1].startswith("pause_") and not token.startswith("pause_"):
            expanded.append("pause_word")
        expanded.append(token)
    return expanded


def _concat(ffmpeg, inputs, destination, runner):
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, list_name = tempfile.mkstemp(
        prefix=destination.stem + ".",
        suffix=".concat.txt",
        dir=str(destination.parent),
        text=True,
    )
    os.close(descriptor)
    list_path = Path(list_name)
    temp = destination.with_name(destination.stem + ".tmp.wav")
    try:
        lines = []
        for input_path in inputs:
            escaped = str(input_path.resolve()).replace("'", "'\\''")
            lines.append("file '{0}'".format(escaped))
        list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-ac",
                "1",
                "-ar",
                "22050",
                "-c:a",
                "pcm_s16le",
                str(temp),
            ],
            runner,
        )
        os.replace(str(temp), str(destination))
    finally:
        list_path.unlink(missing_ok=True)
        temp.unlink(missing_ok=True)


def _probe(ffprobe, path, runner):
    result = runner(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,channels:format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    info = json.loads(result.stdout)
    streams = info.get("streams", [])
    duration = float(info.get("format", {}).get("duration", 0))
    if not streams or duration <= 0:
        raise RuntimeError("invalid generated audio: {0}".format(path))


def build_all(root=None, runner=subprocess.run):
    root = root or project_root()
    manifest = load_manifest(root / "sounds" / "manifest.json")
    ffmpeg = _tool("/opt/homebrew/bin/ffmpeg", "ffmpeg")
    ffprobe = _tool("/opt/homebrew/bin/ffprobe", "ffprobe")
    source_dir = root / "sounds" / "source"
    normalized_dir = root / "sounds" / "normalized"
    generated_dir = root / "sounds" / "generated"

    normalized = {}
    for name, hl1_path in manifest["fragments"].items():
        source = source_dir / (name + ".wav")
        destination = normalized_dir / (name + ".wav")
        _download(source_url(hl1_path), source)
        _normalize(ffmpeg, source, destination, runner)
        normalized[name] = destination

    pause_files = {}
    for name, duration in PAUSES.items():
        destination = normalized_dir / (name + ".wav")
        _make_pause(ffmpeg, duration, destination, runner)
        pause_files[name] = destination

    for name, sequence in manifest["phrases"].items():
        expanded = _expanded_sequence(sequence)
        inputs = [normalized.get(token) or pause_files[token] for token in expanded]
        destination = generated_dir / (name + ".wav")
        _concat(ffmpeg, inputs, destination, runner)
        _probe(ffprobe, destination, runner)


def main():
    try:
        build_all()
    except Exception as exc:
        print("build failed: {0}".format(exc), file=sys.stderr)
        return 1
    print("Built Half-Life intercom phrases in sounds/generated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
