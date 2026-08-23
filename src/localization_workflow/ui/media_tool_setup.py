"""First-run FFmpeg and FFprobe setup dialog."""

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from localization_workflow.infrastructure.media_tools import (
    MediaToolPaths,
    validate_media_tool,
)


class MediaToolSetupDialog(QDialog):
    """Collect and validate the two external media executables."""

    def __init__(
        self,
        ffmpeg: Path | None = None,
        ffprobe: Path | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Set up media tools")
        self.setMinimumWidth(680)
        self._result: MediaToolPaths | None = None
        layout = QVBoxLayout(self)
        explanation = QLabel(
            "FFmpeg and FFprobe were not detected automatically. Select their executable "
            "files. Choosing either tool will also look for its companion in the same folder."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        form = QFormLayout()
        self._ffmpeg = QLineEdit(str(ffmpeg or ""))
        self._ffprobe = QLineEdit(str(ffprobe or ""))
        form.addRow("FFmpeg", self._path_row(self._ffmpeg, "ffmpeg.exe"))
        form.addRow("FFprobe", self._path_row(self._ffprobe, "ffprobe.exe"))
        layout.addLayout(form)
        buttons = QHBoxLayout()
        save_button = QPushButton("Validate and continue")
        save_button.clicked.connect(self._validate_and_accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(save_button)
        buttons.addWidget(cancel_button)
        buttons.addStretch()
        layout.addLayout(buttons)

    @property
    def media_tools(self) -> MediaToolPaths | None:
        return self._result

    def _path_row(self, field: QLineEdit, filename: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(field, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda: self._browse(field, filename))
        row.addWidget(browse)
        return row

    def _browse(self, field: QLineEdit, filename: str) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {filename}",
            field.text(),
            "Windows executables (*.exe);;All files (*)",
        )
        if not selected:
            return
        field.setText(selected)
        selected_path = Path(selected)
        companion_name = "ffprobe.exe" if filename == "ffmpeg.exe" else "ffmpeg.exe"
        companion = selected_path.with_name(companion_name)
        if companion.is_file():
            target = self._ffprobe if companion_name == "ffprobe.exe" else self._ffmpeg
            target.setText(str(companion))

    def _validate_and_accept(self) -> None:
        ffmpeg = Path(self._ffmpeg.text().strip())
        ffprobe = Path(self._ffprobe.text().strip())
        errors = [
            error
            for error in (
                validate_media_tool(ffmpeg, "ffmpeg"),
                validate_media_tool(ffprobe, "ffprobe"),
            )
            if error is not None
        ]
        if errors:
            QMessageBox.warning(self, "Media tools could not be validated", "\n".join(errors))
            return
        self._result = MediaToolPaths(ffmpeg.resolve(), ffprobe.resolve())
        self.accept()
