import json
import subprocess
from pathlib import Path

import pytest

from localization_workflow.infrastructure.media import FFprobeMediaProbe, MediaError


def test_ffprobe_normalizes_video_and_audio_streams(tmp_path: Path) -> None:
    executable = tmp_path / "ffprobe.exe"
    executable.touch()
    payload = {
        "format": {"duration": "65.125"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }

    def runner(*_args, **_kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, json.dumps(payload), "")

    info = FFprobeMediaProbe(executable, runner).probe(tmp_path / "clip.mp4")

    assert info.duration_ms == 65_125
    assert info.media_type == "video"
    assert info.video_codec == "h264"
    assert info.audio_codec == "aac"
    assert (info.width, info.height) == (1280, 720)


def test_ffprobe_rejects_media_without_streams(tmp_path: Path) -> None:
    executable = tmp_path / "ffprobe.exe"
    executable.touch()

    def runner(*_args, **_kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, '{"format": {}, "streams": []}', "")

    with pytest.raises(MediaError, match="no supported"):
        FFprobeMediaProbe(executable, runner).probe(tmp_path / "empty.mp4")
