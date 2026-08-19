from pathlib import Path

import pytest

from localization_workflow.infrastructure.models import ManagedWhisperModels, WhisperModelError


def test_model_selection_remembers_existing_path_without_copying(tmp_path: Path) -> None:
    source = tmp_path / "downloads" / "ggml-test.bin"
    source.parent.mkdir()
    source.write_bytes(b"model" * 250_000)
    models = ManagedWhisperModels(tmp_path / "models")

    selected = models.select(source)

    assert selected == source
    assert list((tmp_path / "models").glob("*.bin")) == []
    assert ManagedWhisperModels(tmp_path / "models").selected() == source


def test_model_selection_rejects_non_bin_file(tmp_path: Path) -> None:
    source = tmp_path / "model.zip"
    source.write_bytes(b"not a model")

    with pytest.raises(WhisperModelError, match=r"\.bin"):
        ManagedWhisperModels(tmp_path / "models").select(source)
