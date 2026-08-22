from pathlib import Path

import pytest

from localization_workflow.infrastructure.instructions import (
    DEFAULT_TRANSLATION_INSTRUCTIONS,
    TranslationInstructionsStore,
)


def test_translation_agents_file_is_created_and_editable(tmp_path: Path) -> None:
    store = TranslationInstructionsStore(tmp_path / "AGENTS.md")

    assert store.read() == DEFAULT_TRANSLATION_INSTRUCTIONS
    store.save("# My translation rules\nKeep dialogue concise.\n")

    assert TranslationInstructionsStore(store.path).read() == (
        "# My translation rules\nKeep dialogue concise.\n"
    )


def test_translation_agents_file_cannot_be_empty(tmp_path: Path) -> None:
    store = TranslationInstructionsStore(tmp_path / "AGENTS.md")

    with pytest.raises(ValueError, match="cannot be empty"):
        store.save("   ")
