"""Speech-to-text provider boundary and Const-me/Whisper adapter."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Protocol


class TranscriptionError(RuntimeError):
    """The configured speech-to-text provider could not transcribe audio."""


class TranscriptionCancelled(TranscriptionError):
    """The user cancelled transcription."""


@dataclass(frozen=True, slots=True)
class ProviderSegment:
    """Provider-neutral timestamped text."""

    start_ms: int
    end_ms: int
    text: str


ProgressCallback = Callable[[int], None]


class SpeechToTextProvider(Protocol):
    """Provider-neutral local transcription contract."""

    @property
    def model_name(self) -> str: ...

    def select_model(self, path: Path) -> None: ...

    def transcribe(
        self,
        audio_path: Path,
        language: str,
        prompt: str | None,
        progress: ProgressCallback,
        cancel: Event,
    ) -> list[ProviderSegment]: ...


_TIME_PATTERN = re.compile(
    r"^(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d{2})[,.](?P<millis>\d{3})$"
)


def parse_subrip(text: str) -> list[ProviderSegment]:
    """Normalize a WhisperPS SubRip export into validated segments."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    segments: list[ProviderSegment] = []
    for block in re.split(r"\n\s*\n", normalized):
        lines = block.splitlines()
        if len(lines) < 3 or "-->" not in lines[1]:
            raise TranscriptionError("Whisper produced an invalid subtitle block.")
        start_raw, end_raw = (part.strip() for part in lines[1].split("-->", maxsplit=1))
        start_ms = _parse_timestamp(start_raw)
        end_ms = _parse_timestamp(end_raw)
        segment_text = "\n".join(lines[2:]).strip()
        if end_ms <= start_ms:
            raise TranscriptionError("Whisper produced an invalid segment duration.")
        if not segment_text:
            continue
        segments.append(ProviderSegment(start_ms, end_ms, segment_text))
    return segments


_CLI_SEGMENT_PATTERN = re.compile(
    r"^\s*\[(?P<start>\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"
    r"(?P<end>\d{2}:\d{2}:\d{2}[,.]\d{3})\]\s*(?P<text>.+?)\s*$"
)


def parse_cli_output(output: str) -> list[ProviderSegment]:
    """Extract native timestamped segments from the official Const-me CLI output."""
    segments: list[ProviderSegment] = []
    for line in output.splitlines():
        match = _CLI_SEGMENT_PATTERN.match(line)
        if match is None:
            continue
        start_ms = _parse_timestamp(match["start"])
        end_ms = _parse_timestamp(match["end"])
        text = match["text"].strip()
        if end_ms <= start_ms or not text:
            continue
        segments.append(ProviderSegment(start_ms, end_ms, text))
    return segments


def _parse_timestamp(value: str) -> int:
    match = _TIME_PATTERN.fullmatch(value)
    if match is None:
        raise TranscriptionError(f"Whisper produced an invalid timestamp: {value}")
    return (
        int(match["hours"]) * 3_600_000
        + int(match["minutes"]) * 60_000
        + int(match["seconds"]) * 1_000
        + int(match["millis"])
    )


class ConstMeWhisperProvider:
    """Invoke the official unmodified Const-me Whisper command-line engine."""

    def __init__(
        self,
        model_path: Path | None,
        cli_executable: Path | None,
    ) -> None:
        self._model_path = model_path.resolve() if model_path else None
        self._cli_executable = cli_executable.resolve() if cli_executable else None

    @property
    def model_name(self) -> str:
        return self._model_path.name if self._model_path else "Not configured"

    def select_model(self, path: Path) -> None:
        """Use a new managed model for subsequent transcription jobs."""
        self._model_path = path.resolve()

    def transcribe(
        self,
        audio_path: Path,
        language: str,
        prompt: str | None,
        progress: ProgressCallback,
        cancel: Event,
    ) -> list[ProviderSegment]:
        if self._model_path is None or not self._model_path.is_file():
            raise TranscriptionError(
                "No Whisper model is configured. Set WHISPER_MODEL_PATH to a ggml model file."
            )
        if self._cli_executable is None or not self._cli_executable.is_file():
            raise TranscriptionError(
                "The Const-me/Whisper CLI is not configured. Set WHISPER_CLI_PATH to main.exe."
            )
        if not audio_path.is_file():
            raise TranscriptionError(f"Transcription audio was not found: {audio_path}")
        if not language.strip() or language.casefold() == "auto-detect":
            raise TranscriptionError("Choose the spoken source language before transcribing.")

        language_code = _language_code(language)
        command = [
            str(self._cli_executable),
            "-m",
            str(self._model_path),
            "-l",
            language_code,
            "-f",
            str(audio_path.resolve()),
            "-nc",
        ]
        if prompt and prompt.strip():
            command.extend(("--prompt", prompt.strip()))
        progress(5)
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            while True:
                try:
                    output, _ = process.communicate(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    if cancel.is_set():
                        process.terminate()
                        raise TranscriptionCancelled("Transcription was cancelled.") from None
            if process.returncode != 0:
                raise TranscriptionError(output.strip() or "Whisper transcription failed.")
            progress(95)
            segments = parse_cli_output(output)
            if not segments:
                raise TranscriptionError("Whisper did not detect timestamped speech.")
            progress(100)
            return segments
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


_LANGUAGE_CODES = {
    "arabic": "ar",
    "chinese": "zh",
    "dutch": "nl",
    "english": "en",
    "french": "fr",
    "german": "de",
    "hebrew": "he",
    "hindi": "hi",
    "italian": "it",
    "japanese": "ja",
    "korean": "ko",
    "polish": "pl",
    "portuguese": "pt",
    "russian": "ru",
    "spanish": "es",
    "swedish": "sv",
    "turkish": "tr",
    "ukrainian": "uk",
    "vietnamese": "vi",
}


def _language_code(language: str) -> str:
    normalized = language.strip().casefold()
    if len(normalized) == 2 and normalized.isalpha():
        return normalized
    code = _LANGUAGE_CODES.get(normalized)
    if code is None:
        raise TranscriptionError(
            f'Unsupported source language "{language}". Use a language name or ISO 639-1 code.'
        )
    return code
