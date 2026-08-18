"""Project workflow service."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from localization_workflow.domain.projects import Project, ProjectStatus
from localization_workflow.infrastructure.database import ProjectRepository
from localization_workflow.infrastructure.media import ManagedMediaStore


class ProjectNotFoundError(LookupError):
    """Requested project does not exist."""


class ProjectService:
    """Coordinate project persistence and managed media."""

    def __init__(self, repository: ProjectRepository, media_store: ManagedMediaStore) -> None:
        self._repository = repository
        self._media_store = media_store

    def create(self, name: str, source_language: str = "Auto-detect") -> Project:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Project name is required.")
        now = datetime.now(UTC)
        project = Project(
            id=str(uuid4()),
            name=clean_name,
            source_language=source_language.strip() or "Auto-detect",
            status=ProjectStatus.EMPTY,
            created_at=now,
            updated_at=now,
        )
        self._repository.add(project)
        return project

    def list(self) -> list[Project]:
        return self._repository.list()

    def get(self, project_id: str) -> Project:
        project = self._repository.get(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        return project

    def rename(self, project_id: str, name: str) -> Project:
        project = self.get(project_id)
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Project name is required.")
        updated = replace(project, name=clean_name, updated_at=datetime.now(UTC))
        self._repository.update(updated)
        return updated

    def import_media(self, project_id: str, source: Path) -> Project:
        project = self.get(project_id)
        destination, info = self._media_store.import_file(project_id, source)
        updated = replace(
            project,
            status=ProjectStatus.MEDIA_READY,
            media_path=destination,
            original_filename=source.name,
            duration_ms=info.duration_ms,
            media_type=info.media_type,
            video_codec=info.video_codec,
            audio_codec=info.audio_codec,
            width=info.width,
            height=info.height,
            updated_at=datetime.now(UTC),
        )
        self._repository.update(updated)
        if project.media_path and project.media_path != destination:
            project.media_path.unlink(missing_ok=True)
        return updated

    def delete(self, project_id: str) -> None:
        self.get(project_id)
        self._repository.delete(project_id)
        self._media_store.delete_project_media(project_id)
