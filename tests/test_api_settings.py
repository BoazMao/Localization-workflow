from pathlib import Path

import pytest

from localization_workflow.infrastructure.api_settings import OpenAISettings, OpenAISettingsStore


def test_api_settings_update_env_without_losing_other_values(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("FFMPEG_PATH=F:/ffmpeg.exe\nOPENAI_API_KEY=old\n", encoding="utf-8")
    store = OpenAISettingsStore(path)

    store.save(OpenAISettings("sk-new", "gpt-test", "https://example.test/v1"))
    saved = path.read_text(encoding="utf-8")

    assert "FFMPEG_PATH=F:/ffmpeg.exe" in saved
    assert "OPENAI_API_KEY=sk-new" in saved
    assert "OPENAI_TRANSLATION_MODEL=gpt-test" in saved
    assert "OPENAI_BASE_URL=https://example.test/v1" in saved
    assert "old" not in saved


def test_api_settings_require_key_and_model(tmp_path: Path) -> None:
    store = OpenAISettingsStore(tmp_path / ".env")

    with pytest.raises(ValueError, match="API key"):
        store.save(OpenAISettings("", "gpt-test", ""))
    with pytest.raises(ValueError, match="model name"):
        store.save(OpenAISettings("sk-test", "", ""))
