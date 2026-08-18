import subprocess
import wave
from pathlib import Path
from threading import Event

from localization_workflow.infrastructure.audio import FFmpegAudioProcessor


def write_wav(path: Path, channels: int = 1, rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"\x00\x00" * rate)


def test_audio_processor_reuses_valid_existing_wav(tmp_path: Path) -> None:
    executable = tmp_path / "ffmpeg.exe"
    executable.touch()
    destination = tmp_path / "derived" / "project-1" / "transcription.wav"
    destination.parent.mkdir(parents=True)
    write_wav(destination)
    progress: list[int] = []

    result = FFmpegAudioProcessor(tmp_path / "derived", executable).prepare(
        "project-1", tmp_path / "source.mp4", 1000, progress.append, Event(), True
    )

    assert result == destination
    assert progress == [100]


def test_audio_processor_creates_canonical_wav(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "ffmpeg.exe"
    executable.touch()

    class FakeProcess:
        stdout = iter(("out_time_ms=500000\n", "progress=end\n"))
        stderr = None

        def wait(self) -> int:
            destination = tmp_path / "derived" / "project-2" / "transcription.partial.wav"
            write_wav(destination)
            return 0

        def poll(self) -> int:
            return 0

        def terminate(self) -> None:
            pass

        def kill(self) -> None:
            pass

    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess())
    progress: list[int] = []

    result = FFmpegAudioProcessor(tmp_path / "derived", executable).prepare(
        "project-2", tmp_path / "source.mp4", 1000, progress.append, Event(), False
    )

    assert result.name == "transcription.wav"
    assert result.exists()
    assert progress == [50, 100]


def test_audio_processor_overwrites_valid_wav_when_reuse_is_disabled(
    monkeypatch, tmp_path: Path
) -> None:
    executable = tmp_path / "ffmpeg.exe"
    executable.touch()
    destination = tmp_path / "derived" / "project-3" / "transcription.wav"
    destination.parent.mkdir(parents=True)
    write_wav(destination)
    original_modified = destination.stat().st_mtime_ns

    class FakeProcess:
        stdout = iter(("progress=end\n",))
        stderr = None

        def wait(self) -> int:
            temporary = destination.with_name("transcription.partial.wav")
            write_wav(temporary, rate=16000)
            temporary.write_bytes(temporary.read_bytes() + b"replacement")
            return 0

        def poll(self) -> int:
            return 0

        def terminate(self) -> None:
            pass

        def kill(self) -> None:
            pass

    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess())

    result = FFmpegAudioProcessor(tmp_path / "derived", executable).prepare(
        "project-3", tmp_path / "new-source.mp4", 1000, lambda _value: None, Event(), False
    )

    assert result == destination
    assert destination.stat().st_mtime_ns >= original_modified
    assert destination.read_bytes().endswith(b"replacement")
