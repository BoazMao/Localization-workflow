"""Persist editable OpenAI settings without disturbing other .env values."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class OpenAISettings:
    api_key: str
    model: str
    base_url: str


class OpenAISettingsStore:
    """Read and update the OpenAI-related entries in the local .env file."""

    _KEYS = ("OPENAI_API_KEY", "OPENAI_TRANSLATION_MODEL", "OPENAI_BASE_URL")

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()

    def save(self, values: OpenAISettings) -> None:
        if not values.api_key.strip():
            raise ValueError("A translation API key is required.")
        if not values.model.strip():
            raise ValueError("A translation model name is required.")
        existing = self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []
        replacements = {
            "OPENAI_API_KEY": values.api_key.strip(),
            "OPENAI_TRANSLATION_MODEL": values.model.strip(),
            "OPENAI_BASE_URL": values.base_url.strip(),
        }
        output: list[str] = []
        written: set[str] = set()
        for line in existing:
            key = line.split("=", 1)[0].strip() if "=" in line else ""
            if key in replacements:
                output.append(f"{key}={replacements[key]}")
                written.add(key)
            else:
                output.append(line)
        for key in self._KEYS:
            if key not in written:
                output.append(f"{key}={replacements[key]}")
        self.path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
