"""Discovery, validation, and persistence for external FFmpeg tools."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MediaToolPaths:
    ffmpeg: Path
    ffprobe: Path


Runner = Callable[..., subprocess.CompletedProcess[str]]
PathLookup = Callable[[str], str | None]


def validate_media_tool(
    path: Path,
    expected_name: str,
    runner: Runner = subprocess.run,
) -> str | None:
    """Return a neutral validation error, or None when the executable works."""
    if not path.is_file():
        return f"{expected_name} was not found at the selected location."
    try:
        result = runner(
            [str(path.resolve()), "-version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return f"{expected_name} could not start: {error}"
    output = f"{result.stdout}\n{result.stderr}".casefold()
    if result.returncode != 0 or expected_name.casefold() not in output:
        return f"The selected file is not a working {expected_name} executable."
    return None


def discover_media_tools(
    configured_ffmpeg: Path | None,
    configured_ffprobe: Path | None,
    *,
    path_lookup: PathLookup = shutil.which,
    runner: Runner = subprocess.run,
) -> MediaToolPaths | None:
    """Find a validated pair from saved paths, PATH, or a companion folder."""
    ffmpeg = _working_candidate(configured_ffmpeg, "ffmpeg", path_lookup, runner)
    ffprobe = _working_candidate(configured_ffprobe, "ffprobe", path_lookup, runner)
    if ffmpeg is not None and ffprobe is None:
        companion = ffmpeg.with_name("ffprobe.exe")
        if validate_media_tool(companion, "ffprobe", runner) is None:
            ffprobe = companion.resolve()
    if ffprobe is not None and ffmpeg is None:
        companion = ffprobe.with_name("ffmpeg.exe")
        if validate_media_tool(companion, "ffmpeg", runner) is None:
            ffmpeg = companion.resolve()
    if ffmpeg is None or ffprobe is None:
        return None
    return MediaToolPaths(ffmpeg.resolve(), ffprobe.resolve())


def _working_candidate(
    configured: Path | None,
    name: str,
    path_lookup: PathLookup,
    runner: Runner,
) -> Path | None:
    candidates: list[Path] = []
    if configured is not None:
        candidates.append(configured)
    discovered = path_lookup(name)
    if discovered:
        candidates.append(Path(discovered))
    executable_name = f"{name}.exe"
    candidates.extend(
        [
            Path(sys.executable).resolve().parent / executable_name,
            Path.cwd() / executable_name,
        ]
    )
    for variable, suffix in (
        ("ProgramFiles", Path("ffmpeg/bin")),
        ("LOCALAPPDATA", Path("Microsoft/WinGet/Links")),
        ("ChocolateyToolsLocation", Path("ffmpeg/bin")),
    ):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / suffix / executable_name)
    for candidate in candidates:
        if validate_media_tool(candidate, name, runner) is None:
            return candidate.resolve()
    return None


class MediaToolSettingsStore:
    """Persist validated media-tool paths without disturbing other .env values."""

    _KEYS = ("FFMPEG_PATH", "FFPROBE_PATH")

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()

    def save(self, values: MediaToolPaths) -> None:
        replacements = {
            "FFMPEG_PATH": values.ffmpeg.as_posix(),
            "FFPROBE_PATH": values.ffprobe.as_posix(),
        }
        existing = self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []
        output: list[str] = []
        written: set[str] = set()
        for line in existing:
            key = line.split("=", 1)[0].strip() if "=" in line else ""
            if key in replacements:
                output.append(f"{key}={replacements[key]}")
                written.add(key)
            else:
                output.append(line)
        for key in self._KEYS:
            if key not in written:
                output.append(f"{key}={replacements[key]}")
        self.path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8", newline="\n")
