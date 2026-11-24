"""Ming-3.0-tts backend: model download, loading, synthesis with progress and cancellation."""

from __future__ import annotations

import gc
import os
import re
import threading
import time
from pathlib import Path

import torch

import devices
import model_store
import postprocess

DEFAULT_MODEL = "inclusionAI/Ming-3.0-tts-0.5B"
REQUIRED_FILES = ("model.safetensors", "config.json", "campplus.onnx", "tokenizer.json", "tokenizer_config.json")


class Cancelled(Exception):
    pass


class _Progress:
    """Turns the model's per-step decode loop into a smooth 0..1 progress value."""

    def __init__(self):
        self.reset(1, lambda *_: None, threading.Event())

    def reset(self, total_fragments, emit, cancel_event):
        self.total = max(1, total_fragments)
        self.done = 0
        self.step = 0
        self.chars = 1
        self.steps_per_char = 0.55        # adapted after every fragment
        self.emit = emit
        self.cancel = cancel_event
        self._last = 0.0

    def begin_fragment(self, text):
        self.step = 0
        self.chars = max(1, len(text))

    def on_step(self, step):
        if self.cancel.is_set():
            raise Cancelled()
        self.step = step
        now = time.monotonic()
        if now - self._last > 0.12:
            self._last = now
            expected = self.chars * self.steps_per_char
            inner = min(step / max(expected, 1), 0.97)
            self.emit((self.done + inner) / self.total,
                      f"Generating part {self.done + 1} of {self.total}")

    def end_fragment(self):
        if self.step:
            observed = self.step / self.chars
            self.steps_per_char = 0.5 * self.steps_per_char + 0.5 * observed
        self.done += 1
        self.emit(self.done / self.total, f"Generated part {self.done} of {self.total}")


PROGRESS = _Progress()


class _StepTqdm:
    """Drop-in replacement for tqdm in the decode loop."""

    def __init__(self, iterable=None, *args, **kwargs):
        self.iterable = iterable

    def __iter__(self):
        for i, item in enumerate(self.iterable):
            PROGRESS.on_step(i)
            yield item

    def update(self, *a, **k): pass
    def close(self): pass
    def set_description(self, *a, **k): pass


def _install_hooks():
    import modeling_bailingmm
    modeling_bailingmm.tqdm = _StepTqdm


# ---------------------------------------------------------------- weights
def ensure_model(model_id: str, models_dir: str, emit, cancel: threading.Event) -> str:
    """A local folder with complete weights. Repo ids are downloaded once into models_dir."""
    if os.path.isdir(model_id):
        missing = [f for f in REQUIRED_FILES if not os.path.isfile(os.path.join(model_id, f))]
        if missing:
            raise FileNotFoundError(f"The model folder {model_id} is incomplete; missing {', '.join(missing)}. "
                                    "Choose another folder in Devices → Advanced.")
        return model_id
    try:
        return model_store.ensure(model_id, models_dir, emit, cancel)
    except model_store.DownloadCancelled:
        raise Cancelled()


# ---------------------------------------------------------------- backend
class MingBackend:
    def __init__(self):
        self.tts = None
        self.device_id = None
        self.precision = None
        self.model_id = None
        _install_hooks()

    @property
    def loaded(self) -> bool:
        return self.tts is not None

    def status(self) -> dict:
        return {"loaded": self.loaded, "device": self.device_id,
                "precision": self.precision, "model": self.model_id,
                "sample_rate": self.tts.sample_rate if self.tts else None}

    def load(self, device_id: str, precision: str, model_id: str, text_normalization: bool, emit,
             models_dir: str = "", cancel: threading.Event | None = None):
        if self.loaded and (device_id, precision, model_id) == (self.device_id, self.precision, self.model_id):
            return self.status()
        self.unload()
        local = ensure_model(model_id, models_dir, lambda f, m: emit(f, "download", m),
                             cancel or threading.Event())
        emit(None, "load", "Loading the model")

        if text_normalization:
            try:
                import pynini  # noqa: F401
            except Exception:
                text_normalization = False

        from ming_tts import MingTTS
        t0 = time.time()
        self.tts = MingTTS(local, device=devices.to_torch_device(device_id),
                           text_normalization=text_normalization,
                           dtype=devices.resolve_dtype(precision))
        self.device_id, self.precision, self.model_id = device_id, precision, model_id
        self.text_normalization = text_normalization
        emit(1.0, "load", f"Ready in {time.time() - t0:.1f}s")
        return {**self.status(), "text_normalization": text_normalization,
                "memory": devices.memory_stats(device_id)}

    def unload(self):
        if self.tts is None:
            return
        self.tts = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        xpu = getattr(torch, "xpu", None)
        if xpu is not None and xpu.is_available():
            xpu.empty_cache()

    # .......................................................... synthesis
    @staticmethod
    def _task_kwargs(voice: dict, language: str | None) -> dict:
        mode = voice["mode"]
        lang = None if language in (None, "", "auto") else language
        if mode == "preset":
            return dict(task="IP", controls={"ip": voice["preset"]}, use_zero_spk_emb=True, language_id=lang)
        if mode == "design":
            if not voice.get("description", "").strip():
                raise ValueError("Describe the voice you want to design.")
            return dict(task="VOICE_DESIGN", controls={"style": voice["description"].strip()},
                        use_zero_spk_emb=True, language_id=lang)
        if mode == "direct":
            if not voice.get("instruction", "").strip():
                raise ValueError("Write an instruction for how the text should be delivered.")
            return dict(task="FREEFORM", instruction=voice["instruction"].strip(),
                        use_zero_spk_emb=True, language_id=lang)
        if mode == "clone":
            ref = voice.get("reference_audio")
            if not ref or not Path(ref).exists():
                raise ValueError("Choose a reference recording to clone.")
            delivery = voice.get("delivery", "natural")
            if delivery == "emotion":
                return dict(task="EMOTION", controls={"emotion": voice.get("emotion", "中性")},
                            prompt_wav_path=ref, use_spk_emb=True, language_id=lang)
            if delivery == "prosody":
                return dict(task="BASIC", controls={
                    "speed": voice.get("speed", "中速"), "pitch": voice.get("pitch", "中"),
                    "volume": voice.get("volume", "中")},
                    prompt_wav_path=ref, use_spk_emb=True, language_id=lang)
            transcript = (voice.get("reference_text") or "").strip()
            if not transcript:
                raise ValueError("Type the exact words spoken in the reference recording.")
            return dict(task="TTS", prompt_wav_path=ref, prompt_text=transcript,
                        use_spk_emb=True, language_id=lang)
        raise ValueError(f"Unknown voice mode {mode!r}")

    def synthesize(self, request: dict, cancel_event: threading.Event, emit) -> dict:
        if not self.loaded:
            raise RuntimeError("The model is not loaded.")
        import tts_tasks

        text = request["text"].strip()
        if not text:
            raise ValueError("There is no text to speak.")
        gen = request.get("generation", {})
        out_cfg = request.get("output", {})
        task_kwargs = self._task_kwargs(request["voice"], request.get("language"))

        seed = int(gen.get("seed", -1))
        if seed < 0:
            seed = int.from_bytes(os.urandom(4), "little") & 0x7FFFFFFF
        torch.manual_seed(seed)

        pause_ms = float(gen.get("paragraph_pause_ms", 0) or 0)
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()] if pause_ms > 0 else [text]
        raw_text = bool(gen.get("raw_text", False))
        max_length = int(gen.get("max_length", 24))

        # Pre-count fragments for an honest progress bar.
        probe = tts_tasks.build_task_generation_kwargs(
            text=paragraphs[0], **{k: v for k, v in task_kwargs.items()
                                   if k in ("task", "controls", "instruction", "language_id",
                                            "prompt_wav_path", "prompt_text", "use_spk_emb",
                                            "use_zero_spk_emb")})
        total = 0
        for p in paragraphs:
            total += 1 if raw_text else len(self.tts.prepare_text(
                p, probe["taskname"], probe["text_language"], max_length))

        PROGRESS.reset(total, lambda f, m: emit(f, "generate", m), cancel_event)
        original_generate = self.tts.model.generate

        def generate_hook(*args, **kwargs):
            PROGRESS.begin_fragment(kwargs.get("text", ""))
            out = original_generate(*args, **kwargs)
            PROGRESS.end_fragment()
            return out

        self.tts.model.generate = generate_hook
        sr = self.tts.sample_rate
        t0 = time.time()
        if torch.cuda.is_available() and str(self.device_id).startswith("cuda"):
            torch.cuda.reset_peak_memory_stats()
        try:
            pieces = []
            for i, p in enumerate(paragraphs):
                wav = self.tts.synthesize(
                    text=p, cfg=float(gen.get("cfg", 2.0)), sigma=float(gen.get("sigma", 0.25)),
                    temperature=float(gen.get("temperature", 0.0)), max_length=max_length,
                    max_decode_steps=int(gen.get("max_decode_steps", 1000)),
                    trim_silence=bool(gen.get("trim_silence", True)), raw_text=raw_text,
                    **task_kwargs)
                pieces.append(wav.float().cpu())
                if i < len(paragraphs) - 1:
                    pieces.append(torch.zeros(1, int(sr * pause_ms / 1000)))
        finally:
            self.tts.model.generate = original_generate
        wave = torch.cat(pieces, dim=-1)
        gen_seconds = time.time() - t0

        emit(1.0, "encode", "Encoding")
        audio, out_sr = postprocess.process(wave, sr, out_cfg)
        path = postprocess.encode(audio, out_sr, Path(request["output_path"]), out_cfg)
        duration = audio.shape[0] / out_sr
        return {
            "path": str(path), "duration": duration, "sample_rate": out_sr,
            "channels": int(audio.shape[1]), "seed": seed,
            "generation_seconds": gen_seconds, "rtf": gen_seconds / max(duration, 1e-6),
            "peaks": postprocess.peaks(audio), "fragments": total,
            "memory": devices.memory_stats(self.device_id),
        }
