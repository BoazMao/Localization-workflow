"""Application bootstrap."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtWidgets import QApplication

from localization_workflow.application.glossary import GlossaryService
from localization_workflow.application.projects import ProjectService
from localization_workflow.application.transcription import TranscriptionService
from localization_workflow.application.translation import TranslationService
from localization_workflow.core.paths import AppPaths
from localization_workflow.core.settings import AppSettings
from localization_workflow.infrastructure.api_settings import OpenAISettingsStore
from localization_workflow.infrastructure.audio import FFmpegAudioProcessor
from localization_workflow.infrastructure.database import (
    Database,
    GlossaryRepository,
    ProjectRepository,
    TranscriptRepository,
    TranslationRepository,
)
from localization_workflow.infrastructure.instructions import TranslationInstructionsStore
from localization_workflow.infrastructure.media import FFprobeMediaProbe, ManagedMediaStore
from localization_workflow.infrastructure.models import ManagedWhisperModels
from localization_workflow.providers.transcription import ConstMeWhisperProvider
from localization_workflow.providers.translation import OpenAITranslationProvider
from localization_workflow.ui.main_window import MainWindow


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    """Create and configure the Qt application."""
    app = QApplication.instance()
    if app is not None:
        if not isinstance(app, QApplication):
            msg = "A non-GUI Qt application already exists in this process."
            raise RuntimeError(msg)
        return app

    qt_app = QApplication(list(argv) if argv is not None else sys.argv)
    qt_app.setApplicationName("Localization Workflow")
    qt_app.setApplicationDisplayName("Localization Workflow")
    qt_app.setOrganizationName("Localization Workflow")
    return qt_app


def main(argv: Sequence[str] | None = None) -> int:
    """Start the native desktop application."""
    app = create_application(argv)
    settings = AppSettings()
    paths = AppPaths.discover(settings.data_dir)
    paths.ensure_directories()

    database = Database(paths.database)
    database.migrate()
    repository = ProjectRepository(database)
    transcripts = TranscriptRepository(database)
    glossary_repository = GlossaryRepository(database)
    translation_repository = TranslationRepository(database)
    media_store = ManagedMediaStore(paths.media, FFprobeMediaProbe(settings.ffprobe_path))
    if settings.ffmpeg_path is None:
        msg = "FFMPEG_PATH must be configured before starting the application."
        raise RuntimeError(msg)
    audio_processor = FFmpegAudioProcessor(paths.derived, settings.ffmpeg_path)
    projects = ProjectService(repository, media_store, audio_processor, transcripts)
    models = ManagedWhisperModels(paths.models, settings.whisper_model_path)
    speech_provider = ConstMeWhisperProvider(
        models.selected(),
        settings.whisper_cli_path,
    )
    transcription = TranscriptionService(repository, transcripts, speech_provider, models)
    glossary = GlossaryService(repository, glossary_repository)
    instruction_store = TranslationInstructionsStore(paths.translation_agents)
    instruction_store.ensure_exists()
    translation_provider = OpenAITranslationProvider(
        settings.openai_api_key, settings.openai_translation_model, settings.openai_base_url
    )
    translation = TranslationService(
        repository,
        transcripts,
        translation_repository,
        glossary,
        translation_provider,
        instruction_store,
    )

    window = MainWindow(
        paths=paths,
        projects=projects,
        transcription=transcription,
        glossary=glossary,
        translation=translation,
        api_settings=OpenAISettingsStore(Path(".env")),
        initial_api_key=settings.openai_api_key or "",
        initial_model=settings.openai_translation_model,
        initial_base_url=settings.openai_base_url or "",
    )
    window.show()
    return app.exec()
