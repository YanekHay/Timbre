"""Voice library (saved reference voices) and generation history."""

from __future__ import annotations

import json
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .paths import data_dir, voices_dir


@dataclass
class SavedVoice:
    id: str
    name: str
    audio: str
    transcript: str
    notes: str = ""
    created: float = field(default_factory=time.time)
    source: str = "file"            # file | design | generation


class VoiceLibrary(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.voices: list[SavedVoice] = []
        self.reload()

    def reload(self) -> None:
        items = []
        for meta in voices_dir().glob("*/voice.json"):
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                v = SavedVoice(**{k: data[k] for k in SavedVoice.__dataclass_fields__ if k in data})
                if Path(v.audio).exists():
                    items.append(v)
            except Exception:
                continue
        self.voices = sorted(items, key=lambda v: -v.created)
        self.changed.emit()

    def get(self, vid: str) -> SavedVoice | None:
        return next((v for v in self.voices if v.id == vid), None)

    def add(self, name: str, audio_path: str, transcript: str, notes: str = "", source: str = "file") -> SavedVoice:
        vid = uuid.uuid4().hex[:12]
        folder = voices_dir() / vid
        folder.mkdir(parents=True)
        src = Path(audio_path)
        dest = folder / ("reference" + src.suffix.lower())
        shutil.copy2(src, dest)
        voice = SavedVoice(id=vid, name=name.strip() or "Untitled voice", audio=str(dest),
                           transcript=transcript.strip(), notes=notes.strip(), source=source)
        self._write(voice)
        self.reload()
        return voice

    def update(self, voice: SavedVoice) -> None:
        self._write(voice)
        self.reload()

    def remove(self, vid: str) -> None:
        shutil.rmtree(voices_dir() / vid, ignore_errors=True)
        self.reload()

    @staticmethod
    def _write(voice: SavedVoice) -> None:
        (voices_dir() / voice.id / "voice.json").write_text(
            json.dumps(asdict(voice), indent=2, ensure_ascii=False), encoding="utf-8")


@dataclass
class HistoryItem:
    id: str
    created: float
    text: str
    voice_label: str
    path: str
    duration: float
    sample_rate: int
    format: str
    seed: int
    generation_seconds: float
    peaks: list[float]
    profile: dict


class History(QObject):
    changed = Signal()
    LIMIT = 500

    def __init__(self):
        super().__init__()
        self.path = data_dir() / "history.json"
        self.items: list[HistoryItem] = []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.items = [HistoryItem(**r) for r in raw]
        except Exception:
            self.items = []

    def add(self, item: HistoryItem) -> None:
        # Keep the stored envelope small; the player re-reads it at full size when needed.
        step = max(1, len(item.peaks) // 400)
        item.peaks = [max(item.peaks[i:i + step]) for i in range(0, len(item.peaks), step)]
        self.items.insert(0, item)
        del self.items[self.LIMIT:]
        self._save()

    def remove(self, hid: str) -> None:
        self.items = [i for i in self.items if i.id != hid]
        self._save()

    def clear(self) -> None:
        self.items = []
        self._save()

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(i) for i in self.items], ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)
        self.changed.emit()
