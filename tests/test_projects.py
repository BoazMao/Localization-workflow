from pathlib import Path
from threading import Event

from localization_workflow.application.projects import ProjectService
from localization_workflow.domain.projects import MediaInfo, ProjectStatus
from localization_workflow.infrastructure.database import Database, ProjectRepository
from localization_workflow.infrastructure.media import ManagedMediaStore


class FakeProbe:
    def probe(self, path: Path) -> MediaInfo:
        assert path.exists()
        return MediaInfo(
            duration_ms=12_500,
            media_type="video",
            video_codec="h264",
            audio_codec="aac",
            width=1920,
            height=1080,
        )


class FakeAudioProcessor:
    def __init__(self) -> None:
        self.reuse_requests: list[bool] = []

    def prepare(
        self,
        project_id: str,
        source: Path,
        duration_ms: int,
        progress,
        cancel: Event,
        reuse_existing: bool,
    ) -> Path:
        self.reuse_requests.append(reuse_existing)
        assert source.exists()
        assert not cancel.is_set()
        destination = source.parents[2] / "derived" / project_id / "transcription.wav"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake wav")
        progress(100)
        return destination


def make_service(
    tmp_path: Path, audio_processor: FakeAudioProcessor | None = None
) -> ProjectService:
    database = Database(tmp_path / "projects.sqlite3")
    database.migrate()
    repository = ProjectRepository(database)
    media_store = ManagedMediaStore(tmp_path / "media", FakeProbe())
    return ProjectService(repository, media_store, audio_processor or FakeAudioProcessor())


def test_project_survives_repository_reopen(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    created = service.create("Training video", "English")

    reopened = make_service(tmp_path).get(created.id)

    assert reopened.name == "Training video"
    assert reopened.source_language == "English"
    assert reopened.status == ProjectStatus.EMPTY


def test_import_copies_media_and_persists_metadata(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    project = service.create("Hydraulics")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fake media")

    updated = service.import_media(project.id, source)

    assert updated.status == ProjectStatus.MEDIA_READY
    assert updated.original_filename == "source.mp4"
    assert updated.media_path is not None
    assert updated.media_path.exists()
    assert updated.media_path != source
    assert updated.duration_ms == 12_500
    assert updated.width == 1920
    assert service.get(project.id).video_codec == "h264"


def test_delete_removes_project_and_managed_media(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    project = service.create("Temporary")
    source = tmp_path / "source.wav"
    source.write_bytes(b"fake media")
    updated = service.import_media(project.id, source)
    assert updated.media_path is not None
    project_dir = updated.media_path.parent

    service.delete(project.id)

    assert service.list() == []
    assert not project_dir.exists()


def test_prepare_audio_persists_ready_state(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    project = service.create("Audio preparation")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fake media")
    imported = service.import_media(project.id, source)
    progress: list[int] = []

    prepared = service.prepare_audio(imported.id, progress.append, Event())

    assert prepared.audio_status.value == "ready"
    assert prepared.derived_audio_path is not None
    assert prepared.derived_audio_path.exists()
    assert progress == [100]
    assert service.get(project.id).audio_status.value == "ready"


def test_replacing_media_forces_audio_regeneration(tmp_path: Path) -> None:
    audio_processor = FakeAudioProcessor()
    service = make_service(tmp_path, audio_processor)
    project = service.create("Replacement media")
    first_source = tmp_path / "first.mp4"
    first_source.write_bytes(b"first media")
    service.import_media(project.id, first_source)
    service.prepare_audio(project.id, lambda _value: None, Event())

    second_source = tmp_path / "second.mp4"
    second_source.write_bytes(b"second media")
    replaced = service.import_media(project.id, second_source)
    service.prepare_audio(project.id, lambda _value: None, Event())

    assert replaced.audio_status.value == "not_prepared"
    assert replaced.derived_audio_path is None
    assert audio_processor.reuse_requests == [False, False]
