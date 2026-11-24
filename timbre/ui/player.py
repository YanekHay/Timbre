"""Waveform view and the persistent player bar."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from . import icons
from .theme import P, theme
from .widgets import icon_button, label


def fmt_time(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60}:{seconds % 60:02d}"


def reveal_in_explorer(path: str) -> None:
    if path and Path(path).exists():
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    elif path:
        folder = Path(path).parent
        if folder.exists():
            os.startfile(folder)


class Waveform(QWidget):
    seek = Signal(float)   # 0..1

    def __init__(self, parent=None, bar: float = 2.0, gap: float = 1.5):
        super().__init__(parent)
        self.peaks: list[float] = []
        self.progress = 0.0
        self.hover: float | None = None
        self.bar, self.gap = bar, gap
        self.busy = False
        self.setMouseTracking(True)
        self.setMinimumHeight(36)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        theme().changed.connect(lambda *_: self.update())

    def set_peaks(self, peaks: list[float]) -> None:
        self.peaks = peaks or []
        self.progress = 0.0
        self.update()

    def set_progress(self, f: float) -> None:
        self.progress = max(0.0, min(1.0, f))
        self.update()

    def _resampled(self, n: int) -> list[float]:
        src = self.peaks
        if not src or n <= 0:
            return []
        out = []
        for i in range(n):
            a = int(i * len(src) / n)
            b = max(a + 1, int((i + 1) * len(src) / n))
            out.append(max(src[a:b]))
        return out

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = P()
        w, h = self.width(), self.height()
        mid = h / 2
        step = self.bar + self.gap
        n = max(1, int(w / step))
        values = self._resampled(n)
        if not values:
            p.setPen(QColor(pal.border_strong))
            p.drawLine(QPointF(0, mid), QPointF(w, mid))
            return
        played = QColor(pal.accent)
        rest = QColor(pal.wave)
        hover_col = QColor(pal.accent)
        hover_col.setAlpha(110)
        p.setPen(Qt.NoPen)
        for i, v in enumerate(values):
            x = i * step
            frac = (x + self.bar / 2) / w
            bh = max(2.0, (v ** 0.8) * (h - 4))
            if frac <= self.progress:
                p.setBrush(played)
            elif self.hover is not None and frac <= self.hover:
                p.setBrush(hover_col)
            else:
                p.setBrush(rest)
            p.drawRoundedRect(QRectF(x, mid - bh / 2, self.bar, bh), 1, 1)

    def mouseMoveEvent(self, e):
        self.hover = max(0.0, min(1.0, e.position().x() / max(1, self.width())))
        self.update()

    def leaveEvent(self, _):
        self.hover = None
        self.update()

    def mousePressEvent(self, e):
        if self.peaks:
            self.seek.emit(max(0.0, min(1.0, e.position().x() / max(1, self.width()))))


class PlayerBar(QFrame):
    """Plays the selected take. Shared by Studio, History and Voices."""

    saveVoiceRequested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PlayerBar")
        self.setFixedHeight(76)
        self.item: dict | None = None

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(1.0)
        self.player.setAudioOutput(self.audio)

        self.play = icon_button("play", "Play (Space)", "bg", 16)
        self.play.setFixedSize(40, 40)
        self.play.setObjectName("PlayButton")
        self.title = label("Nothing to play yet")
        self.title.setMaximumWidth(260)
        self.meta = label("Generated takes appear here", "Hint")
        self.time = label("0:00 / 0:00", "Mono")
        self.wave = Waveform()
        self.reveal = icon_button("folder", "Show in folder")
        self.copy = icon_button("copy", "Copy file path")
        self.save_voice = icon_button("save", "Save this voice to your library")
        for b in (self.reveal, self.copy, self.save_voice):
            b.setEnabled(False)
        self.play.setEnabled(False)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(self.title)
        texts.addWidget(self.meta)
        info = QWidget()
        info.setLayout(texts)
        info.setFixedWidth(260)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 10, 16, 10)
        lay.setSpacing(14)
        lay.addWidget(self.play)
        lay.addWidget(info)
        lay.addWidget(self.wave, 1)
        lay.addWidget(self.time)
        lay.addSpacing(4)
        lay.addWidget(self.save_voice)
        lay.addWidget(self.copy)
        lay.addWidget(self.reveal)

        self.play.clicked.connect(self.toggle)
        self.wave.seek.connect(self._seek)
        self.reveal.clicked.connect(lambda: self.item and reveal_in_explorer(self.item["path"]))
        self.copy.clicked.connect(lambda: self.item and QGuiApplication.clipboard().setText(self.item["path"]))
        self.save_voice.clicked.connect(lambda: self.item and self.saveVoiceRequested.emit(self.item))
        self.player.positionChanged.connect(self._position)
        self.player.playbackStateChanged.connect(self._state)
        self.player.mediaStatusChanged.connect(self._status)

    # item: {path, title, meta, peaks, duration, text, can_save_voice}
    def load(self, item: dict, autoplay: bool = False) -> None:
        self.player.stop()
        self.item = item
        self.title.setText(item.get("title", Path(item["path"]).name))
        self.title.setToolTip(item.get("text", ""))
        self.meta.setText(item.get("meta", ""))
        self.wave.set_peaks(item.get("peaks", []))
        self.time.setText(f"0:00 / {fmt_time(item.get('duration', 0))}")
        exists = Path(item["path"]).exists()
        for b in (self.reveal, self.copy, self.play):
            b.setEnabled(exists)
        self.save_voice.setEnabled(exists and bool(item.get("can_save_voice")))
        self.player.setSource(QUrl.fromLocalFile(item["path"]))
        if autoplay and exists:
            self.player.play()

    def toggle(self) -> None:
        if not self.item:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def stop(self) -> None:
        self.player.stop()

    def _seek(self, f: float) -> None:
        if self.player.duration() > 0:
            self.player.setPosition(int(f * self.player.duration()))
            if self.player.playbackState() != QMediaPlayer.PlayingState:
                self.player.play()

    def _position(self, ms: int) -> None:
        dur = self.player.duration() or int((self.item or {}).get("duration", 0) * 1000)
        if dur:
            self.wave.set_progress(ms / dur)
        self.time.setText(f"{fmt_time(ms / 1000)} / {fmt_time(dur / 1000)}")

    def _state(self, state) -> None:
        playing = state == QMediaPlayer.PlayingState
        icons.bind(self.play, "pause" if playing else "play", "bg", 16)
        self.play.setToolTip("Pause (Space)" if playing else "Play (Space)")

    def _status(self, status) -> None:
        if status == QMediaPlayer.EndOfMedia:
            self.wave.set_progress(0)
            self.player.setPosition(0)
            self.player.pause()
