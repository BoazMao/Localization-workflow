"""Main desktop window."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from localization_workflow.core.paths import AppPaths


class MainWindow(QMainWindow):
    """Application shell established in Milestone 0."""

    def __init__(self, paths: AppPaths) -> None:
        super().__init__()
        self._paths = paths
        self.setWindowTitle("Localization Workflow")
        self.setMinimumSize(960, 640)
        self.resize(1200, 760)
        self._build_actions()
        self._build_menu()
        self._build_content()
        self._build_status_bar()

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

    def _build_content(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(20)

        heading = QLabel("Localization Workflow")
        heading.setObjectName("heading")
        heading.setStyleSheet("font-size: 30px; font-weight: 650;")

        subtitle = QLabel(
            "Turn video into a reviewed transcript and terminology-controlled translation."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 16px; color: #5f6368;")

        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet(
            "QFrame { background: palette(base); border: 1px solid palette(mid); "
            "border-radius: 10px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(14)

        status = QLabel("Milestone 0 · Desktop foundation")
        status.setStyleSheet("font-weight: 600; color: #356859;")
        description = QLabel(
            "The application shell is ready. Project creation and media import "
            "arrive in Milestone 1."
        )
        description.setWordWrap(True)

        actions = QHBoxLayout()
        new_project = QPushButton("New project")
        new_project.setEnabled(False)
        open_project = QPushButton("Open project")
        open_project.setEnabled(False)
        actions.addWidget(new_project)
        actions.addWidget(open_project)
        actions.addStretch()

        card_layout.addWidget(status)
        card_layout.addWidget(description)
        card_layout.addLayout(actions)

        layout.addWidget(heading)
        layout.addWidget(subtitle)
        layout.addWidget(card)
        layout.addStretch()

        root.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCentralWidget(root)

    def _build_status_bar(self) -> None:
        bar = QStatusBar(self)
        bar.showMessage(f"Local data: {self._paths.data}")
        self.setStatusBar(bar)

    def _show_about(self) -> None:
        label = QLabel(
            "Localization Workflow\n\n"
            "A local-first desktop application for AI-assisted audiovisual localization.",
            self,
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWindowTitle("About Localization Workflow")
        label.setMinimumSize(460, 180)
        label.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        label.show()
