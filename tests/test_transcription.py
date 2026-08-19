from pathlib import Path
from threading import Event

import pytest
from test_projects import FakeAudioProcessor

from localization_workflow.application.projects import ProjectService
from localization_workflow.application.transcription import TranscriptionService
from localization_workflow.domain.projects import AudioStatus, MediaInfo, TranscriptionStatus
from localization_workflow.infrastructure.database import (
    Database,
    ProjectRepository,
    TranscriptRepository,
)
from localization_workflow.infrastructure.media import ManagedMediaStore
from localization_workflow.infrastructure.models import ManagedWhisperModels
from localization_workflow.providers.transcription import (
    ProviderSegment,
    parse_cli_output,
    parse_subrip,
)


class FakeProbe:
    def probe(self, path: Path) -> MediaInfo:
        return MediaInfo(2000, "video", "h264", "aac", 1280, 720)


class FakeSpeechProvider:
    model_name = "deterministic-test-model"

    def select_model(self, path: Path) -> None:
        self.model_name = path.name

    def transcribe(self, audio_path, language, progress, cancel):
        assert audio_path.is_file()
        assert language == "English"
        assert not cancel.is_set()
        progress(50)
        progress(100)
        return [
            ProviderSegment(0, 900, "Hello world."),
            ProviderSegment(900, 2000, "This is a test."),
        ]


def make_services(tmp_path: Path):
    database = Database(tmp_path / "projects.sqlite3")
    database.migrate()
    projects_repository = ProjectRepository(database)
    transcripts_repository = TranscriptRepository(database)
    projects = ProjectService(
        projects_repository,
        ManagedMediaStore(tmp_path / "media", FakeProbe()),
        FakeAudioProcessor(),
        transcripts_repository,
    )
    transcription = TranscriptionService(
        projects_repository,
        transcripts_repository,
        FakeSpeechProvider(),
        ManagedWhisperModels(tmp_path / "models"),
    )
    return projects, transcription


def test_parse_subrip_normalizes_multiline_segments() -> None:
    result = parse_subrip(
        "1\n00:00:00,000 --> 00:00:01,250\nFirst line\ncontinues.\n\n"
        "2\n00:00:01.250 --> 00:00:02.000\nSecond line.\n"
    )

    assert result == [
        ProviderSegment(0, 1250, "First line\ncontinues."),
        ProviderSegment(1250, 2000, "Second line."),
    ]


def test_parse_cli_output_uses_native_distinct_timestamps() -> None:
    result = parse_cli_output(
        'Using GPU "Test GPU"\n'
        "[00:00:01.250 --> 00:00:03.500] First segment.\n"
        "[00:00:04.000 --> 00:00:07.200] Second segment.\n"
    )

    assert result == [
        ProviderSegment(1250, 3500, "First segment."),
        ProviderSegment(4000, 7200, "Second segment."),
    ]


def test_transcription_persists_stable_ordered_segments(tmp_path: Path) -> None:
    projects, transcription = make_services(tmp_path)
    project = projects.create("Transcript", "English")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"media")
    projects.import_media(project.id, source)
    prepared = projects.prepare_audio(project.id, lambda _value: None, Event())
    assert prepared.audio_status == AudioStatus.READY

    completed = transcription.transcribe(project.id, lambda _value: None, Event())
    segments = transcription.list_segments(project.id)

    assert completed.transcription_status == TranscriptionStatus.READY
    assert completed.transcription_model == "deterministic-test-model"
    assert [segment.position for segment in segments] == [0, 1]
    assert [segment.text for segment in segments] == ["Hello world.", "This is a test."]
    assert len({segment.id for segment in segments}) == 2


def test_replacing_media_invalidates_transcript(tmp_path: Path) -> None:
    projects, transcription = make_services(tmp_path)
    project = projects.create("Replacement", "English")
    first = tmp_path / "first.mp4"
    first.write_bytes(b"first")
    projects.import_media(project.id, first)
    projects.prepare_audio(project.id, lambda _value: None, Event())
    transcription.transcribe(project.id, lambda _value: None, Event())
    assert transcription.list_segments(project.id)

    second = tmp_path / "second.mp4"
    second.write_bytes(b"second")
    replaced = projects.import_media(project.id, second)

    assert replaced.transcription_status == TranscriptionStatus.NOT_STARTED
    assert transcription.list_segments(project.id) == []


def test_transcription_requires_explicit_language(tmp_path: Path) -> None:
    projects, transcription = make_services(tmp_path)
    project = projects.create("Language required")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"media")
    projects.import_media(project.id, source)
    projects.prepare_audio(project.id, lambda _value: None, Event())

    with pytest.raises(ValueError, match="spoken source language"):
        transcription.transcribe(project.id, lambda _value: None, Event())


def test_edit_preserves_segment_id_and_increments_revision(tmp_path: Path) -> None:
    projects, transcription = make_services(tmp_path)
    project = projects.create("Review", "English")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"media")
    projects.import_media(project.id, source)
    projects.prepare_audio(project.id, lambda _value: None, Event())
    transcription.transcribe(project.id, lambda _value: None, Event())
    original = transcription.list_segments(project.id)[0]

    updated = transcription.save_edits(project.id, {original.id: "Corrected source text."})[0]

    assert updated.id == original.id
    assert updated.start_ms == original.start_ms
    assert updated.end_ms == original.end_ms
    assert updated.text == "Corrected source text."
    assert updated.source_revision == original.source_revision + 1


def test_saving_unchanged_text_does_not_increment_revision(tmp_path: Path) -> None:
    projects, transcription = make_services(tmp_path)
    project = projects.create("No-op review", "English")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"media")
    projects.import_media(project.id, source)
    projects.prepare_audio(project.id, lambda _value: None, Event())
    transcription.transcribe(project.id, lambda _value: None, Event())
    original = transcription.list_segments(project.id)[0]

    unchanged = transcription.save_edits(project.id, {original.id: original.text})[0]

    assert unchanged.source_revision == original.source_revision


def test_empty_segment_edit_is_rejected(tmp_path: Path) -> None:
    projects, transcription = make_services(tmp_path)
    project = projects.create("Validation", "English")

    with pytest.raises(ValueError, match="cannot be empty"):
        transcription.save_edits(project.id, {"segment-id": "   "})
