import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from localization_workflow.app import create_application, environment_file_path


def test_create_application_is_reused(qapp: QApplication) -> None:
    assert create_application([]) is qapp


def test_frozen_application_reads_configuration_beside_executable(
    monkeypatch,
) -> None:
    executable = Path("C:/Portable/Localization Workflow/Localization Workflow.exe")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert environment_file_path() == executable.parent / ".env"
