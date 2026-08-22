"""Editable translation-agent instruction storage."""

from pathlib import Path

DEFAULT_TRANSLATION_INSTRUCTIONS = """# Translation Agent Instructions

Translate audiovisual dialogue naturally and accurately into the requested target language.
Preserve meaning, tone, names, numbers, and formatting. Follow every supplied glossary entry
exactly. Return only the translated segment with no commentary, labels, or quotation marks.
"""


class TranslationInstructionsStore:
    """Own the app-managed editable AGENTS.md file."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()

    def ensure_exists(self) -> None:
        if not self.path.exists():
            self.path.write_text(DEFAULT_TRANSLATION_INSTRUCTIONS, encoding="utf-8")

    def read(self) -> str:
        self.ensure_exists()
        return self.path.read_text(encoding="utf-8")

    def save(self, text: str) -> None:
        if not text.strip():
            raise ValueError("Translation AGENTS.md cannot be empty.")
        self.path.write_text(text, encoding="utf-8")
