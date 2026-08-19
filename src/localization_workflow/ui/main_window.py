"""Project library and media workspace window."""

from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import QSignalBlocker, Qt, QThread, Signal
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from localization_workflow.application.projects import ProjectService
from localization_workflow.application.transcription import TranscriptionService
from localization_workflow.core.paths import AppPaths
from localization_workflow.domain.projects import (
    AudioStatus,
    Project,
    ProjectStatus,
    TranscriptionStatus,
    TranscriptSegment,
)
from localization_workflow.infrastructure.media import SUPPORTED_MEDIA_EXTENSIONS
from localization_workflow.ui.media_player import MediaPlayerWidget, format_milliseconds


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


class MainWindow(QMainWindow):
    """Desktop project library and media workspace."""

    def __init__(
        self,
        paths: AppPaths,
        projects: ProjectService,
        transcription: TranscriptionService,
    ) -> None:
        super().__init__()
        self._paths = paths
        self._projects = projects
        self._transcription = transcription
        self._current_project: Project | None = None
        self._import_worker: ImportWorker | None = None
        self._audio_worker: AudioWorker | None = None
        self._transcription_worker: TranscriptionWorker | None = None
        self._dirty_segments: dict[str, str] = {}
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

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self._quit_action)
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

        layout.addLayout(top)
        layout.addWidget(self._media_details)
        layout.addWidget(self._player, 1)
        layout.addLayout(audio_controls)
        layout.addLayout(model_controls)
        layout.addLayout(transcription_controls)
        layout.addLayout(review_controls)
        layout.addWidget(self._transcript_table, 1)
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
        language, accepted = QInputDialog.getText(
            self, "Source language", "Source language", text="Auto-detect"
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
        self.statusBar().showMessage("Transcript changes saved.", 5000)
        return True

    def _seek_to_segment(self, row: int, _column: int) -> None:
        timing_item = self._transcript_table.item(row, 0)
        if timing_item is not None:
            position = timing_item.data(Qt.ItemDataRole.UserRole)
            if isinstance(position, int):
                self._player.seek(position)

    def _confirm_discard_edits(self) -> bool:
        if not self._dirty_segments:
            return True
        choice = QMessageBox.question(
            self,
            "Unsaved transcript changes",
            "Save transcript changes before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Save:
            return self._save_transcript()
        if choice == QMessageBox.StandardButton.Discard:
            self._dirty_segments.clear()
            return True
        return False

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_discard_edits():
            event.accept()
        else:
            event.ignore()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Localization Workflow",
            "Localization Workflow\n\n"
            "A local-first desktop application for AI-assisted audiovisual localization.",
        )
