"""First-run setup: detect hardware and install the matching compute runtime."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QFileDialog, QVBoxLayout

from .. import hardware, runtime
from ..hardware import human_bytes
from . import icons
from .devices import InstallDialog
from .theme import P
from .widgets import Card, Combo, button, hbox, label, vbox


class SetupDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.c = controller
        self.setWindowTitle("Set up Timbre")
        self.setMinimumWidth(560)
        gpus = hardware.gpus()
        self.variants = runtime.variants()
        rec = self.variants[hardware.recommended_variant(gpus)]

        logo = label()
        logo.setPixmap(icons.pixmap("logo", P().accent, 40))
        title = label("Welcome to Timbre", "PageTitle")
        intro = label("Timbre generates speech on your own computer, so nothing you write leaves it. "
                      "It needs a one-time download of a compute runtime that matches your graphics card.",
                      "Muted", wrap=True)

        found = Card(padding=14, spacing=6, name="Inset")
        found.add(label("FOUND ON THIS PC", "Overline"))
        for g in gpus or []:
            found.add(hbox(label(g.name), None, label(human_bytes(g.vram) + " VRAM", "Value")))
        if not gpus:
            found.add(label("No dedicated graphics card. Timbre will use the CPU.", "Muted"))

        rec_card = Card(padding=16, spacing=8)
        install = button(f"Install {rec.label} · {rec.download_gb:g} GB", "primary", "download")
        install.clicked.connect(lambda: self._install(rec))
        rec_card.add(label("RECOMMENDED", "Overline"), label(rec.label, "SectionTitle"),
                     label(rec.summary, "Muted", wrap=True), hbox(None, install))

        self.other = Combo([(f"{v.label} · {v.download_gb:g} GB", k) for k, v in self.variants.items() if k != rec.key])
        other_btn = button("Install")
        other_btn.clicked.connect(lambda: self._install(self.variants[self.other.value()]))
        existing = button("Use an existing Python environment…", "link")
        existing.clicked.connect(self._existing)
        later = button("Not now", "ghost")
        later.clicked.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 26, 28, 22)
        lay.setSpacing(16)
        lay.addLayout(hbox(logo, vbox(title, spacing=0), None, spacing=12))
        lay.addWidget(intro)
        lay.addWidget(found)
        lay.addWidget(rec_card)
        lay.addLayout(hbox(label("Or install", "Muted"), self.other, other_btn, spacing=8))
        lay.addLayout(hbox(existing, None, later))

    def _install(self, variant) -> None:
        dlg = InstallDialog(variant, parent=self)
        dlg.exec()
        if dlg.ok:
            s = self.c.settings
            s.runtime_variant, s.python_path, s.setup_done = variant.key, "", True
            self.c.save()
            self.accept()

    def _existing(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose python.exe", "", "Python (python.exe)")
        if path:
            s = self.c.settings
            s.python_path, s.setup_done = path, True
            self.c.save()
            self.accept()
