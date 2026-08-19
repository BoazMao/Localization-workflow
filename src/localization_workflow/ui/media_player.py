"""Reusable native media player widget."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget


def format_milliseconds(value: int) -> str:
    """Format milliseconds as hours/minutes/seconds."""
    seconds = max(0, value // 1000)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


class MediaPlayerWidget(QWidget):
    """Video/audio playback controls backed by Qt Multimedia."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._audio.setVolume(0.7)
        self._video = QVideoWidget(self)
        self._video.setMinimumHeight(330)
        self._video.setStyleSheet("background: #111;")
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video)

        self._play_button = QPushButton("Play")
        self._play_button.clicked.connect(self._toggle_playback)
        self._position = QSlider(Qt.Orientation.Horizontal)
        self._position.setRange(0, 0)
        self._position.sliderMoved.connect(self._player.setPosition)
        self._time = QLabel("00:00 / 00:00")
        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setValue(70)
        self._volume.setMaximumWidth(120)
        self._volume.valueChanged.connect(lambda value: self._audio.setVolume(value / 100))

        controls = QHBoxLayout()
        controls.addWidget(self._play_button)
        controls.addWidget(self._position, 1)
        controls.addWidget(self._time)
        controls.addWidget(QLabel("Volume"))
        controls.addWidget(self._volume)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._video, 1)
        layout.addLayout(controls)

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)

    def load(self, path: Path | None) -> None:
        """Load managed media or clear the current player."""
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(str(path)) if path else QUrl())
        self._play_button.setEnabled(path is not None)

    def seek(self, position_ms: int) -> None:
        """Move playback to a transcript timestamp."""
        self._player.setPosition(max(0, position_ms))

    def _toggle_playback(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_position_changed(self, position: int) -> None:
        if not self._position.isSliderDown():
            self._position.setValue(position)
        self._update_time(position, self._player.duration())

    def _on_duration_changed(self, duration: int) -> None:
        self._position.setRange(0, duration)
        self._update_time(self._player.position(), duration)

    def _on_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self._play_button.setText(
            "Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Play"
        )

    def _update_time(self, position: int, duration: int) -> None:
        self._time.setText(f"{format_milliseconds(position)} / {format_milliseconds(duration)}")
