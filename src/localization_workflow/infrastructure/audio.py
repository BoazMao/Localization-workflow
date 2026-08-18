"""Cancellable FFmpeg preparation of canonical transcription audio."""

from __future__ import annotations

import subprocess
import wave
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Protocol


class AudioPreparationError(RuntimeError):
    """FFmpeg or derived-audio validation failure."""


class AudioPreparationCancelled(AudioPreparationError):
    """User cancelled audio preparation."""


ProgressCallback = Callable[[int], None]


class AudioProcessorProtocol(Protocol):
    """Canonical audio-preparation boundary."""

    def prepare(
        self,
        project_id: str,
        source: Path,
        duration_ms: int,
        progress: ProgressCallback,
        cancel: Event,
        reuse_existing: bool,
    ) -> Path: ...


class FFmpegAudioProcessor:
    """Create mono 16 kHz PCM WAV files under managed derived storage."""

    def __init__(self, derived_root: Path, executable: Path) -> None:
        self._derived_root = derived_root.resolve()
        self._executable = executable.resolve()

    def prepare(
        self,
        project_id: str,
        source: Path,
        duration_ms: int,
        progress: ProgressCallback,
        cancel: Event,
        reuse_existing: bool,
    ) -> Path:
        if not self._executable.is_file():
            raise AudioPreparationError(f"Configured FFmpeg was not found: {self._executable}")
        project_dir = (self._derived_root / project_id).resolve()
        if not project_dir.is_relative_to(self._derived_root):
            raise AudioPreparationError("Invalid derived-audio destination.")
        project_dir.mkdir(parents=True, exist_ok=True)
        destination = project_dir / "transcription.wav"
        if reuse_existing and self._is_valid(destination):
            progress(100)
            return destination

        temporary = project_dir / "transcription.partial.wav"
        temporary.unlink(missing_ok=True)
        command = [
            str(self._executable),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-f",
            "wav",
            "-progress",
            "pipe:1",
            "-nostats",
            str(temporary),
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            if process.stdout is None:
                raise AudioPreparationError("FFmpeg progress stream was unavailable.")
            for raw_line in process.stdout:
                if cancel.is_set():
                    process.terminate()
                    raise AudioPreparationCancelled("Audio preparation was cancelled.")
                key, _, value = raw_line.strip().partition("=")
                if key == "out_time_ms" and duration_ms > 0:
                    processed_ms = int(value) // 1000
                    progress(min(99, round(processed_ms * 100 / duration_ms)))
            return_code = process.wait()
            if return_code != 0:
                detail = process.stderr.read().strip() if process.stderr else ""
                raise AudioPreparationError(detail or "FFmpeg could not prepare the audio.")
            if not self._is_valid(temporary):
                raise AudioPreparationError("FFmpeg produced an invalid transcription WAV file.")
            temporary.replace(destination)
            progress(100)
            return destination
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _is_valid(path: Path) -> bool:
        if not path.is_file() or path.stat().st_size <= 44:
            return False
        try:
            with wave.open(str(path), "rb") as audio:
                return (
                    audio.getnchannels() == 1
                    and audio.getframerate() == 16000
                    and audio.getsampwidth() == 2
                    and audio.getnframes() > 0
                )
        except (OSError, EOFError, wave.Error):
            return False
