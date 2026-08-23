"""First-run setup dialog for the Const-me Whisper CLI."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
)

from localization_workflow.infrastructure.whisper_tools import (
    install_whisper_cli,
    validate_whisper_cli,
)


class WhisperSetupDialog(QDialog):
    """Offer automatic installation, manual selection, or deferred setup."""

    def __init__(self, tools_directory: Path) -> None:
        super().__init__()
        self._tools_directory = tools_directory
        self._result: Path | None = None
        self.setWindowTitle("Set up transcription")
        self.setMinimumWidth(620)
        layout = QVBoxLayout(self)
        explanation = QLabel(
            "The Const-me Whisper command-line engine is required for local transcription, "
            "but it was not found. Download the official CLI package from GitHub or select "
            "an existing main.exe. Models are configured separately."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        buttons = QHBoxLayout()
        download_button = QPushButton("Download Whisper CLI")
        download_button.clicked.connect(self._download)
        select_button = QPushButton("Select existing main.exe")
        select_button.clicked.connect(self._select)
        skip_button = QPushButton("Skip for now")
        skip_button.clicked.connect(self.reject)
        buttons.addWidget(download_button)
        buttons.addWidget(select_button)
        buttons.addWidget(skip_button)
        layout.addLayout(buttons)

    @property
    def executable(self) -> Path | None:
        return self._result

    def _download(self) -> None:
        progress = QProgressDialog(
            "Downloading and installing the official Whisper CLI…", "", 0, 0, self
        )
        progress.setWindowTitle("Setting up transcription")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.show()
        QApplication.processEvents()
        try:
            self._result = install_whisper_cli(self._tools_directory)
        except Exception as error:
            QMessageBox.warning(
                self,
                "Whisper CLI could not be installed",
                "The download or installation did not complete. Check the internet connection "
                f"and try again, or select an existing main.exe.\n\nDetails: {error}",
            )
            return
        finally:
            progress.close()
        QMessageBox.information(
            self, "Transcription is ready", "The Whisper CLI was installed successfully."
        )
        self.accept()

    def _select(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select Const-me Whisper main.exe",
            "",
            "main.exe (main.exe);;Windows executables (*.exe);;All files (*)",
        )
        if not selected:
            return
        executable = Path(selected)
        error = validate_whisper_cli(executable)
        if error is not None:
            QMessageBox.warning(self, "Whisper CLI could not be validated", error)
            return
        self._result = executable.resolve()
        self.accept()
