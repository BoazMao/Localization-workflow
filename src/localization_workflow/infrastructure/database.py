"""SQLite engine, migrations, and project persistence."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import DateTime, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from localization_workflow.domain.projects import Project, ProjectStatus


class Base(DeclarativeBase):
    """Declarative model base."""


class ProjectRecord(Base):
    """Database representation of a project."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_language: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    media_path: Mapped[str | None] = mapped_column(String(1000))
    original_filename: Mapped[str | None] = mapped_column(String(500))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    media_type: Mapped[str | None] = mapped_column(String(20))
    video_codec: Mapped[str | None] = mapped_column(String(100))
    audio_codec: Mapped[str | None] = mapped_column(String(100))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Database:
    """Own the SQLite engine and Alembic lifecycle."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.engine = create_engine(f"sqlite:///{path.as_posix()}")
        self._sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def migrate(self) -> None:
        """Upgrade the database to the latest bundled migration."""
        script_location = Path(__file__).parent / "migrations"
        config = Config()
        config.set_main_option("script_location", str(script_location))
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Provide a transactional session."""
        session = self._sessions()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class ProjectRepository:
    """Persist and retrieve project snapshots."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def add(self, project: Project) -> None:
        with self._database.session() as session:
            session.add(self._to_record(project))

    def get(self, project_id: str) -> Project | None:
        with self._database.session() as session:
            record = session.get(ProjectRecord, project_id)
            return self._to_domain(record) if record else None

    def list(self) -> list[Project]:
        with self._database.session() as session:
            records = session.scalars(
                select(ProjectRecord).order_by(ProjectRecord.updated_at.desc())
            ).all()
            return [self._to_domain(record) for record in records]

    def update(self, project: Project) -> None:
        with self._database.session() as session:
            session.merge(self._to_record(project))

    def delete(self, project_id: str) -> None:
        with self._database.session() as session:
            record = session.get(ProjectRecord, project_id)
            if record:
                session.delete(record)

    @staticmethod
    def _to_record(project: Project) -> ProjectRecord:
        return ProjectRecord(
            id=project.id,
            name=project.name,
            source_language=project.source_language,
            status=project.status.value,
            media_path=str(project.media_path) if project.media_path else None,
            original_filename=project.original_filename,
            duration_ms=project.duration_ms,
            media_type=project.media_type,
            video_codec=project.video_codec,
            audio_codec=project.audio_codec,
            width=project.width,
            height=project.height,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    @staticmethod
    def _to_domain(record: ProjectRecord) -> Project:
        created_at = (
            record.created_at.replace(tzinfo=UTC)
            if not record.created_at.tzinfo
            else record.created_at
        )
        updated_at = (
            record.updated_at.replace(tzinfo=UTC)
            if not record.updated_at.tzinfo
            else record.updated_at
        )
        return Project(
            id=record.id,
            name=record.name,
            source_language=record.source_language,
            status=ProjectStatus(record.status),
            created_at=created_at,
            updated_at=updated_at,
            media_path=Path(record.media_path) if record.media_path else None,
            original_filename=record.original_filename,
            duration_ms=record.duration_ms,
            media_type=record.media_type,
            video_codec=record.video_codec,
            audio_codec=record.audio_codec,
            width=record.width,
            height=record.height,
        )
