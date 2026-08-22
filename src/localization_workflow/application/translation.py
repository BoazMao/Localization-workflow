"""Segment translation workflow."""

from __future__ import annotations

from collections.abc import Callable
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
            raise RuntimeError("The active translation provider is not OpenAI.")
        self._provider.configure(api_key, model, base_url)

    def list_translations(self, project_id: str) -> list[SegmentTranslation]:
        return self._translations.list_for_project(project_id)

    def export_srt(self, project_id: str, destination: Path) -> int:
        segments = self._transcripts.list_for_project(project_id)
        translations = {
            value.segment_id: value
            for value in self.list_translations(project_id)
            if value.status == TranslationStatus.READY and value.text
        }
        available = [segment for segment in segments if segment.id in translations]
        if not available:
            raise ValueError("There are no completed translations to export.")
        blocks = []
        for index, segment in enumerate(available, start=1):
            translation = translations[segment.id]
            blocks.append(
                f"{index}\n{self._srt_time(segment.start_ms)} --> "
                f"{self._srt_time(segment.end_ms)}\n{translation.text}"
            )
        destination.write_text("\n\n".join(blocks) + "\n", encoding="utf-8-sig")
        return len(available)

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
            for segment in segments:
                self._persist_result(project, target_language, segment, None, str(error))
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
            if value.status == TranslationStatus.FAILED
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
                TranslationStatus.READY,
                self._provider.name,
                self._provider.model,
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
            )
        self._translations.upsert(translation)
