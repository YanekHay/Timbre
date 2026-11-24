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


MODEL_MARKER = ".timbre-model.json"   # written by engine/model_store.py after a verified download


def models_dir(custom: str = "") -> Path:
    """Where downloaded model weights live (Settings → Storage can change it)."""
    return Path(custom) if custom else data_dir() / "models"


def model_folder(custom: str, repo_id: str) -> Path:
    return models_dir(custom) / repo_id.split("/")[-1]


def model_downloaded(folder: Path) -> bool:
    import json
    try:
        info = json.loads((folder / MODEL_MARKER).read_text(encoding="utf-8"))
        return all((folder / f["name"]).is_file() and (folder / f["name"]).stat().st_size == f["size"]
                   for f in info["files"])
    except Exception:
        return False


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
