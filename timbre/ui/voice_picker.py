"""One active voice: a card that shows it, and a picker that changes it.

A voice is exactly one of:
  * a built-in voice              (mode "preset")
  * one of the user's saved voices, or a recording to clone   (mode "clone")
  * a voice designed from a description of the speaker        (mode "design")
  * a performance directed by an instruction                  (mode "direct")
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from .. import catalog
from . import icons
from .theme import P, theme
from .widgets import ElidedLabel, badge, label

KIND = {"preset": "Built-in", "clone": "Your voice", "design": "Designed", "direct": "Directed"}
ICON = {"preset": "person", "clone": "mic", "design": "pen", "direct": "chat"}


@dataclass
class Summary:
    mode: str
    title: str
    subtitle: str
    kind: str
    icon: str


def summarize(voice, library) -> Summary:
    """Plain-language description of a VoiceConfig, used everywhere a voice is shown."""
    mode = voice.mode
    if mode == "preset":
        p = catalog.preset(voice.preset)
        if p:
            return Summary(mode, p.name, f"{p.gender} · {p.accent} · {p.use}", KIND[mode], ICON[mode])
        return Summary(mode, voice.preset, "Built-in voice", KIND[mode], ICON[mode])
    if mode == "design":
        d = " ".join(voice.description.split())
        return Summary(mode, "Designed voice", (d[:90] + "…" if len(d) > 90 else d) or "Describe the speaker below",
                       KIND[mode], ICON[mode])
    if mode == "direct":
        d = " ".join(voice.instruction.split())
        return Summary(mode, "Directed performance", (d[:90] + "…" if len(d) > 90 else d) or "Write how it should be read below",
                       KIND[mode], ICON[mode])
    saved = library.get(voice.library_id) if voice.library_id else None
    if saved:
        t = " ".join(saved.transcript.split())
        return Summary(mode, saved.name, f"Cloned from a recording · “{t[:60]}{'…' if len(t) > 60 else ''}”",
                       KIND[mode], ICON[mode])
    from pathlib import Path
    if voice.reference_audio:
        return Summary(mode, Path(voice.reference_audio).stem, "Cloned from a recording", "Clone", ICON[mode])
    return Summary(mode, "Clone a recording", "Choose a recording below", "Clone", ICON[mode])


class Avatar(QLabel):
    def __init__(self, size: int = 36):
        super().__init__()
        self.setObjectName("VoiceAvatar")
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self._icon = "person"
        self._size = size
        theme().changed.connect(lambda *_: self.set_icon(self._icon))

    def set_icon(self, name: str) -> None:
        self._icon = name
        self.setPixmap(icons.pixmap(name, P().accent, int(self._size * 0.5)))


class VoiceCard(QPushButton):
    """Shows the active voice. Clickable (opens the picker) unless read-only."""

    def __init__(self, readonly: bool = False):
        super().__init__()
        self.setObjectName("VoiceCard")
        self.setProperty("readonly", "true" if readonly else "false")
        self.setCursor(Qt.ArrowCursor if readonly else Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(64)
        self.avatar = Avatar()
        self.title = label("", "VoiceTitle")
        self.subtitle = ElidedLabel("", "Hint")
        self.kind = badge("")
        self.chevron = QLabel()
        for w in (self.avatar, self.title, self.subtitle, self.kind, self.chevron):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.title)
        top.addWidget(self.kind)
        top.addStretch(1)
        texts.addLayout(top)
        texts.addWidget(self.subtitle)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(12)
        lay.addWidget(self.avatar, 0, Qt.AlignTop)
        lay.addLayout(texts, 1)
        if not readonly:
            lay.addWidget(self.chevron, 0, Qt.AlignVCenter)
            self.setToolTip("Change voice")
        theme().changed.connect(lambda *_: self._chevron())
        self._chevron()

    def _chevron(self) -> None:
        self.chevron.setPixmap(icons.pixmap("chevron-down", P().text2, 16))

    def set_summary(self, s: Summary) -> None:
        self.avatar.set_icon(s.icon)
        self.title.setText(s.title)
        self.subtitle.setText(s.subtitle)
        self.kind.setText(s.kind)

    def sizeHint(self):
        return QSize(300, max(64, self.layout().sizeHint().height()))


class _Row(QWidget):
    def __init__(self, icon: str, title: str, subtitle: str, tag: str = "", selected: bool = False):
        super().__init__()
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        av = Avatar(32)
        av.set_icon(icon)
        t = label(title, "VoiceTitle")
        s = ElidedLabel(subtitle, "Hint")
        texts = QVBoxLayout()
        texts.setSpacing(1)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(t)
        if tag:
            head.addWidget(badge(tag))
        head.addStretch(1)
        texts.addLayout(head)
        texts.addWidget(s)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(12)
        lay.addWidget(av, 0, Qt.AlignTop)
        lay.addLayout(texts, 1)
        if selected:
            tick = QLabel()
            tick.setPixmap(icons.pixmap("check", P().accent, 16))
            lay.addWidget(tick)


class VoicePicker(QDialog):
    """Search and choose the one voice that speaks. Returns a dict of VoiceConfig fields."""

    def __init__(self, current, library, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose a voice")
        self.setMinimumSize(520, 620)
        self.choice: dict | None = None
        self.current = current
        self.library = library
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search voices")
        self.search.setClearButtonEnabled(True)
        self.list = QListWidget()
        self.list.setSpacing(1)
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        lay.addWidget(label("Choose a voice", "PageTitle"))
        lay.addWidget(label("One voice speaks at a time. Pick a built-in or saved voice, or create one.",
                            "Muted", wrap=True))
        lay.addWidget(self.search)
        lay.addWidget(self.list, 1)
        self.search.textChanged.connect(self._fill)
        self.list.itemClicked.connect(self._pick)
        self.list.itemActivated.connect(self._pick)
        self._fill()
        self.search.setFocus()

    def _section(self, text: str) -> None:
        item = QListWidgetItem()
        item.setFlags(Qt.NoItemFlags)
        w = label(text.upper(), "PickerSection")
        item.setSizeHint(w.sizeHint())
        self.list.addItem(item)
        self.list.setItemWidget(item, w)

    def _row(self, data: dict, icon: str, title: str, subtitle: str, tag: str = "", selected: bool = False) -> None:
        item = QListWidgetItem()
        item.setData(Qt.UserRole, data)
        w = _Row(icon, title, subtitle, tag, selected)
        item.setSizeHint(QSize(100, w.sizeHint().height()))
        self.list.addItem(item)
        self.list.setItemWidget(item, w)

    def _fill(self) -> None:
        q = self.search.text().strip().lower()
        match = lambda *parts: not q or any(q in (p or "").lower() for p in parts)  # noqa: E731
        cur = self.current
        self.list.clear()

        create = [
            ({"mode": "design"}, "pen", "Design a voice",
             "Describe the speaker: age, tone, accent, pace"),
            ({"mode": "direct"}, "chat", "Direct a performance",
             "Tell the narrator how to read: mood, energy, pace"),
            ({"mode": "clone", "library_id": ""}, "mic", "Clone a recording",
             "Copy a voice from a 3–20 second recording you may use"),
        ]
        rows = [c for c in create if match(c[2], c[3])]
        if rows:
            self._section("Create")
            for data, icon, title, sub in rows:
                sel = cur.mode == data["mode"] and (data["mode"] != "clone" or (not cur.library_id))
                self._row(data, icon, title, sub, selected=sel)

        mine = [v for v in self.library.voices if match(v.name, v.notes, v.transcript)]
        if mine:
            self._section("Your voices")
            for v in mine:
                t = " ".join(v.transcript.split())
                self._row({"mode": "clone", "library_id": v.id}, "mic", v.name,
                          (v.notes + " · " if v.notes else "") + f"“{t[:70]}{'…' if len(t) > 70 else ''}”",
                          "Your voice", selected=cur.mode == "clone" and cur.library_id == v.id)

        for lang in ("English", "Chinese"):
            built = [p for p in catalog.PRESETS if p.language == lang and match(p.name, p.accent, p.use, p.gender, lang)]
            if built:
                self._section(f"Built-in · {lang}")
                for p in built:
                    self._row({"mode": "preset", "preset": p.id}, "person", p.name,
                              f"{p.gender} · {p.accent} · {p.use}", selected=cur.mode == "preset" and cur.preset == p.id)

    def _pick(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if data:
            self.choice = data
            self.accept()
