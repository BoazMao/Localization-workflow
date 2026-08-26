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
from localization_workflow.providers.translation import TranslationRequest, _parse_batch_result


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


def test_numbered_batch_output_maps_back_to_internal_segment_ids() -> None:
    segments = (("uuid-one", "First"), ("uuid-two", "Second"))

    result = _parse_batch_result(
        '```json\n{"translations":[{"line":1,"text":"第一"},{"line":"2","text":"第二"}]}\n```',
        segments,
    )

    assert result == {"uuid-one": "第一", "uuid-two": "第二"}


def test_numbered_batch_output_reports_missing_lines() -> None:
    segments = (("uuid-one", "First"), ("uuid-two", "Second"))

    with pytest.raises(RuntimeError, match="missing lines: 2"):
        _parse_batch_result('{"translations":[{"line":1,"text":"第一"}]}', segments)


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
    return service, glossary, provider, project, segments, transcripts


def test_translation_uses_agents_and_matching_wordbank_entries(tmp_path: Path) -> None:
    service, glossary, provider, project, segments, _transcripts = make_service(tmp_path)
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
    assert all(value.status == TranslationStatus.DRAFT for value in translations)
    assert all(value.source_revision == 1 for value in translations)


def test_selected_translation_and_failed_retry_are_persisted(tmp_path: Path) -> None:
    service, _glossary, provider, project, segments, _transcripts = make_service(tmp_path)
    provider.fail_text = segments[1].text

    service.translate(project.id, {segments[1].id}, lambda _value: None, Event())
    failed = service.list_translations(project.id)

    assert len(failed) == 1
    assert failed[0].status == TranslationStatus.FAILED
    assert failed[0].error == "temporary provider failure"
    assert failed[0].last_attempt_error == "temporary provider failure"

    provider.fail_text = None
    retried = service.retry_failed(project.id, lambda _value: None, Event())

    assert len(retried) == 1
    assert retried[0].status == TranslationStatus.DRAFT
    assert retried[0].provider == "Fake ChatGPT"
    assert retried[0].model == "test-model"
    assert retried[0].last_attempt_error is None


def test_failed_retranslation_preserves_approved_translation(tmp_path: Path) -> None:
    service, _glossary, provider, project, segments, _transcripts = make_service(tmp_path)
    service.translate(project.id, None, lambda _value: None, Event())
    service.set_review_status(project.id, {segments[0].id}, TranslationStatus.APPROVED)
    before = next(
        value
        for value in service.list_translations(project.id)
        if value.segment_id == segments[0].id
    )
    provider.fail_text = segments[0].text

    service.translate(project.id, {segments[0].id}, lambda _value: None, Event())

    after = next(
        value
        for value in service.list_translations(project.id)
        if value.segment_id == segments[0].id
    )
    assert after.text == before.text
    assert after.status == TranslationStatus.APPROVED
    assert after.source_revision == before.source_revision
    assert after.last_attempt_error == "temporary provider failure"
    assert after.last_attempt_at is not None

    provider.fail_text = None
    retried = service.retry_failed(project.id, lambda _value: None, Event())
    refreshed = next(value for value in retried if value.segment_id == segments[0].id)
    assert refreshed.status == TranslationStatus.DRAFT
    assert refreshed.last_attempt_error is None


def test_completed_translations_export_as_timestamped_unicode_srt(tmp_path: Path) -> None:
    service, _glossary, _provider, project, segments, _transcripts = make_service(tmp_path)
    service.translate(project.id, None, lambda _value: None, Event())
    service.set_review_status(
        project.id,
        {segment.id for segment in segments},
        TranslationStatus.APPROVED,
    )
    destination = tmp_path / "简体中文字幕.srt"

    count = service.export_srt(project.id, destination)
    content = destination.read_text(encoding="utf-8-sig")

    assert count == 2
    assert "1\n00:00:00,000 --> 00:00:01,000\nChinese: Launch the drop ship." in content
    assert "2\n00:00:01,000 --> 00:00:02,000\nChinese: Hold position." in content


def test_cancel_releases_batch_without_persisting_late_response(tmp_path: Path) -> None:
    service, _glossary, provider, project, _segments, _transcripts = make_service(tmp_path)
    provider.block = Event()
    cancel = Event()
    Timer(0.05, cancel.set).start()

    with pytest.raises(TranslationCancelled, match="late API response"):
        service.translate(project.id, None, lambda _value: None, cancel)

    provider.block.set()
    assert service.list_translations(project.id) == []


def test_translation_review_edit_and_approval_are_persisted(tmp_path: Path) -> None:
    service, _glossary, _provider, project, segments, _transcripts = make_service(tmp_path)
    service.translate(project.id, None, lambda _value: None, Event())

    reviewed = service.set_review_status(project.id, {segments[0].id}, TranslationStatus.REVIEWED)
    assert next(value for value in reviewed if value.segment_id == segments[0].id).status == (
        TranslationStatus.REVIEWED
    )

    edited = service.save_edits(project.id, {segments[0].id: "  Human revision.  "})
    changed = next(value for value in edited if value.segment_id == segments[0].id)
    assert changed.text == "Human revision."
    assert changed.status == TranslationStatus.DRAFT

    approved = service.set_review_status(project.id, {segments[0].id}, TranslationStatus.APPROVED)
    assert next(value for value in approved if value.segment_id == segments[0].id).status == (
        TranslationStatus.APPROVED
    )


def test_source_revision_change_makes_translation_outdated(tmp_path: Path) -> None:
    service, _glossary, _provider, project, segments, transcripts = make_service(tmp_path)
    service.translate(project.id, None, lambda _value: None, Event())
    service.set_review_status(project.id, {segments[0].id}, TranslationStatus.APPROVED)

    transcripts.update_texts(project.id, {segments[0].id: "Updated source text."})
    values = service.list_translations(project.id)
    outdated = next(value for value in values if value.segment_id == segments[0].id)

    assert outdated.status == TranslationStatus.OUTDATED
    with pytest.raises(ValueError, match="outdated"):
        service.set_review_status(project.id, {segments[0].id}, TranslationStatus.APPROVED)


def test_only_approved_translations_are_exported(tmp_path: Path) -> None:
    service, _glossary, _provider, project, segments, _transcripts = make_service(tmp_path)
    service.translate(project.id, None, lambda _value: None, Event())

    with pytest.raises(ValueError, match="no approved translations"):
        service.export_srt(project.id, tmp_path / "drafts.srt")

    service.set_review_status(project.id, {segments[0].id}, TranslationStatus.APPROVED)
    destination = tmp_path / "approved.srt"
    assert service.export_srt(project.id, destination) == 1
    assert "Launch the drop ship" in destination.read_text(encoding="utf-8-sig")
    assert "Hold position" not in destination.read_text(encoding="utf-8-sig")


def test_export_readiness_counts_every_segment_state(tmp_path: Path) -> None:
    service, _glossary, _provider, project, segments, transcripts = make_service(tmp_path)
    service.translate(project.id, None, lambda _value: None, Event())
    service.set_review_status(project.id, {segments[0].id}, TranslationStatus.APPROVED)

    initial = service.export_readiness(project.id)
    assert initial.total == 2
    assert initial.approved == 1
    assert initial.draft == 1
    assert initial.usable_count == 2
    assert initial.omitted_count == 0

    transcripts.update_texts(project.id, {segments[0].id: "Revised source."})
    changed = service.export_readiness(project.id)
    assert changed.approved == 0
    assert changed.outdated == 1
    assert changed.draft == 1
    assert changed.omitted_count == 1


def test_explicit_unapproved_export_includes_drafts_and_reviewed(tmp_path: Path) -> None:
    service, _glossary, _provider, project, segments, _transcripts = make_service(tmp_path)
    service.translate(project.id, None, lambda _value: None, Event())
    service.set_review_status(project.id, {segments[0].id}, TranslationStatus.REVIEWED)
    destination = tmp_path / "review-copy.srt"

    count = service.export_srt(project.id, destination, include_unapproved=True)

    assert count == 2
    content = destination.read_bytes()
    assert content.startswith(b"\xef\xbb\xbf")
    decoded = content.decode("utf-8-sig")
    assert decoded.endswith("\n")
    assert "\n\n2\n00:00:01,000 --> 00:00:02,000\n" in decoded


@pytest.mark.parametrize(
    ("start_ms", "end_ms", "message"),
    [
        (-1, 1000, "cannot be negative"),
        (1000, 1000, "end after it starts"),
        (2000, 1000, "end after it starts"),
    ],
)
def test_export_rejects_invalid_timestamps_without_overwriting_destination(
    tmp_path: Path, start_ms: int, end_ms: int, message: str
) -> None:
    service, _glossary, _provider, project, segments, transcripts = make_service(tmp_path)
    transcripts.replace(
        project.id,
        [
            TranscriptSegment(
                segments[0].id,
                project.id,
                0,
                start_ms,
                end_ms,
                segments[0].text,
            )
        ],
    )
    service.translate(project.id, None, lambda _value: None, Event())
    service.set_review_status(project.id, {segments[0].id}, TranslationStatus.APPROVED)
    destination = tmp_path / "existing.srt"
    destination.write_text("keep me", encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        service.export_srt(project.id, destination)

    assert destination.read_text(encoding="utf-8") == "keep me"


def test_export_rejects_non_chronological_cues(tmp_path: Path) -> None:
    service, _glossary, _provider, project, _segments, transcripts = make_service(tmp_path)
    reordered = [
        TranscriptSegment("late", project.id, 0, 2000, 3000, "Late"),
        TranscriptSegment("early", project.id, 1, 0, 1000, "Early"),
    ]
    transcripts.replace(project.id, reordered)
    service.translate(project.id, None, lambda _value: None, Event())
    service.set_review_status(
        project.id, {segment.id for segment in reordered}, TranslationStatus.APPROVED
    )

    with pytest.raises(ValueError, match="chronological order"):
        service.export_srt(project.id, tmp_path / "unordered.srt")


def test_export_requires_srt_extension_and_existing_folder(tmp_path: Path) -> None:
    service, _glossary, _provider, project, segments, _transcripts = make_service(tmp_path)
    service.translate(project.id, None, lambda _value: None, Event())
    service.set_review_status(project.id, {segments[0].id}, TranslationStatus.APPROVED)

    with pytest.raises(ValueError, match=r"end with \.srt"):
        service.export_srt(project.id, tmp_path / "subtitles.txt")
    with pytest.raises(ValueError, match="folder does not exist"):
        service.export_srt(project.id, tmp_path / "missing" / "subtitles.srt")
