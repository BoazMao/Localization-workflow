"""Managed local Whisper model storage and selection."""

from __future__ import annotations

from pathlib import Path


class WhisperModelError(ValueError):
    """A model could not be safely imported or selected."""


class ManagedWhisperModels:
    """Validate local models and persist the active path without copying files."""

    def __init__(self, root: Path, configured_model: Path | None = None) -> None:
        self._root = root.resolve()
        self._configured_model = configured_model.resolve() if configured_model else None
        self._selection_file = self._root / "selected-model.txt"

    def selected(self) -> Path | None:
        if self._selection_file.is_file():
            stored_path = self._selection_file.read_text(encoding="utf-8").strip()
            candidate = Path(stored_path).expanduser().resolve()
            if candidate.is_file():
                return candidate
        if self._configured_model is not None and self._configured_model.is_file():
            return self._configured_model
        return None

    def select(self, source: Path) -> Path:
        source = source.resolve()
        if not source.is_file():
            raise WhisperModelError("The selected Whisper model was not found.")
        if source.suffix.casefold() != ".bin":
            raise WhisperModelError("Choose an uncompressed ggml Whisper model (.bin).")
        if source.stat().st_size < 1_000_000:
            raise WhisperModelError("The selected file is too small to be a Whisper model.")
        self._root.mkdir(parents=True, exist_ok=True)
        self._selection_file.write_text(str(source), encoding="utf-8")
        return source
