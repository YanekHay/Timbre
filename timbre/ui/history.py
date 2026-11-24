"""History: every take, searchable, with one-click reuse of its settings."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QFile, Qt, Signal
from PySide6.QtWidgets import QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QVBoxLayout, QWidget

from .player import fmt_time, reveal_in_explorer
from .widgets import Card, PageHeader, badge, button, hbox, icon_button, label, vbox


def ago(ts: float) -> str:
    d = time.time() - ts
    if d < 60:
        return "just now"
    if d < 3600:
        return f"{int(d // 60)} min ago"
    if d < 86400:
        return f"{int(d // 3600)} h ago"
    return time.strftime("%d %b %Y", time.localtime(ts))


def format_label(fmt: str) -> str:
    base, _, depth = fmt.partition("-")
    depth_label = {"16": "16-bit", "24": "24-bit", "32f": "32-bit float"}.get(depth, "")
    return f"{base.upper()} {depth_label}".strip()


def take_meta(item) -> str:
    sr = f"{item.sample_rate / 1000:g} kHz"
    return f"{item.voice_label} · {fmt_time(item.duration)} · {format_label(item.format)} · {sr}"


class TakeRow(QWidget):
    play = Signal(str)
    reuse = Signal(str)
    reveal = Signal(str)
    remove = Signal(str)

    def __init__(self, item):
        super().__init__()
        missing = not Path(item.path).exists()
        text = item.text.replace("\n", " ")
        title = label(text[:160] + ("…" if len(text) > 160 else ""), wrap=True)
        meta = label(f"{take_meta(item)} · {ago(item.created)}", "Hint")
        play = icon_button("play", "Play")
        play.setEnabled(not missing)
        reuse = button("Reuse settings")
        reveal = icon_button("folder", "Show in folder")
        delete = icon_button("trash", "Remove from history")
        body = QWidget()
        rows = [title, hbox(meta, badge("File missing", "warning") if missing else None, None)]
        body.setLayout(vbox(*rows, spacing=4))
        play.clicked.connect(lambda: self.play.emit(item.id))
        reuse.clicked.connect(lambda: self.reuse.emit(item.id))
        reveal.clicked.connect(lambda: self.reveal.emit(item.id))
        delete.clicked.connect(lambda: self.remove.emit(item.id))
        self.setLayout(hbox(play, body, reuse, reveal, delete, spacing=10, margins=(12, 10, 12, 10)))
        self.layout().setStretch(1, 1)


class HistoryPage(QWidget):
    reuseTake = Signal(object)
    playTake = Signal(object)

    def __init__(self, controller):
        super().__init__()
        self.setObjectName("Page")
        self.c = controller
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search takes")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(240)
        clear = button("Clear history", variant="ghost", icon="trash")
        clear.clicked.connect(self._clear)
        header = PageHeader("History", "Every take you generate, newest first.", [self.search, clear])
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.NoSelection)
        self.list.setSpacing(2)
        self.empty = label("Nothing here yet. Generated takes show up here.", "Muted")
        self.empty.setAlignment(Qt.AlignCenter)
        card = Card(padding=8)
        card.add(self.list, self.empty)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(18)
        root.addWidget(header)
        root.addWidget(card, 1)
        self.search.textChanged.connect(self.refresh)
        self.c.history.changed.connect(self.refresh)
        self.refresh()

    def _find(self, hid):
        return next((i for i in self.c.history.items if i.id == hid), None)

    def refresh(self) -> None:
        q = self.search.text().strip().lower()
        self.list.clear()
        shown = 0
        for item in self.c.history.items:
            if q and q not in item.text.lower() and q not in item.voice_label.lower():
                continue
            row = TakeRow(item)
            row.play.connect(lambda hid: self.playTake.emit(self._find(hid)))
            row.reuse.connect(lambda hid: self.reuseTake.emit(self._find(hid)))
            row.reveal.connect(lambda hid: reveal_in_explorer(self._find(hid).path))
            row.remove.connect(self._remove)
            li = QListWidgetItem()
            li.setSizeHint(row.sizeHint())
            self.list.addItem(li)
            self.list.setItemWidget(li, row)
            shown += 1
            if shown >= 200:
                break
        self.empty.setVisible(shown == 0)
        self.list.setVisible(shown > 0)
        self.empty.setText("No takes match your search." if q and self.c.history.items
                           else "Nothing here yet. Generated takes show up here.")

    def _remove(self, hid: str) -> None:
        item = self._find(hid)
        if not item:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Remove take")
        box.setText("Remove this take from history?")
        keep = box.addButton("Remove, keep file", QMessageBox.AcceptRole)
        trash = box.addButton("Remove and move file to Recycle Bin", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        if box.clickedButton() is trash and Path(item.path).exists():
            QFile.moveToTrash(item.path)
        if box.clickedButton() in (keep, trash):
            self.c.history.remove(hid)

    def _clear(self) -> None:
        if self.c.history.items and QMessageBox.question(
                self, "Clear history", "Clear the whole history? Audio files stay where they are.") == QMessageBox.Yes:
            self.c.history.clear()
