"""Discovery, installation, validation, and persistence for Const-me Whisper CLI."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

WHISPER_CLI_DOWNLOAD_URL = "https://github.com/Const-me/Whisper/releases/latest/download/cli.zip"

Runner = Callable[..., subprocess.CompletedProcess[str]]
Downloader = Callable[[str, Path], None]


def validate_whisper_cli(path: Path, runner: Runner = subprocess.run) -> str | None:
    """Return a neutral validation error, or None for a compatible CLI."""
    if not path.is_file():
        return "Whisper main.exe was not found at the selected location."
    if path.name.casefold() != "main.exe":
        return "Select the main.exe file from the Const-me Whisper CLI package."
    try:
        result = runner(
            [str(path.resolve()), "--help"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return f"The selected Whisper CLI could not start: {error}"
    output = f"{result.stdout}\n{result.stderr}".casefold()
    # Const-me main.exe currently returns 1 for --help and writes the help text to stderr.
    if "--model" not in output or "--language" not in output or "--prompt" not in output:
        return "The selected file is not a compatible Const-me Whisper CLI executable."
    return None


def discover_whisper_cli(
    configured: Path | None,
    tools_directory: Path,
    *,
    runner: Runner = subprocess.run,
) -> Path | None:
    """Find a working CLI from configuration, managed storage, or portable locations."""
    candidates = [
        configured,
        tools_directory / "WhisperCLI" / "main.exe",
        Path(sys.executable).resolve().parent / "WhisperCLI" / "main.exe",
        Path(sys.executable).resolve().parent / "main.exe",
        Path.cwd() / "WhisperCLI" / "main.exe",
        Path.cwd() / "main.exe",
    ]
    for candidate in candidates:
        if candidate is not None and validate_whisper_cli(candidate, runner) is None:
            return candidate.resolve()
    return None


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Localization-Workflow/1.0"})
    with (
        urllib.request.urlopen(request, timeout=120) as response,
        destination.open("wb") as output,
    ):
        shutil.copyfileobj(response, output)


def install_whisper_cli(
    tools_directory: Path,
    *,
    url: str = WHISPER_CLI_DOWNLOAD_URL,
    downloader: Downloader = _download,
    runner: Runner = subprocess.run,
) -> Path:
    """Download and safely install the official CLI package into managed storage."""
    install_directory = tools_directory.resolve() / "WhisperCLI"
    install_directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="whisper-cli-", dir=install_directory.parent
    ) as temporary:
        temporary_directory = Path(temporary)
        archive = temporary_directory / "cli.zip"
        downloader(url, archive)
        with zipfile.ZipFile(archive) as package:
            members = {member.filename.casefold(): member for member in package.infolist()}
            if any(name not in members for name in ("main.exe", "whisper.dll")):
                raise RuntimeError("The downloaded Whisper CLI package is incomplete.")
            extracted = temporary_directory / "extracted"
            extracted.mkdir()
            for name in ("main.exe", "whisper.dll", "lz4.txt"):
                member = members.get(name)
                if member is None:
                    continue
                with package.open(member) as source, (extracted / name).open("wb") as output:
                    shutil.copyfileobj(source, output)
        executable = extracted / "main.exe"
        error = validate_whisper_cli(executable, runner)
        if error is not None:
            raise RuntimeError(error)
        install_directory.mkdir(parents=True, exist_ok=True)
        for item in extracted.iterdir():
            item.replace(install_directory / item.name)
    return (install_directory / "main.exe").resolve()


@dataclass(frozen=True, slots=True)
class WhisperCliSettingsStore:
    """Persist the selected CLI without disturbing other environment settings."""

    path: Path

    def save(self, executable: Path) -> None:
        key = "WHISPER_CLI_PATH"
        replacement = f"{key}={executable.resolve().as_posix()}"
        existing = self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []
        output: list[str] = []
        written = False
        for line in existing:
            current_key = line.split("=", 1)[0].strip() if "=" in line else ""
            if current_key == key:
                output.append(replacement)
                written = True
            else:
                output.append(line)
        if not written:
            output.append(replacement)
        self.path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8", newline="\n")
