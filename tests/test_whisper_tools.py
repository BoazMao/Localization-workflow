import subprocess
import zipfile
from pathlib import Path

from localization_workflow.infrastructure.whisper_tools import (
    WHISPER_CLI_DOWNLOAD_URL,
    WhisperCliSettingsStore,
    discover_whisper_cli,
    install_whisper_cli,
    validate_whisper_cli,
)


def successful_runner(command, **_kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, 1, "", "--model FILE --language LANG --prompt TEXT")


def test_discovery_finds_managed_whisper_cli(tmp_path: Path) -> None:
    executable = tmp_path / "WhisperCLI" / "main.exe"
    executable.parent.mkdir()
    executable.touch()

    result = discover_whisper_cli(None, tmp_path, runner=successful_runner)

    assert result == executable.resolve()


def test_validation_rejects_an_unrelated_executable(tmp_path: Path) -> None:
    executable = tmp_path / "other.exe"
    executable.touch()

    assert "main.exe" in (validate_whisper_cli(executable, successful_runner) or "")


def test_installer_extracts_only_expected_cli_files(tmp_path: Path) -> None:
    def downloader(url: str, destination: Path) -> None:
        assert url == WHISPER_CLI_DOWNLOAD_URL
        with zipfile.ZipFile(destination, "w") as package:
            package.writestr("main.exe", b"exe")
            package.writestr("Whisper.dll", b"dll")
            package.writestr("lz4.txt", b"license")
            package.writestr("../outside.txt", b"unsafe")

    executable = install_whisper_cli(tmp_path, downloader=downloader, runner=successful_runner)

    assert executable == (tmp_path / "WhisperCLI" / "main.exe").resolve()
    assert (tmp_path / "WhisperCLI" / "Whisper.dll").is_file()
    assert not (tmp_path / "outside.txt").exists()


def test_settings_store_preserves_unrelated_values(tmp_path: Path) -> None:
    environment_file = tmp_path / ".env"
    environment_file.write_text("OPENAI_API_KEY=private\nWHISPER_CLI_PATH=old\n", encoding="utf-8")
    executable = tmp_path / "WhisperCLI" / "main.exe"

    WhisperCliSettingsStore(environment_file).save(executable)
    saved = environment_file.read_text(encoding="utf-8")

    assert "OPENAI_API_KEY=private" in saved
    assert f"WHISPER_CLI_PATH={executable.resolve().as_posix()}" in saved
    assert "WHISPER_CLI_PATH=old" not in saved
