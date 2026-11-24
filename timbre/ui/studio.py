"""Studio: write text, shape the voice, generate."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QInputDialog, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QProgressBar,
                               QSpinBox, QSplitter, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from .. import catalog
from ..settings import (GenerationConfig, OutputConfig, Profile, VoiceConfig, delete_profile,
                        list_profiles, load_profile, save_profile, to_dict)
from . import icons
from .widgets import (AdaptiveStack, Card, Combo, Field, PageHeader, PathField, Section, Segmented, SliderField,
                      button, chips, divider, hbox, icon_button, label, scroll_page, vbox)


class PresetList(QListWidget):
    """Built-in voices as two-line rows."""

    def __init__(self):
        super().__init__()
        self.setSpacing(2)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setCursor(Qt.PointingHandCursor)

    def populate(self, language: str) -> None:
        current = self.value()
        self.clear()
        for p in catalog.PRESETS:
            if p.language != language:
                continue
            item = QListWidgetItem()
            row = QWidget()
            row.setAttribute(Qt.WA_TransparentForMouseEvents)
            name = label(p.name, "SectionTitle")
            meta = label(f"{p.gender} · {p.accent} · {p.use}", "Hint")
            row.setLayout(vbox(name, meta, spacing=1, margins=(10, 8, 10, 8)))
            item.setSizeHint(row.sizeHint())
            item.setData(Qt.UserRole, p.id)
            self.addItem(item)
            self.setItemWidget(item, row)
        self.setFixedHeight(sum(self.sizeHintForRow(i) + 4 for i in range(self.count())) + 4)
        if current:
            self.set_value(current)

    def value(self) -> str:
        item = self.currentItem()
        return item.data(Qt.UserRole) if item else ""

    def set_value(self, pid: str) -> None:
        for i in range(self.count()):
            if self.item(i).data(Qt.UserRole) == pid:
                self.setCurrentRow(i)
                return


class Inspector(QWidget):
    changed = Signal()

    def __init__(self, controller):
        super().__init__()
        self.c = controller
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 4, 20, 20)
        lay.setSpacing(0)
        lay.addWidget(self._voice_section())
        lay.addWidget(divider())
        lay.addWidget(self._generation_section())
        lay.addWidget(divider())
        lay.addWidget(self._output_section())
        lay.addStretch(1)

    # ................................................................ voice
    def _voice_section(self) -> Section:
        s = Section("Voice")
        self.mode = Segmented([("Preset", "preset"), ("Design", "design"), ("Direct", "direct"), ("Clone", "clone")])
        self.voice_stack = AdaptiveStack()

        # Preset
        self.preset_lang = Segmented([("English", "English"), ("Chinese", "Chinese")])
        self.presets = PresetList()
        self.presets.populate("English")
        self.preset_lang.changed.connect(self.presets.populate)
        preset_page = QWidget()
        preset_page.setLayout(vbox(self.preset_lang, self.presets, spacing=10))

        # Design
        self.description = QPlainTextEdit()
        self.description.setPlaceholderText("Describe the speaker: age, timbre, pace, accent, setting…")
        self.description.setFixedHeight(96)
        design_page = QWidget()
        design_page.setLayout(vbox(
            self.description,
            chips(catalog.DESIGN_CHIPS, self._append_descriptor),
            label("Designed voices vary a little between takes. To reuse the exact voice, "
                  "save a take you like from the player.", "Hint", wrap=True),
            spacing=10))

        # Direct
        self.instruction = QPlainTextEdit()
        self.instruction.setPlaceholderText("Tell the narrator how to perform the text…")
        self.instruction.setFixedHeight(96)
        direct_page = QWidget()
        direct_page.setLayout(vbox(
            self.instruction,
            chips([n for n, _ in catalog.DIRECT_EXAMPLES],
                  lambda n: self.instruction.setPlainText(dict(catalog.DIRECT_EXAMPLES)[n])),
            spacing=10))

        # Clone
        self.library_voice = Combo()
        self.reference = PathField("Reference recording (WAV, FLAC, MP3)",
                                   filter="Audio (*.wav *.flac *.mp3 *.ogg)")
        self.reference_text = QPlainTextEdit()
        self.reference_text.setPlaceholderText("Exactly what is said in the recording")
        self.reference_text.setFixedHeight(64)
        self.delivery = Segmented([("Natural", "natural"), ("Emotion", "emotion"), ("Prosody", "prosody")])
        self.emotion = Combo([(n, v) for n, v in catalog.EMOTIONS])
        self.speed = Combo(catalog.SPEEDS)
        self.pitch = Combo(catalog.LEVELS)
        self.volume = Combo(catalog.LEVELS)
        self.emotion_field = Field("Emotion", self.emotion)
        self.prosody_field = QWidget()
        self.prosody_field.setLayout(hbox(Field("Speed", self.speed), Field("Pitch", self.pitch),
                                          Field("Volume", self.volume)))
        self.file_fields = QWidget()
        self.file_fields.setLayout(vbox(
            Field("Recording", self.reference, "3–20 seconds of clean speech, one speaker."),
            Field("Transcript", self.reference_text), spacing=12))
        clone_page = QWidget()
        clone_page.setLayout(vbox(Field("Voice", self.library_voice), self.file_fields,
                                  Field("Delivery", self.delivery), self.emotion_field,
                                  self.prosody_field, spacing=12))
        self.library_voice.currentIndexChanged.connect(self._clone_visibility)
        self.delivery.changed.connect(lambda *_: self._clone_visibility())
        self.c.library.changed.connect(self._fill_library)
        self._fill_library()

        for page in (preset_page, design_page, direct_page, clone_page):
            self.voice_stack.addWidget(page)
        self.mode.changed.connect(self._mode_changed)

        self.language = Combo(catalog.LANGUAGES)
        s.add(self.mode, self.voice_stack, Field("Language", self.language,
                                                 "Auto works for English and Chinese."))
        return s

    def _append_descriptor(self, word: str) -> None:
        text = self.description.toPlainText().strip()
        if word.lower() in text.lower():
            return
        sep = ", " if text and not text.endswith((",", ".")) else " " if text else ""
        self.description.setPlainText(f"{text}{sep}{word}")
        self.description.moveCursor(QTextCursor.End)

    def _mode_changed(self, key: str) -> None:
        self.voice_stack.setCurrentIndex(["preset", "design", "direct", "clone"].index(key))
        self.changed.emit()

    def _fill_library(self) -> None:
        current = self.library_voice.value()
        self.library_voice.blockSignals(True)
        self.library_voice.clear()
        self.library_voice.addItem("Use a recording…", "")
        for v in self.c.library.voices:
            self.library_voice.addItem(v.name, v.id)
        self.library_voice.set_value(current or "")
        self.library_voice.blockSignals(False)
        self._clone_visibility()

    def _clone_visibility(self) -> None:
        self.file_fields.setVisible(not self.library_voice.value())
        d = self.delivery.value()
        self.emotion_field.setVisible(d == "emotion")
        self.prosody_field.setVisible(d == "prosody")

    # ........................................................... generation
    def _generation_section(self) -> Section:
        s = Section("Generation", expanded=False)
        d = GenerationConfig()
        self.cfg = SliderField("Guidance", 1.0, 5.0, 0.1, d.cfg, 1,
                               hint="How closely the voice follows the prompt. Higher is stricter but can sound forced.")
        self.sigma = SliderField("Variation", 0.0, 1.0, 0.05, d.sigma, 2,
                                 hint="Randomness in the acoustic detail. Lower is steadier.")
        self.temperature = SliderField("Temperature", 0.0, 1.0, 0.05, d.temperature, 2,
                                       hint="0 picks the most likely rhythm every time.")
        self.max_length = SliderField("Chunk length", 8, 80, 1, d.max_length, 0,
                                      hint="Long text is split into chunks of about this many words.")
        self.max_steps = SliderField("Max steps per chunk", 200, 3000, 50, d.max_decode_steps, 0)
        self.pause = SliderField("Paragraph pause", 0, 2000, 50, d.paragraph_pause_ms, 0, " ms",
                                 hint="Silence between paragraphs (blank lines). 0 reads everything as one block.")
        self.seed = QSpinBox()
        self.seed.setRange(0, 2_147_483_647)
        self.seed.setButtonSymbols(QSpinBox.NoButtons)
        self.seed_random = QCheckBox("Random")
        self.seed_random.toggled.connect(lambda on: self.seed.setEnabled(not on))
        self.trim = QCheckBox("Trim trailing silence")
        self.raw = QCheckBox("Send text as one piece (no chunking)")
        reset = button("Reset to defaults", "link")
        reset.clicked.connect(lambda: self._set_generation(GenerationConfig()))
        s.add(self.cfg, self.sigma, self.temperature, self.max_length, self.max_steps, self.pause,
              Field("Seed", None, "Fix the seed to reproduce a take exactly."),
              hbox(self.seed, self.seed_random, None),
              self.trim, self.raw, hbox(reset, None))
        return s

    # ............................................................... output
    def _output_section(self) -> Section:
        s = Section("Output")
        self.format = Combo(catalog.FORMATS)
        self.bit_depth = Combo(catalog.BIT_DEPTHS)
        self.quality = SliderField("Quality", 0.1, 1.0, 0.05, 0.9, 2, hint="For MP3 and Ogg. Higher means larger files.")
        self.sample_rate = Combo(catalog.SAMPLE_RATES)
        self.channels = Segmented([("Mono", "1"), ("Stereo", "2")])
        self.normalize = Segmented([("Loudness", "loudness"), ("Peak", "peak"), ("Off", "off")])
        self.lufs = SliderField("Target loudness", -30.0, -10.0, 0.5, -18.0, 1, " LUFS",
                                hint="-16 for podcasts, -18 to -20 for audiobooks.")
        self.peak = SliderField("Peak level", -12.0, 0.0, 0.5, -1.0, 1, " dB")
        self.ceiling = SliderField("Ceiling", -6.0, 0.0, 0.5, -1.0, 1, " dB", hint="Hard limit for peaks after normalising.")
        self.fade_in = SliderField("Fade in", 0, 500, 5, 0, 0, " ms")
        self.fade_out = SliderField("Fade out", 0, 500, 5, 15, 0, " ms")
        self.pad_start = SliderField("Silence before", 0, 3000, 50, 0, 0, " ms")
        self.pad_end = SliderField("Silence after", 0, 3000, 50, 150, 0, " ms")
        self.highpass = Combo([("Off", 0), ("40 Hz", 40), ("60 Hz", 60), ("80 Hz", 80)])
        self.folder = PathField("Music\\Timbre", directory=True)
        self.template = QLineEdit()
        self.template.setPlaceholderText("{date}_{time}_{voice}_{text}")
        self.open_after = QCheckBox("Show the file in Explorer after generating")

        self.format.currentIndexChanged.connect(lambda *_: self._output_visibility())
        self.normalize.changed.connect(lambda *_: self._output_visibility())

        self.bit_field = Field("Bit depth", self.bit_depth)
        s.add(hbox(Field("Format", self.format), self.bit_field),
              self.quality,
              hbox(Field("Sample rate", self.sample_rate), Field("Channels", self.channels)),
              Field("Normalise", self.normalize), self.lufs, self.peak, self.ceiling,
              hbox(self.fade_in, self.fade_out, spacing=16),
              hbox(self.pad_start, self.pad_end, spacing=16),
              Field("Rumble filter", self.highpass),
              Field("Folder", self.folder),
              Field("File name", self.template, "Tokens: {date} {time} {voice} {text} {seed}"),
              self.open_after)
        return s

    def _output_visibility(self) -> None:
        fmt = self.format.value()
        lossless = fmt in ("wav", "flac")
        self.bit_field.setVisible(lossless)
        self.quality.setVisible(not lossless)
        idx = self.bit_depth.findData("32f")
        self.bit_depth.model().item(idx).setEnabled(fmt == "wav")
        if fmt == "flac" and self.bit_depth.value() == "32f":
            self.bit_depth.set_value("24")
        mode = self.normalize.value()
        self.lufs.setVisible(mode == "loudness")
        self.peak.setVisible(mode == "peak")

    # ............................................................. binding
    def profile(self) -> Profile:
        v = VoiceConfig(
            mode=self.mode.value(), preset=self.presets.value() or "UK_George",
            description=self.description.toPlainText().strip(),
            instruction=self.instruction.toPlainText().strip(),
            library_id=self.library_voice.value() or "",
            reference_audio=self.reference.value(), reference_text=self.reference_text.toPlainText().strip(),
            delivery=self.delivery.value(), emotion=self.emotion.value(), speed=self.speed.value(),
            pitch=self.pitch.value(), volume=self.volume.value(), language=self.language.value())
        g = GenerationConfig(
            cfg=round(self.cfg.value(), 2), sigma=round(self.sigma.value(), 2),
            temperature=round(self.temperature.value(), 2), max_length=int(self.max_length.value()),
            max_decode_steps=int(self.max_steps.value()), paragraph_pause_ms=int(self.pause.value()),
            seed=-1 if self.seed_random.isChecked() else self.seed.value(),
            trim_silence=self.trim.isChecked(), raw_text=self.raw.isChecked())
        o = OutputConfig(
            format=self.format.value(), bit_depth=self.bit_depth.value(), quality=round(self.quality.value(), 2),
            sample_rate=int(self.sample_rate.value()), channels=int(self.channels.value()),
            normalize=self.normalize.value(), target_lufs=self.lufs.value(), peak_db=self.peak.value(),
            ceiling_db=self.ceiling.value(), fade_in_ms=int(self.fade_in.value()),
            fade_out_ms=int(self.fade_out.value()), pad_start_ms=int(self.pad_start.value()),
            pad_end_ms=int(self.pad_end.value()), highpass_hz=int(self.highpass.value()),
            folder=self.folder.value(), name_template=self.template.text().strip() or OutputConfig.name_template,
            open_folder_after=self.open_after.isChecked())
        return Profile(voice=v, generation=g, output=o)

    def set_profile(self, p: Profile) -> None:
        v, o = p.voice, p.output
        self.mode.set_value(v.mode)
        self._mode_changed(v.mode)
        pr = catalog.preset(v.preset)
        if pr:
            self.preset_lang.set_value(pr.language)
            self.presets.populate(pr.language)
        self.presets.set_value(v.preset)
        self.description.setPlainText(v.description)
        self.instruction.setPlainText(v.instruction)
        self.library_voice.set_value(v.library_id)
        self.reference.set_value(v.reference_audio)
        self.reference_text.setPlainText(v.reference_text)
        self.delivery.set_value(v.delivery)
        self.emotion.set_value(v.emotion)
        self.speed.set_value(v.speed)
        self.pitch.set_value(v.pitch)
        self.volume.set_value(v.volume)
        self.language.set_value(v.language)
        self._clone_visibility()
        self._set_generation(p.generation)
        self.format.set_value(o.format)
        self.bit_depth.set_value(o.bit_depth)
        self.quality.set_value(o.quality)
        self.sample_rate.set_value(o.sample_rate)
        self.channels.set_value(str(o.channels))
        self.normalize.set_value(o.normalize)
        self.lufs.set_value(o.target_lufs)
        self.peak.set_value(o.peak_db)
        self.ceiling.set_value(o.ceiling_db)
        self.fade_in.set_value(o.fade_in_ms)
        self.fade_out.set_value(o.fade_out_ms)
        self.pad_start.set_value(o.pad_start_ms)
        self.pad_end.set_value(o.pad_end_ms)
        self.highpass.set_value(o.highpass_hz)
        self.folder.set_value(o.folder)
        self.template.setText(o.name_template)
        self.open_after.setChecked(o.open_folder_after)
        self._output_visibility()

    def _set_generation(self, g: GenerationConfig) -> None:
        self.cfg.set_value(g.cfg)
        self.sigma.set_value(g.sigma)
        self.temperature.set_value(g.temperature)
        self.max_length.set_value(g.max_length)
        self.max_steps.set_value(g.max_decode_steps)
        self.pause.set_value(g.paragraph_pause_ms)
        self.seed_random.setChecked(g.seed < 0)
        self.seed.setValue(max(0, g.seed))
        self.seed.setEnabled(g.seed >= 0)
        self.trim.setChecked(g.trim_silence)
        self.raw.setChecked(g.raw_text)


class StudioPage(QWidget):
    def __init__(self, controller, open_devices):
        super().__init__()
        self.setObjectName("Page")
        self.c = controller
        self.open_devices = open_devices

        # Header with profiles
        self.profile_combo = Combo()
        self.profile_combo.setMinimumWidth(180)
        self.profile_combo.setToolTip("Profiles store every voice, generation and output setting")
        self.profile_menu_btn = QToolButton()
        self.profile_menu_btn.setText("Profile")
        icons.bind(self.profile_menu_btn, "save", "text2", 16)
        self.profile_menu_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.profile_menu_btn.setPopupMode(QToolButton.InstantPopup)
        self.profile_menu_btn.setCursor(Qt.PointingHandCursor)
        menu = QMenu(self)
        menu.addAction("Save", self._save_profile)
        menu.addAction("Save as new…", lambda: self._save_profile(new=True))
        menu.addSeparator()
        menu.addAction("Import…", self._import_profile)
        menu.addAction("Export…", self._export_profile)
        menu.addSeparator()
        menu.addAction("Delete", self._delete_profile)
        self.profile_menu_btn.setMenu(menu)
        header = PageHeader("Studio", "Write, shape the voice, generate.",
                            [self.profile_combo, self.profile_menu_btn])

        # Editor
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("Editor")
        self.editor.setPlaceholderText("Type or paste the text you want to hear.\n\n"
                                       "Leave a blank line between paragraphs to add a pause.")
        self.stats = label("", "Hint")
        self.tag_btn = QToolButton()
        self.tag_btn.setText("Insert sound")
        icons.bind(self.tag_btn, "tag", "text2", 16)
        self.tag_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.tag_btn.setPopupMode(QToolButton.InstantPopup)
        self.tag_btn.setProperty("variant", "ghost")
        self.tag_btn.setCursor(Qt.PointingHandCursor)
        tag_menu = QMenu(self)
        for name, tag in catalog.TAGS:
            tag_menu.addAction(f"{name}    {tag}", lambda t=tag: self._insert(t))
        self.tag_btn.setMenu(tag_menu)
        import_btn = button("Import text", "ghost", "file")
        import_btn.clicked.connect(self._import_text)
        clear_btn = button("Clear", "ghost", "x")
        clear_btn.clicked.connect(self.editor.clear)
        editor_card = Card(padding=20, spacing=10)
        editor_card.add(self.editor, divider(), hbox(self.tag_btn, import_btn, clear_btn, None, self.stats))

        # Action bar
        self.status = label("", "Muted")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1000)
        self.progress.hide()
        self.setup_link = button("Set up a compute runtime", "link")
        self.setup_link.clicked.connect(open_devices)
        self.setup_link.hide()
        self.cancel_btn = button("Cancel", icon="x")
        self.cancel_btn.hide()
        self.cancel_btn.clicked.connect(self.c.cancel)
        self.generate_btn = button("Generate", "primary", "play")
        self.generate_btn.setToolTip("Generate (Ctrl+Enter)")
        self.generate_btn.setMinimumWidth(132)
        self.generate_btn.setMinimumHeight(36)
        self.generate_btn.clicked.connect(self.generate)
        status_col = QWidget()
        status_col.setLayout(vbox(hbox(self.status, self.setup_link, None), self.progress, spacing=6))
        actions = hbox(status_col, self.cancel_btn, self.generate_btn, spacing=10)
        actions.setStretch(0, 1)

        left = QWidget()
        left.setLayout(vbox(editor_card, actions, spacing=14, margins=(0, 0, 0, 0)))

        # Inspector
        self.inspector = Inspector(controller)
        inspector_card = Card(padding=0, spacing=0)
        inspector_card.add(scroll_page(self.inspector))
        inspector_card.setMinimumWidth(340)
        inspector_card.setMaximumWidth(440)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(inspector_card)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setHandleWidth(16)
        split.setChildrenCollapsible(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(18)
        root.addWidget(header)
        root.addWidget(split, 1)

        # State
        self.editor.textChanged.connect(self._update_stats)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.generate)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self.generate)
        QShortcut(QKeySequence("Escape"), self, activated=self._escape)
        self.profile_combo.activated.connect(self._apply_profile)

        c = self.c
        c.generationStarted.connect(self._busy)
        c.generationProgress.connect(self._gen_progress)
        c.modelProgress.connect(self._model_progress)
        c.generationFinished.connect(self._idle_done)
        c.generationFailed.connect(self._failed)
        c.engineStateChanged.connect(lambda *_: self._refresh_ready())
        c.modelStatusChanged.connect(self._model_status)
        c.needsSetup.connect(self._refresh_ready)

        self.editor.setPlainText(c.settings.last_text)
        self.inspector.set_profile(c.settings.studio)
        self._fill_profiles(c.settings.active_profile)
        self._update_stats()
        self._refresh_ready()

    # ------------------------------------------------------------- helpers
    def _insert(self, tag: str) -> None:
        cur = self.editor.textCursor()
        before = self.editor.toPlainText()[:cur.position()]
        prefix = "" if not before or before.endswith((" ", "\n")) else " "
        cur.insertText(prefix + tag + " ")
        self.editor.setFocus()

    def _import_text(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import text", "", "Text (*.txt *.md);;All files (*)")
        if path:
            self.editor.setPlainText(Path(path).read_text(encoding="utf-8", errors="replace"))

    def _update_stats(self) -> None:
        text = self.editor.toPlainText()
        spoken = re.sub(r"\[[^\]]+\]", "", text)
        words = len(re.findall(r"[\w']+", spoken))
        cjk = len(re.findall(r"[㐀-鿿]", spoken))
        seconds = words / 2.6 + cjk / 4.5
        est = f" · about {int(seconds // 60)}:{int(seconds % 60):02d}" if seconds >= 1 else ""
        self.stats.setText(f"{len(text):,} characters · {words:,} words{est}")
        self._refresh_ready()

    def _refresh_ready(self) -> None:
        if self.c.generating or self.c.loading:
            return
        engine = self.c.engine.state
        has_text = bool(self.editor.toPlainText().strip())
        self.setup_link.setVisible(engine in ("stopped", "crashed"))
        if engine == "starting":
            msg = "Starting the engine…"
        elif engine in ("stopped", "crashed"):
            msg = "The speech engine isn't running." if engine == "crashed" else "No compute runtime yet."
        elif not self.c.model_status.get("loaded"):
            msg = ("The model loads when you generate." if self.c.model_downloaded() else
                   "The model (about 3 GB) downloads the first time you generate.")
        else:
            dev = self.c.device_info(self.c.model_status.get("device", "")) or {}
            msg = f"Ready on {dev.get('name', self.c.model_status.get('device'))}"
        self.status.setText(msg)
        self.generate_btn.setEnabled(engine == "ready" and has_text)

    def generate(self) -> None:
        if not self.generate_btn.isEnabled():
            return
        text = self.editor.toPlainText().strip()
        profile = self.inspector.profile()
        self.c.settings.studio = profile
        self.c.settings.last_text = self.editor.toPlainText()
        self.c.save()
        self.c.generate(text, profile)

    def _escape(self) -> None:
        if self.c.generating:
            self.c.cancel()

    def _busy(self) -> None:
        self.generate_btn.setEnabled(False)
        self.generate_btn.setText("Generating")
        self.cancel_btn.show()
        self.progress.show()
        self.progress.setRange(0, 0)
        self.status.setText("Starting…")
        self.setup_link.hide()

    def _set_progress(self, f: float, msg: str) -> None:
        if f is None or f < 0:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(f * 1000))
        if msg:
            self.status.setText(msg)

    def _model_progress(self, f: float, msg: str) -> None:
        self.progress.show()
        self.cancel_btn.setVisible(self.c.loading)   # a download can be cancelled and resumes later
        self.generate_btn.setEnabled(False)
        self._set_progress(f, msg)

    def _model_status(self, *_):
        # A finished (or failed) model load: clear its progress unless a generation follows.
        if not self.c.generating and not self.c.loading:
            self._reset_actions()

    def _gen_progress(self, f: float, msg: str) -> None:
        self.cancel_btn.show()
        self._set_progress(f, msg)

    def _reset_actions(self) -> None:
        self.generate_btn.setText("Generate")
        self.cancel_btn.hide()
        self.progress.hide()
        self._refresh_ready()

    def _idle_done(self, item) -> None:
        self._reset_actions()
        rtf = item.generation_seconds / max(item.duration, 1e-6)
        self.status.setText(f"Done · {item.duration:.1f} s of audio in {item.generation_seconds:.1f} s"
                            f" ({1 / rtf:.2f}× real time)")

    def _failed(self, message: str, kind: str) -> None:
        self._reset_actions()
        if kind == "cancelled":
            self.status.setText("Cancelled.")
            return
        if kind == "oom":
            message = ("The device ran out of memory. Close other GPU apps, choose a lower precision, "
                       "or switch to the CPU in Devices.")
        self.status.setText("")
        QMessageBox.warning(self, "Couldn't generate", message)

    # ------------------------------------------------------------ profiles
    def _fill_profiles(self, active: str = "") -> None:
        self.profile_combo.clear()
        self.profile_combo.addItem("Unsaved settings", "")
        for name in list_profiles():
            self.profile_combo.addItem(name, name)
        self.profile_combo.set_value(active)

    def _apply_profile(self) -> None:
        name = self.profile_combo.value()
        self.c.settings.active_profile = name
        if name:
            try:
                self.inspector.set_profile(load_profile(name))
            except Exception as e:
                QMessageBox.warning(self, "Profile", f"Couldn't load “{name}”: {e}")

    def _save_profile(self, new: bool = False) -> None:
        name = self.profile_combo.value()
        if new or not name:
            name, ok = QInputDialog.getText(self, "Save profile", "Profile name")
            if not ok or not name.strip():
                return
        save_profile(name.strip(), self.inspector.profile())
        self.c.settings.active_profile = name.strip()
        self._fill_profiles(name.strip())

    def _import_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import profile", "", "Timbre profile (*.json)")
        if not path:
            return
        try:
            p = load_profile(path)
        except Exception as e:
            QMessageBox.warning(self, "Import profile", f"That file isn't a Timbre profile: {e}")
            return
        save_profile(Path(path).stem, p)
        self._fill_profiles(Path(path).stem)
        self.inspector.set_profile(p)

    def _export_profile(self) -> None:
        import json
        path, _ = QFileDialog.getSaveFileName(self, "Export profile",
                                              (self.profile_combo.value() or "profile") + ".json",
                                              "Timbre profile (*.json)")
        if path:
            Path(path).write_text(json.dumps(to_dict(self.inspector.profile()), indent=2, ensure_ascii=False),
                                  encoding="utf-8")

    def _delete_profile(self) -> None:
        name = self.profile_combo.value()
        if name and QMessageBox.question(self, "Delete profile", f"Delete the profile “{name}”?") == QMessageBox.Yes:
            delete_profile(name)
            self._fill_profiles("")

    def persist(self) -> None:
        self.c.settings.studio = self.inspector.profile()
        self.c.settings.last_text = self.editor.toPlainText()

    def load_profile_dict(self, profile: Profile, text: str | None = None) -> None:
        self.inspector.set_profile(profile)
        if text is not None:
            self.editor.setPlainText(text)
        self.profile_combo.set_value("")
