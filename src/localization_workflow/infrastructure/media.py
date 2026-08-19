"""Managed media import and FFprobe metadata normalization."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from localization_workflow.domain.projects import MediaInfo

SUPPORTED_MEDIA_EXTENSIONS = frozenset(
    {
        ".mp4",
        ".mov",
        ".mkv",
        ".avi",
        ".webm",
        ".m4v",
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".flac",
        ".ogg",
    }
)


class MediaError(RuntimeError):
    """Actionable media import or inspection error."""


class MediaProbeProtocol(Protocol):
    """Metadata probe boundary used by the import service."""

    def probe(self, path: Path) -> MediaInfo: ...


Runner = Callable[..., subprocess.CompletedProcess[str]]


class FFprobeMediaProbe:
    """Inspect media using one FFprobe subprocess boundary."""

    def __init__(self, executable: Path | None = None, runner: Runner = subprocess.run) -> None:
        self._executable = executable
        self._runner = runner

    def probe(self, path: Path) -> MediaInfo:
        executable = self._resolve_executable()
        command: Sequence[str] = (
            str(executable),
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        )
        try:
            result = self._runner(
                command,
                capture_output=True,
                text=True,
                check=False,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as error:
            raise MediaError(f"FFprobe could not start: {error}") from error
        if result.returncode != 0:
            detail = result.stderr.strip() or "The file could not be inspected."
            raise MediaError(detail)
        try:
            payload = json.loads(result.stdout)
            return self._normalize(payload)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise MediaError("FFprobe returned invalid metadata.") from error

    def _resolve_executable(self) -> Path:
        if self._executable:
            if self._executable.is_file():
                return self._executable
            raise MediaError(f"Configured FFprobe executable was not found: {self._executable}")
        discovered = shutil.which("ffprobe")
        if not discovered:
            raise MediaError("FFprobe was not found. Configure FFPROBE_PATH or add it to PATH.")
        return Path(discovered)

    @staticmethod
    def _normalize(payload: dict[str, object]) -> MediaInfo:
        raw_streams = payload.get("streams", [])
        streams = raw_streams if isinstance(raw_streams, list) else []
        video = next(
            (
                item
                for item in streams
                if isinstance(item, dict) and item.get("codec_type") == "video"
            ),
            None,
        )
        audio = next(
            (
                item
                for item in streams
                if isinstance(item, dict) and item.get("codec_type") == "audio"
            ),
            None,
        )
        if not video and not audio:
            raise MediaError("The selected file has no supported audio or video stream.")
        raw_format = payload.get("format", {})
        media_format = raw_format if isinstance(raw_format, dict) else {}
        duration_seconds = float(media_format.get("duration", 0) or 0)
        return MediaInfo(
            duration_ms=max(0, round(duration_seconds * 1000)),
            media_type="video" if video else "audio",
            video_codec=str(video.get("codec_name")) if video and video.get("codec_name") else None,
            audio_codec=str(audio.get("codec_name")) if audio and audio.get("codec_name") else None,
            width=int(video["width"]) if video and video.get("width") else None,
            height=int(video["height"]) if video and video.get("height") else None,
        )


class ManagedMediaStore:
    """Copy user-selected files into application-owned project storage."""

    def __init__(self, media_root: Path, probe: MediaProbeProtocol) -> None:
        self._media_root = media_root.resolve()
        self._probe = probe

    def import_file(self, project_id: str, source: Path) -> tuple[Path, MediaInfo]:
        source = source.resolve()
        if not source.is_file():
            raise MediaError("The selected media file does not exist.")
        if source.suffix.lower() not in SUPPORTED_MEDIA_EXTENSIONS:
            raise MediaError(f"Unsupported media type: {source.suffix or 'no extension'}")
        project_dir = (self._media_root / project_id).resolve()
        if not project_dir.is_relative_to(self._media_root):
            raise MediaError("Invalid managed-media destination.")
        project_dir.mkdir(parents=True, exist_ok=True)
        destination = project_dir / f"{uuid4().hex}{source.suffix.lower()}"
        try:
            shutil.copy2(source, destination)
            info = self._probe.probe(destination)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return destination, info

    def delete_project_media(self, project_id: str) -> None:
        project_dir = (self._media_root / project_id).resolve()
        if project_dir == self._media_root or not project_dir.is_relative_to(self._media_root):
            raise MediaError("Refusing to remove an unsafe media path.")
        if project_dir.exists():
            shutil.rmtree(project_dir)
