"""Settings: appearance, storage locations, about."""

from __future__ import annotations

import os

from PySide6.QtWidgets import QVBoxLayout, QWidget

from .. import __version__, paths
from .widgets import Card, Field, PageHeader, PathField, Segmented, button, hbox, label, scroll_page, vbox


class SettingsPage(QWidget):
    def __init__(self, controller, theme_manager):
        super().__init__()
        self.setObjectName("Page")
        self.c = controller
        self.t = theme_manager

        appearance = Card()
        self.theme = Segmented([("System", "system"), ("Light", "light"), ("Dark", "dark")])
        self.theme.set_value(self.c.settings.theme)
        self.theme.changed.connect(self._theme)
        self.theme.setMaximumWidth(320)
        appearance.add(label("Appearance", "SectionTitle"), Field("Theme", self.theme))

        storage = Card()
        self.hf_home = PathField("Default Hugging Face cache", directory=True)
        self.hf_home.set_value(self.c.settings.hf_home)
        self.hf_home.changed.connect(self._hf_home)
        open_data = button("Open Timbre's data folder", icon="folder")
        open_data.clicked.connect(lambda: os.startfile(paths.data_dir()))
        storage.add(label("Storage", "SectionTitle"),
                    Field("Model download folder", self.hf_home,
                          "Where model weights are cached (about 2 GB). Leave empty to share the standard "
                          "Hugging Face cache with other apps. Takes effect after the engine restarts."),
                    Field("App data", None, f"Settings, voices, profiles, runtimes and history live in {paths.data_dir()}"),
                    hbox(open_data, None))

        about = Card()
        about.add(label("About", "SectionTitle"),
                  label(f"Timbre {__version__}", "Muted"),
                  label("Speech by Ming-3.0-tts-0.5B (inclusionAI, MIT licence). Interface built with Qt for Python "
                        "(LGPL). Voices you clone must be yours or used with permission.", "Hint", wrap=True))

        content = QWidget()
        content.setLayout(vbox(PageHeader("Settings"), appearance, storage, about, None,
                               spacing=18, margins=(28, 24, 28, 24)))
        content.setMaximumWidth(860)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll_page(content))

    def _theme(self, mode: str) -> None:
        self.c.settings.theme = mode
        self.c.save()
        self.t.apply(mode)

    def _hf_home(self, path: str) -> None:
        self.c.settings.hf_home = path.strip()
        self.c.save()
