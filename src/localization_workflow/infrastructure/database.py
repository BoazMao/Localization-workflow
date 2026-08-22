"""SQLite engine, migrations, and project persistence."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from localization_workflow.domain.projects import (
    AudioStatus,
    GlossaryEntry,
    Project,
    ProjectStatus,
    TranscriptionStatus,
    TranscriptSegment,
)


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
    audio_status: Mapped[str] = mapped_column(String(30), nullable=False, default="not_prepared")
    derived_audio_path: Mapped[str | None] = mapped_column(String(1000))
    derived_audio_duration_ms: Mapped[int | None] = mapped_column(Integer)
    audio_error: Mapped[str | None] = mapped_column(String(1000))
    transcription_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="not_started"
    )
    transcription_model: Mapped[str | None] = mapped_column(String(500))
    transcription_error: Mapped[str | None] = mapped_column(String(1000))
    target_language: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TranscriptSegmentRecord(Base):
    """Database representation of a timestamped source segment."""

    __tablename__ = "transcript_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class GlossaryEntryRecord(Base):
    """Database representation of a project glossary entry."""

    __tablename__ = "glossary_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_term: Mapped[str] = mapped_column(String(500), nullable=False)
    source_term_key: Mapped[str] = mapped_column(String(500), nullable=False)
    target_term: Mapped[str] = mapped_column(String(500), nullable=False)


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
            audio_status=project.audio_status.value,
            derived_audio_path=(
                str(project.derived_audio_path) if project.derived_audio_path else None
            ),
            derived_audio_duration_ms=project.derived_audio_duration_ms,
            audio_error=project.audio_error,
            transcription_status=project.transcription_status.value,
            transcription_model=project.transcription_model,
            transcription_error=project.transcription_error,
            target_language=project.target_language,
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
            audio_status=AudioStatus(record.audio_status),
            derived_audio_path=(
                Path(record.derived_audio_path) if record.derived_audio_path else None
            ),
            derived_audio_duration_ms=record.derived_audio_duration_ms,
            audio_error=record.audio_error,
            transcription_status=TranscriptionStatus(record.transcription_status),
            transcription_model=record.transcription_model,
            transcription_error=record.transcription_error,
            target_language=record.target_language,
        )


class TranscriptRepository:
    """Persist ordered transcript segments."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def list_for_project(self, project_id: str) -> list[TranscriptSegment]:
        with self._database.session() as session:
            records = session.scalars(
                select(TranscriptSegmentRecord)
                .where(TranscriptSegmentRecord.project_id == project_id)
                .order_by(TranscriptSegmentRecord.position)
            ).all()
            return [self._to_domain(record) for record in records]

    def replace(self, project_id: str, segments: list[TranscriptSegment]) -> None:
        with self._database.session() as session:
            session.execute(
                delete(TranscriptSegmentRecord).where(
                    TranscriptSegmentRecord.project_id == project_id
                )
            )
            session.add_all(
                TranscriptSegmentRecord(
                    id=segment.id,
                    project_id=segment.project_id,
                    position=segment.position,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    text=segment.text,
                    source_revision=segment.source_revision,
                )
                for segment in segments
            )

    def delete(self, project_id: str) -> None:
        self.replace(project_id, [])

    def update_texts(self, project_id: str, changes: dict[str, str]) -> list[TranscriptSegment]:
        """Atomically update text and increment revisions only for real changes."""
        if not changes:
            return self.list_for_project(project_id)
        with self._database.session() as session:
            records = session.scalars(
                select(TranscriptSegmentRecord).where(
                    TranscriptSegmentRecord.project_id == project_id,
                    TranscriptSegmentRecord.id.in_(changes),
                )
            ).all()
            if len(records) != len(changes):
                raise LookupError("One or more transcript segments no longer exist.")
            for record in records:
                new_text = changes[record.id]
                if record.text != new_text:
                    record.text = new_text
                    record.source_revision += 1
            all_records = session.scalars(
                select(TranscriptSegmentRecord)
                .where(TranscriptSegmentRecord.project_id == project_id)
                .order_by(TranscriptSegmentRecord.position)
            ).all()
            return [self._to_domain(record) for record in all_records]

    @staticmethod
    def _to_domain(record: TranscriptSegmentRecord) -> TranscriptSegment:
        return TranscriptSegment(
            id=record.id,
            project_id=record.project_id,
            position=record.position,
            start_ms=record.start_ms,
            end_ms=record.end_ms,
            text=record.text,
            source_revision=record.source_revision,
        )


class GlossaryRepository:
    """Persist project terminology constraints."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def list_for_project(self, project_id: str) -> list[GlossaryEntry]:
        with self._database.session() as session:
            records = session.scalars(
                select(GlossaryEntryRecord)
                .where(GlossaryEntryRecord.project_id == project_id)
                .order_by(GlossaryEntryRecord.source_term_key)
            ).all()
            return [self._to_domain(record) for record in records]

    def add(self, entry: GlossaryEntry) -> None:
        with self._database.session() as session:
            duplicate = session.scalar(
                select(GlossaryEntryRecord).where(
                    GlossaryEntryRecord.project_id == entry.project_id,
                    GlossaryEntryRecord.source_term_key == entry.source_term.casefold(),
                )
            )
            if duplicate is not None:
                raise ValueError("That source term already exists in this glossary.")
            session.add(
                GlossaryEntryRecord(
                    id=entry.id,
                    project_id=entry.project_id,
                    source_term=entry.source_term,
                    source_term_key=entry.source_term.casefold(),
                    target_term=entry.target_term,
                )
            )

    def update(self, entry: GlossaryEntry) -> None:
        with self._database.session() as session:
            record = session.get(GlossaryEntryRecord, entry.id)
            if record is None or record.project_id != entry.project_id:
                raise LookupError(entry.id)
            duplicate = session.scalar(
                select(GlossaryEntryRecord).where(
                    GlossaryEntryRecord.project_id == entry.project_id,
                    GlossaryEntryRecord.source_term_key == entry.source_term.casefold(),
                    GlossaryEntryRecord.id != entry.id,
                )
            )
            if duplicate is not None:
                raise ValueError("That source term already exists in this glossary.")
            record.source_term = entry.source_term
            record.source_term_key = entry.source_term.casefold()
            record.target_term = entry.target_term

    def delete(self, project_id: str, entry_id: str) -> None:
        with self._database.session() as session:
            record = session.get(GlossaryEntryRecord, entry_id)
            if record is None or record.project_id != project_id:
                raise LookupError(entry_id)
            session.delete(record)

    @staticmethod
    def _to_domain(record: GlossaryEntryRecord) -> GlossaryEntry:
        return GlossaryEntry(
            id=record.id,
            project_id=record.project_id,
            source_term=record.source_term,
            target_term=record.target_term,
        )
