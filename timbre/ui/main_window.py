"""Main window: navigation rail, pages, player bar."""

from __future__ import annotations

import ctypes

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow,
                               QPlainTextEdit, QLineEdit, QPushButton, QStackedWidget, QVBoxLayout,
                               QWidget)

from ..settings import from_dict, Profile
from . import icons
from .devices import DevicesPage
from .batch import BatchPage
from .history import HistoryPage, take_meta
from .player import PlayerBar
from .settings_page import SettingsPage
from .setup import SetupDialog
from .studio import StudioPage
from .theme import P, theme
from .voices import VoicesPage
from .widgets import Toast, label


def set_dark_title_bar(window, dark: bool) -> None:
    try:
        hwnd = int(window.winId())
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


class StatusPill(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.c = controller
        self.dot = QLabel()
        self.text = label("", "Hint", wrap=True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 8, 8)
        lay.setSpacing(8)
        lay.addWidget(self.dot, 0, Qt.AlignTop)
        lay.addWidget(self.text, 1)
        for sig in (controller.engineStateChanged, controller.modelStatusChanged, controller.devicesChanged):
            sig.connect(lambda *_: self.refresh())
        controller.modelProgress.connect(self._progress)
        theme().changed.connect(lambda *_: self.refresh())
        self.refresh()

    def _set(self, color: str, text: str) -> None:
        self.dot.setPixmap(icons.pixmap("dot", color, 14))
        self.text.setText(text)

    def _progress(self, f: float, msg: str) -> None:
        self._set(P().warning, msg if f < 0 else f"{msg}")

    def refresh(self) -> None:
        p, c = P(), self.c
        state = c.engine.state
        if state == "starting":
            self._set(p.warning, "Starting engine")
        elif state in ("stopped", "crashed"):
            self._set(p.danger if state == "crashed" else p.text3,
                      "Engine stopped" if state == "crashed" else "No runtime yet")
        elif c.model_status.get("loaded"):
            dev = c.device_info(c.model_status["device"]) or {"name": c.model_status["device"]}
            name = dev["name"].replace("NVIDIA ", "").replace("GeForce ", "").replace(" Laptop GPU", "")
            self._set(p.success, f"{name} · {c.model_status['precision'].upper()}")
        else:
            self._set(p.text3, "Model not loaded")


class MainWindow(QMainWindow):
    PAGES = [("Studio", "studio"), ("Batch", "batch"), ("Voices", "voices"), ("History", "history"),
             ("Devices", "devices"), ("Settings", "settings")]
    DEVICES = 4

    def __init__(self, controller):
        super().__init__()
        self.c = controller
        self.setWindowTitle("Timbre")
        self.setWindowIcon(QIcon(icons.pixmap("logo", "#2853D6", 256, 1)))
        self.setMinimumSize(1080, 700)
        self.resize(1360, 860)

        # Rail
        rail = QFrame()
        rail.setObjectName("Rail")
        rail.setFixedWidth(208)
        rl = QVBoxLayout(rail)
        rl.setContentsMargins(12, 18, 12, 12)
        rl.setSpacing(2)
        brand = QHBoxLayout()
        brand.setContentsMargins(8, 0, 0, 18)
        self.logo = QLabel()
        brand.addWidget(self.logo)
        brand.addSpacing(8)
        brand.addWidget(label("Timbre", "Wordmark"))
        brand.addStretch(1)
        rl.addLayout(brand)
        self.nav = QButtonGroup(self)
        self.nav_buttons = []
        for i, (text, icon) in enumerate(self.PAGES):
            b = QPushButton(text)
            b.setObjectName("RailButton")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            icons.bind(b, icon, "text2", 18)
            b.setToolTip(f"{text} (Ctrl+{i + 1})")
            self.nav.addButton(b, i)
            self.nav_buttons.append(b)
            rl.addWidget(b)
        rl.addStretch(1)
        rl.addWidget(StatusPill(controller))

        # Pages
        self.player = PlayerBar()
        self.studio = StudioPage(controller, open_devices=lambda: self.go(self.DEVICES))
        self.batch = BatchPage(controller, self.studio)
        self.voices = VoicesPage(controller, self.player)
        self.history_page = HistoryPage(controller)
        self.devices = DevicesPage(controller)
        self.settings_page = SettingsPage(controller, theme())
        self.stack = QStackedWidget()
        for page in (self.studio, self.batch, self.voices, self.history_page, self.devices, self.settings_page):
            self.stack.addWidget(page)

        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(0)
        rlay.addWidget(self.stack, 1)
        rlay.addWidget(self.player)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(rail)
        lay.addWidget(right, 1)
        self.setCentralWidget(central)
        self.toast = Toast(central)

        # Wiring
        self.nav.idClicked.connect(self.go)
        self.go(0)
        for i in range(len(self.PAGES)):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, activated=lambda i=i: self.go(i))

        c = controller
        c.toast.connect(self.toast.show_message)
        c.generationFinished.connect(self._take_ready)
        c.needsSetup.connect(self._needs_setup)
        self.player.saveVoiceRequested.connect(self._save_voice)
        self.voices.useVoice.connect(self._use_voice)
        self.history_page.reuseTake.connect(self._reuse)
        self.history_page.playTake.connect(lambda item: item and self._play_history(item))
        self.batch.playTake.connect(self._play_history)
        self.batch.openStudio.connect(lambda: self.go(0))
        theme().changed.connect(self._theme_changed)
        self._theme_changed(P())

        if c.settings.geometry:
            self.restoreGeometry(QByteArray.fromBase64(c.settings.geometry.encode()))

    # -------------------------------------------------------------- actions
    def go(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)

    def keyPressEvent(self, e) -> None:
        # Space reaches the window only when the focused widget didn't use it
        # (text fields and buttons do), so it never steals typing.
        if e.key() == Qt.Key_Space and not e.modifiers():
            self.player.toggle()
            return
        super().keyPressEvent(e)

    def _player_item(self, item, mode: str = "") -> dict:
        return {"path": item.path, "title": item.text.replace("\n", " ")[:60] or "Take",
                "meta": take_meta(item), "peaks": item.peaks, "duration": item.duration, "text": item.text,
                "can_save_voice": True, "suggested_name": f"{item.voice_label} take",
                "source": "design" if mode == "design" else "generation"}

    def _take_ready(self, item) -> None:
        # Batch takes load into the player quietly instead of playing over each other.
        autoplay = not getattr(item, "from_batch", False)
        self.player.load(self._player_item(item, item.profile.get("voice", {}).get("mode", "")), autoplay=autoplay)

    def _play_history(self, item) -> None:
        self.player.load(self._player_item(item), autoplay=True)

    def _save_voice(self, item: dict) -> None:
        self.voices.save_from_take(item)

    def _use_voice(self, vid: str) -> None:
        p = self.studio.inspector.profile()
        p.voice.mode = "clone"
        p.voice.library_id = vid
        self.studio.load_profile_dict(p)
        self.go(0)

    def _reuse(self, item) -> None:
        if item:
            self.studio.load_profile_dict(from_dict(Profile, item.profile), item.text)
            self.go(0)
            self.toast.show_message("Loaded the text and settings from that take.")

    def _needs_setup(self) -> None:
        QTimer.singleShot(250, self._run_setup)

    def _run_setup(self) -> None:
        if SetupDialog(self.c, self).exec():
            self.c.start_engine()
        else:
            self.go(self.DEVICES)

    def _theme_changed(self, palette) -> None:
        icons.refresh_all()
        self.logo.setPixmap(icons.pixmap("logo", palette.accent, 22))
        set_dark_title_bar(self, palette.name == "dark")

    def closeEvent(self, e) -> None:
        self.studio.persist()
        self.c.settings.geometry = bytes(self.saveGeometry().toBase64()).decode()
        self.player.stop()
        self.c.shutdown()
        super().closeEvent(e)
