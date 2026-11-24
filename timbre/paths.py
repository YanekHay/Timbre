"""Filesystem locations. Works both from source and from a PyInstaller build."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "Timbre"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Folder holding engine/, runtimes.json and bin/ (the project root from source)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = data_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def runtimes_dir() -> Path:
    return data_dir() / "runtimes"


def voices_dir() -> Path:
    path = data_dir() / "voices"
    path.mkdir(parents=True, exist_ok=True)
    return path


def profiles_dir() -> Path:
    path = data_dir() / "profiles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_output_dir() -> Path:
    music = Path.home() / "Music"
    return (music if music.exists() else Path.home()) / APP_NAME


def engine_script() -> Path:
    return resource_root() / "engine" / "worker.py"


def manifest_path() -> Path:
    return resource_root() / "runtimes.json"


def uv_executable() -> str | None:
    bundled = resource_root() / "bin" / "uv.exe"
    if bundled.exists():
        return str(bundled)
    return shutil.which("uv")


BUNDLED_MODEL_NAME = "Ming-3.0-tts-0.5B"


def bundled_model_dir() -> Path | None:
    """Model weights shipped with the installer ({app}\\models\\...), or next to the source tree."""
    roots = [Path(sys.executable).parent] if is_frozen() else []
    roots.append(resource_root())
    for root in roots:
        folder = root / "models" / BUNDLED_MODEL_NAME
        if (folder / "model.safetensors").is_file() and (folder / "config.json").is_file():
            return folder
    return None


def dev_python() -> Path | None:
    """When running from source, reuse a nearby virtualenv that already has torch."""
    if is_frozen():
        return None
    here = resource_root()
    for folder in (here, *here.parents[:2]):
        candidate = folder / ".venv" / "Scripts" / "python.exe"
        if candidate.exists() and (folder / ".venv" / "Lib" / "site-packages" / "torch").exists():
            return candidate
    return None
