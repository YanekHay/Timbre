"""Batch: import many texts and generate them back to back, one file each."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QProgressBar, QVBoxLayout, QWidget)

from .player import reveal_in_explorer
from .widgets import (Card, Combo, Field, PageHeader, Segmented, SummaryRow, badge, button, divider, hbox,
                      icon_button, label, scroll_page, vbox)

def catalog_languages():
    from .. import catalog
    return catalog.LANGUAGES


TEXT_FILTER = "Text (*.txt *.md);;All files (*)"


@dataclass
class BatchItem:
    name: str
    text: str
    source: str = ""
    status: str = "queued"          # queued | running | done | failed | cancelled
    fraction: float = 0.0
    message: str = ""
    result: object = None           # HistoryItem when done
    uid: int = field(default_factory=lambda: BatchItem._next())

    _counter = 0

    @staticmethod
    def _next() -> int:
        BatchItem._counter += 1
        return BatchItem._counter


def split_text(text: str, mode: str) -> list[str]:
    text = text.replace("\r\n", "\n").strip()
    if mode == "paragraph":
        parts = re.split(r"\n\s*\n", text)
    elif mode == "line":
        parts = text.split("\n")
    else:
        parts = [text]
    return [p.strip() for p in parts if p.strip()]


def safe_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", name).strip(" .")[:80] or "take"


class ItemRow(QWidget):
    removeRequested = Signal(int)
    playRequested = Signal(int)
    renamed = Signal(int, str)

    def __init__(self, index: int, item: BatchItem):
        super().__init__()
        self.uid = item.uid
        self.index = label(f"{index:02d}", "Mono")
        self.index.setFixedWidth(26)
        self.name = QLineEdit(item.name)
        self.name.setFixedWidth(220)
        self.name.setToolTip("Output file name")
        self.name.editingFinished.connect(lambda: self.renamed.emit(self.uid, self.name.text()))
        flat = " ".join(item.text.split())
        self.preview = label(flat[:150] + ("…" if len(flat) > 150 else ""), "Muted")
        self.preview.setToolTip(item.text[:2000])
        self.meta = label(f"{len(item.text):,} characters" + (f" · {Path(item.source).name}" if item.source else ""), "Hint")
        self.state = badge("Queued")
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)
        self.bar.hide()
        self.play = icon_button("play", "Play")
        self.reveal = icon_button("folder", "Show in folder")
        self.remove = icon_button("x", "Remove from batch")
        self.play.clicked.connect(lambda: self.playRequested.emit(self.uid))
        self.remove.clicked.connect(lambda: self.removeRequested.emit(self.uid))
        self._item = item
        self.reveal.clicked.connect(lambda: self._item.result and reveal_in_explorer(self._item.result.path))
        body = QWidget()
        body.setLayout(vbox(self.preview, hbox(self.meta, None), self.bar, spacing=4))
        lay = hbox(self.index, self.name, body, self.state, self.play, self.reveal, self.remove,
                   spacing=10, margins=(12, 10, 12, 10))
        lay.setStretch(2, 1)
        self.setLayout(lay)
        self.update_from(item)

    def update_from(self, item: BatchItem) -> None:
        self._item = item
        names = {"queued": ("Queued", ""), "running": ("Generating", "accent"), "done": ("Done", "success"),
                 "failed": ("Failed", "warning"), "cancelled": ("Cancelled", "")}
        text, kind = names[item.status]
        self.state.setText(text)
        self.state.setObjectName({"accent": "BadgeAccent", "success": "BadgeSuccess",
                                  "warning": "BadgeWarning"}.get(kind, "Badge"))
        self.state.style().unpolish(self.state)
        self.state.style().polish(self.state)
        self.state.setToolTip(item.message)
        running = item.status == "running"
        self.bar.setVisible(running)
        if running:
            if item.fraction < 0:
                self.bar.setRange(0, 0)
            else:
                self.bar.setRange(0, 1000)
                self.bar.setValue(int(item.fraction * 1000))
        done = item.status == "done"
        self.play.setVisible(done)
        self.reveal.setVisible(done)
        self.remove.setVisible(item.status != "running")
        self.name.setReadOnly(item.status in ("running", "done"))
        if item.status == "failed":
            self.meta.setText(f"Failed: {item.message}")
        elif done and item.result is not None:
            self.meta.setText(f"{item.result.duration:.1f} s of audio · {Path(item.result.path).name}")


class BatchPage(QWidget):
    playTake = Signal(object)
    openStudio = Signal()

    def __init__(self, controller, studio):
        super().__init__()
        self.setObjectName("Page")
        self.c = controller
        self.studio = studio
        self.items: list[BatchItem] = []
        self.rows: dict[int, ItemRow] = {}
        self.current: BatchItem | None = None
        self.running = False
        self.stop_after = False
        self.profile = None
        self.setAcceptDrops(True)

        add = button("Add text files", "primary", "plus")
        add.clicked.connect(lambda: self.add_files())
        clear = button("Clear finished", "ghost", "x")
        clear.clicked.connect(self.clear_finished)
        header = PageHeader("Batch", "Turn many texts into audio files in one go, one file per take.")

        # ---------- left: the queue
        self.split = Segmented([("Whole file", "file"), ("Each paragraph", "paragraph"), ("Each line", "line")])
        self.split.setMaximumWidth(380)
        import_row = hbox(Field("Split imported files into", self.split, help=(
            "Applies to files you add next. Whole file: one audio file per text file. Each paragraph: "
            "paragraphs separated by a blank line become separate takes. Each line: every non-empty line "
            "becomes a take.")), None, clear, add, spacing=10)
        import_row.setAlignment(clear, Qt.AlignBottom)
        import_row.setAlignment(add, Qt.AlignBottom)

        self.columns = QWidget()
        self.columns.setLayout(hbox(label("#", "ColHeader"), 14, label("FILE NAME", "ColHeader"), 168,
                                    label("TEXT", "ColHeader"), None, label("STATUS", "ColHeader"), 96,
                                    margins=(14, 0, 12, 0), spacing=0))
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.NoSelection)
        self.list.setSpacing(2)
        self.empty = label("Drop .txt or .md files here, or use Add text files.\n"
                           "Each file, paragraph or line becomes its own audio file.", "Muted")
        self.empty.setAlignment(Qt.AlignCenter)
        queue = Card(padding=8, spacing=6)
        queue.add(self.columns, self.list, self.empty)
        left = QWidget()
        left.setLayout(vbox(import_row, queue, spacing=12))
        left.layout().setStretch(1, 1)

        # ---------- right: exactly what this batch will use
        from ..settings import list_profiles
        from .voice_picker import VoiceCard
        self.source = Combo()
        self.source.addItem("Current Studio settings", "")
        for name in list_profiles():
            self.source.addItem(f"Profile: {name}", name)
        self.source.currentIndexChanged.connect(lambda *_: self.refresh_settings())
        self.voice_card = VoiceCard(readonly=True)
        self.rows_summary = {k: SummaryRow(t, help=h) for k, t, h in (
            ("speed", "Speed", "Tempo of the finished audio. Change it in Studio, Voice tab."),
            ("language", "Language", "Language hint sent to the model."),
            ("format", "File", "Format, bit depth and sample rate of every file in the batch."),
            ("loudness", "Loudness", "How every file is levelled, so takes match each other."),
            ("folder", "Saves to", "Folder the batch writes into."),
        )}
        self.edit_btn = button("Change in Studio", "link")
        self.edit_btn.clicked.connect(self.openStudio.emit)
        self.lock_note = label("Locked while the batch runs.", "Hint")
        self.lock_note.hide()
        self.subfolder_on = QCheckBox("Put the files in a subfolder")
        self.subfolder_on.setChecked(True)
        self.subfolder = QLineEdit(datetime.now().strftime("Batch %Y-%m-%d"))
        self.subfolder_on.toggled.connect(self.subfolder.setEnabled)
        self.subfolder_on.toggled.connect(lambda *_: self.refresh_settings())
        self.subfolder.textChanged.connect(lambda *_: self.refresh_settings())

        self.summary = label("", "Muted", wrap=True)
        self.overall = QProgressBar()
        self.overall.setTextVisible(False)
        self.overall.setRange(0, 1000)
        self.overall.hide()
        self.stop_btn = button("Stop after this take")
        self.stop_btn.setToolTip("Finish the take that is generating now, then stop. Remaining takes stay queued.")
        self.stop_btn.clicked.connect(self._stop_after)
        self.cancel_btn = button("Cancel", icon="x")
        self.cancel_btn.setToolTip("Stop now. The current take is discarded and stays queued.")
        self.cancel_btn.clicked.connect(self._cancel)
        self.start_btn = button("Start batch", "primary", "play")
        self.start_btn.setMinimumHeight(38)
        self.start_btn.clicked.connect(self.start)

        settings = Card(padding=20, spacing=12)
        settings.add(label("Batch settings", "SectionTitle"),
                     Field("Use settings from", self.source, help=(
                         "Current Studio settings uses whatever is set in Studio right now. A profile uses "
                         "the voice and settings saved in it, whatever Studio shows.")),
                     Field("Voice", self.voice_card, help="Every take in this batch is spoken by this voice."),
                     *self.rows_summary.values(),
                     hbox(self.edit_btn, None, self.lock_note),
                     divider(),
                     Field("Output folder", None, help="Keeps the batch together instead of mixing it with other takes."),
                     self.subfolder_on, self.subfolder,
                     divider(),
                     self.summary, self.overall,
                     hbox(self.stop_btn, self.cancel_btn, None),
                     self.start_btn)
        settings.setMinimumWidth(340)
        settings.setMaximumWidth(400)
        right = scroll_page(settings)
        right.setMinimumWidth(360)
        right.setMaximumWidth(420)

        body = hbox(left, right, spacing=20)
        body.setStretch(0, 1)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)
        root.addWidget(header)
        root.addLayout(body, 1)

        c = self.c
        c.generationProgress.connect(self._progress)
        c.modelProgress.connect(self._progress)
        c.generationFinished.connect(self._finished)
        c.generationFailed.connect(self._failed)
        c.engineStateChanged.connect(lambda *_: self._refresh())
        self._refresh()

    # ------------------------------------------------------------ import
    def add_files(self, paths: list[str] | None = None) -> None:
        if paths is None:
            paths, _ = QFileDialog.getOpenFileNames(self, "Add text files", "", TEXT_FILTER)
        mode = self.split.value()
        added = 0
        for path in paths:
            try:
                text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
            except OSError as e:
                QMessageBox.warning(self, "Batch", f"Couldn't read {path}: {e}")
                continue
            parts = split_text(text, mode)
            stem = safe_name(Path(path).stem)
            for i, part in enumerate(parts, 1):
                name = stem if len(parts) == 1 else f"{stem}-{i:03d}"
                self.items.append(BatchItem(name=name, text=part, source=path))
                added += 1
        if added:
            self._rebuild()
            self.c.toast.emit(f"Added {added} take{'s' if added != 1 else ''} to the batch.")
        elif paths:
            self.c.toast.emit("Those files had no text to speak.")

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        paths = [u.toLocalFile() for u in e.mimeData().urls()
                 if u.toLocalFile().lower().endswith((".txt", ".md"))]
        if paths:
            self.add_files(paths)

    # ------------------------------------------------------------- queue
    def _rebuild(self) -> None:
        self.list.clear()
        self.rows.clear()
        for i, item in enumerate(self.items, 1):
            row = ItemRow(i, item)
            row.removeRequested.connect(self._remove)
            row.playRequested.connect(self._play)
            row.renamed.connect(self._rename)
            li = QListWidgetItem()
            li.setSizeHint(row.sizeHint())
            self.list.addItem(li)
            self.list.setItemWidget(li, row)
            self.rows[item.uid] = row
        self._refresh()

    def _find(self, uid: int) -> BatchItem | None:
        return next((i for i in self.items if i.uid == uid), None)

    def _remove(self, uid: int) -> None:
        self.items = [i for i in self.items if i.uid != uid]
        self._rebuild()

    def _rename(self, uid: int, name: str) -> None:
        item = self._find(uid)
        if item and item.status == "queued":
            item.name = safe_name(name)

    def _play(self, uid: int) -> None:
        item = self._find(uid)
        if item and item.result:
            self.playTake.emit(item.result)

    def clear_finished(self) -> None:
        self.items = [i for i in self.items if i.status in ("queued", "running")]
        self._rebuild()

    def _update_row(self, item: BatchItem) -> None:
        row = self.rows.get(item.uid)
        if row:
            row.update_from(item)

    def _refresh(self) -> None:
        n = len(self.items)
        done = sum(i.status == "done" for i in self.items)
        failed = sum(i.status == "failed" for i in self.items)
        queued = sum(i.status == "queued" for i in self.items)
        self.empty.setVisible(n == 0)
        self.list.setVisible(n > 0)
        if self.running:
            pos = done + failed + 1
            self.summary.setText(f"Take {min(pos, n)} of {n}"
                                 + (f" · {self.current.message}" if self.current and self.current.message else ""))
        elif n:
            parts = [f"{n} take{'s' if n != 1 else ''}"]
            if done:
                parts.append(f"{done} done")
            if failed:
                parts.append(f"{failed} failed")
            if queued and (done or failed):
                parts.append(f"{queued} waiting")
            self.summary.setText(" · ".join(parts))
        else:
            self.summary.setText("")
        self.start_btn.setVisible(not self.running)
        self.start_btn.setEnabled(queued > 0 and self.c.engine.is_ready and not self.c.generating)
        self.start_btn.setText("Resume batch" if (done or failed) and queued else "Start batch")
        self.stop_btn.setVisible(self.running)
        self.stop_btn.setEnabled(not self.stop_after)
        self.cancel_btn.setVisible(self.running)
        self.overall.setVisible(self.running)
        if self.running and n:
            frac = (done + failed + (max(self.current.fraction, 0) if self.current else 0)) / n
            self.overall.setValue(int(frac * 1000))

    # --------------------------------------------------------------- run
    # ---------------------------------------------------------- settings
    def chosen_profile(self):
        from ..settings import load_profile
        name = self.source.value()
        if name:
            try:
                return load_profile(name)
            except Exception:
                self.source.set_value("")
        return self.studio.inspector.profile()

    def refresh_settings(self) -> None:
        """Show exactly what the batch will use (or is using, while running)."""
        from .history import format_label
        from .voice_picker import summarize
        p = self.profile if self.running and self.profile else self.chosen_profile()
        self.voice_card.set_summary(summarize(p.voice, self.c.library))
        o = p.output
        lang = dict((v, k) for k, v in catalog_languages()).get(p.voice.language, p.voice.language)
        rate = "44.1 kHz" if not o.sample_rate else f"{o.sample_rate / 1000:g} kHz"
        fmt = format_label(o.format if o.format in ("mp3", "ogg") else f"{o.format}-{o.bit_depth}")
        loud = {"loudness": f"{o.target_lufs:g} LUFS", "peak": f"Peak {o.peak_db:g} dB", "off": "Unchanged"}[o.normalize]
        folder = o.resolved_folder()
        if self.subfolder_on.isChecked() and self.subfolder.text().strip():
            folder = folder / self.subfolder.text().strip()
        self.rows_summary["speed"].set(f"{o.speed:.2f}×" + ("  (natural)" if abs(o.speed - 1) < 1e-3 else ""))
        self.rows_summary["language"].set(lang)
        self.rows_summary["format"].set(f"{fmt} · {rate} · {'Stereo' if o.channels == 2 else 'Mono'}")
        self.rows_summary["loudness"].set(loud)
        self.rows_summary["folder"].set(str(folder))
        self.rows_summary["folder"].value.setToolTip(str(folder))
        self.edit_btn.setVisible(not self.source.value() and not self.running)

    def _lock(self, on: bool) -> None:
        for w in (self.source, self.subfolder_on, self.subfolder, self.split):
            w.setEnabled(not on)
        self.lock_note.setVisible(on)
        self.refresh_settings()

    def showEvent(self, e) -> None:
        # Studio may have changed while this page was hidden.
        from ..settings import list_profiles
        current = self.source.value()
        self.source.blockSignals(True)
        self.source.clear()
        self.source.addItem("Current Studio settings", "")
        for name in list_profiles():
            self.source.addItem(f"Profile: {name}", name)
        self.source.set_value(current)
        self.source.blockSignals(False)
        self.refresh_settings()
        super().showEvent(e)

    def start(self) -> None:
        if self.running or self.c.generating:
            return
        self.profile = self.chosen_profile()
        self._lock(True)
        self.running = True
        self.stop_after = False
        self.c.batch_running = True
        self._next()

    def _next(self) -> None:
        nxt = next((i for i in self.items if i.status == "queued"), None)
        if nxt is None or self.stop_after:
            self._end()
            return
        self.current = nxt
        nxt.status, nxt.fraction, nxt.message = "running", -1.0, "Starting"
        self._update_row(nxt)
        self._refresh()
        folder = self.subfolder.text().strip() if self.subfolder_on.isChecked() else ""
        self.c.generate(nxt.text, self.profile, name=nxt.name, subfolder=folder)

    def _end(self) -> None:
        self._lock(False)
        was_running = self.running
        self.running = False
        self.current = None
        self.c.batch_running = False
        self._refresh()
        if was_running:
            done = sum(i.status == "done" for i in self.items)
            failed = sum(i.status == "failed" for i in self.items)
            self.c.toast.emit(f"Batch finished: {done} done" + (f", {failed} failed" if failed else "") + ".")

    def _progress(self, f: float, msg: str) -> None:
        if self.running and self.current:
            self.current.fraction = f
            self.current.message = msg
            self._update_row(self.current)
            self._refresh()

    def _finished(self, hitem) -> None:
        if not (self.running and self.current):
            return
        item = self.current
        item.status, item.fraction, item.result, item.message = "done", 1.0, hitem, ""
        self._update_row(item)
        self._next()

    def _failed(self, message: str, kind: str) -> None:
        if not (self.running and self.current):
            return
        item = self.current
        if kind == "cancelled":
            item.status, item.message = "queued", ""
            self._update_row(item)
            self._end()
            return
        item.status, item.message = "failed", message
        self._update_row(item)
        # Engine or model problems would fail every take: stop instead of burning through the queue.
        if kind in ("engine", "oom") or message.startswith("Couldn't load the model"):
            self._end()
            QMessageBox.warning(self, "Batch stopped", message)
        else:
            self._next()

    def _stop_after(self) -> None:
        self.stop_after = True
        self._refresh()

    def _cancel(self) -> None:
        self.stop_after = True
        self.c.cancel()
