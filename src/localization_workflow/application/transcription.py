"""Timestamped source-transcription workflow."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from uuid import uuid4

from localization_workflow.domain.projects import (
    AudioStatus,
    Project,
    TranscriptionStatus,
    TranscriptSegment,
)
from localization_workflow.infrastructure.database import ProjectRepository, TranscriptRepository
from localization_workflow.infrastructure.models import ManagedWhisperModels
from localization_workflow.providers.transcription import (
    ProgressCallback,
    SpeechToTextProvider,
    TranscriptionCancelled,
)


class TranscriptionService:
    """Coordinate local speech recognition and stable segment persistence."""

    def __init__(
        self,
        projects: ProjectRepository,
        transcripts: TranscriptRepository,
        provider: SpeechToTextProvider,
        models: ManagedWhisperModels,
    ) -> None:
        self._projects = projects
        self._transcripts = transcripts
        self._provider = provider
        self._models = models

    @property
    def model_name(self) -> str:
        return self._provider.model_name

    def select_model(self, source: Path) -> Path:
        selected = self._models.select(source)
        self._provider.select_model(selected)
        return selected

    def list_segments(self, project_id: str) -> list[TranscriptSegment]:
        return self._transcripts.list_for_project(project_id)

    def configure_wordbank(self, project_id: str, text: str, enabled: bool) -> Project:
        project = self._projects.get(project_id)
        if project is None:
            raise LookupError(project_id)
        updated = replace(
            project,
            whisper_wordbank=text.strip(),
            whisper_wordbank_enabled=enabled,
            updated_at=datetime.now(UTC),
        )
        self._projects.update(updated)
        return updated

    def save_edits(self, project_id: str, changes: dict[str, str]) -> list[TranscriptSegment]:
        normalized: dict[str, str] = {}
        for segment_id, text in changes.items():
            clean_text = text.strip()
            if not clean_text:
                raise ValueError("Transcript segments cannot be empty.")
            normalized[segment_id] = clean_text
        updated = self._transcripts.update_texts(project_id, normalized)
        project = self._projects.get(project_id)
        if project is None:
            raise LookupError(project_id)
        self._projects.update(replace(project, updated_at=datetime.now(UTC)))
        return updated

    def transcribe(
        self,
        project_id: str,
        progress: ProgressCallback,
        cancel: Event,
    ) -> Project:
        project = self._projects.get(project_id)
        if project is None:
            raise LookupError(project_id)
        if project.audio_status != AudioStatus.READY or project.derived_audio_path is None:
            raise ValueError("Prepare transcription audio before transcribing.")
        if project.source_language.casefold() == "auto-detect":
            raise ValueError("Choose the spoken source language before transcribing.")

        processing = replace(
            project,
            transcription_status=TranscriptionStatus.PROCESSING,
            transcription_error=None,
            updated_at=datetime.now(UTC),
        )
        self._projects.update(processing)
        try:
            provider_segments = self._provider.transcribe(
                project.derived_audio_path,
                project.source_language,
                project.whisper_wordbank if project.whisper_wordbank_enabled else None,
                progress,
                cancel,
            )
        except TranscriptionCancelled:
            cancelled = replace(
                project,
                transcription_status=TranscriptionStatus.NOT_STARTED,
                transcription_error=None,
                updated_at=datetime.now(UTC),
            )
            self._projects.update(cancelled)
            raise
        except Exception as error:
            failed = replace(
                project,
                transcription_status=TranscriptionStatus.FAILED,
                transcription_error=str(error),
                updated_at=datetime.now(UTC),
            )
            self._projects.update(failed)
            raise

        segments = [
            TranscriptSegment(
                id=str(uuid4()),
                project_id=project.id,
                position=position,
                start_ms=value.start_ms,
                end_ms=value.end_ms,
                text=value.text,
            )
            for position, value in enumerate(provider_segments)
        ]
        self._transcripts.replace(project.id, segments)
        ready = replace(
            project,
            transcription_status=TranscriptionStatus.READY,
            transcription_model=self._provider.model_name,
            transcription_error=None,
            updated_at=datetime.now(UTC),
        )
        self._projects.update(ready)
        return ready
