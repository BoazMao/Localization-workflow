"""Project library and media workspace window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from localization_workflow.application.projects import ProjectService
from localization_workflow.core.paths import AppPaths
from localization_workflow.domain.projects import Project, ProjectStatus
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


class MainWindow(QMainWindow):
    """Desktop project library and media workspace."""

    def __init__(self, paths: AppPaths, projects: ProjectService) -> None:
        super().__init__()
        self._paths = paths
        self._projects = projects
        self._current_project: Project | None = None
        self._import_worker: ImportWorker | None = None
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

        layout.addLayout(top)
        layout.addWidget(self._media_details)
        layout.addWidget(self._player, 1)
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
        self._pages.setCurrentWidget(self._workspace_page)

    def _show_library(self) -> None:
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
        self.statusBar().showMessage("Media imported successfully.", 5000)

    def _on_import_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Media import failed", message)
        self.statusBar().showMessage("Media import failed.", 5000)

    def _on_import_finished(self) -> None:
        self._import_button.setEnabled(True)
        if self._import_worker:
            self._import_worker.deleteLater()
        self._import_worker = None

    def _update_media_display(self, project: Project) -> None:
        if not project.media_path:
            self._media_details.setText("No media imported yet.")
            self._player.load(None)
            return
        resolution = (
            f" · {project.width}x{project.height}" if project.width and project.height else ""
        )
        codecs = " / ".join(value for value in (project.video_codec, project.audio_codec) if value)
        self._media_details.setText(
            f"{project.original_filename} · {format_milliseconds(project.duration_ms or 0)}"
            f"{resolution} · {codecs or 'Unknown codec'}"
        )
        self._player.load(project.media_path)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Localization Workflow",
            "Localization Workflow\n\n"
            "A local-first desktop application for AI-assisted audiovisual localization.",
        )
