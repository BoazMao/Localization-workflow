"""Application configuration loaded from environment variables and .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Local application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    data_dir: Path | None = Field(default=None, validation_alias="LOCALIZATION_WORKFLOW_DATA_DIR")
    ffmpeg_path: Path | None = Field(default=None, validation_alias="FFMPEG_PATH")
    ffprobe_path: Path | None = Field(default=None, validation_alias="FFPROBE_PATH")
