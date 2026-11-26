"""Studio: write text, choose one voice, generate."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QInputDialog, QLineEdit, QMenu, QMessageBox,
                               QPlainTextEdit, QProgressBar, QSpinBox, QSplitter, QToolButton, QVBoxLayout,
                               QWidget)

from .. import catalog
from ..settings import (GenerationConfig, OutputConfig, Profile, VoiceConfig, delete_profile,
                        list_profiles, load_profile, save_profile, to_dict)
from . import icons
from .voice_picker import VoiceCard, VoicePicker, summarize
from .widgets import (AdaptiveStack, Card, Combo, Field, OneOf, PageHeader, PathField, Section, Segmented, SliderField,
                      TabBar, button, chips, divider, hbox, label, scroll_page, vbox)

# Hover explanations, kept together so the wording stays consistent.
HELP = {
    "voice": "Who speaks. Exactly one voice is active; click to pick a built-in voice, one of your saved "
             "voices, or create one by describing, directing or cloning.",
    "description": "Describe the speaker, not the text: age, gender, timbre (deep, bright, raspy), pace, "
                   "accent and setting. Designed voices vary a little between takes.",
    "direction": "Tell the narrator how to perform the text: mood, energy, pace, character. "
                 "The model picks a fitting voice.",
    "recording": "A clean clip of one person speaking, 3–20 seconds, no music or background noise. "
                 "WAV or FLAC gives the best result.",
    "transcript": "Exactly the words spoken in the recording. Mismatched text makes the clone less accurate.",
    "delivery": "Natural keeps the recording's own style. Emotion applies a feeling. Prosody sets speaking "
                "rate, pitch and loudness through the model.",
    "speed": "Changes the pace of the finished audio without changing the voice's pitch. 1.00× is the model's "
             "natural pace; 0.90× is a little slower. Very large changes can sound processed.",
    "language": "Auto works for English and Chinese. For German, Spanish, French, Korean or Japanese text, "
                "choose the language so it's pronounced correctly.",
    "guidance": "How strictly the model follows the voice and style prompt. Higher is closer to the prompt but "
                "can sound forced; lower is looser and more natural. Default 2.0.",
    "variation": "Randomness in fine acoustic detail. Lower is steadier and more consistent between takes; "
                 "higher sounds livelier. Default 0.25.",
    "temperature": "Randomness in rhythm and phrasing. 0 always picks the most likely delivery. Default 0.",
    "chunk": "Long text is split into chunks of about this many words, spoken one after another. "
             "Shorter chunks are more stable; longer ones flow better. Default 24.",
    "steps": "Upper limit on generation steps per chunk. Only raise it if long chunks get cut off.",
    "pause": "Silence inserted between paragraphs (separated by a blank line). 0 reads all text as one block.",
    "seed": "A fixed seed makes the same settings and text produce the same take again. "
            "Random gives a fresh take each time.",
    "trim": "Removes silence the model leaves at the end of each chunk.",
    "raw": "Sends the whole text to the model at once instead of in chunks. Can sound smoother for short "
           "texts but is less reliable for long ones.",
    "format": "WAV and FLAC are lossless; FLAC is about half the size. MP3 and Ogg are small files for sharing.",
    "bits": "24-bit is ideal for editing; 16-bit is CD quality and smaller. 32-bit float is for audio editors.",
    "quality": "Encoder quality for MP3 and Ogg. Higher sounds better and makes larger files.",
    "rate": "The model speaks at 44.1 kHz. 48 kHz suits video; lower rates make smaller files but lose clarity.",
    "channels": "The voice is mono. Stereo copies it to both channels, for tools that require stereo.",
    "normalise": "Loudness matches perceived volume (best for listening). Peak only scales the loudest point. "
                 "Off keeps the model's raw level.",
    "lufs": "Target perceived loudness. -16 LUFS for podcasts and online, -18 to -20 for audiobooks, "
            "-23 for broadcast.",
    "peak": "Level of the loudest sample after scaling.",
    "ceiling": "Peaks are never louder than this after normalising, which prevents clipping.",
    "fades": "Short fades remove clicks at the very start and end of the file.",
    "padding": "Silence added before and after the speech, useful when joining clips.",
    "rumble": "Removes very low frequencies (hum, desk thumps) below this frequency.",
    "folder": "Where generated files are saved.",
    "filename": "Name pattern for new files. Tokens: {date} {time} {voice} {text} {seed}.",
}


class Inspector(QWidget):
    """Settings panel: the active voice and its options, and output settings."""

    changed = Signal()

    def __init__(self, controller):
        super().__init__()
        self.c = controller
        self.voice = VoiceConfig()
        self.tabs = TabBar([("Voice", "voice"), ("Output", "output")])
        self.pages = AdaptiveStack()
        self.pages.addWidget(scroll_page(self._voice_page()))
        self.pages.addWidget(scroll_page(self._output_page()))
        self.tabs.changed.connect(lambda k: self.pages.setCurrentIndex(0 if k == "voice" else 1))
        bar = QWidget()
        bar.setLayout(vbox(self.tabs, margins=(20, 0, 20, 0)))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(bar)
        lay.addWidget(self.pages, 1)
        self.c.library.changed.connect(self._refresh_voice)

    @staticmethod
    def _page(*items) -> QWidget:
        w = QWidget()
        w.setLayout(vbox(*items, None, spacing=16, margins=(20, 18, 20, 24)))
        return w

    # ............................................................ voice tab
    def _voice_page(self) -> QWidget:
        self.voice_card = VoiceCard()
        self.voice_card.clicked.connect(self._choose_voice)

        # Options for the active voice type; only one is ever visible.
        self.preset_info = label("", "Callout", wrap=True)
        preset_panel = QWidget()
        preset_panel.setLayout(vbox(self.preset_info))

        self.description = QPlainTextEdit()
        self.description.setPlaceholderText("e.g. A deep, warm male narrator in his fifties, calm and unhurried, "
                                            "recorded in a quiet studio")
        self.description.setFixedHeight(92)
        self.description.textChanged.connect(self._text_changed)
        design_panel = QWidget()
        design_panel.setLayout(vbox(
            Field("Voice description", self.description, help=HELP["description"]),
            chips(catalog.DESIGN_CHIPS, self._append_descriptor), spacing=10))

        self.instruction = QPlainTextEdit()
        self.instruction.setPlaceholderText("e.g. Read like a warm bedtime story, softly and slowly")
        self.instruction.setFixedHeight(92)
        self.instruction.textChanged.connect(self._text_changed)
        direct_panel = QWidget()
        direct_panel.setLayout(vbox(
            Field("Direction", self.instruction, help=HELP["direction"]),
            chips([n for n, _ in catalog.DIRECT_EXAMPLES],
                  lambda n: self.instruction.setPlainText(dict(catalog.DIRECT_EXAMPLES)[n])), spacing=10))

        self.reference = PathField("Choose a recording", filter="Audio (*.wav *.flac *.mp3 *.ogg)")
        self.reference.changed.connect(lambda *_: self._refresh_voice())
        self.reference_text = QPlainTextEdit()
        self.reference_text.setPlaceholderText("Exactly what is said in the recording")
        self.reference_text.setFixedHeight(64)
        self.file_fields = QWidget()
        self.file_fields.setLayout(vbox(Field("Recording", self.reference, help=HELP["recording"]),
                                        Field("Transcript", self.reference_text, help=HELP["transcript"]),
                                        spacing=12))
        self.delivery = Segmented([("Natural", "natural"), ("Emotion", "emotion"), ("Prosody", "prosody")])
        self.delivery.changed.connect(lambda *_: self._clone_visibility())
        self.emotion = Combo([(n, v) for n, v in catalog.EMOTIONS])
        self.speed_ctl = Combo(catalog.SPEEDS)
        self.pitch = Combo(catalog.LEVELS)
        self.volume = Combo(catalog.LEVELS)
        self.emotion_field = Field("Emotion", self.emotion)
        self.prosody_field = QWidget()
        self.prosody_field.setLayout(hbox(Field("Rate", self.speed_ctl), Field("Pitch", self.pitch),
                                          Field("Loudness", self.volume)))
        clone_panel = QWidget()
        clone_panel.setLayout(vbox(self.file_fields,
                                   Field("Delivery", self.delivery, help=HELP["delivery"]),
                                   self.emotion_field, self.prosody_field, spacing=12))

        self.voice_options = OneOf()
        for panel in (preset_panel, design_panel, direct_panel, clone_panel):
            self.voice_options.addWidget(panel)

        self.speed = SliderField("Speed", 0.70, 1.30, 0.05, 1.0, 2, "×", help=HELP["speed"],
                                 ends=("Slower", "Faster"), default=1.0)
        self.language = Combo(catalog.LANGUAGES)

        adv = Section("Advanced generation", expanded=False)
        d = GenerationConfig()
        self.cfg = SliderField("Guidance", 1.0, 5.0, 0.1, d.cfg, 1, help=HELP["guidance"],
                               ends=("Looser", "Stricter"), default=d.cfg)
        self.sigma = SliderField("Variation", 0.0, 1.0, 0.05, d.sigma, 2, help=HELP["variation"],
                                 ends=("Steadier", "Livelier"), default=d.sigma)
        self.temperature = SliderField("Temperature", 0.0, 1.0, 0.05, d.temperature, 2, help=HELP["temperature"],
                                       default=d.temperature)
        self.max_length = SliderField("Chunk length", 8, 80, 1, d.max_length, 0, " words", help=HELP["chunk"],
                                      default=d.max_length)
        self.max_steps = SliderField("Max steps per chunk", 200, 3000, 50, d.max_decode_steps, 0, help=HELP["steps"],
                                     default=d.max_decode_steps)
        self.pause = SliderField("Paragraph pause", 0, 2000, 50, d.paragraph_pause_ms, 0, " ms", help=HELP["pause"],
                                 default=d.paragraph_pause_ms)
        self.seed = QSpinBox()
        self.seed.setRange(0, 2_147_483_647)
        self.seed.setButtonSymbols(QSpinBox.NoButtons)
        self.seed_random = QCheckBox("Random")
        self.seed_random.toggled.connect(lambda on: self.seed.setEnabled(not on))
        self.trim = QCheckBox("Trim trailing silence")
        self.trim.setToolTip(HELP["trim"])
        self.raw = QCheckBox("Send text as one piece")
        self.raw.setToolTip(HELP["raw"])
        reset = button("Reset to defaults", "link")
        reset.clicked.connect(lambda: self._set_generation(GenerationConfig()))
        adv.add(self.cfg, self.sigma, self.temperature, self.max_length, self.max_steps, self.pause,
                Field("Seed", None, help=HELP["seed"]), hbox(self.seed, self.seed_random, None),
                self.trim, self.raw, hbox(reset, None))

        return self._page(Field("Voice", self.voice_card, help=HELP["voice"]), self.voice_options,
                          divider(), self.speed, Field("Language", self.language, help=HELP["language"]),
                          divider(), adv)

    def _choose_voice(self) -> None:
        current = self._voice_config()
        dlg = VoicePicker(current, self.c.library, self)
        if dlg.exec() and dlg.choice:
            choice = dlg.choice
            self.voice.mode = choice["mode"]
            if "preset" in choice:
                self.voice.preset = choice["preset"]
            if choice["mode"] == "clone":
                self.voice.library_id = choice.get("library_id", "")
            self._refresh_voice()
            if self.voice.mode == "design" and not self.description.toPlainText().strip():
                self.description.setFocus()
            elif self.voice.mode == "direct" and not self.instruction.toPlainText().strip():
                self.instruction.setFocus()
            self.changed.emit()

    def _append_descriptor(self, word: str) -> None:
        text = self.description.toPlainText().strip()
        if word.lower() in text.lower():
            return
        sep = ", " if text and not text.endswith((",", ".")) else " " if text else ""
        self.description.setPlainText(f"{text}{sep}{word}")
        self.description.moveCursor(QTextCursor.End)

    def _text_changed(self) -> None:
        # Keep the voice card's subtitle in step with what's typed for designed/directed voices.
        if self.voice.mode in ("design", "direct"):
            self.voice_card.set_summary(summarize(self._voice_config(), self.c.library))

    def _refresh_voice(self) -> None:
        v = self._voice_config()
        self.voice_card.set_summary(summarize(v, self.c.library))
        self.voice_options.setCurrentIndex(["preset", "design", "direct", "clone"].index(v.mode))
        if v.mode == "preset":
            p = catalog.preset(v.preset)
            lang = f" It speaks {p.language}." if p else ""
            self.preset_info.setText(
                f"Built-in voice.{lang} Built-in voices have a fixed style, so emotion and prosody controls "
                "don't apply. Use Speed below, or save a take you like to Your voices and clone it for full control.")
        self._clone_visibility()

    def _clone_visibility(self) -> None:
        self.file_fields.setVisible(self.voice.mode == "clone" and not self.voice.library_id)
        d = self.delivery.value()
        self.emotion_field.setVisible(d == "emotion")
        self.prosody_field.setVisible(d == "prosody")


    # ........................................................... output tab
    def _output_page(self) -> QWidget:
        self.format = Combo(catalog.FORMATS)
        self.bit_depth = Combo(catalog.BIT_DEPTHS)
        self.quality = SliderField("Quality", 0.1, 1.0, 0.05, 0.9, 2, help=HELP["quality"],
                                   ends=("Smaller", "Better"), default=0.9)
        self.sample_rate = Combo(catalog.SAMPLE_RATES)
        self.channels = Segmented([("Mono", "1"), ("Stereo", "2")])
        self.normalize = Segmented([("Loudness", "loudness"), ("Peak", "peak"), ("Off", "off")])
        self.lufs = SliderField("Target loudness", -30.0, -10.0, 0.5, -18.0, 1, " LUFS", help=HELP["lufs"],
                                ends=("Quieter", "Louder"), default=-18.0)
        self.peak = SliderField("Peak level", -12.0, 0.0, 0.5, -1.0, 1, " dB", help=HELP["peak"], default=-1.0)
        self.ceiling = SliderField("Ceiling", -6.0, 0.0, 0.5, -1.0, 1, " dB", help=HELP["ceiling"], default=-1.0)
        self.fade_in = SliderField("Fade in", 0, 500, 5, 0, 0, " ms", help=HELP["fades"], default=0)
        self.fade_out = SliderField("Fade out", 0, 500, 5, 15, 0, " ms", help=HELP["fades"], default=15)
        self.pad_start = SliderField("Silence before", 0, 3000, 50, 0, 0, " ms", help=HELP["padding"], default=0)
        self.pad_end = SliderField("Silence after", 0, 3000, 50, 150, 0, " ms", help=HELP["padding"], default=150)
        self.highpass = Combo([("Off", 0), ("40 Hz", 40), ("60 Hz", 60), ("80 Hz", 80)])
        self.folder = PathField("Music\\Timbre", directory=True)
        self.template = QLineEdit()
        self.template.setPlaceholderText("{date}_{time}_{voice}_{text}")
        self.open_after = QCheckBox("Show the file in Explorer after generating")
        self.format.currentIndexChanged.connect(lambda *_: self._output_visibility())
        self.normalize.changed.connect(lambda *_: self._output_visibility())
        self.bit_field = Field("Bit depth", self.bit_depth, help=HELP["bits"])

        group = lambda t: label(t.upper(), "GroupTitle")  # noqa: E731
        return self._page(
            group("File"),
            hbox(Field("Format", self.format, help=HELP["format"]), self.bit_field),
            self.quality,
            hbox(Field("Sample rate", self.sample_rate, help=HELP["rate"]),
                 Field("Channels", self.channels, help=HELP["channels"])),
            divider(), group("Loudness"),
            Field("Normalise", self.normalize, help=HELP["normalise"]), self.lufs, self.peak, self.ceiling,
            divider(), group("Edges and clean-up"),
            self.fade_in, self.fade_out, self.pad_start, self.pad_end,
            Field("Rumble filter", self.highpass, help=HELP["rumble"]),
            divider(), group("Saving"),
            Field("Folder", self.folder, help=HELP["folder"]),
            Field("File name", self.template, help=HELP["filename"]), self.open_after)

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
    def _voice_config(self) -> VoiceConfig:
        v = self.voice
        return VoiceConfig(
            mode=v.mode, preset=v.preset or "UK_George",
            description=self.description.toPlainText().strip(),
            instruction=self.instruction.toPlainText().strip(),
            library_id=v.library_id if v.mode == "clone" else "",
            reference_audio=self.reference.value(), reference_text=self.reference_text.toPlainText().strip(),
            delivery=self.delivery.value(), emotion=self.emotion.value(), speed=self.speed_ctl.value(),
            pitch=self.pitch.value(), volume=self.volume.value(), language=self.language.value())

    def profile(self) -> Profile:
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
            open_folder_after=self.open_after.isChecked(), speed=round(self.speed.value(), 2))
        return Profile(voice=self._voice_config(), generation=g, output=o)

    def set_profile(self, p: Profile) -> None:
        v, o = p.voice, p.output
        if v.mode == "clone" and v.library_id and not self.c.library.get(v.library_id):
            v.library_id = ""                       # the saved voice was deleted
        self.voice = VoiceConfig(mode=v.mode, preset=v.preset, library_id=v.library_id)
        self.description.setPlainText(v.description)
        self.instruction.setPlainText(v.instruction)
        self.reference.set_value(v.reference_audio)
        self.reference_text.setPlainText(v.reference_text)
        self.delivery.set_value(v.delivery)
        self.emotion.set_value(v.emotion)
        self.speed_ctl.set_value(v.speed)
        self.pitch.set_value(v.pitch)
        self.volume.set_value(v.volume)
        self.language.set_value(v.language)
        self._set_generation(p.generation)
        self.speed.set_value(o.speed or 1.0)
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
        self._refresh_voice()

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
        self.inspector.changed.connect(self._refresh_ready)
        self.inspector.speed.valueChanged.connect(lambda *_: self._refresh_ready())
        inspector_card = Card(padding=0, spacing=0)
        inspector_card.add(self.inspector)
        inspector_card.setMinimumWidth(380)
        inspector_card.setMaximumWidth(460)

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
        if engine == "ready":
            # Say exactly what Generate will use, so there's no doubt which voice speaks.
            p = self.inspector.profile()
            voice = summarize(p.voice, self.c.library).title
            speed = f" at {p.output.speed:.2f}×" if abs(p.output.speed - 1) > 1e-3 else ""
            msg = f"{msg}  ·  Voice: {voice}{speed}"
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
