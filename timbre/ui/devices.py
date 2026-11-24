"""Devices: hardware inventory, compute runtimes, inference device and precision."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLineEdit,
                               QMessageBox, QPlainTextEdit, QProgressBar, QRadioButton, QVBoxLayout,
                               QWidget)

from .. import hardware, runtime
from ..hardware import human_bytes
from .widgets import (Card, Field, PageHeader, PathField, Section, Segmented, badge, button, divider,
                      hbox, label, scroll_page, vbox)


# ------------------------------------------------------------------ dialogs
class InstallDialog(QDialog):
    def __init__(self, variant: runtime.Variant, index_override: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Install {variant.label} runtime")
        self.setMinimumSize(620, 420)
        self.ok = False
        self.installer = runtime.RuntimeInstaller(variant, index_override, self)
        self.step = label(f"Installing the {variant.label} runtime", "SectionTitle")
        self.sub = label(f"About {variant.download_gb:g} GB will be downloaded once. You can keep using "
                         "your PC; this takes a few minutes.", "Muted", wrap=True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setObjectName("Mono")
        self.log.setMaximumBlockCount(4000)
        self.cancel = button("Cancel")
        self.done_btn = button("Done", "primary")
        self.done_btn.hide()
        self.cancel.clicked.connect(self._cancel)
        self.done_btn.clicked.connect(self.accept)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(self.step)
        lay.addWidget(self.sub)
        lay.addWidget(self.bar)
        lay.addWidget(self.log, 1)
        lay.addLayout(hbox(None, self.cancel, self.done_btn))
        self.installer.output.connect(self._append)
        self.installer.stepChanged.connect(self._step)
        self.installer.finished.connect(self._finished)

    def exec(self):
        self.installer.start()
        return super().exec()

    def _append(self, text: str) -> None:
        self.log.moveCursor(self.log.textCursor().MoveOperation.End)
        self.log.insertPlainText(text.replace("\r", "\n"))
        self.log.ensureCursorVisible()

    def _step(self, i: int, n: int, text: str) -> None:
        self.step.setText(f"Step {i + 1} of {n} · {text}")

    def _finished(self, ok: bool, message: str) -> None:
        self.ok = ok
        self.bar.setRange(0, 1)
        self.bar.setValue(1 if ok else 0)
        self.step.setText(message)
        self.sub.setText("Timbre will now restart its engine on the new runtime." if ok else
                         "Nothing was changed. You can retry, pick another runtime, or use an existing environment.")
        self.cancel.hide()
        self.done_btn.show()

    def _cancel(self) -> None:
        self.installer.cancel()


class LogDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Engine log")
        self.setMinimumSize(760, 480)
        self.text = QPlainTextEdit("\n".join(controller.engine.log))
        self.text.setReadOnly(True)
        self.text.setObjectName("Mono")
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        controller.engine.logLine.connect(self.text.appendPlainText)
        close = button("Close")
        close.clicked.connect(self.accept)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.addWidget(self.text, 1)
        lay.addLayout(hbox(None, close))


# ------------------------------------------------------------------ tiles
class VariantTile(Card):
    def __init__(self, variant: runtime.Variant, recommended: bool, active: bool, on_install, on_use):
        super().__init__(padding=14, spacing=6, name="Inset")
        tags = []
        if active:
            tags.append(badge("In use", "accent"))
        elif variant.installed:
            tags.append(badge("Installed", "success"))
        if recommended:
            tags.append(badge("Recommended for this PC", "accent" if not active else ""))
        if variant.status == "preview":
            tags.append(badge("Preview", "warning"))
        head = hbox(label(variant.label, "SectionTitle"), *tags, None, spacing=6)
        action = button("Reinstall" if variant.installed else f"Install · {variant.download_gb:g} GB",
                        "primary" if recommended and not variant.installed else "",
                        "download" if not variant.installed else "refresh")
        action.clicked.connect(lambda: on_install(variant))
        row = [action]
        if variant.installed and not active:
            use = button("Use")
            use.clicked.connect(lambda: on_use(variant))
            row.insert(0, use)
        self.add(head, label(variant.summary, "Muted", wrap=True))
        if variant.note:
            self.add(label(variant.note, "Hint", wrap=True))
        self.add(hbox(None, *row))


# ------------------------------------------------------------------ page
class DevicesPage(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.setObjectName("Page")
        self.c = controller
        self.gpus = hardware.gpus()
        self.cpu = hardware.cpu()
        self.recommended = hardware.recommended_variant(self.gpus)

        refresh = button("Rescan", icon="refresh")
        refresh.clicked.connect(self._rescan)
        header = PageHeader("Devices", "Choose where speech is generated and how.", [refresh])

        self.hardware_card = Card()
        self.runtime_card = Card()
        self.device_card = Card()
        content = QWidget()
        content.setLayout(vbox(header, self.device_card, self.runtime_card, self.hardware_card, None,
                               spacing=18, margins=(28, 24, 28, 24)))
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll_page(content))

        self._build_device_card()
        self._build_runtime_card()
        self._build_hardware_card()

        c = self.c
        c.devicesChanged.connect(lambda *_: self._fill_devices())
        c.engineStateChanged.connect(lambda *_: self._refresh_runtime_status())
        c.modelStatusChanged.connect(lambda *_: self._refresh_model_status())
        c.modelProgress.connect(self._model_progress)
        c.memoryChanged.connect(self._memory)
        self._refresh_runtime_status()
        self._refresh_model_status()

    # ............................................................ device
    def _build_device_card(self) -> None:
        card = self.device_card
        self.engine_badge = badge("")
        card.add(hbox(label("Inference device", "SectionTitle"), None, self.engine_badge))
        self.device_list = QWidget()
        self.device_layout = QVBoxLayout(self.device_list)
        self.device_layout.setContentsMargins(0, 0, 0, 0)
        self.device_layout.setSpacing(6)
        self.device_group = QButtonGroup(self)
        self.device_group.buttonClicked.connect(self._device_chosen)
        self.precision = Segmented([("Auto", "auto"), ("BF16", "bf16"), ("FP16", "fp16"), ("FP32", "fp32")])
        self.precision.changed.connect(self._precision_chosen)
        self.precision_hint = label("", "Hint", wrap=True)

        self.model_state = label("", "Muted")
        self.model_bar = QProgressBar()
        self.model_bar.setTextVisible(False)
        self.model_bar.setRange(0, 1000)
        self.model_bar.hide()
        self.mem_label = label("", "Value")
        self.mem_bar = QProgressBar()
        self.mem_bar.setTextVisible(False)
        self.mem_bar.setRange(0, 1000)
        self.mem_bar.hide()
        self.load_btn = button("Load model", "primary", "bolt")
        self.unload_btn = button("Unload")
        self.cancel_load_btn = button("Cancel")
        self.cancel_load_btn.hide()
        self.load_btn.clicked.connect(lambda: self.c.load_model())
        self.unload_btn.clicked.connect(self.c.unload_model)
        self.cancel_load_btn.clicked.connect(self.c.cancel)

        adv = Section("Advanced", expanded=False)
        self.model_id = QLineEdit(self.c.settings.device.model)
        self.model_id.editingFinished.connect(self._model_id_changed)
        self.tn = QCheckBox("Text normalisation (reads numbers, dates and units; needs pynini)")
        self.tn.setChecked(self.c.settings.device.text_normalization)
        self.tn.toggled.connect(self._tn_changed)
        self.autoload = QCheckBox("Load the model when Timbre starts")
        self.autoload.setChecked(self.c.settings.device.load_on_start)
        self.autoload.toggled.connect(self._autoload_changed)
        model_hint = ("A Hugging Face repo id (downloaded once into the model folder from Settings) "
                      "or a local folder with Ming-3.0-tts-0.5B weights.")
        adv.add(Field("Model", self.model_id, model_hint),
                self.tn, self.autoload)

        card.add(self.device_list,
                 Field("Precision", self.precision), self.precision_hint,
                 divider(),
                 hbox(vbox(self.model_state, self.model_bar, spacing=6), None, self.cancel_load_btn,
                      self.unload_btn, self.load_btn),
                 vbox(hbox(label("Memory", "Muted"), None, self.mem_label), self.mem_bar, spacing=6),
                 adv)

    def _fill_devices(self) -> None:
        for b in self.device_group.buttons():
            self.device_group.removeButton(b)
        while self.device_layout.count():
            w = self.device_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        current = self.c.settings.device.device
        options = [("auto", "Automatic", self._auto_caption())] + [
            (d["id"], d["name"], self._device_caption(d)) for d in self.c.devices]
        for did, name, caption in options:
            row = QWidget()
            radio = QRadioButton(name)
            radio.setCursor(Qt.PointingHandCursor)
            radio.setProperty("device", did)
            radio.setChecked(did == current or (current not in {o[0] for o in options} and did == "auto"))
            self.device_group.addButton(radio)
            cap = label(caption, "Hint")
            cap.setContentsMargins(26, 0, 0, 0)
            row.setLayout(vbox(radio, cap, spacing=2, margins=(10, 8, 10, 8)))
            row.setObjectName("Inset")
            row.setAttribute(Qt.WA_StyledBackground, True)
            self.device_layout.addWidget(row)
        if not self.c.devices:
            self.device_layout.addWidget(label("Devices appear once the engine is running.", "Muted"))
        self._update_precisions()

    def _auto_caption(self) -> str:
        best = self.c.device_info(self.c.best_device)
        return f"Currently {best['name']}" if best else "Picks the fastest device available"

    @staticmethod
    def _device_caption(d: dict) -> str:
        backend = {"cuda": "CUDA", "rocm": "ROCm", "xpu": "Intel XPU", "directml": "DirectML", "cpu": "CPU"}[d["backend"]]
        mem = human_bytes(d.get("memory_total"))
        extra = f" · compute {d['capability']}" if d["backend"] == "cuda" and d.get("capability") else \
            (f" · {d['capability']}" if d.get("capability") else "")
        kind = "RAM" if d["kind"] == "cpu" else "VRAM"
        return f"{backend} · {mem} {kind}{extra}"

    def _device_chosen(self, radio) -> None:
        self.c.settings.device.device = radio.property("device")
        self.c.save()
        self._update_precisions()
        self._refresh_model_status()

    def _update_precisions(self) -> None:
        device, precision = self.c.resolved_device()
        info = self.c.device_info(device) or {"precisions": ["fp32"], "recommended_precision": "fp32"}
        self.precision.set_enabled_keys({"auto", *info["precisions"]})
        chosen = self.c.settings.device.precision
        if chosen != "auto" and chosen not in info["precisions"]:
            chosen = "auto"
        self.precision.set_value(chosen)
        notes = {
            "bf16": "BF16 halves memory with no audible loss. Best on RTX 30-series and newer, Arc and Radeon 7000+.",
            "fp16": "FP16 halves memory. Can be unstable on some models; use it if BF16 isn't offered.",
            "fp32": "FP32 is the safest choice on older GPUs and CPUs, and uses twice the memory.",
        }
        self.precision_hint.setText(f"Auto uses {precision.upper()} on this device. {notes[precision]}")

    def _precision_chosen(self, key: str) -> None:
        self.c.settings.device.precision = key
        self.c.save()
        self._update_precisions()
        self._refresh_model_status()

    def _model_id_changed(self) -> None:
        self.c.settings.device.model = self.model_id.text().strip() or self.c.settings.device.model
        self.c.save()

    def _tn_changed(self, on: bool) -> None:
        self.c.settings.device.text_normalization = on
        self.c.save()

    def _autoload_changed(self, on: bool) -> None:
        self.c.settings.device.load_on_start = on
        self.c.save()

    def _refresh_model_status(self) -> None:
        st = self.c.model_status
        ready = self.c.engine.is_ready
        self.model_bar.hide()
        self.cancel_load_btn.hide()
        if st.get("loaded"):
            dev = self.c.device_info(st["device"]) or {"name": st["device"]}
            want = self.c.resolved_device()
            stale = want != (st["device"], st["precision"])
            text = f"Model loaded on {dev['name']} · {st['precision'].upper()}"
            if stale:
                text += "  ·  Reload to apply your new choice"
            self.model_state.setText(text)
            self.load_btn.setText("Reload model" if stale else "Loaded")
            self.load_btn.setEnabled(stale and ready)
            self.unload_btn.setEnabled(ready)
        else:
            err = st.get("error")
            downloaded = self.c.model_downloaded()
            if err:
                text = f"Couldn't load: {err}"
            elif downloaded:
                text = "Model downloaded · not loaded"
            else:
                text = "Model not downloaded yet · about 3 GB once, then it works offline"
            self.model_state.setText(text)
            self.model_state.setToolTip(str(self.c.model_folder()))
            self.load_btn.setText("Load model" if downloaded else "Download and load")
            self.load_btn.setEnabled(ready and not self.c.loading)
            self.unload_btn.setEnabled(False)

    def _model_progress(self, f: float, msg: str) -> None:
        self.model_bar.show()
        if f < 0:
            self.model_bar.setRange(0, 0)
        else:
            self.model_bar.setRange(0, 1000)
            self.model_bar.setValue(int(f * 1000))
        self.model_state.setText(msg)
        self.load_btn.setEnabled(False)
        self.cancel_load_btn.setVisible(self.c.loading)

    def _memory(self, m: dict) -> None:
        total, alloc = m.get("total"), m.get("allocated")
        if total and alloc is not None:
            free = m.get("free") or 0
            used_all = total - free if free else alloc
            self.mem_label.setText(f"Timbre {human_bytes(alloc)} · all apps {human_bytes(used_all)} of {human_bytes(total)}")
            self.mem_bar.show()
            self.mem_bar.setValue(int(1000 * used_all / total))
        elif alloc:
            self.mem_label.setText(f"Timbre {human_bytes(alloc)}")
            self.mem_bar.hide()
        else:
            self.mem_label.setText("Shared with system RAM" if self.c.model_status.get("device") == "cpu" else "—")
            self.mem_bar.hide()

    # ........................................................... runtime
    def _build_runtime_card(self) -> None:
        card = self.runtime_card
        self.runtime_status = label("", "Muted", wrap=True)
        restart = button("Restart engine", icon="refresh")
        restart.clicked.connect(self.c.restart_engine)
        log = button("Engine log", icon="file")
        log.clicked.connect(lambda: LogDialog(self.c, self).exec())
        card.add(hbox(label("Compute runtime", "SectionTitle"), None, log, restart),
                 self.runtime_status,
                 label("Each runtime is a private PyTorch build for one GPU family. "
                       "Install the one recommended for this PC; you can keep several and switch.", "Hint", wrap=True))
        self.tiles = QWidget()
        self.tiles_layout = QVBoxLayout(self.tiles)
        self.tiles_layout.setContentsMargins(0, 0, 0, 0)
        self.tiles_layout.setSpacing(8)
        card.add(self.tiles)

        adv = Section("Advanced", expanded=False)
        self.custom_python = PathField("Path to python.exe", filter="Python (python.exe)")
        self.custom_python.set_value(self.c.settings.python_path)
        use_custom = button("Use this environment")
        use_custom.clicked.connect(self._use_custom)
        clear_custom = button("Stop using it", "ghost")
        clear_custom.clicked.connect(self._clear_custom)
        self.index_override = QLineEdit()
        self.index_override.setPlaceholderText("Package index for the next install (optional)")
        adv.add(Field("Existing Python environment", self.custom_python,
                      "Any environment with PyTorch and the packages in runtimes.json works, "
                      "for example a ROCm or Conda setup you manage yourself."),
                hbox(None, clear_custom, use_custom),
                Field("Custom PyTorch index URL", self.index_override,
                      "Overrides the index for the runtime you install next, e.g. an AMD per-GPU wheel index."))
        card.add(adv)
        self._fill_tiles()

    def _fill_tiles(self) -> None:
        while self.tiles_layout.count():
            w = self.tiles_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        vs = runtime.variants()
        active = self.c.python_source
        order = [self.recommended] + [k for k in vs if k != self.recommended]
        for key in order:
            v = vs[key]
            self.tiles_layout.addWidget(VariantTile(v, key == self.recommended, key == active,
                                                    self._install, self._use_variant))

    def _install(self, variant) -> None:
        if self.c.generating or self.c.loading:
            QMessageBox.information(self, "Install runtime", "Wait for the current job to finish first.")
            return
        dlg = InstallDialog(variant, self.index_override.text().strip(), self)
        dlg.exec()
        if dlg.ok:
            self._use_variant(variant)

    def _use_variant(self, variant) -> None:
        self.c.settings.runtime_variant = variant.key
        self.c.settings.python_path = ""
        self.c.settings.setup_done = True
        self.c.save()
        self.c.restart_engine()
        self._fill_tiles()

    def _use_custom(self) -> None:
        path = self.custom_python.value()
        if not path.lower().endswith("python.exe"):
            QMessageBox.information(self, "Python environment", "Choose a python.exe file.")
            return
        self.c.settings.python_path = path
        self.c.settings.setup_done = True
        self.c.save()
        self.c.restart_engine()
        self._fill_tiles()

    def _clear_custom(self) -> None:
        self.c.settings.python_path = ""
        self.custom_python.set_value("")
        self.c.save()
        self.c.restart_engine()
        self._fill_tiles()

    def _refresh_runtime_status(self) -> None:
        state = self.c.engine.state
        names = {"ready": ("Running", "success"), "starting": ("Starting", ""),
                 "stopped": ("Not running", "warning"), "crashed": ("Stopped unexpectedly", "warning")}
        text, kind = names.get(state, (state, ""))
        self.engine_badge.setText(f"Engine · {text}")
        self.engine_badge.setObjectName({"success": "BadgeSuccess", "warning": "BadgeWarning"}.get(kind, "Badge"))
        self.engine_badge.style().unpolish(self.engine_badge)
        self.engine_badge.style().polish(self.engine_badge)
        rt = self.c.engine.runtime
        source = {"custom": "your Python environment", "development": "the development environment"}.get(
            self.c.python_source, (runtime.variants().get(self.c.python_source).label + " runtime")
            if self.c.python_source in runtime.variants() else "no runtime")
        if state == "ready" and rt:
            backend = f"CUDA {rt['cuda']}" if rt.get("cuda") else f"ROCm {rt['hip']}" if rt.get("hip") else \
                "Intel XPU" if rt.get("xpu") else "CPU"
            self.runtime_status.setText(f"Using {source} · PyTorch {rt['torch']} · {backend} · Python {rt['python']}")
        elif state in ("stopped", "crashed") and not self.c.python_source:
            self.runtime_status.setText("No runtime installed yet. Install the recommended one below.")
        elif state == "crashed":
            self.runtime_status.setText(f"The engine on {source} stopped. Open the engine log for details.")
        else:
            self.runtime_status.setText(f"Starting {source}…")
        self._refresh_model_status()
        self._fill_tiles()

    # .......................................................... hardware
    def _build_hardware_card(self) -> None:
        card = self.hardware_card
        card.add(label("This PC", "SectionTitle"))
        self.hw_rows = QWidget()
        self.hw_layout = QVBoxLayout(self.hw_rows)
        self.hw_layout.setContentsMargins(0, 0, 0, 0)
        self.hw_layout.setSpacing(0)
        card.add(self.hw_rows)
        self._fill_hardware()

    def _fill_hardware(self) -> None:
        while self.hw_layout.count():
            w = self.hw_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        def row(kind, name, detail, tag=""):
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(0, 8, 0, 8)
            k = label(kind, "Overline")
            k.setFixedWidth(84)
            lay.addWidget(k)
            lay.addWidget(label(name))
            if tag:
                lay.addWidget(badge(tag))
            lay.addStretch(1)
            lay.addWidget(label(detail, "Value"))
            self.hw_layout.addWidget(w)

        if not self.gpus:
            row("GPU", "No graphics adapter found", "")
        for g in self.gpus:
            row("GPU", g.name, f"{human_bytes(g.vram)} · driver {g.driver}",
                g.vendor_label + (" · integrated" if g.integrated else ""))
        row("CPU", self.cpu.name, f"{self.cpu.threads} threads")
        row("Memory", "System RAM", human_bytes(self.cpu.ram))

    def _rescan(self) -> None:
        self.gpus = hardware.gpus()
        self.cpu = hardware.cpu()
        self.recommended = hardware.recommended_variant(self.gpus)
        self._fill_hardware()
        self._fill_tiles()
        if self.c.engine.is_ready:
            self.c.probe()
