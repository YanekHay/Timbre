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
        from ..paths import models_dir
        self.models = PathField(str(models_dir()), directory=True)
        self.models.set_value(self.c.settings.models_dir)
        self.models.changed.connect(self._models_dir)
        open_data = button("Open Timbre's data folder", icon="folder")
        open_data.clicked.connect(lambda: os.startfile(paths.data_dir()))
        storage.add(label("Storage", "SectionTitle"),
                    Field("Model folder", self.models,
                          "Where the model weights are downloaded (about 3 GB, once). Leave empty for the default. "
                          "Changing it doesn't move an existing download; Timbre downloads again into the new folder "
                          "the next time the model loads."),
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

    def _models_dir(self, path: str) -> None:
        self.c.settings.models_dir = path.strip()
        self.c.save()
