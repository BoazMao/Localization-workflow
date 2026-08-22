"""Project and media domain values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class ProjectStatus(StrEnum):
    """Current project workflow state."""

    EMPTY = "empty"
    MEDIA_READY = "media_ready"


class AudioStatus(StrEnum):
    """Derived transcription-audio processing state."""

    NOT_PREPARED = "not_prepared"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class TranscriptionStatus(StrEnum):
    """Current source-transcription state."""

    NOT_STARTED = "not_started"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class MediaInfo:
    """Normalized metadata returned by a media probe."""

    duration_ms: int
    media_type: str
    video_codec: str | None = None
    audio_codec: str | None = None
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True, slots=True)
class Project:
    """Persistent localization project snapshot."""

    id: str
    name: str
    source_language: str
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
    media_path: Path | None = None
    original_filename: str | None = None
    duration_ms: int | None = None
    media_type: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    width: int | None = None
    height: int | None = None
    audio_status: AudioStatus = AudioStatus.NOT_PREPARED
    derived_audio_path: Path | None = None
    derived_audio_duration_ms: int | None = None
    audio_error: str | None = None
    transcription_status: TranscriptionStatus = TranscriptionStatus.NOT_STARTED
    transcription_model: str | None = None
    transcription_error: str | None = None
    target_language: str | None = None


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    """Stable, timestamped source-text segment."""

    id: str
    project_id: str
    position: int
    start_ms: int
    end_ms: int
    text: str
    source_revision: int = 1


@dataclass(frozen=True, slots=True)
class GlossaryEntry:
    """Required translation for a source-language term."""

    id: str
    project_id: str
    source_term: str
    target_term: str
