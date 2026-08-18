from pathlib import Path

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


def make_service(tmp_path: Path) -> ProjectService:
    database = Database(tmp_path / "projects.sqlite3")
    database.migrate()
    repository = ProjectRepository(database)
    media_store = ManagedMediaStore(tmp_path / "media", FakeProbe())
    return ProjectService(repository, media_store)


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
