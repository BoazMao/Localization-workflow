"""Application bootstrap."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

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
from localization_workflow.infrastructure.media_tools import (
    MediaToolPaths,
    MediaToolSettingsStore,
    discover_media_tools,
)
from localization_workflow.infrastructure.models import ManagedWhisperModels
from localization_workflow.providers.transcription import ConstMeWhisperProvider
from localization_workflow.providers.translation import OpenAITranslationProvider
from localization_workflow.ui.main_window import MainWindow
from localization_workflow.ui.media_tool_setup import MediaToolSetupDialog


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


def environment_file_path() -> Path:
    """Locate portable configuration beside the executable or source checkout."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / ".env"
    return Path(__file__).resolve().parents[2] / ".env"


def ensure_media_tools(
    settings: AppSettings, environment_file: Path
) -> MediaToolPaths | None:
    """Detect media tools or collect them through first-run desktop setup."""
    detected = discover_media_tools(settings.ffmpeg_path, settings.ffprobe_path)
    if detected is None:
        dialog = MediaToolSetupDialog(settings.ffmpeg_path, settings.ffprobe_path)
        dialog.exec()
        detected = dialog.media_tools
    if detected is None:
        return None
    MediaToolSettingsStore(environment_file).save(detected)
    return detected


def _run(app: QApplication) -> int:
    environment_file = environment_file_path()
    settings = AppSettings(_env_file=environment_file)  # type: ignore[call-arg]
    media_tools = ensure_media_tools(settings, environment_file)
    if media_tools is None:
        return 0
    paths = AppPaths.discover(settings.data_dir)
    paths.ensure_directories()

    database = Database(paths.database)
    database.migrate()
    repository = ProjectRepository(database)
    transcripts = TranscriptRepository(database)
    glossary_repository = GlossaryRepository(database)
    translation_repository = TranslationRepository(database)
    media_store = ManagedMediaStore(paths.media, FFprobeMediaProbe(media_tools.ffprobe))
    audio_processor = FFmpegAudioProcessor(paths.derived, media_tools.ffmpeg)
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
        api_settings=OpenAISettingsStore(environment_file),
        initial_api_key=settings.openai_api_key or "",
        initial_model=settings.openai_translation_model,
        initial_base_url=settings.openai_base_url or "",
    )
    window.show()
    return app.exec()


def main(argv: Sequence[str] | None = None) -> int:
    """Start the native desktop application with visible startup failure recovery."""
    app = create_application(argv)
    try:
        return _run(app)
    except Exception as error:
        QMessageBox.critical(
            None,
            "Localization Workflow could not start",
            "The application could not start. Check the local configuration and try again."
            f"\n\nDetails: {error}",
        )
        return 1
