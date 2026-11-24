"""Application controller: owns the engine, settings, library and history.

Pages talk to the controller; the controller talks to the engine.
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from . import catalog, runtime
from .engine_client import EngineClient
from .library import History, HistoryItem, VoiceLibrary
from .settings import Profile, SettingsStore, to_dict


def _slug(text: str, limit: int = 40) -> str:
    text = re.sub(r"\[[^\]]+\]", "", text)
    words = re.findall(r"[\w']+", text)[:6]
    s = "-".join(words).lower()
    s = re.sub(r"[^\w\-]+", "", s)
    return s[:limit].strip("-") or "take"


class Controller(QObject):
    engineStateChanged = Signal(str)
    devicesChanged = Signal(list)
    modelStatusChanged = Signal(dict)
    modelProgress = Signal(float, str)          # fraction, message (load / download)
    generationStarted = Signal()
    generationProgress = Signal(float, str)
    generationFinished = Signal(object)         # HistoryItem
    generationFailed = Signal(str, str)         # message, kind
    needsSetup = Signal()
    toast = Signal(str)
    memoryChanged = Signal(dict)

    def __init__(self):
        super().__init__()
        self.store = SettingsStore()
        self.settings = self.store.settings
        self.engine = EngineClient(self)
        self.library = VoiceLibrary()
        self.history = History()
        self.devices: list[dict] = []
        self.best_device = "cpu"
        self.model_status: dict = {"loaded": False}
        self.loading = False
        self.generating = False
        self.python_source = ""
        self.batch_running = False      # the player stays quiet while a batch runs
        self._queued_generation: tuple | None = None
        self.engine.stateChanged.connect(self._engine_state)
        self.memory_timer = QTimer(self, interval=2500, timeout=self._poll_memory)

    # ------------------------------------------------------------- engine
    def start_engine(self) -> bool:
        python, source = runtime.resolve_python(self.settings)
        self.python_source = source
        if not python:
            self.needsSetup.emit()
            return False
        self.engine.start(python)
        return True

    def restart_engine(self) -> None:
        self.model_status = {"loaded": False}
        self.modelStatusChanged.emit(self.model_status)
        self.engine.stop()
        self.start_engine()

    def _engine_state(self, state: str) -> None:
        self.engineStateChanged.emit(state)
        if state == "ready":
            self.probe()
        elif state in ("crashed", "stopped"):
            self.loading = self.generating = False
            self.model_status = {"loaded": False}
            self.modelStatusChanged.emit(self.model_status)
            self.memory_timer.stop()

    def probe(self) -> None:
        def done(msg):
            self.devices = msg["devices"]
            self.best_device = msg["best"]
            self.devicesChanged.emit(self.devices)
            # Never start a multi-GB download unprompted: auto-load only weights already on disk.
            if (self.settings.device.load_on_start and not self.model_status.get("loaded")
                    and self.model_downloaded()):
                self.load_model()
            else:
                self.modelStatusChanged.emit(self.model_status)
        self.engine.request("probe", on_result=done)

    def resolved_device(self) -> tuple[str, str]:
        cfg = self.settings.device
        ids = {d["id"]: d for d in self.devices}
        device = cfg.device if cfg.device in ids else self.best_device
        info = ids.get(device, {"precisions": ["fp32"], "recommended_precision": "fp32"})
        precision = cfg.precision if cfg.precision in info["precisions"] else info["recommended_precision"]
        return device, precision

    def device_info(self, device_id: str) -> dict | None:
        return next((d for d in self.devices if d["id"] == device_id), None)

    # -------------------------------------------------------------- model
    def load_model(self, then=None) -> None:
        if not self.engine.is_ready or self.loading:
            return
        device, precision = self.resolved_device()
        self.loading = True
        self.modelProgress.emit(0.0, "Preparing model")

        def progress(msg):
            f = msg.get("fraction")
            self.modelProgress.emit(f if f is not None else -1.0, msg.get("message") or "Loading")

        def done(msg):
            self.loading = False
            self.model_status = msg
            self.modelStatusChanged.emit(msg)
            self.memoryChanged.emit(msg.get("memory", {}))
            self.memory_timer.start()
            if then:
                then()

        def failed(msg):
            self.loading = False
            cancelled = msg.get("kind") == "cancelled"
            self.model_status = {"loaded": False} if cancelled else {"loaded": False, "error": msg.get("message")}
            self.modelStatusChanged.emit(self.model_status)
            if cancelled:
                self.toast.emit("Download paused. It picks up where it stopped next time.")
            self.generationFailed.emit("Couldn't load the model: " + msg.get("message", ""), msg.get("kind", ""))

        self.engine.request("load", on_result=done, on_error=failed, on_progress=progress,
                            device=device, precision=precision, model=self.settings.device.model.strip(),
                            models_dir=str(self.models_path()),
                            text_normalization=self.settings.device.text_normalization)

    def models_path(self):
        from .paths import models_dir
        return models_dir(self.settings.models_dir)

    def model_folder(self):
        from .paths import model_folder
        return model_folder(self.settings.models_dir, self.settings.device.model)

    def model_downloaded(self) -> bool:
        """True when the weights are on disk (or the model setting points at a local folder)."""
        from pathlib import Path
        from .paths import model_downloaded
        model = self.settings.device.model.strip()
        if Path(model).is_dir():
            return True
        return model_downloaded(self.model_folder())

    def unload_model(self) -> None:
        def done(msg):
            self.model_status = msg
            self.modelStatusChanged.emit(msg)
            self.memory_timer.stop()
            self._poll_memory()
        self.engine.request("unload", on_result=done)

    def _poll_memory(self) -> None:
        if self.engine.is_ready:
            self.engine.request("stats", on_result=lambda m: self.memoryChanged.emit(m.get("memory", {})))

    # --------------------------------------------------------- generation
    def voice_label(self, profile: Profile) -> str:
        v = profile.voice
        if v.mode == "preset":
            p = catalog.preset(v.preset)
            return p.name if p else v.preset
        if v.mode == "design":
            return "Designed voice"
        if v.mode == "direct":
            return "Directed voice"
        saved = self.library.get(v.library_id) if v.library_id else None
        return saved.name if saved else (Path(v.reference_audio).stem or "Cloned voice")

    def output_path(self, text: str, profile: Profile, seed: int, name: str = "",
                    subfolder: str = "") -> Path:
        out = profile.output
        now = datetime.now()
        template = out.name_template or "{date}_{time}_{voice}_{text}"
        tokens = {"date": now.strftime("%Y-%m-%d"), "time": now.strftime("%H%M%S"),
                  "voice": _slug(self.voice_label(profile), 24), "text": _slug(text),
                  "seed": str(seed) if seed >= 0 else "random"}
        try:
            stem = template.format(**tokens)
        except (KeyError, IndexError, ValueError):
            stem = "{date}_{time}_{voice}_{text}".format(**tokens)
        if name:                                    # batch items name their own files
            stem = name
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", stem).strip(" .") or "take"
        folder = out.resolved_folder()
        if subfolder:
            folder = folder / (re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", subfolder).strip(" .") or "batch")
        folder.mkdir(parents=True, exist_ok=True)
        ext = {"wav": ".wav", "flac": ".flac", "mp3": ".mp3", "ogg": ".ogg"}[out.format]
        path, n = folder / (stem + ext), 2
        while path.exists():
            path, n = folder / f"{stem}-{n}{ext}", n + 1
        return path

    def generate(self, text: str, profile: Profile, name: str = "", subfolder: str = "") -> None:
        if self.generating:
            return
        if not self.engine.is_ready:
            self.generationFailed.emit("The engine isn't running yet. Set up a runtime in Devices.", "engine")
            return
        if not self.model_status.get("loaded"):
            self.generating = True
            self.generationStarted.emit()
            self.generating = False
            self.load_model(then=lambda: self.generate(text, profile, name, subfolder))
            return

        v = profile.voice
        voice = to_dict(v)
        if v.mode == "clone" and v.library_id:
            saved = self.library.get(v.library_id)
            if saved:
                voice["reference_audio"] = saved.audio
                voice["reference_text"] = saved.transcript
        path = self.output_path(text, profile, profile.generation.seed, name, subfolder)
        self.generating = True
        self.generationStarted.emit()
        started = time.time()
        from_batch = self.batch_running

        def progress(msg):
            f = msg.get("fraction")
            self.generationProgress.emit(f if f is not None else -1.0, msg.get("message", ""))

        def done(msg):
            self.generating = False
            out = profile.output
            item = HistoryItem(
                id=uuid.uuid4().hex[:12], created=started, text=text,
                voice_label=self.voice_label(profile), path=msg["path"], duration=msg["duration"],
                sample_rate=msg["sample_rate"],
                format=out.format if out.format in ("mp3", "ogg") else f"{out.format}-{out.bit_depth}",
                seed=msg["seed"], generation_seconds=msg["generation_seconds"],
                peaks=msg.get("peaks", []), profile=to_dict(profile))
            full_peaks = list(item.peaks)
            self.history.add(item)
            item.peaks = full_peaks
            self.memoryChanged.emit(msg.get("memory", {}))
            item.from_batch = from_batch
            self.generationFinished.emit(item)
            if out.open_folder_after:
                from .ui.player import reveal_in_explorer
                reveal_in_explorer(msg["path"])

        def failed(msg):
            self.generating = False
            self.generationFailed.emit(msg.get("message", "Generation failed."), msg.get("kind", ""))
            if msg.get("kind") == "oom":
                self.model_status = {"loaded": False}
                self.modelStatusChanged.emit(self.model_status)

        self.engine.request("generate", on_result=done, on_error=failed, on_progress=progress,
                            text=text, voice=voice, language=v.language,
                            generation=to_dict(profile.generation), output=to_dict(profile.output),
                            output_path=str(path))

    def cancel(self) -> None:
        self.engine.cancel()

    def save(self) -> None:
        self.store.save()

    def shutdown(self) -> None:
        self.save()
        self.engine.stop()
