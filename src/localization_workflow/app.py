"""Application bootstrap."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from localization_workflow.core.paths import AppPaths
from localization_workflow.ui.main_window import MainWindow


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    """Create and configure the Qt application."""
    app = QApplication.instance()
    if app is not None:
        return app

    qt_app = QApplication(list(argv) if argv is not None else sys.argv)
    qt_app.setApplicationName("Localization Workflow")
    qt_app.setApplicationDisplayName("Localization Workflow")
    qt_app.setOrganizationName("Localization Workflow")
    return qt_app


def main(argv: Sequence[str] | None = None) -> int:
    """Start the native desktop application."""
    app = create_application(argv)
    paths = AppPaths.discover()
    paths.ensure_directories()

    window = MainWindow(paths=paths)
    window.show()
    return app.exec()
