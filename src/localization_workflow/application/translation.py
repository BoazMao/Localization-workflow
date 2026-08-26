"""Segment translation workflow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

from localization_workflow.application.glossary import GlossaryService
from localization_workflow.domain.projects import (
    Project,
    SegmentTranslation,
    TranscriptSegment,
    TranslationStatus,
)
from localization_workflow.infrastructure.database import (
    ProjectRepository,
    TranscriptRepository,
    TranslationRepository,
)
from localization_workflow.infrastructure.instructions import TranslationInstructionsStore
from localization_workflow.providers.translation import (
    OpenAITranslationProvider,
    TranslationProvider,
    TranslationRequest,
)


class TranslationCancelled(RuntimeError):
    """User cancelled a translation batch."""


@dataclass(frozen=True, slots=True)
class ExportReadiness:
    """Review-state summary used to make an informed export choice."""

    total: int
    approved: int
    reviewed: int
    draft: int
    outdated: int
    failed: int
    missing: int

    @property
    def approved_only_count(self) -> int:
        return self.approved

    @property
    def usable_count(self) -> int:
        return self.approved + self.reviewed + self.draft

    @property
    def omitted_count(self) -> int:
        return self.outdated + self.failed + self.missing


class TranslationService:
    """Translate source segments with instructions and matching glossary constraints."""

    def __init__(
        self,
        projects: ProjectRepository,
        transcripts: TranscriptRepository,
        translations: TranslationRepository,
        glossary: GlossaryService,
        provider: TranslationProvider,
        instructions: TranslationInstructionsStore,
    ) -> None:
        self._projects = projects
        self._transcripts = transcripts
        self._translations = translations
        self._glossary = glossary
        self._provider = provider
        self._instructions = instructions

    @property
    def provider_label(self) -> str:
        return f"{self._provider.name} · {self._provider.model}"

    def read_instructions(self) -> str:
        return self._instructions.read()

    def save_instructions(self, text: str) -> None:
        self._instructions.save(text)

    def configure_openai(self, api_key: str, model: str, base_url: str = "") -> None:
        if not isinstance(self._provider, OpenAITranslationProvider):
            raise RuntimeError("The active model does not support editable API settings.")
        self._provider.configure(api_key, model, base_url)

    def list_translations(self, project_id: str) -> list[SegmentTranslation]:
        revisions = {
            segment.id: segment.source_revision
            for segment in self._transcripts.list_for_project(project_id)
        }
        values = self._translations.list_for_project(project_id)
        return [
            replace(value, status=TranslationStatus.OUTDATED)
            if value.status != TranslationStatus.FAILED
            and revisions.get(value.segment_id) != value.source_revision
            else value
            for value in values
        ]

    def save_edits(self, project_id: str, changes: dict[str, str]) -> list[SegmentTranslation]:
        """Save human translation edits as drafts for the current source revision."""
        segments = {
            segment.id: segment for segment in self._transcripts.list_for_project(project_id)
        }
        translations = {
            value.segment_id: value for value in self._translations.list_for_project(project_id)
        }
        for segment_id, text in changes.items():
            segment = segments.get(segment_id)
            current = translations.get(segment_id)
            clean_text = text.strip()
            if segment is None or current is None:
                raise LookupError("One or more translations no longer exist.")
            if not clean_text:
                raise ValueError("Translation text cannot be empty.")
            self._translations.upsert(
                replace(
                    current,
                    text=clean_text,
                    source_revision=segment.source_revision,
                    status=TranslationStatus.DRAFT,
                    error=None,
                    updated_at=datetime.now(UTC),
                )
            )
        return self.list_translations(project_id)

    def set_review_status(
        self,
        project_id: str,
        segment_ids: set[str],
        status: TranslationStatus,
    ) -> list[SegmentTranslation]:
        """Mark current translations reviewed or approved."""
        if status not in {TranslationStatus.REVIEWED, TranslationStatus.APPROVED}:
            raise ValueError("Translations can only be marked reviewed or approved.")
        if not segment_ids:
            raise ValueError("Select one or more translations first.")
        visible = {value.segment_id: value for value in self.list_translations(project_id)}
        stored = {
            value.segment_id: value for value in self._translations.list_for_project(project_id)
        }
        for segment_id in segment_ids:
            value = visible.get(segment_id)
            if value is None:
                raise LookupError("One or more translations no longer exist.")
            if value.status in {TranslationStatus.FAILED, TranslationStatus.OUTDATED}:
                raise ValueError("Failed or outdated translations cannot be reviewed or approved.")
            if not value.text:
                raise ValueError("Empty translations cannot be reviewed or approved.")
        now = datetime.now(UTC)
        for segment_id in segment_ids:
            self._translations.upsert(replace(stored[segment_id], status=status, updated_at=now))
        return self.list_translations(project_id)

    def export_readiness(self, project_id: str) -> ExportReadiness:
        segments = self._transcripts.list_for_project(project_id)
        translations = {value.segment_id: value for value in self.list_translations(project_id)}
        counts = {status: 0 for status in TranslationStatus}
        missing = 0
        for segment in segments:
            value = translations.get(segment.id)
            if value is None:
                missing += 1
            else:
                counts[value.status] += 1
        return ExportReadiness(
            total=len(segments),
            approved=counts[TranslationStatus.APPROVED],
            reviewed=counts[TranslationStatus.REVIEWED],
            draft=counts[TranslationStatus.DRAFT],
            outdated=counts[TranslationStatus.OUTDATED],
            failed=counts[TranslationStatus.FAILED],
            missing=missing,
        )

    def export_srt(
        self,
        project_id: str,
        destination: Path,
        *,
        include_unapproved: bool = False,
    ) -> int:
        """Write a validated UTF-8 BOM SubRip file without partial output."""
        if destination.suffix.casefold() != ".srt":
            raise ValueError("The subtitle output filename must end with .srt.")
        if not destination.parent.is_dir():
            raise ValueError("The selected subtitle output folder does not exist.")
        segments = self._transcripts.list_for_project(project_id)
        eligible_statuses = {TranslationStatus.APPROVED}
        if include_unapproved:
            eligible_statuses.update({TranslationStatus.DRAFT, TranslationStatus.REVIEWED})
        translations = {
            value.segment_id: value
            for value in self.list_translations(project_id)
            if value.status in eligible_statuses and value.text
        }
        available = [segment for segment in segments if segment.id in translations]
        if not available:
            scope = "usable" if include_unapproved else "approved"
            raise ValueError(f"There are no {scope} translations to export.")
        self._validate_export_segments(available)
        blocks: list[str] = []
        for index, segment in enumerate(available, start=1):
            translation = translations[segment.id]
            text = self._normalize_srt_text(translation.text or "")
            blocks.append(
                f"{index}\n{self._srt_time(segment.start_ms)} --> "
                f"{self._srt_time(segment.end_ms)}\n{text}"
            )
        temporary = destination.with_name(f".{destination.name}.tmp")
        try:
            temporary.write_text(
                "\n\n".join(blocks) + "\n",
                encoding="utf-8-sig",
                newline="\n",
            )
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return len(available)

    @staticmethod
    def _validate_export_segments(segments: list[TranscriptSegment]) -> None:
        previous_start = -1
        for segment in segments:
            if segment.start_ms < 0:
                raise ValueError("Subtitle timestamps cannot be negative.")
            if segment.end_ms <= segment.start_ms:
                raise ValueError("Every subtitle must end after it starts.")
            if segment.start_ms < previous_start:
                raise ValueError("Subtitle cues are not in chronological order.")
            previous_start = segment.start_ms

    @staticmethod
    def _normalize_srt_text(text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            raise ValueError("Subtitle text cannot be empty.")
        if "\x00" in normalized:
            raise ValueError("Subtitle text contains an invalid null character.")
        return normalized

    @staticmethod
    def _srt_time(milliseconds: int) -> str:
        hours, remainder = divmod(max(0, milliseconds), 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        seconds, milliseconds = divmod(remainder, 1_000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def translate(
        self,
        project_id: str,
        segment_ids: set[str] | None,
        progress: Callable[[int], None],
        cancel: Event,
    ) -> list[SegmentTranslation]:
        project = self._projects.get(project_id)
        if project is None:
            raise LookupError(project_id)
        if not project.target_language:
            raise ValueError("Set a target language before translating.")
        target_language = project.target_language
        segments = self._transcripts.list_for_project(project_id)
        if segment_ids is not None:
            segments = [segment for segment in segments if segment.id in segment_ids]
        if not segments:
            raise ValueError("No transcript segments were selected for translation.")
        instructions = self._instructions.read()
        wordbank = self._glossary.read_wordbank(project_id)
        if cancel.is_set():
            raise TranslationCancelled("Translation was cancelled.")
        request = TranslationRequest(
            segments=tuple((segment.id, segment.text) for segment in segments),
            source_language=project.source_language,
            target_language=target_language,
            wordbank=wordbank,
            instructions=instructions,
        )
        progress(10)
        try:
            results = self._call_provider_cancellable(request, cancel)
            if set(results) != {segment.id for segment in segments}:
                raise RuntimeError(
                    "The translation provider did not return exactly one result per segment."
                )
        except TranslationCancelled:
            raise
        except Exception as error:
            existing = {
                value.segment_id: value for value in self._translations.list_for_project(project_id)
            }
            for segment in segments:
                self._persist_failure(
                    project,
                    target_language,
                    segment,
                    existing.get(segment.id),
                    str(error),
                )
        else:
            for segment in segments:
                self._persist_result(project, target_language, segment, results[segment.id], None)
        progress(100)
        return self.list_translations(project_id)

    def _call_provider_cancellable(
        self, request: TranslationRequest, cancel: Event
    ) -> dict[str, str]:
        outcome: Queue[dict[str, str] | Exception] = Queue(maxsize=1)

        def call_provider() -> None:
            try:
                outcome.put(self._provider.translate_batch(request))
            except Exception as error:
                outcome.put(error)

        Thread(target=call_provider, daemon=True, name="translation-api-call").start()
        while True:
            if cancel.is_set():
                raise TranslationCancelled(
                    "Translation was cancelled; any late API response will be discarded."
                )
            try:
                result = outcome.get(timeout=0.1)
            except Empty:
                continue
            if isinstance(result, Exception):
                raise result
            return result

    def retry_failed(
        self, project_id: str, progress: Callable[[int], None], cancel: Event
    ) -> list[SegmentTranslation]:
        failed_ids = {
            value.segment_id
            for value in self.list_translations(project_id)
            if value.status == TranslationStatus.FAILED or value.last_attempt_error is not None
        }
        if not failed_ids:
            raise ValueError("There are no failed translations to retry.")
        return self.translate(project_id, failed_ids, progress, cancel)

    def _persist_result(
        self,
        project: Project,
        target_language: str,
        segment: TranscriptSegment,
        text: str | None,
        error: str | None,
    ) -> None:
        now = datetime.now(UTC)
        if error is None and text is not None:
            translation = SegmentTranslation(
                segment.id,
                project.id,
                target_language,
                text,
                segment.source_revision,
                TranslationStatus.DRAFT,
                self._provider.name,
                self._provider.model,
                None,
                now,
                None,
                now,
            )
        else:
            translation = SegmentTranslation(
                segment.id,
                project.id,
                target_language,
                None,
                segment.source_revision,
                TranslationStatus.FAILED,
                self._provider.name,
                self._provider.model,
                error or "Unknown translation error",
                now,
                error or "Unknown translation error",
                now,
            )
        self._translations.upsert(translation)

    def _persist_failure(
        self,
        project: Project,
        target_language: str,
        segment: TranscriptSegment,
        current: SegmentTranslation | None,
        error: str,
    ) -> None:
        """Record a failed attempt without destroying a usable translation."""
        now = datetime.now(UTC)
        if current is not None and current.text:
            self._translations.upsert(
                replace(
                    current,
                    last_attempt_error=error,
                    last_attempt_at=now,
                )
            )
            return
        self._persist_result(project, target_language, segment, None, error)
