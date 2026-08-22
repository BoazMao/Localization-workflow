"""Operating-system-aware application paths."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path

_DATA_DIR_ENV = "LOCALIZATION_WORKFLOW_DATA_DIR"


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Filesystem locations owned by the application."""

    data: Path
    media: Path
    derived: Path
    exports: Path
    models: Path
    tools: Path
    database: Path
    translation_agents: Path

    @classmethod
    def discover(cls, configured_data_dir: Path | None = None) -> AppPaths:
        """Resolve paths, honoring an explicit data-directory override."""
        configured = configured_data_dir or os.environ.get(_DATA_DIR_ENV)
        data = (
            Path(configured).expanduser().resolve()
            if configured
            else Path(
                user_data_path(
                    appname="Localization Workflow",
                    appauthor="Localization Workflow",
                    ensure_exists=False,
                )
            )
        )
        return cls(
            data=data,
            media=data / "media",
            derived=data / "derived",
            exports=data / "exports",
            models=data / "models",
            tools=data / "tools",
            database=data / "localization-workflow.sqlite3",
            translation_agents=data / "AGENTS.md",
        )

    def ensure_directories(self) -> None:
        """Create application-owned directories if they do not exist."""
        for directory in (
            self.data,
            self.media,
            self.derived,
            self.exports,
            self.models,
            self.tools,
        ):
            directory.mkdir(parents=True, exist_ok=True)
