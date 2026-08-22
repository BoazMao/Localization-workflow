"""Project library and media workspace window."""

from __future__ import annotations

from pathlib import Path
from threading import Event
from time import perf_counter

from PySide6.QtCore import QSignalBlocker, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from localization_workflow.application.glossary import GlossaryService
from localization_workflow.application.projects import ProjectService
from localization_workflow.application.transcription import TranscriptionService
from localization_workflow.application.translation import TranslationService
from localization_workflow.core.paths import AppPaths
from localization_workflow.domain.projects import (
    AudioStatus,
    Project,
    ProjectStatus,
    SegmentTranslation,
    TranscriptionStatus,
    TranscriptSegment,
    TranslationStatus,
)
from localization_workflow.infrastructure.api_settings import OpenAISettings, OpenAISettingsStore
from localization_workflow.infrastructure.media import SUPPORTED_MEDIA_EXTENSIONS
from localization_workflow.ui.media_player import MediaPlayerWidget, format_milliseconds

LANGUAGE_OPTIONS = ("English", "Simplified Chinese")
OPENAI_MODEL_OPTIONS = (
    ("GPT-5.6 Terra — balanced (recommended)", "gpt-5.6-terra"),
    ("GPT-5.6 Sol — highest quality", "gpt-5.6-sol"),
    ("GPT-5.5 — high-capability reasoning", "gpt-5.5"),
    ("GPT-5.4 — reliable general-purpose", "gpt-5.4"),
    ("GPT-5.3 Codex Spark — economical", "gpt-5.3-codex-spark"),
    ("Claude Fable 5", "claude-fable-5"),
    ("Claude Haiku 4.5", "claude-haiku-4-5"),
    ("Claude Haiku 4.5 (2025-10-01)", "claude-haiku-4-5-20251001"),
    ("Claude Opus 4.5", "claude-opus-4-5"),
    ("Claude Opus 4.6", "claude-opus-4-6"),
    ("Claude Opus 4.7", "claude-opus-4-7"),
    ("Claude Opus 4.8", "claude-opus-4-8"),
)


class ImportWorker(QThread):
    """Copy and inspect media without blocking the Qt UI thread."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, service: ProjectService, project_id: str, source: Path) -> None:
        super().__init__()
        self._service = service
        self._project_id = project_id
        self._source = source

    def run(self) -> None:
        try:
            self.completed.emit(self._service.import_media(self._project_id, self._source))
        except Exception as error:
            self.failed.emit(str(error))


class AudioWorker(QThread):
    """Prepare transcription audio without blocking the UI thread."""

    completed = Signal(object)
    failed = Signal(str)
    progress_changed = Signal(int)

    def __init__(self, service: ProjectService, project_id: str) -> None:
        super().__init__()
        self._service = service
        self._project_id = project_id
        self._cancel = Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            project = self._service.prepare_audio(
                self._project_id, self.progress_changed.emit, self._cancel
            )
            self.completed.emit(project)
        except Exception as error:
            self.failed.emit(str(error))


class TranscriptionWorker(QThread):
    """Run local Whisper transcription without blocking the Qt UI thread."""

    completed = Signal(object)
    failed = Signal(str)
    progress_changed = Signal(int)

    def __init__(self, service: TranscriptionService, project_id: str) -> None:
        super().__init__()
        self._service = service
        self._project_id = project_id
        self._cancel = Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            project = self._service.transcribe(
                self._project_id, self.progress_changed.emit, self._cancel
            )
            self.completed.emit(project)
        except Exception as error:
            self.failed.emit(str(error))


class TranslationWorker(QThread):
    """Translate transcript segments without blocking the desktop interface."""

    completed = Signal(object)
    failed = Signal(str)
    progress_changed = Signal(int)

    def __init__(
        self,
        service: TranslationService,
        project_id: str,
        segment_ids: set[str] | None = None,
        retry_failed: bool = False,
    ) -> None:
        super().__init__()
        self._service = service
        self._project_id = project_id
        self._segment_ids = segment_ids
        self._retry_failed = retry_failed
        self._cancel = Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            if self._retry_failed:
                result = self._service.retry_failed(
                    self._project_id, self.progress_changed.emit, self._cancel
                )
            else:
                result = self._service.translate(
                    self._project_id,
                    self._segment_ids,
                    self.progress_changed.emit,
                    self._cancel,
                )
            self.completed.emit(result)
        except Exception as error:
            self.failed.emit(str(error))


class MainWindow(QMainWindow):
    """Desktop project library and media workspace."""

    def __init__(
        self,
        paths: AppPaths,
        projects: ProjectService,
        transcription: TranscriptionService,
        glossary: GlossaryService,
        translation: TranslationService,
        api_settings: OpenAISettingsStore,
        initial_api_key: str,
        initial_model: str,
        initial_base_url: str,
    ) -> None:
        super().__init__()
        self._paths = paths
        self._projects = projects
        self._transcription = transcription
        self._glossary = glossary
        self._translation = translation
        self._api_settings = api_settings
        self._current_project: Project | None = None
        self._import_worker: ImportWorker | None = None
        self._audio_worker: AudioWorker | None = None
        self._transcription_worker: TranscriptionWorker | None = None
        self._translation_worker: TranslationWorker | None = None
        self._translation_started_at: float | None = None
        self._translation_timer = QTimer(self)
        self._translation_timer.setInterval(100)
        self._translation_timer.timeout.connect(self._update_translation_elapsed)
        self._dirty_segments: dict[str, str] = {}
        self._dirty_translations: dict[str, str] = {}
        self._initial_api_key = initial_api_key
        self._initial_model = initial_model
        self._initial_base_url = initial_base_url
        self.setWindowTitle("Localization Workflow")
        self.setMinimumSize(1024, 700)
        self.resize(1280, 820)
        self._build_actions()
        self._build_menu()
        self._build_pages()
        self._build_status_bar()
        self._refresh_projects()

    def _build_actions(self) -> None:
        self._quit_action = QAction("Quit", self)
        self._quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self._quit_action.triggered.connect(self.close)
        self._about_action = QAction("About", self)
        self._about_action.triggered.connect(self._show_about)
        self._api_settings_action = QAction("AI model API settings…", self)
        self._api_settings_action.triggered.connect(self._show_api_settings)
        self._instructions_action = QAction("Translation instructions…", self)
        self._instructions_action.triggered.connect(self._show_translation_instructions)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self._quit_action)
        settings_menu = self.menuBar().addMenu("&Settings")
        settings_menu.addAction(self._api_settings_action)
        settings_menu.addAction(self._instructions_action)
        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self._about_action)

    def _build_pages(self) -> None:
        self._pages = QStackedWidget(self)
        self._library_page = self._build_library_page()
        self._workspace_page = self._build_workspace_page()
        self._pages.addWidget(self._library_page)
        self._pages.addWidget(self._workspace_page)
        self.setCentralWidget(self._pages)

    def _build_library_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(42, 34, 42, 34)
        heading = QLabel("Your localization projects")
        heading.setStyleSheet("font-size: 28px; font-weight: 650;")
        subtitle = QLabel("Create a project, then import a video or audio file to begin.")
        subtitle.setStyleSheet("font-size: 15px; color: #5f6368;")
        self._project_list = QListWidget()
        self._project_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._project_list.itemDoubleClicked.connect(lambda _item: self._open_selected())

        buttons = QHBoxLayout()
        new_button = QPushButton("New project")
        new_button.clicked.connect(self._create_project)
        open_button = QPushButton("Open")
        open_button.clicked.connect(self._open_selected)
        rename_button = QPushButton("Rename")
        rename_button.clicked.connect(self._rename_selected)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self._delete_selected)
        for button in (new_button, open_button, rename_button, delete_button):
            buttons.addWidget(button)
        buttons.addStretch()

        layout.addWidget(heading)
        layout.addWidget(subtitle)
        layout.addSpacing(10)
        layout.addWidget(self._project_list, 1)
        layout.addLayout(buttons)
        return page

    def _build_workspace_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        top = QHBoxLayout()
        back_button = QPushButton("← Projects")
        back_button.clicked.connect(self._show_library)
        self._project_heading = QLabel()
        self._project_heading.setStyleSheet("font-size: 24px; font-weight: 650;")
        self._import_button = QPushButton("Import media")
        self._import_button.clicked.connect(self._choose_media)
        top.addWidget(back_button)
        top.addWidget(self._project_heading, 1)
        top.addWidget(self._import_button)

        self._media_details = QLabel("No media imported yet.")
        self._media_details.setWordWrap(True)
        self._media_details.setStyleSheet("color: #5f6368;")
        self._player = MediaPlayerWidget()
        self._player.load(None)
        audio_controls = QHBoxLayout()
        self._prepare_audio_button = QPushButton("Prepare audio")
        self._prepare_audio_button.clicked.connect(self._prepare_audio)
        self._cancel_audio_button = QPushButton("Cancel")
        self._cancel_audio_button.clicked.connect(self._cancel_audio)
        self._cancel_audio_button.setVisible(False)
        self._audio_progress = QProgressBar()
        self._audio_progress.setRange(0, 100)
        self._audio_progress.setVisible(False)
        self._audio_status = QLabel("Audio not prepared")
        audio_controls.addWidget(self._prepare_audio_button)
        audio_controls.addWidget(self._cancel_audio_button)
        audio_controls.addWidget(self._audio_progress, 1)
        audio_controls.addWidget(self._audio_status)

        transcription_controls = QHBoxLayout()
        self._transcribe_button = QPushButton("Transcribe with Whisper")
        self._transcribe_button.clicked.connect(self._transcribe)
        self._cancel_transcription_button = QPushButton("Cancel")
        self._cancel_transcription_button.clicked.connect(self._cancel_transcription)
        self._cancel_transcription_button.setVisible(False)
        self._transcription_progress = QProgressBar()
        self._transcription_progress.setRange(0, 100)
        self._transcription_progress.setVisible(False)
        self._transcription_status = QLabel("Not transcribed")
        transcription_controls.addWidget(self._transcribe_button)
        transcription_controls.addWidget(self._cancel_transcription_button)
        transcription_controls.addWidget(self._transcription_progress, 1)
        transcription_controls.addWidget(self._transcription_status)

        model_controls = QHBoxLayout()
        self._model_label = QLabel(f"Whisper model: {self._transcription.model_name}")
        self._model_label.setStyleSheet("color: #5f6368;")
        self._import_model_button = QPushButton("Select existing model")
        self._import_model_button.clicked.connect(self._choose_model)
        model_controls.addWidget(self._model_label, 1)
        model_controls.addWidget(self._import_model_button)
        whisper_wordbank_controls = QHBoxLayout()
        self._use_whisper_wordbank = QCheckBox("Use wordbank")
        self._use_whisper_wordbank.toggled.connect(self._toggle_whisper_wordbank)
        edit_whisper_wordbank_button = QPushButton("Edit Whisper wordbank")
        edit_whisper_wordbank_button.clicked.connect(self._show_whisper_wordbank)
        whisper_wordbank_controls.addWidget(self._use_whisper_wordbank)
        whisper_wordbank_controls.addWidget(edit_whisper_wordbank_button)
        whisper_wordbank_controls.addStretch()
        self._transcript_table = QTableWidget(0, 3)
        self._transcript_table.setHorizontalHeaderLabels(("Time", "Source transcript", "Rev"))
        header = self._transcript_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._transcript_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self._transcript_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._transcript_table.itemChanged.connect(self._on_transcript_changed)
        self._transcript_table.cellClicked.connect(self._seek_to_segment)
        review_controls = QHBoxLayout()
        self._save_transcript_button = QPushButton("Save transcript changes")
        self._save_transcript_button.setEnabled(False)
        self._save_transcript_button.clicked.connect(self._save_transcript)
        self._save_status = QLabel("All changes saved")
        self._save_status.setStyleSheet("color: #5f6368;")
        review_controls.addWidget(self._save_transcript_button)
        review_controls.addWidget(self._save_status)
        review_controls.addStretch()

        transcript_page = QWidget()
        transcript_layout = QVBoxLayout(transcript_page)
        transcript_layout.setContentsMargins(0, 8, 0, 0)
        transcript_layout.addLayout(review_controls)
        transcript_layout.addWidget(self._transcript_table)

        glossary_page = QWidget()
        glossary_layout = QVBoxLayout(glossary_page)
        glossary_layout.setContentsMargins(0, 8, 0, 0)
        target_controls = QHBoxLayout()
        self._target_language_label = QLabel("Target language: Not set")
        set_target_button = QPushButton("Set target language")
        set_target_button.clicked.connect(self._set_target_language)
        target_controls.addWidget(self._target_language_label)
        target_controls.addWidget(set_target_button)
        target_controls.addStretch()
        wordbank_help = QLabel(
            "Paste terminology, examples, style notes, alternatives, or any other natural-"
            "language context. The AI model receives the complete wordbank for every translation."
        )
        wordbank_help.setWordWrap(True)
        wordbank_help.setStyleSheet("color: #5f6368;")
        self._wordbank_editor = QPlainTextEdit()
        self._wordbank_editor.setPlaceholderText(
            "Example:\n1. 转点: Rotate\n2. 守点: Hold the spot\n3. 进圈: Get into the ring/zone"
        )
        save_wordbank_button = QPushButton("Save wordbank")
        save_wordbank_button.clicked.connect(self._save_wordbank)
        glossary_layout.addLayout(target_controls)
        glossary_layout.addWidget(wordbank_help)
        glossary_layout.addWidget(self._wordbank_editor, 1)
        glossary_layout.addWidget(save_wordbank_button)

        translation_page = QWidget()
        translation_layout = QVBoxLayout(translation_page)
        translation_layout.setContentsMargins(0, 8, 0, 0)
        provider_row = QHBoxLayout()
        self._provider_label = QLabel(f"AI translation: {self._translation.provider_label}")
        self._provider_label.setStyleSheet("color: #5f6368;")
        provider_row.addWidget(self._provider_label)
        provider_row.addStretch()
        translation_controls = QHBoxLayout()
        self._translate_all_button = QPushButton("Translate all")
        self._translate_all_button.clicked.connect(self._translate_all)
        self._translate_selected_button = QPushButton("Translate selected")
        self._translate_selected_button.clicked.connect(self._translate_selected)
        self._retry_translation_button = QPushButton("Retry failed")
        self._retry_translation_button.clicked.connect(self._retry_failed_translations)
        self._save_translation_button = QPushButton("Save edits")
        self._save_translation_button.clicked.connect(self._save_translation_edits)
        self._save_translation_button.setEnabled(False)
        self._mark_reviewed_button = QPushButton("Mark reviewed")
        self._mark_reviewed_button.clicked.connect(
            lambda: self._mark_translation_status(TranslationStatus.REVIEWED)
        )
        self._approve_translation_button = QPushButton("Approve")
        self._approve_translation_button.clicked.connect(
            lambda: self._mark_translation_status(TranslationStatus.APPROVED)
        )
        self._export_translation_button = QPushButton("Export translated SRT")
        self._export_translation_button.clicked.connect(self._export_translated_srt)
        self._cancel_translation_button = QPushButton("Cancel")
        self._cancel_translation_button.clicked.connect(self._cancel_translation)
        self._cancel_translation_button.setVisible(False)
        self._translation_status_detail = QLabel("Ready")
        self._translation_status_detail.setStyleSheet("color: #5f6368;")
        for button in (
            self._translate_all_button,
            self._translate_selected_button,
            self._retry_translation_button,
            self._save_translation_button,
            self._mark_reviewed_button,
            self._approve_translation_button,
            self._export_translation_button,
            self._cancel_translation_button,
        ):
            translation_controls.addWidget(button)
        translation_controls.addWidget(self._translation_status_detail, 1)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Show"))
        self._translation_filter = QComboBox()
        for label, value in (
            ("All", "all"),
            ("Not translated", "missing"),
            ("Draft", TranslationStatus.DRAFT.value),
            ("Reviewed", TranslationStatus.REVIEWED.value),
            ("Approved", TranslationStatus.APPROVED.value),
            ("Outdated", TranslationStatus.OUTDATED.value),
            ("Failed", TranslationStatus.FAILED.value),
        ):
            self._translation_filter.addItem(label, value)
        self._translation_filter.currentIndexChanged.connect(self._apply_translation_filter)
        filter_row.addWidget(self._translation_filter)
        filter_row.addStretch()
        self._translation_table = QTableWidget(0, 4)
        self._translation_table.setHorizontalHeaderLabels(
            ("Time", "Source", "Translation", "Status")
        )
        translation_header = self._translation_table.horizontalHeader()
        translation_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        translation_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        translation_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        translation_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._translation_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._translation_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._translation_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self._translation_table.itemChanged.connect(self._on_translation_changed)
        self._translation_table.cellClicked.connect(self._seek_to_translation_segment)
        translation_layout.addLayout(provider_row)
        translation_layout.addLayout(translation_controls)
        translation_layout.addLayout(filter_row)
        translation_layout.addWidget(self._translation_table, 1)

        workspace_tabs = QTabWidget()
        workspace_tabs.addTab(transcript_page, "Transcript")
        workspace_tabs.addTab(glossary_page, "Wordbank")
        workspace_tabs.addTab(translation_page, "Translation")

        media_tools = QWidget()
        media_tools_layout = QVBoxLayout(media_tools)
        media_tools_layout.setContentsMargins(12, 0, 0, 0)
        audio_heading = QLabel("Transcription audio")
        audio_heading.setStyleSheet("font-weight: 600;")
        model_heading = QLabel("Whisper model")
        model_heading.setStyleSheet("font-weight: 600;")
        transcription_heading = QLabel("Transcription")
        transcription_heading.setStyleSheet("font-weight: 600;")
        wordbank_heading = QLabel("Recognition vocabulary")
        wordbank_heading.setStyleSheet("font-weight: 600;")
        media_tools_layout.addWidget(audio_heading)
        media_tools_layout.addLayout(audio_controls)
        media_tools_layout.addSpacing(8)
        media_tools_layout.addWidget(model_heading)
        media_tools_layout.addLayout(model_controls)
        media_tools_layout.addSpacing(8)
        media_tools_layout.addWidget(wordbank_heading)
        media_tools_layout.addLayout(whisper_wordbank_controls)
        media_tools_layout.addSpacing(8)
        media_tools_layout.addWidget(transcription_heading)
        media_tools_layout.addLayout(transcription_controls)
        media_tools_layout.addStretch()

        media_area = QHBoxLayout()
        media_area.setSpacing(12)
        media_area.addWidget(self._player, 3)
        media_area.addWidget(media_tools, 2)

        layout.addLayout(top)
        layout.addWidget(self._media_details)
        layout.addLayout(media_area)
        layout.addWidget(workspace_tabs, 1)
        return page

    def _build_status_bar(self) -> None:
        bar = QStatusBar(self)
        bar.showMessage(f"Local data: {self._paths.data}")
        self.setStatusBar(bar)

    def _refresh_projects(self, select_id: str | None = None) -> None:
        self._project_list.clear()
        for project in self._projects.list():
            status = "Media ready" if project.status == ProjectStatus.MEDIA_READY else "No media"
            item = QListWidgetItem(f"{project.name}\n{project.source_language} · {status}")
            item.setData(Qt.ItemDataRole.UserRole, project.id)
            self._project_list.addItem(item)
            if project.id == select_id:
                self._project_list.setCurrentItem(item)

    def _selected_id(self) -> str | None:
        item = self._project_list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _create_project(self) -> None:
        name, accepted = QInputDialog.getText(self, "New project", "Project name")
        if not accepted:
            return
        language, accepted = QInputDialog.getItem(
            self,
            "Source language",
            "Source language",
            LANGUAGE_OPTIONS,
            0,
            False,
        )
        if not accepted:
            return
        try:
            project = self._projects.create(name, language)
        except ValueError as error:
            QMessageBox.warning(self, "Could not create project", str(error))
            return
        self._refresh_projects(project.id)
        self._open_project(project)

    def _open_selected(self) -> None:
        project_id = self._selected_id()
        if project_id:
            self._open_project(self._projects.get(project_id))

    def _open_project(self, project: Project) -> None:
        self._current_project = project
        self._project_heading.setText(project.name)
        self._update_media_display(project)
        self._update_transcription_display(project)
        self._refresh_glossary(project)
        self._refresh_whisper_wordbank(project)
        self._refresh_translations(project)
        self._pages.setCurrentWidget(self._workspace_page)

    def _show_library(self) -> None:
        if not self._confirm_discard_edits():
            return
        self._player.load(None)
        self._refresh_projects(self._current_project.id if self._current_project else None)
        self._pages.setCurrentWidget(self._library_page)

    def _rename_selected(self) -> None:
        project_id = self._selected_id()
        if not project_id:
            return
        project = self._projects.get(project_id)
        name, accepted = QInputDialog.getText(
            self, "Rename project", "Project name", text=project.name
        )
        if accepted:
            try:
                updated = self._projects.rename(project_id, name)
            except ValueError as error:
                QMessageBox.warning(self, "Could not rename project", str(error))
                return
            self._refresh_projects(updated.id)

    def _delete_selected(self) -> None:
        project_id = self._selected_id()
        if not project_id:
            return
        project = self._projects.get(project_id)
        choice = QMessageBox.question(
            self,
            "Delete project",
            f'Delete "{project.name}" and its managed media? This cannot be undone.',
        )
        if choice == QMessageBox.StandardButton.Yes:
            self._projects.delete(project_id)
            self._refresh_projects()

    def _choose_media(self) -> None:
        if self._current_project is None or self._import_worker is not None:
            return
        if not self._confirm_discard_edits():
            return
        extensions = " ".join(f"*{extension}" for extension in sorted(SUPPORTED_MEDIA_EXTENSIONS))
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import video or audio", "", f"Media files ({extensions});;All files (*)"
        )
        if not filename:
            return
        self._import_button.setEnabled(False)
        self.statusBar().showMessage("Copying and inspecting media…")
        worker = ImportWorker(self._projects, self._current_project.id, Path(filename))
        worker.completed.connect(self._on_import_completed)
        worker.failed.connect(self._on_import_failed)
        worker.finished.connect(self._on_import_finished)
        self._import_worker = worker
        worker.start()

    def _on_import_completed(self, value: object) -> None:
        if not isinstance(value, Project):
            self._on_import_failed("Unexpected import result.")
            return
        self._current_project = value
        self._update_media_display(value)
        self._update_transcription_display(value)
        self.statusBar().showMessage("Media imported successfully.", 5000)

    def _on_import_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Media import failed", message)
        self.statusBar().showMessage("Media import failed.", 5000)

    def _on_import_finished(self) -> None:
        self._import_button.setEnabled(True)
        if self._import_worker:
            self._import_worker.deleteLater()
        self._import_worker = None

    def _prepare_audio(self) -> None:
        if self._current_project is None or self._audio_worker is not None:
            return
        if not self._current_project.media_path:
            QMessageBox.information(self, "Prepare audio", "Import media first.")
            return
        worker = AudioWorker(self._projects, self._current_project.id)
        worker.progress_changed.connect(self._audio_progress.setValue)
        worker.completed.connect(self._on_audio_completed)
        worker.failed.connect(self._on_audio_failed)
        worker.finished.connect(self._on_audio_finished)
        self._audio_worker = worker
        self._prepare_audio_button.setEnabled(False)
        self._cancel_audio_button.setVisible(True)
        self._audio_progress.setValue(0)
        self._audio_progress.setVisible(True)
        self._audio_status.setText("Preparing mono 16 kHz WAV…")
        worker.start()

    def _cancel_audio(self) -> None:
        if self._audio_worker:
            self._cancel_audio_button.setEnabled(False)
            self._audio_status.setText("Cancelling…")
            self._audio_worker.cancel()

    def _on_audio_completed(self, value: object) -> None:
        if isinstance(value, Project):
            self._current_project = value
            self._update_audio_display(value)
            self._update_transcription_display(value)
            self.statusBar().showMessage("Transcription audio is ready.", 5000)

    def _on_audio_failed(self, message: str) -> None:
        if self._current_project:
            self._current_project = self._projects.get(self._current_project.id)
            self._update_audio_display(self._current_project)
        if "cancel" not in message.lower():
            QMessageBox.critical(self, "Audio preparation failed", message)

    def _on_audio_finished(self) -> None:
        self._prepare_audio_button.setEnabled(True)
        self._cancel_audio_button.setEnabled(True)
        self._cancel_audio_button.setVisible(False)
        self._audio_progress.setVisible(False)
        if self._audio_worker:
            self._audio_worker.deleteLater()
        self._audio_worker = None

    def _transcribe(self) -> None:
        if self._current_project is None or self._transcription_worker is not None:
            return
        if not self._confirm_discard_edits():
            return
        if self._current_project.audio_status != AudioStatus.READY:
            QMessageBox.information(self, "Transcribe", "Prepare transcription audio first.")
            return
        if self._current_project.source_language.casefold() == "auto-detect":
            QMessageBox.information(
                self,
                "Choose source language",
                "Const-me/Whisper requires the spoken source language. Create this project "
                "with an explicit language before transcribing.",
            )
            return
        worker = TranscriptionWorker(self._transcription, self._current_project.id)
        worker.progress_changed.connect(self._transcription_progress.setValue)
        worker.completed.connect(self._on_transcription_completed)
        worker.failed.connect(self._on_transcription_failed)
        worker.finished.connect(self._on_transcription_finished)
        self._transcription_worker = worker
        self._transcribe_button.setEnabled(False)
        self._cancel_transcription_button.setVisible(True)
        self._transcription_progress.setValue(0)
        self._transcription_progress.setVisible(True)
        self._transcription_status.setText("Transcribing locally…")
        worker.start()

    def _choose_model(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select existing Whisper model",
            "",
            "Whisper models (*.bin);;All files (*)",
        )
        if not filename:
            return
        try:
            selected = self._transcription.select_model(Path(filename))
        except Exception as error:
            QMessageBox.critical(self, "Model selection failed", str(error))
            self.statusBar().showMessage("Whisper model selection failed.", 5000)
            return
        self._model_label.setText(f"Whisper model: {self._transcription.model_name}")
        self.statusBar().showMessage(f"Whisper model selected: {selected.name}", 5000)

    def _refresh_whisper_wordbank(self, project: Project) -> None:
        blocker = QSignalBlocker(self._use_whisper_wordbank)
        self._use_whisper_wordbank.setChecked(project.whisper_wordbank_enabled)
        self._use_whisper_wordbank.setToolTip(
            f"{len(project.whisper_wordbank)} character(s) saved"
            if project.whisper_wordbank
            else "No recognition vocabulary saved"
        )
        del blocker

    def _toggle_whisper_wordbank(self, enabled: bool) -> None:
        if self._current_project is None:
            return
        self._current_project = self._transcription.configure_wordbank(
            self._current_project.id,
            self._current_project.whisper_wordbank,
            enabled,
        )
        self._refresh_whisper_wordbank(self._current_project)
        state = "enabled" if enabled else "disabled"
        self.statusBar().showMessage(f"Whisper wordbank {state}.", 5000)

    def _show_whisper_wordbank(self) -> None:
        if self._current_project is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Whisper recognition wordbank")
        dialog.resize(680, 480)
        layout = QVBoxLayout(dialog)
        help_text = QLabel(
            "Enter source-language names, terminology, and phrases Whisper commonly mishears. "
            "Keep this concise; it biases recognition but does not force exact matches."
        )
        help_text.setWordWrap(True)
        self._whisper_wordbank_editor = QPlainTextEdit()
        self._whisper_wordbank_editor.setPlainText(self._current_project.whisper_wordbank)
        self._whisper_wordbank_editor.setPlaceholderText(
            "Apex Legends, ImperialHal, Verhulst, Genburten, Gibraltar, Shield Battery"
        )
        buttons = QHBoxLayout()
        save_button = QPushButton("Save wordbank")
        save_button.clicked.connect(self._save_whisper_wordbank)
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        buttons.addWidget(save_button)
        buttons.addWidget(close_button)
        buttons.addStretch()
        layout.addWidget(help_text)
        layout.addWidget(self._whisper_wordbank_editor, 1)
        layout.addLayout(buttons)
        dialog.exec()

    def _save_whisper_wordbank(self) -> None:
        if self._current_project is None:
            return
        self._current_project = self._transcription.configure_wordbank(
            self._current_project.id,
            self._whisper_wordbank_editor.toPlainText(),
            self._use_whisper_wordbank.isChecked(),
        )
        self._refresh_whisper_wordbank(self._current_project)
        self.statusBar().showMessage("Whisper wordbank saved.", 5000)

    def _cancel_transcription(self) -> None:
        if self._transcription_worker:
            self._cancel_transcription_button.setEnabled(False)
            self._transcription_status.setText("Cancelling…")
            self._transcription_worker.cancel()

    def _on_transcription_completed(self, value: object) -> None:
        if isinstance(value, Project):
            self._current_project = value
            self._update_transcription_display(value)
            self.statusBar().showMessage("Local transcription completed.", 5000)

    def _on_transcription_failed(self, message: str) -> None:
        if self._current_project:
            self._current_project = self._projects.get(self._current_project.id)
            self._update_transcription_display(self._current_project)
        if "cancel" not in message.lower():
            QMessageBox.critical(self, "Transcription failed", message)

    def _on_transcription_finished(self) -> None:
        self._transcribe_button.setEnabled(True)
        self._cancel_transcription_button.setEnabled(True)
        self._cancel_transcription_button.setVisible(False)
        self._transcription_progress.setVisible(False)
        if self._transcription_worker:
            self._transcription_worker.deleteLater()
        self._transcription_worker = None

    def _update_media_display(self, project: Project) -> None:
        if not project.media_path:
            self._media_details.setText("No media imported yet.")
            self._player.load(None)
            self._prepare_audio_button.setEnabled(False)
            self._update_audio_display(project)
            self._update_transcription_display(project)
            return
        self._prepare_audio_button.setEnabled(True)
        resolution = (
            f" · {project.width}x{project.height}" if project.width and project.height else ""
        )
        codecs = " / ".join(value for value in (project.video_codec, project.audio_codec) if value)
        self._media_details.setText(
            f"{project.original_filename} · {format_milliseconds(project.duration_ms or 0)}"
            f"{resolution} · {codecs or 'Unknown codec'}"
        )
        self._player.load(project.media_path)
        self._update_audio_display(project)
        self._update_transcription_display(project)

    def _update_audio_display(self, project: Project) -> None:
        labels = {
            AudioStatus.NOT_PREPARED: "Audio not prepared",
            AudioStatus.PROCESSING: "Audio preparation interrupted",
            AudioStatus.READY: "Mono 16 kHz WAV ready",
            AudioStatus.FAILED: f"Audio failed: {project.audio_error or 'Unknown error'}",
        }
        self._audio_status.setText(labels[project.audio_status])

    def _update_transcription_display(self, project: Project) -> None:
        labels = {
            TranscriptionStatus.NOT_STARTED: "Not transcribed",
            TranscriptionStatus.PROCESSING: "Transcription interrupted",
            TranscriptionStatus.READY: f"Transcript ready · {project.transcription_model}",
            TranscriptionStatus.FAILED: (
                f"Transcription failed: {project.transcription_error or 'Unknown error'}"
            ),
        }
        self._transcription_status.setText(labels[project.transcription_status])
        self._transcribe_button.setEnabled(project.audio_status == AudioStatus.READY)
        segments = self._transcription.list_segments(project.id)
        self._populate_transcript(segments)

    def _populate_transcript(self, segments: list[TranscriptSegment]) -> None:
        blocker = QSignalBlocker(self._transcript_table)
        self._transcript_table.setRowCount(len(segments))
        for row, segment in enumerate(segments):
            timing = (
                f"{format_milliseconds(segment.start_ms)} - {format_milliseconds(segment.end_ms)}"
            )
            timing_item = QTableWidgetItem(timing)
            timing_item.setData(Qt.ItemDataRole.UserRole, segment.start_ms)
            timing_item.setFlags(timing_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            text_item = QTableWidgetItem(segment.text)
            text_item.setData(Qt.ItemDataRole.UserRole, segment.id)
            revision_item = QTableWidgetItem(str(segment.source_revision))
            revision_item.setFlags(revision_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._transcript_table.setItem(row, 0, timing_item)
            self._transcript_table.setItem(row, 1, text_item)
            self._transcript_table.setItem(row, 2, revision_item)
        del blocker
        self._dirty_segments.clear()
        self._save_transcript_button.setEnabled(False)
        self._save_status.setText("All changes saved")

    def _on_transcript_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 1:
            return
        segment_id = item.data(Qt.ItemDataRole.UserRole)
        if segment_id:
            self._dirty_segments[str(segment_id)] = item.text()
            self._save_transcript_button.setEnabled(True)
            self._save_status.setText(f"{len(self._dirty_segments)} unsaved change(s)")

    def _save_transcript(self) -> bool:
        if not self._dirty_segments:
            return True
        if self._current_project is None:
            return False
        try:
            segments = self._transcription.save_edits(
                self._current_project.id, self._dirty_segments
            )
        except Exception as error:
            self._save_status.setText("Save failed")
            QMessageBox.critical(self, "Transcript save failed", str(error))
            return False
        self._populate_transcript(segments)
        self._refresh_translations(self._current_project)
        self.statusBar().showMessage("Transcript changes saved.", 5000)
        return True

    def _seek_to_segment(self, row: int, _column: int) -> None:
        timing_item = self._transcript_table.item(row, 0)
        if timing_item is not None:
            position = timing_item.data(Qt.ItemDataRole.UserRole)
            if isinstance(position, int):
                self._player.seek(position)

    def _confirm_discard_edits(self) -> bool:
        if not self._dirty_segments and not self._dirty_translations:
            return True
        choice = QMessageBox.question(
            self,
            "Unsaved changes",
            "Save transcript and translation changes before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Save:
            return self._save_transcript() and self._save_translation_edits()
        if choice == QMessageBox.StandardButton.Discard:
            self._dirty_segments.clear()
            self._dirty_translations.clear()
            return True
        return False

    def _refresh_glossary(self, project: Project) -> None:
        self._target_language_label.setText(
            f"Target language: {project.target_language or 'Not set'}"
        )
        self._wordbank_editor.setPlainText(self._glossary.read_wordbank(project.id))

    def _save_wordbank(self) -> bool:
        if self._current_project is None:
            return False
        try:
            self._current_project = self._glossary.save_wordbank(
                self._current_project.id, self._wordbank_editor.toPlainText()
            )
        except Exception as error:
            QMessageBox.critical(self, "Could not save wordbank", str(error))
            return False
        self.statusBar().showMessage("Wordbank saved.", 5000)
        return True

    def _set_target_language(self) -> None:
        if self._current_project is None:
            return
        current_index = (
            LANGUAGE_OPTIONS.index(self._current_project.target_language)
            if self._current_project.target_language in LANGUAGE_OPTIONS
            else 0
        )
        language, accepted = QInputDialog.getItem(
            self,
            "Target language",
            "Translate into",
            LANGUAGE_OPTIONS,
            current_index,
            False,
        )
        if not accepted:
            return
        try:
            updated = self._glossary.set_target_language(self._current_project.id, language)
        except ValueError as error:
            QMessageBox.warning(self, "Invalid target language", str(error))
            return
        self._current_project = updated
        self._refresh_glossary(updated)
        self._refresh_translations(updated)

    def _show_translation_instructions(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Translation instructions (AGENTS.md)")
        dialog.resize(760, 560)
        layout = QVBoxLayout(dialog)
        description = QLabel(
            "These global instructions guide every AI translation. "
            f"Stored locally at: {self._paths.translation_agents}"
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #5f6368;")
        self._translation_instructions = QPlainTextEdit()
        self._translation_instructions.setPlainText(self._translation.read_instructions())
        buttons = QHBoxLayout()
        save_button = QPushButton("Save instructions")
        save_button.clicked.connect(self._save_translation_instructions)
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        buttons.addWidget(save_button)
        buttons.addWidget(close_button)
        buttons.addStretch()
        layout.addWidget(description)
        layout.addWidget(self._translation_instructions, 1)
        layout.addLayout(buttons)
        dialog.exec()

    def _save_translation_instructions(self) -> bool:
        try:
            self._translation.save_instructions(self._translation_instructions.toPlainText())
        except Exception as error:
            QMessageBox.critical(self, "Could not save instructions", str(error))
            return False
        self.statusBar().showMessage("Translation instructions saved.", 5000)
        return True

    def _refresh_translations(self, project: Project) -> None:
        blocker = QSignalBlocker(self._translation_table)
        segments = self._transcription.list_segments(project.id)
        translations = {
            value.segment_id: value for value in self._translation.list_translations(project.id)
        }
        self._translation_table.setRowCount(len(segments))
        for row, segment in enumerate(segments):
            value = translations.get(segment.id)
            timing_item = QTableWidgetItem(
                f"{format_milliseconds(segment.start_ms)} - {format_milliseconds(segment.end_ms)}"
            )
            timing_item.setData(Qt.ItemDataRole.UserRole, segment.id)
            source_item = QTableWidgetItem(segment.text)
            translated_text = ""
            status = "Not translated"
            if value is not None:
                translated_text = value.text or ""
                if value.status == TranslationStatus.FAILED:
                    status = "Failed — hover for details"
                else:
                    status = value.status.value.title()
            timing_item.setFlags(timing_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            source_item.setFlags(source_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._translation_table.setItem(row, 0, timing_item)
            self._translation_table.setItem(row, 1, source_item)
            translation_item = QTableWidgetItem(translated_text)
            translation_item.setData(Qt.ItemDataRole.UserRole, segment.id)
            if value is None or value.status == TranslationStatus.FAILED:
                translation_item.setFlags(translation_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._translation_table.setItem(row, 2, translation_item)
            status_item = QTableWidgetItem(status)
            status_item.setData(
                Qt.ItemDataRole.UserRole,
                value.status.value if value is not None else "missing",
            )
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if value is not None and value.status == TranslationStatus.FAILED:
                status_item.setToolTip(value.error or "Unknown translation error")
            self._translation_table.setItem(row, 3, status_item)
        del blocker
        self._dirty_translations.clear()
        self._save_translation_button.setEnabled(False)
        self._apply_translation_filter()

    def _on_translation_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 2:
            return
        segment_id = item.data(Qt.ItemDataRole.UserRole)
        if segment_id:
            self._dirty_translations[str(segment_id)] = item.text()
            self._save_translation_button.setEnabled(True)

    def _save_translation_edits(self) -> bool:
        if not self._dirty_translations:
            return True
        if self._current_project is None:
            return False
        try:
            self._translation.save_edits(self._current_project.id, self._dirty_translations)
        except Exception as error:
            QMessageBox.critical(self, "Could not save translation edits", str(error))
            return False
        self._refresh_translations(self._current_project)
        self.statusBar().showMessage("Translation edits saved as drafts.", 5000)
        return True

    def _selected_translation_ids(self) -> set[str]:
        return {
            str(item.data(Qt.ItemDataRole.UserRole))
            for item in (
                self._translation_table.item(index.row(), 0)
                for index in self._translation_table.selectionModel().selectedRows()
            )
            if item is not None and item.data(Qt.ItemDataRole.UserRole)
        }

    def _seek_to_translation_segment(self, row: int, _column: int) -> None:
        if self._current_project is None:
            return
        segment_id_item = self._translation_table.item(row, 0)
        if segment_id_item is None:
            return
        segment_id = segment_id_item.data(Qt.ItemDataRole.UserRole)
        segment = next(
            (
                value
                for value in self._transcription.list_segments(self._current_project.id)
                if value.id == segment_id
            ),
            None,
        )
        if segment is not None:
            self._player.seek(segment.start_ms)

    def _mark_translation_status(self, status: TranslationStatus) -> None:
        if self._current_project is None:
            return
        if not self._save_translation_edits():
            return
        selected_ids = self._selected_translation_ids()
        if not selected_ids:
            QMessageBox.information(self, "Review translations", "Select one or more rows first.")
            return
        try:
            self._translation.set_review_status(self._current_project.id, selected_ids, status)
        except Exception as error:
            QMessageBox.warning(self, "Could not update review status", str(error))
            return
        self._refresh_translations(self._current_project)
        self.statusBar().showMessage(
            f"{len(selected_ids)} translation(s) marked {status.value}.", 5000
        )

    def _apply_translation_filter(self) -> None:
        selected = str(self._translation_filter.currentData())
        for row in range(self._translation_table.rowCount()):
            status_item = self._translation_table.item(row, 3)
            row_status = (
                str(status_item.data(Qt.ItemDataRole.UserRole))
                if status_item is not None
                else "missing"
            )
            self._translation_table.setRowHidden(row, selected != "all" and row_status != selected)

    def _translate_all(self) -> None:
        self._start_translation(None)

    def _translate_selected(self) -> None:
        selected_ids = self._selected_translation_ids()
        if not selected_ids:
            QMessageBox.information(
                self, "Translate selected", "Select one or more translation rows first."
            )
            return
        self._start_translation(selected_ids)

    def _retry_failed_translations(self) -> None:
        self._start_translation(None, retry_failed=True)

    def _export_translated_srt(self) -> None:
        if self._current_project is None:
            return
        readiness = self._translation.export_readiness(self._current_project.id)
        if readiness.total == 0:
            QMessageBox.information(
                self, "Nothing to export", "This project has no transcript segments."
            )
            return
        if readiness.usable_count == 0:
            QMessageBox.warning(
                self,
                "Nothing ready to export",
                "There are no approved, reviewed, or draft translations.\n\n"
                f"Outdated: {readiness.outdated}\n"
                f"Failed: {readiness.failed}\n"
                f"Not translated: {readiness.missing}",
            )
            return
        include_unapproved = False
        if readiness.approved != readiness.total:
            summary = (
                f"Total segments: {readiness.total}\n"
                f"Approved: {readiness.approved}\n"
                f"Reviewed: {readiness.reviewed}\n"
                f"Draft: {readiness.draft}\n"
                f"Outdated: {readiness.outdated}\n"
                f"Failed: {readiness.failed}\n"
                f"Not translated: {readiness.missing}\n\n"
                "Outdated, failed, and untranslated segments are always omitted."
            )
            choices: list[str] = []
            if readiness.approved:
                choices.append(f"Approved only ({readiness.approved})")
            if readiness.reviewed or readiness.draft:
                choices.append(
                    "Include reviewed and draft "
                    f"({readiness.usable_count}; explicit unapproved export)"
                )
            choice, accepted = QInputDialog.getItem(
                self,
                "Choose subtitle export",
                summary,
                choices,
                0,
                False,
            )
            if not accepted:
                return
            include_unapproved = choice.startswith("Include")
        safe_name = "".join(
            "_" if character in '<>:"/\\|?*' else character
            for character in self._current_project.name
        ).strip(" .")
        suggested = f"{safe_name or 'subtitles'}-translated.srt"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export translated subtitles", suggested, "SubRip subtitles (*.srt)"
        )
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.casefold() != ".srt":
            destination = destination.with_suffix(".srt")
        try:
            count = self._translation.export_srt(
                self._current_project.id,
                destination,
                include_unapproved=include_unapproved,
            )
        except Exception as error:
            QMessageBox.critical(self, "Could not export subtitles", str(error))
            return
        message = f"Exported {count} translated segment(s) to {destination}."
        if count < readiness.total:
            message += f" {readiness.total - count} unavailable segment(s) were omitted."
        QMessageBox.information(self, "Subtitles exported", message)

    def _start_translation(self, segment_ids: set[str] | None, retry_failed: bool = False) -> None:
        if self._current_project is None or self._translation_worker is not None:
            return
        if not self._save_wordbank():
            return
        worker = TranslationWorker(
            self._translation,
            self._current_project.id,
            segment_ids=segment_ids,
            retry_failed=retry_failed,
        )
        worker.completed.connect(self._on_translation_completed)
        worker.failed.connect(self._on_translation_failed)
        worker.finished.connect(self._on_translation_finished)
        self._translation_worker = worker
        self._set_translation_running(True)
        self._translation_started_at = perf_counter()
        self._translation_status_detail.setText("Preparing batch…")
        self._translation_timer.start()
        self.statusBar().showMessage("Translating with the AI model…")
        worker.start()

    def _update_translation_elapsed(self) -> None:
        if self._translation_started_at is None:
            return
        elapsed_ms = round((perf_counter() - self._translation_started_at) * 1000)
        self._translation_status_detail.setText(f"API request in flight · {elapsed_ms:,} ms")

    def _cancel_translation(self) -> None:
        if self._translation_worker:
            self._cancel_translation_button.setEnabled(False)
            self.statusBar().showMessage("Cancellation requested; waiting for the batch call…")
            self._translation_worker.cancel()

    def _on_translation_completed(self, value: object) -> None:
        self._translation_timer.stop()
        elapsed_ms = self._translation_elapsed_ms()
        if self._current_project:
            self._refresh_translations(self._current_project)
        translations = (
            [item for item in value if isinstance(item, SegmentTranslation)]
            if isinstance(value, list)
            else []
        )
        failed = [item for item in translations if item.status == TranslationStatus.FAILED]
        if failed:
            first_error = failed[0].error or "Unknown API error"
            QMessageBox.warning(
                self,
                "Translation batch had failures",
                f"{len(failed)} translation(s) failed. No error messages were saved as "
                f"translated text.\n\nFirst error:\n{first_error}",
            )
            self.statusBar().showMessage(
                f"Translation completed with {len(failed)} failure(s).", 5000
            )
            self._translation_status_detail.setText(
                f"API returned in {elapsed_ms:,} ms · batch failed"
            )
        else:
            self.statusBar().showMessage("Translation batch completed.", 5000)
            self._translation_status_detail.setText(
                f"API returned and results parsed in {elapsed_ms:,} ms"
            )

    def _on_translation_failed(self, message: str) -> None:
        self._translation_timer.stop()
        elapsed_ms = self._translation_elapsed_ms()
        if self._current_project:
            self._refresh_translations(self._current_project)
        if "cancel" in message.lower():
            self._translation_status_detail.setText(f"Cancelled after {elapsed_ms:,} ms")
        else:
            self._translation_status_detail.setText(f"Failed after {elapsed_ms:,} ms")
            QMessageBox.critical(self, "Translation could not start", message)

    def _on_translation_finished(self) -> None:
        self._translation_timer.stop()
        self._translation_started_at = None
        self._set_translation_running(False)
        if self._translation_worker:
            self._translation_worker.deleteLater()
        self._translation_worker = None

    def _set_translation_running(self, running: bool) -> None:
        self._translate_all_button.setEnabled(not running)
        self._translate_selected_button.setEnabled(not running)
        self._retry_translation_button.setEnabled(not running)
        self._save_translation_button.setEnabled(not running and bool(self._dirty_translations))
        self._mark_reviewed_button.setEnabled(not running)
        self._approve_translation_button.setEnabled(not running)
        self._export_translation_button.setEnabled(not running)
        self._cancel_translation_button.setEnabled(True)
        self._cancel_translation_button.setVisible(running)

    def _translation_elapsed_ms(self) -> int:
        if self._translation_started_at is None:
            return 0
        return round((perf_counter() - self._translation_started_at) * 1000)

    def _show_api_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("AI model API settings")
        dialog.setMinimumWidth(560)
        layout = QVBoxLayout(dialog)
        help_text = QLabel(
            "These details are stored only in the local .env file and take effect immediately."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #5f6368;")
        self._api_key_input = QLineEdit(self._initial_api_key)
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_input.setPlaceholderText("OpenAI API key")
        show_key_button = QPushButton("Show/hide key")
        show_key_button.clicked.connect(self._toggle_api_key_visibility)
        key_row = QHBoxLayout()
        key_row.addWidget(self._api_key_input, 1)
        key_row.addWidget(show_key_button)
        self._api_model_input = QComboBox()
        for label, model_id in OPENAI_MODEL_OPTIONS:
            self._api_model_input.addItem(label, model_id)
        selected_model = next(
            (
                index
                for index, (_label, model_id) in enumerate(OPENAI_MODEL_OPTIONS)
                if model_id == self._initial_model
            ),
            0,
        )
        self._api_model_input.setCurrentIndex(selected_model)
        self._api_base_url_input = QLineEdit(self._initial_base_url)
        self._api_base_url_input.setPlaceholderText("Optional API base URL; leave blank for OpenAI")
        buttons = QHBoxLayout()
        save_button = QPushButton("Save API settings")
        save_button.clicked.connect(self._save_api_settings)
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        buttons.addWidget(save_button)
        buttons.addWidget(close_button)
        buttons.addStretch()
        layout.addWidget(help_text)
        layout.addWidget(QLabel("API key"))
        layout.addLayout(key_row)
        layout.addWidget(QLabel("Translation model"))
        layout.addWidget(self._api_model_input)
        layout.addWidget(QLabel("API base URL (optional)"))
        layout.addWidget(self._api_base_url_input)
        layout.addLayout(buttons)
        dialog.exec()

    def _toggle_api_key_visibility(self) -> None:
        mode = self._api_key_input.echoMode()
        self._api_key_input.setEchoMode(
            QLineEdit.EchoMode.Normal
            if mode == QLineEdit.EchoMode.Password
            else QLineEdit.EchoMode.Password
        )

    def _save_api_settings(self) -> None:
        values = OpenAISettings(
            api_key=self._api_key_input.text(),
            model=str(self._api_model_input.currentData()),
            base_url=self._api_base_url_input.text(),
        )
        try:
            self._api_settings.save(values)
            self._translation.configure_openai(values.api_key, values.model, values.base_url)
        except Exception as error:
            QMessageBox.critical(self, "Could not save API settings", str(error))
            return
        self._initial_api_key = values.api_key.strip()
        self._initial_model = values.model.strip()
        self._initial_base_url = values.base_url.strip()
        self._provider_label.setText(f"AI translation: {self._translation.provider_label}")
        self.statusBar().showMessage("AI model API settings saved and activated.", 5000)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_discard_edits():
            event.accept()
        else:
            event.ignore()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Localization Workflow",
            "Localization Workflow 1.0.0rc1\n\n"
            "A local-first desktop application for AI-assisted audiovisual localization.",
        )
