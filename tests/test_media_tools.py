import subprocess
from pathlib import Path

from localization_workflow.infrastructure.media_tools import (
    MediaToolPaths,
    MediaToolSettingsStore,
    discover_media_tools,
    validate_media_tool,
)


def successful_runner(command, **_kwargs) -> subprocess.CompletedProcess[str]:
    name = Path(command[0]).stem
    return subprocess.CompletedProcess(command, 0, f"{name} version test", "")


def test_discovery_uses_path_and_finds_companion(tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffprobe = tmp_path / "ffprobe.exe"
    ffmpeg.touch()
    ffprobe.touch()

    result = discover_media_tools(
        None,
        None,
        path_lookup=lambda name: str(ffmpeg) if name == "ffmpeg" else None,
        runner=successful_runner,
    )

    assert result == MediaToolPaths(ffmpeg.resolve(), ffprobe.resolve())


def test_invalid_executable_is_rejected(tmp_path: Path) -> None:
    executable = tmp_path / "ffmpeg.exe"
    executable.touch()

    def failed_runner(command, **_kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "not a tool")

    assert "not a working" in validate_media_tool(executable, "ffmpeg", failed_runner)


def test_media_tool_settings_preserve_unrelated_values(tmp_path: Path) -> None:
    environment_file = tmp_path / ".env"
    environment_file.write_text("OPENAI_API_KEY=private\nFFMPEG_PATH=old\n", encoding="utf-8")
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffprobe = tmp_path / "ffprobe.exe"

    MediaToolSettingsStore(environment_file).save(MediaToolPaths(ffmpeg, ffprobe))
    saved = environment_file.read_text(encoding="utf-8")

    assert "OPENAI_API_KEY=private" in saved
    assert f"FFMPEG_PATH={ffmpeg.as_posix()}" in saved
    assert f"FFPROBE_PATH={ffprobe.as_posix()}" in saved
    assert "FFMPEG_PATH=old" not in saved
