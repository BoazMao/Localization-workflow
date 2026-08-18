from pathlib import Path

from localization_workflow.core.paths import AppPaths


def test_discover_uses_configured_data_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "custom-data"
    monkeypatch.setenv("LOCALIZATION_WORKFLOW_DATA_DIR", str(data_dir))

    paths = AppPaths.discover()

    assert paths.data == data_dir.resolve()
    assert paths.media == data_dir.resolve() / "media"
    assert paths.database == data_dir.resolve() / "localization-workflow.sqlite3"


def test_ensure_directories_creates_owned_folders(tmp_path: Path) -> None:
    paths = AppPaths(
        data=tmp_path,
        media=tmp_path / "media",
        derived=tmp_path / "derived",
        exports=tmp_path / "exports",
        database=tmp_path / "app.sqlite3",
    )

    paths.ensure_directories()

    assert paths.media.is_dir()
    assert paths.derived.is_dir()
    assert paths.exports.is_dir()


def test_discover_accepts_explicit_data_directory(tmp_path: Path) -> None:
    paths = AppPaths.discover(tmp_path / "explicit")

    assert paths.data == (tmp_path / "explicit").resolve()
