"""Voices: the user's saved reference voices for cloning."""

from __future__ import annotations

import re
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QInputDialog, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QVBoxLayout, QWidget)

from .widgets import (Card, Field, PageHeader, PathField, badge, button, hbox, icon_button, label,
                      vbox)


class VoiceDialog(QDialog):
    def __init__(self, parent=None, name="", audio="", transcript="", notes="", audio_locked=False):
        super().__init__(parent)
        self.setWindowTitle("Save voice")
        self.setMinimumWidth(460)
        self.name = QLineEdit(name)
        self.name.setPlaceholderText("e.g. Deep narrator")
        self.audio = PathField("Recording", filter="Audio (*.wav *.flac *.mp3 *.ogg)")
        self.audio.set_value(audio)
        self.audio.setEnabled(not audio_locked)
        self.transcript = QPlainTextEdit(transcript)
        self.transcript.setPlaceholderText("Exactly what is said in the recording")
        self.transcript.setFixedHeight(90)
        self.notes = QLineEdit(notes)
        self.notes.setPlaceholderText("Optional")
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setProperty("variant", "primary")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(14)
        lay.addWidget(label("Save voice", "PageTitle"))
        lay.addWidget(label("A saved voice is a short recording plus its transcript. "
                            "Use it in Studio → Clone.", "Muted", wrap=True))
        lay.addWidget(Field("Name", self.name))
        lay.addWidget(Field("Recording", self.audio, "3–20 seconds of clean speech works best."))
        lay.addWidget(Field("Transcript", self.transcript))
        lay.addWidget(Field("Notes", self.notes))
        lay.addWidget(buttons)

    def _accept(self) -> None:
        if not self.name.text().strip() or not self.audio.value() or not self.transcript.toPlainText().strip():
            QMessageBox.information(self, "Save voice", "Add a name, a recording and its transcript.")
            return
        self.accept()

    def values(self) -> dict:
        return {"name": self.name.text().strip(), "audio_path": self.audio.value(),
                "transcript": self.transcript.toPlainText().strip(), "notes": self.notes.text().strip()}


class VoiceRow(QWidget):
    play = Signal(str)
    use = Signal(str)
    rename = Signal(str)
    remove = Signal(str)

    def __init__(self, voice):
        super().__init__()
        name = label(voice.name, "SectionTitle")
        source = {"design": "Designed", "generation": "From a take", "file": "Recording"}.get(voice.source, "Recording")
        when = datetime.fromtimestamp(voice.created).strftime("%d %b %Y")
        meta = label(f"{when}" + (f" · {voice.notes}" if voice.notes else ""), "Hint")
        transcript = label("“" + (voice.transcript[:140] + ("…" if len(voice.transcript) > 140 else "")) + "”",
                           "Muted", wrap=True)
        play = icon_button("play", "Preview")
        use = button("Use in Studio")
        more_rename = icon_button("file", "Rename")
        delete = icon_button("trash", "Delete")
        play.clicked.connect(lambda: self.play.emit(voice.id))
        use.clicked.connect(lambda: self.use.emit(voice.id))
        more_rename.clicked.connect(lambda: self.rename.emit(voice.id))
        delete.clicked.connect(lambda: self.remove.emit(voice.id))
        text = QWidget()
        text.setLayout(vbox(hbox(name, badge(source), None, spacing=8), transcript, meta, spacing=4))
        self.setLayout(hbox(play, text, use, more_rename, delete, spacing=10, margins=(12, 12, 12, 12)))
        self.layout().setStretch(1, 1)


class VoicesPage(QWidget):
    useVoice = Signal(str)

    def __init__(self, controller, player):
        super().__init__()
        self.setObjectName("Page")
        self.c = controller
        self.player = player
        add = button("Add voice", "primary", "plus")
        add.clicked.connect(self.add_voice)
        header = PageHeader("Voices", "Saved recordings you can clone in Studio.", [add])
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.NoSelection)
        self.list.setSpacing(4)
        self.empty = label("No saved voices yet.\nAdd a recording here, or save a take you like from the player.",
                           "Muted", wrap=True)
        self.empty.setAlignment(Qt.AlignCenter)
        card = Card(padding=8)
        card.add(self.list, self.empty)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(18)
        root.addWidget(header)
        root.addWidget(card, 1)
        self.c.library.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        for v in self.c.library.voices:
            row = VoiceRow(v)
            row.play.connect(self._play)
            row.use.connect(self.useVoice.emit)
            row.rename.connect(self._rename)
            row.remove.connect(self._remove)
            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
        empty = not self.c.library.voices
        self.empty.setVisible(empty)
        self.list.setVisible(not empty)

    def _play(self, vid: str) -> None:
        v = self.c.library.get(vid)
        if v:
            self.player.load({"path": v.audio, "title": v.name, "meta": "Saved voice · reference",
                              "peaks": [], "duration": 0, "text": v.transcript}, autoplay=True)

    def _rename(self, vid: str) -> None:
        v = self.c.library.get(vid)
        if not v:
            return
        name, ok = QInputDialog.getText(self, "Rename voice", "Name", text=v.name)
        if ok and name.strip():
            v.name = name.strip()
            self.c.library.update(v)

    def _remove(self, vid: str) -> None:
        v = self.c.library.get(vid)
        if v and QMessageBox.question(self, "Delete voice",
                                      f"Delete “{v.name}”? Its reference recording is removed from Timbre's "
                                      f"library folder.") == QMessageBox.Yes:
            self.c.library.remove(vid)

    def add_voice(self, audio: str = "", transcript: str = "", name: str = "", source: str = "file") -> None:
        dlg = VoiceDialog(self, name=name, audio=audio, transcript=transcript, audio_locked=bool(audio))
        if dlg.exec() == QDialog.Accepted:
            vals = dlg.values()
            self.c.library.add(vals["name"], vals["audio_path"], vals["transcript"], vals["notes"], source=source)
            self.c.toast.emit(f"Saved “{vals['name']}” to Voices.")

    def save_from_take(self, item: dict) -> None:
        transcript = re.sub(r"\s*\[[^\]]+\]\s*", " ", item.get("text", "")).strip()
        self.add_voice(item["path"], transcript, item.get("suggested_name", ""),
                       source=item.get("source", "generation"))
