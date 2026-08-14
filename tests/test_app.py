from PySide6.QtWidgets import QApplication

from localization_workflow.app import create_application


def test_create_application_is_reused(qapp: QApplication) -> None:
    assert create_application([]) is qapp
