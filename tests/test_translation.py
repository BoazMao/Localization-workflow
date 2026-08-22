from pathlib import Path
from threading import Event, Timer

import pytest
from test_projects import FakeAudioProcessor, FakeProbe

from localization_workflow.application.glossary import GlossaryService
from localization_workflow.application.projects import ProjectService
from localization_workflow.application.translation import TranslationCancelled, TranslationService
from localization_workflow.domain.projects import TranscriptSegment, TranslationStatus
from localization_workflow.infrastructure.database import (
    Database,
    GlossaryRepository,
    ProjectRepository,
    TranscriptRepository,
    TranslationRepository,
)
from localization_workflow.infrastructure.instructions import TranslationInstructionsStore
from localization_workflow.infrastructure.media import ManagedMediaStore
from localization_workflow.providers.translation import TranslationRequest


class FakeTranslationProvider:
    name = "Fake ChatGPT"
    model = "test-model"

    def __init__(self) -> None:
        self.requests: list[TranslationRequest] = []
        self.fail_text: str | None = None
        self.block: Event | None = None

    def translate_batch(self, request: TranslationRequest) -> dict[str, str]:
        self.requests.append(request)
        if self.block is not None:
            self.block.wait()
        if self.fail_text and any(text == self.fail_text for _segment_id, text in request.segments):
            raise RuntimeError("temporary provider failure")
        return {segment_id: f"Chinese: {text}" for segment_id, text in request.segments}


def make_service(tmp_path: Path):
    database = Database(tmp_path / "projects.sqlite3")
    database.migrate()
    projects = ProjectRepository(database)
    transcripts = TranscriptRepository(database)
    project_service = ProjectService(
        projects,
        ManagedMediaStore(tmp_path / "media", FakeProbe()),
        FakeAudioProcessor(),
        transcripts,
    )
    glossary = GlossaryService(projects, GlossaryRepository(database))
    provider = FakeTranslationProvider()
    instructions = TranslationInstructionsStore(tmp_path / "AGENTS.md")
    instructions.save("Use neutral Latin American Spanish.")
    service = TranslationService(
        projects,
        transcripts,
        TranslationRepository(database),
        glossary,
        provider,
        instructions,
    )
    project = project_service.create("Translation", "English")
    project = glossary.set_target_language(project.id, "Simplified Chinese")
    segments = [
        TranscriptSegment("one", project.id, 0, 0, 1000, "Launch the drop ship."),
        TranscriptSegment("two", project.id, 1, 1000, 2000, "Hold position."),
    ]
    transcripts.replace(project.id, segments)
    return service, glossary, provider, project, segments


def test_translation_uses_agents_and_matching_wordbank_entries(tmp_path: Path) -> None:
    service, glossary, provider, project, segments = make_service(tmp_path)
    wordbank = (
        "1. drop ship: nave de desembarco\n2. Push can be used as a verb when the team advances."
    )
    glossary.save_wordbank(project.id, wordbank)
    progress: list[int] = []

    translations = service.translate(project.id, None, progress.append, Event())

    assert progress == [10, 100]
    assert len(provider.requests) == 1
    assert provider.requests[0].instructions == "Use neutral Latin American Spanish."
    assert provider.requests[0].wordbank == wordbank
    assert provider.requests[0].segments == (
        (segments[0].id, segments[0].text),
        (segments[1].id, segments[1].text),
    )
    assert [value.segment_id for value in translations] == [segment.id for segment in segments]
    assert all(value.status == TranslationStatus.READY for value in translations)
    assert all(value.source_revision == 1 for value in translations)


def test_selected_translation_and_failed_retry_are_persisted(tmp_path: Path) -> None:
    service, _glossary, provider, project, segments = make_service(tmp_path)
    provider.fail_text = segments[1].text

    service.translate(project.id, {segments[1].id}, lambda _value: None, Event())
    failed = service.list_translations(project.id)

    assert len(failed) == 1
    assert failed[0].status == TranslationStatus.FAILED
    assert failed[0].error == "temporary provider failure"

    provider.fail_text = None
    retried = service.retry_failed(project.id, lambda _value: None, Event())

    assert len(retried) == 1
    assert retried[0].status == TranslationStatus.READY
    assert retried[0].provider == "Fake ChatGPT"
    assert retried[0].model == "test-model"


def test_completed_translations_export_as_timestamped_unicode_srt(tmp_path: Path) -> None:
    service, _glossary, _provider, project, _segments = make_service(tmp_path)
    service.translate(project.id, None, lambda _value: None, Event())
    destination = tmp_path / "简体中文字幕.srt"

    count = service.export_srt(project.id, destination)
    content = destination.read_text(encoding="utf-8-sig")

    assert count == 2
    assert "1\n00:00:00,000 --> 00:00:01,000\nChinese: Launch the drop ship." in content
    assert "2\n00:00:01,000 --> 00:00:02,000\nChinese: Hold position." in content


def test_cancel_releases_batch_without_persisting_late_response(tmp_path: Path) -> None:
    service, _glossary, provider, project, _segments = make_service(tmp_path)
    provider.block = Event()
    cancel = Event()
    Timer(0.05, cancel.set).start()

    with pytest.raises(TranslationCancelled, match="late API response"):
        service.translate(project.id, None, lambda _value: None, cancel)

    provider.block.set()
    assert service.list_translations(project.id) == []
