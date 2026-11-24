"""Typed settings with tolerant JSON persistence, plus Studio profiles."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path

from .paths import data_dir, default_output_dir, profiles_dir

DEFAULT_MODEL = "inclusionAI/Ming-3.0-tts-0.5B"


@dataclass
class VoiceConfig:
    mode: str = "preset"              # preset | design | direct | clone
    preset: str = "UK_George"
    description: str = ""
    instruction: str = ""
    library_id: str = ""
    reference_audio: str = ""
    reference_text: str = ""
    delivery: str = "natural"         # natural | emotion | prosody
    emotion: str = "中性"
    speed: str = "中速"
    pitch: str = "中"
    volume: str = "中"
    language: str = "auto"


@dataclass
class GenerationConfig:
    cfg: float = 2.0
    sigma: float = 0.25
    temperature: float = 0.0
    max_length: int = 24
    max_decode_steps: int = 1000
    paragraph_pause_ms: int = 350
    seed: int = -1
    trim_silence: bool = True
    raw_text: bool = False


@dataclass
class OutputConfig:
    format: str = "wav"               # wav | flac | mp3 | ogg
    bit_depth: str = "24"             # 16 | 24 | 32f
    quality: float = 0.9              # mp3 / ogg
    sample_rate: int = 0              # 0 = native (44.1 kHz)
    channels: int = 1
    normalize: str = "loudness"       # loudness | peak | off
    target_lufs: float = -18.0
    peak_db: float = -1.0
    ceiling_db: float = -1.0
    fade_in_ms: int = 0
    fade_out_ms: int = 15
    pad_start_ms: int = 0
    pad_end_ms: int = 150
    highpass_hz: int = 0
    folder: str = ""
    name_template: str = "{date}_{time}_{voice}_{text}"
    open_folder_after: bool = False

    def resolved_folder(self) -> Path:
        return Path(self.folder) if self.folder else default_output_dir()


@dataclass
class Profile:
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


@dataclass
class DeviceConfig:
    device: str = "auto"              # auto | cuda:0 | xpu:0 | cpu ...
    precision: str = "auto"           # auto | bf16 | fp16 | fp32
    model: str = DEFAULT_MODEL
    text_normalization: bool = False
    load_on_start: bool = True


@dataclass
class AppSettings:
    theme: str = "system"
    python_path: str = ""
    runtime_variant: str = ""
    models_dir: str = ""              # "" = %LOCALAPPDATA%\Timbre\models
    device: DeviceConfig = field(default_factory=DeviceConfig)
    studio: Profile = field(default_factory=Profile)
    active_profile: str = ""
    last_text: str = ""
    geometry: str = ""
    setup_done: bool = False


def _load_into(cls, data):
    if not is_dataclass(cls) or not isinstance(data, dict):
        return cls()
    kwargs = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        value = data[f.name]
        default = getattr(cls(), f.name)
        if is_dataclass(default):
            kwargs[f.name] = _load_into(type(default), value)
        elif isinstance(default, bool):
            kwargs[f.name] = bool(value)
        elif isinstance(default, (int, float)) and isinstance(value, (int, float)):
            kwargs[f.name] = type(default)(value)
        elif isinstance(default, str) and isinstance(value, str):
            kwargs[f.name] = value
    return cls(**kwargs)


def to_dict(obj) -> dict:
    return asdict(obj)


def from_dict(cls, data):
    return _load_into(cls, data)


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "settings.json"
        self.settings = self.load()

    def load(self) -> AppSettings:
        try:
            return from_dict(AppSettings, json.loads(self.path.read_text(encoding="utf-8")))
        except Exception:
            return AppSettings()

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(to_dict(self.settings), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)


# ---------------------------------------------------------------- profiles
def _slug(name: str) -> str:
    return re.sub(r"[^\w\- ]+", "", name).strip() or "profile"


def list_profiles() -> list[str]:
    return sorted(p.stem for p in profiles_dir().glob("*.json"))


def save_profile(name: str, profile: Profile) -> Path:
    path = profiles_dir() / f"{_slug(name)}.json"
    path.write_text(json.dumps(to_dict(profile), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_profile(name_or_path: str) -> Profile:
    path = Path(name_or_path)
    if not path.suffix:
        path = profiles_dir() / f"{name_or_path}.json"
    return from_dict(Profile, json.loads(path.read_text(encoding="utf-8")))


def delete_profile(name: str) -> None:
    (profiles_dir() / f"{name}.json").unlink(missing_ok=True)
